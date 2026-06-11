from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

_logger = logging.getLogger(__name__)

from ..schemas import AnalysisResult, OHLCVBar, PriceInfo, ReferenceCaseResponse, SymbolInfo
from ...core.config import get_settings
from ...core.redis import cache_get, cache_set
from ...services.analysis_service import analyze_symbol_dataframe, build_no_signal_snapshot
import pandas as pd

from ...services.data_fetcher import UNIVERSE_CACHE_KEY, get_data_fetcher
from ...services.reference_case_service import build_reference_cases, schedule_reference_case_warmup
from ...services.scanner import FALLBACK_CODES, get_scan_results
from ...services.timeframe_service import DEFAULT_TIMEFRAME, SUPPORTED_TIMEFRAMES, get_timeframe_spec

router = APIRouter(prefix="/symbols", tags=["symbols"])
settings = get_settings()
POPULAR_SEARCH_CODES = {code for code, _, _ in FALLBACK_CODES}


def _validate_timeframe(timeframe: str) -> str:
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(status_code=422, detail=f"Unsupported timeframe: {timeframe}")
    return timeframe


async def _get_search_universe(fetcher) -> pd.DataFrame:
    # Fast path: universe already cached → return immediately (no pykrx call)
    cached_raw = await cache_get(UNIVERSE_CACHE_KEY)
    if cached_raw:
        return pd.DataFrame(cached_raw)

    # Cache miss: return fast fallback (scan results + hardcoded codes) immediately
    # and kick off background warmup so subsequent searches are fast.
    asyncio.create_task(fetcher.get_universe())

    rows: list[dict] = []
    seen: set[str] = set()
    try:
        cached_scan = await get_scan_results(DEFAULT_TIMEFRAME)
        for row in cached_scan:
            code = row.get("code") or row.get("symbol", {}).get("code", "")
            if code and code not in seen:
                seen.add(code)
                rows.append({
                    "code": code,
                    "name": row.get("name") or row.get("symbol", {}).get("name", code),
                    "market": row.get("market") or row.get("symbol", {}).get("market", "KRX"),
                })
    except Exception:
        pass

    for code, name, market in FALLBACK_CODES:
        if code not in seen:
            seen.add(code)
            rows.append({"code": code, "name": name, "market": market})

    return pd.DataFrame(rows, columns=["code", "name", "market"]) if rows else pd.DataFrame()


@router.get("/search")
async def search_symbols(q: str = Query(min_length=1)) -> list[SymbolInfo]:
    fetcher = get_data_fetcher()
    universe = await _get_search_universe(fetcher)
    if universe.empty:
        return []

    query = q.strip().lower()
    code_match = universe["code"].astype(str).str.lower().str.contains(query, na=False, regex=False)
    name_match = universe["name"].fillna("").astype(str).str.lower().str.contains(query, na=False, regex=False)

    results = universe[code_match | name_match].copy()
    if results.empty:
        return []

    results["match_score"] = 0
    results.loc[results["code"].astype(str).str.lower() == query, "match_score"] += 100
    results.loc[results["code"].astype(str).str.lower().str.startswith(query), "match_score"] += 50
    results.loc[results["name"].fillna("").astype(str).str.lower() == query, "match_score"] += 80
    results.loc[results["name"].fillna("").astype(str).str.lower().str.startswith(query), "match_score"] += 25
    results.loc[results["name"].fillna("").astype(str).str.lower().str.contains(query, regex=False), "match_score"] += 10
    results.loc[results["code"].astype(str).isin(POPULAR_SEARCH_CODES), "match_score"] += 15
    results.loc[results["name"].fillna("").astype(str).str.contains("스팩", na=False), "match_score"] -= 60
    results.loc[results["name"].fillna("").astype(str).str.endswith("우", na=False), "match_score"] -= 20
    results["name_length"] = results["name"].fillna("").astype(str).str.len()
    results = results.sort_values(["match_score", "name_length", "market", "code"], ascending=[False, True, True, True]).head(20)

    return [
        SymbolInfo(
            code=row["code"],
            name=row.get("name") or row["code"],
            market=row["market"],
            sector=None,
            market_cap=None,
            is_in_universe=True,
        )
        for _, row in results.iterrows()
    ]


