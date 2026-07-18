"""시장 체제 게이트 — 지수가 장기 이동평균 아래면 신호 발행을 정지하는 래퍼.

사전 등록 실험 ① (2026-07-18): 추세·돌파 전략은 약세장에서 피를 흘린다는
문헌·자체 실측(2022 상반기 편입 후 전 전략 성적 하락)에 따라, KOSPI 종가가
200일 이동평균 위일 때만 신호를 인정한다. 게이트는 신호일까지의 지수 데이터만
사용한다 (인과성 — MA는 과거 종가로만 계산, 결측일은 직전 지수일로 판정).
"""
from __future__ import annotations

import bisect
from datetime import date
from typing import Callable, Mapping

import pandas as pd

from .types import Signal

RegimeLookup = Callable[[date], bool]

DEFAULT_MA_WINDOW = 200


def fetch_kospi_bars(lookback_days: int = 400) -> pd.DataFrame:
    """KOSPI 지수 일봉(date/close) — FDR 'KS11'. 게이트 판정용 (블로킹 IO).

    async 컨텍스트에서는 asyncio.to_thread로 감싸서 호출할 것.
    """
    from datetime import timedelta

    import FinanceDataReader as fdr

    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    raw = fdr.DataReader("KS11", start)
    return pd.DataFrame({"date": raw.index.date, "close": raw["Close"].values})


def build_regime_lookup(index_bars: pd.DataFrame, ma_window: int = 200) -> RegimeLookup:
    """지수 일봉(date/close)으로 '이 날짜에 체제가 우호적인가' 조회 함수를 만든다.

    - 판정: 그 날짜 기준 직전 지수일의 종가 > 그 시점 MA(ma_window)
    - MA 워밍업 이전이거나 지수 이력 밖이면 False (모르면 안 산다 — 보수적)
    """
    frame = index_bars.sort_values("date").reset_index(drop=True)
    closes = frame["close"].astype(float)
    ma = closes.rolling(ma_window).mean()
    dates = [d.date() if hasattr(d, "date") else d for d in pd.to_datetime(frame["date"])]
    ok_flags = [
        bool((not pd.isna(ma.iloc[i])) and closes.iloc[i] > ma.iloc[i])
        for i in range(len(frame))
    ]

    def lookup(when: date) -> bool:
        # 직전 지수일 asof — 주말·휴장일 신호도 마지막 거래일 체제로 판정
        idx = bisect.bisect_right(dates, when) - 1
        if idx < 0:
            return False
        return ok_flags[idx]

    return lookup


class RegimeGatedStrategy:
    """전략 래퍼 — 신호일의 체제가 우호적일 때만 신호를 통과시킨다.

    id는 원본 그대로 유지한다 (리포트 비교·기존 파이프라인 호환), 라벨로만 구분.
    """

    def __init__(self, inner, regime_ok: RegimeLookup):
        self._inner = inner
        self._regime_ok = regime_ok
        self.id = inner.id
        self.label = f"{inner.label} + 체제 게이트"
        self.causal_signals = getattr(inner, "causal_signals", False)
        # 하네스는 hasattr(panel_signals)로 패널/종목 경로를 고른다 — 원본에 있을 때만
        # 래퍼에도 노출해야 종목 단위 전략이 패널 경로로 잘못 들어가지 않는다.
        if hasattr(inner, "panel_signals"):
            self.panel_signals = self._gated_panel_signals

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return self._inner.fit(train_bars)

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        return [s for s in self._inner.signals(code, bars, params) if self._regime_ok(s.signal_date)]

    def _gated_panel_signals(self, bars_by_code: Mapping[str, pd.DataFrame], params: dict) -> list[Signal]:
        return [s for s in self._inner.panel_signals(bars_by_code, params) if self._regime_ok(s.signal_date)]
