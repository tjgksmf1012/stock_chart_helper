from __future__ import annotations

from datetime import datetime

import pytest

from app.services.pattern_engine import PatternResult
from app.services.probability_engine import compute_probability, compute_probability_with_features
from app.services.probability_model import FEATURE_NAMES


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
        volume_context_fit=0.70,
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


def test_volume_context_fit_moves_the_hand_tuned_probability():
    # Regression: volume_context_fit is real research signal (breakout-day volume
    # confirmation is one of the most consistently cited discriminators in the
    # technical-analysis literature) but used to be folded only into
    # textbook_similarity/formation_quality with no independent weight in either
    # the hand-tuned formula or the trainable feature vector. It must now move
    # its own-direction probability measurably, holding everything else fixed.
    strong_volume = make_pattern("double_bottom", volume_context_fit=0.95)
    weak_volume = make_pattern("double_bottom", volume_context_fit=0.10)
    out_strong = compute_probability(strong_volume, **HEALTHY)
    out_weak = compute_probability(weak_volume, **HEALTHY)
    assert out_strong.p_up > out_weak.p_up


def test_direction_neutral_pattern_leans_down_when_breakdown_is_bearish():
    pattern = make_pattern("rectangle", neckline=100.0, target_level=80.0)
    out = compute_probability(pattern, **HEALTHY)
    assert out.p_down > out.p_up


class TestCalibrationIsApplied:
    """Regression: 학습 모델이 없고 보정 매핑이 있으면 최종 p_up에 반영돼야 한다.

    단, 보정 결과는 3분법(승/패/미해소) 승률이므로 (c, 1-c)로 그대로 넣지 않고
    기저율 대비 초과분만 방향 우위로 반영한다 — 기저율 30%대 매핑이 약세 패턴을
    "상승 70%"로 반전시키던 버그(2026-07)의 회귀 방지.
    """

    def test_flat_mapping_at_base_rate_neutralizes_direction(self, monkeypatch):
        import app.services.probability_engine as pe

        baseline = compute_probability(make_pattern("double_bottom"), **HEALTHY)
        assert baseline.p_up != pytest.approx(0.5)  # sanity: heuristic normally leans away from 0.5

        # 매핑이 모든 입력을 기저율로 납작하게 만들면 방향 우위는 사라져 0.5가 된다.
        monkeypatch.setattr(pe, "calibrate_probability", lambda raw: 0.30)
        monkeypatch.setattr(pe, "calibration_base_rate", lambda: 0.30)
        out = compute_probability(make_pattern("double_bottom"), **HEALTHY)

        assert out.p_up == pytest.approx(0.5, abs=1e-6)
        assert out.p_down == pytest.approx(0.5, abs=1e-6)
        assert out.pattern_win_rate == pytest.approx(0.30)  # 실측 승률은 별도 필드로 노출

    def test_calibration_shifts_direction_relative_to_base_rate(self, monkeypatch):
        import app.services.probability_engine as pe

        monkeypatch.setattr(pe, "calibration_base_rate", lambda: 0.30)

        monkeypatch.setattr(pe, "calibrate_probability", lambda raw: 0.40)
        up = compute_probability(make_pattern("double_bottom"), **HEALTHY)
        assert up.p_up > 0.5  # 기저율보다 나은 셋업 → 자기 방향 우위

        monkeypatch.setattr(pe, "calibrate_probability", lambda raw: 0.20)
        down = compute_probability(make_pattern("double_bottom"), **HEALTHY)
        assert down.p_up < 0.5  # 기저율보다 나쁜 셋업 → 자기 방향 확신 하락


