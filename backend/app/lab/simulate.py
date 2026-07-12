"""신호 → 트레이드 시뮬레이션 (롱 온리, 보수적 체결 규칙).

규칙 (스펙 §2, deep_analysis/backtest_engine의 보수 관행 계승):
- 진입: 신호 다음 봉 시가. 다음 봉이 없으면 신호 폐기.
- 청산 우선순위 (봉 단위): ① 손절 (같은 봉에서 목표와 겹치면 손절 우선,
  갭다운으로 시가가 이미 손절 아래면 시가 체결) ② 목표 (갭업이면 시가)
  ③ 시간 청산 (진입 봉 포함 max_holding_days 거래일째 종가)
  ④ 데이터 끝 (마지막 종가, exit_reason="data_end")
- 1종목 1포지션: 보유 중 발생한 신호는 버린다.
"""
from __future__ import annotations

import pandas as pd

from .costs import CostModel
from .types import Signal, Trade


def simulate_trades(
    bars: pd.DataFrame,
    signals: list[Signal],
    cost_model: CostModel,
    strategy_id: str,
) -> list[Trade]:
    if bars.empty or not signals:
        return []

    dates = pd.to_datetime(bars["date"]).dt.date.tolist()
    index_by_date = {d: i for i, d in enumerate(dates)}
    trades: list[Trade] = []
    blocked_until = -1  # 이 인덱스(포함)까지 포지션 보유 중

    for signal in sorted(signals, key=lambda s: s.signal_date):
        signal_idx = index_by_date.get(signal.signal_date)
        if signal_idx is None or signal_idx + 1 >= len(bars):
            continue
        entry_idx = signal_idx + 1
        if entry_idx <= blocked_until:
            continue  # 1종목 1포지션

        entry_price = float(bars.iloc[entry_idx]["open"])
        exit_idx, exit_price, exit_reason = _resolve_exit(bars, entry_idx, signal)
        gross = exit_price / entry_price - 1
        trades.append(
            Trade(
                code=signal.code,
                strategy_id=strategy_id,
                entry_date=dates[entry_idx],
                entry_price=entry_price,
                exit_date=dates[exit_idx],
                exit_price=exit_price,
                exit_reason=exit_reason,
                gross_return_pct=round(gross, 6),
                net_return_pct=round(cost_model.net_return_pct(entry_price, exit_price), 6),
            )
        )
        blocked_until = exit_idx

    return trades


def _resolve_exit(bars: pd.DataFrame, entry_idx: int, signal: Signal) -> tuple[int, float, str]:
    last_idx = len(bars) - 1
    time_exit_idx = min(entry_idx + signal.max_holding_days - 1, last_idx)

    for idx in range(entry_idx, time_exit_idx + 1):
        bar = bars.iloc[idx]
        open_, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
        # ① 손절 우선 (보수적) — 갭다운이면 실제 체결 가능한 시가로
        if low <= signal.stop_price:
            return idx, min(open_, signal.stop_price), "stop"
        # ② 목표 — 갭업이면 시가로 (더 유리한 체결을 가정하지 않는다)
        if signal.target_price is not None and high >= signal.target_price:
            return idx, max(open_, signal.target_price), "target"

    close = float(bars.iloc[time_exit_idx]["close"])
    # 보유 일수를 다 채우기 전에 데이터가 끝났으면 time이 아니라 data_end
    reached_full_holding = (entry_idx + signal.max_holding_days - 1) <= last_idx
    return time_exit_idx, close, ("time" if reached_full_holding else "data_end")