@router.get("/{symbol}/bars")
async def get_bars(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    days: int | None = Query(default=None, ge=10, le=3650),
) -> list[OHLCVBar]:
    timeframe = _validate_timeframe(timeframe)
    spec = get_timeframe_spec(timeframe)
    lookback_days = days or spec.chart_lookback_days
    cache_key = f"bars:v3:{symbol}:{timeframe}:{lookback_days}"
    cached = await cache_get(cache_key)
    if cached:
        return [OHLCVBar(**bar) for bar in cached]

    fetcher = get_data_fetcher()
    try:
        if spec.intraday:
            df = await asyncio.wait_for(
                fetcher.get_stock_ohlcv_by_timeframe(symbol, timeframe, lookback_days=lookback_days),
                timeout=18,
            )
        else:
            df = await fetcher.get_stock_ohlcv_by_timeframe(symbol, timeframe, lookback_days=lookback_days)
    except TimeoutError:
        df = pd.DataFrame()
    if df.empty:
        return []

    ts_col = "datetime" if "datetime" in df.columns else "date"
    bars: list[OHLCVBar] = []
    for _, row in df.iterrows():
        amount = row.get("amount")
        timestamp = (
            row[ts_col].isoformat()
            if hasattr(row[ts_col], "isoformat") and ts_col == "datetime"
            else str(row[ts_col])[:10]
        )
        bars.append(
            OHLCVBar(
                date=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                amount=float(amount) if amount is not None and str(amount) != "nan" else None,
            )
        )

    ttl = settings.intraday_bars_ttl if spec.intraday else settings.daily_bars_ttl
    await cache_set(cache_key, [bar.model_dump() for bar in bars], ttl)
    return bars


@router.get("/{symbol}/analysis")
async def get_analysis(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> AnalysisResult:
    timeframe = _validate_timeframe(timeframe)
    cache_key = f"analysis:v12:{symbol}:{timeframe}"
    cached = await cache_get(cache_key)
    if cached:
        return AnalysisResult(**cached)

    fetcher = get_data_fetcher()
    df = await fetcher.get_stock_ohlcv_by_timeframe(symbol, timeframe)

    name = await fetcher.get_stock_name(symbol)
    market_cap = await fetcher.get_market_cap(symbol)

    # universe는 캐시가 있을 때만 조회 (없으면 "KRX" 기본값)
    # get_universe() 직접 await는 최대 50초 블로킹 → 분석 API 타임아웃의 주범
    market = "KRX"
    _cached_univ = await cache_get(UNIVERSE_CACHE_KEY)
    if _cached_univ:
        _univ_df = pd.DataFrame(_cached_univ)
        _matched = _univ_df.loc[_univ_df["code"] == symbol]
        if not _matched.empty:
            market = str(_matched.iloc[0]["market"])

    symbol_info = SymbolInfo(
        code=symbol,
        name=name,
        market=market,
        sector=None,
        market_cap=market_cap,
        is_in_universe=market_cap is not None and market_cap >= settings.min_market_cap_billion,
    )

    try:
        result = (
            await analyze_symbol_dataframe(symbol_info, timeframe, df)
            if not df.empty
            else build_no_signal_snapshot(symbol_info, timeframe, df)
        )
    except Exception as _exc:
        tb = traceback.format_exc()
        _logger.error("analyze_symbol_dataframe failed for %s/%s: %s\n%s", symbol, timeframe, _exc, tb)
        raise HTTPException(status_code=500, detail=f"Analysis error: {type(_exc).__name__}: {_exc}")
    await cache_set(cache_key, result.model_dump(), settings.pattern_cache_ttl)
    await schedule_reference_case_warmup(symbol_code=symbol, timeframe=timeframe, analysis=result, limit=3)
    return result


@router.get("/{symbol}/reference-cases")
async def get_reference_cases(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=6, ge=1, le=12),
) -> ReferenceCaseResponse:
    timeframe = _validate_timeframe(timeframe)

    fetcher = get_data_fetcher()
    df = await fetcher.get_stock_ohlcv_by_timeframe(symbol, timeframe)

    name = await fetcher.get_stock_name(symbol)
    market_cap = await fetcher.get_market_cap(symbol)

    market = "KRX"
    _cached_univ2 = await cache_get(UNIVERSE_CACHE_KEY)
    if _cached_univ2:
        _univ_df2 = pd.DataFrame(_cached_univ2)
        _matched2 = _univ_df2.loc[_univ_df2["code"] == symbol]
        if not _matched2.empty:
            market = str(_matched2.iloc[0]["market"])

    symbol_info = SymbolInfo(
        code=symbol,
        name=name,
        market=market,
        sector=None,
        market_cap=market_cap,
        is_in_universe=market_cap is not None and market_cap >= settings.min_market_cap_billion,
    )

    analysis = (
        await analyze_symbol_dataframe(symbol_info, timeframe, df)
        if not df.empty
        else build_no_signal_snapshot(symbol_info, timeframe, df)
    )
    return await build_reference_cases(symbol_code=symbol, timeframe=timeframe, analysis=analysis, limit=limit)


