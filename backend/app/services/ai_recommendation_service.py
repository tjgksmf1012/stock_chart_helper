"""Rule-based portfolio manager style recommendations from scan results."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime

from ..api.schemas import AiRecommendationItem, AiRecommendationResponse, SymbolInfo
from ..core.redis import cache_get, cache_set
from .openai_recommendation_service import apply_openai_recommendation_overlay
from .personalization_service import load_personalization_snapshot, score_personal_fit
from .scanner import get_scan_results
from .timeframe_service import DEFAULT_TIMEFRAME, timeframe_label


DISCLAIMER = "투자 권유가 아닌 기술적 분석 보조 정보입니다. 실제 매매 여부, 비중, 손절, 현금 관리는 직접 확인하세요."
WATCHLIST_CACHE_KEY = "watchlist:v1:default"

STANCE_LABELS = {
    "priority_watch": "우선 검토",
    "wait_for_trigger": "트리거 대기",
    "avoid_chase": "추격 금지",
    "risk_review": "리스크 점검",
}

_RECOMMENDATION_CACHE_PREFIX = "ai:recommendations:v3"
_IN_FLIGHT_RECOMMENDATIONS: set[str] = set()


async def build_ai_recommendations(timeframe: str = DEFAULT_TIMEFRAME, limit: int = 8) -> AiRecommendationResponse:
    timeframe = timeframe or DEFAULT_TIMEFRAME
    cache_key = f"{_RECOMMENDATION_CACHE_PREFIX}:{timeframe}:{limit}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict):
        return AiRecommendationResponse.model_validate(cached)

    if cache_key in _IN_FLIGHT_RECOMMENDATIONS:
        await asyncio.sleep(0.15)
        cached = await cache_get(cache_key)
        if isinstance(cached, dict):
            return AiRecommendationResponse.model_validate(cached)

    _IN_FLIGHT_RECOMMENDATIONS.add(cache_key)
    try:
        rows, watch_codes, personalization = await asyncio.gather(
            get_scan_results(timeframe),
            _load_watchlist_codes(),
            load_personalization_snapshot(),
        )
        ranked = [_make_recommendation(row, timeframe, watch_codes, personalization) for row in rows]
        _apply_overlap_risk(ranked)
        ranked.sort(
            key=lambda item: (
                item.watchlist_priority,
                _watchlist_focus_score(item),
                item.personal_fit_score,
                item.score,
                item.confidence,
                item.p_up - item.p_down,
            ),
            reverse=True,
        )

        items = _rerank(ranked[:limit])
        priority_items = _rerank([item for item in ranked if item.stance == "priority_watch"][:limit])
        watch_items = _rerank([item for item in ranked if item.stance in {"wait_for_trigger", "avoid_chase"}][:limit])
        risk_items = _rerank(
            sorted(
                [item for item in ranked if item.stance == "risk_review"],
                key=lambda item: (
                    item.watchlist_priority,
                    item.personal_fit_score,
                    len(item.risk_flags),
                    1 - item.data_quality,
                    item.p_down,
                ),
                reverse=True,
            )[:limit]
        )
        watchlist_focus_items = _rerank(
            sorted(
                [item for item in ranked if item.watchlist_priority],
                key=lambda item: (_watchlist_focus_score(item), item.personal_fit_score, item.score, item.confidence),
                reverse=True,
            )[:limit]
        )
        personalized_items = _rerank(
            sorted(
                [item for item in ranked if item.personal_fit_score > 0],
                key=lambda item: (item.watchlist_priority, item.personal_fit_score, item.score, item.confidence),
                reverse=True,
            )[:limit]
        )

        response = AiRecommendationResponse(
            generated_at=datetime.utcnow().isoformat(),
            timeframe=timeframe,
            timeframe_label=timeframe_label(timeframe),
            market_brief=_market_brief(ranked, timeframe, watchlist_focus_items),
            portfolio_guidance=_portfolio_guidance(
                priority_items,
                watch_items,
                risk_items,
                watchlist_focus_items,
                personalized_items,
                personalization,
            ),
            items=items,
            priority_items=priority_items,
            watch_items=watch_items,
            risk_items=risk_items,
            watchlist_focus_items=watchlist_focus_items,
            personalized_items=personalized_items,
            personal_style=personalization.get("style_profile") or {},
            disclaimer=DISCLAIMER,
        )
        response = await apply_openai_recommendation_overlay(response)
        await cache_set(cache_key, response.model_dump(mode="json"), ttl=45)
        return response
    finally:
        _IN_FLIGHT_RECOMMENDATIONS.discard(cache_key)


async def _load_watchlist_codes() -> set[str]:
    stored = await cache_get(WATCHLIST_CACHE_KEY)
    if not isinstance(stored, list):
        return set()
    return {str(item.get("code", "")).strip() for item in stored if isinstance(item, dict) and item.get("code")}


def _make_recommendation(row: dict, timeframe: str, watch_codes: set[str], personalization: dict | None) -> AiRecommendationItem:
    watched = str(row.get("code", "")) in watch_codes
    score = min(_recommendation_score(row) + _watchlist_score_bonus(row, watched), 100.0)
    confidence = _confidence(row)
    stance = _stance(row, score)
    symbol_code = row["code"]
    personal_fit_score, personal_fit_label, personal_fit_reasons = score_personal_fit(row, personalization)

    return AiRecommendationItem(
        rank=0,
        symbol=SymbolInfo(
            code=symbol_code,
            name=row.get("name", symbol_code),
            market=row.get("market", "KOSPI"),
            sector=None,
            market_cap=None,
            is_in_universe=True,
        ),
        timeframe=row.get("timeframe", timeframe),
        timeframe_label=row.get("timeframe_label", timeframe_label(row.get("timeframe", timeframe))),
        stance=stance,
        stance_label=STANCE_LABELS[stance],
        score=round(score, 1),
        confidence=round(confidence, 3),
        source_category=_source_category(row),
        watchlist_priority=watched,
        summary=_summary(row, stance),
        action_line=_action_line(row, stance),
        do_now=_do_now(row, stance),
        avoid_if=_avoid_if(row),
        review_price=_review_price(row),
        skip_reason=_skip_reason(row, stance),
        overlap_risk="",
        reasons=_reasons(row),
        risk_flags=_risk_flags(row),
        next_actions=_next_actions(row, stance),
        position_hint=_position_hint(row, stance, watched),
        pattern_type=row.get("pattern_type"),
        state=row.get("state"),
        p_up=round(float(row.get("p_up", 0.0)), 4),
        p_down=round(float(row.get("p_down", 0.0)), 4),
        trade_readiness_score=round(float(row.get("trade_readiness_score", 0.0)), 4),
        entry_window_score=round(float(row.get("entry_window_score", 0.0)), 4),
        freshness_score=round(float(row.get("freshness_score", 0.0)), 4),
        reward_risk_ratio=round(float(row.get("reward_risk_ratio", 0.0)), 3),
        data_quality=round(float(row.get("data_quality", 0.0)), 4),
        confluence_score=round(float(row.get("confluence_score", 0.0)), 4),
        next_trigger=str(row.get("next_trigger", "") or ""),
        chart_path=f"/chart/{symbol_code}",
        personal_fit_score=personal_fit_score,
        personal_fit_label=personal_fit_label,
        personal_fit_reasons=personal_fit_reasons,
    )


def _watchlist_score_bonus(row: dict, watched: bool) -> float:
    if not watched:
        return 0.0

    bonus = 6.0
    if float(row.get("entry_window_score", 0.0)) >= 0.5:
        bonus += 2.0
    if float(row.get("trade_readiness_score", 0.0)) >= 0.55:
        bonus += 1.5
    if row.get("no_signal_flag") or row.get("action_plan") == "cooling":
        bonus -= 2.5
    return max(bonus, 1.5)


def _watchlist_focus_score(item: AiRecommendationItem) -> float:
    stance_bonus = {
        "priority_watch": 26.0,
        "wait_for_trigger": 18.0,
        "avoid_chase": 12.0,
        "risk_review": 20.0,
    }.get(item.stance, 0.0)
    risk_bonus = min(len(item.risk_flags) * 1.5, 6.0)
    return (
        stance_bonus
        + item.score * 0.45
        + item.personal_fit_score * 0.20
        + item.trade_readiness_score * 12.0
        + item.entry_window_score * 10.0
        + risk_bonus
    )


def _apply_overlap_risk(items: list[AiRecommendationItem]) -> None:
    pattern_counts = Counter(item.pattern_type or "none" for item in items)
    stance_counts = Counter(item.stance for item in items)
    watched_count = sum(1 for item in items if item.watchlist_priority)

    for item in items:
        messages: list[str] = []
        if item.pattern_type and pattern_counts[item.pattern_type] >= 3:
            messages.append(f"{item.pattern_type} 패턴 후보가 많아 같은 구조 노출이 겹칩니다.")
        if stance_counts[item.stance] >= 4:
            messages.append(f"{item.stance_label} 후보가 많아 비슷한 의사결정이 반복될 수 있습니다.")
        if item.watchlist_priority and watched_count >= 3:
            messages.append("관심종목이 여러 개라 동일한 방향으로 포지션이 몰릴 수 있습니다.")
        item.overlap_risk = " ".join(messages[:2])


def _recommendation_score(row: dict) -> float:
    p_up = float(row.get("p_up", 0.0))
    p_down = float(row.get("p_down", 0.0))
    edge = _clamp((p_up - p_down + 0.20) / 0.55)
    score = (
        0.20 * float(row.get("trade_readiness_score", 0.0))
        + 0.16 * float(row.get("entry_window_score", 0.0))
        + 0.12 * float(row.get("freshness_score", 0.0))
        + 0.10 * float(row.get("reentry_score", 0.0))
        + 0.10 * float(row.get("active_setup_score", 0.0))
        + 0.10 * float(row.get("historical_edge_score", 0.0))
        + 0.08 * float(row.get("confluence_score", 0.5))
        + 0.06 * float(row.get("data_quality", 0.0))
        + 0.04 * float(row.get("liquidity_score", 0.0))
        + 0.04 * edge
    )
    if row.get("no_signal_flag"):
        score -= 0.22
    if row.get("action_plan") == "cooling":
        score -= 0.12
    score -= min(len(row.get("risk_flags") or []) * 0.035, 0.14)
    return _clamp(score) * 100


def _confidence(row: dict) -> float:
    confidence = (
        0.35 * float(row.get("confidence", 0.0))
        + 0.25 * float(row.get("sample_reliability", 0.0))
        + 0.25 * float(row.get("data_quality", 0.0))
        + 0.15 * float(row.get("liquidity_score", 0.0))
    )
    return _clamp(confidence)


def _stance(row: dict, score: float) -> str:
    if row.get("no_signal_flag") or float(row.get("data_quality", 0.0)) < 0.38:
        return "risk_review"
    if row.get("action_plan") == "cooling":
        return "risk_review"
    if float(row.get("entry_window_score", 0.0)) < 0.34 and float(row.get("p_up", 0.0)) >= 0.58:
        return "avoid_chase"
    if score >= 68 and float(row.get("p_up", 0.0)) >= 0.55 and float(row.get("trade_readiness_score", 0.0)) >= 0.50:
        return "priority_watch"
    if score >= 52:
        return "wait_for_trigger"
    return "risk_review"


def _summary(row: dict, stance: str) -> str:
    name = row.get("name", row.get("code", "종목"))
    pattern = row.get("pattern_type") or "구조 미확인"
    readiness = row.get("trade_readiness_label") or "준비도 확인 필요"
    if stance == "priority_watch":
        return f"{name}은 {pattern} 구조가 살아 있고 {readiness} 구간이라 오늘 바로 체크할 후보입니다."
    if stance == "wait_for_trigger":
        return f"{name}은 구조는 유지되지만 아직 트리거 확인이 먼저인 대기 후보입니다."
    if stance == "avoid_chase":
        return f"{name}은 방향성은 좋지만 이미 앞서가 있어 추격 대신 눌림 확인이 더 중요합니다."
    return f"{name}은 지금은 방어적으로 봐야 하는 후보입니다. 리스크와 데이터 상태를 먼저 점검해야 합니다."


def _reasons(row: dict) -> list[str]:
    reasons = [
        f"상승 확률 {float(row.get('p_up', 0.0)) * 100:.1f}%, 하락 확률 {float(row.get('p_down', 0.0)) * 100:.1f}%",
        f"거래 준비도 {float(row.get('trade_readiness_score', 0.0)) * 100:.0f}%, 진입 구간 {float(row.get('entry_window_score', 0.0)) * 100:.0f}%",
        f"데이터 품질 {float(row.get('data_quality', 0.0)) * 100:.0f}%, 신뢰도 {float(row.get('confidence', 0.0)) * 100:.0f}%",
    ]
    if row.get("reason_summary"):
        reasons.append(str(row["reason_summary"]))
    elif row.get("confluence_summary"):
        reasons.append(str(row["confluence_summary"]))
    return reasons[:4]


def _do_now(row: dict, stance: str) -> str:
    trigger = str(row.get("next_trigger") or "").strip()
    if trigger:
        return f"{trigger} 확인 후 다시 평가"
    if stance == "priority_watch":
        return "핵심 가격대와 거래량 반응 확인"
    if stance == "avoid_chase":
        return "눌림 또는 지지 확인 전까지 대기"
    if stance == "risk_review":
        return "신규 진입보다 리스크 정리 우선"
    return "트리거 형성 전까지 관찰 유지"


def _avoid_if(row: dict) -> str:
    risk_flags = [str(flag) for flag in (row.get("risk_flags") or []) if flag]
    if risk_flags:
        return risk_flags[0]
    no_signal_reason = str(row.get("no_signal_reason") or "").strip()
    if no_signal_reason:
        return no_signal_reason
    if float(row.get("reward_risk_ratio", 0.0)) < 1.2:
        return "손익비가 낮아 비중 확대를 피해야 함"
    return "핵심 가격대 지지 확인 전 추격 금지"


def _review_price(row: dict) -> str:
    trigger = str(row.get("next_trigger") or "").strip()
    if trigger:
        return trigger
    entry_window = str(row.get("entry_window_summary") or "").strip()
    if entry_window:
        return entry_window
    reentry_trigger = str(row.get("reentry_trigger") or "").strip()
    if reentry_trigger:
        return reentry_trigger
    return "핵심 가격대가 다시 정렬될 때 재검토"


def _skip_reason(row: dict, stance: str) -> str:
    if stance == "priority_watch":
        return "이미 상위 우선 후보라 오늘 안 보낼 이유가 크지 않습니다."
    no_signal_reason = str(row.get("no_signal_reason") or "").strip()
    if no_signal_reason:
        return no_signal_reason
    if float(row.get("data_quality", 0.0)) < 0.45:
        return "데이터 품질이 낮아 오늘은 강하게 해석하지 않는 편이 낫습니다."
    if stance == "avoid_chase":
        return "가격이 먼저 달려서 눌림 없이 접근하면 기대값이 떨어집니다."
    return "트리거가 아직 완성되지 않아 서둘러 볼 이유가 약합니다."


def _action_line(row: dict, stance: str) -> str:
    return f"지금 할 일: {_do_now(row, stance)}"


def _risk_flags(row: dict) -> list[str]:
    flags = [str(flag) for flag in (row.get("risk_flags") or []) if flag]
    if row.get("trend_warning"):
        flags.append(str(row["trend_warning"]))
    if float(row.get("reward_risk_ratio", 0.0)) < 1.2:
        flags.append("손익비가 낮아 포지션 크기 축소가 필요합니다.")
    if row.get("no_signal_flag") and row.get("no_signal_reason"):
        flags.append(str(row["no_signal_reason"]))
    return flags[:5]


def _next_actions(row: dict, stance: str) -> list[str]:
    actions: list[str] = []
    actions.append(f"지금 할 일: {_do_now(row, stance)}")
    actions.append(f"진입 금지 조건: {_avoid_if(row)}")
    actions.append(f"다시 볼 가격: {_review_price(row)}")
    actions.append(f"오늘 안 봐도 되는 이유: {_skip_reason(row, stance)}")
    return actions[:4]


def _position_hint(row: dict, stance: str, watched: bool) -> str:
    head = "관심종목 우선 후보입니다. " if watched else ""
    if stance == "priority_watch":
        return f"{head}확인 신호가 나오면 대응하고, 무효화 기준은 미리 정해두는 쪽이 적절합니다."
    if stance == "wait_for_trigger":
        return f"{head}지금은 자리 선점보다 트리거 확인을 기다리는 단계입니다."
    if stance == "avoid_chase":
        return f"{head}가격이 앞서가 있으니 눌림이나 재지지 전까지는 보수적으로 보세요."
    return f"{head}지금은 방어적 판단이 우선입니다."


def _source_category(row: dict) -> str:
    if row.get("live_intraday_candidate"):
        return "live_intraday"
    if row.get("no_signal_flag"):
        return "risk_watch"
    if row.get("state") in {"armed", "confirmed"}:
        return "active_pattern"
    if row.get("state") == "forming":
        return "forming_pattern"
    return "scan_result"


def _market_brief(items: list[AiRecommendationItem], timeframe: str, watchlist_focus_items: list[AiRecommendationItem]) -> str:
    if not items:
        return f"{timeframe_label(timeframe)} 기준으로 아직 정리된 추천 후보가 없습니다."
    priority = sum(1 for item in items if item.stance == "priority_watch")
    watch = sum(1 for item in items if item.stance in {"wait_for_trigger", "avoid_chase"})
    risk = sum(1 for item in items if item.stance == "risk_review")
    watchlist_count = len(watchlist_focus_items)
    return (
        f"{timeframe_label(timeframe)} 기준으로 우선 검토 {priority}개, 대기 {watch}개, 리스크 점검 {risk}개입니다. "
        f"관심종목 우선 후보는 {watchlist_count}개입니다."
    )


def _portfolio_guidance(
    priority_items: list[AiRecommendationItem],
    watch_items: list[AiRecommendationItem],
    risk_items: list[AiRecommendationItem],
    watchlist_focus_items: list[AiRecommendationItem],
    personalized_items: list[AiRecommendationItem],
    personalization: dict | None,
) -> str:
    style = (personalization or {}).get("style_profile") or {}
    style_label = style.get("style_label")
    if personalized_items and style_label:
        lead = personalized_items[0]
        return (
            f"내 기록 기준 현재 운용 스타일은 {style_label}에 가깝습니다. "
            f"오늘은 {lead.symbol.name}처럼 내 스타일 적합도가 높은 후보부터 보는 편이 피로도가 낮습니다."
        )
    if watchlist_focus_items:
        lead = watchlist_focus_items[0]
        return (
            f"관심종목에서는 {lead.symbol.name}을 먼저 보세요. "
            "이미 들고 있거나 계속 추적하는 종목과 신규 후보가 같은 방향으로 겹치면 비중이 몰릴 수 있습니다."
        )
    if priority_items:
        lead = priority_items[0]
        return f"오늘은 {lead.symbol.name}처럼 준비도와 데이터 품질이 함께 맞는 후보부터 보는 편이 효율적입니다."
    if watch_items:
        lead = watch_items[0]
        return f"즉시 진입보다 {lead.symbol.name}처럼 트리거 확인이 필요한 후보가 많습니다. 기다리는 쪽이 낫습니다."
    if risk_items:
        return "리스크 점검 후보 비중이 높습니다. 신규 진입보다 무효화 기준과 데이터 상태를 먼저 정리하세요."
    return "추천 후보가 충분히 쌓이면 이 영역이 운용 가이드를 보여줍니다."


def _rerank(items: list[AiRecommendationItem]) -> list[AiRecommendationItem]:
    return [item.model_copy(update={"rank": index + 1}) for index, item in enumerate(items)]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
