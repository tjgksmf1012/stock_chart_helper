"""Dashboard API for ranked market scan views and scan status controls."""

from datetime import datetime

from fastapi import APIRouter, Query

from ..schemas import DashboardItem, DashboardResponse, ScanStatusResponse, SymbolInfo
from ...services.scanner import get_scan_results, get_scan_status, trigger_scan
from ...services.timeframe_service import DEFAULT_TIMEFRAME, SUPPORTED_TIMEFRAMES, timeframe_label

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _quality_weight(row: dict) -> float:
    return float(row.get("data_quality") or 0.0)


def _liquidity_weight(row: dict) -> float:
    return max(0.25, float(row.get("liquidity_score") or 0.0))


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
        timeframe=row.get("timeframe"),
        timeframe_label=row.get("timeframe_label"),
        data_source=row.get("data_source"),
        data_quality=row.get("data_quality", 0.0),
        source_note=row.get("source_note"),
        fetch_status=row.get("fetch_status"),
        fetch_message=row.get("fetch_message"),
        pattern_type=row.get("pattern_type"),
        state=row.get("state"),
        p_up=row["p_up"],
        p_down=row["p_down"],
        textbook_similarity=row["textbook_similarity"],
        confidence=row["confidence"],
        entry_score=row["entry_score"],
        completion_proximity=row.get("completion_proximity", 0.0),
        recency_score=row.get("recency_score", 0.0),
        bars_since_signal=row.get("bars_since_signal"),
        liquidity_score=row.get("liquidity_score", 0.0),
        avg_turnover_billion=row.get("avg_turnover_billion", 0.0),
        no_signal_flag=row["no_signal_flag"],
        reason_summary=row["reason_summary"],
        sample_size=row.get("sample_size"),
        stats_timeframe=row.get("stats_timeframe"),
        available_bars=row.get("available_bars", 0),
    )


def _response(category: str, timeframe: str, items: list[DashboardItem]) -> DashboardResponse:
    return DashboardResponse(
        category=category,
        timeframe=timeframe,
        timeframe_label=timeframe_label(timeframe),
        items=items,
        generated_at=datetime.utcnow().isoformat(),
    )


def _validated_timeframe(timeframe: str) -> str:
    if timeframe not in SUPPORTED_TIMEFRAMES:
        return DEFAULT_TIMEFRAME
    return timeframe


@router.get("/scan-status", response_model=ScanStatusResponse)
async def dashboard_scan_status(timeframe: str = Query(default=DEFAULT_TIMEFRAME)) -> ScanStatusResponse:
    timeframe = _validated_timeframe(timeframe)
    return ScanStatusResponse(**(await get_scan_status(timeframe=timeframe)))


@router.post("/scan-refresh", response_model=ScanStatusResponse)
async def dashboard_scan_refresh(timeframe: str = Query(default=DEFAULT_TIMEFRAME)) -> ScanStatusResponse:
    timeframe = _validated_timeframe(timeframe)
    return ScanStatusResponse(**(await trigger_scan(force_refresh=True, source="manual", timeframe=timeframe)))


@router.get("/long-high-probability")
async def dashboard_long(
    limit: int = Query(default=10, le=50),
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> DashboardResponse:
    timeframe = _validated_timeframe(timeframe)
    data = await get_scan_results(timeframe=timeframe)
    ranked = [row for row in data if not row["no_signal_flag"] and row["p_up"] > 0.55]
    ranked.sort(key=lambda row: row["entry_score"] * _quality_weight(row) * _liquidity_weight(row), reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("long_high_probability", timeframe, items)


@router.get("/short-high-probability")
async def dashboard_short(
    limit: int = Query(default=10, le=50),
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> DashboardResponse:
    timeframe = _validated_timeframe(timeframe)
    data = await get_scan_results(timeframe=timeframe)
    ranked = [row for row in data if not row["no_signal_flag"] and row["p_down"] > 0.55]
    ranked.sort(key=lambda row: row["p_down"] * _quality_weight(row) * _liquidity_weight(row), reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("short_high_probability", timeframe, items)


@router.get("/high-textbook-similarity")
async def dashboard_similarity(
    limit: int = Query(default=10, le=50),
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> DashboardResponse:
    timeframe = _validated_timeframe(timeframe)
    data = await get_scan_results(timeframe=timeframe)
    ranked = sorted(data, key=lambda row: row["textbook_similarity"] * _quality_weight(row) * _liquidity_weight(row), reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("high_textbook_similarity", timeframe, items)


@router.get("/watchlist-no-signal")
async def dashboard_no_signal(
    limit: int = Query(default=10, le=50),
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> DashboardResponse:
    timeframe = _validated_timeframe(timeframe)
    data = await get_scan_results(timeframe=timeframe)
    ranked = [row for row in data if row["no_signal_flag"]]
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("watchlist_no_signal", timeframe, items)


@router.get("/pattern-armed")
async def dashboard_armed(
    limit: int = Query(default=10, le=50),
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> DashboardResponse:
    timeframe = _validated_timeframe(timeframe)
    data = await get_scan_results(timeframe=timeframe)
    ranked = [
        row
        for row in data
        if row.get("state") in ("armed", "forming", "confirmed") and row["completion_proximity"] >= 0.45
    ]
    ranked.sort(
        key=lambda row: (
            row["completion_proximity"] * _quality_weight(row),
            row["textbook_similarity"] * _quality_weight(row) * _liquidity_weight(row),
        ),
        reverse=True,
    )
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("pattern_armed", timeframe, items)
