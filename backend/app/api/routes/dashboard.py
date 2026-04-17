"""Dashboard API for ranked market scan views and scan status controls."""

from datetime import datetime

from fastapi import APIRouter, Query

from ..schemas import DashboardItem, DashboardResponse, ScanStatusResponse, SymbolInfo
from ...services.scanner import get_scan_results, get_scan_status, trigger_scan

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
        pattern_type=row.get("pattern_type"),
        state=row.get("state"),
        p_up=row["p_up"],
        p_down=row["p_down"],
        textbook_similarity=row["textbook_similarity"],
        confidence=row["confidence"],
        entry_score=row["entry_score"],
        no_signal_flag=row["no_signal_flag"],
        reason_summary=row["reason_summary"],
    )


def _response(category: str, items: list[DashboardItem]) -> DashboardResponse:
    return DashboardResponse(
        category=category,
        items=items,
        generated_at=datetime.utcnow().isoformat(),
    )


@router.get("/scan-status", response_model=ScanStatusResponse)
async def dashboard_scan_status() -> ScanStatusResponse:
    return ScanStatusResponse(**(await get_scan_status()))


@router.post("/scan-refresh", response_model=ScanStatusResponse)
async def dashboard_scan_refresh() -> ScanStatusResponse:
    return ScanStatusResponse(**(await trigger_scan(force_refresh=True, source="manual")))


@router.get("/long-high-probability")
async def dashboard_long(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await get_scan_results()
    ranked = [row for row in data if not row["no_signal_flag"] and row["p_up"] > 0.55]
    ranked.sort(key=lambda row: row["entry_score"], reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("long_high_probability", items)


@router.get("/short-high-probability")
async def dashboard_short(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await get_scan_results()
    ranked = [row for row in data if not row["no_signal_flag"] and row["p_down"] > 0.55]
    ranked.sort(key=lambda row: row["p_down"], reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("short_high_probability", items)


@router.get("/high-textbook-similarity")
async def dashboard_similarity(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await get_scan_results()
    ranked = sorted(data, key=lambda row: row["textbook_similarity"], reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("high_textbook_similarity", items)


@router.get("/watchlist-no-signal")
async def dashboard_no_signal(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await get_scan_results()
    ranked = [row for row in data if row["no_signal_flag"]]
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("watchlist_no_signal", items)


@router.get("/pattern-armed")
async def dashboard_armed(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await get_scan_results()
    ranked = [
        row
        for row in data
        if row.get("state") in ("armed", "forming") and row["textbook_similarity"] >= 0.5
    ]
    ranked.sort(key=lambda row: row["textbook_similarity"], reverse=True)
    items = [_make_item(index + 1, row) for index, row in enumerate(ranked[:limit])]
    return _response("pattern_armed", items)
