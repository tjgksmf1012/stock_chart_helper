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
