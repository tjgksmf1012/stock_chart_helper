"""
Dashboard API: returns ranked lists for each dashboard category.

Categories (plan §11.1):
  - long_high_probability
  - short_high_probability
  - high_textbook_similarity
  - watchlist_no_signal
  - pattern_armed   (패턴 거의 완성)
"""

from fastapi import APIRouter, Query
from datetime import datetime, date, timedelta
import asyncio

from ..schemas import DashboardResponse, DashboardItem, SymbolInfo
from ...services.data_fetcher import get_data_fetcher
from ...services.pattern_engine import PatternEngine
from ...services.probability_engine import compute_probability
from ...core.redis import cache_get, cache_set
from ...core.config import get_settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
settings = get_settings()

# Demo universe (20 large-cap KR stocks) used when live scan is not running
DEMO_CODES = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # NAVER
    "051910",  # LG화학
    "006400",  # 삼성SDI
    "035720",  # 카카오
    "028260",  # 삼성물산
    "012330",  # 현대모비스
    "068270",  # 셀트리온
    "105560",  # KB금융
]


async def _analyze_code(code: str) -> dict | None:
    fetcher = get_data_fetcher()
    end = date.today()
    start = end - timedelta(days=365)
    try:
        df = await fetcher.get_stock_ohlcv(code, start, end)
        name = await fetcher.get_stock_name(code)
        if df.empty or len(df) < 20:
            return None
        engine = PatternEngine()
        patterns = engine.detect_all(df)
        if not patterns:
            return {
                "code": code, "name": name,
                "pattern_type": None, "state": None,
                "p_up": 0.5, "p_down": 0.5,
                "textbook_similarity": 0.0, "confidence": 0.0,
                "entry_score": 0.0, "no_signal_flag": True,
                "reason_summary": "감지된 패턴 없음",
            }
        best = max(patterns, key=lambda p: p.textbook_similarity)
        prob = compute_probability(best, sample_size=50)
        return {
            "code": code, "name": name,
            "pattern_type": best.pattern_type, "state": best.state,
            "p_up": prob.p_up, "p_down": prob.p_down,
            "textbook_similarity": prob.textbook_similarity,
            "confidence": prob.confidence,
            "entry_score": prob.entry_score,
            "no_signal_flag": prob.no_signal_flag,
            "reason_summary": prob.reason_summary,
        }
    except Exception:
        return None


async def _get_dashboard_data() -> list[dict]:
    cache_key = "dashboard:all"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    tasks = [_analyze_code(code) for code in DEMO_CODES]
    results = await asyncio.gather(*tasks)
    data = [r for r in results if r is not None]
    await cache_set(cache_key, data, settings.dashboard_cache_ttl)
    return data


def _make_item(rank: int, row: dict) -> DashboardItem:
    return DashboardItem(
        rank=rank,
        symbol=SymbolInfo(
            code=row["code"],
            name=row["name"],
            market="KOSPI",
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


@router.get("/long-high-probability")
async def dashboard_long(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await _get_dashboard_data()
    ranked = sorted(data, key=lambda r: r["entry_score"], reverse=True)
    ranked = [r for r in ranked if not r["no_signal_flag"] and r["p_up"] > 0.55]
    items = [_make_item(i + 1, r) for i, r in enumerate(ranked[:limit])]
    return DashboardResponse(category="long_high_probability", items=items, generated_at=datetime.utcnow().isoformat())


@router.get("/short-high-probability")
async def dashboard_short(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await _get_dashboard_data()
    ranked = sorted(data, key=lambda r: r["p_down"], reverse=True)
    ranked = [r for r in ranked if not r["no_signal_flag"] and r["p_down"] > 0.55]
    items = [_make_item(i + 1, r) for i, r in enumerate(ranked[:limit])]
    return DashboardResponse(category="short_high_probability", items=items, generated_at=datetime.utcnow().isoformat())


@router.get("/high-textbook-similarity")
async def dashboard_similarity(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await _get_dashboard_data()
    ranked = sorted(data, key=lambda r: r["textbook_similarity"], reverse=True)
    items = [_make_item(i + 1, r) for i, r in enumerate(ranked[:limit])]
    return DashboardResponse(category="high_textbook_similarity", items=items, generated_at=datetime.utcnow().isoformat())


@router.get("/watchlist-no-signal")
async def dashboard_no_signal(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await _get_dashboard_data()
    ranked = [r for r in data if r["no_signal_flag"]]
    items = [_make_item(i + 1, r) for i, r in enumerate(ranked[:limit])]
    return DashboardResponse(category="watchlist_no_signal", items=items, generated_at=datetime.utcnow().isoformat())


@router.get("/pattern-armed")
async def dashboard_armed(limit: int = Query(default=10, le=50)) -> DashboardResponse:
    data = await _get_dashboard_data()
    ranked = [r for r in data if r.get("state") in ("armed", "forming") and r["textbook_similarity"] >= 0.5]
    ranked = sorted(ranked, key=lambda r: r["textbook_similarity"], reverse=True)
    items = [_make_item(i + 1, r) for i, r in enumerate(ranked[:limit])]
    return DashboardResponse(category="pattern_armed", items=items, generated_at=datetime.utcnow().isoformat())
