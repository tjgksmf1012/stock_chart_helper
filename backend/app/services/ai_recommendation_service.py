"""Rule-based portfolio manager style recommendations from scan results."""

from __future__ import annotations

import asyncio
from datetime import datetime

from ..api.schemas import AiRecommendationItem, AiRecommendationResponse, SymbolInfo
from ..core.redis import cache_get, cache_set
from .openai_recommendation_service import apply_openai_recommendation_overlay
from .scanner import get_scan_results
from .timeframe_service import DEFAULT_TIMEFRAME, timeframe_label


DISCLAIMER = "투자 권유가 아닌 기술적 분석 보조 의견입니다. 실제 매매 전 재무, 뉴스, 수급, 손절 기준을 직접 확인하세요."

STANCE_LABELS = {
    "priority_watch": "우선 검토",
    "wait_for_trigger": "트리거 대기",
    "avoid_chase": "추격 금지",
    "risk_review": "리스크 점검",
}

_RECOMMENDATION_CACHE_PREFIX = "ai:recommendations:v1"
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
        rows = await get_scan_results(timeframe)
        ranked = [_make_recommendation(row, timeframe) for row in rows]
        ranked.sort(key=lambda item: (item.score, item.confidence, item.p_up - item.p_down), reverse=True)

        items = _rerank(ranked[:limit])
        priority_items = _rerank([item for item in ranked if item.stance == "priority_watch"][:limit])
        watch_items = _rerank([item for item in ranked if item.stance in {"wait_for_trigger", "avoid_chase"}][:limit])
        risk_items = _rerank(
            sorted(
                [item for item in ranked if item.stance == "risk_review"],
                key=lambda item: (len(item.risk_flags), 1 - item.data_quality, item.p_down),
                reverse=True,
            )[:limit]
        )

        response = AiRecommendationResponse(
            generated_at=datetime.utcnow().isoformat(),
            timeframe=timeframe,
            timeframe_label=timeframe_label(timeframe),
            market_brief=_market_brief(ranked, timeframe),
            portfolio_guidance=_portfolio_guidance(priority_items, watch_items, risk_items),
            items=items,
            priority_items=priority_items,
            watch_items=watch_items,
            risk_items=risk_items,
            disclaimer=DISCLAIMER,
        )
        response = await apply_openai_recommendation_overlay(response)
        await cache_set(cache_key, response.model_dump(mode="json"), ttl=45)
        return response
    finally:
        _IN_FLIGHT_RECOMMENDATIONS.discard(cache_key)


def _make_recommendation(row: dict, timeframe: str) -> AiRecommendationItem:
    score = _recommendation_score(row)
    confidence = _confidence(row)
    stance = _stance(row, score)
    symbol_code = row["code"]
    reasons = _reasons(row, score)
    next_actions = _next_actions(row, stance)

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
        summary=_summary(row, stance, score),
        reasons=reasons,
        risk_flags=_risk_flags(row),
        next_actions=next_actions,
        position_hint=_position_hint(row, stance, score),
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
        next_trigger=row.get("next_trigger", ""),
        chart_path=f"/chart/{symbol_code}",
    )


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


def _summary(row: dict, stance: str, score: float) -> str:
    name = row.get("name", row.get("code", "종목"))
    pattern = row.get("pattern_type") or "명확한 패턴 없음"
    readiness = row.get("trade_readiness_label") or "준비도 확인 필요"
    if stance == "priority_watch":
        return f"{name}은 {pattern} 구조와 {readiness}가 함께 들어와 우선 관찰 후보입니다."
    if stance == "wait_for_trigger":
        return f"{name}은 점수 {score:.0f}점으로 구조는 살아 있지만 확인 트리거를 기다리는 편이 좋습니다."
    if stance == "avoid_chase":
        return f"{name}은 방향성은 보이나 진입 구간 점수가 낮아 추격보다 눌림 확인이 우선입니다."
    return f"{name}은 현재 데이터 품질, 손익비, 리스크 플래그를 먼저 점검해야 합니다."


