"""Tests for the momentum breakout detector — a non-swing-point track that scans for
resistance proximity + volume expansion + positive momentum directly, instead of waiting
for a classic W/M/triangle shape to fully complete.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pattern_engine import PatternEngine


def _build_df(closes: list[float], volumes: list[float], highs: list[float] | None = None, lows: list[float] | None = None) -> pd.DataFrame:
    n = len(closes)
    dates = pd.bdate_range("2023-01-02", periods=n)
    highs = highs or [c * 1.005 for c in closes]
    lows = lows or [c * 0.995 for c in closes]
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _detect(df: pd.DataFrame, rs_fit: float = 0.5):
    return PatternEngine()._detect_momentum_breakout(df, swings=[], regime_fit=0.5, timeframe="1d", rs_fit=rs_fit)


class TestMomentumBreakoutDetection:
    def test_confirmed_breakout_with_volume_expansion(self):
        base = [100.0] * 55  # flat consolidation, resistance ~= 100 * 1.005 (high)
        base_volumes = [1_000_000.0] * 55
        # breakout bar: close ~3% above resistance (within the +6% detection window)
        # with a clear volume surge (>= +45% confirmed threshold)
        closes = base + [103.5]
        highs = [c * 1.005 for c in base] + [104.0]
        lows = [c * 0.995 for c in base] + [102.5]
        volumes = base_volumes + [2_500_000.0]
        df = _build_df(closes, volumes, highs, lows)

        results = _detect(df)

        assert results, "expected a momentum_breakout detection"
        pattern = results[0]
        assert pattern.pattern_type == "momentum_breakout"
        assert pattern.state == "confirmed"
        assert pattern.neckline is not None and pattern.invalidation_level is not None
        assert pattern.invalidation_level < pattern.neckline < (pattern.target_level or float("inf"))

    def test_armed_when_close_but_not_through_resistance(self):
        base = [100.0] * 55
        base_volumes = [1_000_000.0] * 55
        # climbing steadily toward, but not through, resistance; modest volume pickup
        closes = base + [100.4]
        highs = [c * 1.005 for c in base] + [100.6]
        lows = [c * 0.995 for c in base] + [99.9]
        volumes = base_volumes + [1_100_000.0]
        df = _build_df(closes, volumes, highs, lows)

        results = _detect(df)

        assert results
        assert results[0].state in {"armed", "forming"}

    def test_forming_with_modest_volume_and_distance(self):
        # base lower than resistance, with a small positive move on the final bar
        # (momentum must be positive) but below-average volume -> forming, not armed.
        base = [94.0] * 55
        base_volumes = [1_000_000.0] * 55
        closes = base + [96.3]
        volumes = base_volumes + [900_000.0]
        df = _build_df(closes, volumes)

        results = _detect(df)

        assert results
        assert results[0].state == "forming"

    def test_no_detection_in_a_downtrend(self):
        # steadily declining closes -> 11-bar momentum return is negative
        closes = [100.0 - i * 0.3 for i in range(55)]
        volumes = [1_000_000.0] * 55
        df = _build_df(closes, volumes)

        assert _detect(df) == []

    def test_no_detection_when_price_too_far_below_resistance(self):
        base = [100.0] * 55
        base_volumes = [1_000_000.0] * 55
        closes = base + [85.0]  # -15%, outside the -8%..+6% window
        volumes = base_volumes + [1_000_000.0]
        df = _build_df(closes, volumes)

        assert _detect(df) == []

    def test_no_detection_when_price_too_far_above_resistance(self):
        base = [100.0] * 55
        base_volumes = [1_000_000.0] * 55
        closes = base + [115.0]  # +15%, outside the -8%..+6% window
        volumes = base_volumes + [1_000_000.0]
        df = _build_df(closes, volumes)

        assert _detect(df) == []

    def test_too_short_a_series_yields_no_detection(self):
        closes = [100.0] * 20
        volumes = [1_000_000.0] * 20
        df = _build_df(closes, volumes)
        assert _detect(df) == []

    def test_no_detection_when_price_below_own_trend_ma(self):
        # Recent 30-bar consolidation sits right at the breakout level (so the
        # resistance-distance/momentum checks alone would pass), but an earlier
        # higher-priced leg still inside the 50-bar trend window keeps the 50-bar
        # average above the current price -> the stock isn't in an established
        # uptrend yet, so this must not fire as a breakout.
        decline = [110.0 - i * (15.0 / 19) for i in range(20)]  # 110 -> 95 over 20 bars
        flat = [95.0] * 30
        base = decline + flat
        closes = base + [96.0]
        volumes = [1_000_000.0] * len(closes)
        df = _build_df(closes, volumes)

        assert _detect(df) == []

    def test_low_relative_strength_prevents_confirmed_state(self):
        # Same textbook breakout setup as the confirmed-state test, but the stock is
        # badly lagging the market (rs_fit far below neutral) -> should not be trusted
        # as a confirmed breakout, only a forming setup at most.
        base = [100.0] * 55
        base_volumes = [1_000_000.0] * 55
        closes = base + [103.5]
        highs = [c * 1.005 for c in base] + [104.0]
        lows = [c * 0.995 for c in base] + [102.5]
        volumes = base_volumes + [2_500_000.0]
        df = _build_df(closes, volumes, highs, lows)

        results = _detect(df, rs_fit=0.15)

        assert results
        assert results[0].state == "forming"

    def test_result_flows_through_textbook_similarity_and_bullish_classification(self):
        from app.services.pattern_engine import BULLISH_PATTERNS

        base = [100.0] * 55
        base_volumes = [1_000_000.0] * 55
        closes = base + [103.5]
        highs = [c * 1.005 for c in base] + [104.0]
        lows = [c * 0.995 for c in base] + [102.5]
        volumes = base_volumes + [2_500_000.0]
        df = _build_df(closes, volumes, highs, lows)

        results = _detect(df)
        pattern = results[0]

        assert "momentum_breakout" in BULLISH_PATTERNS
        assert 0.0 <= pattern.textbook_similarity <= 1.0
