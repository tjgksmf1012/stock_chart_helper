# -*- coding: utf-8 -*-
"""Tests for backtest_engine helpers (pure-function, no network/Redis)."""

from __future__ import annotations

import pytest

from app.services.backtest_engine import (
    _BACKTEST_CONFIG,
    _BACKTEST_TIMEFRAMES,
    _BACKTEST_UNIVERSE,
    _DEFAULT_WIN_RATES,
    _bucket_to_stat_line,
    _default_stat_line,
    _default_stats,
    _edge_score,
    _effective_sample_size,
    _is_bullish,
    _resolve_bar_outcome,
)


class TestResolveBarOutcome:
    """Regression: a bar that touches both the target and the stop in the same
    day/week must resolve as a loss (conservative -- we can't know from OHLC alone
    which was hit first), not always a win. Mirrors offline_calibration.py's
    simulate_window_outcome(), which already got this right.
    """

    def test_bullish_bar_touching_both_target_and_stop_resolves_as_loss(self):
        # target=110, stop=95; a wide bar with low=90 (below stop) and high=115 (above target).
        outcome = _resolve_bar_outcome(high=115, low=90, target=110, invalidation=95, bullish=True)
        assert outcome is False

    def test_bearish_bar_touching_both_target_and_stop_resolves_as_loss(self):
        # target=90 (price falling to it), stop=105; wide bar high=110, low=85.
        outcome = _resolve_bar_outcome(high=110, low=85, target=90, invalidation=105, bullish=False)
        assert outcome is False

    def test_bullish_bar_hitting_only_target_is_a_win(self):
        outcome = _resolve_bar_outcome(high=112, low=101, target=110, invalidation=95, bullish=True)
        assert outcome is True

    def test_bullish_bar_hitting_only_stop_is_a_loss(self):
        outcome = _resolve_bar_outcome(high=100, low=93, target=110, invalidation=95, bullish=True)
        assert outcome is False

    def test_bar_hitting_neither_is_none(self):
        outcome = _resolve_bar_outcome(high=103, low=98, target=110, invalidation=95, bullish=True)
        assert outcome is None


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

    def test_flagged_as_synthetic(self):
        # A hand-tuned default must be distinguishable from a real backtest result --
        # otherwise a UI showing both renders them with identical apparent confidence.
        stat = _default_stat_line("double_bottom", "1d", 0.58, 20)
        assert stat["is_synthetic"] is True


class TestBucketToStatLineIsSynthetic:
    def test_real_backtest_result_is_not_flagged_as_synthetic(self):
        bucket = {"wins": 12, "total": 20, "timeouts": 5, "mfe_sum": 0.08 * 20, "mae_sum": 0.03 * 20, "bars_sum": 10.0 * 20}
        line = _bucket_to_stat_line("double_bottom", "1d", bucket)
        assert line is not None
        assert line["is_synthetic"] is False


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


class TestEffectiveSampleSize:
    def test_discounts_overlapping_windows(self):
        # 1d: window=60, step=10 -> overlap_factor ~= 1/6, but never below the
        # "종목 수만큼은 독립"이라는 바닥(len(_BACKTEST_UNIVERSE))보다 작게 깎이진 않는다.
        total = 300
        effective = _effective_sample_size(total, "1d")
        assert effective < total
        assert effective >= min(total, len(_BACKTEST_UNIVERSE))

    def test_never_exceeds_raw_total(self):
        for tf in _BACKTEST_TIMEFRAMES:
            assert _effective_sample_size(10, tf) <= 10

    def test_zero_total_is_zero(self):
        assert _effective_sample_size(0, "1d") == 0

    def test_small_total_floors_at_least_one(self):
        assert _effective_sample_size(1, "1d") >= 1

    def test_distinct_stock_count_overrides_universe_wide_floor(self):
        # Regression: the floor used to always be len(_BACKTEST_UNIVERSE) (79) regardless
        # of how many distinct stocks actually produced this specific pattern/timeframe
        # bucket -- a rare pattern seen on only 4 stocks would get its reliability floored
        # as if all 79 confirmed it. Passing the real per-bucket count should use that
        # instead.
        total = 300
        effective_with_few_stocks = _effective_sample_size(total, "1d", distinct_stock_count=4)
        assert effective_with_few_stocks < len(_BACKTEST_UNIVERSE)
        assert effective_with_few_stocks >= 4

    def test_omitting_distinct_stock_count_keeps_old_universe_wide_floor(self):
        total = 300
        effective = _effective_sample_size(total, "1d")
        assert effective >= min(total, len(_BACKTEST_UNIVERSE))


class TestBucketToStatLine:
    def _bucket(self, wins=12, total=20, timeouts=5, mfe=0.08, mae=0.03, bars=10.0) -> dict:
        return {"wins": wins, "total": total, "timeouts": timeouts, "mfe_sum": mfe * total, "mae_sum": mae * total, "bars_sum": bars * total}

    def test_win_rate_includes_timeouts_in_denominator(self):
        # 12승 + (20-12)패 = 8패, timeout 5건 -> attempts = 25, win_rate = 12/25 = 0.48
        # (해소표본만 썼다면 12/20=0.60으로 실제보다 낙관적으로 나왔을 것)
        line = _bucket_to_stat_line("double_bottom", "1d", self._bucket(wins=12, total=20, timeouts=5))
        assert line is not None
        assert line["win_rate"] == pytest.approx(12 / 25, abs=0.001)
        assert line["total"] == 25
        assert line["resolution_rate"] == pytest.approx(20 / 25, abs=0.001)

    def test_below_minimum_attempts_returns_none(self):
        line = _bucket_to_stat_line("double_bottom", "1d", self._bucket(wins=1, total=2, timeouts=1))
        assert line is None

    def test_all_timeout_returns_none(self):
        bucket = {"wins": 0, "total": 0, "timeouts": 10, "mfe_sum": 0.0, "mae_sum": 0.0, "bars_sum": 0.0}
        assert _bucket_to_stat_line("double_bottom", "1d", bucket) is None

    def test_sample_size_is_discounted_but_total_is_raw(self):
        line = _bucket_to_stat_line("double_bottom", "1d", self._bucket(wins=60, total=100, timeouts=20))
        assert line is not None
        assert line["total"] == 120
        assert line["sample_size"] <= line["total"]


class TestBacktestStockSync:
    """_backtest_stock_sync 결과 계약 — timeout 포함, win_rate 분리 검증."""

    def test_every_row_has_outcome(self, sample_ohlcv_df_long):
        from app.services.backtest_engine import _backtest_stock_sync

        rows = _backtest_stock_sync("1d", sample_ohlcv_df_long)
        for row in rows:
            assert row["outcome"] in {"win", "loss", "timeout"}
            # resolved 행은 win 불리언이 outcome과 일치
            if row["outcome"] != "timeout":
                assert row["win"] == (row["outcome"] == "win")

    def test_timeout_reachable_on_realistic_walk(self, sample_ohlcv_df_long):
        from app.services.backtest_engine import _backtest_stock_sync

        # 랜덤워크 300봉에서는 목표·손절 어디에도 안 닿는 timeout이 실제로 발생한다.
        # (이 표본은 win_rate 분모(attempts)에는 들어가되 MFE/MAE/bars 평균에서는 빠진다)
        rows = _backtest_stock_sync("1d", sample_ohlcv_df_long)
        assert any(r["outcome"] == "timeout" for r in rows)
        assert any(r["outcome"] in {"win", "loss"} for r in rows)
