from __future__ import annotations

from app.services.money_flow_service import _compute_alignment


class TestComputeAlignment:
    """Pattern-vs-money-flow alignment classification (pure, threshold 50억)."""

    def test_no_pattern_is_neutral(self):
        alignment, _, _ = _compute_alignment(100.0, 100.0, None)
        assert alignment == "neutral"

    def test_weak_flow_below_threshold_is_neutral(self):
        alignment, _, _ = _compute_alignment(10.0, 10.0, "double_bottom")
        assert alignment == "neutral"

    def test_bullish_pattern_with_bullish_flow_is_aligned(self):
        alignment, _, _ = _compute_alignment(100.0, 100.0, "double_bottom")
        assert alignment == "aligned"

    def test_bullish_pattern_with_bearish_flow_is_diverged(self):
        alignment, _, _ = _compute_alignment(-100.0, -100.0, "double_bottom")
        assert alignment == "diverged"

    def test_bearish_pattern_with_bearish_flow_is_aligned(self):
        alignment, _, _ = _compute_alignment(-100.0, -100.0, "double_top")
        assert alignment == "aligned"

    def test_opposing_foreign_and_institution_is_mixed(self):
        # foreign strongly buys, institution strongly sells; combined still >= threshold
        alignment, _, _ = _compute_alignment(200.0, -100.0, "double_bottom")
        assert alignment == "mixed"
