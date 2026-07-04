from __future__ import annotations

import json
import random

import pytest

from app.services import probability_model as pm


@pytest.fixture(autouse=True)
def _isolated_model_path(tmp_path, monkeypatch):
    """Point the model file at a scratch path and reset the module cache so
    tests don't leak state into each other or touch the real data/ dir."""
    settings = pm.get_settings()
    monkeypatch.setattr(settings, "probability_model_path", str(tmp_path / "model.json"))
    pm._cache["mtime"] = None
    pm._cache["model"] = None
    yield
    pm._cache["mtime"] = None
    pm._cache["model"] = None


def _flat_features(rule: float = 0.5) -> dict[str, float]:
    return {name: (rule if name == "rule" else 0.5) for name in pm.FEATURE_NAMES}


class TestPredictWithoutModel:
    def test_returns_none_when_no_file_exists(self):
        assert pm.predict_directional_probability(_flat_features()) is None


class TestFitProbabilityModel:
    def test_returns_none_below_min_samples(self):
        rows = [(_flat_features(0.9), True)] * 50  # well under MIN_FIT_SAMPLES
        assert pm.fit_probability_model(rows) is None

    def test_learns_that_a_predictive_feature_actually_predicts_wins(self):
        # "rule" strongly predicts the outcome; every other feature is pure noise --
        # a correctly-wired logistic regression should recover that "rule" matters
        # and the noise features don't.
        random.seed(0)
        rows: list[tuple[dict[str, float], bool]] = []
        for _ in range(300):
            is_win = random.random() < 0.5
            rule_value = random.uniform(0.7, 0.95) if is_win else random.uniform(0.05, 0.3)
            features = {name: random.uniform(0.4, 0.6) for name in pm.FEATURE_NAMES}
            features["rule"] = rule_value
            rows.append((features, is_win))

        model = pm.fit_probability_model(rows)
        assert model is not None
        assert model.sample_size == 300
        assert len(model.coef) == len(pm.FEATURE_NAMES)
        assert model.feature_names == list(pm.FEATURE_NAMES)

        # fit_probability_model() deliberately doesn't auto-persist.
        pm.save_probability_model(model)

        p_high_rule = pm.predict_directional_probability(_flat_features(0.9))
        p_low_rule = pm.predict_directional_probability(_flat_features(0.1))
        assert p_high_rule is not None and p_low_rule is not None
        assert p_high_rule > 0.5 > p_low_rule


class TestSaveAndLoadRoundTrip:
    def test_save_then_predict_uses_persisted_model(self):
        model = pm.ProbabilityModel(
            feature_names=list(pm.FEATURE_NAMES),
            mean=[0.5] * len(pm.FEATURE_NAMES),
            scale=[1.0] * len(pm.FEATURE_NAMES),
            coef=[0.0] * len(pm.FEATURE_NAMES),
            intercept=0.0,
            sample_size=500,
            fitted_at="2026-01-01T00:00:00",
        )
        pm.save_probability_model(model)
        # all-zero coef/intercept -> sigmoid(0) == 0.5 regardless of input features
        assert pm.predict_directional_probability(_flat_features(0.9)) == pytest.approx(0.5)

    def test_load_ignores_corrupt_file(self):
        settings = pm.get_settings()
        path = pm._resolve_path(settings.probability_model_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json {{{")

        assert pm.predict_directional_probability(_flat_features()) is None

    def test_load_ignores_model_with_mismatched_feature_names(self):
        # Guards against a stale model file left over from a previous FEATURE_NAMES
        # definition silently being applied with misaligned coefficients.
        settings = pm.get_settings()
        path = pm._resolve_path(settings.probability_model_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "feature_names": ["totally", "different", "features"],
            "mean": [0.5, 0.5, 0.5],
            "scale": [1.0, 1.0, 1.0],
            "coef": [1.0, 1.0, 1.0],
            "intercept": 0.0,
            "sample_size": 500,
            "fitted_at": "2026-01-01T00:00:00",
        }))

        assert pm.predict_directional_probability(_flat_features()) is None
