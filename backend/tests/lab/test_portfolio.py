from datetime import date

from app.lab.portfolio import portfolio_equity_metrics
from app.lab.types import Trade

from .conftest import make_bars


def _trade(code: str, entry: str, entry_px: float, exit_: str, exit_px: float, net: float) -> Trade:
    return Trade(
        code=code, strategy_id="t",
        entry_date=date.fromisoformat(entry), entry_price=entry_px,
        exit_date=date.fromisoformat(exit_), exit_price=exit_px,
        exit_reason="time", gross_return_pct=net, net_return_pct=net,
    )


class TestPortfolioEquity:
    def test_single_trade_mdd_is_slot_weighted(self):
        # 슬롯 10개 중 1개만 사용 → -30% 트레이드라도 포트폴리오 MDD는 ~3%
        # (순차 복리 가정으로 MDD가 100%까지 과장되던 문제의 해결책)
        bars = {"A": make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 101, 99, 90),
            ("2025-01-06", 90, 91, 69, 70),
        ])}
        trades = [_trade("A", "2025-01-03", 100.0, "2025-01-06", 70.0, -0.30)]
        m = portfolio_equity_metrics(trades, bars, slots=10)
        assert 0.02 <= m["portfolio_mdd_pct"] <= 0.05
        assert m["portfolio_total_return_pct"] < 0

    def test_no_trades(self):
        m = portfolio_equity_metrics([], {}, slots=10)
        assert m["portfolio_mdd_pct"] == 0.0
        assert m["portfolio_total_return_pct"] == 0.0

    def test_two_concurrent_trades_each_use_own_slot(self):
        bars = {
            "A": make_bars([
                ("2025-01-02", 100, 101, 99, 100),
                ("2025-01-03", 100, 101, 99, 110),
            ]),
            "B": make_bars([
                ("2025-01-02", 200, 201, 199, 200),
                ("2025-01-03", 200, 201, 199, 220),
            ]),
        }
        trades = [
            _trade("A", "2025-01-03", 100.0, "2025-01-03", 110.0, 0.10),
            _trade("B", "2025-01-03", 200.0, "2025-01-03", 220.0, 0.10),
        ]
        m = portfolio_equity_metrics(trades, bars, slots=10)
        # 두 슬롯이 각각 +10% → 포트폴리오 +2% 근처
        assert 0.015 <= m["portfolio_total_return_pct"] <= 0.025
