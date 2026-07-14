"""자동 종이매매 — 라이브 신호를 기록하고 백테스트와 같은 규칙으로 청산.

순수 로직(중복 제거, 실측 집계)은 이 모듈에, DB IO와 시세 로딩은 라우터/스케줄러가
담당한다. 청산은 lab.simulate.simulate_trades를 그대로 써서 백테스트와 의미를
일치시킨다 — 그래야 실측 EV와 백테스트 EV의 드리프트를 apples-to-apples로 잰다.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from ..lab.costs import CostModel
from ..lab.simulate import simulate_trades
from ..lab.types import Signal


def dedupe_key(strategy_id: str, code: str, signal_date: str) -> tuple[str, str, str]:
    return (strategy_id, code, signal_date)


def new_paper_trade_signals(
    signals: Iterable[Mapping[str, Any]], existing_keys: set[tuple[str, str, str]]
) -> list[dict[str, Any]]:
    """이미 기록된(strategy+code+signal_date) 신호와 배치 내 중복을 제거한 새 신호만."""
    seen = set(existing_keys)
    out: list[dict[str, Any]] = []
    for sig in signals:
        key = dedupe_key(sig["strategy_id"], sig["code"], sig["signal_date"])
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(sig))
    return out


def evaluate_paper_trade(
    open_trade: Mapping[str, Any], bars: pd.DataFrame, cost_model: CostModel
) -> dict[str, Any] | None:
    """열린 종이매매를 백테스트와 같은 규칙으로 청산 시도.

    반환:
    - 청산 필드 dict (stop/target/time 도달) → 호출부가 status=closed로 갱신
    - None → 아직 진입 전이거나 보유기간이 안 끝남(data_end) → 계속 열어둠
    백테스트와 동일한 simulate_trades를 쓰므로 실측 EV가 백테스트 EV와 같은 규칙.
    """
    signal = Signal(
        code=open_trade["code"],
        signal_date=date.fromisoformat(open_trade["signal_date"]),
        stop_price=float(open_trade["stop_price"]),
        target_price=open_trade["target_price"],
        max_holding_days=int(open_trade["max_holding_days"]),
    )
    trades = simulate_trades(bars, [signal], cost_model, strategy_id=open_trade.get("strategy_id", "lab"))
    if not trades:
        return None  # 진입 봉 없음 (신호가 마지막 봉) → 아직 열어둠
    trade = trades[0]
    if trade.exit_reason == "data_end":
        return None  # 보유기간 미완료 → 열어둠
    return {
        "entry_date": trade.entry_date.isoformat(),
        "entry_price": trade.entry_price,
        "exit_date": trade.exit_date.isoformat(),
        "exit_price": trade.exit_price,
        "exit_reason": trade.exit_reason,
        "net_return_pct": trade.net_return_pct,
    }


def realized_summary_by_strategy(trades: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    """닫힌 종이매매를 전략별로 묶어 실측 EV·승률·표본수를 집계."""
    by_strategy: dict[str, list[float]] = {}
    for trade in trades:
        if trade.get("status") != "closed" or trade.get("net_return_pct") is None:
            continue
        by_strategy.setdefault(trade["strategy_id"], []).append(float(trade["net_return_pct"]))

    summary: dict[str, dict[str, float]] = {}
    for strategy_id, returns in by_strategy.items():
        arr = np.asarray(returns, dtype=float)
        summary[strategy_id] = {
            "n": int(len(arr)),
            "ev_pct": float(arr.mean()),
            "win_rate": float((arr > 0).mean()),
        }
    return summary


# 드리프트 판정에 필요한 최소 실측 표본 — 이 미만이면 판단 보류
_MIN_DRIFT_SAMPLES = 20


def drift_status(realized_ev: float | None, realized_n: int, backtest_ci_low: float | None) -> str:
    """실측 EV가 백테스트 신뢰구간 하한을 이탈했는지 판정.

    - insufficient: 실측 표본이 아직 부족(<20)
    - drifting: 실측 EV가 백테스트 95% CI 하한보다 낮음 → 전략을 관찰로 강등해야 함
    - ok: 실측이 백테스트 하한 이상 (검증이 실전에서도 유지되는 중)
    백테스트 CI가 없으면 unknown.
    """
    if realized_n < _MIN_DRIFT_SAMPLES or realized_ev is None:
        return "insufficient"
    if backtest_ci_low is None:
        return "unknown"
    return "drifting" if realized_ev < backtest_ci_low else "ok"
