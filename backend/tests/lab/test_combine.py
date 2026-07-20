from datetime import date

from app.lab.combine import monthly_r_series, pairwise_correlation, trades_from_report_dicts
from app.lab.types import Trade


def _trade_dict(code: str, entry: str, exit_: str, net: float, stop: float = 90.0) -> dict:
    return {
        "code": code, "strategy_id": "s", "entry_date": entry, "entry_price": 100.0,
        "exit_date": exit_, "exit_price": 100.0 * (1 + net), "exit_reason": "time",
        "gross_return_pct": net, "net_return_pct": net, "stop_price": stop,
    }


def _trade(entry: date, exit_: date, net: float, stop: float = 90.0) -> Trade:
    return Trade(
        code="A", strategy_id="s", entry_date=entry, entry_price=100.0,
        exit_date=exit_, exit_price=100.0 * (1 + net), exit_reason="time",
        gross_return_pct=net, net_return_pct=net, stop_price=stop,
    )


class TestTradesFromReportDicts:
    def test_parses_dates_and_fields(self):
        trades = trades_from_report_dicts([_trade_dict("A", "2024-01-05", "2024-02-01", 0.05)])
        assert trades[0].entry_date == date(2024, 1, 5)
        assert trades[0].exit_date == date(2024, 2, 1)
        assert trades[0].net_return_pct == 0.05
        assert trades[0].stop_price == 90.0

    def test_skips_malformed_rows(self):
        rows = [_trade_dict("A", "2024-01-05", "2024-02-01", 0.05), {"broken": True}]
        assert len(trades_from_report_dicts(rows)) == 1


class TestMonthlyRSeries:
    def test_sums_r_by_exit_month(self):
        # stop 90 → 손절거리 10% → R = net/0.10
        trades = [
            _trade(date(2024, 1, 3), date(2024, 1, 20), 0.05),   # R=+0.5
            _trade(date(2024, 1, 10), date(2024, 1, 25), 0.03),  # R=+0.3
            _trade(date(2024, 2, 1), date(2024, 2, 15), -0.02),  # R=-0.2
        ]
        series = monthly_r_series(trades)
        assert abs(series["2024-01"] - 0.8) < 1e-9
        assert abs(series["2024-02"] - (-0.2)) < 1e-9

    def test_loss_cap_applied(self):
        # 갭 폭락: R=-8 → -3으로 상한 (risk_based_metrics와 동일 규칙)
        series = monthly_r_series([_trade(date(2024, 1, 3), date(2024, 1, 20), -0.80)])
        assert abs(series["2024-01"] - (-3.0)) < 1e-9

    def test_missing_stop_excluded(self):
        series = monthly_r_series([_trade(date(2024, 1, 3), date(2024, 1, 20), 0.05, stop=None)])
        assert series == {}


class TestPairwiseCorrelation:
    def test_identical_series_is_one(self):
        a = {"2024-01": 1.0, "2024-02": -0.5, "2024-03": 0.3}
        assert abs(pairwise_correlation(a, dict(a)) - 1.0) < 1e-9

    def test_opposite_series_is_minus_one(self):
        a = {"2024-01": 1.0, "2024-02": -0.5, "2024-03": 0.3}
        b = {k: -v for k, v in a.items()}
        assert abs(pairwise_correlation(a, b) - (-1.0)) < 1e-9

    def test_missing_months_treated_as_zero(self):
        # 겹치지 않는 달은 0으로 채워 정렬 — 한쪽만 거래한 달도 상관에 반영
        a = {"2024-01": 1.0}
        b = {"2024-02": 1.0}
        corr = pairwise_correlation(a, b)
        assert corr is not None and corr < 0  # 서로 반대 시점에만 수익 → 음의 상관

    def test_insufficient_months_returns_none(self):
        assert pairwise_correlation({"2024-01": 1.0}, {"2024-01": 0.5}) is None


class TestMonthlySharpe:
    def test_constant_positive_series_has_no_sharpe(self):
        # 표준편차 0 → 정의 불가 (None)
        from app.lab.combine import monthly_sharpe
        assert monthly_sharpe({"2024-01": 1.0, "2024-02": 1.0}) is None

    def test_known_series(self):
        from app.lab.combine import monthly_sharpe
        # 평균 0.5, 모표준편차 0.5 → 샤프 1.0
        assert abs(monthly_sharpe({"2024-01": 0.0, "2024-02": 1.0}) - 1.0) < 1e-9

    def test_insufficient_months(self):
        from app.lab.combine import monthly_sharpe
        assert monthly_sharpe({"2024-01": 1.0}) is None

    def test_combined_of_anticorrelated_beats_individuals(self):
        # 완전 역상관 두 시계열의 합은 변동성이 0에 가까워져 샤프가 발산 —
        # 분산 효과의 극단 사례가 수학적으로 재현되는지 확인
        from app.lab.combine import combine_series, monthly_sharpe
        a = {"2024-01": 1.0, "2024-02": 0.0, "2024-03": 1.0, "2024-04": 0.0}
        b = {"2024-01": 0.0, "2024-02": 1.0, "2024-03": 0.0, "2024-04": 1.0}
        combined = combine_series([a, b])
        assert combined == {"2024-01": 1.0, "2024-02": 1.0, "2024-03": 1.0, "2024-04": 1.0}
        assert monthly_sharpe(combined) is None  # 변동성 0 → 발산(None)이 정직한 표현
        assert monthly_sharpe(a) is not None
