from __future__ import annotations

from app.services.sector_service import build_sector_heatmap


def test_build_sector_heatmap_aggregates_and_sorts():
    rows = [
        {"code": "A", "pattern_type": "double_bottom", "name": "AA"},
        {"code": "B", "pattern_type": "double_bottom", "name": "BB"},
        {"code": "C", "pattern_type": "double_top", "name": "CC"},
        {"code": "D", "pattern_type": "ascending_triangle", "name": "DD"},
        {"code": "E", "pattern_type": "", "name": "EE"},  # no pattern -> skipped
    ]
    code_to_sector = {"A": "반도체", "B": "반도체", "C": "반도체", "D": "바이오"}

    result = build_sector_heatmap(rows, code_to_sector)
    by_name = {s["sector_name"]: s for s in result}

    assert set(by_name) == {"반도체", "바이오"}

    semi = by_name["반도체"]
    assert semi["bullish_count"] == 2
    assert semi["bearish_count"] == 1
    assert semi["net_score"] == 1
    assert semi["top_symbols"] == ["AA", "BB"]  # bearish names are not listed

    bio = by_name["바이오"]
    assert bio["bullish_count"] == 1
    assert bio["net_score"] == 1


def test_unmapped_code_is_skipped_not_pooled_into_a_fake_sector():
    # Regression: unmapped codes (e.g. cold sector-map cache) used to be pooled into a
    # fake "기타" bucket that could dominate the heatmap (sorted by |net_score|) and
    # look indistinguishable from a real sector rotation signal. They should just be
    # excluded from sector aggregation instead.
    rows = [
        {"code": "Z", "pattern_type": "double_bottom", "name": "ZZ"},  # unmapped
        {"code": "Y", "pattern_type": "", "name": "YY"},  # no pattern -> skipped
    ]
    result = build_sector_heatmap(rows, {})

    assert result == []


def test_direction_neutral_pattern_uses_instance_direction():
    # Regression: rectangle/symmetric_triangle/channels are direction-neutral TYPES --
    # a static BULLISH_PATTERNS/BEARISH_PATTERNS membership check silently dropped them
    # from both counts regardless of which way the specific instance actually broke.
    rows = [
        # bullish rectangle instance: target above trigger_level (neckline)
        {"code": "A", "pattern_type": "rectangle", "name": "AA", "trigger_level": 100.0, "target_level": 110.0},
        # bearish rectangle instance: target below trigger_level
        {"code": "B", "pattern_type": "rectangle", "name": "BB", "trigger_level": 100.0, "target_level": 90.0},
    ]
    code_to_sector = {"A": "반도체", "B": "반도체"}

    result = build_sector_heatmap(rows, code_to_sector)
    semi = result[0]
    assert semi["bullish_count"] == 1
    assert semi["bearish_count"] == 1
