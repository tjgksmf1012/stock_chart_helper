"""워크포워드 하네스 — 파라미터는 학습 구간에서만, 검증 구간은 한 번만.

인샘플(학습 구간) 성적은 계산하지 않는다. 검증 구간 트레이드만 모아
summarize/bootstrap/verdict로 판정한다 (스펙 §2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Mapping, Protocol

import pandas as pd

from .costs import CostModel
from .metrics import Summary, bootstrap_ci, decide_verdict, summarize
from .simulate import simulate_trades
from .types import Signal, Trade


class Strategy(Protocol):
    id: str
    label: str

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict: ...
    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]: ...


@dataclass(frozen=True)
class Window:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass
class LabRunResult:
    strategy_id: str
    strategy_label: str
    trades: list[Trade]
    summary: Summary
    ci: tuple[float, float]
    random_ev_pct: float | None
    verdict: str
    windows: list[Window] = field(default_factory=list)
    data_coverage: float = 1.0  # 유니버스 중 시세 확보 종목 비율 (CLI에서 채움)


def walk_forward_windows(
    start: date, end: date, train_years: int = 2, test_months: int = 6, step_months: int = 6
) -> list[Window]:
    windows: list[Window] = []
    cursor = pd.Timestamp(start)
    while True:
        train_end = cursor + pd.DateOffset(years=train_years) - pd.Timedelta(days=1)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1)
        if test_end.date() > end:
            break
        windows.append(
            Window(
                train_start=cursor.date(), train_end=train_end.date(),
                test_start=test_start.date(), test_end=test_end.date(),
            )
        )
        cursor = cursor + pd.DateOffset(months=step_months)
    return windows


def run_walk_forward(
    strategy: Strategy,
    bars_by_code: Mapping[str, pd.DataFrame],
    universe_fn: Callable[[Window], list[str]],
    cost_model: CostModel,
    windows: list[Window],
    random_ev_pct: float | None = None,
) -> LabRunResult:
    all_trades: list[Trade] = []

    for window in windows:
        codes = [c for c in universe_fn(window) if c in bars_by_code]
        train = {code: _slice(bars_by_code[code], end=window.train_end) for code in codes}
        train = {c: df for c, df in train.items() if not df.empty}
        if not train:
            continue
        params = strategy.fit(train)

        for code in codes:
            # 지표 워밍업을 위해 학습 구간 포함, 검증 종료일까지만 노출 (그 뒤는 하네스가 차단)
            visible = _slice(bars_by_code[code], end=window.test_end)
            if visible.empty:
                continue
            signals = [
                s for s in strategy.signals(code, visible, params)
                if window.test_start <= s.signal_date <= window.test_end
            ]
            all_trades.extend(simulate_trades(visible, signals, cost_model, strategy.id))

    summary = summarize(all_trades)
    ci = bootstrap_ci([t.net_return_pct for t in all_trades])
    verdict = decide_verdict(summary.ev_pct, ci[0], random_ev_pct) if summary.n else "fail"
    return LabRunResult(
        strategy_id=strategy.id,
        strategy_label=strategy.label,
        trades=all_trades,
        summary=summary,
        ci=ci,
        random_ev_pct=random_ev_pct,
        verdict=verdict,
        windows=windows,
    )


def _slice(bars: pd.DataFrame, end: date) -> pd.DataFrame:
    mask = pd.to_datetime(bars["date"]).dt.date <= end
    return bars.loc[mask].reset_index(drop=True)
