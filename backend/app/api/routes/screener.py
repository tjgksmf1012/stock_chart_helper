from __future__ import annotations

from fastapi import APIRouter

from ..schemas import DashboardItem, ScreenerRequest
from .dashboard import _make_item
from ...services.scanner import get_scan_results
from ...services.timeframe_service import DEFAULT_TIMEFRAME

router = APIRouter(prefix="/screeners", tags=["screener"])

SORT_KEYS = {
    "composite_score": lambda row: row.get("composite_score", row["entry_score"]),
    "entry_score": lambda row: row["entry_score"],
    "p_up": lambda row: row["p_up"],
    "textbook_similarity": lambda row: row["textbook_similarity"],
    "confidence": lambda row: row["confidence"],
    "p_down": lambda row: row["p_down"],
    "sample_reliability": lambda row: row.get("sample_reliability", 0.0),
    "trade_readiness_score": lambda row: row.get("trade_readiness_score", 0.0),
    "entry_window_score": lambda row: row.get("entry_window_score", 0.0),
    "freshness_score": lambda row: row.get("freshness_score", 0.0),
    "active_setup_score": lambda row: row.get("active_setup_score", 0.0),
    "confluence_score": lambda row: row.get("confluence_score", 0.0),
    "data_quality": lambda row: row.get("data_quality", 0.0),
    "historical_edge_score": lambda row: row.get("historical_edge_score", 0.0),
}


@router.post("/run")
async def run_screener(req: ScreenerRequest) -> list[DashboardItem]:
    timeframes = req.timeframes or [DEFAULT_TIMEFRAME]
    merged: list[dict] = []
    for timeframe in timeframes:
        merged.extend(await get_scan_results(timeframe))

    filtered = merged
    if req.exclude_no_signal:
        filtered = [row for row in filtered if not row["no_signal_flag"]]
    if req.pattern_types:
        filtered = [row for row in filtered if row.get("pattern_type") in req.pattern_types]
    if req.states:
        filtered = [row for row in filtered if row.get("state") in req.states]
    if req.markets:
        filtered = [row for row in filtered if row.get("market") in req.markets]
    if req.fetch_statuses:
        filtered = [row for row in filtered if row.get("fetch_status") in req.fetch_statuses]
    if req.min_market_cap is not None:
        filtered = [row for row in filtered if (row.get("market_cap") or 0) >= req.min_market_cap]

    filtered = [row for row in filtered if row["textbook_similarity"] >= req.min_textbook_similarity]
    filtered = [row for row in filtered if row["p_up"] >= req.min_p_up]
    filtered = [row for row in filtered if row["p_down"] <= req.max_p_down]
    filtered = [row for row in filtered if row["confidence"] >= req.min_confidence]
    filtered = [row for row in filtered if row.get("sample_reliability", 0) >= req.min_sample_reliability]
    filtered = [row for row in filtered if row.get("data_quality", 0) >= req.min_data_quality]
    filtered = [row for row in filtered if row.get("trade_readiness_score", 0) >= req.min_trade_readiness_score]
    filtered = [row for row in filtered if row.get("entry_window_score", 0) >= req.min_entry_window_score]
    filtered = [row for row in filtered if row.get("freshness_score", 0) >= req.min_freshness_score]
    filtered = [row for row in filtered if row.get("active_setup_score", 0) >= req.min_active_setup_score]
    filtered = [row for row in filtered if row.get("confluence_score", 0) >= req.min_confluence_score]
    filtered = [row for row in filtered if row.get("historical_edge_score", 0) >= req.min_historical_edge_score]

    sort_key = SORT_KEYS.get(req.sort_by, SORT_KEYS["composite_score"])
    reverse = req.sort_by != "p_down"
    filtered.sort(key=sort_key, reverse=reverse)
    return [_make_item(index + 1, row) for index, row in enumerate(filtered[: req.limit])]
