import pandas as pd

from app.lab.universe import select_top_by_market_cap


class TestSelectTop:
    def test_orders_by_cap_and_limits(self):
        caps = pd.Series({"A": 300.0, "B": 100.0, "C": 200.0})
        assert select_top_by_market_cap(caps, top_n=2) == ["A", "C"]

    def test_drops_nan_and_nonpositive(self):
        caps = pd.Series({"A": 100.0, "B": float("nan"), "C": 0.0, "D": -5.0})
        assert select_top_by_market_cap(caps, top_n=10) == ["A"]

    def test_empty(self):
        assert select_top_by_market_cap(pd.Series(dtype=float), top_n=5) == []
