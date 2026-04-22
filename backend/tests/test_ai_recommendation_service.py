from __future__ import annotations

from app.api.schemas import AiRecommendationItem, SymbolInfo
from app.services.ai_recommendation_service import _apply_overlap_risk


def _item(code: str, *, watched: bool) -> AiRecommendationItem:
    return AiRecommendationItem(
        rank=0,
        symbol=SymbolInfo(code=code, name=code, market="KOSPI", sector=None, market_cap=None, is_in_universe=True),
        timeframe="1d",
        timeframe_label="일봉",
        stance="priority_watch",
        stance_label="우선 검토",
        score=72.0,
        confidence=0.7,
        source_category="active_pattern",
        watchlist_priority=watched,
        summary="요약",
        action_line="지금 할 일: 확인",
        do_now="확인",
        avoid_if="무효화 이탈",
        review_price="트리거 재확인",
        skip_reason="트리거 미완성",
        overlap_risk="",
        reasons=["근거"],
        risk_flags=[],
        next_actions=["다음 행동"],
        position_hint="포지션 힌트",
        pattern_type="double_bottom",
        state="armed",
        p_up=0.6,
        p_down=0.4,
        trade_readiness_score=0.7,
        entry_window_score=0.6,
        freshness_score=0.5,
        reward_risk_ratio=1.5,
        data_quality=0.8,
        confluence_score=0.6,
        next_trigger="트리거 확인",
        chart_path=f"/chart/{code}",
    )


def test_overlap_risk_mentions_pattern_and_watchlist_crowding():
    items = [_item("005930", watched=True), _item("000660", watched=True), _item("035420", watched=True)]

    _apply_overlap_risk(items)

    assert "패턴 후보가 많아" in items[0].overlap_risk
    assert "관심종목이 여러 개" in items[0].overlap_risk
