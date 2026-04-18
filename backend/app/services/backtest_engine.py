"""
Timeframe-aware lightweight backtesting statistics.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.redis import cache_get, cache_set
from .pattern_engine import PatternEngine, PatternResult

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
}

_DEFAULT_SAMPLE_SIZES = {"1mo": 12, "1wk": 16, "1d": 20}
_BACKTEST_TIMEFRAMES = ("1mo", "1wk", "1d")
_BACKTEST_UNIVERSE = [
    "005930", "000660", "035420", "005380", "051910",
    "006400", "035720", "068270", "105560", "055550",
    "247540", "086520", "000270", "028260", "096770",
]
_BACKTEST_CONFIG = {
    "1mo": {"window": 24, "step": 2, "max_forward": 6, "lookback_days": 3650, "min_bars": 32},
    "1wk": {"window": 36, "step": 3, "max_forward": 12, "lookback_days": 3650, "min_bars": 56},
    "1d": {"window": 60, "step": 10, "max_forward": 40, "lookback_days": 730, "min_bars": 100},
}

_backtest_running = False


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
    }


def _default_stats() -> dict[str, dict[str, dict[str, float | int | str]]]:
    return {
        timeframe: {
            pattern_type: _default_stat_line(pattern_type, timeframe, win_rate, _DEFAULT_SAMPLE_SIZES[timeframe])
            for pattern_type, win_rate in _DEFAULT_WIN_RATES.items()
        }
        for timeframe in _BACKTEST_TIMEFRAMES
    }


def _is_bullish(pattern_type: str) -> bool:
    return pattern_type in {
        "double_bottom",
        "inverse_head_and_shoulders",
        "ascending_triangle",
        "cup_and_handle",
        "rounding_bottom",
        "rectangle",
    }


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
            bullish = _is_bullish(pattern.pattern_type)
            entry_price = float(window_df.iloc[-1]["close"])
            favorable_excursion = 0.0
            adverse_excursion = 0.0
            bars_to_outcome: int | None = None

            for step, (_, bar) in enumerate(forward_bars.iterrows(), start=1):
                high = float(bar["high"])
                low = float(bar["low"])
                if bullish:
                    favorable_excursion = max(favorable_excursion, max(0.0, (high - entry_price) / max(entry_price, 1e-9)))
                    adverse_excursion = max(adverse_excursion, max(0.0, (entry_price - low) / max(entry_price, 1e-9)))
                    if high >= pattern.target_level:
                        win = True
                        bars_to_outcome = step
                        break
                    if low <= pattern.invalidation_level:
                        win = False
                        bars_to_outcome = step
                        break
                else:
                    favorable_excursion = max(favorable_excursion, max(0.0, (entry_price - low) / max(entry_price, 1e-9)))
                    adverse_excursion = max(adverse_excursion, max(0.0, (high - entry_price) / max(entry_price, 1e-9)))
                    if low <= pattern.target_level:
                        win = True
                        bars_to_outcome = step
                        break
                    if high >= pattern.invalidation_level:
                        win = False
                        bars_to_outcome = step
                        break

            if win is not None and bars_to_outcome is not None:
                results.append(
                    {
                        "pattern_type": pattern.pattern_type,
                        "win": win,
                        "timeframe": timeframe,
                        "mfe_pct": round(favorable_excursion, 4),
                        "mae_pct": round(adverse_excursion, 4),
                        "bars_to_outcome": bars_to_outcome,
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

        for timeframe in _BACKTEST_TIMEFRAMES:
            cfg = _BACKTEST_CONFIG[timeframe]
            for code in _BACKTEST_UNIVERSE:
                try:
                    df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=int(cfg["lookback_days"]))
                    if df.empty or len(df) < int(cfg["min_bars"]):
                        continue
                    stock_results = await asyncio.to_thread(_backtest_stock_sync, timeframe, df)
                    for result in stock_results:
                        bucket = aggregated[timeframe].setdefault(
                            result["pattern_type"],
                            {"wins": 0, "total": 0, "mfe_sum": 0.0, "mae_sum": 0.0, "bars_sum": 0.0},
                        )
                        bucket["total"] += 1
                        bucket["mfe_sum"] += float(result["mfe_pct"])
                        bucket["mae_sum"] += float(result["mae_pct"])
                        bucket["bars_sum"] += float(result["bars_to_outcome"])
                        if result["win"]:
                            bucket["wins"] += 1
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logger.warning("Backtest failed for %s (%s): %s", code, timeframe, exc)

        stats = _default_stats()
        for timeframe, pattern_counts in aggregated.items():
            for pattern_type, bucket in pattern_counts.items():
                wins = int(bucket["wins"])
                total = int(bucket["total"])
                if total < 5:
                    continue
                avg_mfe_pct = round(float(bucket["mfe_sum"]) / total, 4)
                avg_mae_pct = round(float(bucket["mae_sum"]) / total, 4)
                avg_bars_to_outcome = round(float(bucket["bars_sum"]) / total, 2)
                win_rate = round(wins / total, 3)
                stats[timeframe][pattern_type] = {
                    "pattern_type": pattern_type,
                    "timeframe": timeframe,
                    "win_rate": win_rate,
                    "sample_size": total,
                    "wins": wins,
                    "total": total,
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
                }

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
