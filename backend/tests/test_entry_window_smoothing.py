"""Regression tests for the entry-window scoring cliff.

Before this fix, _entry_window_profile() had hard percentage cutoffs (e.g. exactly
2.5% past the breakout neckline for daily bars) where the score would fall off a
cliff — a fresh breakout at 2.4% scored ~0.80, but the same setup at 2.6% scored
~0.64, a ~20-point drop from a 0.2 percentage-point difference in price. Since a
single day's normal volatility routinely exceeds that gap, and the app only scans
a few times a day rather than continuously, the "실전 후보" (ready_now) tier —
which requires entry_window_score >= 0.68 — was effectively unreachable except in
a razor-thin window immediately after confirmation. This pins the smoothed
replacement: score should decay gradually with distance, not jump.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.analysis_service import _action_plan_profile, _entry_window_profile
from app.services.pattern_engine import PatternResult


def _confirmed_pattern(target: float = 11000.0) -> PatternResult:
    return PatternResult(
        pattern_type="double_bottom",
        state="confirmed",
        grade="A",
        start_dt=datetime(2023, 1, 1),
        end_dt=datetime(2023, 3, 1),
        neckline=9000.0,
        invalidation_level=8500.0,
        target_level=target,
    )


def _entry_window_at_extension(pct: float, target: float = 11000.0) -> dict:
    pattern = _confirmed_pattern(target)
    current_close = 9000.0 * (1 + pct / 100)
    reward_risk_ratio = (target - current_close) / (current_close - 8500.0)
    target_distance_pct = (target - current_close) / current_close
    stop_distance_pct = (current_close - 8500.0) / current_close
    return _entry_window_profile(
        timeframe="1d",
        pattern=pattern,
        current_close=current_close,
        reward_risk_ratio=reward_risk_ratio,
        headroom_score=0.75,
        target_distance_pct=target_distance_pct,
        stop_distance_pct=stop_distance_pct,
        completion_proximity=0.8,
        target_hit_at=None,
        invalidated_at=None,
    )


class TestNoCliffAtOldThreshold:
    def test_score_changes_gradually_around_old_2_5_percent_boundary(self):
        just_under = _entry_window_at_extension(2.4)["entry_window_score"]
        just_over = _entry_window_at_extension(2.6)["entry_window_score"]
        # A 0.2-point change in breakout extension shouldn't swing the score by
        # more than a few points — the old code jumped ~0.16 (0.80 -> 0.64) here.
        assert abs(just_under - just_over) < 0.05

    def test_score_decays_monotonically_with_extension(self):
        pcts = [0.5, 1.0, 2.0, 3.0, 4.0]
        scores = [_entry_window_at_extension(p)["entry_window_score"] for p in pcts]
        assert scores == sorted(scores, reverse=True)

    def test_no_single_step_drop_exceeds_a_few_points(self):
        pcts = [round(x * 0.5, 1) for x in range(1, 11)]  # 0.5 .. 5.0 in 0.5 steps
        scores = [_entry_window_at_extension(p)["entry_window_score"] for p in pcts]
        for a, b in zip(scores, scores[1:]):
            assert a - b < 0.08


class TestReadyNowReachableOutsideRazorThinWindow:
    def test_ready_now_reachable_at_1_percent_past_breakout(self):
        assert self._action_plan_at(1.0)["action_plan"] == "ready_now"

    def test_ready_now_reachable_at_3_percent_past_breakout(self):
        # This was impossible before the fix (already deep in the "확장 추격" cap).
        assert self._action_plan_at(3.0)["action_plan"] == "ready_now"

    def test_ready_now_reachable_at_4_percent_past_breakout(self):
        assert self._action_plan_at(4.0)["action_plan"] == "ready_now"

    def _action_plan_at(self, pct: float) -> dict:
        target = 11000.0
        pattern = _confirmed_pattern(target)
        current_close = 9000.0 * (1 + pct / 100)
        reward_risk_ratio = (target - current_close) / (current_close - 8500.0)
        target_distance_pct = (target - current_close) / current_close
        stop_distance_pct = (current_close - 8500.0) / current_close
        ew = _entry_window_profile(
            timeframe="1d",
            pattern=pattern,
            current_close=current_close,
            reward_risk_ratio=reward_risk_ratio,
            headroom_score=0.75,
            target_distance_pct=target_distance_pct,
            stop_distance_pct=stop_distance_pct,
            completion_proximity=0.8,
            target_hit_at=None,
            invalidated_at=None,
        )
        return _action_plan_profile(
            timeframe="1d",
            pattern=pattern,
            p_up=0.65,
            p_down=0.35,
            entry_score=ew["entry_window_score"],
            completion_proximity=0.8,
            recency_score=0.9,
            data_quality=0.9,
            reward_risk_ratio=reward_risk_ratio,
            headroom_score=0.75,
            entry_window_score=ew["entry_window_score"],
            entry_window_label=ew["entry_window_label"],
            freshness_score=0.85,
            freshness_label="신선",
            reentry_score=0.5,
            reentry_label="none",
            historical_edge_score=0.7,
            trend_alignment_score=0.8,
            intraday_session_score=0.5,
            target_hit_at=None,
            invalidated_at=None,
            fetch_status="live_ok",
        )


class TestStillGatesOnRewardRisk:
    def test_poor_reward_risk_still_caps_score_low(self):
        # Deep extension with degraded reward:risk should still land in "관망",
        # not be rescued by the smoothing fix.
        result = _entry_window_at_extension(15.0)
        assert result["entry_window_score"] < 0.4
        assert result["entry_window_label"] == "관망"

    def test_fresh_breakout_below_1_15_rr_gets_a_small_penalty(self):
        # Same extension, lower reward:risk (via a nearer target) should score
        # a bit lower than the same extension with a generous target, but not cliff.
        generous = _entry_window_at_extension(1.0, target=11000.0)
        tight = _entry_window_at_extension(1.0, target=9300.0)
        assert tight["entry_window_score"] < generous["entry_window_score"]
