from datetime import date

import pandas as pd

from app.strategies.xs_momentum import XsMomentumStrategy


def make_bars(daily_ret: float, n: int = 300, start: str = "2023-01-02") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + daily_ret))
    return pd.DataFrame({
        "date": dates.date, "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": [1000] * n,
    })


class TestXsMomentum:
    def test_picks_strongest_when_all_positive(self):
        strategy = XsMomentumStrategy()
        panel = {
            "STRONG": make_bars(0.004), "MID": make_bars(0.002),
            "WEAK": make_bars(0.0005), "FLAT": make_bars(0.0),
        }
        signals = strategy.panel_signals(panel, {})
        codes = {s.code for s in signals}
        assert "STRONG" in codes           # 최강 종목은 반드시 선정
        assert "FLAT" not in codes         # 모멘텀 0 이하는 제외
        for s in signals:
            assert s.max_holding_days == 21
            assert s.stop_price > 0

    def test_negative_momentum_universe_yields_nothing(self):
        strategy = XsMomentumStrategy()
        panel = {"D1": make_bars(-0.002), "D2": make_bars(-0.003)}
        assert strategy.panel_signals(panel, {}) == []

    def test_short_history_ignored(self):
        strategy = XsMomentumStrategy()
        panel = {"NEW": make_bars(0.005, n=100), "OLD": make_bars(0.003)}
        codes = {s.code for s in strategy.panel_signals(panel, {})}
        assert "NEW" not in codes and "OLD" in codes

    def test_per_code_signals_empty(self):
        # 단독 종목으로는 상대 강도가 정의되지 않는다 — 패널 경로 전용
        strategy = XsMomentumStrategy()
        assert strategy.signals("A", make_bars(0.004), {}) == []

    def test_causality_truncated_panel_is_subset(self):
        strategy = XsMomentumStrategy()
        panel = {"A": make_bars(0.004), "B": make_bars(0.002), "C": make_bars(0.001)}
        full = {(s.code, s.signal_date) for s in strategy.panel_signals(panel, {})}
        cutoff = date(2024, 1, 31)
        truncated_panel = {
            c: df[pd.to_datetime(df["date"]).dt.date <= cutoff].reset_index(drop=True)
            for c, df in panel.items()
        }
        truncated = {(s.code, s.signal_date) for s in strategy.panel_signals(truncated_panel, {})}
        assert truncated == {x for x in full if x[1] <= cutoff}
