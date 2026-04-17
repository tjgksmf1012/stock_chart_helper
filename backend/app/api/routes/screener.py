from fastapi import APIRouter
from ..schemas import ScreenerRequest, DashboardItem, SymbolInfo
from .dashboard import _get_dashboard_data, _make_item

router = APIRouter(prefix="/screeners", tags=["screener"])


@router.post("/run")
async def run_screener(req: ScreenerRequest) -> list[DashboardItem]:
    data = await _get_dashboard_data()

    filtered = data
    if req.exclude_no_signal:
        filtered = [r for r in filtered if not r["no_signal_flag"]]
    if req.pattern_types:
        filtered = [r for r in filtered if r.get("pattern_type") in req.pattern_types]
    if req.states:
        filtered = [r for r in filtered if r.get("state") in req.states]

    filtered = [r for r in filtered if r["textbook_similarity"] >= req.min_textbook_similarity]
    filtered = [r for r in filtered if r["p_up"] >= req.min_p_up]
    filtered = [r for r in filtered if r["p_down"] <= req.max_p_down]
    filtered = [r for r in filtered if r["confidence"] >= req.min_confidence]

    filtered = sorted(filtered, key=lambda r: r["entry_score"], reverse=True)
    return [_make_item(i + 1, r) for i, r in enumerate(filtered[: req.limit])]