class TestComputeProbabilityWithFeatures:
    """compute_probability_with_features() must be a strict superset of
    compute_probability() (same ProbabilityOutput) plus the 10-component feature
    vector that scripts/fit_probability_model.py trains on.
    """

    def test_matches_compute_probability_and_returns_all_feature_names(self):
        pattern = make_pattern("double_bottom")
        plain = compute_probability(pattern, **HEALTHY)
        out, features = compute_probability_with_features(pattern, **HEALTHY)

        assert out == plain
        assert features is not None
        assert set(features.keys()) == set(FEATURE_NAMES)
        assert all(0.0 <= v <= 1.0 for v in features.values())

    def test_features_is_none_for_no_signal_early_returns(self):
        _, features = compute_probability_with_features(make_pattern(state="invalidated"), **HEALTHY)
        assert features is None

        args = {**HEALTHY, "sample_size": 3, "wins": 2, "total": 3}
        _, features = compute_probability_with_features(make_pattern(), **args)
        assert features is None

    def test_own_direction_features_match_regardless_of_bullish_or_bearish(self):
        # A bullish and a bearish pattern built from identical underlying quality
        # inputs (same textbook_similarity, state, etc.) should produce identical
        # "own direction" feature values -- confidence in *its own* direction,
        # not literal "up". Getting this backwards was a real bug caught before
        # shipping: raw *_up values flip meaning depending on pattern direction.
        bullish_pattern = make_pattern("double_bottom")
        bearish_pattern = make_pattern("double_top")
        _, bullish_features = compute_probability_with_features(bullish_pattern, **HEALTHY)
        _, bearish_features = compute_probability_with_features(bearish_pattern, **HEALTHY)

        assert bullish_features is not None and bearish_features is not None
        for name in FEATURE_NAMES:
            assert bullish_features[name] == pytest.approx(bearish_features[name], abs=1e-9), name


class TestProbabilityModelOverride:
    """Regression: a fitted probability model must actually replace the hand-tuned
    weighted sum, otherwise scripts/fit_probability_model.py's output would
    silently have no effect on the app (same failure mode already fixed once for
    probability_calibration.py's isotonic mapping).
    """

    def test_model_prediction_propagates_into_final_p_up(self, monkeypatch):
        import app.services.probability_engine as pe

        baseline = compute_probability(make_pattern("double_bottom"), **HEALTHY)
        assert baseline.p_up != pytest.approx(0.5)  # sanity: heuristic normally leans away from 0.5

        # Pretend a fitted model is very confident in the *opposite* of what the
        # hand-tuned formula would say, to make the override unmistakable.
        monkeypatch.setattr(pe, "predict_directional_probability", lambda features: 0.05)
        out = compute_probability(make_pattern("double_bottom"), **HEALTHY)

        # own-direction p = 0.05 for a bullish pattern -> p_up_raw = 0.05 (pre-cap/
        # pre-calibration), i.e. p_up should end up far lower than the baseline.
        assert out.p_up < baseline.p_up


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


def test_low_base_rate_model_does_not_invert_direction(monkeypatch):
    # 실측 기저 승률이 30%대인 학습 모델이 있어도, 약세 패턴이 "상승 69%"로
    # 반전되면 안 된다 (2026-07 실측 버그 회귀 방지). 모델 출력은 3분법 승률이라
    # 기저율 대비 초과분만 방향 우위로 반영돼야 한다.
    monkeypatch.setattr(
        "app.services.probability_engine.predict_directional_probability", lambda features: 0.31
    )
    monkeypatch.setattr("app.services.probability_engine.model_base_rate", lambda: 0.30)

    up = compute_probability(make_pattern("double_bottom"), **HEALTHY)
    down = compute_probability(make_pattern("double_top"), **HEALTHY)

    assert up.p_up > up.p_down          # 기저율보다 나은 강세 셋업은 여전히 위쪽으로
    assert down.p_down > down.p_up      # 약세 패턴이 상승 우위로 뒤집히지 않음
    assert up.pattern_win_rate == pytest.approx(0.31)  # 실측 승률은 별도 지표로 그대로 노출


def test_below_base_rate_model_leans_against_pattern(monkeypatch):
    # 기저율보다 나쁜 셋업이면 자기 방향 확신이 0.5 아래로 내려가는 건 정상이지만,
    # 클램프(0.2) 밖으로 폭주하지 않아야 한다.
    monkeypatch.setattr(
        "app.services.probability_engine.predict_directional_probability", lambda features: 0.05
    )
    monkeypatch.setattr("app.services.probability_engine.model_base_rate", lambda: 0.30)

    out = compute_probability(make_pattern("double_bottom"), **HEALTHY)
    assert out.p_up < 0.5
    assert out.p_up >= 0.2
