from datetime import date

import pandas as pd

from app.lab.costs import CostModel
from app.lab.types import Signal
from app.lab.walkforward import Window, run_walk_forward, walk_forward_windows

from .conftest import make_bars

NO_COST = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)


class TestWindows:
    def test_rolling_windows(self):
        windows = walk_forward_windows(
            start=date(2020, 1, 1), end=date(2022, 12, 31),
            train_years=1, test_months=6, step_months=6,
        )
        assert windows[0] == Window(
            train_start=date(2020, 1, 1), train_end=date(2020, 12, 31),
            test_start=date(2021, 1, 1), test_end=date(2021, 6, 30),
        )
        assert windows[1].test_start == date(2021, 7, 1)
        # 검증 구간이 end를 넘는 윈도우는 만들지 않는다
        assert all(w.test_end <= date(2022, 12, 31) for w in windows)

    def test_no_window_when_period_too_short(self):
        assert walk_forward_windows(
            start=date(2022, 1, 1), end=date(2022, 6, 30),
            train_years=1, test_months=6, step_months=6,
        ) == []


class _FixedStrategy:
    """fit은 학습 구간 마지막 날짜를 기억하고, signals는 매월 첫 봉에 신호를 낸다."""
    id = "fixed"
    label = "테스트 고정 전략"

    def __init__(self):
        self.seen_train_end: list[pd.Timestamp] = []

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        last = max(df["date"].max() for df in train_bars.values())
        self.seen_train_end.append(last)
        return {"stop_pct": 0.05}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        out = []
        months = set()
        for _, row in bars.iterrows():
            d = row["date"].date()
            key = (d.year, d.month)
            if key not in months:
                months.add(key)
                out.append(Signal(code=code, signal_date=d,
                                  stop_price=float(row["close"]) * (1 - params["stop_pct"]),
                                  max_holding_days=5))
        return out


def _monotone_bars(start: str, periods: int) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    rows = [(str(d.date()), 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i, d in enumerate(dates)]
    return make_bars(rows)


class TestHarness:
    def test_trades_only_in_test_ranges_and_fit_sees_only_train(self):
        bars = {"A": _monotone_bars("2020-01-01", 700)}
        strategy = _FixedStrategy()
        windows = walk_forward_windows(
            start=date(2020, 1, 1), end=date(2022, 6, 30),
            train_years=1, test_months=6, step_months=6,
        )
        result = run_walk_forward(
            strategy=strategy,
            bars_by_code=bars,
            universe_fn=lambda window: ["A"],
            cost_model=NO_COST,
            windows=windows,
        )
        assert result.strategy_id == "fixed"
        assert result.summary.n > 0
        # 진입일은 반드시 어떤 검증 구간 안에 있다
        for t in result.trades:
            assert any(w.test_start <= t.entry_date <= w.test_end for w in windows)
        # 미래 데이터 누출 방지: fit이 본 마지막 날짜는 각 학습 구간 종료일 이하
        for seen, w in zip(strategy.seen_train_end, windows):
            assert seen.date() <= w.train_end

    def test_verdict_present(self):
        bars = {"A": _monotone_bars("2020-01-01", 700)}
        result = run_walk_forward(
            strategy=_FixedStrategy(), bars_by_code=bars,
            universe_fn=lambda window: ["A"], cost_model=NO_COST,
            windows=walk_forward_windows(
                start=date(2020, 1, 1), end=date(2022, 6, 30),
                train_years=1, test_months=6, step_months=6,
            ),
        )
        assert result.verdict in {"pass", "watch", "fail"}
