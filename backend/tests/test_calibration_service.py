from __future__ import annotations

from app.services.calibration_service import (
    build_calibration_report,
    outcome_to_pair,
)


class TestOutcomeToPair:
    def test_bullish_win_maps_to_p_up_and_true(self):
        pair = outcome_to_pair(
            {"outcome": "win", "p_up_at_signal": 0.66, "entry_price": 100, "target_price": 110}
        )
        assert pair == (0.66, True)

    def test_bullish_loss_maps_to_p_up_and_false(self):
        pair = outcome_to_pair(
            {"outcome": "loss", "p_up_at_signal": 0.55, "entry_price": 100, "target_price": 108}
        )
        assert pair == (0.55, False)

    def test_bearish_signal_inverts_probability_to_taken_direction(self):
        # target below entry => short setup => predicted win prob is p_down = 1 - p_up
        pair = outcome_to_pair(
            {"outcome": "stopped_out", "p_up_at_signal": 0.40, "entry_price": 100, "target_price": 90}
        )
        assert pair is not None
        predicted, won = pair
        assert round(predicted, 4) == 0.60
        assert won is False

    def test_pending_is_excluded(self):
        assert outcome_to_pair({"outcome": "pending", "p_up_at_signal": 0.7}) is None

    def test_cancelled_is_excluded(self):
        assert outcome_to_pair({"outcome": "cancelled", "p_up_at_signal": 0.7}) is None

    def test_missing_probability_is_excluded(self):
        assert outcome_to_pair({"outcome": "win", "p_up_at_signal": None}) is None


class TestBuildCalibrationReport:
    def test_empty_returns_insufficient_sample(self):
        report = build_calibration_report([])
        assert report.sample_size == 0
        assert report.bins == []
        assert "표본 부족" in report.reliability

    def test_perfectly_calibrated_is_flagged_well_calibrated(self):
        # 100 signals all predicted 0.6, exactly 60 win => observed == predicted
        pairs = [(0.6, True)] * 60 + [(0.6, False)] * 40
        report = build_calibration_report(pairs)
        assert report.sample_size == 100
        assert report.resolved_wins == 60
        assert report.base_rate == 0.6
        assert report.mean_predicted == 0.6
        assert report.ece == 0.0
        assert report.mean_gap == 0.0
        assert report.reliability.startswith("양호")
        # single populated bin [0.6, 0.7)
        assert len(report.bins) == 1
        assert report.bins[0].observed == 0.6
        assert report.bins[0].predicted == 0.6

    def test_brier_score_matches_known_value(self):
        # pred 0.6 with 60% win rate: 0.6*(0.6-1)^2 + 0.4*(0.6-0)^2 = 0.24
        pairs = [(0.6, True)] * 60 + [(0.6, False)] * 40
        report = build_calibration_report(pairs)
        assert report.brier_score == 0.24

    def test_overconfident_predictions_are_flagged(self):
        # predicts 0.8 but only half actually win
        pairs = [(0.8, True)] * 50 + [(0.8, False)] * 50
        report = build_calibration_report(pairs)
        assert report.ece == 0.3
        assert report.mean_gap == -0.3  # observed - predicted < 0 => overconfident
        assert "과신" in report.reliability

    def test_underconfident_predictions_are_flagged(self):
        # predicts 0.55 but 90% actually win
        pairs = [(0.55, True)] * 90 + [(0.55, False)] * 10
        report = build_calibration_report(pairs)
        assert report.mean_gap > 0.05
        assert "과소" in report.reliability

    def test_probability_one_lands_in_last_bin(self):
        pairs = [(1.0, True), (0.0, False)]
        report = build_calibration_report(pairs, min_samples=1)
        assert report.brier_score == 0.0
        uppers = {b.upper for b in report.bins}
        assert 1.0 in uppers


class TestPerBinSampleGating:
    """Regression: the reliability verdict used to only check the *total* sample size
    (n >= 20) before declaring the calibration "well calibrated", even though that total
    is spread across 10 bins -- a bin with 1-2 trades could swing its observed win rate
    to 0% or 100% and still count fully toward "well calibrated". Bins below
    MIN_BIN_SAMPLES should be excluded from the ECE/verdict and flagged.
    """

    def test_thin_bin_is_flagged_low_confidence(self):
        # 20 total, but split thinly: one bin with 18, one bin with just 2.
        pairs = [(0.6, True)] * 11 + [(0.6, False)] * 7 + [(0.95, True)] * 2
        report = build_calibration_report(pairs)
        thin_bins = [b for b in report.bins if b.low_confidence]
        assert thin_bins, "expected at least one thin bin"
        assert all(b.count < 5 for b in thin_bins)

    def test_all_bins_thin_reports_insufficient_per_bin_sample_even_if_total_is_enough(self):
        # 20 total pairs, but spread one-per-bin across bin boundaries -- total clears
        # MIN_CALIBRATION_SAMPLES but no single bin has enough for a trustworthy verdict.
        pairs = [(i / 20 + 0.025, i % 2 == 0) for i in range(20)]
        report = build_calibration_report(pairs)
        assert report.sample_size >= 20
        assert "구간별 표본 부족" in report.reliability

    def test_well_populated_single_bin_is_unaffected(self):
        # Sanity: existing well-calibrated case (one bin, 100 samples) must still pass.
        pairs = [(0.6, True)] * 60 + [(0.6, False)] * 40
        report = build_calibration_report(pairs)
        assert report.reliability.startswith("양호")
        assert not any(b.low_confidence for b in report.bins)
