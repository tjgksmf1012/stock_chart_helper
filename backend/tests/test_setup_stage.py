"""Regression tests for _setup_stage's AND-gate softening.

Before this fix, reaching "trigger_ready" (armed) or "late_base" (forming) required
every independent factor (formation_quality, confluence_score, completion_proximity)
to *individually* clear the same high threshold. Chaining several near-independent
"AND >= 0.6-ish" conditions makes the joint probability of reaching the top tier much
lower than any single factor's pass rate would suggest -- the same class of bug as the
entry-window score cliff fixed elsewhere this session. The fix blends the factors with
weights (so an exceptionally strong factor can offset a merely-decent one) while still
requiring a floor on every factor, so a single terrible dimension can't be masked.
"""

from __future__ import annotations

from app.services.scanner import _setup_stage


def _row(**overrides) -> dict:
    base = {
        "state": "armed",
        "completion_proximity": 0.6,
        "formation_quality": 0.6,
        "confluence_score": 0.6,
    }
    base.update(overrides)
    return base


class TestTriggerReadySoftAnd:
    def test_both_factors_comfortably_above_threshold_is_trigger_ready(self):
        row = _row(formation_quality=0.70, confluence_score=0.70)
        assert _setup_stage(row) == "trigger_ready"

    def test_one_strong_one_merely_decent_can_still_reach_trigger_ready(self):
        # confluence just below the old hard 0.62 cutoff, but formation_quality is strong --
        # under the old pure-AND gate this was unconditionally "breakout_watch".
        row = _row(formation_quality=0.75, confluence_score=0.55)
        assert _setup_stage(row) == "trigger_ready"

    def test_both_factors_weak_stays_breakout_watch(self):
        row = _row(formation_quality=0.40, confluence_score=0.40)
        assert _setup_stage(row) == "breakout_watch"

    def test_one_factor_very_weak_is_not_rescued_by_the_other(self):
        # formation_quality is excellent but confluence is genuinely poor -- the floor
        # should still block trigger_ready rather than let one axis carry the whole score.
        row = _row(formation_quality=0.95, confluence_score=0.20)
        assert _setup_stage(row) == "breakout_watch"


class TestLateBaseSoftAnd:
    def test_all_three_factors_strong_is_late_base(self):
        row = _row(state="forming", completion_proximity=0.75, formation_quality=0.60, confluence_score=0.60)
        assert _setup_stage(row) == "late_base"

    def test_one_factor_slightly_under_old_threshold_can_still_reach_late_base(self):
        row = _row(state="forming", completion_proximity=0.75, formation_quality=0.60, confluence_score=0.50)
        assert _setup_stage(row) == "late_base"

    def test_all_three_weak_falls_through_to_base_building(self):
        row = _row(state="forming", completion_proximity=0.30, formation_quality=0.30, confluence_score=0.30)
        assert _setup_stage(row) == "base_building"
