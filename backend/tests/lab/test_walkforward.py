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

    def test_causal_strategy_computes_signals_once_per_code(self):
        # causal_signals=True인 고정 규칙 전략은 종목당 signals()를 1회만 호출한다
        # (윈도우마다 재계산하던 것이 런타임의 주범이었음)
        class _CausalCounting(_FixedStrategy):
            causal_signals = True

            def __init__(self):
                super().__init__()
                self.signal_calls = 0

            def signals(self, code, bars, params):
                self.signal_calls += 1
                return super().signals(code, bars, params)

        bars = {"A": _monotone_bars("2020-01-01", 700), "B": _monotone_bars("2020-01-01", 700)}
        strategy = _CausalCounting()
        windows = walk_forward_windows(
            start=date(2020, 1, 1), end=date(2022, 6, 30),
            train_years=1, test_months=6, step_months=6,
        )
        result = run_walk_forward(
            strategy=strategy, bars_by_code=bars,
            universe_fn=lambda w: ["A", "B"], cost_model=NO_COST, windows=windows,
        )
        assert strategy.signal_calls == 2  # 종목 수만큼만
        assert result.summary.n > 0
        # 결과에 검증 구간 신호가 실려 온다 (CLI 벤치마크 재사용)
        assert result.signals
        assert all(any(w.test_start <= s.signal_date <= w.test_end for w in windows) for s in result.signals)

    def test_causal_strategy_no_overlapping_trades_per_code(self):
        # 전역 1종목 1포지션 — 윈도우 경계를 넘어도 보유 중 중복 진입 금지
        class _Causal(_FixedStrategy):
            causal_signals = True

        bars = {"A": _monotone_bars("2020-01-01", 700)}
        result = run_walk_forward(
            strategy=_Causal(), bars_by_code=bars,
            universe_fn=lambda w: ["A"], cost_model=NO_COST,
            windows=walk_forward_windows(
                start=date(2020, 1, 1), end=date(2022, 6, 30),
                train_years=1, test_months=6, step_months=6,
            ),
        )
        ordered = sorted(result.trades, key=lambda t: t.entry_date)
        for prev, nxt in zip(ordered, ordered[1:]):
            assert nxt.entry_date > prev.exit_date

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


class _PanelEcho:
    """panel_signals 훅 검증용 — 패널 전체를 보고 코드별 고정 신호 방출."""
    id = "panel_echo"
    label = "패널 에코"
    causal_signals = True

    def __init__(self):
        self.panel_calls = 0
        self.seen_codes: list[str] = []

    def fit(self, train_bars):
        return {}

    def signals(self, code, bars, params):
        raise AssertionError("panel 전략에서는 signals()가 호출되면 안 된다")

    def panel_signals(self, bars_by_code, params):
        self.panel_calls += 1
        self.seen_codes = sorted(bars_by_code)
        out = []
        for code, bars in sorted(bars_by_code.items()):
            months = set()
            for _, row in bars.iterrows():
                d = row["date"].date()
                key = (d.year, d.month)
                if key not in months:
                    months.add(key)
                    out.append(Signal(code=code, signal_date=d,
                                      stop_price=float(row["close"]) * 0.9,
                                      max_holding_days=5))
        return out


class TestPanelSignalsPath:
    def _windows(self):
        return walk_forward_windows(
            start=date(2020, 1, 1), end=date(2022, 6, 30),
            train_years=1, test_months=6, step_months=6,
        )

    def test_panel_hook_called_once_and_universe_filtered(self):
        # 코드 A만 유니버스에 있음 → 패널은 1회 호출, 트레이드/신호는 A만
        bars = {"A": _monotone_bars("2020-01-01", 700), "B": _monotone_bars("2020-01-01", 700)}
        strategy = _PanelEcho()
        windows = self._windows()
        result = run_walk_forward(
            strategy=strategy, bars_by_code=bars,
            universe_fn=lambda w: ["A"], cost_model=NO_COST, windows=windows,
        )
        assert strategy.panel_calls == 1
        assert strategy.seen_codes == ["A"]  # 유니버스 밖 종목은 패널에도 없다
        assert result.summary.n > 0
        assert all(t.code == "A" for t in result.trades)
        assert all(s.code == "A" for s in result.signals)
        # 신호는 반드시 검증 구간 안에서만 인정된다
        assert all(any(w.test_start <= s.signal_date <= w.test_end for w in windows) for s in result.signals)

    def test_panel_signals_outside_test_ranges_dropped(self):
        bars = {"A": _monotone_bars("2020-01-01", 700)}
        windows = self._windows()
        result = run_walk_forward(
            strategy=_PanelEcho(), bars_by_code=bars,
            universe_fn=lambda w: ["A"], cost_model=NO_COST, windows=windows,
        )
        for t in result.trades:
            assert any(w.test_start <= t.entry_date <= w.test_end for w in windows)
