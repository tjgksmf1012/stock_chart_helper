"""Dashboard API for ranked market scan views and scan status controls."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from ..schemas import DashboardItem, DashboardOverviewResponse, DashboardResponse, ScanStatusResponse, SymbolInfo
from ...services.scanner import get_scan_results, get_scan_status, trigger_scan
from ...services.timeframe_service import DEFAULT_TIMEFRAME, timeframe_label

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _make_item(rank: int, row: dict) -> DashboardItem:
    return DashboardItem(
        rank=rank,
        symbol=SymbolInfo(
            code=row["code"],
            name=row["name"],
            market=row.get("market", "KOSPI"),
            sector=None,
            market_cap=None,
            is_in_universe=True,
        ),
        timeframe=row.get("timeframe", DEFAULT_TIMEFRAME),
        timeframe_label=row.get("timeframe_label", timeframe_label(row.get("timeframe", DEFAULT_TIMEFRAME))),
        pattern_type=row.get("pattern_type"),
        state=row.get("state"),
        setup_stage=row.get("setup_stage", "neutral"),
        p_up=row["p_up"],
        p_down=row["p_down"],
        textbook_similarity=row["textbook_similarity"],
        formation_quality=row.get("formation_quality", 0.0),
        leg_balance_fit=row.get("leg_balance_fit", 0.0),
        reversal_energy_fit=row.get("reversal_energy_fit", 0.0),
        breakout_quality_fit=row.get("breakout_quality_fit", 0.0),
        retest_quality_fit=row.get("retest_quality_fit", 0.0),
        confidence=row["confidence"],
        entry_score=row["entry_score"],
        reward_risk_ratio=row.get("reward_risk_ratio", 0.0),
        headroom_score=row.get("headroom_score", 0.0),
        target_distance_pct=row.get("target_distance_pct", 0.0),
        stop_distance_pct=row.get("stop_distance_pct", 0.0),
        avg_mfe_pct=row.get("avg_mfe_pct", 0.0),
        avg_mae_pct=row.get("avg_mae_pct", 0.0),
        avg_bars_to_outcome=row.get("avg_bars_to_outcome", 0.0),
        historical_edge_score=row.get("historical_edge_score", 0.0),
        trend_alignment_score=row.get("trend_alignment_score", 0.0),
        trend_direction=row.get("trend_direction", "sideways"),
        trend_warning=row.get("trend_warning", ""),
        action_plan=row.get("action_plan", "watch"),
        action_plan_label=row.get("action_plan_label", "관찰 후보"),
        action_plan_summary=row.get("action_plan_summary", ""),
        action_priority_score=row.get("action_priority_score", 0.0),
        risk_flags=row.get("risk_flags", []),
        confirmation_checklist=row.get("confirmation_checklist", []),
        next_trigger=row.get("next_trigger", ""),
        trade_readiness_score=row.get("trade_readiness_score", 0.0),
        trade_readiness_label=row.get("trade_readiness_label", "보류"),
        trade_readiness_summary=row.get("trade_readiness_summary", ""),
        entry_window_score=row.get("entry_window_score", 0.0),
        entry_window_label=row.get("entry_window_label", "재확인 필요"),
        entry_window_summary=row.get("entry_window_summary", ""),
        freshness_score=row.get("freshness_score", 0.0),
        freshness_label=row.get("freshness_label", "재확인 필요"),
        freshness_summary=row.get("freshness_summary", ""),
        reentry_score=row.get("reentry_score", 0.0),
        reentry_label=row.get("reentry_label", "재확인 필요"),
        reentry_summary=row.get("reentry_summary", ""),
        reentry_case=row.get("reentry_case", "none"),
        reentry_case_label=row.get("reentry_case_label", "구조 없음"),
        reentry_trigger=row.get("reentry_trigger", ""),
        reentry_compression_score=row.get("reentry_compression_score", 0.0),
        reentry_volume_recovery_score=row.get("reentry_volume_recovery_score", 0.0),
        reentry_trigger_hold_score=row.get("reentry_trigger_hold_score", 0.0),
        reentry_wick_absorption_score=row.get("reentry_wick_absorption_score", 0.0),
        reentry_failure_burden_score=row.get("reentry_failure_burden_score", 0.0),
        reentry_factors=row.get("reentry_factors", []),
        score_factors=row.get("score_factors", []),
        active_setup_score=row.get("active_setup_score", 0.0),
        active_setup_label=row.get("active_setup_label", "활성 셋업 없음"),
        active_setup_summary=row.get("active_setup_summary", ""),
        active_pattern_count=row.get("active_pattern_count", 0),
        completed_pattern_count=row.get("completed_pattern_count", 0),
        no_signal_flag=row["no_signal_flag"],
        reason_summary=row["reason_summary"],
        completion_proximity=row.get("completion_proximity", 0.0),
        recency_score=row.get("recency_score", 0.0),
        data_source=row.get("data_source", "unknown"),
        data_quality=row.get("data_quality", 0.0),
        source_note=row.get("source_note", ""),
        fetch_status=row.get("fetch_status", "unknown"),
        fetch_status_label=row.get("fetch_status_label", "상태 정보 없음"),
        fetch_message=row.get("fetch_message", ""),
        liquidity_score=row.get("liquidity_score", 0.0),
        avg_turnover_billion=row.get("avg_turnover_billion", 0.0),
        sample_size=row.get("sample_size", 0),
        empirical_win_rate=row.get("empirical_win_rate", 0.5),
        sample_reliability=row.get("sample_reliability", 0.0),
        stats_timeframe=row.get("stats_timeframe", "1d"),
        available_bars=row.get("available_bars", 0),
        confluence_score=row.get("confluence_score", 0.0),
        confluence_summary=row.get("confluence_summary", ""),
        scenario_text=row.get("scenario_text", ""),
        live_intraday_candidate=row.get("live_intraday_candidate", False),
        live_intraday_priority_score=row.get("live_intraday_priority_score", 0.0),
        live_intraday_reason=row.get("live_intraday_reason", ""),
        non_live_intraday_reason=row.get("non_live_intraday_reason", ""),
        intraday_collection_mode=row.get("intraday_collection_mode", "budget"),
    )


def _response(category: str, timeframe: str, items: list[DashboardItem]) -> DashboardResponse:
    return DashboardResponse(
        category=category,
        timeframe=timeframe,
        timeframe_label=timeframe_label(timeframe),
        items=items,
        generated_at=datetime.utcnow().isoformat(),
    )


def _timeframe_query(timeframe: str) -> str:
    return timeframe or DEFAULT_TIMEFRAME


def _placeholder_rows(data: list[dict], limit: int) -> list[dict]:
    placeholders = [row for row in data if row.get("fetch_status") == "placeholder_pending"]
    placeholders.sort(
        key=lambda row: (
            row.get("composite_score", 0.0),
            row.get("data_quality", 0.0),
            row.get("liquidity_score", 0.0),
            row.get("symbol_rank_hint", 0.0),
        ),
        reverse=True,
    )
    return placeholders[:limit]


def _resolve_ranked_rows(ranked: list[dict], data: list[dict], limit: int, *, allow_placeholder: bool = False) -> list[dict]:
    if ranked or not allow_placeholder:
        return ranked[:limit]
    return _placeholder_rows(data, limit)


def _allow_placeholder(timeframe: str) -> bool:
    return timeframe in {"1m", "15m", "30m", "60m"}


def _long_response(timeframe: str, data: list[dict], limit: int) -> DashboardResponse:
    ranked = [row for row in data if not row["no_signal_flag"] and row["p_up"] > 0.55 and row.get("action_plan") != "cooling"]
    ranked.sort(
        key=lambda row: (
            row.get("trade_readiness_score", 0.0),
            row.get("entry_window_score", 0.0),
            row.get("freshness_score", 0.0),
            row.get("reentry_score", 0.0),
            row.get("active_setup_score", 0.0),
            row.get("composite_score", row["entry_score"]),
            row.get("historical_edge_score", 0.0),
            row["data_quality"],
            row["liquidity_score"],
        ),
        reverse=True,
    )
    ranked = _resolve_ranked_rows(ranked, data, limit, allow_placeholder=_allow_placeholder(timeframe))
    return _response("long_high_probability", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked)])


def _short_response(timeframe: str, data: list[dict], limit: int) -> DashboardResponse:
    ranked = [row for row in data if not row["no_signal_flag"] and row["p_down"] > 0.55 and row.get("action_plan") != "cooling"]
    ranked.sort(
        key=lambda row: (
            row.get("trade_readiness_score", 0.0),
            row.get("entry_window_score", 0.0),
            row.get("freshness_score", 0.0),
            row.get("reentry_score", 0.0),
            row.get("active_setup_score", 0.0),
            row.get("composite_score", row["p_down"]),
            row.get("historical_edge_score", 0.0),
            row["data_quality"],
            row["liquidity_score"],
        ),
        reverse=True,
    )
    ranked = _resolve_ranked_rows(ranked, data, limit, allow_placeholder=_allow_placeholder(timeframe))
    return _response("short_high_probability", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked)])


def _similarity_response(timeframe: str, data: list[dict], limit: int) -> DashboardResponse:
    ranked = sorted(
        data,
        key=lambda row: (
            row.get("trade_readiness_score", 0.0),
            row.get("entry_window_score", 0.0),
            row.get("freshness_score", 0.0),
            row.get("reentry_score", 0.0),
            row.get("active_setup_score", 0.0),
            row["textbook_similarity"],
            row.get("historical_edge_score", 0.0),
            row.get("confluence_score", 0.5),
            row["recency_score"],
        ),
        reverse=True,
    )
    ranked = _resolve_ranked_rows(ranked, data, limit, allow_placeholder=_allow_placeholder(timeframe))
    return _response("high_textbook_similarity", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked)])


def _no_signal_response(timeframe: str, data: list[dict], limit: int) -> DashboardResponse:
    ranked = [row for row in data if row["no_signal_flag"]]
    ranked.sort(key=lambda row: (row["data_quality"], row.get("historical_edge_score", 0.0), row["available_bars"]), reverse=True)
    return _response("watchlist_no_signal", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])])


def _armed_response(timeframe: str, data: list[dict], limit: int) -> DashboardResponse:
    ranked = [
        row for row in data
        if row.get("state") in ("armed", "forming") and row["textbook_similarity"] >= 0.5
    ]
    ranked.sort(
        key=lambda row: (
            row.get("trade_readiness_score", 0.0),
            row.get("entry_window_score", 0.0),
            row.get("freshness_score", 0.0),
            row.get("reentry_score", 0.0),
            row.get("active_setup_score", 0.0),
            row["completion_proximity"],
            row.get("historical_edge_score", 0.0),
            row.get("confluence_score", 0.5),
            row["recency_score"],
        ),
        reverse=True,
    )
    ranked = _resolve_ranked_rows(ranked, data, limit, allow_placeholder=_allow_placeholder(timeframe))
    return _response("pattern_armed", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked)])


def _forming_response(timeframe: str, data: list[dict], limit: int) -> DashboardResponse:
    ranked = [
        row for row in data
        if row.get("state") == "forming"
        and row.get("formation_quality", 0.0) >= 0.42
        and row.get("textbook_similarity", 0.0) >= 0.45
    ]
    ranked.sort(
        key=lambda row: (
            row.get("trade_readiness_score", 0.0),
            row.get("entry_window_score", 0.0),
            row.get("reentry_score", 0.0),
            row.get("active_setup_score", 0.0),
            0.34 * row.get("completion_proximity", 0.0)
            + 0.24 * row.get("formation_quality", 0.0)
            + 0.18 * row.get("confluence_score", 0.5)
            + 0.12 * row.get("trend_alignment_score", 0.0)
            + 0.12 * row.get("recency_score", 0.0),
            row.get("historical_edge_score", 0.0),
            row.get("data_quality", 0.0),
        ),
        reverse=True,
    )
    ranked = _resolve_ranked_rows(ranked, data, limit, allow_placeholder=_allow_placeholder(timeframe))
    return _response("forming_candidates", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked)])


async def _live_intraday_response(timeframe: str, data: list[dict], limit: int, *, status: dict | None = None) -> DashboardResponse:
    status = status or await get_scan_status(timeframe)
    if _allow_placeholder(timeframe) and (status.get("cached_result_count") or 0) == 0:
        if not status.get("is_running"):
            await trigger_scan(timeframe=timeframe, force_refresh=False, source="background")
        placeholders = _placeholder_rows(data, limit)
        return _response("live_intraday_candidates", timeframe, [_make_item(index + 1, row) for index, row in enumerate(placeholders)])

    ranked = [
        row for row in data
        if row.get("fetch_status") in {"live_ok", "live_augmented_by_store"}
    ]
    ranked = _resolve_ranked_rows(ranked, data, limit, allow_placeholder=_allow_placeholder(timeframe))
    ranked.sort(
        key=lambda row: (
            row.get("trade_readiness_score", 0.0),
            row.get("entry_window_score", 0.0),
            row.get("reentry_score", 0.0),
            row.get("active_setup_score", 0.0),
            row.get("composite_score", row.get("entry_score", 0.0)),
            row.get("historical_edge_score", 0.0),
            row.get("completion_proximity", 0.0),
            row.get("liquidity_score", 0.0),
        ),
        reverse=True,
    )
    return _response("live_intraday_candidates", timeframe, [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])])


@router.get("/scan-status", response_model=ScanStatusResponse)
async def dashboard_scan_status(timeframe: str = Query(default=DEFAULT_TIMEFRAME)) -> ScanStatusResponse:
    return ScanStatusResponse(**(await get_scan_status(_timeframe_query(timeframe))))


@router.post("/scan-refresh", response_model=ScanStatusResponse)
async def dashboard_scan_refresh(timeframe: str = Query(default=DEFAULT_TIMEFRAME)) -> ScanStatusResponse:
    return ScanStatusResponse(**(await trigger_scan(timeframe=_timeframe_query(timeframe), force_refresh=True, source="manual")))


@router.get("/long-high-probability")
async def dashboard_long(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    return _long_response(timeframe, data, limit)


@router.get("/short-high-probability")
async def dashboard_short(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    return _short_response(timeframe, data, limit)


@router.get("/high-textbook-similarity")
async def dashboard_similarity(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    return _similarity_response(timeframe, data, limit)


@router.get("/watchlist-no-signal")
async def dashboard_no_signal(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    return _no_signal_response(timeframe, data, limit)


@router.get("/pattern-armed")
async def dashboard_armed(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    return _armed_response(timeframe, data, limit)


@router.get("/forming-candidates")
async def dashboard_forming(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    return _forming_response(timeframe, data, limit)


@router.get("/live-intraday-candidates")
async def dashboard_live_intraday(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardResponse:
    timeframe = _timeframe_query(timeframe)
    data = await get_scan_results(timeframe)
    status = await get_scan_status(timeframe)
    return await _live_intraday_response(timeframe, data, limit, status=status)


@router.get("/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=10, le=50),
) -> DashboardOverviewResponse:
    timeframe = _timeframe_query(timeframe)
    status = await get_scan_status(timeframe)
    data = await get_scan_results(timeframe)

    return DashboardOverviewResponse(
        timeframe=timeframe,
        timeframe_label=timeframe_label(timeframe),
        generated_at=datetime.utcnow().isoformat(),
        long_high_probability=_long_response(timeframe, data, limit),
        pattern_armed=_armed_response(timeframe, data, limit),
        live_intraday_candidates=await _live_intraday_response(timeframe, data, limit, status=status),
        forming_candidates=_forming_response(timeframe, data, limit),
        high_textbook_similarity=_similarity_response(timeframe, data, limit),
        short_high_probability=_short_response(timeframe, data, limit),
        watchlist_no_signal=_no_signal_response(timeframe, data, limit),
    )
