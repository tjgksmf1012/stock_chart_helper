from datetime import date

import pytest

from app.lab.sizing import position_size, risk_based_metrics
from app.lab.types import Trade


class TestPositionSize:
    def test_basic_fixed_fractional(self):
        # 계좌 1,000만원, 리스크 1% = 10만원. 진입 10,000 / 손절 9,500 → 주당 리스크 500원
        # → 200주, 포지션 200만원
        r = position_size(account_value=10_000_000, risk_pct=0.01, entry_price=10_000, stop_price=9_500)
        assert r["shares"] == 200
        assert r["position_value"] == 2_000_000
        assert r["risk_amount"] == 100_000

    def test_concentration_cap_limits_position(self):
        # 손절이 너무 타이트하면(0.5%) 포지션이 계좌를 초과하려 함 → 상한(기본 20%)으로 제한
        r = position_size(account_value=10_000_000, risk_pct=0.01, entry_price=10_000, stop_price=9_950)
        assert r["position_value"] <= 10_000_000 * 0.2
        assert r["capped_by_concentration"] is True

    def test_no_cap_flag_when_under_limit(self):
        r = position_size(account_value=10_000_000, risk_pct=0.01, entry_price=10_000, stop_price=9_000)
        assert r["capped_by_concentration"] is False

    def test_invalid_stop_above_entry_returns_zero(self):
        # 롱인데 손절이 진입가 이상 → 사이징 불가
        r = position_size(account_value=10_000_000, risk_pct=0.01, entry_price=10_000, stop_price=10_500)
        assert r["shares"] == 0

    def test_shares_floor_to_int(self):
        # 10만원 리스크 / 주당 3,330원 = 30.03주 → 30주 (집중 상한 미달 구간)
        r = position_size(account_value=10_000_000, risk_pct=0.01, entry_price=10_000, stop_price=6_670)
        assert r["shares"] == 30
        assert r["capped_by_concentration"] is False


def _trade(net: float, entry: float = 100.0, stop: float = 95.0, day: int = 1) -> Trade:
    return Trade(
        code="A", strategy_id="t",
        entry_date=date(2025, 1, day), entry_price=entry,
        exit_date=date(2025, 1, day + 1), exit_price=entry * (1 + net),
        exit_reason="time", gross_return_pct=net, net_return_pct=net,
        stop_price=stop,
    )


class TestRiskBasedMetrics:
    def test_stop_out_loses_exactly_risk_pct(self):
        # 손절 거리 5%에서 -5% 청산 = 정확히 -1R → 자본 -1% (리스크 1% 기준)
        trades = [_trade(net=-0.05, entry=100.0, stop=95.0)]
        m = risk_based_metrics(trades, risk_pct=0.01)
        assert abs(m["total_return_pct"] - (-0.01)) < 1e-9
        assert abs(m["mdd_pct"] - 0.01) < 1e-9

    def test_r_multiple_scales_gain(self):
        # 손절 거리 5%에서 +10% 청산 = +2R → 자본 +2% (리스크 1%)
        trades = [_trade(net=0.10, entry=100.0, stop=95.0)]
        m = risk_based_metrics(trades, risk_pct=0.01)
        assert abs(m["total_return_pct"] - 0.02) < 1e-9

    def test_compounding_sequence_mdd(self):
        # +2R, -1R, -1R (리스크 1%): 고점 1.02 → 저점 1.02*0.99*0.99
        trades = [
            _trade(net=0.10, day=1), _trade(net=-0.05, day=3), _trade(net=-0.05, day=5),
        ]
        m = risk_based_metrics(trades, risk_pct=0.01)
        expected_equity = 1.02 * 0.99 * 0.99
        assert abs(m["total_return_pct"] - (expected_equity - 1)) < 1e-9
        assert abs(m["mdd_pct"] - (1 - expected_equity / 1.02)) < 1e-9

    def test_missing_stop_trades_are_skipped(self):
        trades = [_trade(net=0.10), _trade(net=0.10)]
        no_stop = Trade(
            code="B", strategy_id="t", entry_date=date(2025, 1, 1), entry_price=100.0,
            exit_date=date(2025, 1, 2), exit_price=110.0, exit_reason="time",
            gross_return_pct=0.10, net_return_pct=0.10, stop_price=None,
        )
        m = risk_based_metrics(trades + [no_stop], risk_pct=0.01)
        assert m["n_used"] == 2

    def test_empty(self):
        m = risk_based_metrics([], risk_pct=0.01)
        assert m["n_used"] == 0 and m["mdd_pct"] == 0.0

    def test_r_multiple_capped_against_gap_blowups(self):
        # 갭으로 손절보다 훨씬 아래 체결(-20%, 손절거리 1%) = -20R이지만
        # 리스크 1%면 자본 -20%로 폭주 → 트레이드당 손실 상한이 걸려야 한다
        trades = [_trade(net=-0.20, entry=100.0, stop=99.0)]
        m = risk_based_metrics(trades, risk_pct=0.01, max_loss_r=3.0)
        assert m["total_return_pct"] >= -0.03 - 1e-9  # -3R 이하로 안 내려감