@router.get("/{symbol}/price")
async def get_price(symbol: str) -> PriceInfo:
    cache_key = f"price:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        return PriceInfo(**cached)

    fetcher = get_data_fetcher()
    from ...services.kis_client import get_kis_client

    kis = get_kis_client()
    if kis.configured:
        try:
            kis_data = await kis.fetch_current_price(symbol)
            if kis_data and kis_data.get("close"):
                end = date.today()
                start = end - timedelta(days=5)
                hist = await fetcher.get_stock_ohlcv(symbol, start, end)
                prev_close = float(hist["close"].iloc[-2]) if len(hist) >= 2 else float(hist["close"].iloc[-1])
                close = float(kis_data["close"])
                change = close - prev_close
                change_pct = change / prev_close if prev_close else 0.0
                info = PriceInfo(
                    code=symbol,
                    close=close,
                    prev_close=prev_close,
                    change=round(change, 2),
                    change_pct=round(change_pct, 4),
                    volume=kis_data.get("volume") or 0,
                    source="kis",
                    timestamp=kis_data.get("timestamp"),
                )
                await cache_set(cache_key, info.model_dump(), ttl=60)
                return info
        except Exception:
            pass

    try:
        end = date.today()
        start = end - timedelta(days=5)
        hist = await fetcher.get_stock_ohlcv(symbol, start, end)
        if not hist.empty:
            close = float(hist["close"].iloc[-1])
            prev_close = float(hist["close"].iloc[-2]) if len(hist) >= 2 else close
            change = close - prev_close
            change_pct = change / prev_close if prev_close else 0.0
            volume = int(hist["volume"].iloc[-1])
            info = PriceInfo(
                code=symbol,
                close=close,
                prev_close=prev_close,
                change=round(change, 2),
                change_pct=round(change_pct, 4),
                volume=volume,
                source="pykrx",
                timestamp=str(hist["date"].iloc[-1])[:10],
            )
            await cache_set(cache_key, info.model_dump(), ttl=300)
            return info
    except Exception:
        pass

    return PriceInfo(code=symbol, close=0.0, prev_close=0.0, change=0.0, change_pct=0.0, volume=0, source="none")


@router.get("/{symbol}/money-flow")
async def get_money_flow_endpoint(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    pattern_type: str | None = Query(default=None),
) -> dict:
    """외국인/기관 순매수 데이터 (T+1). 4시간 캐시.

    pattern_type을 쿼리로 받으면 그대로 정렬 판정에 사용 (프론트가 분석 결과를
    이미 알고 있을 때). 없으면 분석 캐시 참조 — 단, 분석·수급을 동시 요청하는
    첫 방문에는 캐시가 비어 '패턴 없음'으로 빠질 수 있어 쿼리 전달이 정확하다.
    """
    from ...services.money_flow_service import get_money_flow

    if pattern_type is None:
        cached_analysis = await cache_get(f"analysis:v12:{symbol}:{timeframe}")
        if isinstance(cached_analysis, dict) and cached_analysis.get("patterns"):
            pats = cached_analysis["patterns"]
            if pats and isinstance(pats[0], dict):
                pattern_type = pats[0].get("pattern_type")

    result = await get_money_flow(symbol, pattern_type)
    if result is None:
        return {
            "foreign_net_3d": 0.0,
            "foreign_net_10d": 0.0,
            "institution_net_3d": 0.0,
            "institution_net_10d": 0.0,
            "alignment": "neutral",
            "alignment_label": "수급 데이터 없음",
            "alignment_note": "",
            "daily": [],
        }
    return result
