"""
Sector classification service using pykrx WICS sector index constituents.
Maps stock code → sector name, aggregates scan results into sector heatmap.
Cached for 24 hours (sector memberships rarely change).

Non-blocking design: cache miss → return empty immediately + background build.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

import pandas as pd

from ..core.redis import cache_get, cache_set
from .pattern_engine import resolve_pattern_direction

logger = logging.getLogger(__name__)

_SECTOR_MAP_CACHE_KEY = "market:sector-map:v1"
_SECTOR_MAP_TTL = 86400  # 24시간

# 동시 pykrx 호출 수 제한 (18개 섹터를 한 번에 다 쏘면 thread pool 포화)
_SECTOR_SEMAPHORE: asyncio.Semaphore | None = None
_sector_build_task: asyncio.Task | None = None  # 진행 중인 빌드 task 추적

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

def _get_semaphore() -> asyncio.Semaphore:
    global _SECTOR_SEMAPHORE
    if _SECTOR_SEMAPHORE is None:
        _SECTOR_SEMAPHORE = asyncio.Semaphore(3)  # 한 번에 최대 3개 섹터만 pykrx 호출
    return _SECTOR_SEMAPHORE


async def _fetch_sector_constituents(ticker: str, today: str) -> tuple[str, list[str]]:
    """단일 섹터 인덱스의 구성 종목 코드 리스트를 반환. 세마포어로 동시 호출 제한."""
    sector_name = _SECTOR_TICKERS.get(ticker, ticker)
    # KRX가 이미 차단 판정(쿨다운)이면 호출 자체를 건너뛴다 — pykrx가 실패마다
    # 내부 print를 찍어 로그 스팸이 되고, 어차피 빈 응답이다
    from .data_fetcher import krx_in_cooldown

    if await krx_in_cooldown():
        return sector_name, []
    sem = _get_semaphore()
    try:
        from pykrx import stock as krx
        async with sem:
            df = await asyncio.wait_for(
                asyncio.to_thread(krx.get_index_portfolio_deposit_file, ticker, today),
                timeout=10.0,
            )
        if df is None or (hasattr(df, "empty") and df.empty):
            return sector_name, []

        if isinstance(df, pd.DataFrame):
            if df.index.dtype == object or str(df.index.dtype).startswith("object"):
                codes = [str(c).zfill(6) for c in df.index if str(c).strip()]
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


async def _build_sector_map() -> dict[str, str]:
    """18개 섹터를 순차 배치(3개씩)로 가져와 캐시에 저장."""
    from .data_fetcher import krx_in_cooldown, mark_krx_cooldown

    if await krx_in_cooldown():
        logger.info("sector map build skipped — KRX cooldown 중 (쿨다운 해제 후 재시도)")
        return {}

    today = date.today().strftime("%Y%m%d")
    tickers = list(_SECTOR_TICKERS.keys())

    # 세마포어가 3이므로 asyncio.gather로 한 번에 보내도 최대 3개만 동시 실행
    results = await asyncio.gather(
        *[_fetch_sector_constituents(t, today) for t in tickers],
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
    elif not code_to_sector:
        # 18개 전부 빈 응답 = KRX 차단인데 아직 쿨다운 마크 전 — 여기서 걸어줘야
        # 프론트의 30초 재시도 루프가 15분간 pykrx를 다시 두들기지 않는다
        await mark_krx_cooldown("sector constituents: 전 섹터 빈 응답 (KRX 차단 추정)")
    return code_to_sector


async def get_sector_map() -> dict[str, str]:
    """
    Returns {stock_code: sector_name} mapping.

    Non-blocking:
    - 캐시 히트 → 즉시 반환
    - 캐시 미스 + 빌드 진행 중 → 빈 dict 즉시 반환
    - 캐시 미스 + 빌드 없음 → 백그라운드 빌드 시작 후 빈 dict 즉시 반환
    """
    global _sector_build_task

    cached = await cache_get(_SECTOR_MAP_CACHE_KEY)
    if cached and isinstance(cached, dict) and len(cached) > 50:
        return cached

    # 이미 빌드 중이면 즉시 빈 dict 반환
    if _sector_build_task is not None and not _sector_build_task.done():
        logger.debug("sector map build in progress, returning empty")
        return {}

    # 백그라운드 빌드 시작
    logger.info("sector map cache miss — starting background build")

    async def _run_build() -> None:
        try:
            await _build_sector_map()
        except Exception as exc:
            logger.warning("sector map background build failed: %s", exc)

    _sector_build_task = asyncio.create_task(_run_build())
    return {}


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
        # 섹터 맵이 콜드 캐시거나(빌드 중이면 get_sector_map()이 빈 dict를 즉시 반환)
        # 해당 종목이 아직 안 잡혀 있으면, "기타"라는 가짜 섹터로 몰아넣지 않고
        # 그냥 집계에서 뺀다 — 안 그러면 실제 섹터 로테이션처럼 보이는 거대한
        # "기타" 버킷이 |net_score| 정렬에서 히트맵 최상단을 차지할 수 있다.
        sector = code_to_sector.get(code)
        if not sector:
            continue
        pattern = row.get("pattern_type") or ""
        if not pattern:
            continue

        if sector not in aggregation:
            aggregation[sector] = {"bullish": 0, "bearish": 0, "symbols": []}

        # symmetric_triangle/rectangle/rising_channel/falling_channel은 타입만으로
        # 방향이 안 정해지는 구조라, 정적 집합(BULLISH_PATTERNS/BEARISH_PATTERNS)만
        # 보면 둘 중 어디에도 안 걸려 집계에서 통째로 빠진다. trigger_level(=neckline)
        # 대비 target_level로 이 종목의 실제 방향을 판정한다.
        bullish = resolve_pattern_direction(pattern, row.get("trigger_level"), row.get("target_level"))
        if bullish:
            aggregation[sector]["bullish"] += 1
            name = row.get("name", code)
            if name not in aggregation[sector]["symbols"]:
                aggregation[sector]["symbols"].append(name)
        else:
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
