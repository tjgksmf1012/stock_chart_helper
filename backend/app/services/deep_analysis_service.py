"""한 종목 정밀분석 — 과거 패턴 성적표 + 장기 맥락.

차트 페이지의 [정밀분석] 버튼으로만 호출되는 온디맨드 심층 분석.
스캔용 경량 분석과 달리 수년치 일봉 이력을 슬라이딩 윈도우로 리플레이해
"이 종목에서 이 패턴이 과거에 어떻게 끝났나"를 직접 계산한다.
결과는 12시간 캐시 (free tier 보호).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from ..core.redis import cache_get, cache_set
from .backtest_engine import _is_bullish
from .data_fetcher import get_data_fetcher
from .pattern_engine import PatternEngine, PatternResult

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "deep:v1"
_CACHE_TTL = 43200  # 12시간

# 동시 실행 1개 제한 — 리플레이는 CPU 집약적이라 free tier(0.1 CPU)에서
# 여러 건이 겹치면 헬스체크까지 밀려 서비스가 재시작될 수 있다.
_replay_semaphore = asyncio.Semaphore(1)

# 진행률 추적 (단일 인스턴스 전제 — Render free tier는 1대)
# {code: {"done": int, "total": int}} — 리플레이 스레드가 직접 갱신
_replay_progress: dict[str, dict[str, int]] = {}


def get_deep_progress(symbol_code: str) -> dict[str, Any]:
    """진행 중인 정밀분석의 리플레이 진행률. 미실행이면 running=False."""
    progress = _replay_progress.get(symbol_code)
    if not progress:
        return {"running": False, "done": 0, "total": 0}
    return {"running": True, **progress}

# 일봉 리플레이 설정 — 백테스트(window 60/step 10)보다 촘촘하게, 단 중복은 시그니처로 제거
_LOOKBACK_DAYS = 2200      # ~6년 달력일 ≈ 1,500 거래일
_WINDOW = 120              # 패턴 탐지 구간 (봉)
_STEP = 5                  # 윈도우 이동 간격
_MAX_FORWARD = 40          # 결과 판정 최대 추적 (봉)
_MAX_CASES_RETURNED = 30   # 응답에 담는 최근 사례 수


def _case_signature(pattern: PatternResult) -> tuple[str, str]:
    """같은 구조가 인접 윈도우에서 반복 탐지되는 것을 걸러내는 시그니처."""
    last_dt = ""
    for point in pattern.key_points:
        dt = str(point.get("dt") or "")
        if dt > last_dt:
            last_dt = dt
    return (pattern.pattern_type, last_dt[:10])


def _replay_pattern_cases_sync(bars_df: pd.DataFrame, progress_code: str | None = None) -> list[dict[str, Any]]:
    """과거 이력을 슬라이딩 윈도우로 리플레이해 확정 패턴의 결과를 수집."""
    engine = PatternEngine()
    n = len(bars_df)
    cases: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    window_starts = list(range(0, max(0, n - _WINDOW - 1), _STEP))
    total_windows = max(1, len(window_starts))

    for window_no, start_idx in enumerate(window_starts, start=1):
        if progress_code is not None:
            _replay_progress[progress_code] = {"done": window_no, "total": total_windows}
        window_df = bars_df.iloc[start_idx:start_idx + _WINDOW].copy().reset_index(drop=True)
        try:
            patterns = engine.detect_all(window_df, timeframe="1d")
        except Exception:
            continue

        for pattern in patterns:
            if pattern.state != "confirmed":
                continue
            if pattern.target_level is None or pattern.invalidation_level is None:
                continue
            signature = _case_signature(pattern)
            if not signature[1] or signature in seen:
                continue
            seen.add(signature)

            entry_price = float(window_df.iloc[-1]["close"])
            signal_date = str(window_df.iloc[-1]["date"])[:10]
            bullish = _is_bullish(pattern.pattern_type)
            forward = bars_df.iloc[start_idx + _WINDOW:start_idx + _WINDOW + _MAX_FORWARD]

            outcome = "timeout"
            bars_to_outcome: int | None = None
            move_pct = 0.0
            mfe = 0.0
            mae = 0.0
            for step_no, (_, bar) in enumerate(forward.iterrows(), start=1):
                high = float(bar["high"])
                low = float(bar["low"])
                if bullish:
                    mfe = max(mfe, (high - entry_price) / max(entry_price, 1e-9))
                    mae = max(mae, (entry_price - low) / max(entry_price, 1e-9))
                    if high >= pattern.target_level:
                        outcome, bars_to_outcome = "success", step_no
                        move_pct = (pattern.target_level - entry_price) / max(entry_price, 1e-9)
                        break
                    if low <= pattern.invalidation_level:
                        outcome, bars_to_outcome = "fail", step_no
                        move_pct = (pattern.invalidation_level - entry_price) / max(entry_price, 1e-9)
                        break
                else:
                    mfe = max(mfe, (entry_price - low) / max(entry_price, 1e-9))
                    mae = max(mae, (high - entry_price) / max(entry_price, 1e-9))
                    if low <= pattern.target_level:
                        outcome, bars_to_outcome = "success", step_no
                        move_pct = (pattern.target_level - entry_price) / max(entry_price, 1e-9)
                        break
                    if high >= pattern.invalidation_level:
                        outcome, bars_to_outcome = "fail", step_no
                        move_pct = (pattern.invalidation_level - entry_price) / max(entry_price, 1e-9)
                        break

            if outcome == "timeout" and len(forward) > 0:
                last_close = float(forward.iloc[-1]["close"])
                move_pct = (last_close - entry_price) / max(entry_price, 1e-9)

            cases.append(
                {
                    "pattern_type": pattern.pattern_type,
                    "signal_date": signal_date,
                    "outcome": outcome,
                    "bars_to_outcome": bars_to_outcome,
                    "move_pct": round(move_pct, 4),
                    "mfe_pct": round(mfe, 4),
                    "mae_pct": round(mae, 4),
                }
            )

    cases.sort(key=lambda case: case["signal_date"])
    return cases


def _summarize_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(case["pattern_type"], []).append(case)

    stats: list[dict[str, Any]] = []
    for pattern_type, rows in grouped.items():
        wins = [row for row in rows if row["outcome"] == "success"]
        losses = [row for row in rows if row["outcome"] == "fail"]
        timeouts = [row for row in rows if row["outcome"] == "timeout"]
        resolved = wins + losses
        resolved_bars = [row["bars_to_outcome"] for row in resolved if row["bars_to_outcome"]]
        stats.append(
            {
                "pattern_type": pattern_type,
                "total": len(rows),
                "wins": len(wins),
                "losses": len(losses),
                "timeouts": len(timeouts),
                "win_rate": round(len(wins) / len(resolved), 3) if resolved else None,
                "avg_bars_to_outcome": round(sum(resolved_bars) / len(resolved_bars), 1) if resolved_bars else None,
                "avg_win_move_pct": round(sum(row["move_pct"] for row in wins) / len(wins), 4) if wins else None,
                "avg_loss_move_pct": round(sum(row["move_pct"] for row in losses) / len(losses), 4) if losses else None,
            }
        )

    stats.sort(key=lambda row: row["total"], reverse=True)
    return stats


def _long_context(bars_df: pd.DataFrame) -> dict[str, Any]:
    """52주 위치·변동성 국면 등 장기 맥락."""
    if bars_df.empty:
        return {}
    closes = pd.to_numeric(bars_df["close"], errors="coerce").dropna()
    if closes.empty:
        return {}
    current = float(closes.iloc[-1])

    year = closes.tail(252)
    week52_high = float(year.max())
    week52_low = float(year.min())
    span = max(week52_high - week52_low, 1e-9)
    week52_position = (current - week52_low) / span

    returns = closes.pct_change().dropna()
    recent_vol = float(returns.tail(20).std()) if len(returns) >= 20 else 0.0
    year_vol = float(returns.tail(252).std()) if len(returns) >= 60 else recent_vol
    if year_vol <= 0:
        regime = "보통"
    elif recent_vol >= year_vol * 1.3:
        regime = "확대"
    elif recent_vol <= year_vol * 0.7:
        regime = "수축"
    else:
        regime = "보통"

    return {
        "week52_high": round(week52_high, 2),
        "week52_low": round(week52_low, 2),
        "week52_position": round(week52_position, 3),
        "volatility_recent_pct": round(recent_vol * 100, 2),
        "volatility_year_pct": round(year_vol * 100, 2),
        "volatility_regime": regime,
    }


async def build_deep_analysis(symbol_code: str) -> dict[str, Any]:
    cache_key = f"{_CACHE_PREFIX}:{symbol_code}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    fetcher = get_data_fetcher()
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    bars_df = await fetcher.get_stock_ohlcv(symbol_code, start, end)

    if bars_df is None or bars_df.empty or len(bars_df) < _WINDOW + 20:
        return {
            "symbol_code": symbol_code,
            "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "available_bars": 0 if bars_df is None else len(bars_df),
            "cases": [],
            "stats": [],
            "long_context": {},
            "note": "이력 데이터가 부족해 정밀분석을 수행하지 못했습니다.",
        }

    bars_df = bars_df.reset_index(drop=True)
    async with _replay_semaphore:
        try:
            cases = await asyncio.to_thread(_replay_pattern_cases_sync, bars_df, symbol_code)
        finally:
            _replay_progress.pop(symbol_code, None)

    result = {
        "symbol_code": symbol_code,
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "available_bars": len(bars_df),
        "case_count": len(cases),
        "cases": cases[-_MAX_CASES_RETURNED:][::-1],  # 최근순
        "stats": _summarize_cases(cases),
        "long_context": _long_context(bars_df),
        "note": "",
    }
    await cache_set(cache_key, result, ttl=_CACHE_TTL)
    return result
