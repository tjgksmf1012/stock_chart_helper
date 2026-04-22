from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    CacheRuntimeStatus,
    IntradayCandidateWarmupRequest,
    IntradayStoreStatus,
    IntradayWarmupJobStatus,
    IntradayWarmupRequest,
    IntradayWarmupResponse,
    IntradayWarmupResult,
    KisPrimeStatus,
    KisRuntimeStatus,
    RuntimeStatusResponse,
    ScanHistoryRunSummary,
    ScanQualityReportResponse,
)
from ...core.config import get_settings
from ...core.redis import cache_backend_status
from ...services.data_fetcher import get_data_fetcher
from ...services.intraday_store import get_intraday_store
from ...services.kis_client import get_kis_client
from ...services.scan_history_service import build_scan_quality_report, list_recent_scan_runs, prune_scan_history
from ...services.scanner import get_scan_results
from ...services.timeframe_service import get_timeframe_spec, is_intraday_timeframe

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()
_warmup_task: asyncio.Task | None = None
_kis_prime_task: asyncio.Task | None = None
_warmup_status: dict[str, Any] = {
    "status": "idle",
    "is_running": False,
    "source": None,
    "allow_live": False,
    "started_at": None,
    "finished_at": None,
    "total_requests": 0,
    "completed_count": 0,
    "success_count": 0,
    "failure_count": 0,
    "symbols": [],
    "timeframes": [],
    "last_error": None,
    "trigger_accepted": None,
    "results": [],
}
_kis_prime_status: dict[str, Any] = {
    "status": "idle",
    "is_running": False,
    "requested_at": None,
    "finished_at": None,
    "triggered_by": None,
    "symbol": None,
    "timeframe": None,
    "ok": None,
    "token_cached_before": False,
    "token_cached_after": False,
    "token_expires_at": None,
    "token_expires_in_seconds": None,
    "resolved_base_url": None,
    "store_rows_before": 0,
    "store_rows_after": 0,
    "store_rows_added": 0,
    "bars_returned": 0,
    "data_source": None,
    "fetch_status": None,
    "message": None,
    "last_error": None,
}

SCHEDULED_INTRADAY_WARMUP_PLANS: list[dict[str, Any]] = [
    {
        "id": "open_candidate_cache",
        "label": "장초반 후보 분봉 캐시",
        "source_timeframe": "1d",
        "limit": 20,
        "timeframes": ["15m", "30m", "60m"],
        "allow_live": False,
        "schedule": "평일 09:20",
    },
    {
        "id": "midday_candidate_cache",
        "label": "장중 후보 분봉 캐시",
        "source_timeframe": "1d",
        "limit": 20,
        "timeframes": ["15m", "30m", "60m"],
        "allow_live": False,
        "schedule": "평일 12:40",
    },
    {
        "id": "closing_candidate_cache",
        "label": "마감 전 후보 분봉 캐시",
        "source_timeframe": "60m",
        "limit": 15,
        "timeframes": ["15m", "30m", "60m"],
        "allow_live": False,
        "schedule": "평일 14:50",
    },
]


