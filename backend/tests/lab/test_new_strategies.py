"""Phase 2 전략 3종 — 트리거/비트리거/인과성 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategies.high52_breakout import High52BreakoutStrategy
from app.strategies.trend_tsmom import TrendTsmomStrategy
from app.strategies.vol_breakout import VolBreakoutStrategy

from .conftest import make_bars


def assert_causal(strategy, bars: pd.DataFrame, cut_at: int) -> None:
    """앞부분만 잘라 넣어도 그 구간의 신호는 전체를 넣었을 때와 같아야 한다."""
    cut = bars.iloc[:cut_at].reset_index(drop=True)
    cutoff = pd.Timestamp(cut["date"].max()).date()
    sig_cut = {(s.signal_date, round(s.stop_price, 4)) for s in strategy.signals("A", cut, {})}
    sig_full = {
        (s.signal_date, round(s.stop_price, 4))
        for s in strategy.signals("A", bars, {})
        if s.signal_date <= cutoff
    }
    assert sig_cut == sig_full


def _rising_bars(periods: int = 320, start: str = "2023-01-02") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    rows = []
    for i, d in enumerate(dates):
        c = 100.0 + 0.2 * i
        rows.append((str(d.date()), c - 0.3, c + 0.5, c - 0.6, c))
    return make_bars(rows)


def _falling_bars(periods: int = 320, start: str = "2023-01-02") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    rows = []
    for i, d in enumerate(dates):
        c = 200.0 - 0.2 * i
        rows.append((str(d.date()), c + 0.3, c + 0.6, c - 0.5, c))
    return make_bars(rows)


class TestVolBreakout:
    def test_triggers_when_close_exceeds_open_plus_k_range(self):
        bars = make_bars([
            ("2025-01-02", 100, 105, 95, 100),   # 전일 레인지 10
            ("2025-01-03", 100, 107, 99, 106),   # 106 > 100 + 0.5*10 → 신호
        ])
        signals = VolBreakoutStrategy().signals("A", bars, {})
        assert len(signals) == 1
        assert signals[0].signal_date.isoformat() == "2025-01-03"
        assert signals[0].stop_price < 106

    def test_no_trigger_when_move_too_small(self):
        bars = make_bars([
            ("2025-01-02", 100, 105, 95, 100),
            ("2025-01-03", 100, 104.5, 99, 104),  # 104 < 105 → 무신호
        ])
        assert VolBreakoutStrategy().signals("A", bars, {}) == []

    def test_causal(self):
        rng = np.random.default_rng(11)
        dates = pd.bdate_range("2024-01-02", periods=120)
        close = 100 * np.cumprod(1 + rng.normal(0, 0.02, 120))
        rows = [
            (str(d.date()), float(c * 0.99), float(c * 1.02), float(c * 0.97), float(c))
            for d, c in zip(dates, close)
        ]
        assert_causal(VolBreakoutStrategy(), make_bars(rows), cut_at=80)


class TestHigh52Breakout:
    def test_triggers_on_20d_close_breakout_near_52w_high(self):
        rows = [(f"day{i}", 100.0, 101.0, 99.0, 100.0) for i in range(260)]
        dates = pd.bdate_range("2023-01-02", periods=260)
        rows = [(str(d.date()), 100.0, 101.0, 99.0, 100.0) for d in dates[:-1]]
        rows.append((str(dates[-1].date()), 100.0, 102.5, 99.5, 102.0))  # 신고가권 + 20일 종가 돌파
        signals = High52BreakoutStrategy().signals("A", make_bars(rows), {})
        assert len(signals) == 1
        assert signals[0].signal_date == dates[-1].date()

    def test_no_trigger_when_flat(self):
        dates = pd.bdate_range("2023-01-02", periods=260)
        rows = [(str(d.date()), 100.0, 101.0, 99.0, 100.0) for d in dates]
        assert High52BreakoutStrategy().signals("A", make_bars(rows), {}) == []

    def test_requires_252_bars(self):
        dates = pd.bdate_range("2024-01-02", periods=100)
        rows = [(str(d.date()), 100.0, 101.0, 99.0, 100.0 + i * 0.5) for i, d in enumerate(dates)]
        assert High52BreakoutStrategy().signals("A", make_bars(rows), {}) == []

    def test_causal(self):
        assert_causal(High52BreakoutStrategy(), _rising_bars(320), cut_at=290)


class TestTrendTsmom:
    def test_triggers_on_month_start_in_uptrend(self):
        signals = TrendTsmomStrategy().signals("A", _rising_bars(320), {})
        assert signals, "상승 추세에서는 월초 신호가 있어야 한다"
        months = {(s.signal_date.year, s.signal_date.month) for s in signals}
        assert len(months) == len(signals)  # 월 1회

    def test_no_trigger_in_downtrend(self):
        assert TrendTsmomStrategy().signals("A", _falling_bars(320), {}) == []

    def test_causal(self):
        assert_causal(TrendTsmomStrategy(), _rising_bars(320), cut_at=290)
