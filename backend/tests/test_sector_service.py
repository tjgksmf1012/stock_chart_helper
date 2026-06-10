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


def test_unmapped_code_falls_into_etc_and_no_pattern_is_skipped():
    rows = [
        {"code": "Z", "pattern_type": "double_bottom", "name": "ZZ"},  # unmapped -> 기타
        {"code": "Y", "pattern_type": "", "name": "YY"},  # no pattern -> skipped
    ]
    result = build_sector_heatmap(rows, {})

    assert len(result) == 1
    assert result[0]["sector_name"] == "기타"
    assert result[0]["bullish_count"] == 1
    assert result[0]["bearish_count"] == 0
