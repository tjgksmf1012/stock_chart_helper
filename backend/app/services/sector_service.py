"""
Sector classification service using pykrx WICS sector index constituents.
Maps stock code → sector name, aggregates scan results into sector heatmap.
Cached for 24 hours (sector memberships rarely change).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

_SECTOR_MAP_CACHE_KEY = "market:sector-map:v1"
_SECTOR_MAP_TTL = 86400  # 24시간

# KOSPI WICS 섹터 인덱스 티커 → 섹터명
_SECTOR_TICKERS: dict[str, str] = {
    "1028": "운수장비",
    "1003": "건설업",
    "1044": "IT",
    "1017": "금융업",
    "1010": "음식료품",
    "1022": "화학",
    "1005": "기계",
    "1007": "철강금속",
    "1008": "전기가스업",
    "1015": "전기전자",
    "1016": "의약품",
    "1006": "종이목재",
    "1009": "섬유의복",
    "1011": "유통업",
    "1014": "운수창고",
    "1021": "통신업",
    "1024": "서비스업",
    "1034": "비금속광물",
}

_BULLISH_PATTERNS = {
    "double_bottom", "inverse_head_and_shoulders", "ascending_triangle",
    "rectangle", "cup_and_handle", "rounding_bottom", "vcp",
}
_BEARISH_PATTERNS = {
    "double_top", "head_and_shoulders", "descending_triangle",
}


async def _fetch_sector_constituents(ticker: str, today: str) -> tuple[str, list[str]]:
    """단일 섹터 인덱스의 구성 종목 코드 리스트를 반환."""
    sector_name = _SECTOR_TICKERS.get(ticker, ticker)
    try:
        from pykrx import stock as krx
        df = await asyncio.wait_for(
            asyncio.to_thread(krx.get_index_portfolio_deposit_file, ticker, today),
            timeout=12.0,
        )
        if df is None or (hasattr(df, "empty") and df.empty):
            return sector_name, []

        # pykrx 반환형이 버전마다 다를 수 있음
        if isinstance(df, pd.DataFrame):
            # 종목코드가 인덱스인 경우
            if df.index.dtype == object or str(df.index.dtype).startswith("object"):
                codes = [str(c).zfill(6) for c in df.index if str(c).strip()]
            # 또는 컬럼 중 코드 컬럼 찾기
            elif "티커" in df.columns:
                codes = [str(c).zfill(6) for c in df["티커"] if str(c).strip()]
            elif "종목코드" in df.columns:
                codes = [str(c).zfill(6) for c in df["종목코드"] if str(c).strip()]
            else:
                codes = [str(c).zfill(6) for c in df.iloc[:, 0] if str(c).strip()]
        elif isinstance(df, (list, tuple)):
            codes = [str(c).zfill(6) for c in df if str(c).strip()]
        else:
            codes = []

        return sector_name, [c for c in codes if c and c != "000000"]
    except Exception as exc:
        logger.debug("sector %s (%s) fetch failed: %s", sector_name, ticker, exc)
        return sector_name, []


async def get_sector_map() -> dict[str, str]:
    """
    Returns {stock_code: sector_name} mapping.
    Fetches from pykrx if not cached; caches for 24h.
    """
    cached = await cache_get(_SECTOR_MAP_CACHE_KEY)
    if cached and isinstance(cached, dict) and len(cached) > 50:
        return cached

    today = date.today().strftime("%Y%m%d")

    results = await asyncio.gather(
        *[_fetch_sector_constituents(t, today) for t in _SECTOR_TICKERS],
        return_exceptions=True,
    )

    code_to_sector: dict[str, str] = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        sector_name, codes = r
        for code in codes:
            code_to_sector[code] = sector_name

    logger.info("sector map built: %d stocks", len(code_to_sector))
    if len(code_to_sector) > 50:
        await cache_set(_SECTOR_MAP_CACHE_KEY, code_to_sector, ttl=_SECTOR_MAP_TTL)
    return code_to_sector


def build_sector_heatmap(
    scan_rows: list[dict],
    code_to_sector: dict[str, str],
) -> list[dict]:
    """
    스캔 결과 rows와 섹터 맵을 받아 섹터별 패턴 분포를 집계.
    Returns list of sector dicts sorted by |net_score| descending.
    """
    aggregation: dict[str, dict] = {}

    for row in scan_rows:
        code = row.get("code", "")
        sector = code_to_sector.get(code, "기타")
        pattern = row.get("pattern_type") or ""
        if not pattern:
            continue

        if sector not in aggregation:
            aggregation[sector] = {"bullish": 0, "bearish": 0, "symbols": []}

        if pattern in _BULLISH_PATTERNS:
            aggregation[sector]["bullish"] += 1
            name = row.get("name", code)
            if name not in aggregation[sector]["symbols"]:
                aggregation[sector]["symbols"].append(name)
        elif pattern in _BEARISH_PATTERNS:
            aggregation[sector]["bearish"] += 1

    sectors = []
    for name, v in aggregation.items():
        if v["bullish"] + v["bearish"] == 0:
            continue
        sectors.append({
            "sector_name": name,
            "bullish_count": v["bullish"],
            "bearish_count": v["bearish"],
            "net_score": v["bullish"] - v["bearish"],
            "top_symbols": v["symbols"][:3],
        })
    sectors.sort(key=lambda s: abs(s["net_score"]), reverse=True)
    return sectors