def _reasons(row: dict, score: float) -> list[str]:
    reasons = [
        f"상승확률 {float(row.get('p_up', 0.0)) * 100:.1f}%, 하락확률 {float(row.get('p_down', 0.0)) * 100:.1f}%",
        f"거래준비도 {float(row.get('trade_readiness_score', 0.0)) * 100:.0f}%, 진입구간 {float(row.get('entry_window_score', 0.0)) * 100:.0f}%",
        f"데이터 품질 {float(row.get('data_quality', 0.0)) * 100:.0f}%, 신뢰도 {float(row.get('confidence', 0.0)) * 100:.0f}%",
    ]
    if row.get("reason_summary"):
        reasons.append(str(row["reason_summary"]))
    elif row.get("confluence_summary"):
        reasons.append(str(row["confluence_summary"]))
    return reasons[:4]


def _risk_flags(row: dict) -> list[str]:
    flags = [str(flag) for flag in (row.get("risk_flags") or []) if flag]
    if row.get("trend_warning"):
        flags.append(str(row["trend_warning"]))
    if float(row.get("reward_risk_ratio", 0.0)) < 1.2:
        flags.append("손익비가 낮아 포지션 크기 축소 필요")
    if row.get("no_signal_flag") and row.get("no_signal_reason"):
        flags.append(str(row["no_signal_reason"]))
    return flags[:5]


def _next_actions(row: dict, stance: str) -> list[str]:
    actions: list[str] = []
    if row.get("next_trigger"):
        actions.append(str(row["next_trigger"]))
    actions.extend(str(item) for item in (row.get("confirmation_checklist") or [])[:3] if item)
    if stance == "priority_watch":
        actions.append("돌파 확인 전에는 분할 관찰, 확인 후에도 손절 기준을 먼저 고정")
    elif stance == "avoid_chase":
        actions.append("현재가 추격보다 재테스트, 거래량 회복, 지지 확인을 기다림")
    elif stance == "risk_review":
        actions.append("신호가 다시 정렬될 때까지 관망 후보로 분류")
    else:
        actions.append("트리거 충족 전에는 관심종목에만 보관")
    return actions[:5]


def _position_hint(row: dict, stance: str, score: float) -> str:
    if stance == "priority_watch" and score >= 76:
        return "강한 후보지만 확정 신호와 손절선을 동시에 확인하세요."
    if stance == "priority_watch":
        return "우선 관찰 후보입니다. 진입은 확인 트리거 이후가 적합합니다."
    if stance == "wait_for_trigger":
        return "관심종목에 두고 트리거가 맞을 때만 다시 평가하세요."
    if stance == "avoid_chase":
        return "가격이 앞서간 구간입니다. 눌림이나 재테스트 전에는 보수적으로 보세요."
    return "현재는 방어적 판단이 우선입니다."


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


def _market_brief(items: list[AiRecommendationItem], timeframe: str) -> str:
    if not items:
        return f"{timeframe_label(timeframe)} 기준으로 평가할 스캔 결과가 아직 없습니다."
    priority = sum(1 for item in items if item.stance == "priority_watch")
    watch = sum(1 for item in items if item.stance in {"wait_for_trigger", "avoid_chase"})
    risk = sum(1 for item in items if item.stance == "risk_review")
    avg_score = sum(item.score for item in items) / len(items)
    return f"{timeframe_label(timeframe)} 스캔에서 우선 검토 {priority}개, 트리거 대기 {watch}개, 리스크 점검 {risk}개가 잡혔고 평균 운용 점수는 {avg_score:.0f}점입니다."


def _portfolio_guidance(
    priority_items: list[AiRecommendationItem],
    watch_items: list[AiRecommendationItem],
    risk_items: list[AiRecommendationItem],
) -> str:
    if priority_items:
        top = priority_items[0]
        return f"오늘은 {top.symbol.name}처럼 준비도와 데이터 품질이 같이 맞는 후보를 먼저 보되, 같은 업종/동일 방향 후보를 과하게 겹치지 않는 구성이 좋습니다."
    if watch_items:
        top = watch_items[0]
        return f"즉시 매수 후보보다 {top.symbol.name} 같은 트리거 대기 후보가 많습니다. 돌파, 거래량, 재테스트가 맞기 전까지는 현금 비중을 남겨두는 쪽이 낫습니다."
    if risk_items:
        return "리스크 점검 후보 비중이 높습니다. 지금은 공격보다 관망, 손절 기준 재정리, 데이터 품질 확인이 우선입니다."
    return "충분한 후보가 아직 없습니다. 스캔이 끝난 뒤 다시 평가하세요."


def _rerank(items: list[AiRecommendationItem]) -> list[AiRecommendationItem]:
    return [item.model_copy(update={"rank": index + 1}) for index, item in enumerate(items)]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
