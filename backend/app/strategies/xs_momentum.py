"""횡단면 모멘텀 (상대 강도) — 유니버스에서 상대적으로 강한 종목을 산다.

시계열 모멘텀(trend_tsmom: "이 종목이 자기 과거보다 강한가")과 독립적인,
가장 오래 검증된 팩터("남들보다 강한가"). 규칙 고정, 학습 없음:
- 월 첫 거래일 리밸런스, 12-1개월 모멘텀 (최근 1개월 제외 — 단기 반전 회피)
- 그 달 유효 종목(253봉 이상) 중 모멘텀 > 0 이면서 상위 10% (최소 5종목)
- 손절 15%, 목표 없음, 보유 21거래일 (다음 리밸런스까지 — 여전히 상위면 재신호)
"""
from __future__ import annotations

import math
from typing import Mapping

import pandas as pd

from ..lab.types import Signal

_MIN_BARS = 253
_SKIP_BARS = 21
_MOM_BARS = 252
_STOP_PCT = 0.15
_MAX_HOLDING = 21
_TOP_PCT = 0.10
_MIN_PICKS = 5


class XsMomentumStrategy:
    id = "xs_momentum"
    label = "횡단면 모멘텀 (상대 강도, 월 1회)"
    causal_signals = True

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        # 단독 종목으로는 "상대 강도"가 정의되지 않는다 — 패널 경로 전용
        return []

    def panel_signals(self, bars_by_code: Mapping[str, pd.DataFrame], params: dict) -> list[Signal]:
        # month_key -> code -> (signal_date, momentum, close)
        # 리밸런스일의 모멘텀은 그 날까지의 데이터만 쓰므로 패널을 뒤에서 잘라도
        # 과거 신호가 변하지 않는다 (인과성 — 회귀 테스트로 보증).
        by_month: dict[str, dict[str, tuple]] = {}
        for code, bars in bars_by_code.items():
            if bars is None or len(bars) < _MIN_BARS:
                continue
            dates = pd.to_datetime(bars["date"]).dt.date.tolist()
            closes = bars["close"].astype(float).tolist()
            for i in range(_MIN_BARS - 1, len(bars)):
                if i > 0 and dates[i].month == dates[i - 1].month:
                    continue  # 월 첫 거래일만
                base, recent, close = closes[i - _MOM_BARS], closes[i - _SKIP_BARS], closes[i]
                if base <= 0 or recent <= 0 or close <= 0:
                    continue
                month_key = f"{dates[i].year:04d}-{dates[i].month:02d}"
                by_month.setdefault(month_key, {})[code] = (dates[i], recent / base - 1, close)

        out: list[Signal] = []
        for month_key in sorted(by_month):
            entries = by_month[month_key]
            n_picks = max(_MIN_PICKS, math.ceil(len(entries) * _TOP_PCT))
            ranked = sorted(entries.items(), key=lambda kv: kv[1][1], reverse=True)
            for code, (signal_date, momentum, close) in ranked[:n_picks]:
                if momentum <= 0:
                    break  # 내림차순이므로 이후는 전부 0 이하
                out.append(Signal(
                    code=code, signal_date=signal_date,
                    stop_price=close * (1 - _STOP_PCT),
                    target_price=None, max_holding_days=_MAX_HOLDING,
                ))
        out.sort(key=lambda s: (s.signal_date, s.code))
        return out
