"""
Market scanner for dashboard and screener results.

The scanner traverses a Korean stock universe, runs the rule-based pattern engine,
computes probability scores, and caches the ranked results for the UI.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

from ..core.config import get_settings
from ..core.redis import cache_delete, cache_get, cache_set
from .analysis_service import analyze_symbol_dataframe
from .data_fetcher import get_data_fetcher
from .timeframe_service import DEFAULT_TIMEFRAME, get_timeframe_spec, timeframe_label

logger = logging.getLogger(__name__)
settings = get_settings()

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
    "timeframe": DEFAULT_TIMEFRAME,
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


async def _get_cached_count(timeframe: str | None = None) -> int:
    key_timeframe = timeframe or _scan_status.get("timeframe") or DEFAULT_TIMEFRAME
    cached = await cache_get(_scan_cache_key(key_timeframe))
    return len(cached) if isinstance(cached, list) else 0


def _scan_cache_key(timeframe: str) -> str:
    return f"scanner:full_results:{timeframe}"


async def get_scan_status(timeframe: str | None = None) -> dict[str, Any]:
    if _scan_status.get("is_running") and (_scan_task is None or _scan_task.done()):
        _update_scan_status(is_running=False)
    status = dict(_scan_status)
    key_timeframe = timeframe or status.get("timeframe") or DEFAULT_TIMEFRAME
    status["timeframe"] = key_timeframe
    status["cached_result_count"] = max(status.get("cached_result_count", 0), await _get_cached_count(key_timeframe))
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
            cap_df = await asyncio.wait_for(
                asyncio.to_thread(krx.get_market_cap_by_ticker, today, market=market),
                timeout=10.0,
            )
            if cap_df is None or cap_df.empty:
                continue

            for code, row in cap_df.iterrows():
                market_cap = float(row.get("시가총액", row.get("Marcap", 0))) / 1e8
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

    # FDR fallback — use market cap from FDR listing when pykrx is unavailable
    if not universe.empty and "code" in universe.columns:
        try:
            import FinanceDataReader as fdr

            def _fdr_caps() -> list[tuple[str, str, str, float]]:
                df = fdr.StockListing("KRX")
                df = df[df["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])].copy()
                df["market_norm"] = df["Market"].map(lambda m: "KOSDAQ" if "KOSDAQ" in m else "KOSPI")
                df["code_str"] = df["Code"].astype(str).str.zfill(6)
                df["cap_bil"] = df["Marcap"].fillna(0).astype(float) / 1e8  # KRW → 억원
                df = df[df["cap_bil"] >= settings.min_market_cap_billion]
                df = df.sort_values("cap_bil", ascending=False)
                rows_out = []
                for _, r in df.head(limit * 2).iterrows():
                    code_s = r["code_str"]
                    name_s = str(r["Name"]) if r["Name"] else code_s
                    rows_out.append((code_s, name_s, r["market_norm"], float(r["cap_bil"])))
                return rows_out

            fdr_rows = await asyncio.to_thread(_fdr_caps)
            if fdr_rows:
                fdr_rows.sort(key=lambda x: x[3], reverse=True)
                logger.info("Using FDR market universe: %d stocks", len(fdr_rows))
                return [(code, name, market) for code, name, market, _ in fdr_rows[:limit]]
        except Exception as exc:
            logger.warning("FDR universe for scanner failed: %s", exc)

    logger.warning("Falling back to static scanner universe")
    return FALLBACK_CODES[:limit]


async def _analyze_one(
    code: str,
    name: str,
    market: str,
    *,
    timeframe: str,
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    fetcher = get_data_fetcher()
    cache_key = f"scan:result:{timeframe}:{code}"
    if not force_refresh:
        cached = await cache_get(cache_key)
        if cached:
            return cached

    try:
        spec = get_timeframe_spec(timeframe)
        df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=spec.scanner_lookback_days)
        if df.empty or len(df) < spec.min_bars:
            return None

        symbol_info = {
            "code": code,
            "name": name,
            "market": market,
            "sector": None,
            "market_cap": await fetcher.get_market_cap(code),
            "is_in_universe": True,
        }
        snapshot = await analyze_symbol_dataframe(symbol_info=symbol_info, timeframe=timeframe, df=df)
        best_pattern = snapshot["patterns"][0] if snapshot["patterns"] else None
        result = {
            "code": code,
            "name": name,
            "market": market,
            "timeframe": timeframe,
            "timeframe_label": timeframe_label(timeframe),
            "data_source": snapshot["data_source"],
            "data_quality": snapshot["data_quality"],
            "source_note": snapshot["source_note"],
            "pattern_type": best_pattern["pattern_type"] if best_pattern else None,
            "state": best_pattern["state"] if best_pattern else None,
            "p_up": snapshot["p_up"],
            "p_down": snapshot["p_down"],
            "textbook_similarity": snapshot["textbook_similarity"],
            "confidence": snapshot["confidence"],
            "entry_score": snapshot["entry_score"],
            "completion_proximity": snapshot["completion_proximity"],
            "recency_score": snapshot["recency_score"],
            "bars_since_signal": snapshot["bars_since_signal"],
            "no_signal_flag": snapshot["no_signal_flag"],
            "reason_summary": snapshot["reason_summary"],
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
    timeframe: str = DEFAULT_TIMEFRAME,
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
            timeframe=timeframe,
            source=source,
            last_started_at=started_at.isoformat(),
            last_error=None,
            duration_ms=None,
        )

        if force_refresh:
            await cache_delete(_scan_cache_key(timeframe))

        cached = None if force_refresh else await cache_get(_scan_cache_key(timeframe))
        if cached:
            _update_scan_status(
                status="ready",
                is_running=False,
                timeframe=timeframe,
                cached_result_count=len(cached),
                last_finished_at=_utc_now_iso(),
                duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            )
            return cached

        try:
            logger.info(
                "Starting market scan: limit=%d, batch_size=%d, source=%s, timeframe=%s",
                limit,
                batch_size,
                source,
                timeframe,
            )
            universe = await _fetch_universe_codes(limit)
            _update_scan_status(universe_size=len(universe))

            results: list[dict[str, Any]] = []
            for index in range(0, len(universe), batch_size):
                batch = universe[index:index + batch_size]
                tasks = [
                    asyncio.wait_for(
                        _analyze_one(code, name, market, timeframe=timeframe, force_refresh=force_refresh),
                        timeout=25.0,
                    )
                    for code, name, market in batch
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for item in batch_results:
                    if isinstance(item, dict):
                        results.append(item)
                await asyncio.sleep(0.05)

            await cache_set(_scan_cache_key(timeframe), results, ttl=settings.dashboard_cache_ttl * 10)
            finished_at = datetime.utcnow()
            _update_scan_status(
                status="ready",
                is_running=False,
                timeframe=timeframe,
                cached_result_count=len(results),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            logger.info("Market scan complete: result_count=%d, source=%s, timeframe=%s", len(results), source, timeframe)
            return results
        except Exception as exc:
            finished_at = datetime.utcnow()
            _update_scan_status(
                status="error",
                is_running=False,
                timeframe=timeframe,
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
    timeframe: str = DEFAULT_TIMEFRAME,
) -> dict[str, Any]:
    """Starts a background scan if one is not already running."""
    global _scan_task

    if _scan_task and not _scan_task.done():
        status = await get_scan_status()
        status["trigger_accepted"] = False
        return status

    _scan_task = asyncio.create_task(
        run_scan(limit=limit, batch_size=batch_size, force_refresh=force_refresh, source=source, timeframe=timeframe)
    )
    status = await get_scan_status()
    status["status"] = "queued"
    status["is_running"] = True
    status["timeframe"] = timeframe
    status["source"] = source
    status["last_started_at"] = _utc_now_iso()
    status["trigger_accepted"] = True
    return status


async def get_scan_results(timeframe: str = DEFAULT_TIMEFRAME) -> list[dict[str, Any]]:
    """Returns cached scan results, warming with a quick fallback scan when needed."""
    cached = await cache_get(_scan_cache_key(timeframe))
    if cached:
        if not (_scan_task and not _scan_task.done()):
            _update_scan_status(status="ready", timeframe=timeframe, cached_result_count=len(cached))
        return cached

    # Full scan already running — don't start a second fallback scan that would clobber its status
    if _scan_task and not _scan_task.done():
        _update_scan_status(status="running", is_running=True, timeframe=timeframe)
        return []

    _update_scan_status(status="warming", is_running=False, source="fallback", timeframe=timeframe)
    logger.info("Cache cold; running fallback quick scan")
    quick = await asyncio.gather(
        *[
            _analyze_one(code, name, market, timeframe=timeframe)
            for code, name, market in FALLBACK_CODES
        ],
        return_exceptions=True,
    )
    results = [item for item in quick if isinstance(item, dict)]
    await cache_set(_scan_cache_key(timeframe), results, ttl=300)
    _update_scan_status(
        status="ready",
        timeframe=timeframe,
        cached_result_count=len(results),
        universe_size=len(FALLBACK_CODES),
        last_finished_at=_utc_now_iso(),
        source="fallback",
    )

    if not _scan_task or _scan_task.done():
        # force_refresh=True so the full scan overwrites the small fallback result set
        await trigger_scan(force_refresh=True, source="background", timeframe=timeframe)

    return results
