"""ATR 적응 손절 래퍼 — 고정 % 손절을 변동성 비례로 바꾼다.

사전 등록 실험 ② (2026-07-18 등록, 파라미터 고정 2.5×ATR(20) — 그리드 서치 금지):
고정 % 손절은 저변동 종목에선 너무 넓고 고변동 종목에선 너무 좁다.
가설: 노이즈 손절이 줄어 손익비가 개선된다.

인과성: 신호일의 ATR은 그 날짜까지의 봉으로만 계산된다 (rolling — 미래 참조 없음).
ATR 워밍업이 안 된 신호는 원본 손절을 유지한다 (신호를 버리는 것보다 보수적).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import pandas as pd

from .types import Signal

DEFAULT_ATR_WINDOW = 20
DEFAULT_ATR_MULT = 2.5


def compute_atr(bars: pd.DataFrame, window: int = DEFAULT_ATR_WINDOW) -> pd.Series:
    """단순이동평균 ATR — TR = max(고저폭, |고가-전일종가|, |저가-전일종가|)."""
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    prev_close = bars["close"].astype(float).shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(window).mean()


class AtrStopStrategy:
    """전략 래퍼 — 신호의 손절가를 '신호일 종가 − mult×ATR'로 교체한다.

    id는 원본 유지(리포트 비교·파이프라인 호환), 라벨로만 구분. 손절 외
    (신호일·목표가·보유기간)는 건드리지 않는다.
    """

    def __init__(self, inner, atr_window: int = DEFAULT_ATR_WINDOW, atr_mult: float = DEFAULT_ATR_MULT):
        self._inner = inner
        self._window = atr_window
        self._mult = atr_mult
        self.id = inner.id
        self.label = f"{inner.label} + ATR 손절({atr_mult}×{atr_window})"
        self.causal_signals = getattr(inner, "causal_signals", False)
        # 하네스는 hasattr(panel_signals)로 경로를 고른다 — 원본에 있을 때만 노출
        if hasattr(inner, "panel_signals"):
            self.panel_signals = self._panel_signals_with_atr

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return self._inner.fit(train_bars)

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        return self._apply(self._inner.signals(code, bars, params), bars)

    def _panel_signals_with_atr(self, bars_by_code: Mapping[str, pd.DataFrame], params: dict) -> list[Signal]:
        out: list[Signal] = []
        raw = self._inner.panel_signals(bars_by_code, params)
        by_code: dict[str, list[Signal]] = {}
        for s in raw:
            by_code.setdefault(s.code, []).append(s)
        for code, sigs in by_code.items():
            bars = bars_by_code.get(code)
            out.extend(self._apply(sigs, bars) if bars is not None else sigs)
        return out

    def _apply(self, sigs: list[Signal], bars: pd.DataFrame) -> list[Signal]:
        if not sigs or bars is None or bars.empty:
            return sigs
        atr = compute_atr(bars, self._window)
        closes = bars["close"].astype(float)
        idx_by_date = {
            (d.date() if hasattr(d, "date") else d): i
            for i, d in enumerate(pd.to_datetime(bars["date"]))
        }
        out: list[Signal] = []
        for sig in sigs:
            i = idx_by_date.get(sig.signal_date)
            if i is None or pd.isna(atr.iloc[i]) or atr.iloc[i] <= 0:
                out.append(sig)  # ATR 불가 → 원본 손절 유지 (보수적)
                continue
            stop = float(closes.iloc[i]) - self._mult * float(atr.iloc[i])
            if stop <= 0:
                out.append(sig)  # 극단 변동성으로 음수 손절 → 원본 유지
                continue
            out.append(replace(sig, stop_price=stop))
        return out
