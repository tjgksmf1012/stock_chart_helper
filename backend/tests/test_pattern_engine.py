# -*- coding: utf-8 -*-
"""Regression tests for PatternEngine.

These tests verify that:
1. The engine initialises without errors.
2. detect_all() always returns a list (never raises on normal data).
3. Every PatternResult exposes the expected interface.
4. Score fields are in [0, 1].
5. State values are from the known set.
"""

from __future__ import annotations

import pytest

from app.services.pattern_engine import PatternEngine, PatternResult

VALID_STATES = {"forming", "armed", "confirmed", "invalidated", "played_out"}
VALID_GRADES = {"A", "B", "C"}

KNOWN_PATTERN_TYPES = {
    "double_bottom",
    "double_top",
    "head_and_shoulders",
    "inverse_head_and_shoulders",
    "ascending_triangle",
    "descending_triangle",
    "symmetric_triangle",
    "rectangle",
    "rising_channel",
    "falling_channel",
    "cup_and_handle",
    "rounding_bottom",
    "vcp",
    "momentum_breakout",
}


class TestPatternEngineInit:
    def test_instantiates(self):
        engine = PatternEngine()
        assert engine is not None

    def test_has_detect_all(self):
        engine = PatternEngine()
        assert callable(getattr(engine, "detect_all", None))


class TestDetectAllReturnType:
    def test_returns_list_on_normal_df(self, sample_ohlcv_df):
        engine = PatternEngine()
        results = engine.detect_all(sample_ohlcv_df)
        assert isinstance(results, list)

    def test_returns_list_on_long_df(self, sample_ohlcv_df_long):
        engine = PatternEngine()
        results = engine.detect_all(sample_ohlcv_df_long)
        assert isinstance(results, list)

    def test_returns_list_on_empty_df(self):
        import pandas as pd

        engine = PatternEngine()
        empty = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        results = engine.detect_all(empty)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_returns_list_on_short_df(self):
        """Only 5 bars — too short for any pattern, but must not crash."""
        import pandas as pd

        engine = PatternEngine()
        tiny = pd.DataFrame(
            {
                "date": pd.bdate_range("2023-01-02", periods=5),
                "open": [100, 101, 99, 102, 100],
                "high": [103, 104, 102, 105, 103],
                "low": [98, 99, 97, 100, 98],
                "close": [101, 100, 101, 103, 101],
                "volume": [1_000_000] * 5,
            }
        )
        results = engine.detect_all(tiny)
        assert isinstance(results, list)


class TestPatternResultSchema:
    def test_required_attributes(self, sample_ohlcv_df_long):
        engine = PatternEngine()
        results = engine.detect_all(sample_ohlcv_df_long)
        for result in results:
            assert isinstance(result, PatternResult), "Expected PatternResult instances"
            # Required string fields
            assert isinstance(result.pattern_type, str) and result.pattern_type, "pattern_type must be a non-empty string"
            assert isinstance(result.state, str) and result.state in VALID_STATES, f"state '{result.state}' not in {VALID_STATES}"
            assert isinstance(result.grade, str) and result.grade in VALID_GRADES, f"grade '{result.grade}' not in {VALID_GRADES}"
            # Score fields in [0, 1]
            assert 0.0 <= result.textbook_similarity <= 1.0, "textbook_similarity out of range"
            assert 0.0 <= result.geometry_fit <= 1.0, "geometry_fit out of range"
            # Level fields (when not None must be positive)
            if result.target_level is not None:
                assert result.target_level > 0
            if result.invalidation_level is not None:
                assert result.invalidation_level > 0
            if result.neckline is not None:
                assert result.neckline > 0

    def test_pattern_types_are_known(self, sample_ohlcv_df_long):
        """Detected pattern types should all be from the documented set."""
        engine = PatternEngine()
        results = engine.detect_all(sample_ohlcv_df_long)
        for result in results:
            assert result.pattern_type in KNOWN_PATTERN_TYPES, (
                f"Unexpected pattern type: {result.pattern_type}"
            )

    def test_no_nan_in_score_fields(self, sample_ohlcv_df_long):
        import math

        engine = PatternEngine()
        results = engine.detect_all(sample_ohlcv_df_long)
        for result in results:
            for attr in ("textbook_similarity", "geometry_fit", "leg_balance_fit"):
                val = getattr(result, attr, None)
                if val is not None:
                    assert not math.isnan(val), f"{attr} is NaN in {result.pattern_type}"

    def test_start_dt_is_set(self, sample_ohlcv_df_long):
        engine = PatternEngine()
        results = engine.detect_all(sample_ohlcv_df_long)
        for result in results:
            assert result.start_dt, "start_dt must be set"


def _build_ohlcv_from_closes(closes):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-02", periods=len(closes))
    rows = []
    for dt, close in zip(dates, closes):
        open_px = close * (1 + rng.normal(0, 0.002))
        high = max(open_px, close) * (1 + abs(rng.normal(0, 0.003)))
        low = min(open_px, close) * (1 - abs(rng.normal(0, 0.003)))
        rows.append(
            {
                "date": dt,
                "open": round(open_px),
                "high": round(high),
                "low": round(low),
                "close": round(close),
                "volume": 1_000_000,
            }
        )
    return pd.DataFrame(rows)


class TestPositiveDetection:
    """A textbook synthetic pattern must actually be detected, not just 'no crash'."""

    def test_detects_textbook_double_bottom(self):
        import numpy as np

        closes = (
            list(np.linspace(10_000, 9_000, 30))
            + list(np.linspace(9_000, 8_000, 15))  # first leg down to L1
            + list(np.linspace(8_000, 9_000, 15))  # bounce up to the neckline
            + list(np.linspace(9_000, 8_050, 15))  # second leg down to ~L1
            + list(np.linspace(8_050, 9_400, 20))  # breakout back through the neckline
        )
        df = _build_ohlcv_from_closes(closes)
        results = PatternEngine().detect_all(df, timeframe="1d")

        doubles = [r for r in results if r.pattern_type == "double_bottom"]
        assert doubles, f"expected a double_bottom, got {[r.pattern_type for r in results]}"

        db = doubles[0]
        assert db.state in VALID_STATES
        assert db.grade in VALID_GRADES
        assert db.textbook_similarity > 0.5
        if db.target_level is not None:
            assert db.target_level > 0
        if db.invalidation_level is not None:
            assert db.invalidation_level > 0
