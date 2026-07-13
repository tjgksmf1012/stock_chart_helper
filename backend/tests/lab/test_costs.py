from app.lab.costs import CostModel


class TestCostModel:
    def test_default_round_trip_is_conservative(self):
        # 기본값: 매수(수수료 0.015% + 슬리피지 0.1%) + 매도(수수료 + 거래세 0.15% + 슬리피지)
        cm = CostModel()
        assert 0.003 <= cm.round_trip_pct <= 0.005  # 왕복 0.3~0.5% 사이

    def test_net_return_flat_price_is_negative(self):
        # 같은 가격에 사고 팔면 비용만큼 손실
        cm = CostModel()
        net = cm.net_return_pct(entry_price=10_000, exit_price=10_000)
        assert net < 0
        assert abs(net + cm.round_trip_pct) < 0.0005  # 근사적으로 -왕복비용

    def test_net_return_math_is_multiplicative(self):
        # 체결가에 비용을 곱셈으로 반영: (매도가*(1-매도비용)) / (매수가*(1+매수비용)) - 1
        cm = CostModel(commission_pct=0.001, tax_pct=0.002, slippage_pct=0.0)
        net = cm.net_return_pct(entry_price=100.0, exit_price=110.0)
        expected = (110.0 * (1 - 0.003)) / (100.0 * (1 + 0.001)) - 1
        assert abs(net - expected) < 1e-12

    def test_zero_cost_model_returns_gross(self):
        cm = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)
        assert abs(cm.net_return_pct(100.0, 105.0) - 0.05) < 1e-12
