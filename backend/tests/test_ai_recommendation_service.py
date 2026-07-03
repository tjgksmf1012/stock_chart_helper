from __future__ import annotations

from app.api.schemas import AiRecommendationItem, SymbolInfo
from app.services.ai_recommendation_service import _apply_overlap_risk, _stance, _watchlist_score_bonus


class TestStanceSoftAnd:
    """Regression: priority_watch used to require score>=68 AND p_up>=0.55 AND
    trade_readiness_score>=0.50 all simultaneously -- missing any one by a hair (e.g.
    p_up=0.549) demoted an objectively excellent candidate to 'wait_for_trigger'.
    """

    def test_all_three_comfortably_above_threshold_is_priority_watch(self):
        row = {"p_up": 0.70, "trade_readiness_score": 0.70, "entry_window_score": 0.6, "data_quality": 0.9}
        assert _stance(row, score=75.0) == "priority_watch"

    def test_one_factor_just_under_old_threshold_can_still_be_priority_watch(self):
        # p_up just below the old hard 0.55 cutoff, but score and readiness are strong.
        row = {"p_up": 0.549, "trade_readiness_score": 0.90, "entry_window_score": 0.6, "data_quality": 0.9}
        assert _stance(row, score=95.0) == "priority_watch"

    def test_all_three_weak_is_not_priority_watch(self):
        row = {"p_up": 0.40, "trade_readiness_score": 0.35, "entry_window_score": 0.4, "data_quality": 0.9}
        assert _stance(row, score=55.0) != "priority_watch"

    def test_one_factor_very_weak_is_not_rescued_by_the_others(self):
        # trade_readiness is essentially zero -- shouldn't be masked by a high score/p_up.
        row = {"p_up": 0.90, "trade_readiness_score": 0.05, "entry_window_score": 0.6, "data_quality": 0.9}
        assert _stance(row, score=90.0) != "priority_watch"


class TestWatchlistScoreBonusFloor:
    """The healthy-path floor (max(bonus, 1.5)) is meant to guarantee watchlisted
    stocks at least a small bump; it must not apply once the no_signal_flag/cooling
    penalty has been subtracted, or that floor would partially undo the penalty.
    """

    def test_healthy_watchlisted_stock_gets_the_base_bonus(self):
        row = {"entry_window_score": 0.1, "trade_readiness_score": 0.1}
        assert _watchlist_score_bonus(row, watched=True) == 6.0

    def test_no_signal_watchlisted_stock_gets_the_full_penalty_no_extra_floor(self):
        row = {"entry_window_score": 0.1, "trade_readiness_score": 0.1, "no_signal_flag": True}
        # base 6.0 - 2.5 penalty = 3.5, not re-floored up to the healthy-path 1.5+ floor
        # (which wouldn't bind here anyway, but the penalty branch must not apply it).
        assert _watchlist_score_bonus(row, watched=True) == 3.5

    def test_cooling_watchlisted_stock_gets_the_full_penalty_no_extra_floor(self):
        row = {"entry_window_score": 0.1, "trade_readiness_score": 0.1, "action_plan": "cooling"}
        assert _watchlist_score_bonus(row, watched=True) == 3.5

    def test_unwatched_stock_always_gets_zero(self):
        assert _watchlist_score_bonus({"no_signal_flag": True}, watched=False) == 0.0


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
        action_line="지금 할 일: 트리거 확인 후 재평가",
        do_now="트리거 확인",
        avoid_if="무효화선 이탈",
        review_price="트리거 가격 확인",
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


class TestOverlayCacheKey:
    """오버레이 캐시 키 안정성 — 점수 소수점 흔들림에 키가 바뀌면 안 된다."""

    @staticmethod
    def _payload(score: float, codes: tuple[str, ...] = ("282330", "032830")) -> dict:
        return {
            "timeframe": "1d",
            "items": [
                {"symbol_code": code, "stance": "priority_watch", "score": score,
                 "p_up": 0.59 + score / 1000, "trade_readiness": 0.7}
                for code in codes
            ],
        }

    def test_stable_within_score_band(self):
        from app.services.openai_recommendation_service import _overlay_cache_key

        # 같은 10점 밴드(50~59.9) 안에서는 키가 같아야 함 — 스캔마다 흔들리는
        # 소수점이 키를 바꾸면 캐시가 영원히 miss돼 항상 'refreshing'으로 보인다
        assert _overlay_cache_key(self._payload(53.2)) == _overlay_cache_key(self._payload(57.9))

    def test_changes_on_band_or_lineup_change(self):
        from app.services.openai_recommendation_service import _overlay_cache_key

        base = _overlay_cache_key(self._payload(53.2))
        assert _overlay_cache_key(self._payload(63.0)) != base          # 밴드 변경
        assert _overlay_cache_key(self._payload(53.2, ("282330",))) != base  # 라인업 변경


class TestRefreshInFlight:
    """고아 refreshing 플래그 판별 — 재시작으로 죽은 태스크의 플래그는 무시."""

    def test_fresh_attempt_is_in_flight(self):
        from datetime import datetime

        from app.services.openai_recommendation_service import _refresh_in_flight

        assert _refresh_in_flight({"refreshing": True, "last_attempt_at": datetime.utcnow().isoformat()}) is True

    def test_orphaned_flag_is_ignored(self):
        from datetime import datetime, timedelta

        from app.services.openai_recommendation_service import _refresh_in_flight

        old = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        assert _refresh_in_flight({"refreshing": True, "last_attempt_at": old}) is False

    def test_no_flag(self):
        from app.services.openai_recommendation_service import _refresh_in_flight

        assert _refresh_in_flight({}) is False
