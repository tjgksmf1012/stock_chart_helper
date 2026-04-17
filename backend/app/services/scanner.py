"""
Market scanner for dashboard and screener results.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from ..api.schemas import SymbolInfo
from ..core.config import get_settings
from ..core.redis import cache_delete, cache_get, cache_set
from .analysis_service import analyze_symbol_dataframe
from .data_fetcher import get_data_fetcher
from .timeframe_service import DEFAULT_TIMEFRAME, timeframe_label

logger = logging.getLogger(__name__)
settings = get_settings()

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

ANCHOR_TIMEFRAMES: dict[str, list[str]] = {
    "1mo": ["1wk"],
    "1wk": ["1mo", "1d"],
    "1d": ["1wk", "1mo"],
    "60m": ["1d", "1wk"],
    "30m": ["60m", "1d"],
    "15m": ["60m", "1d"],
    "1m": ["15m", "60m"],
}

_scan_lock = asyncio.Lock()
_scan_tasks: dict[str, asyncio.Task] = {}
_scan_status: dict[str, dict[str, Any]] = {}


def _full_scan_cache_key(timeframe: str) -> str:
    return f"scanner:v3:full_results:{timeframe}"


def _single_scan_cache_key(timeframe: str, code: str) -> str:
    return f"scan:v3:result:{timeframe}:{code}"


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _status_template(timeframe: str) -> dict[str, Any]:
    return {
        "timeframe": timeframe,
        "timeframe_label": timeframe_label(timeframe),
        "status": "idle",
        "is_running": False,
        "source": None,
        "candidate_source": None,
        "candidate_count": None,
        "cached_result_count": 0,
        "universe_size": None,
        "last_started_at": None,
        "last_finished_at": None,
        "last_error": None,
        "duration_ms": None,
    }


def _update_scan_status(timeframe: str, **kwargs: Any) -> None:
    status = _scan_status.setdefault(timeframe, _status_template(timeframe))
    status.update(kwargs)


def _direction_score(row: dict[str, Any]) -> float:
    return float(row.get("p_up", 0.5)) - float(row.get("p_down", 0.5))


def _direction_label(score: float) -> str:
    if score >= 0.08:
        return "상승"
    if score <= -0.08:
        return "하락"
    return "중립"


def _confluence_anchor_weights(timeframe: str) -> list[tuple[str, float]]:
    anchors = ANCHOR_TIMEFRAMES.get(timeframe, [])
    if len(anchors) == 2:
        return [(anchors[0], 0.6), (anchors[1], 0.4)]
    if len(anchors) == 1:
        return [(anchors[0], 1.0)]
    return []


async def _get_cached_count(timeframe: str) -> int:
    cached = await cache_get(_full_scan_cache_key(timeframe))
    return len(cached) if isinstance(cached, list) else 0


async def get_scan_status(timeframe: str = DEFAULT_TIMEFRAME) -> dict[str, Any]:
    status = dict(_scan_status.get(timeframe) or _status_template(timeframe))
    status["cached_result_count"] = max(status.get("cached_result_count", 0), await _get_cached_count(timeframe))
    return status


async def _fetch_universe_codes(limit: int = 100) -> list[tuple[str, str, str]]:
    fetcher = get_data_fetcher()
    universe = await fetcher.get_universe()
    universe_names = (
        {
            str(row["code"]): row.get("name", row["code"]) or row["code"]
            for _, row in universe.iterrows()
        }
        if not universe.empty
        else {}
    )

    try:
        from pykrx import stock as krx

        today = datetime.today().strftime("%Y%m%d")
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
                rows.append((code_str, universe_names.get(code_str, code_str), market, market_cap))

        if rows:
            rows.sort(key=lambda item: item[3], reverse=True)
            return [(code, name, market) for code, name, market, _ in rows[:limit]]
    except Exception as exc:
        logger.warning("Bulk market-cap universe fetch failed: %s", exc)

    logger.warning("Falling back to static scanner universe")
    return FALLBACK_CODES[:limit]


async def _build_confluence(
    code: str,
    name: str,
    market: str,
    timeframe: str,
    primary_row: dict[str, Any],
    force_refresh: bool,
) -> dict[str, Any]:
    weights = _confluence_anchor_weights(timeframe)
    if not weights:
        own_direction = _direction_label(_direction_score(primary_row))
        return {
            "confluence_score": 0.5,
            "confluence_summary": f"{timeframe_label(timeframe)} 단독 신호 기준입니다.",
            "scenario_text": f"{timeframe_label(timeframe)} 기준 {own_direction} 시나리오를 단독으로 해석한 결과입니다.",
            "composite_score": round(
                0.66 * float(primary_row.get("entry_score", 0.0))
                + 0.12 * float(primary_row.get("sample_reliability", 0.0))
                + 0.12 * float(primary_row.get("data_quality", 0.0))
                + 0.10 * float(primary_row.get("recency_score", 0.0)),
                3,
            ),
        }

    primary_direction = _direction_score(primary_row)
    agreement_parts: list[str] = []
    weighted_score = 0.0
    weighted_total = 0.0

    for anchor_timeframe, weight in weights:
        anchor_row = await _analyze_one(
            code,
            name,
            market,
            anchor_timeframe,
            force_refresh=force_refresh,
            include_confluence=False,
        )
        weighted_total += weight
        if not anchor_row:
            weighted_score += 0.45 * weight
            agreement_parts.append(f"{timeframe_label(anchor_timeframe)} 데이터 없음")
            continue

        anchor_direction = _direction_score(anchor_row)
        if anchor_row.get("no_signal_flag"):
            anchor_score = 0.50
        elif primary_direction * anchor_direction > 0.02:
            anchor_score = 0.92 if abs(anchor_direction) >= 0.15 else 0.78
        elif primary_direction * anchor_direction < -0.02:
            anchor_score = 0.10 if abs(anchor_direction) >= 0.15 else 0.24
        else:
            anchor_score = 0.56

        weighted_score += anchor_score * weight
        agreement_parts.append(f"{timeframe_label(anchor_timeframe)} {_direction_label(anchor_direction)}")

    confluence_score = weighted_score / weighted_total if weighted_total else 0.5
    own_direction = _direction_label(primary_direction)

    if confluence_score >= 0.74:
        scenario_text = (
            f"{timeframe_label(timeframe)} 신호와 상위 타임프레임 방향이 비슷해 {own_direction} 추세 추종형으로 보기 좋습니다."
        )
    elif confluence_score >= 0.56:
        scenario_text = (
            f"{timeframe_label(timeframe)} 신호는 유지되지만 상위 축 정렬은 절반 정도입니다. 무효화 기준을 우선 보는 편이 좋습니다."
        )
    else:
        scenario_text = (
            f"{timeframe_label(timeframe)} 신호와 주변 타임프레임이 엇갈립니다. 추세 매매보다 짧은 트리거 확인용으로 보는 편이 낫습니다."
        )

    composite_score = (
        0.46 * float(primary_row.get("entry_score", 0.0))
        + 0.18 * confluence_score
        + 0.12 * float(primary_row.get("sample_reliability", 0.0))
        + 0.10 * float(primary_row.get("data_quality", 0.0))
        + 0.08 * float(primary_row.get("recency_score", 0.0))
        + 0.06 * float(primary_row.get("completion_proximity", 0.0))
    )

    return {
        "confluence_score": round(confluence_score, 3),
        "confluence_summary": " / ".join(agreement_parts),
        "scenario_text": scenario_text,
        "composite_score": round(composite_score, 3),
    }


async def _analyze_one(
    code: str,
    name: str,
    market: str,
    timeframe: str,
    force_refresh: bool = False,
    include_confluence: bool = True,
) -> dict[str, Any] | None:
    fetcher = get_data_fetcher()
    cache_key = _single_scan_cache_key(timeframe, code)
    if not force_refresh:
        cached = await cache_get(cache_key)
        if cached:
            return cached

    try:
        df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe)
        if df.empty:
            return None

        symbol = SymbolInfo(
            code=code,
            name=name,
            market=market,
            sector=None,
            market_cap=await fetcher.get_market_cap(code),
            is_in_universe=True,
        )
        analysis = await analyze_symbol_dataframe(symbol, timeframe, df)
        result: dict[str, Any] = {
            "code": code,
            "name": name,
            "market": market,
            "timeframe": timeframe,
            "timeframe_label": analysis.timeframe_label,
            "pattern_type": analysis.patterns[0].pattern_type if analysis.patterns else None,
            "state": analysis.patterns[0].state if analysis.patterns else None,
            "p_up": analysis.p_up,
            "p_down": analysis.p_down,
            "textbook_similarity": analysis.textbook_similarity,
            "confidence": analysis.confidence,
            "entry_score": analysis.entry_score,
            "no_signal_flag": analysis.no_signal_flag,
            "reason_summary": analysis.reason_summary,
            "completion_proximity": analysis.completion_proximity,
            "recency_score": analysis.recency_score,
            "data_source": analysis.data_source,
            "data_quality": analysis.data_quality,
            "source_note": analysis.source_note,
            "fetch_status": analysis.fetch_status,
            "fetch_status_label": analysis.fetch_status_label,
            "fetch_message": analysis.fetch_message,
            "liquidity_score": analysis.liquidity_score,
            "avg_turnover_billion": analysis.avg_turnover_billion,
            "sample_size": analysis.sample_size,
            "empirical_win_rate": analysis.empirical_win_rate,
            "sample_reliability": analysis.sample_reliability,
            "stats_timeframe": analysis.stats_timeframe,
            "available_bars": analysis.available_bars,
        }

        if include_confluence:
            result.update(await _build_confluence(code, name, market, timeframe, result, force_refresh))
        else:
            result.update(
                {
                    "confluence_score": 0.5,
                    "confluence_summary": f"{timeframe_label(timeframe)} 단독 분석",
                    "scenario_text": f"{timeframe_label(timeframe)} 신호만 기준으로 계산한 보조 결과입니다.",
                    "composite_score": round(
                        0.75 * float(result["entry_score"]) + 0.25 * float(result["sample_reliability"]),
                        3,
                    ),
                }
            )

        await cache_set(cache_key, result, ttl=1800)
        return result
    except Exception as exc:
        logger.warning("Scan failed for %s (%s): %s", code, timeframe, exc)
        return None


async def _select_candidates(limit: int, timeframe: str) -> tuple[list[tuple[str, str, str]], str]:
    if timeframe in {"1d", "1wk", "1mo"}:
        return await _fetch_universe_codes(limit), "krx_universe"

    seed_limit = max(settings.intraday_seed_limit, limit * settings.intraday_seed_multiplier)
    daily_candidates = await get_scan_results("1d")
    daily_candidates = [
        row
        for row in daily_candidates
        if row.get("entry_score", 0) >= 0.45 and row.get("confidence", 0) >= 0.30
    ]
    daily_candidates.sort(
        key=lambda row: (
            row.get("composite_score", 0),
            row.get("sample_reliability", 0),
            row.get("entry_score", 0),
            row.get("data_quality", 0),
            row.get("liquidity_score", 0),
        ),
        reverse=True,
    )

    if daily_candidates:
        selected = [(row["code"], row["name"], row.get("market", "KRX")) for row in daily_candidates[:seed_limit]]
        return selected, "daily_seed"

    return await _fetch_universe_codes(seed_limit), "krx_universe_fallback"


async def run_scan(
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = 100,
    batch_size: int = 10,
    force_refresh: bool = False,
    source: str = "scheduled",
) -> list[dict[str, Any]]:
    started_at = datetime.utcnow()
    cache_key = _full_scan_cache_key(timeframe)

    async with _scan_lock:
        _update_scan_status(
            timeframe,
            status="running",
            is_running=True,
            source=source,
            last_started_at=started_at.isoformat(),
            last_error=None,
            duration_ms=None,
        )

        if force_refresh:
            await cache_delete(cache_key)

        cached = None if force_refresh else await cache_get(cache_key)
        if cached:
            _update_scan_status(
                timeframe,
                status="ready",
                is_running=False,
                cached_result_count=len(cached),
                last_finished_at=_utc_now_iso(),
                duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            )
            return cached

        try:
            universe, candidate_source = await _select_candidates(limit, timeframe)
            _update_scan_status(
                timeframe,
                universe_size=len(universe),
                candidate_source=candidate_source,
                candidate_count=len(universe),
            )

            results: list[dict[str, Any]] = []
            for index in range(0, len(universe), batch_size):
                batch = universe[index:index + batch_size]
                tasks = [
                    _analyze_one(code, name, market, timeframe, force_refresh=force_refresh)
                    for code, name, market in batch
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for item in batch_results:
                    if isinstance(item, dict):
                        results.append(item)
                await asyncio.sleep(0.08)

            results.sort(
                key=lambda row: (
                    0 if row["no_signal_flag"] else 1,
                    row.get("composite_score", 0),
                    row.get("sample_reliability", 0),
                    row.get("entry_score", 0),
                    row.get("data_quality", 0),
                    row.get("liquidity_score", 0),
                    row.get("textbook_similarity", 0),
                ),
                reverse=True,
            )
            await cache_set(cache_key, results, ttl=settings.dashboard_cache_ttl * 20)
            finished_at = datetime.utcnow()
            _update_scan_status(
                timeframe,
                status="ready",
                is_running=False,
                cached_result_count=len(results),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            return results
        except Exception as exc:
            finished_at = datetime.utcnow()
            _update_scan_status(
                timeframe,
                status="error",
                is_running=False,
                last_error=str(exc),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            logger.exception("Market scan crashed")
            raise


async def trigger_scan(
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = 100,
    batch_size: int = 10,
    force_refresh: bool = True,
    source: str = "manual",
) -> dict[str, Any]:
    task = _scan_tasks.get(timeframe)
    if task and not task.done():
        status = await get_scan_status(timeframe)
        status["trigger_accepted"] = False
        return status

    _scan_tasks[timeframe] = asyncio.create_task(
        run_scan(timeframe=timeframe, limit=limit, batch_size=batch_size, force_refresh=force_refresh, source=source)
    )
    status = await get_scan_status(timeframe)
    status["status"] = "queued"
    status["is_running"] = True
    status["source"] = source
    status["last_started_at"] = _utc_now_iso()
    status["trigger_accepted"] = True
    return status


async def get_scan_results(timeframe: str = DEFAULT_TIMEFRAME) -> list[dict[str, Any]]:
    cache_key = _full_scan_cache_key(timeframe)
    cached = await cache_get(cache_key)
    if cached:
        _update_scan_status(timeframe, status="ready", cached_result_count=len(cached))
        return cached

    _update_scan_status(timeframe, status="warming", is_running=False, source="fallback")
    fallback = FALLBACK_CODES if timeframe == "1d" else FALLBACK_CODES[: min(len(FALLBACK_CODES), settings.intraday_seed_limit)]
    quick = await asyncio.gather(
        *[_analyze_one(code, name, market, timeframe) for code, name, market in fallback],
        return_exceptions=True,
    )
    results = [item for item in quick if isinstance(item, dict)]
    results.sort(
        key=lambda row: (
            row.get("composite_score", row.get("entry_score", 0)),
            row.get("sample_reliability", 0),
        ),
        reverse=True,
    )
    await cache_set(cache_key, results, ttl=300)
    _update_scan_status(
        timeframe,
        status="ready",
        cached_result_count=len(results),
        universe_size=len(fallback),
        candidate_source="fallback",
        candidate_count=len(fallback),
        last_finished_at=_utc_now_iso(),
        source="fallback",
    )

    task = _scan_tasks.get(timeframe)
    if not task or task.done():
        await trigger_scan(timeframe=timeframe, force_refresh=False, source="background")

    return results
