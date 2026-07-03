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

    def test_detects_textbook_cup_and_handle(self):
        import numpy as np

        closes = (
            list(np.linspace(11_000, 12_000, 20))  # up to the left rim
            + list(np.linspace(12_000, 9_000, 50))  # down into the cup
            + list(np.linspace(9_000, 11_800, 50))  # recovery to the right rim (~left rim)
            + list(np.linspace(11_800, 11_000, 16))  # shallow handle pullback (upper half of the cup)
            + list(np.linspace(11_000, 12_600, 24))  # breakout above the rim
        )
        df = _build_ohlcv_from_closes(closes)
        results = PatternEngine().detect_all(df, timeframe="1d")

        cups = [r for r in results if r.pattern_type == "cup_and_handle"]
        assert cups, f"expected a cup_and_handle, got {[r.pattern_type for r in results]}"

        cup = cups[0]
        assert cup.state == "confirmed"
        assert cup.grade in VALID_GRADES
        assert cup.neckline is not None and cup.invalidation_level is not None and cup.target_level is not None
        assert cup.invalidation_level < cup.neckline < cup.target_level

    def test_detects_textbook_rounding_bottom(self):
        import numpy as np

        closes = (
            list(np.linspace(10_000, 11_500, 30))  # up to the left rim
            + list(np.linspace(11_500, 8_500, 70))  # gradual decline into the base
            + list(np.linspace(8_500, 12_200, 100))  # gradual, continuous recovery through the rim
        )
        df = _build_ohlcv_from_closes(closes)
        results = PatternEngine().detect_all(df, timeframe="1d")

        bottoms = [r for r in results if r.pattern_type == "rounding_bottom"]
        assert bottoms, f"expected a rounding_bottom, got {[r.pattern_type for r in results]}"

        base = bottoms[0]
        assert base.state == "confirmed"
        assert base.grade in VALID_GRADES
        assert base.invalidation_level < base.neckline < base.target_level

    def test_detects_textbook_rising_channel(self):
        import numpy as np

        closes = (
            list(np.linspace(8_500, 9_800, 15))
            + list(np.linspace(9_800, 9_000, 15))
            + list(np.linspace(9_000, 10_300, 15))
            + list(np.linspace(10_300, 9_500, 15))
            + list(np.linspace(9_500, 10_800, 15))
            + list(np.linspace(10_800, 10_000, 15))
            + list(np.linspace(10_000, 12_000, 20))  # breaks above the upper trendline
        )
        df = _build_ohlcv_from_closes(closes)
        results = PatternEngine().detect_all(df, timeframe="1d")

        channels = [r for r in results if r.pattern_type == "rising_channel"]
        assert channels, f"expected a rising_channel, got {[r.pattern_type for r in results]}"

        channel = channels[0]
        assert channel.state == "confirmed"
        assert channel.target_level is not None and channel.neckline is not None
        assert channel.target_level > channel.neckline  # bullish breakout above the channel

    def test_detects_falling_channel_with_bullish_reversal_breakout(self):
        import numpy as np

        closes = (
            list(np.linspace(11_000, 12_500, 15))
            + list(np.linspace(12_500, 10_500, 15))
            + list(np.linspace(10_500, 12_000, 15))
            + list(np.linspace(12_000, 10_000, 15))
            + list(np.linspace(10_000, 11_500, 15))
            + list(np.linspace(11_500, 9_500, 15))
            + list(np.linspace(9_500, 13_500, 20))  # breaks above the (descending) upper trendline
        )
        df = _build_ohlcv_from_closes(closes)
        results = PatternEngine().detect_all(df, timeframe="1d")

        channels = [r for r in results if r.pattern_type == "falling_channel"]
        assert channels, f"expected a falling_channel, got {[r.pattern_type for r in results]}"

        channel = channels[0]
        assert channel.state == "confirmed"
        assert channel.target_level is not None and channel.neckline is not None
        assert channel.target_level > channel.neckline  # reversal: broke up out of the falling channel


