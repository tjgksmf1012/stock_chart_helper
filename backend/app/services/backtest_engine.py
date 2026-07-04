"""
Timeframe-aware lightweight backtesting statistics.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.redis import cache_get, cache_set
from .pattern_engine import PatternEngine, PatternResult, pattern_direction_is_bullish

logger = logging.getLogger(__name__)

BACKTEST_CACHE_KEY = "backtest:pattern_stats"
BACKTEST_TTL = 86400

_DEFAULT_WIN_RATES: dict[str, float] = {
    "double_bottom": 0.58,
    "double_top": 0.56,
    "head_and_shoulders": 0.55,
    "inverse_head_and_shoulders": 0.59,
    "ascending_triangle": 0.60,
    "descending_triangle": 0.57,
    "symmetric_triangle": 0.52,
    "rectangle": 0.54,
    "rising_channel": 0.53,
    "falling_channel": 0.53,
    "cup_and_handle": 0.62,
    "rounding_bottom": 0.60,
    "momentum_breakout": 0.55,
}

_DEFAULT_SAMPLE_SIZES = {"1mo": 12, "1wk": 16, "1d": 20}
_BACKTEST_TIMEFRAMES = ("1mo", "1wk", "1d")
_BACKTEST_UNIVERSE = [
    # KOSPI 핵심 블루칩 (original 15)
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # 네이버
    "005380",  # 현대차
    "051910",  # LG화학
    "006400",  # 삼성SDI
    "035720",  # 카카오
    "068270",  # 셀트리온
    "105560",  # KB금융
    "055550",  # 신한지주
    "247540",  # 에코프로비엠
    "086520",  # 에코프로
    "000270",  # 기아
    "028260",  # 삼성물산
    "096770",  # SK이노베이션
    # 추가 KOSPI 대형주
    "005490",  # POSCO홀딩스
    "066570",  # LG전자
    "207940",  # 삼성바이오로직스
    "373220",  # LG에너지솔루션
    "086790",  # 하나금융지주
    "034730",  # SK㈜
    "017670",  # SK텔레콤
    "030200",  # KT
    "009150",  # 삼성전기
    "010950",  # S-Oil
    "015760",  # 한국전력
    "000810",  # 삼성화재
    "090430",  # 아모레퍼시픽
    "024110",  # IBK기업은행
    "032830",  # 삼성생명
    "003550",  # LG
    "009540",  # HD현대중공업
    "071050",  # 한국금융지주
    "034220",  # LG디스플레이
    # KOSDAQ 대형주
    "302440",  # SK바이오팜
    "041510",  # SM엔터테인먼트
    "352820",  # 하이브
    "035900",  # JYP엔터테인먼트
    "214150",  # 클래시스
    "196170",  # 알테오젠
    # 중형주 확장 — 스캔 유니버스가 시가총액 300억, 거래대금 15억까지 낮아졌는데
    # 백테스트 승률은 여전히 초대형주 40개에서만 뽑히면 중소형 신규 편입 종목엔
    # 안 맞는 승률이 적용된다. 확실히 아는 코드 위주로 중형주 비중을 늘림
    # (다만 실제 300억대 소형주까지는 코드 확인이 어려워 완전히 커버하진 못함).
    "011200",  # HMM
    "010060",  # OCI홀딩스
    "004020",  # 현대제철
    "006800",  # 미래에셋증권
    "016360",  # 삼성증권
    "138040",  # 메리츠금융지주
    "047810",  # 한국항공우주
    "012450",  # 한화에어로스페이스
    "010130",  # 고려아연
    "051900",  # LG생활건강
    "097950",  # CJ제일제당
    "018260",  # 삼성에스디에스
    "271560",  # 오리온
    "112610",  # 씨에스윈드
    "000100",  # 유한양행
    "293490",  # 카카오게임즈
    "259960",  # 크래프톤
    "145020",  # 휴젤
    "000120",  # CJ대한통운
    "010620",  # 현대미포조선
    "011780",  # 금호석유
    "004990",  # 롯데지주
    "023530",  # 롯데쇼핑
    "069960",  # 현대백화점
    "035250",  # 강원랜드
    "021240",  # 코웨이
    "009830",  # 한화솔루션
    "010120",  # LS ELECTRIC
    "011210",  # 현대위아
    "032640",  # LG유플러스
    "018880",  # 한온시스템
]
_BACKTEST_CONFIG = {
    "1mo": {"window": 24, "step": 2, "max_forward": 6, "lookback_days": 3650, "min_bars": 32},
    "1wk": {"window": 36, "step": 3, "max_forward": 12, "lookback_days": 3650, "min_bars": 56},
    "1d": {"window": 60, "step": 10, "max_forward": 40, "lookback_days": 730, "min_bars": 100},
}

_backtest_running = False


def get_backtest_universe() -> list[str]:
    return list(_BACKTEST_UNIVERSE)


def _spread_sample(codes: list[str], count: int) -> list[str]:
    if count <= 0 or not codes:
        return []
    if count >= len(codes):
        return list(codes)
    step = len(codes) / count
    return [codes[int(i * step)] for i in range(count)]


async def get_expanded_backtest_universe(target_size: int = 200) -> list[str]:
    """확률 재보정 학습(scripts/fit_probability_calibration.py) 전용 — 손으로 골라
    유지보수하는 _BACKTEST_UNIVERSE(79종목) 대신, 이미 스캔에 쓰이는 실제 KRX 전체
    유니버스에서 골고루 샘플을 뽑아 학습 표본 다양성을 늘린다.

    hardcoded 리스트를 그냥 더 늘리는 대신 이렇게 하는 이유: 상장폐지/이름 변경된
    종목 코드를 손으로 추가하면 검증 없이 틀린 코드가 섞일 위험이 있다. 실제 KRX
    유니버스(data_fetcher.get_universe(), 이미 스캔에서 매일 쓰는 검증된 데이터)를
    쓰면 그 위험이 없다.

    라이브 유니버스를 못 가져오면(네트워크 제한 등) 기존 고정 리스트로 그대로
    폴백한다 — 이 함수가 있다고 해서 라이브 데이터 없이 새 종목이 생기지는 않는다.
    """
    curated = get_backtest_universe()
    try:
        from .data_fetcher import get_data_fetcher

        universe_df = await get_data_fetcher().get_universe()
    except Exception as exc:
        logger.warning("failed to fetch live universe for expanded backtest set: %s", exc)
        return curated

    if universe_df is None or universe_df.empty or "code" not in universe_df.columns:
        return curated

    names = universe_df.get("name")
    if names is not None:
        is_spac = names.fillna("").astype(str).str.contains("스팩", na=False)
        is_preferred = names.fillna("").astype(str).str.endswith("우", na=False)
        universe_df = universe_df.loc[~(is_spac | is_preferred)]

    live_codes = sorted({str(c) for c in universe_df["code"].tolist()} - set(curated))
    extra_needed = max(0, target_size - len(curated))
    return curated + _spread_sample(live_codes, extra_needed)


def get_backtest_config(timeframe: str) -> dict[str, int]:
    return dict(_BACKTEST_CONFIG.get(timeframe, _BACKTEST_CONFIG["1d"]))


def _edge_score(win_rate: float, avg_mfe_pct: float, avg_mae_pct: float, avg_bars_to_outcome: float, max_forward: int) -> float:
    rr = avg_mfe_pct / max(avg_mae_pct, 0.01)
    rr_score = max(0.0, min(1.0, rr / 2.5))
    mfe_score = max(0.0, min(1.0, avg_mfe_pct / 0.18))
    speed_score = max(0.0, min(1.0, 1 - (avg_bars_to_outcome / max(max_forward, 1))))
    edge = (
        0.42 * win_rate
        + 0.24 * rr_score
        + 0.20 * mfe_score
        + 0.14 * speed_score
    )
    return round(max(0.0, min(1.0, edge)), 3)


def _default_stat_line(pattern_type: str, timeframe: str, win_rate: float, sample_size: int) -> dict[str, float | int | str]:
    mfe_baseline = {"1mo": 0.18, "1wk": 0.11, "1d": 0.075}
    mae_baseline = {"1mo": 0.08, "1wk": 0.05, "1d": 0.035}
    bars_baseline = {"1mo": 4.0, "1wk": 7.0, "1d": 16.0}
    strength = max(0.8, min(1.15, win_rate / 0.55))
    avg_mfe_pct = round(mfe_baseline[timeframe] * strength, 4)
    avg_mae_pct = round(mae_baseline[timeframe] / max(strength, 0.85), 4)
    avg_bars_to_outcome = round(bars_baseline[timeframe], 2)
    return {
        "pattern_type": pattern_type,
        "timeframe": timeframe,
        "win_rate": win_rate,
        "sample_size": sample_size,
        "wins": int(round(win_rate * sample_size)),
        "total": sample_size,
        "avg_mfe_pct": avg_mfe_pct,
        "avg_mae_pct": avg_mae_pct,
        "avg_bars_to_outcome": avg_bars_to_outcome,
        "historical_edge_score": _edge_score(win_rate, avg_mfe_pct, avg_mae_pct, avg_bars_to_outcome, _BACKTEST_CONFIG[timeframe]["max_forward"]),
        # 실제 백테스트가 아니라 손으로 튜닝한 기본값이라는 표시 — real vs guessed를
        # 구분할 방법이 없으면 둘 다 똑같이 신뢰도 있어 보이는 화면으로 나간다.
        "is_synthetic": True,
    }


def _default_stats() -> dict[str, dict[str, dict[str, float | int | str]]]:
    return {
        timeframe: {
            pattern_type: _default_stat_line(pattern_type, timeframe, win_rate, _DEFAULT_SAMPLE_SIZES[timeframe])
            for pattern_type, win_rate in _DEFAULT_WIN_RATES.items()
        }
        for timeframe in _BACKTEST_TIMEFRAMES
    }


def _resolve_bar_outcome(
    high: float, low: float, target: float, invalidation: float, *, bullish: bool
) -> bool | None:
    """단일 봉이 목표가/손절가 중 무엇을 먼저 건드렸는지 판정한다.

    일봉/주봉 OHLC만으로는 봉 안에서 고가와 저가 중 어느 쪽이 먼저 찍혔는지 알 수 없다.
    목표가를 먼저 체크하면 두 값을 모두 건드리는 변동성 큰 봉(돌파 직후 흔함)이 항상
    승리로 집계되어 승률이 구조적으로 부풀려진다. offline_calibration.py의
    simulate_window_outcome()과 동일하게, 손절을 먼저 확인하는 보수적 관행을 따른다.
    Returns True(승)/False(패)/None(둘 다 미도달).
    """
    if bullish:
        if low <= invalidation:
            return False
        if high >= target:
            return True
    else:
        if high >= invalidation:
            return False
        if low <= target:
            return True
    return None


def _bucket_to_stat_line(
    pattern_type: str,
    timeframe: str,
    bucket: dict[str, float | int],
    distinct_stock_count: int | None = None,
) -> dict[str, float | int | str] | None:
    """집계된 wins/total/timeouts 버킷을 통계 라인으로 변환. 표본이 너무 적으면 None."""
    wins = int(bucket["wins"])
    resolved = int(bucket["total"])
    timeouts = int(bucket["timeouts"])
    # timeout(목표·손절 어디에도 안 닿고 흐지부지 끝난 경우)도 시도 횟수에 넣는다.
    # 해소된 표본만으로 승률을 계산하면 "애매하게 끝난 경우"가 통째로 빠져
    # 승률이 실제보다 낙관적으로 보이는 편향이 생긴다.
    attempts = resolved + timeouts
    if attempts < 5 or resolved == 0:
        return None
    avg_mfe_pct = round(float(bucket["mfe_sum"]) / resolved, 4)
    avg_mae_pct = round(float(bucket["mae_sum"]) / resolved, 4)
    avg_bars_to_outcome = round(float(bucket["bars_sum"]) / resolved, 2)
    win_rate = round(wins / attempts, 3)
    resolution_rate = round(resolved / attempts, 3)
    return {
        "pattern_type": pattern_type,
        "timeframe": timeframe,
        "win_rate": win_rate,
        # 슬라이딩 윈도우(step < window)로 만든 표본은 서로 대부분 겹쳐 사실상
        # 독립표본이 아니다 — 신뢰구간 계산(sample_reliability)에 쓰이는
        # "표본수"는 그 중첩을 감안해 할인한 값을 쓴다. win_rate 자체(점 추정치)는
        # 원래 카운트(wins/total)를 그대로 쓴다 — 편향 문제가 아니라 분산 과소평가 문제이므로.
        "sample_size": _effective_sample_size(attempts, timeframe, distinct_stock_count),
        "wins": wins,
        "total": attempts,
        "timeouts": timeouts,
        "resolution_rate": resolution_rate,
        "avg_mfe_pct": avg_mfe_pct,
        "avg_mae_pct": avg_mae_pct,
        "avg_bars_to_outcome": avg_bars_to_outcome,
        "historical_edge_score": _edge_score(
            win_rate,
            avg_mfe_pct,
            avg_mae_pct,
            avg_bars_to_outcome,
            int(_BACKTEST_CONFIG[timeframe]["max_forward"]),
        ),
        "is_synthetic": False,
    }


def _effective_sample_size(total: int, timeframe: str, distinct_stock_count: int | None = None) -> int:
    """겹치는 슬라이딩 윈도우 표본수를 신뢰구간 계산용으로 할인한다.

    window=60/step=10처럼 연속 표본끼리 대부분 겹치면 "표본수"가 부풀려져
    실제보다 신뢰구간이 좁게(과신하게) 나온다. step/window 비율만큼 할인하되,
    이 (패턴, 타임프레임) 버킷에 실제로 기여한 서로 다른 종목 수만큼은 독립 관측으로
    인정해 바닥을 둔다.

    예전엔 이 바닥값으로 항상 전체 유니버스 크기(len(_BACKTEST_UNIVERSE), 79)를 썼다 —
    79종목 중 실제로는 4종목만 어떤 희귀 패턴(예: 월봉 symmetric_triangle)을 만들어냈어도
    마치 79종목 전부가 그 패턴을 확인해준 것처럼 신뢰도가 부풀려지는 문제가 있었다.
    distinct_stock_count를 넘기지 않으면(개별 단위 테스트 등) 기존처럼 유니버스 전체
    크기를 바닥으로 쓴다.
    """
    if total <= 0:
        return 0
    cfg = _BACKTEST_CONFIG.get(timeframe, _BACKTEST_CONFIG["1d"])
    overlap_factor = min(1.0, cfg["step"] / cfg["window"])
    discounted = round(total * overlap_factor)
    universe_floor = len(_BACKTEST_UNIVERSE) if distinct_stock_count is None else max(0, distinct_stock_count)
    floor = min(total, universe_floor)
    return max(1, max(discounted, floor))


def _backtest_stock_sync(timeframe: str, bars_df: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    engine = PatternEngine()
    cfg = _BACKTEST_CONFIG[timeframe]
    n = len(bars_df)
    window = int(cfg["window"])
    step = int(cfg["step"])
    max_forward = int(cfg["max_forward"])

    for start_idx in range(0, max(0, n - window - max_forward), step):
        window_df = bars_df.iloc[start_idx:start_idx + window].copy().reset_index(drop=True)
        patterns: list[PatternResult] = engine.detect_all(window_df)
        for pattern in patterns:
            if pattern.state != "confirmed":
                continue
            if pattern.target_level is None or pattern.invalidation_level is None:
                continue

            forward_bars = bars_df.iloc[start_idx + window:start_idx + window + max_forward]
            win: bool | None = None
            # 대칭삼각형/직사각형/채널처럼 방향이 타입만으로 안 정해지는 패턴은
            # _is_bullish(타입 문자열)만 보면 늘 베어리시로 잘못 취급된다(둘 중
            # 어느 정적 집합에도 없어서). 이 인스턴스가 실제로 어느 방향으로
            # 돌파했는지(target_level 기준)를 보는 pattern_direction_is_bullish를 쓴다.
            bullish = pattern_direction_is_bullish(pattern)
            entry_price = float(window_df.iloc[-1]["close"])
            favorable_excursion = 0.0
            adverse_excursion = 0.0
            bars_to_outcome: int | None = None

            for bar_step, (_, bar) in enumerate(forward_bars.iterrows(), start=1):
                high = float(bar["high"])
                low = float(bar["low"])
                if bullish:
                    favorable_excursion = max(favorable_excursion, max(0.0, (high - entry_price) / max(entry_price, 1e-9)))
                    adverse_excursion = max(adverse_excursion, max(0.0, (entry_price - low) / max(entry_price, 1e-9)))
                else:
                    favorable_excursion = max(favorable_excursion, max(0.0, (entry_price - low) / max(entry_price, 1e-9)))
                    adverse_excursion = max(adverse_excursion, max(0.0, (high - entry_price) / max(entry_price, 1e-9)))
                outcome_here = _resolve_bar_outcome(
                    high, low, pattern.target_level, pattern.invalidation_level, bullish=bullish
                )
                if outcome_here is not None:
                    win = outcome_here
                    bars_to_outcome = bar_step
                    break

            # timeout(목표·손절 미도달)도 별도 outcome으로 기록 — win_rate 집계 단계에서
            # 시도 횟수(분모)에 포함되고, MFE/MAE/bars 평균에서만 제외된다.
            outcome = "timeout" if win is None else ("win" if win else "loss")
            results.append(
                {
                    "pattern_type": pattern.pattern_type,
                    "outcome": outcome,
                    "win": bool(win),  # outcome != timeout일 때만 의미 있음
                    "timeframe": timeframe,
                    "mfe_pct": round(favorable_excursion, 4),
                    "mae_pct": round(adverse_excursion, 4),
                    "bars_to_outcome": bars_to_outcome if bars_to_outcome is not None else max_forward,
                }
            )

    return results


async def run_backtest() -> dict[str, dict[str, dict[str, float | int | str]]]:
    global _backtest_running
    if _backtest_running:
        return await get_pattern_stats_map()

    _backtest_running = True
    try:
        from .data_fetcher import get_data_fetcher

        fetcher = get_data_fetcher()
        aggregated: dict[str, dict[str, dict[str, float | int]]] = {timeframe: {} for timeframe in _BACKTEST_TIMEFRAMES}
        # (패턴, 타임프레임) 버킷마다 실제로 기여한 서로 다른 종목을 추적한다 —
        # _effective_sample_size()가 유니버스 전체 크기 대신 이 값을 신뢰도 바닥으로 쓴다.
        contributing_stocks: dict[str, dict[str, set[str]]] = {timeframe: {} for timeframe in _BACKTEST_TIMEFRAMES}

        for timeframe in _BACKTEST_TIMEFRAMES:
            cfg = _BACKTEST_CONFIG[timeframe]
            for code in _BACKTEST_UNIVERSE:
                try:
                    df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=int(cfg["lookback_days"]))
                    if df.empty or len(df) < int(cfg["min_bars"]):
                        continue
                    stock_results = await asyncio.to_thread(_backtest_stock_sync, timeframe, df)
                    for result in stock_results:
                        pattern_type = result["pattern_type"]
                        bucket = aggregated[timeframe].setdefault(
                            pattern_type,
                            {"wins": 0, "total": 0, "timeouts": 0, "mfe_sum": 0.0, "mae_sum": 0.0, "bars_sum": 0.0},
                        )
                        contributing_stocks[timeframe].setdefault(pattern_type, set()).add(code)
                        # timeout은 wins/mfe/mae/bars 집계에선 빠지지만, 아래 _bucket_to_stat_line
                        # 에서 win_rate 분모(attempts)에는 포함된다.
                        if result.get("outcome") == "timeout":
                            bucket["timeouts"] += 1
                            continue
                        bucket["total"] += 1
                        bucket["mfe_sum"] += float(result["mfe_pct"])
                        bucket["mae_sum"] += float(result["mae_pct"])
                        bucket["bars_sum"] += float(result["bars_to_outcome"])
                        if result.get("outcome") == "win" or result.get("win"):
                            bucket["wins"] += 1
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logger.warning("Backtest failed for %s (%s): %s", code, timeframe, exc)

        stats = _default_stats()
        for timeframe, pattern_counts in aggregated.items():
            for pattern_type, bucket in pattern_counts.items():
                distinct_stock_count = len(contributing_stocks[timeframe].get(pattern_type, ()))
                stat_line = _bucket_to_stat_line(pattern_type, timeframe, bucket, distinct_stock_count)
                if stat_line is not None:
                    stats[timeframe][pattern_type] = stat_line

        await cache_set(BACKTEST_CACHE_KEY, stats, BACKTEST_TTL)
        return stats
    except Exception as exc:
        logger.error("Backtest failed: %s", exc)
        return _default_stats()
    finally:
        _backtest_running = False


async def get_pattern_stats_map() -> dict[str, dict[str, dict[str, float | int | str]]]:
    cached = await cache_get(BACKTEST_CACHE_KEY)
    if cached and isinstance(cached, dict):
        return cached
    asyncio.create_task(run_backtest())
    return _default_stats()


async def get_pattern_stats(pattern_type: str, timeframe: str) -> dict[str, float | int | str]:
    timeframe_key = timeframe if timeframe in _BACKTEST_TIMEFRAMES else "1d"
    stats = await get_pattern_stats_map()
    timeframe_stats = stats.get(timeframe_key) or {}
    pattern_stats = timeframe_stats.get(pattern_type)
    if pattern_stats:
        return pattern_stats

    default_rate = _DEFAULT_WIN_RATES.get(pattern_type, 0.55)
    default_sample = _DEFAULT_SAMPLE_SIZES.get(timeframe_key, 16)
    return {
        **_default_stat_line(pattern_type, timeframe_key, default_rate, default_sample),
    }
