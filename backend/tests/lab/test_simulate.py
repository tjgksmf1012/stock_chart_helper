from datetime import date

from app.lab.costs import CostModel
from app.lab.simulate import simulate_trades
from app.lab.types import Signal

from .conftest import make_bars

NO_COST = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)


class TestEntryRule:
    def test_entry_is_next_bar_open(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),   # 신호 봉
            ("2025-01-03", 102, 103, 101, 102),  # 진입 봉 (시가 102)
            ("2025-01-06", 102, 120, 101, 118),  # 목표 도달
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert len(trades) == 1
        assert trades[0].entry_price == 102.0
        assert trades[0].entry_date == date(2025, 1, 3)

    def test_signal_on_last_bar_is_skipped(self):
        bars = make_bars([("2025-01-02", 100, 101, 99, 100)])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0)
        assert simulate_trades(bars, [sig], NO_COST, strategy_id="t") == []


class TestExitRules:
    def test_stop_checked_before_target_same_bar(self):
        # 한 봉에서 손절/목표 둘 다 스치면 보수적으로 손절 우선 (기존 백테스트 관행)
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 115, 94, 96),  # low가 stop(95) 아래, high가 target(110) 위
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "stop"
        assert trades[0].exit_price == 95.0

    def test_gap_down_open_below_stop_exits_at_open(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 90, 92, 88, 91),  # 시가부터 stop(95) 아래 갭
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "stop"
        assert trades[0].exit_price == 90.0  # stop가 아니라 실제 체결 가능한 시가

    def test_target_hit_exits_at_target(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 101, 112, 100, 111),
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "target"
        assert trades[0].exit_price == 110.0
        assert abs(trades[0].gross_return_pct - (110.0 / 101.0 - 1)) < 1e-6

    def test_time_exit_at_close_after_max_holding(self, flat_bars):
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=90.0, max_holding_days=3)
        trades = simulate_trades(flat_bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "time"
        # 진입 봉(01-03) 포함 3거래일 보유 → 01-07 종가 청산
        assert trades[0].exit_date == date(2025, 1, 7)

    def test_data_end_exit_at_last_close(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 101, 99, 100),
            ("2025-01-06", 100, 101, 99, 101),
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=90.0, max_holding_days=40)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "data_end"
        assert trades[0].exit_price == 101.0


class TestOverlap:
    def test_second_signal_during_open_position_is_skipped(self, flat_bars):
        s1 = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=90.0, max_holding_days=5)
        s2 = Signal(code="A", signal_date=date(2025, 1, 3), stop_price=90.0, max_holding_days=5)
        trades = simulate_trades(flat_bars, [s1, s2], NO_COST, strategy_id="t")
        assert len(trades) == 1  # 1종목 1포지션


class TestBadDataGuards:
    def test_zero_open_entry_bar_skips_signal(self):
        # 거래정지 등으로 시가 0인 봉 — 진입 불가로 신호 폐기 (실데이터 발견 케이스)
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 0, 0, 0, 0),
            ("2025-01-06", 100, 101, 99, 100),
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0)
        assert simulate_trades(bars, [sig], NO_COST, strategy_id="t") == []

    def test_zero_price_bar_during_holding_is_ignored(self):
        # 보유 중간의 0가격 봉은 손절/목표 판정에서 건너뛴다 (가짜 손절 방지)
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 101, 99, 100),
            ("2025-01-06", 0, 0, 0, 0),
            ("2025-01-07", 101, 112, 100, 111),
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert len(trades) == 1
        assert trades[0].exit_reason == "target"


class TestCostsApplied:
    def test_net_return_uses_cost_model(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 112, 100, 111),
        ])
        cm = CostModel(commission_pct=0.001, tax_pct=0.002, slippage_pct=0.0)
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], cm, strategy_id="t")
        assert abs(trades[0].net_return_pct - cm.net_return_pct(100.0, 110.0)) < 1e-6
        assert trades[0].net_return_pct < trades[0].gross_return_pct
