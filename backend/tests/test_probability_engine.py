from __future__ import annotations

from datetime import datetime

import pytest

from app.services.pattern_engine import PatternResult
from app.services.probability_engine import compute_probability


def make_pattern(pattern_type: str = "double_bottom", state: str = "confirmed", **over) -> PatternResult:
    base = dict(
        pattern_type=pattern_type,
        state=state,
        grade="A",
        start_dt=datetime(2026, 1, 1),
        end_dt=datetime(2026, 2, 1),
        invalidation_level=90.0,
        target_level=120.0,
        textbook_similarity=0.70,
        leg_balance_fit=0.70,
        reversal_energy_fit=0.70,
        variant_fit=0.70,
        breakout_quality_fit=0.70,
        retest_quality_fit=0.70,
        candlestick_confirmation_fit=0.70,
    )
    base.update(over)
    return PatternResult(**base)


# Inputs strong enough to clear every "no signal" gate, so we can assert on a live signal.
HEALTHY = dict(
    timeframe="1d",
    similar_win_rate=0.62,
    sample_size=40,
    liquidity_score=0.70,
    regime_match=0.60,
    data_quality=0.90,
    completion_proximity=0.70,
    recency_score=0.70,
    reward_risk_ratio=2.0,
    headroom_score=0.60,
    target_distance_pct=0.05,
    stop_distance_pct=0.03,
    avg_mfe_pct=0.08,
    avg_mae_pct=0.04,
    avg_bars_to_outcome=8.0,
    historical_edge_score=0.60,
    wins=25,
    total=40,
)


def test_invalidated_pattern_is_no_signal_and_neutral():
    out = compute_probability(make_pattern(state="invalidated"), **HEALTHY)
    assert out.no_signal_flag is True
    assert out.p_up == 0.5 and out.p_down == 0.5
    assert out.confidence == 0.0


def test_played_out_pattern_is_no_signal():
    out = compute_probability(make_pattern(state="played_out"), **HEALTHY)
    assert out.no_signal_flag is True


def test_tiny_sample_is_no_signal():
    args = {**HEALTHY, "sample_size": 3, "wins": 2, "total": 3}
    out = compute_probability(make_pattern(), **args)
    assert out.no_signal_flag is True
    assert out.p_up == 0.5


def test_probabilities_sum_to_one_and_within_bounds():
    out = compute_probability(make_pattern(), **HEALTHY)
    assert abs(out.p_up + out.p_down - 1.0) <= 0.0011  # allow 3-decimal rounding slack
    assert 0.0 <= out.p_up <= 1.0
    assert 0.0 <= out.p_down <= 1.0


def test_bullish_confirmed_leans_up_and_emits_signal():
    out = compute_probability(make_pattern("double_bottom"), **HEALTHY)
    assert out.no_signal_flag is False
    assert out.p_up > out.p_down


def test_bearish_confirmed_leans_down():
    out = compute_probability(make_pattern("double_top"), **HEALTHY)
    assert out.p_down > out.p_up


def test_direction_neutral_pattern_leans_up_when_breakout_is_bullish():
    # rectangle has no fixed direction — instance direction comes from target vs neckline.
    pattern = make_pattern("rectangle", neckline=100.0, target_level=120.0)
    out = compute_probability(pattern, **HEALTHY)
    assert out.p_up > out.p_down


def test_direction_neutral_pattern_leans_down_when_breakdown_is_bearish():
    pattern = make_pattern("rectangle", neckline=100.0, target_level=80.0)
    out = compute_probability(pattern, **HEALTHY)
    assert out.p_down > out.p_up


class TestCalibrationIsApplied:
    """Regression: compute_probability must run its raw p_up/p_down through
    probability_calibration.calibrate_probability() before capping, otherwise
    a fitted recalibration mapping would silently have no effect on the app.
    """

    def test_calibrated_value_propagates_into_final_p_up(self, monkeypatch):
        import app.services.probability_engine as pe

        baseline = compute_probability(make_pattern("double_bottom"), **HEALTHY)
        assert baseline.p_up != pytest.approx(0.5)  # sanity: heuristic normally leans away from 0.5

        # Pretend the fitted mapping flattens every input to exactly 0.5.
        monkeypatch.setattr(pe, "calibrate_probability", lambda raw: 0.5)
        out = compute_probability(make_pattern("double_bottom"), **HEALTHY)

        assert out.p_up == pytest.approx(0.5, abs=1e-6)
        assert out.p_down == pytest.approx(0.5, abs=1e-6)


def test_direction_probability_is_capped_at_078():
    # Even with maxed-out inputs the directional probability must stay <= 0.78.
    args = {
        **HEALTHY,
        "similar_win_rate": 0.99,
        "wins": 40,
        "total": 40,
        "reward_risk_ratio": 5.0,
        "headroom_score": 1.0,
        "regime_match": 1.0,
        "completion_proximity": 1.0,
        "recency_score": 1.0,
        "historical_edge_score": 1.0,
    }
    out = compute_probability(make_pattern(textbook_similarity=0.95), **args)
    assert max(out.p_up, out.p_down) <= 0.78
