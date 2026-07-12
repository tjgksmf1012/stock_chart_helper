"""거래 비용 모델 — 모든 랩 수익률은 이 모델을 통과한 net 값만 쓴다.

기본값은 한국 주식 개인 기준 보수적 추정:
- 수수료 편도 0.015%, 매도 시 거래세 0.15%, 슬리피지 편도 0.1%
왕복 약 0.38%. 비용 차감 전 수치는 화면에 표시하지 않는다(스펙).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    commission_pct: float = 0.00015
    tax_pct: float = 0.0015
    slippage_pct: float = 0.001

    @property
    def entry_cost_pct(self) -> float:
        return self.commission_pct + self.slippage_pct

    @property
    def exit_cost_pct(self) -> float:
        return self.commission_pct + self.tax_pct + self.slippage_pct

    @property
    def round_trip_pct(self) -> float:
        return self.entry_cost_pct + self.exit_cost_pct

    def net_return_pct(self, entry_price: float, exit_price: float) -> float:
        """실효 매수단가/매도단가 기준 순수익률."""
        buy = entry_price * (1 + self.entry_cost_pct)
        sell = exit_price * (1 - self.exit_cost_pct)
        return sell / buy - 1