class TestHeadAndShouldersPicksMostRecentMatch:
    """Regression: _detect_head_and_shoulders / _detect_inverse_head_and_shoulders used to
    walk swing triples oldest-first and `return` on the first valid match, unlike every other
    detector (which collects all matches and returns the most recent). A stale H&S from
    months ago could get reported forever instead of a fresh, currently-relevant one.
    """

    def test_head_and_shoulders_returns_recent_formation_not_stale_one(self):
        from app.services.pattern_engine import PatternEngine
        from app.services.swing_points import SwingPoint

        import numpy as np
        import pandas as pd

        # Both formations are deliberately priced close to the final close (~14,000) so
        # BOTH pass every filter (symmetry, height, and the forming-distance check) —
        # the only thing that should decide which one is reported is recency.
        closes = (
            list(np.linspace(13_000, 15_200, 10))  # up to stale LS
            + list(np.linspace(15_200, 13_800, 5))  # down to stale neckline low
            + list(np.linspace(13_800, 16_200, 5))  # up to stale head
            + list(np.linspace(16_200, 13_850, 5))  # down to stale neckline low
            + list(np.linspace(13_850, 15_100, 5))  # up to stale RS
            + list(np.linspace(15_100, 14_200, 10))  # drift toward the recent formation
            + list(np.linspace(14_200, 16_000, 40))  # rally to the recent LS
            + list(np.linspace(16_000, 14_500, 5))  # down to recent neckline low
            + list(np.linspace(14_500, 17_500, 5))  # up to recent head
            + list(np.linspace(17_500, 14_600, 5))  # down to recent neckline low
            + list(np.linspace(14_600, 15_900, 5))  # up to recent RS
            + list(np.linspace(15_900, 14_000, 30))  # confirms the recent neckline (~14,550)
        )
        df = _build_ohlcv_from_closes(closes)
        dates = pd.Timestamp("2023-01-02") + pd.to_timedelta(np.arange(len(df)), unit="D")

        def sp(idx: int, price: float, kind: str) -> SwingPoint:
            return SwingPoint(index=idx, datetime=dates[idx].to_pydatetime(), price=price, kind=kind, strength=5)

        swings = [
            sp(9, 15_200, "high"),   # stale LS
            sp(14, 13_800, "low"),   # stale left neckline low
            sp(19, 16_200, "high"),  # stale head
            sp(24, 13_850, "low"),   # stale right neckline low
            sp(29, 15_100, "high"),  # stale RS
            sp(79, 16_000, "high"),  # recent LS
            sp(84, 14_500, "low"),   # recent left neckline low
            sp(89, 17_500, "high"),  # recent head
            sp(94, 14_600, "low"),   # recent right neckline low
            sp(99, 15_900, "high"),  # recent RS
        ]

        engine = PatternEngine()
        results = engine._detect_head_and_shoulders(df, swings, regime_fit=0.6, timeframe="1d")

        assert results, "expected at least the recent head-and-shoulders to be detected"
        assert len(results) == 1, "only the most recent match should be returned, not every match"
        result = results[0]
        # The stale formation's neckline is ~13,825; the recent one's is ~14,550. If the
        # bug were still present, the first (stale) match would win instead.
        assert result.neckline is not None and result.neckline > 14_000, (
            f"expected the recent formation's neckline (~14,550), got {result.neckline} "
            "-- looks like the stale (oldest) match won instead of the most recent one"
        )


class TestSymmetricTriangleCanReachConfirmed:
    """Regression: the symmetric_triangle branch only had armed/forming states -- a
    dead end that made 'confirmed' (and therefore grade A) structurally unreachable
    no matter how clean the breakout was.
    """

    def test_clean_upward_breakout_reaches_confirmed(self):
        from app.services.pattern_engine import PatternEngine
        from app.services.swing_points import SwingPoint

        import numpy as np
        import pandas as pd

        closes = (
            list(np.linspace(10_000, 12_000, 10))  # up to first (highest) high
            + list(np.linspace(12_000, 9_000, 10))  # down to first (lowest) low
            + list(np.linspace(9_000, 11_500, 10))  # up to second high (lower than first)
            + list(np.linspace(11_500, 9_500, 10))  # down to second low (higher than first)
            + list(np.linspace(9_500, 11_000, 10))  # up to third high (lower still -- converging)
            + list(np.linspace(11_000, 10_000, 10))  # down to third low (higher still -- converging)
            + list(np.linspace(10_000, 10_800, 15))  # clean breakout above the apex (~10,500)
        )
        df = _build_ohlcv_from_closes(closes)
        dates = pd.Timestamp("2023-01-02") + pd.to_timedelta(np.arange(len(df)), unit="D")

        def sp(idx: int, price: float, kind: str) -> SwingPoint:
            return SwingPoint(index=idx, datetime=dates[idx].to_pydatetime(), price=price, kind=kind, strength=5)

        swings = [
            sp(10, 12_000, "high"),
            sp(20, 9_000, "low"),
            sp(30, 11_500, "high"),
            sp(40, 9_500, "low"),
            sp(50, 11_000, "high"),
            sp(60, 10_000, "low"),
        ]

        engine = PatternEngine()
        results = engine._detect_triangles(df, swings, regime_fit=0.6, timeframe="1d")

        symmetric = [r for r in results if r.pattern_type == "symmetric_triangle"]
        assert symmetric, f"expected a symmetric_triangle, got {[r.pattern_type for r in results]}"
        assert symmetric[0].state == "confirmed", (
            f"clean breakout above the apex should reach 'confirmed', got {symmetric[0].state}"
        )


