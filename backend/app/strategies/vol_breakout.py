"""변동성 돌파 (래리 윌리엄스 k-팩터, 일봉 종가 확인형) — 스펙 §2 vol_breakout.

규칙 (고정 파라미터, 학습 없음):
- 신호: 당일 종가 > 당일 시가 + k × 전일 레인지(고가-저가), k=0.5
- 손절 3%, 목표 없음(시간 청산), 보유 10거래일
원전은 장중 돌파 진입이지만, 일봉 백테스트에서는 종가 확인 후 다음 날 시가
진입(시뮬레이터 규칙)이 미래 참조 없는 보수적 근사다.
"""
from __future__ import annotations

import pandas as pd

from ..lab.types import Signal

_K = 0.5
_STOP_PCT = 0.03
_MAX_HOLDING = 10


class VolBreakoutStrategy:
    id = "vol_breakout"
    label = "변동성 돌파 (k=0.5)"
    causal_signals = True

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        if len(bars) < 2:
            return []
        out: list[Signal] = []
        highs = bars["high"].astype(float).tolist()
        lows = bars["low"].astype(float).tolist()
        opens = bars["open"].astype(float).tolist()
        closes = bars["close"].astype(float).tolist()
        dates = pd.to_datetime(bars["date"]).dt.date.tolist()

        for i in range(1, len(bars)):
            prev_range = highs[i - 1] - lows[i - 1]
            if prev_range <= 0 or opens[i] <= 0 or closes[i] <= 0:
                continue
            if closes[i] > opens[i] + _K * prev_range:
                out.append(
                    Signal(
                        code=code,
                        signal_date=dates[i],
                        stop_price=closes[i] * (1 - _STOP_PCT),
                        target_price=None,
                        max_holding_days=_MAX_HOLDING,
                    )
                )
        return out
