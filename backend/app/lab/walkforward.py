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
    # 검증 구간에서 실제 사용된 피검체 신호 — 랜덤 벤치마크가 재계산 없이 재사용
    signals: list[Signal] = field(default_factory=list)


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
    # causal_signals=True: "signals(앞부분만 자른 시계열) == 전체 시계열 신호의
    # 그 구간 부분집합"을 보장하는 전략 (고정 규칙 + 과거 데이터만 사용,
    # 어댑터의 truncation 회귀 테스트로 검증). 이 경우 종목당 신호를 1회만
    # 계산하고, 시뮬레이션도 종목당 1회(전 윈도우 통합)로 돌려서
    # (a) 런타임을 크게 줄이고 (b) 윈도우 경계에서 트레이드가 잘리거나
    # 다음 윈도우와 중복 포지션이 생기는 아티팩트를 없앤다.
    if getattr(strategy, "causal_signals", False):
        all_trades, used_signals = _run_causal(strategy, bars_by_code, universe_fn, cost_model, windows)
    else:
        all_trades, used_signals = _run_per_window(strategy, bars_by_code, universe_fn, cost_model, windows)

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
        signals=used_signals,
    )


def _run_per_window(
    strategy: Strategy,
    bars_by_code: Mapping[str, pd.DataFrame],
    universe_fn: Callable[[Window], list[str]],
    cost_model: CostModel,
    windows: list[Window],
) -> tuple[list[Trade], list[Signal]]:
    """학습 파라미터가 윈도우마다 달라질 수 있는 전략의 기본 경로."""
    all_trades: list[Trade] = []
    used_signals: list[Signal] = []

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
            used_signals.extend(signals)
            all_trades.extend(simulate_trades(visible, signals, cost_model, strategy.id))

    return all_trades, used_signals


def _run_causal(
    strategy: Strategy,
    bars_by_code: Mapping[str, pd.DataFrame],
    universe_fn: Callable[[Window], list[str]],
    cost_model: CostModel,
    windows: list[Window],
) -> tuple[list[Trade], list[Signal]]:
    """고정 규칙(causal) 전략의 빠른 경로 — 종목당 신호/시뮬레이션 1회."""
    if not windows:
        return [], []
    # 고정 규칙이므로 params는 첫 학습 구간 기준 1회만
    first = windows[0]
    train = {
        code: df for code, df in (
            (c, _slice(bars_by_code[c], end=first.train_end)) for c in bars_by_code
        ) if not df.empty
    }
    params = strategy.fit(train) if train else {}

    # 종목이 "어떤 윈도우 유니버스에 속한 검증 구간"에서만 신호를 인정
    ranges_by_code: dict[str, list[Window]] = {}
    for window in windows:
        for code in universe_fn(window):
            if code in bars_by_code:
                ranges_by_code.setdefault(code, []).append(window)

    all_trades: list[Trade] = []
    used_signals: list[Signal] = []
    last_test_end = max(w.test_end for w in windows)

    for code, code_windows in ranges_by_code.items():
        visible = _slice(bars_by_code[code], end=last_test_end)
        if visible.empty:
            continue
        signals = [
            s for s in strategy.signals(code, visible, params)
            if any(w.test_start <= s.signal_date <= w.test_end for w in code_windows)
        ]
        used_signals.extend(signals)
        # 종목당 1회 시뮬레이션 → 전역 1종목 1포지션, 경계 truncation 없음
        all_trades.extend(simulate_trades(visible, signals, cost_model, strategy.id))

    return all_trades, used_signals


def _slice(bars: pd.DataFrame, end: date) -> pd.DataFrame:
    mask = pd.to_datetime(bars["date"]).dt.date <= end
    return bars.loc[mask].reset_index(drop=True)
