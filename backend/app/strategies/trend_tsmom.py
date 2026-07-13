"""추세 필터 + 시계열 모멘텀 (TSMOM 최소형) — 스펙 §2 trend_momentum.

규칙 (고정 파라미터, 학습 없음):
- 최소 252거래일 이력 필요, 월 첫 거래일에만 평가 (월 1회 진입 후보)
- 신호: 종가 > 150일 이동평균 AND 12-1개월 모멘텀 > 0
  (12-1: 최근 1개월 제외 — 단기 반전 효과 회피, 학계 표준)
- 손절 15%, 목표 없음, 보유 60거래일
"""
from __future__ import annotations

import pandas as pd

from ..lab.types import Signal

_MIN_BARS = 252
_MA_WINDOW = 150
_SKIP_BARS = 21    # 최근 1개월
_MOM_BARS = 252    # 12개월
_STOP_PCT = 0.15
_MAX_HOLDING = 60


class TrendTsmomStrategy:
    id = "trend_tsmom"
    label = "추세+시계열 모멘텀 (월 1회)"
    causal_signals = True

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        if len(bars) < _MIN_BARS + 1:
            return []
        closes = bars["close"].astype(float)
        ma = closes.rolling(_MA_WINDOW).mean()
        dates = pd.to_datetime(bars["date"]).dt.date.tolist()
        close_list = closes.tolist()
        ma_list = ma.tolist()
        out: list[Signal] = []

        for i in range(_MIN_BARS, len(bars)):
            # 월 첫 거래일만 평가
            if dates[i].month == dates[i - 1].month:
                continue
            close = close_list[i]
            base = close_list[i - _MOM_BARS]
            recent = close_list[i - _SKIP_BARS]
            if close <= 0 or base <= 0 or recent <= 0 or pd.isna(ma_list[i]):
                continue
            momentum_12_1 = recent / base - 1
            if close > ma_list[i] and momentum_12_1 > 0:
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
