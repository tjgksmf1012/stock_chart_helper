"""포트폴리오 자본곡선 — 일별 마크투마켓 + 고정 슬롯 균등가중.

metrics.Summary.mdd_pct는 "모든 트레이드를 순차 복리"로 가정해 다종목 결과에서
낙폭이 심하게 과장된다 (Phase 1에서 100%로 표기된 문제). 여기서는 각 포지션이
자본의 1/slots을 쓰고 나머지는 현금(수익률 0)이라는 현실적인 가정으로
일별 수익률을 집계해 MDD와 누적 수익률을 계산한다.

일별 마크: 진입일은 진입가→종가, 중간일은 종가→종가, 청산일은 직전 종가→청산가.
0가격 봉(거래정지)은 마크에서 건너뛴다.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping

import numpy as np
import pandas as pd

from .types import Trade


def portfolio_equity_metrics(
    trades: list[Trade],
    bars_by_code: Mapping[str, pd.DataFrame],
    slots: int = 10,
) -> dict[str, float]:
    empty = {"portfolio_mdd_pct": 0.0, "portfolio_total_return_pct": 0.0}
    if not trades:
        return empty

    daily: dict = defaultdict(float)  # date -> 슬롯 가중 전 수익률 합
    for trade in trades:
        bars = bars_by_code.get(trade.code)
        if bars is None or bars.empty:
            continue
        dates = pd.to_datetime(bars["date"]).dt.date.tolist()
        closes = [float(c) for c in bars["close"]]
        index_by_date = {d: i for i, d in enumerate(dates)}
        entry_idx = index_by_date.get(trade.entry_date)
        exit_idx = index_by_date.get(trade.exit_date)
        if entry_idx is None or exit_idx is None or exit_idx < entry_idx:
            continue

        prev_price = trade.entry_price
        for i in range(entry_idx, exit_idx + 1):
            mark = trade.exit_price if i == exit_idx else closes[i]
            if mark <= 0 or prev_price <= 0:
                continue  # 거래정지 등 0가격 봉은 마크 생략 (다음 유효 봉에서 갭 반영)
            daily[dates[i]] += mark / prev_price - 1
            prev_price = mark

    if not daily:
        return empty

    returns = [daily[d] / slots for d in sorted(daily)]
    equity = np.cumprod([1 + r for r in returns])
    peak = np.maximum.accumulate(equity)
    return {
        "portfolio_mdd_pct": float(np.max(1 - equity / peak)),
        "portfolio_total_return_pct": float(equity[-1] - 1),
    }
