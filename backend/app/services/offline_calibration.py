"""Offline probability calibration: replay history through the live pipeline.

The live calibration report (GET /outcomes/calibration) needs resolved saved
signals, which take weeks to accumulate. This module answers the same question
— "when the model says 65%, does it win 65% of the time?" — immediately, by
walking historical windows per symbol, scoring each window with the *real*
production pipeline (analyze_symbol_dataframe), then resolving the signal
against the bars that actually followed (target vs invalidation touch).

Expensive (one analyze call per window), so results are cached and builds run
as background tasks; callers get {"status": "building"} until ready.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pandas as pd

from ..api.schemas import SymbolInfo
from ..core.redis import cache_get, cache_set
from .analysis_service import analyze_symbol_dataframe
from .backtest_engine import get_backtest_config, get_backtest_universe
from .calibration_service import build_calibration_report
from .pattern_engine import pattern_direction_is_bullish

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "calibration:offline:v1"
_CACHE_TTL = 7 * 86400  # rebuilt weekly at most; refresh=true forces it
# 8 -> 20: 예전엔 get_backtest_universe()[:8]로 뽑아서 유니버스 앞쪽(초대형주 위주,
# _BACKTEST_UNIVERSE의 정렬 순서 참고)만 검증했다. "예측 확률이 실제로 맞는가"를
# 초대형주 8개로만 답하면서 중소형주에도 같은 결론을 적용하는 셈이었다. 여전히
# 무료 인스턴스 배경 작업 부하는 신경 써야 하므로 전체(79) 대신 20으로만 늘리되,
# _select_offline_symbols()로 유니버스 전체에 고르게 퍼진 표본을 뽑는다.
_OFFLINE_MAX_SYMBOLS = 20
# Real sleep (not just a loop tick) between windows so /health and user requests
# get CPU time while the build crunches pandas on the tiny free instance.
_WINDOW_BREATH_SECONDS = 0.05
_SYMBOL_BREATH_SECONDS = 0.5

_build_tasks: dict[str, asyncio.Task] = {}


def _select_offline_symbols(universe: list[str], max_symbols: int) -> list[str]:
    """유니버스에서 max_symbols개를 고르게 퍼뜨려 뽑는다.

    앞쪽 max_symbols개만 자르면(정렬상 초대형주 위주) 캘리브레이션 검증이
    초대형주에만 편중된다. 등간격으로 뽑아 중형주 구간도 표본에 포함시킨다.
    """
    if max_symbols <= 0:
        return []
    if max_symbols >= len(universe):
        return list(universe)
    step = len(universe) / max_symbols
    return [universe[int(i * step)] for i in range(max_symbols)]


def simulate_window_outcome(
    forward_df: pd.DataFrame,
    *,
    bullish: bool,
    target: float,
    invalidation: float,
) -> bool | None:
    """Resolve a signal against the bars that followed it.

    Returns True (target touched first), False (invalidation touched first,
    or both on the same bar — conservative), or None if neither level was
    reached within the forward window.
    """
    if forward_df is None or forward_df.empty:
        return None

    for row in forward_df.itertuples(index=False):
        high = float(row.high)
        low = float(row.low)
        if bullish:
            target_hit = high >= target
            stop_hit = low <= invalidation
        else:
            target_hit = low <= target
            stop_hit = high >= invalidation

        if stop_hit:
            return False
        if target_hit:
            return True
    return None


async def collect_symbol_pairs(
    symbol: SymbolInfo,
    timeframe: str,
    bars_df: pd.DataFrame,
    *,
    window: int,
    step: int,
    max_forward: int,
) -> tuple[list[tuple[str, float, bool]], dict[str, int]]:
    """Walk one symbol's history and emit (pattern_type, predicted, won) triples.

    Each window is analyzed exactly as production would have on that day
    (only data up to the window end is visible). no_signal results are skipped
    because production would not act on them either. pattern_type is carried
    along so callers can break the calibration report down per pattern type
    (an aggregate report can look weak/overconfident even when a subset of
    pattern types has real skill, diluted by weaker ones pooled in).
    """
    pairs: list[tuple[str, float, bool]] = []
    windows = 0
    signals = 0
    unresolved = 0
    n = len(bars_df)

    for start in range(0, max(0, n - window - 1), step):
        window_df = bars_df.iloc[start:start + window].copy().reset_index(drop=True)
        if len(window_df) < window:
            break
        windows += 1

        try:
            result = await analyze_symbol_dataframe(symbol, timeframe, window_df)
        except Exception as exc:
            logger.debug("offline calibration analyze failed for %s @%d: %s", symbol.code, start, exc)
            continue

        if result.no_signal_flag or not result.patterns:
            continue
        primary = result.patterns[0]
        if primary.target_level is None or primary.invalidation_level is None:
            continue
        bullish = pattern_direction_is_bullish(primary)

        signals += 1
        predicted = result.p_up if bullish else result.p_down
        forward_df = bars_df.iloc[start + window:start + window + max_forward]
        won = simulate_window_outcome(
            forward_df,
            bullish=bullish,
            target=float(primary.target_level),
            invalidation=float(primary.invalidation_level),
        )
        pattern_type = str(primary.pattern_type)
        if won is None:
            # backtest_engine.py의 _bucket_to_stat_line()과 같은 이유로, 목표·손절
            # 어디에도 닿지 않은 timeout을 그냥 버리면 "애매하게 끝난 경우"가 통째로
            # 빠져 승률(=칼리브레이션 base_rate)이 실제보다 낙관적으로 보이는 편향이
            # 생긴다. build_calibration_report()는 (predicted, won: bool) 쌍만 받으므로
            # timeout을 손절과 동일하게(=False) 분모에 포함시켜 같은 효과를 낸다.
            unresolved += 1
            pairs.append((pattern_type, float(predicted), False))
            continue
        pairs.append((pattern_type, float(predicted), bool(won)))

        # keep the event loop responsive during long background builds
        await asyncio.sleep(_WINDOW_BREATH_SECONDS)

    return pairs, {"windows": windows, "signals": signals, "unresolved": unresolved}


async def run_offline_calibration(
    timeframe: str = "1d",
    symbols: list[str] | None = None,
    max_symbols: int = _OFFLINE_MAX_SYMBOLS,
) -> dict:
    """Build the offline calibration report and cache it."""
    from .data_fetcher import get_data_fetcher

    cfg = get_backtest_config(timeframe)
    codes = symbols or _select_offline_symbols(get_backtest_universe(), max_symbols)
    fetcher = get_data_fetcher()

    all_pairs: list[tuple[float, bool]] = []
    totals = {"symbols": 0, "windows": 0, "signals": 0, "unresolved": 0}

    for code in codes:
        try:
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=int(cfg["lookback_days"]))
            if df.empty or len(df) < int(cfg["min_bars"]):
                continue
            symbol = SymbolInfo(code=code, name=code, market="KOSPI", sector=None, market_cap=None, is_in_universe=True)
            pairs, meta = await collect_symbol_pairs(
                symbol,
                timeframe,
                df,
                window=int(cfg["window"]),
                step=int(cfg["step"]),
                max_forward=int(cfg["max_forward"]),
            )
            all_pairs.extend((predicted, won) for _, predicted, won in pairs)
            totals["symbols"] += 1
            totals["windows"] += meta["windows"]
            totals["signals"] += meta["signals"]
            totals["unresolved"] += meta["unresolved"]
            await asyncio.sleep(_SYMBOL_BREATH_SECONDS)
        except Exception as exc:
            logger.warning("offline calibration failed for %s (%s): %s", code, timeframe, exc)

    report = build_calibration_report(all_pairs)
    payload = {
        "timeframe": timeframe,
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulated": totals,
        "evaluated_total": totals["signals"],
        "scored_total": len(all_pairs),
        **report.to_dict(),
    }
    await cache_set(f"{_CACHE_PREFIX}:{timeframe}", payload, _CACHE_TTL)
    logger.info(
        "offline calibration ready (%s): %d pairs from %d signals / %d windows",
        timeframe, len(all_pairs), totals["signals"], totals["windows"],
    )
    return payload


async def get_offline_calibration(timeframe: str = "1d", refresh: bool = False) -> dict:
    """Non-blocking accessor: cached report, or kick off a background build."""
    cache_key = f"{_CACHE_PREFIX}:{timeframe}"
    if not refresh:
        cached = await cache_get(cache_key)
        if isinstance(cached, dict) and cached.get("status") == "ready":
            return cached

    task = _build_tasks.get(timeframe)
    if task is not None and not task.done():
        return {"timeframe": timeframe, "status": "building"}

    async def _safe_run() -> None:
        try:
            await run_offline_calibration(timeframe)
        except Exception as exc:
            logger.warning("offline calibration build failed (%s): %s", timeframe, exc)

    _build_tasks[timeframe] = asyncio.create_task(_safe_run())
    return {"timeframe": timeframe, "status": "building"}
