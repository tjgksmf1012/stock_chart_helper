"""신호 게이트 — 검증을 통과한(pass/watch) 전략의 최근 신호만 수집.

스펙(2026-07-12 트레이딩 랩) Phase 3의 핵심: 탈락(fail) 전략의 신호는 추천에
쓰이지 않는다. 이 모듈은 순수 로직(어느 전략이 자격 있나, 최근 신호 필터)만
담고, 시세/유니버스 로딩 IO는 라우터가 담당한다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

import pandas as pd

_VERDICT_ORDER = {"pass": 0, "watch": 1, "fail": 2}
_DEFAULT_ALLOWED = frozenset({"pass", "watch"})


def eligible_strategy_ids(
    reports: Iterable[Mapping[str, Any]], allowed: Iterable[str] = _DEFAULT_ALLOWED
) -> list[str]:
    """검증 리포트에서 자격 있는 전략 id를 판정 우선순위 순으로 반환."""
    allowed_set = set(allowed)
    eligible = [r for r in reports if r.get("verdict") in allowed_set]
    eligible.sort(key=lambda r: (_VERDICT_ORDER.get(r.get("verdict"), 3), -(r.get("ev_pct") or 0.0)))
    return [str(r["strategy"]) for r in eligible if r.get("strategy")]


def collect_recent_signals(
    strategy: Any,
    bars_by_code: Mapping[str, pd.DataFrame],
    as_of: date,
    lookback_days: int = 5,
) -> list[dict[str, Any]]:
    """전략을 각 종목 시세에 돌려, 최근 lookback_days 영업일 내 신호만 dict로 반환.

    신호일이 as_of - lookback_days ~ as_of 사이인 것만 남긴다 (오래된 신호 제외).
    """
    floor = as_of - timedelta(days=lookback_days)
    # 종목당 대표 신호 1개만 — 같은 종목이 여러 패턴으로 잡히면 리스트에 반복돼
    # 구매자에게 중복 피로감을 준다. 최신 신호일 우선, 동률이면 가장 타이트한(높은)
    # 손절을 남긴다 (롱 기준 손실 폭이 작은 쪽).
    best_by_code: dict[str, dict[str, Any]] = {}
    for code, bars in bars_by_code.items():
        if bars is None or bars.empty:
            continue
        # 신호일 종가 조회용 — 포지션 사이징의 기준가(다음날 시가 진입의 근사)
        close_by_date = {
            d.date() if hasattr(d, "date") else d: float(c)
            for d, c in zip(pd.to_datetime(bars["date"]), bars["close"])
        }
        for sig in strategy.signals(code, bars, {}):
            if not (floor <= sig.signal_date <= as_of):
                continue
            reference = close_by_date.get(sig.signal_date)
            row = {
                "strategy_id": strategy.id,
                "strategy_label": getattr(strategy, "label", strategy.id),
                "code": sig.code,
                "signal_date": sig.signal_date.isoformat(),
                "reference_price": round(reference, 2) if reference else None,
                "stop_price": round(sig.stop_price, 2),
                "target_price": round(sig.target_price, 2) if sig.target_price is not None else None,
                "max_holding_days": sig.max_holding_days,
            }
            prev = best_by_code.get(sig.code)
            if prev is None or (row["signal_date"], row["stop_price"]) > (prev["signal_date"], prev["stop_price"]):
                best_by_code[sig.code] = row

    out = sorted(best_by_code.values(), key=lambda s: s["signal_date"], reverse=True)
    return out