def _read_token_cache_status(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return {
            "token_cached": False,
            "token_expires_at": None,
            "token_expires_in_seconds": None,
            "resolved_base_url": None,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expires_at = float(payload.get("expires_at", 0))
        remaining = int(expires_at - datetime.now().timestamp())
        if remaining <= 0:
            return {
                "token_cached": False,
                "token_expires_at": datetime.fromtimestamp(expires_at).isoformat() if expires_at else None,
                "token_expires_in_seconds": 0,
                "resolved_base_url": payload.get("base_url"),
            }

        return {
            "token_cached": bool(payload.get("access_token")),
            "token_expires_at": datetime.fromtimestamp(expires_at).isoformat(),
            "token_expires_in_seconds": remaining,
            "resolved_base_url": payload.get("base_url"),
        }
    except Exception:
        return {
            "token_cached": False,
            "token_expires_at": None,
            "token_expires_in_seconds": None,
            "resolved_base_url": None,
        }


def _kis_guidance(configured: bool, token_cached: bool, token_remaining: int | None) -> list[str]:
    guidance: list[str] = []
    if not configured:
        guidance.append("KIS App Key/App Secret이 설정되지 않아 분봉은 저장·공개 데이터 위주로 동작합니다.")
    elif not token_cached:
        guidance.append("아직 활성 KIS 토큰이 없습니다. 첫 실시간 요청 시 토큰이 발급됩니다.")
    elif token_remaining is not None and token_remaining < 60 * 60:
        guidance.append("KIS 토큰 만료가 1시간 이내입니다. 만료 후 다음 실시간 요청에서 새 토큰이 발급됩니다.")
    else:
        guidance.append("KIS 토큰이 캐시되어 있어 잦은 재발급 없이 분봉 요청을 처리할 수 있습니다.")

    guidance.append("KIS 토큰은 파일과 Redis 캐시를 먼저 확인하므로 24시간 내 불필요한 재발급을 줄이도록 설계되어 있습니다.")
    guidance.append("분봉 정확도는 실시간 KIS 데이터와 로컬 분봉 저장 캐시가 쌓일수록 더 좋아집니다.")
    return guidance


@router.get("/status", response_model=RuntimeStatusResponse)
async def get_runtime_status() -> RuntimeStatusResponse:
    kis = get_kis_client()
    token_status = _read_token_cache_status(settings.kis_token_cache_path)
    runtime_token_status = await kis.get_cached_token_status()
    cache_status = await cache_backend_status()
    intraday_store_status = await get_intraday_store().get_status()
    configured = kis.configured
    token_cached = bool(token_status["token_cached"] or runtime_token_status["token_cached"])
    token_remaining = token_status["token_expires_in_seconds"]

    return RuntimeStatusResponse(
        generated_at=datetime.utcnow().isoformat(),
        app_name=settings.app_name,
        debug=settings.debug,
        kis=KisRuntimeStatus(
            configured=configured,
            environment=settings.kis_env,
            token_cached=token_cached,
            token_expires_at=token_status["token_expires_at"],
            token_expires_in_seconds=token_remaining,
            resolved_base_url=token_status["resolved_base_url"] or runtime_token_status["resolved_base_url"] or kis._resolved_base_url,
            token_cache_path=settings.kis_token_cache_path,
            max_concurrent_requests=settings.kis_max_concurrent_requests,
            request_spacing_ms=settings.kis_request_spacing_ms,
            guidance=_kis_guidance(configured, token_cached, token_remaining),
            last_prime=_get_kis_prime_status(),
        ),
        cache=CacheRuntimeStatus(**cache_status),
        intraday_store=IntradayStoreStatus(**intraday_store_status),
        scheduler_enabled=True,
        scheduled_warmups=SCHEDULED_INTRADAY_WARMUP_PLANS,
        data_notes=[
            "월봉·주봉·일봉은 KRX 일봉 데이터를 기준으로 집계합니다.",
            "분봉은 KIS 당일 분봉, Yahoo 공개 분봉, 로컬 저장 캐시를 조합해 사용합니다.",
            "운영 중에는 모든 분봉 후보를 실시간 호출하지 않고, 우선순위가 높은 후보부터 예열하는 방식으로 비용과 호출 수를 관리합니다.",
        ],
    )


@router.get("/scan-history", response_model=list[ScanHistoryRunSummary])
async def get_scan_history(
    timeframe: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=30),
) -> list[ScanHistoryRunSummary]:
    rows = await list_recent_scan_runs(limit=limit, timeframe=timeframe)
    return [ScanHistoryRunSummary(**row) for row in rows]


@router.get("/scan-quality-report", response_model=ScanQualityReportResponse)
async def get_scan_quality_report(
    timeframe: str = Query(default="1d"),
    lookback_days: int = Query(default=180, ge=30, le=730),
    forward_bars: int = Query(default=20, ge=5, le=60),
) -> ScanQualityReportResponse:
    payload = await build_scan_quality_report(
        timeframe=timeframe,
        lookback_days=lookback_days,
        forward_bars=forward_bars,
    )
    return ScanQualityReportResponse(**payload)


async def _resolve_kis_prime_symbol(symbol: str | None) -> str:
    normalized = _normalize_symbol_codes([symbol] if symbol else [], max_count=1)
    if normalized:
        return normalized[0]

    rows = await get_scan_results("1d")
    for row in rows:
        code = str(row.get("code") or "").strip()
        if code:
            return code.zfill(6) if code.isdigit() else code
    return "005930"


async def _prime_kis_once(
    *,
    symbol: str | None,
    timeframe: str,
    triggered_by: str,
) -> KisPrimeStatus:
    requested_at = datetime.utcnow().isoformat()
    kis = get_kis_client()
    if timeframe not in {"1m", "15m", "30m", "60m"}:
        raise HTTPException(status_code=422, detail=f"Unsupported intraday timeframe: {timeframe}")

    token_before = _read_token_cache_status(settings.kis_token_cache_path)
    runtime_token_before = await kis.get_cached_token_status()
    store_before = await get_intraday_store().get_status()
    resolved_symbol = await _resolve_kis_prime_symbol(symbol)

    _set_kis_prime_status(
        status="running",
        is_running=True,
        requested_at=requested_at,
        finished_at=None,
        triggered_by=triggered_by,
        symbol=resolved_symbol,
        timeframe=timeframe,
        ok=None,
        token_cached_before=bool(token_before["token_cached"] or runtime_token_before["token_cached"]),
        token_cached_after=False,
        token_expires_at=None,
        token_expires_in_seconds=None,
        resolved_base_url=token_before.get("resolved_base_url"),
        store_rows_before=int(store_before.get("total_rows", 0)),
        store_rows_after=int(store_before.get("total_rows", 0)),
        store_rows_added=0,
        bars_returned=0,
        data_source=None,
        fetch_status=None,
        message=None,
        last_error=None,
    )

    if not kis.configured:
        result = KisPrimeStatus(
            status="error",
            is_running=False,
            requested_at=requested_at,
            finished_at=datetime.utcnow().isoformat(),
            triggered_by=triggered_by,
            symbol=resolved_symbol,
            timeframe=timeframe,
            ok=False,
            token_cached_before=bool(token_before["token_cached"] or runtime_token_before["token_cached"]),
            token_cached_after=False,
            resolved_base_url=token_before.get("resolved_base_url"),
            store_rows_before=int(store_before.get("total_rows", 0)),
            store_rows_after=int(store_before.get("total_rows", 0)),
            store_rows_added=0,
            bars_returned=0,
            data_source="kis_intraday",
            fetch_status="kis_not_configured",
            message="KIS API 자격 증명이 비어 있어 토큰을 발급할 수 없습니다.",
            last_error="kis_not_configured",
        )
        _set_kis_prime_status(**result.model_dump())
        return result

    try:
        await kis.ensure_access_token()
        fetcher = get_data_fetcher()
        df = await fetcher.get_stock_ohlcv_by_timeframe(
            resolved_symbol,
            timeframe,
            lookback_days=2,
            allow_live_intraday=True,
        )
        token_after = _read_token_cache_status(settings.kis_token_cache_path)
        runtime_token_after = await kis.get_cached_token_status()
        store_after = await get_intraday_store().get_status()

        fetch_status = str(df.attrs.get("fetch_status") or "live_ok")
        message = str(df.attrs.get("fetch_message") or "KIS 토큰 프라이밍과 분봉 확인이 완료되었습니다.")
        token_cached_after = bool(token_after["token_cached"] or runtime_token_after["token_cached"])
        result = KisPrimeStatus(
            status="ready",
            is_running=False,
            requested_at=requested_at,
            finished_at=datetime.utcnow().isoformat(),
            triggered_by=triggered_by,
            symbol=resolved_symbol,
            timeframe=timeframe,
            ok=bool(token_cached_after or len(df) > 0),
            token_cached_before=bool(token_before["token_cached"] or runtime_token_before["token_cached"]),
            token_cached_after=token_cached_after,
            token_expires_at=token_after["token_expires_at"],
            token_expires_in_seconds=token_after["token_expires_in_seconds"],
            resolved_base_url=token_after["resolved_base_url"] or runtime_token_after["resolved_base_url"] or kis._resolved_base_url,
            store_rows_before=int(store_before.get("total_rows", 0)),
            store_rows_after=int(store_after.get("total_rows", 0)),
            store_rows_added=max(0, int(store_after.get("total_rows", 0)) - int(store_before.get("total_rows", 0))),
            bars_returned=int(len(df)),
            data_source=str(df.attrs.get("data_source") or "unknown"),
            fetch_status=fetch_status,
            message=message,
            last_error=None,
        )
        _set_kis_prime_status(**result.model_dump())
        return result
    except Exception as exc:
        token_after = _read_token_cache_status(settings.kis_token_cache_path)
        runtime_token_after = await kis.get_cached_token_status()
        store_after = await get_intraday_store().get_status()
        result = KisPrimeStatus(
            status="error",
            is_running=False,
            requested_at=requested_at,
            finished_at=datetime.utcnow().isoformat(),
            triggered_by=triggered_by,
            symbol=resolved_symbol,
            timeframe=timeframe,
            ok=False,
            token_cached_before=bool(token_before["token_cached"] or runtime_token_before["token_cached"]),
            token_cached_after=bool(token_after["token_cached"] or runtime_token_after["token_cached"]),
            token_expires_at=token_after["token_expires_at"],
            token_expires_in_seconds=token_after["token_expires_in_seconds"],
            resolved_base_url=token_after["resolved_base_url"] or runtime_token_after["resolved_base_url"] or kis._resolved_base_url,
            store_rows_before=int(store_before.get("total_rows", 0)),
            store_rows_after=int(store_after.get("total_rows", 0)),
            store_rows_added=max(0, int(store_after.get("total_rows", 0)) - int(store_before.get("total_rows", 0))),
            bars_returned=0,
            data_source="kis_intraday",
            fetch_status="kis_error",
            message="KIS 토큰 프라이밍 또는 첫 분봉 수집이 실패했습니다.",
            last_error=str(exc),
        )
        _set_kis_prime_status(**result.model_dump())
        return result


def _normalize_symbol_codes(symbols: list[str], max_count: int = 50) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for symbol in symbols:
        code = str(symbol).strip()
        if not code:
            continue
        if code.isdigit():
            code = code.zfill(6)
        if code not in seen:
            seen.add(code)
            normalized.append(code)
    return normalized[:max_count]


def _normalize_intraday_timeframes(timeframes: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for timeframe in timeframes:
        value = str(timeframe).strip()
        if not value or value in seen:
            continue
        if not is_intraday_timeframe(value):
            raise HTTPException(status_code=422, detail=f"Unsupported intraday timeframe: {value}")
        get_timeframe_spec(value)
        seen.add(value)
        normalized.append(value)
    return normalized or ["15m", "30m", "60m"]


def _set_warmup_status(**kwargs: Any) -> None:
    _warmup_status.update(kwargs)


def _get_warmup_status(trigger_accepted: bool | None = None) -> IntradayWarmupJobStatus:
    payload = dict(_warmup_status)
    if trigger_accepted is not None:
        payload["trigger_accepted"] = trigger_accepted
    return IntradayWarmupJobStatus(**payload)


def _set_kis_prime_status(**kwargs: Any) -> None:
    _kis_prime_status.update(kwargs)


def _get_kis_prime_status() -> KisPrimeStatus:
    return KisPrimeStatus(**dict(_kis_prime_status))


async def _candidate_symbols_for_warmup(request: IntradayCandidateWarmupRequest) -> list[str]:
    source_timeframe = str(request.source_timeframe or "1d")
    if source_timeframe not in {"1mo", "1wk", "1d", "60m", "30m", "15m", "1m"}:
        raise HTTPException(status_code=422, detail=f"Unsupported source timeframe: {source_timeframe}")

    rows = await get_scan_results(source_timeframe)
    candidates = [
        row
        for row in rows
        if row.get("code") and not row.get("no_signal_flag") and row.get("action_plan") != "cooling"
    ]
    candidates.sort(
        key=lambda row: (
            float(row.get("action_priority_score", 0.0)),
            float(row.get("composite_score", 0.0)),
            float(row.get("entry_score", 0.0)),
            float(row.get("data_quality", 0.0)),
        ),
        reverse=True,
    )
    return _normalize_symbol_codes([str(row["code"]) for row in candidates[: request.limit]], max_count=request.limit)


async def _run_intraday_warmup(
    *,
    symbols: list[str],
    timeframes: list[str],
    allow_live: bool,
    lookback_days: int | None,
    on_result: Any | None = None,
) -> IntradayWarmupResponse:
    symbols = _normalize_symbol_codes(symbols)
    fetcher = get_data_fetcher()
    semaphore = asyncio.Semaphore(3 if allow_live else 6)
    results: list[IntradayWarmupResult] = []

    async def collect(symbol: str, timeframe: str) -> IntradayWarmupResult:
        async with semaphore:
            try:
                spec = get_timeframe_spec(timeframe)
                days = lookback_days or spec.chart_lookback_days
                df = await fetcher.get_stock_ohlcv_by_timeframe(
                    symbol,
                    timeframe,
                    lookback_days=days,
                    allow_live_intraday=allow_live,
                )
                return IntradayWarmupResult(
                    symbol=symbol,
                    timeframe=timeframe,
                    ok=not df.empty,
                    bars=int(len(df)),
                    data_source=str(df.attrs.get("data_source") or "unknown"),
                    fetch_status=str(df.attrs.get("fetch_status") or "unknown"),
                    message=str(df.attrs.get("fetch_message") or ""),
                )
            except Exception as exc:
                return IntradayWarmupResult(
                    symbol=symbol,
                    timeframe=timeframe,
                    ok=False,
                    bars=0,
                    data_source="error",
                    fetch_status="error",
                    message=str(exc),
                )

    tasks = [collect(symbol, timeframe) for symbol in symbols for timeframe in timeframes]
    for task in asyncio.as_completed(tasks):
        result = await task
        results.append(result)
        if on_result:
            on_result(result, len(results), len(tasks))
    success_count = sum(1 for result in results if result.ok)

    return IntradayWarmupResponse(
        requested_at=datetime.utcnow().isoformat(),
        allow_live=allow_live,
        symbols=symbols,
        timeframes=timeframes,
        total_requests=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        results=results,
    )


@router.post("/intraday/warmup", response_model=IntradayWarmupResponse)
async def warmup_intraday_cache(request: IntradayWarmupRequest) -> IntradayWarmupResponse:
    symbols = _normalize_symbol_codes(request.symbols)
    if not symbols:
        raise HTTPException(status_code=422, detail="At least one symbol is required.")

    timeframes = _normalize_intraday_timeframes(request.timeframes)
    return await _run_intraday_warmup(
        symbols=symbols,
        timeframes=timeframes,
        allow_live=request.allow_live,
        lookback_days=request.lookback_days,
    )


@router.post("/intraday/warmup-candidates", response_model=IntradayWarmupResponse)
async def warmup_intraday_candidates(request: IntradayCandidateWarmupRequest) -> IntradayWarmupResponse:
    timeframes = _normalize_intraday_timeframes(request.timeframes)
    symbols = await _candidate_symbols_for_warmup(request)
    if not symbols:
        raise HTTPException(status_code=404, detail="No eligible candidates were found for intraday warmup.")

    return await _run_intraday_warmup(
        symbols=symbols,
        timeframes=timeframes,
        allow_live=request.allow_live,
        lookback_days=request.lookback_days,
    )


@router.get("/intraday/warmup-status", response_model=IntradayWarmupJobStatus)
async def get_intraday_warmup_status() -> IntradayWarmupJobStatus:
    return _get_warmup_status()


@router.get("/kis/prime-status", response_model=KisPrimeStatus)
async def get_kis_prime_status() -> KisPrimeStatus:
    return _get_kis_prime_status()


@router.post("/kis/prime", response_model=KisPrimeStatus)
async def prime_kis_runtime(symbol: str | None = None, timeframe: str = "1m") -> KisPrimeStatus:
    return await _prime_kis_once(symbol=symbol, timeframe=timeframe, triggered_by="manual")


async def _run_warmup_background(
    *,
    source: str,
    symbols: list[str],
    timeframes: list[str],
    allow_live: bool,
    lookback_days: int | None,
) -> None:
    started_at = datetime.utcnow().isoformat()
    total_requests = len(symbols) * len(timeframes)
    _set_warmup_status(
        status="running",
        is_running=True,
        source=source,
        allow_live=allow_live,
        started_at=started_at,
        finished_at=None,
        total_requests=total_requests,
        completed_count=0,
        success_count=0,
        failure_count=0,
        symbols=symbols,
        timeframes=timeframes,
        last_error=None,
        trigger_accepted=True,
        results=[],
    )

    def on_result(result: IntradayWarmupResult, completed: int, total: int) -> None:
        current_results = list(_warmup_status.get("results") or [])
        current_results.append(result)
        success_count = sum(1 for item in current_results if item.ok)
        _set_warmup_status(
            total_requests=total,
            completed_count=completed,
            success_count=success_count,
            failure_count=completed - success_count,
            results=current_results[-30:],
        )

    try:
        response = await _run_intraday_warmup(
            symbols=symbols,
            timeframes=timeframes,
            allow_live=allow_live,
            lookback_days=lookback_days,
            on_result=on_result,
        )
        _set_warmup_status(
            status="ready",
            is_running=False,
            finished_at=datetime.utcnow().isoformat(),
            total_requests=response.total_requests,
            completed_count=response.total_requests,
            success_count=response.success_count,
            failure_count=response.failure_count,
            results=response.results[-30:],
        )
    except Exception as exc:
        _set_warmup_status(
            status="error",
            is_running=False,
            finished_at=datetime.utcnow().isoformat(),
            last_error=str(exc),
        )


def _trigger_background_warmup(
    *,
    source: str,
    symbols: list[str],
    timeframes: list[str],
    allow_live: bool,
    lookback_days: int | None,
) -> IntradayWarmupJobStatus:
    global _warmup_task
    if _warmup_task and not _warmup_task.done():
        return _get_warmup_status(trigger_accepted=False)

    _set_warmup_status(
        status="queued",
        is_running=True,
        source=source,
        allow_live=allow_live,
        started_at=datetime.utcnow().isoformat(),
        finished_at=None,
        total_requests=len(symbols) * len(timeframes),
        completed_count=0,
        success_count=0,
        failure_count=0,
        symbols=symbols,
        timeframes=timeframes,
        last_error=None,
        trigger_accepted=True,
        results=[],
    )
    _warmup_task = asyncio.create_task(
        _run_warmup_background(
            source=source,
            symbols=symbols,
            timeframes=timeframes,
            allow_live=allow_live,
            lookback_days=lookback_days,
        )
    )
    return _get_warmup_status(trigger_accepted=True)


def _scheduled_warmup_plan(plan_id: str) -> dict[str, Any] | None:
    return next((plan for plan in SCHEDULED_INTRADAY_WARMUP_PLANS if plan["id"] == plan_id), None)


async def run_scheduled_intraday_warmup(plan_id: str) -> IntradayWarmupJobStatus | None:
    plan = _scheduled_warmup_plan(plan_id)
    if not plan:
        return None

    request = IntradayCandidateWarmupRequest(
        source_timeframe=str(plan["source_timeframe"]),
        limit=int(plan["limit"]),
        timeframes=list(plan["timeframes"]),
        allow_live=bool(plan["allow_live"]),
    )
    timeframes = _normalize_intraday_timeframes(request.timeframes)
    symbols = await _candidate_symbols_for_warmup(request)
    if not symbols:
        return _get_warmup_status(trigger_accepted=False)

    return _trigger_background_warmup(
        source=f"scheduled:{plan_id}",
        symbols=symbols,
        timeframes=timeframes,
        allow_live=request.allow_live,
        lookback_days=request.lookback_days,
    )


@router.post("/intraday/warmup/background", response_model=IntradayWarmupJobStatus)
async def trigger_intraday_warmup_background(request: IntradayWarmupRequest) -> IntradayWarmupJobStatus:
    symbols = _normalize_symbol_codes(request.symbols)
    if not symbols:
        raise HTTPException(status_code=422, detail="At least one symbol is required.")
    timeframes = _normalize_intraday_timeframes(request.timeframes)
    return _trigger_background_warmup(
        source="manual_symbols",
        symbols=symbols,
        timeframes=timeframes,
        allow_live=request.allow_live,
        lookback_days=request.lookback_days,
    )


@router.post("/intraday/warmup-candidates/background", response_model=IntradayWarmupJobStatus)
async def trigger_intraday_candidate_warmup_background(request: IntradayCandidateWarmupRequest) -> IntradayWarmupJobStatus:
    timeframes = _normalize_intraday_timeframes(request.timeframes)
    symbols = await _candidate_symbols_for_warmup(request)
    if not symbols:
        raise HTTPException(status_code=404, detail="No eligible candidates were found for intraday warmup.")
    return _trigger_background_warmup(
        source=f"candidates:{request.source_timeframe}",
        symbols=symbols,
        timeframes=timeframes,
        allow_live=request.allow_live,
        lookback_days=request.lookback_days,
    )


def trigger_background_kis_prime(*, symbol: str | None = None, timeframe: str = "1m", triggered_by: str = "startup") -> bool:
    global _kis_prime_task
    if _kis_prime_task and not _kis_prime_task.done():
        return False

    async def _runner() -> None:
        await _prime_kis_once(symbol=symbol, timeframe=timeframe, triggered_by=triggered_by)

    _kis_prime_task = asyncio.create_task(_runner())
    return True
