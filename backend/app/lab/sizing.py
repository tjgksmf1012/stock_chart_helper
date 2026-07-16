"""포지션 사이징 — "엣지가 있다"를 "얼마를 사도 되는가"로 변환하는 레이어.

두 가지를 제공한다:
1. position_size(): 고정 리스크(fixed-fractional) 사이징 — 손절에 걸렸을 때
   정확히 계좌의 risk_pct만 잃도록 주수를 계산. 손절이 타이트하면 포지션이
   계좌 대비 과대해지므로 집중 상한(max_position_pct)으로 자른다.
2. risk_based_metrics(): 백테스트 트레이드를 R-멀티플(수익률 ÷ 손절거리)로
   환산해 "매 트레이드 리스크 R%" 규율로 운용했을 때의 자본곡선/MDD.
   기존 슬롯 균등가중 MDD보다 실제 운용 규율에 가까운 수치다.

정직성 규칙: 갭 하락으로 손절보다 훨씬 아래에서 체결되면 R-멀티플이 폭주하므로
트레이드당 손실 상한(max_loss_r)을 두되, 이는 낙관이 아니라 "그 이상은
사이징만으로 못 막는다"는 한계를 명시하는 것이다 — 리포트에 함께 표기할 것.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from .types import Trade


def position_size(
    account_value: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    max_position_pct: float = 0.2,
) -> dict[str, Any]:
    """손절 시 계좌의 risk_pct만 잃도록 주수 계산 (롱 전용).

    반환: shares, position_value, risk_amount, capped_by_concentration
    손절이 진입가 이상이거나 입력이 유효하지 않으면 shares=0.
    """
    empty = {"shares": 0, "position_value": 0.0, "risk_amount": 0.0, "capped_by_concentration": False}
    if account_value <= 0 or risk_pct <= 0 or entry_price <= 0:
        return empty
    per_share_risk = entry_price - stop_price
    if per_share_risk <= 0:
        return empty  # 롱인데 손절이 진입가 이상 — 사이징 불가

    shares = math.floor(account_value * risk_pct / per_share_risk)
    capped = False
    max_shares_by_concentration = math.floor(account_value * max_position_pct / entry_price)
    if shares > max_shares_by_concentration:
        shares = max_shares_by_concentration
        capped = True

    return {
        "shares": shares,
        "position_value": shares * entry_price,
        "risk_amount": round(shares * per_share_risk),
        "capped_by_concentration": capped,
    }


def risk_based_metrics(
    trades: Iterable[Trade],
    risk_pct: float = 0.01,
    max_loss_r: float = 3.0,
) -> dict[str, Any]:
    """트레이드를 R-멀티플로 환산해 고정 리스크 운용 시의 자본곡선 지표 계산.

    R = net_return_pct / stop_distance_pct (stop_distance = (entry-stop)/entry).
    각 트레이드가 자본에 미치는 영향 = risk_pct × R. 손실 R은 max_loss_r로 상한
    (갭 폭주 방지 — 한계는 리포트에 명시). stop_price 없는 트레이드는 제외.
    """
    r_multiples: list[float] = []
    ordered = sorted(trades, key=lambda t: t.exit_date)
    for trade in ordered:
        if trade.stop_price is None or trade.entry_price <= 0:
            continue
        stop_distance = (trade.entry_price - trade.stop_price) / trade.entry_price
        if stop_distance <= 0:
            continue
        r = trade.net_return_pct / stop_distance
        if r < -max_loss_r:
            r = -max_loss_r
        r_multiples.append(r)

    if not r_multiples:
        return {"n_used": 0, "total_return_pct": 0.0, "mdd_pct": 0.0, "avg_r": 0.0, "risk_pct": risk_pct}

    # 초기 자본 1.0을 곡선 앞에 붙인다 — 안 붙이면 첫 트레이드가 손실일 때
    # 초기 자본 대비 낙폭이 MDD에서 통째로 빠진다
    equity = np.cumprod([1.0] + [1 + risk_pct * r for r in r_multiples])
    peak = np.maximum.accumulate(equity)
    return {
        "n_used": len(r_multiples),
        "total_return_pct": float(equity[-1] - 1),
        "mdd_pct": float(np.max(1 - equity / peak)),
        "avg_r": float(np.mean(r_multiples)),
        "risk_pct": risk_pct,
    }
