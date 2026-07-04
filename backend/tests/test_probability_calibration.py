from __future__ import annotations

import pytest

from app.services import probability_calibration as pc


@pytest.fixture(autouse=True)
def _isolated_calibration_path(tmp_path, monkeypatch):
    """Point the calibration file at a scratch path and reset the module cache
    so tests don't leak state into each other or touch the real data/ dir."""
    settings = pc.get_settings()
    monkeypatch.setattr(settings, "probability_calibration_path", str(tmp_path / "calibration.json"))
    pc._cache["mtime"] = None
    pc._cache["mapping"] = None
    yield
    pc._cache["mtime"] = None
    pc._cache["mapping"] = None


class TestCalibrateProbabilityWithoutMapping:
    def test_returns_input_unchanged_when_no_file_exists(self):
        assert pc.calibrate_probability(0.73) == 0.73
        assert pc.calibrate_probability(0.12) == 0.12


class TestFitCalibrationMapping:
    def test_returns_none_below_min_samples(self):
        pairs = [(0.6, True)] * 50  # well under MIN_FIT_SAMPLES
        assert pc.fit_calibration_mapping(pairs) is None

    def test_fits_a_monotonic_mapping_with_enough_samples(self):
        # Construct a case where the heuristic is systematically overconfident:
        # it says 0.8 but real win rate at that level is only ~0.5, and it says
        # 0.5 but real win rate there is ~0.3. Isotonic regression should recover
        # a monotonic correction that reflects this.
        pairs = []
        for _ in range(150):
            pairs.append((0.8, True))
        for _ in range(150):
            pairs.append((0.8, False))
        for _ in range(90):
            pairs.append((0.5, True))
        for _ in range(210):
            pairs.append((0.5, False))

        mapping = pc.fit_calibration_mapping(pairs)
        assert mapping is not None
        assert mapping.sample_size == 600
        assert len(mapping.x) >= 2
        # monotonic non-decreasing
        assert all(a <= b for a, b in zip(mapping.x, mapping.x[1:]))
        assert all(a <= b for a, b in zip(mapping.y, mapping.y[1:]))

        # fit_calibration_mapping() deliberately doesn't auto-persist -- callers
        # must save explicitly before calibrate_probability() will pick it up.
        pc.save_calibration_mapping(mapping)

        calibrated_at_08 = pc.calibrate_probability(0.8)
        calibrated_at_05 = pc.calibrate_probability(0.5)
        # The heuristic's 0.8 realized only ~0.5 win rate -- calibration should
        # pull it down substantially, not leave it near 0.8.
        assert calibrated_at_08 < 0.65
        # 0.5 realized ~0.3 -- calibration should pull it down too.
        assert calibrated_at_05 < 0.5


class TestSaveAndLoadRoundTrip:
    def test_save_then_calibrate_uses_persisted_mapping(self):
        mapping = pc.CalibrationMapping(x=[0.0, 0.5, 1.0], y=[0.0, 0.3, 1.0], sample_size=500, fitted_at="2026-01-01T00:00:00")
        pc.save_calibration_mapping(mapping)

        assert pc.calibrate_probability(0.5) == pytest.approx(0.3)
        assert pc.calibrate_probability(0.0) == pytest.approx(0.0)
        assert pc.calibrate_probability(1.0) == pytest.approx(1.0)

    def test_load_ignores_corrupt_file(self):
        settings = pc.get_settings()
        path = pc._resolve_path(settings.probability_calibration_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json {{{")

        # Falls back to identity rather than raising.
        assert pc.calibrate_probability(0.42) == 0.42

    def test_result_stays_within_bounds_for_out_of_range_input(self):
        mapping = pc.CalibrationMapping(x=[0.2, 0.8], y=[0.1, 0.9], sample_size=500, fitted_at="2026-01-01T00:00:00")
        pc.save_calibration_mapping(mapping)

        assert 0.0 <= pc.calibrate_probability(-1.0) <= 1.0
        assert 0.0 <= pc.calibrate_probability(2.0) <= 1.0
