"""
Market scanner for dashboard and screener results.

The scanner traverses a Korean stock universe, runs the rule-based pattern engine,
computes probability scores, and caches the ranked results for the UI.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

from ..core.config import get_settings
from ..core.redis import cache_delete, cache_get, cache_set
from .data_fetcher import get_data_fetcher
from .pattern_engine import PatternEngine
from .probability_engine import compute_probability

logger = logging.getLogger(__name__)
settings = get_settings()

FULL_SCAN_CACHE_KEY = "scanner:full_results"

# Fallback universe used when the full symbol list is not available yet.
FALLBACK_CODES: list[tuple[str, str, str]] = [
    ("005930", "삼성전자", "KOSPI"),
    ("000660", "SK하이닉스", "KOSPI"),
    ("207940", "삼성바이오로직스", "KOSPI"),
    ("005380", "현대차", "KOSPI"),
    ("000270", "기아", "KOSPI"),
    ("035420", "NAVER", "KOSPI"),
    ("051910", "LG화학", "KOSPI"),
    ("006400", "삼성SDI", "KOSPI"),
    ("035720", "카카오", "KOSPI"),
    ("068270", "셀트리온", "KOSPI"),
    ("247540", "에코프로비엠", "KOSDAQ"),
    ("086520", "에코프로", "KOSDAQ"),
    ("091990", "셀트리온헬스케어", "KOSDAQ"),
    ("041510", "에스엠", "KOSDAQ"),
    ("263750", "펄어비스", "KOSDAQ"),
]

_scan_lock = asyncio.Lock()
_scan_task: asyncio.Task | None = None
_scan_status: dict[str, Any] = {
    "status": "idle",
    "is_running": False,
    "source": None,
    "cached_result_count": 0,
    "universe_size": None,
    "last_started_at": None,
    "last_finished_at": None,
    "last_error": None,
    "duration_ms": None,
}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _update_scan_status(**kwargs: Any) -> None:
    _scan_status.update(kwargs)


async def _get_cached_count() -> int:
    cached = await cache_get(FULL_SCAN_CACHE_KEY)
    return len(cached) if isinstance(cached, list) else 0


async def get_scan_status() -> dict[str, Any]:
    status = dict(_scan_status)
    status["cached_result_count"] = max(status.get("cached_result_count", 0), await _get_cached_count())
    return status


async def _fetch_universe_codes(limit: int = 100) -> list[tuple[str, str, str]]:
    """Returns (code, name, market) tuples ordered by market cap where possible."""
    fetcher = get_data_fetcher()
    universe = await fetcher.get_universe()
    universe_names = {
        str(row["code"]): row.get("name", row["code"]) or row["code"]
        for _, row in universe.iterrows()
    } if not universe.empty else {}

    try:
        from pykrx import stock as krx

        today = date.today().strftime("%Y%m%d")
        rows: list[tuple[str, str, str, float]] = []

        for market in ("KOSPI", "KOSDAQ"):
            cap_df = await asyncio.to_thread(krx.get_market_cap, today, today, market=market)
            if cap_df is None or cap_df.empty:
                continue

            for code, row in cap_df.iterrows():
                market_cap = float(row.get("시가총액", 0)) / 1e8
                if market_cap < settings.min_market_cap_billion:
                    continue
                code_str = str(code)
                rows.append((
                    code_str,
                    universe_names.get(code_str, code_str),
                    market,
                    market_cap,
                ))

        if rows:
            rows.sort(key=lambda item: item[3], reverse=True)
            return [(code, name, market) for code, name, market, _ in rows[:limit]]
    except Exception as exc:
        logger.warning("Bulk market-cap universe fetch failed: %s", exc)

    logger.warning("Falling back to static scanner universe")
    return FALLBACK_CODES[:limit]


async def _analyze_one(code: str, name: str, market: str, force_refresh: bool = False) -> dict[str, Any] | None:
    fetcher = get_data_fetcher()
    end = date.today()
    start = end - timedelta(days=400)

    cache_key = f"scan:result:{code}"
    if not force_refresh:
        cached = await cache_get(cache_key)
        if cached:
            return cached

    try:
        df = await fetcher.get_stock_ohlcv(code, start, end)
        if df.empty or len(df) < 30:
            return None

        engine = PatternEngine()
        patterns = engine.detect_all(df)

        if not patterns:
            result: dict[str, Any] = {
                "code": code,
                "name": name,
                "market": market,
                "pattern_type": None,
                "state": None,
                "p_up": 0.5,
                "p_down": 0.5,
                "textbook_similarity": 0.0,
                "confidence": 0.0,
                "entry_score": 0.0,
                "no_signal_flag": True,
                "reason_summary": "감지된 패턴이 없습니다.",
            }
        else:
            best = max(patterns, key=lambda pattern: pattern.textbook_similarity)
            prob = compute_probability(best, sample_size=50)
            result = {
                "code": code,
                "name": name,
                "market": market,
                "pattern_type": best.pattern_type,
                "state": best.state,
                "p_up": prob.p_up,
                "p_down": prob.p_down,
                "textbook_similarity": prob.textbook_similarity,
                "confidence": prob.confidence,
                "entry_score": prob.entry_score,
                "no_signal_flag": prob.no_signal_flag,
                "reason_summary": prob.reason_summary,
            }

        await cache_set(cache_key, result, ttl=3600)
        return result
    except Exception as exc:
        logger.warning("Scan failed for %s: %s", code, exc)
        return None


async def run_scan(
    limit: int = 100,
    batch_size: int = 10,
    force_refresh: bool = False,
    source: str = "scheduled",
) -> list[dict[str, Any]]:
    """
    Runs a full market scan and updates shared scan status metadata.

    When `force_refresh` is false and a cached full scan exists, the cached result is reused.
    """
    started_at = datetime.utcnow()

    async with _scan_lock:
        _update_scan_status(
            status="running",
            is_running=True,
            source=source,
            last_started_at=started_at.isoformat(),
            last_error=None,
            duration_ms=None,
        )

        if force_refresh:
            await cache_delete(FULL_SCAN_CACHE_KEY)

        cached = None if force_refresh else await cache_get(FULL_SCAN_CACHE_KEY)
        if cached:
            _update_scan_status(
                status="ready",
                is_running=False,
                cached_result_count=len(cached),
                last_finished_at=_utc_now_iso(),
                duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            )
            return cached

        try:
            logger.info("Starting market scan", limit=limit, batch_size=batch_size, source=source)
            universe = await _fetch_universe_codes(limit)
            _update_scan_status(universe_size=len(universe))

            results: list[dict[str, Any]] = []
            for index in range(0, len(universe), batch_size):
                batch = universe[index:index + batch_size]
                tasks = [_analyze_one(code, name, market, force_refresh=force_refresh) for code, name, market in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for item in batch_results:
                    if isinstance(item, dict):
                        results.append(item)
                await asyncio.sleep(0.1)

            await cache_set(FULL_SCAN_CACHE_KEY, results, ttl=settings.dashboard_cache_ttl * 10)
            finished_at = datetime.utcnow()
            _update_scan_status(
                status="ready",
                is_running=False,
                cached_result_count=len(results),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            logger.info("Market scan complete", result_count=len(results), source=source)
            return results
        except Exception as exc:
            finished_at = datetime.utcnow()
            _update_scan_status(
                status="error",
                is_running=False,
                last_error=str(exc),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            logger.exception("Market scan crashed")
            raise


async def trigger_scan(
    limit: int = 100,
    batch_size: int = 10,
    force_refresh: bool = True,
    source: str = "manual",
) -> dict[str, Any]:
    """Starts a background scan if one is not already running."""
    global _scan_task

    if _scan_task and not _scan_task.done():
        status = await get_scan_status()
        status["trigger_accepted"] = False
        return status

    _scan_task = asyncio.create_task(
        run_scan(limit=limit, batch_size=batch_size, force_refresh=force_refresh, source=source)
    )
    status = await get_scan_status()
    status["status"] = "queued"
    status["is_running"] = True
    status["source"] = source
    status["last_started_at"] = _utc_now_iso()
    status["trigger_accepted"] = True
    return status


async def get_scan_results() -> list[dict[str, Any]]:
    """Returns cached scan results, warming with a quick fallback scan when needed."""
    cached = await cache_get(FULL_SCAN_CACHE_KEY)
    if cached:
        _update_scan_status(
            status="ready",
            cached_result_count=len(cached),
        )
        return cached

    _update_scan_status(status="warming", is_running=False, source="fallback")
    logger.info("Cache cold; running fallback quick scan")
    quick = await asyncio.gather(
        *[_analyze_one(code, name, market) for code, name, market in FALLBACK_CODES],
        return_exceptions=True,
    )
    results = [item for item in quick if isinstance(item, dict)]
    await cache_set(FULL_SCAN_CACHE_KEY, results, ttl=300)
    _update_scan_status(
        status="ready",
        cached_result_count=len(results),
        universe_size=len(FALLBACK_CODES),
        last_finished_at=_utc_now_iso(),
        source="fallback",
    )

    if not _scan_task or _scan_task.done():
        await trigger_scan(force_refresh=False, source="background")

    return results