class TestRectangleCanBreakDownBearish:
    """Regression: _detect_rectangle only ever checked a breakout above resistance.
    A clean breakdown below support was invisible -- state stayed 'forming' forever,
    never 'invalidated', and the stale upside target kept pointing above a price that
    had already broken the other way.
    """

    def test_clean_downward_breakdown_reaches_confirmed_bearish(self):
        from app.services.pattern_engine import PatternEngine
        from app.services.swing_points import SwingPoint

        import numpy as np
        import pandas as pd

        closes = (
            list(np.linspace(11_000, 12_000, 10))  # up to first high (resistance test)
            + list(np.linspace(12_000, 10_000, 10))  # down to first low (support test)
            + list(np.linspace(10_000, 11_950, 10))  # up to second high
            + list(np.linspace(11_950, 10_050, 10))  # down to second low
            + list(np.linspace(10_050, 12_050, 10))  # up to third high
            + list(np.linspace(12_050, 10_000, 10))  # down to third low
            + list(np.linspace(10_000, 9_000, 15))  # clean breakdown below support (~10,017)
        )
        df = _build_ohlcv_from_closes(closes)
        dates = pd.Timestamp("2023-01-02") + pd.to_timedelta(np.arange(len(df)), unit="D")

        def sp(idx: int, price: float, kind: str) -> SwingPoint:
            return SwingPoint(index=idx, datetime=dates[idx].to_pydatetime(), price=price, kind=kind, strength=5)

        swings = [
            sp(10, 12_000, "high"),
            sp(20, 10_000, "low"),
            sp(30, 11_950, "high"),
            sp(40, 10_050, "low"),
            sp(50, 12_050, "high"),
            sp(60, 10_000, "low"),
        ]

        engine = PatternEngine()
        results = engine._detect_rectangle(df, swings, regime_fit=0.6, timeframe="1d")

        rectangles = [r for r in results if r.pattern_type == "rectangle"]
        assert rectangles, "expected a rectangle detection"
        rect = rectangles[0]
        assert rect.state == "confirmed", f"clean breakdown below support should reach 'confirmed', got {rect.state}"
        assert rect.target_level is not None and rect.invalidation_level is not None
        # bearish: target below the breakout level (support), invalidation above it.
        assert rect.target_level < rect.neckline < rect.invalidation_level


class TestDescendingTriangleRequiresFlatSupport:
    """Regression: descending_triangle used to match whenever highs were descending
    and lows were 'not ascending' -- which also matched lows that were clearly
    descending too (a parallel down-channel/wedge, not a converging triangle). A real
    descending triangle needs roughly flat support, mirroring how ascending_triangle
    already requires roughly flat resistance.
    """

    def test_parallel_falling_highs_and_lows_is_not_a_descending_triangle(self):
        from app.services.pattern_engine import PatternEngine
        from app.services.swing_points import SwingPoint
        from datetime import datetime, timedelta

        base = datetime(2023, 1, 2)

        def sp(idx: int, price: float, kind: str) -> SwingPoint:
            return SwingPoint(index=idx, datetime=base + timedelta(days=idx), price=price, kind=kind, strength=5)

        # Highs fall 12,000 -> 11,000 -> 10,000; lows fall 9,000 -> 8,000 -> 7,000 --
        # both clearly descending in parallel, not converging on a flat support line.
        swings = [
            sp(10, 12_000, "high"),
            sp(15, 9_000, "low"),
            sp(30, 11_000, "high"),
            sp(35, 8_000, "low"),
            sp(50, 10_000, "high"),
            sp(55, 7_000, "low"),
        ]
        import numpy as np

        closes = list(np.linspace(12_000, 7_000, 60))
        df = _build_ohlcv_from_closes(closes)

        engine = PatternEngine()
        results = engine._detect_triangles(df, swings, regime_fit=0.6, timeframe="1d")

        descending = [r for r in results if r.pattern_type == "descending_triangle"]
        assert not descending, (
            f"parallel falling highs/lows should not be classified as descending_triangle, got {results}"
        )
