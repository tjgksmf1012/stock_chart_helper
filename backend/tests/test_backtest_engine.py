# -*- coding: utf-8 -*-
"""Tests for backtest_engine helpers (pure-function, no network/Redis)."""

from __future__ import annotations

import pytest

from app.services.backtest_engine import (
    _BACKTEST_CONFIG,
    _BACKTEST_TIMEFRAMES,
    _BACKTEST_UNIVERSE,
    _DEFAULT_WIN_RATES,
    _default_stat_line,
    _default_stats,
    _edge_score,
    _is_bullish,
)


class TestEdgeScore:
    def test_returns_float_in_range(self):
        score = _edge_score(0.6, 0.12, 0.05, 10.0, 40)
        assert 0.0 <= score <= 1.0

    def test_better_win_rate_gives_higher_score(self):
        low = _edge_score(0.50, 0.10, 0.06, 12.0, 40)
        high = _edge_score(0.70, 0.10, 0.06, 12.0, 40)
        assert high > low

    def test_zero_mae_safe(self):
        """avg_mae_pct=0 should not raise (guarded with max(…, 0.01))."""
        score = _edge_score(0.55, 0.08, 0.0, 10.0, 40)
        assert 0.0 <= score <= 1.0

    def test_extreme_inputs_clamped(self):
        score = _edge_score(1.0, 1.0, 0.0, 1.0, 40)
        assert score <= 1.0
        score = _edge_score(0.0, 0.0, 1.0, 40.0, 40)
        assert score >= 0.0


class TestDefaultStatLine:
    def test_returns_all_required_keys(self):
        stat = _default_stat_line("double_bottom", "1d", 0.58, 20)
        required = {"pattern_type", "timeframe", "win_rate", "sample_size", "wins", "total", "avg_mfe_pct", "avg_mae_pct", "avg_bars_to_outcome", "historical_edge_score"}
        assert required.issubset(stat.keys())

    def test_win_rate_preserved(self):
        stat = _default_stat_line("cup_and_handle", "1wk", 0.62, 16)
        assert stat["win_rate"] == pytest.approx(0.62, abs=0.001)

    def test_historical_edge_in_range(self):
        for pt, wr in _DEFAULT_WIN_RATES.items():
            for tf in _BACKTEST_TIMEFRAMES:
                stat = _default_stat_line(pt, tf, wr, 16)
                assert 0.0 <= stat["historical_edge_score"] <= 1.0


class TestDefaultStats:
    def test_covers_all_timeframes(self):
        stats = _default_stats()
        assert set(stats.keys()) == set(_BACKTEST_TIMEFRAMES)

    def test_covers_all_patterns(self):
        stats = _default_stats()
        for tf in _BACKTEST_TIMEFRAMES:
            assert set(stats[tf].keys()) == set(_DEFAULT_WIN_RATES.keys())


class TestIsBullish:
    @pytest.mark.parametrize("pt", ["double_bottom", "inverse_head_and_shoulders", "ascending_triangle", "cup_and_handle", "rounding_bottom", "rectangle"])
    def test_bullish_patterns(self, pt):
        assert _is_bullish(pt) is True

    @pytest.mark.parametrize("pt", ["double_top", "head_and_shoulders", "descending_triangle", "falling_channel"])
    def test_non_bullish_patterns(self, pt):
        assert _is_bullish(pt) is False


class TestUniverseExpansion:
    def test_universe_size(self):
        """Universe should have at least 30 stocks after expansion."""
        assert len(_BACKTEST_UNIVERSE) >= 30, f"Universe too small: {len(_BACKTEST_UNIVERSE)} stocks"

    def test_no_duplicate_codes(self):
        assert len(_BACKTEST_UNIVERSE) == len(set(_BACKTEST_UNIVERSE)), "Duplicate codes found"

    def test_codes_are_6_digits(self):
        for code in _BACKTEST_UNIVERSE:
            assert code.isdigit() and len(code) == 6, f"Invalid code: {code}"

    def test_config_covers_timeframes(self):
        for tf in _BACKTEST_TIMEFRAMES:
            assert tf in _BACKTEST_CONFIG
