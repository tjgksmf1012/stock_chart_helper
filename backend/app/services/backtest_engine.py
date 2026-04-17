"""
Lightweight backtesting engine: computes historical win rates per pattern type.

Methodology:
  1. For each stock in the reference universe, fetch 2 years of daily bars.
  2. Slide a detection window (step = 5 bars) and run PatternEngine.
  3. For every detected CONFIRMED pattern, look forward up to max_forward bars:
       - Win  = price touched target_level before invalidation_level
       - Loss = price touched invalidation_level first, or timed out
  4. Aggregate win/loss counts per pattern_type.
  5. Results are cached for 24 h and refreshed by APScheduler.

The win rate returned here replaces the hardcoded 0.55 in probability_engine.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from ..core.redis import cache_get, cache_set
from .pattern_engine import PatternEngine, PatternResult

logger = logging.getLogger(__name__)

BACKTEST_CACHE_KEY = "backtest:win_rates"
BACKTEST_TTL = 86400  # 24 h

# Default win rates used until a backtest has been run
_DEFAULT_WIN_RATES: dict[str, float] = {
    "double_bottom":              0.58,
    "double_top":                 0.56,
    "head_and_shoulders":         0.55,
    "inverse_head_and_shoulders": 0.59,
    "ascending_triangle":         0.60,
    "descending_triangle":        0.57,
    "symmetric_triangle":         0.52,
    "rectangle":                  0.54,
    "rising_channel":             0.53,
    "falling_channel":            0.53,
    "cup_and_handle":             0.62,
    "rounding_bottom":            0.60,
}

# Stocks used for computing win rates (diversified, liquid)
_BACKTEST_UNIVERSE = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # NAVER
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
]

_backtest_running = False


async def _backtest_stock(code: str, bars_df: Any) -> list[dict[str, Any]]:
    """Returns list of {pattern_type, win} dicts for one stock."""
    import pandas as pd
    import numpy as np

    results: list[dict[str, Any]] = []
    engine = PatternEngine()
    n = len(bars_df)
    window = 60          # detection window size
    step = 10            # slide step
    max_forward = 40     # bars to look forward for resolution

    for start_idx in range(0, n - window - max_forward, step):
        window_df = bars_df.iloc[start_idx : start_idx + window].copy().reset_index(drop=True)
        patterns: list[PatternResult] = engine.detect_all(window_df)

        for pattern in patterns:
            if pattern.state != "confirmed":
                continue
            if pattern.target_level is None or pattern.invalidation_level is None:
                continue

            target = pattern.target_level
            invalidation = pattern.invalidation_level
            forward_bars = bars_df.iloc[start_idx + window : start_idx + window + max_forward]

            win: bool | None = None
            for _, bar in forward_bars.iterrows():
                high = float(bar["high"])
                low = float(bar["low"])

                if pattern.pattern_type in {
                    "double_bottom", "inverse_head_and_shoulders",
                    "ascending_triangle", "cup_and_handle", "rounding_bottom",
                }:
                    # Bullish: target above, invalidation below
                    if high >= target:
                        win = True
                        break
                    if low <= invalidation:
                        win = False
                        break
                else:
                    # Bearish: target below, invalidation above
                    if low <= target:
                        win = True
                        break
                    if high >= invalidation:
                        win = False
                        break

            if win is not None:
                results.append({"pattern_type": pattern.pattern_type, "win": win})

    return results


async def run_backtest() -> dict[str, float]:
    """
    Runs the full backtest over the reference universe.
    Returns {pattern_type: win_rate} mapping.
    """
    global _backtest_running
    if _backtest_running:
        logger.info("Backtest already running — skipping duplicate request")
        return await get_win_rates()

    _backtest_running = True
    logger.info("Starting backtest over %d stocks…", len(_BACKTEST_UNIVERSE))

    try:
        from .data_fetcher import get_data_fetcher
        fetcher = get_data_fetcher()
        end = date.today()
        start = end - timedelta(days=730)  # 2 years

        all_results: list[dict[str, Any]] = []

        for code in _BACKTEST_UNIVERSE:
            try:
                df = await fetcher.get_stock_ohlcv(code, start, end)
                if df.empty or len(df) < 80:
                    continue
                stock_results = await asyncio.to_thread(_backtest_stock_sync, code, df)
                all_results.extend(stock_results)
                await asyncio.sleep(0.05)
            except Exception as exc:
                logger.warning("Backtest failed for %s: %s", code, exc)

        # Aggregate
        counts: dict[str, list[int]] = {}  # pattern_type → [wins, total]
        for r in all_results:
            pt = r["pattern_type"]
            if pt not in counts:
                counts[pt] = [0, 0]
            counts[pt][1] += 1
            if r["win"]:
                counts[pt][0] += 1

        win_rates: dict[str, float] = dict(_DEFAULT_WIN_RATES)
        for pt, (wins, total) in counts.items():
            if total >= 5:  # require at least 5 samples
                win_rates[pt] = round(wins / total, 3)
                logger.info("Backtest %s: %d/%d = %.1f%%", pt, wins, total, wins / total * 100)

        await cache_set(BACKTEST_CACHE_KEY, win_rates, BACKTEST_TTL)
        logger.info("Backtest complete — %d total trades across %d pattern types", len(all_results), len(counts))
        return win_rates

    except Exception as exc:
        logger.error("Backtest failed: %s", exc)
        return dict(_DEFAULT_WIN_RATES)
    finally:
        _backtest_running = False


def _backtest_stock_sync(code: str, bars_df: Any) -> list[dict[str, Any]]:
    """Synchronous wrapper so asyncio.to_thread can call the CPU-bound logic."""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_backtest_stock(code, bars_df))
    finally:
        loop.close()


async def get_win_rates() -> dict[str, float]:
    """Returns cached win rates; triggers background backtest if cache is cold."""
    cached = await cache_get(BACKTEST_CACHE_KEY)
    if cached and isinstance(cached, dict):
        return cached

    # Return defaults immediately; schedule full backtest in background
    asyncio.create_task(run_backtest())
    return dict(_DEFAULT_WIN_RATES)


async def get_win_rate(pattern_type: str) -> float:
    rates = await get_win_rates()
    return rates.get(pattern_type, 0.55)
