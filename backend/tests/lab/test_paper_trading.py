from datetime import date

from app.lab.costs import CostModel
from app.services.lab_paper_trading import (
    dedupe_key,
    drift_status,
    evaluate_paper_trade,
    new_paper_trade_signals,
    realized_summary_by_strategy,
)

from .conftest import make_bars

NO_COST = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)


def _sig(strategy: str, code: str, day: str) -> dict:
    return {
        "strategy_id": strategy, "code": code, "signal_date": day,
        "stop_price": 90.0, "target_price": None, "max_holding_days": 40,
    }


class TestDedupe:
    def test_filters_already_recorded(self):
        signals = [_sig("s1", "A", "2026-07-09"), _sig("s1", "B", "2026-07-09")]
        existing = {dedupe_key("s1", "A", "2026-07-09")}
        out = new_paper_trade_signals(signals, existing)
        assert [s["code"] for s in out] == ["B"]

    def test_dedupes_within_batch(self):
        signals = [_sig("s1", "A", "2026-07-09"), _sig("s1", "A", "2026-07-09")]
        out = new_paper_trade_signals(signals, set())
        assert len(out) == 1

    def test_all_new(self):
        signals = [_sig("s1", "A", "2026-07-09"), _sig("s2", "A", "2026-07-09")]
        assert len(new_paper_trade_signals(signals, set())) == 2


class TestRealizedSummary:
    def _closed(self, strategy: str, net: float) -> dict:
        return {"strategy_id": strategy, "status": "closed", "net_return_pct": net}

    def test_groups_by_strategy_and_computes_ev(self):
        trades = [
            self._closed("s1", 0.10), self._closed("s1", -0.04),
            self._closed("s2", 0.02),
        ]
        summary = realized_summary_by_strategy(trades)
        assert summary["s1"]["n"] == 2
        assert abs(summary["s1"]["ev_pct"] - 0.03) < 1e-12
        assert abs(summary["s1"]["win_rate"] - 0.5) < 1e-12
        assert summary["s2"]["n"] == 1

    def test_ignores_open_trades(self):
        trades = [
            {"strategy_id": "s1", "status": "open", "net_return_pct": None},
            self._closed("s1", 0.05),
        ]
        summary = realized_summary_by_strategy(trades)
        assert summary["s1"]["n"] == 1

    def test_empty(self):
        assert realized_summary_by_strategy([]) == {}


class TestEvaluatePaperTrade:
    def _open(self, stop=95.0, target=110.0, holding=40) -> dict:
        return {
            "code": "A", "signal_date": "2025-01-02",
            "stop_price": stop, "target_price": target, "max_holding_days": holding,
        }

    def test_closes_when_target_reached(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 101, 112, 100, 111),  # 진입 101, 목표 110 도달
        ])
        result = evaluate_paper_trade(self._open(), bars, NO_COST)
        assert result is not None
        assert result["exit_reason"] == "target"
        assert result["entry_price"] == 101.0
        assert result["net_return_pct"] > 0

    def test_stays_open_when_not_enough_bars(self):
        # 진입 후 아직 보유기간 안 끝났고 목표/손절 미도달 → data_end → 열어둠
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 101, 99, 100),
        ])
        assert evaluate_paper_trade(self._open(holding=40), bars, NO_COST) is None

    def test_no_entry_bar_stays_open(self):
        # 신호일이 마지막 봉이면 진입 불가 → 아직 열어둠
        bars = make_bars([("2025-01-02", 100, 101, 99, 100)])
        assert evaluate_paper_trade(self._open(), bars, NO_COST) is None

    def test_time_exit_closes(self):
        bars = make_bars([(f"2025-01-{d:02d}", 100, 101, 99, 100) for d in range(2, 12)])
        result = evaluate_paper_trade(self._open(stop=80.0, target=None, holding=3), bars, NO_COST)
        assert result is not None
        assert result["exit_reason"] == "time"


class TestDriftStatus:
    def test_insufficient_below_min_samples(self):
        assert drift_status(realized_ev=0.05, realized_n=5, backtest_ci_low=0.01) == "insufficient"

    def test_ok_when_realized_above_backtest_floor(self):
        assert drift_status(realized_ev=0.03, realized_n=30, backtest_ci_low=0.01) == "ok"

    def test_drifting_when_realized_below_floor(self):
        assert drift_status(realized_ev=-0.005, realized_n=30, backtest_ci_low=0.01) == "drifting"

    def test_unknown_without_backtest_ci(self):
        assert drift_status(realized_ev=0.03, realized_n=30, backtest_ci_low=None) == "unknown"

    def test_none_ev_is_insufficient(self):
        assert drift_status(realized_ev=None, realized_n=30, backtest_ci_low=0.01) == "insufficient"
