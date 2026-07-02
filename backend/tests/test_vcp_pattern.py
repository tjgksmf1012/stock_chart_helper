"""Tests for the VCP (volatility contraction pattern) detector.

Covers the two Minervini-style guardrails added on top of the original geometry-only
detection: relative strength (rs_fit) as a precondition for a trusted breakout, and a
long-term stage-2 trend check (price above its 150-bar average) so a locally tidy
contraction shape sitting inside a much bigger downtrend isn't read as a real VCP.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.pattern_engine import PatternEngine


def _vcp_legs(rng: np.random.Generator, base_tail: float) -> list[float]:
    peak1 = 96.0
    low1 = peak1 * 0.84
    peak2 = peak1 * 1.015
    low2 = peak2 * 0.89
    peak3 = peak2 * 1.015
    low3 = peak3 * 0.95
    pivot_close = peak3 * 1.02

    return (
        list(np.linspace(base_tail, peak1, 10))
        + list(np.linspace(peak1, low1, 14))
        + list(np.linspace(low1, peak2, 14))
        + list(np.linspace(peak2, low2, 12))
        + list(np.linspace(low2, peak3, 12))
        + list(np.linspace(peak3, low3, 10))
        + list(np.linspace(low3, pivot_close, 16))
        + [pivot_close] * 4
    )


def _build_df(closes: list[float], seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=len(closes))
    rows = []
    for dt, close in zip(dates, closes):
        open_px = close * (1 + rng.normal(0, 0.0015))
        high = max(open_px, close) * (1 + abs(rng.normal(0, 0.002)))
        low = min(open_px, close) * (1 - abs(rng.normal(0, 0.002)))
        rows.append({"date": dt, "open": open_px, "high": high, "low": low, "close": close, "volume": 1_000_000.0})
    return pd.DataFrame(rows)


def _rising_base_df() -> pd.DataFrame:
    # Long uptrend base (155 bars) so the stage-2 (MA150) check is satisfied, followed by
    # three progressively tighter pullbacks (~16% / ~11% / ~5%) into a breakout leg.
    base = list(np.linspace(70, 95, 155))
    return _build_df(base + _vcp_legs(np.random.default_rng(3), base[-1]))


def _vcp_legs_with_descending_peaks(base_tail: float) -> list[float]:
    # Textbook VCP shape where each contraction's *high* is also a bit lower than the
    # last (not just the pullback depth), e.g. 100 -> 97 -> 94. A pivot break just above
    # the most recent (lowest, tightest) high should be a real breakout even though it
    # never reclaims the much older first-contraction high.
    peak1, low1 = 100.0, 100.0 * 0.84
    peak2, low2 = 97.0, 97.0 * 0.89
    peak3, low3 = 94.0, 94.0 * 0.95
    pivot_close = peak3 * 1.02  # clears peak3 with room to spare, nowhere near peak1/peak2

    return (
        list(np.linspace(base_tail, peak1, 10))
        + list(np.linspace(peak1, low1, 14))
        + list(np.linspace(low1, peak2, 14))
        + list(np.linspace(peak2, low2, 12))
        + list(np.linspace(low2, peak3, 12))
        + list(np.linspace(peak3, low3, 10))
        + list(np.linspace(low3, pivot_close, 16))
        + [pivot_close] * 4
    )


class TestVcpDetection:
    def test_detects_confirmed_vcp_with_neutral_rs(self):
        df = _rising_base_df()
        engine = PatternEngine()
        results = engine.detect_all(df, regime_fit=0.5, timeframe="1d", rs_fit=0.5)
        vcp = [r for r in results if r.pattern_type == "vcp"]

        assert vcp, "expected a vcp detection on a textbook 3-contraction shape"
        pattern = vcp[0]
        assert pattern.state == "confirmed"
        assert pattern.variant == "3_contractions"
        assert pattern.invalidation_level < pattern.neckline < (pattern.target_level or float("inf"))

    def test_weak_relative_strength_prevents_confirmed_state(self):
        # Same shape as the confirmed case, but the stock is badly lagging the market
        # (rs_fit far below neutral) -> Minervini's RS precondition isn't met, so this
        # must not be trusted as a confirmed/armed breakout.
        df = _rising_base_df()
        engine = PatternEngine()
        results = engine.detect_all(df, regime_fit=0.5, timeframe="1d", rs_fit=0.1)
        vcp = [r for r in results if r.pattern_type == "vcp"]

        assert vcp
        assert vcp[0].state == "forming"

    def test_gray_zone_rs_demotes_one_step_instead_of_a_cliff(self):
        # rs_fit=0.30 sits in the gray zone (0.20-0.35): weak enough to distrust a full
        # breakout, but not so weak it should be treated identically to a badly-lagging
        # stock (rs_fit=0.1). A hard "always forming below 0.35" cliff used to make
        # rs_fit=0.349 vs 0.351 flip between fully confirmed and fully forming; this
        # should instead land one notch down (armed), not the bottom.
        df = _rising_base_df()
        engine = PatternEngine()
        results = engine.detect_all(df, regime_fit=0.5, timeframe="1d", rs_fit=0.30)
        vcp = [r for r in results if r.pattern_type == "vcp"]

        assert vcp
        assert vcp[0].state == "armed"

    def test_pivot_uses_most_recent_contraction_high_not_the_max(self):
        # Peaks descend across the three contractions (100 -> 97 -> 94). The old code set
        # the breakout pivot at max(highs) = 100 (the oldest, widest contraction), so a
        # clean break above the most recent resistance (94) would never register as
        # confirmed/armed since price never reclaims 100. The fix should trigger off the
        # most recent contraction's high (94) instead.
        base = list(np.linspace(70, 100, 155))
        df = _build_df(base + _vcp_legs_with_descending_peaks(base[-1]))
        engine = PatternEngine()
        results = engine.detect_all(df, regime_fit=0.5, timeframe="1d", rs_fit=0.5)
        vcp = [r for r in results if r.pattern_type == "vcp"]

        assert vcp, "expected a vcp detection with a pivot at the most recent contraction high"
        assert vcp[0].state == "confirmed"
        assert vcp[0].neckline is not None and vcp[0].neckline < 96.0, (
            f"expected the pivot/neckline near the most recent high (~94), got {vcp[0].neckline} "
            "-- looks like max(highs) (~100) won instead of the most recent contraction high"
        )

    def test_rejects_locally_tidy_contraction_inside_a_long_downtrend(self):
        # The recent 3-contraction shape is identical to the confirmed case, but it sits
        # on top of a sharp long-term decline that's still inside the trailing 150-bar
        # window -> the 150-bar average is well above the current price, so this isn't
        # stage 2 yet and shouldn't be read as a real VCP setup.
        base = list(np.linspace(250, 96, 60))
        df = _build_df(base + _vcp_legs(np.random.default_rng(3), base[-1]))

        engine = PatternEngine()
        results = engine.detect_all(df, regime_fit=0.5, timeframe="1d", rs_fit=0.5)
        vcp = [r for r in results if r.pattern_type == "vcp"]

        assert vcp == []
