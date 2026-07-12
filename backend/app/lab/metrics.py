"""검증 지표와 판정 — 스펙 §2 metrics.py.

판정 3등급:
- pass: EV > 0, 부트스트랩 95% CI 하한 > 0, 랜덤 벤치마크 EV 초과
- watch: EV > 0이지만 CI에 0 포함 또는 랜덤 벤치마크 못 넘음
- fail: EV <= 0
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import Trade


@dataclass(frozen=True)
class Summary:
    n: int
    ev_pct: float          # 거래당 순기대값 (비용 차감)
    win_rate: float
    payoff_ratio: float    # 평균이익 / 평균손실 (한쪽이 없으면 0)
    mdd_pct: float         # 청산일 순서 단일 포지션 복리 곡선 기준
    avg_holding_days: float


def summarize(trades: list[Trade]) -> Summary:
    if not trades:
        return Summary(n=0, ev_pct=0.0, win_rate=0.0, payoff_ratio=0.0, mdd_pct=0.0, avg_holding_days=0.0)

    returns = [t.net_return_pct for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [-r for r in returns if r < 0]
    payoff = (float(np.mean(wins)) / float(np.mean(losses))) if wins and losses else 0.0

    ordered = sorted(trades, key=lambda t: t.exit_date)
    equity = np.cumprod([1 + t.net_return_pct for t in ordered])
    peak = np.maximum.accumulate(equity)
    mdd = float(np.max(1 - equity / peak)) if len(equity) else 0.0

    holding = [max(1, (t.exit_date - t.entry_date).days) for t in trades]
    return Summary(
        n=len(trades),
        ev_pct=float(np.mean(returns)),
        win_rate=len(wins) / len(trades),
        payoff_ratio=payoff,
        mdd_pct=mdd,
        avg_holding_days=float(np.mean(holding)),
    )


def bootstrap_ci(
    values: list[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 42
) -> tuple[float, float]:
    """트레이드 수익률 리샘플링으로 평균의 (1-alpha) 신뢰구간."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def decide_verdict(ev_pct: float, ci_low: float, random_ev_pct: float | None) -> str:
    if ev_pct <= 0:
        return "fail"
    if ci_low > 0 and (random_ev_pct is None or ev_pct > random_ev_pct):
        return "pass"
    return "watch"
