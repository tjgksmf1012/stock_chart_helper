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
    out: list[dict[str, Any]] = []
    for code, bars in bars_by_code.items():
        if bars is None or bars.empty:
            continue
        for sig in strategy.signals(code, bars, {}):
            if floor <= sig.signal_date <= as_of:
                out.append(
                    {
                        "strategy_id": strategy.id,
                        "strategy_label": getattr(strategy, "label", strategy.id),
                        "code": sig.code,
                        "signal_date": sig.signal_date.isoformat(),
                        "stop_price": round(sig.stop_price, 2),
                        "target_price": round(sig.target_price, 2) if sig.target_price is not None else None,
                        "max_holding_days": sig.max_holding_days,
                    }
                )
    out.sort(key=lambda s: s["signal_date"], reverse=True)
    return out
