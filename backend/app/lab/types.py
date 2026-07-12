"""랩 공용 타입 — 신호와 시뮬레이션 트레이드.

Signal.signal_date는 "이 봉의 종가까지의 정보만으로 신호가 확정된 날"이다.
진입은 항상 다음 봉 시가로 시뮬레이션한다(신호 봉 종가 진입은 미래 참조).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Signal:
    code: str
    signal_date: date
    stop_price: float
    target_price: float | None = None
    max_holding_days: int = 40  # 거래일 기준 시간 청산


@dataclass(frozen=True)
class Trade:
    code: str
    strategy_id: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    exit_reason: str  # "stop" | "target" | "time" | "data_end"
    gross_return_pct: float  # 비용 차감 전 (참고용, 화면 노출 금지)
    net_return_pct: float    # 비용 차감 후 — 모든 지표는 이 값 기준
