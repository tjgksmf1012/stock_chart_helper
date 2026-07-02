from __future__ import annotations

import pandas as pd
import pytest

from app.services.swing_points import (
    SwingPoint,
    alternating_swings,
    detect_swing_points,
    get_significant_swings,
)


def _df_from_highs_lows(highs: list[float], lows: list[float]) -> pd.DataFrame:
    dates = pd.bdate_range(start="2024-01-02", periods=len(highs))
    return pd.DataFrame({"date": dates, "high": highs, "low": lows, "close": [(h + l) / 2 for h, l in zip(highs, lows)]})


class TestDetectSwingPoints:
    def test_detects_a_clear_pivot_high(self):
        # A single sharp spike in the middle, flat elsewhere.
        highs = [100.0] * 5 + [110.0] + [100.0] * 5
        lows = [95.0] * 11
        df = _df_from_highs_lows(highs, lows)

        points = detect_swing_points(df, window=3)

        highs_found = [p for p in points if p.kind == "high"]
        assert len(highs_found) == 1
        assert highs_found[0].index == 5
        assert highs_found[0].price == 110.0
        assert highs_found[0].strength == 3

    def test_detects_a_clear_pivot_low(self):
        highs = [105.0] * 11
        lows = [100.0] * 5 + [90.0] + [100.0] * 5
        df = _df_from_highs_lows(highs, lows)

        points = detect_swing_points(df, window=3)

        lows_found = [p for p in points if p.kind == "low"]
        assert len(lows_found) == 1
        assert lows_found[0].index == 5
        assert lows_found[0].price == 90.0

    def test_flat_series_has_no_swings(self):
        df = _df_from_highs_lows([100.0] * 15, [95.0] * 15)
        points = detect_swing_points(df, window=3)
        assert points == []

    def test_results_are_sorted_by_index(self):
        # Two spikes: one low pivot then one high pivot later.
        highs = [100.0] * 5 + [100.0] + [100.0] * 4 + [120.0] + [100.0] * 4
        lows = [95.0] * 5 + [80.0] + [95.0] * 4 + [95.0] + [95.0] * 4
        df = _df_from_highs_lows(highs, lows)

        points = detect_swing_points(df, window=3)

        indices = [p.index for p in points]
        assert indices == sorted(indices)


class TestGetSignificantSwings:
    def test_short_series_returns_empty(self):
        df = _df_from_highs_lows([100.0] * 19, [95.0] * 19)
        assert get_significant_swings(df) == []

    def test_uses_larger_adaptive_window_for_long_series(self):
        # window = clamp(n // 20, min_window, max_window)
        n = 400
        df = _df_from_highs_lows([100.0] * n, [95.0] * n)
        # Even on a flat series we can confirm no crash and empty result for lack of pivots.
        assert get_significant_swings(df, min_window=3, max_window=10) == []

    def test_adaptive_window_is_clamped_to_max(self):
        n = 300  # n // 20 == 15, above max_window=10
        highs = [100.0] * (n // 2) + [150.0] + [100.0] * (n // 2 - 1)
        lows = [95.0] * n
        df = _df_from_highs_lows(highs, lows)

        points = get_significant_swings(df, min_window=3, max_window=10)

        assert all(p.strength == 10 for p in points)


class TestAlternatingSwings:
    def test_empty_input_returns_empty(self):
        assert alternating_swings([]) == []

    def test_already_alternating_is_unchanged(self):
        points = [
            SwingPoint(0, pd.Timestamp("2024-01-02").to_pydatetime(), 90.0, "low", 3),
            SwingPoint(5, pd.Timestamp("2024-01-09").to_pydatetime(), 110.0, "high", 3),
            SwingPoint(10, pd.Timestamp("2024-01-16").to_pydatetime(), 85.0, "low", 3),
        ]
        result = alternating_swings(points)
        assert result == points

    def test_consecutive_highs_keep_the_higher_one(self):
        points = [
            SwingPoint(0, pd.Timestamp("2024-01-02").to_pydatetime(), 100.0, "high", 3),
            SwingPoint(3, pd.Timestamp("2024-01-05").to_pydatetime(), 105.0, "high", 3),
        ]
        result = alternating_swings(points)
        assert len(result) == 1
        assert result[0].price == 105.0

    def test_consecutive_lows_keep_the_lower_one(self):
        points = [
            SwingPoint(0, pd.Timestamp("2024-01-02").to_pydatetime(), 90.0, "low", 3),
            SwingPoint(3, pd.Timestamp("2024-01-05").to_pydatetime(), 85.0, "low", 3),
        ]
        result = alternating_swings(points)
        assert len(result) == 1
        assert result[0].price == 85.0

    def test_consecutive_highs_ignore_a_lower_second_peak(self):
        points = [
            SwingPoint(0, pd.Timestamp("2024-01-02").to_pydatetime(), 105.0, "high", 3),
            SwingPoint(3, pd.Timestamp("2024-01-05").to_pydatetime(), 100.0, "high", 3),
        ]
        result = alternating_swings(points)
        assert len(result) == 1
        assert result[0].price == 105.0
