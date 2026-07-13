"""52주 신고가 근접 돌파 (George & Hwang 계열) — 스펙 §2 high52_breakout.

규칙 (고정 파라미터, 학습 없음):
- 최소 252거래일 이력 필요
- 신호: 당일 종가가 52주(252봉) 고가의 98% 이상 AND 직전 20봉 종가 최고치 돌파
- 손절 8%, 목표 없음, 보유 40거래일
"""
from __future__ import annotations

import pandas as pd

from ..lab.types import Signal

_LOOKBACK = 252
_NEAR_HIGH = 0.98
_BREAKOUT_LOOKBACK = 20
_STOP_PCT = 0.08
_MAX_HOLDING = 40


class High52BreakoutStrategy:
    id = "high52_breakout"
    label = "52주 신고가 근접 돌파"
    causal_signals = True

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        if len(bars) < _LOOKBACK + 1:
            return []
        highs = bars["high"].astype(float).tolist()
        closes = bars["close"].astype(float).tolist()
        dates = pd.to_datetime(bars["date"]).dt.date.tolist()
        out: list[Signal] = []

        for i in range(_LOOKBACK, len(bars)):
            close = closes[i]
            if close <= 0:
                continue
            high_52w = max(highs[i - _LOOKBACK + 1: i + 1])
            prev_20_close_max = max(closes[i - _BREAKOUT_LOOKBACK: i])
            if high_52w <= 0 or prev_20_close_max <= 0:
                continue
            if close >= _NEAR_HIGH * high_52w and close > prev_20_close_max:
                out.append(
                    Signal(
                        code=code,
                        signal_date=dates[i],
                        stop_price=close * (1 - _STOP_PCT),
                        target_price=None,
                        max_holding_days=_MAX_HOLDING,
                    )
                )
        return out
