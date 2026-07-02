"""Regression tests for the forming/armed pattern quality-scoring fix.

Context: breakout_quality_fit and retest_quality_fit are only meaningful once a
breakout has actually happened. For forming/armed patterns they sit at their
(low) unset defaults, which previously dragged down formation quality — and
therefore textbook_similarity, probability caps, and completion_proximity —
for otherwise well-formed pre-breakout setups. These tests lock in that a
strong forming/armed pattern now clearly outscores a weak one, using only the
pre-breakout-meaningful signals.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.analysis_service import _completion_proximity, _formation_completion_quality
from app.services.pattern_engine import PatternResult, _finalize_textbook_similarity, _formation_quality_score
from app.services.probability_engine import _formation_quality, _probability_cap


def _pattern(state: str, *, strong: bool, pattern_type: str = "double_bottom", **overrides) -> PatternResult:
    if strong:
        base = dict(
            leg_balance_fit=0.90,
            reversal_energy_fit=0.85,
            variant_fit=0.88,
            candlestick_confirmation_fit=0.70,
            geometry_fit=0.80,
            swing_structure_fit=0.75,
            volume_context_fit=0.70,
            volatility_context_fit=0.65,
            regime_fit=0.60,
        )
    else:
        base = dict(
            leg_balance_fit=0.35,
            reversal_energy_fit=0.30,
            variant_fit=0.35,
            candlestick_confirmation_fit=0.40,
            geometry_fit=0.40,
            swing_structure_fit=0.35,
            volume_context_fit=0.30,
            volatility_context_fit=0.30,
            regime_fit=0.50,
        )
    # breakout_quality_fit / retest_quality_fit are always at their pre-breakout
    # defaults for forming/armed patterns (no breakout has occurred yet).
    base["breakout_quality_fit"] = 0.35
    base["retest_quality_fit"] = 0.45
    base.update(overrides)
    return PatternResult(
        pattern_type=pattern_type,
        state=state,
        grade="B",
        start_dt=datetime(2026, 1, 1),
        end_dt=None,
        neckline=100.0,
        invalidation_level=90.0,
        target_level=115.0,
        **base,
    )


class TestPatternEngineFormationQualityScore:
    def test_forming_ignores_breakout_and_retest_defaults(self):
        strong = _pattern("forming", strong=True)
        weak = _pattern("forming", strong=False)
        assert _formation_quality_score(strong) > 0.75
        assert _formation_quality_score(weak) < 0.40
        assert _formation_quality_score(strong) > _formation_quality_score(weak)

    def test_armed_uses_the_same_pre_breakout_weighting_as_forming(self):
        strong = _pattern("armed", strong=True)
        assert _formation_quality_score(strong) == _formation_quality_score(_pattern("forming", strong=True))

    def test_confirmed_still_uses_full_weighting_including_breakout_retest(self):
        # Two confirmed patterns differing only in breakout/retest quality must NOT score
        # identically — those signals matter once a breakout has actually happened.
        good_breakout = _pattern("confirmed", strong=True, breakout_quality_fit=0.90, retest_quality_fit=0.90)
        poor_breakout = _pattern("confirmed", strong=True, breakout_quality_fit=0.20, retest_quality_fit=0.20)
        assert _formation_quality_score(good_breakout) > _formation_quality_score(poor_breakout)

    def test_strong_forming_pattern_gets_a_higher_textbook_similarity_cap(self):
        strong = _pattern("forming", strong=True)
        weak = _pattern("forming", strong=False)
        assert _finalize_textbook_similarity(strong) > _finalize_textbook_similarity(weak)


class TestProbabilityEngineFormationQuality:
    def test_forming_ignores_breakout_and_retest_defaults(self):
        strong = _pattern("forming", strong=True)
        weak = _pattern("forming", strong=False)
        assert _formation_quality(strong) > 0.75
        assert _formation_quality(weak) < 0.40

    def test_confirmed_still_uses_full_weighting(self):
        good_breakout = _pattern("confirmed", strong=True, breakout_quality_fit=0.90, retest_quality_fit=0.90)
        poor_breakout = _pattern("confirmed", strong=True, breakout_quality_fit=0.20, retest_quality_fit=0.20)
        assert _formation_quality(good_breakout) > _formation_quality(poor_breakout)

    def test_strong_forming_pattern_earns_a_higher_probability_cap(self):
        strong = _pattern("forming", strong=True, textbook_similarity=0.80)
        weak = _pattern("forming", strong=False, textbook_similarity=0.56)
        common = dict(
            timeframe="1d",
            no_signal=False,
            reward_risk_ratio=2.0,
            headroom_score=0.6,
            target_distance_pct=0.03,
            avg_mfe_pct=0.06,
            edge_score=0.6,
            confidence=0.6,
            sample_reliability=0.6,
        )
        strong_cap = _probability_cap(strong, **common)
        weak_cap = _probability_cap(weak, **common)
        assert strong_cap > weak_cap


class TestCompletionProximity:
    def test_strong_forming_pattern_has_higher_completion_proximity_than_weak(self):
        strong = _pattern("forming", strong=True)
        weak = _pattern("forming", strong=False)
        # current_close chosen so price progress alone doesn't already saturate either case
        assert _completion_proximity(strong, current_close=93.0) > _completion_proximity(weak, current_close=93.0)

    def test_forming_no_longer_flatly_floors_at_a_fixed_value(self):
        strong = _pattern("forming", strong=True)
        weak = _pattern("forming", strong=False)
        # price sitting right at invalidation (no progress) so baseline dominates
        assert _completion_proximity(strong, current_close=90.0) >= 0.40
        assert _completion_proximity(weak, current_close=90.0) <= 0.30
        # the old implementation returned an identical flat 0.25 for both regardless of quality
        assert _completion_proximity(strong, current_close=90.0) - _completion_proximity(weak, current_close=90.0) >= 0.15

    def test_confirmed_stays_high_regardless_of_quality(self):
        strong = _pattern("confirmed", strong=True)
        weak = _pattern("confirmed", strong=False)
        assert _completion_proximity(strong, current_close=101.0) >= 0.85
        assert _completion_proximity(weak, current_close=101.0) >= 0.85

    def test_price_progress_can_still_exceed_baseline(self):
        weak = _pattern("armed", strong=False)
        # price already very close to neckline -> progress should dominate the low baseline
        result = _completion_proximity(weak, current_close=99.0)
        assert result > 0.85
