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


class TestKisDailyRows:
    """KIS 투자자 동향 → 일별 억원 변환 및 미정산 당일 행 제외."""

    @staticmethod
    def _fake_kis(trends):
        class FakeKis:
            configured = True

            async def fetch_investor_trends(self, code):
                return trends

        return FakeKis()

    import pytest as _pytest

    @_pytest.mark.anyio
    async def test_today_unsettled_row_excluded(self, monkeypatch):
        from datetime import date as _date

        from app.services import money_flow_service as mfs

        today = _date.today().strftime("%Y-%m-%d")
        trends = [
            {"date": "2026-06-09", "foreign_value_million": 5440.0, "institution_value_million": 710.0, "person_value_million": 0.0},
            {"date": "2026-06-10", "foreign_value_million": 6710.0, "institution_value_million": -3150.0, "person_value_million": 0.0},
            {"date": today, "foreign_value_million": 0.0, "institution_value_million": 0.0, "person_value_million": 0.0},
        ]
        monkeypatch.setattr("app.services.kis_client.get_kis_client", lambda: self._fake_kis(trends))

        rows = await mfs._fetch_daily_rows_kis("024110")
        assert [row["date"] for row in rows] == ["2026-06-09", "2026-06-10"]
        # 백만원 → 억원 변환 검증
        assert rows[-1]["foreign"] == 67.1
        assert rows[-1]["institution"] == -31.5

    @_pytest.mark.anyio
    async def test_settled_today_row_kept(self, monkeypatch):
        from datetime import date as _date

        from app.services import money_flow_service as mfs

        today = _date.today().strftime("%Y-%m-%d")
        trends = [
            {"date": "2026-06-10", "foreign_value_million": 1000.0, "institution_value_million": 500.0, "person_value_million": 0.0},
            {"date": today, "foreign_value_million": 2000.0, "institution_value_million": -800.0, "person_value_million": 0.0},
        ]
        monkeypatch.setattr("app.services.kis_client.get_kis_client", lambda: self._fake_kis(trends))

        rows = await mfs._fetch_daily_rows_kis("024110")
        assert len(rows) == 2
        assert rows[-1]["foreign"] == 20.0
