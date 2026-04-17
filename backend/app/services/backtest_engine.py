"""
Lightweight backtesting engine for timeframe-aware pattern statistics.

The engine computes win rates and sample sizes per pattern and per timeframe.
Those stats are later used to calibrate confidence instead of relying on a
single hard-coded sample size.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
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

_DEFAULT_SAMPLE_SIZES = {
    "1mo": 12,
    "1wk": 16,
    "1d": 20,
}

_BACKTEST_UNIVERSE = [
    "005930",
    "000660",
    "035420",
    "005380",
    "051910",
    "006400",
    "035720",
    "068270",
    "105560",
    "055550",
    "247540",
    "086520",
    "000270",
    "028260",
    "096770",
]

_BACKTEST_TIMEFRAMES = ("1mo", "1wk", "1d")

_BACKTEST_CONFIG = {
    "1mo": {"window": 24, "step": 2, "max_forward": 6, "lookback_days": 3650, "min_bars": 32},
    "1wk": {"window": 36, "step": 3, "max_forward": 12, "lookback_days": 3650, "min_bars": 56},
    "1d": {"window": 60, "step": 10, "max_forward": 40, "lookback_days": 730, "min_bars": 100},
}

_backtest_running = False


def _default_stats() -> dict[str, dict[str, dict[str, float | int | str]]]:
    return {
        timeframe: {
            pattern_type: {
                "pattern_type": pattern_type,
                "timeframe": timeframe,
                "win_rate": win_rate,
                "sample_size": _DEFAULT_SAMPLE_SIZES[timeframe],
                "wins": int(round(win_rate * _DEFAULT_SAMPLE_SIZES[timeframe])),
                "total": _DEFAULT_SAMPLE_SIZES[timeframe],
            }
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


def _backtest_stock_sync(
    timeframe: str,
    bars_df: Any,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    engine = PatternEngine()
    cfg = _BACKTEST_CONFIG[timeframe]
    n = len(bars_df)
    window = int(cfg["window"])
    step = int(cfg["step"])
    max_forward = int(cfg["max_forward"])

    for start_idx in range(0, max(0, n - window - max_forward), step):
        window_df = bars_df.iloc[start_idx : start_idx + window].copy().reset_index(drop=True)
        patterns: list[PatternResult] = engine.detect_all(window_df)

        for pattern in patterns:
            if pattern.state != "confirmed":
                continue
            if pattern.target_level is None or pattern.invalidation_level is None:
                continue

            forward_bars = bars_df.iloc[start_idx + window : start_idx + window + max_forward]
            win: bool | None = None
            bullish = _is_bullish(pattern.pattern_type)

            for _, bar in forward_bars.iterrows():
                high = float(bar["high"])
                low = float(bar["low"])

                if bullish:
                    if high >= pattern.target_level:
                        win = True
                        break
                    if low <= pattern.invalidation_level:
                        win = False
                        break
                else:
                    if low <= pattern.target_level:
                        win = True
                        break
                    if high >= pattern.invalidation_level:
                        win = False
                        break

            if win is not None:
                results.append({"pattern_type": pattern.pattern_type, "win": win, "timeframe": timeframe})

    return results


async def run_backtest() -> dict[str, dict[str, dict[str, float | int | str]]]:
    global _backtest_running
    if _backtest_running:
        logger.info("Backtest already running; skipping duplicate request")
        return await get_pattern_stats_map()

    _backtest_running = True
    logger.info("Starting timeframe-aware backtest", timeframes=list(_BACKTEST_TIMEFRAMES))

    try:
        from .data_fetcher import get_data_fetcher

        fetcher = get_data_fetcher()
        aggregated: dict[str, dict[str, list[int]]] = {
            timeframe: {} for timeframe in _BACKTEST_TIMEFRAMES
        }

        for timeframe in _BACKTEST_TIMEFRAMES:
            cfg = _BACKTEST_CONFIG[timeframe]
            for code in _BACKTEST_UNIVERSE:
                try:
                    df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=int(cfg["lookback_days"]))
                    if df.empty or len(df) < int(cfg["min_bars"]):
                        continue
                    stock_results = await asyncio.to_thread(_backtest_stock_sync, timeframe, df)
                    for result in stock_results:
                        bucket = aggregated[timeframe].setdefault(result["pattern_type"], [0, 0])
                        bucket[1] += 1
                        if result["win"]:
                            bucket[0] += 1
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    logger.warning("Backtest failed for %s (%s): %s", code, timeframe, exc)

        stats = _default_stats()
        for timeframe, pattern_counts in aggregated.items():
            for pattern_type, (wins, total) in pattern_counts.items():
                if total < 5:
                    continue
                stats[timeframe][pattern_type] = {
                    "pattern_type": pattern_type,
                    "timeframe": timeframe,
                    "win_rate": round(wins / total, 3),
                    "sample_size": total,
                    "wins": wins,
                    "total": total,
                }
                logger.info(
                    "Backtest result",
                    timeframe=timeframe,
                    pattern_type=pattern_type,
                    wins=wins,
                    total=total,
                )

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
        "pattern_type": pattern_type,
        "timeframe": timeframe_key,
        "win_rate": default_rate,
        "sample_size": default_sample,
        "wins": int(round(default_rate * default_sample)),
        "total": default_sample,
    }
