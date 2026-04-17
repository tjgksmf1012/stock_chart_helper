from __future__ import annotations

from fastapi import APIRouter

from ..schemas import DashboardItem, ScreenerRequest
from .dashboard import _make_item
from ...services.scanner import get_scan_results
from ...services.timeframe_service import DEFAULT_TIMEFRAME

router = APIRouter(prefix="/screeners", tags=["screener"])

SORT_KEYS = {
    "entry_score": lambda row: row["entry_score"],
    "p_up": lambda row: row["p_up"],
    "textbook_similarity": lambda row: row["textbook_similarity"],
    "confidence": lambda row: row["confidence"],
    "p_down": lambda row: row["p_down"],
}


@router.post("/run")
async def run_screener(req: ScreenerRequest) -> list[DashboardItem]:
    timeframes = req.timeframes or [DEFAULT_TIMEFRAME]
    merged: list[dict] = []
    for timeframe in timeframes:
        merged.extend(await get_scan_results(timeframe))

    filtered = merged
    if req.exclude_no_signal:
        filtered = [r for r in filtered if not r["no_signal_flag"]]
    if req.pattern_types:
        filtered = [r for r in filtered if r.get("pattern_type") in req.pattern_types]
    if req.states:
        filtered = [r for r in filtered if r.get("state") in req.states]
    if req.markets:
        filtered = [r for r in filtered if r.get("market") in req.markets]
    if req.min_market_cap is not None:
        filtered = [r for r in filtered if (r.get("market_cap") or 0) >= req.min_market_cap]

    filtered = [r for r in filtered if r["textbook_similarity"] >= req.min_textbook_similarity]
    filtered = [r for r in filtered if r["p_up"] >= req.min_p_up]
    filtered = [r for r in filtered if r["p_down"] <= req.max_p_down]
    filtered = [r for r in filtered if r["confidence"] >= req.min_confidence]

    sort_key = SORT_KEYS.get(req.sort_by, SORT_KEYS["entry_score"])
    filtered.sort(key=sort_key, reverse=True)
    return [_make_item(i + 1, r) for i, r in enumerate(filtered[: req.limit])]
