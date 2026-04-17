from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from ..schemas import AnalysisResult, OHLCVBar, PriceInfo, SymbolInfo
from ...core.config import get_settings
from ...core.redis import cache_get, cache_set
from ...services.analysis_service import analyze_symbol_dataframe
from ...services.data_fetcher import get_data_fetcher
from ...services.timeframe_service import DEFAULT_TIMEFRAME, SUPPORTED_TIMEFRAMES, get_timeframe_spec, is_intraday_timeframe

router = APIRouter(prefix="/symbols", tags=["symbols"])
settings = get_settings()


def _validate_timeframe(timeframe: str) -> str:
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe. Available: {', '.join(SUPPORTED_TIMEFRAMES)}",
        )
    return timeframe


def _frame_to_bars(df, timeframe: str) -> list[OHLCVBar]:
    timestamp_key = "datetime" if is_intraday_timeframe(timeframe) else "date"
    bars: list[OHLCVBar] = []
    for _, row in df.iterrows():
        amount = row.get("amount")
        stamp = row[timestamp_key]
        timestamp = stamp.isoformat() if timestamp_key == "datetime" else str(stamp)[:10]
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
    return bars


@router.get("/search")
async def search_symbols(q: str = Query(min_length=1)) -> list[SymbolInfo]:
    fetcher = get_data_fetcher()
    universe = await fetcher.get_universe()
    if universe.empty:
        return []

    query = q.strip().lower()
    code_match = universe["code"].astype(str).str.lower().str.contains(query, na=False)
    name_match = universe["name"].fillna("").astype(str).str.lower().str.contains(query, na=False)

    results = universe[code_match | name_match].copy()
    if results.empty:
        return []

    results["match_score"] = 0
    results.loc[results["code"].astype(str).str.lower() == query, "match_score"] += 100
    results.loc[results["code"].astype(str).str.lower().str.startswith(query), "match_score"] += 50
    results.loc[results["name"].fillna("").astype(str).str.lower().str.startswith(query), "match_score"] += 25
    results = results.sort_values(["match_score", "market", "code"], ascending=[False, True, True]).head(20)

    out: list[SymbolInfo] = []
    for _, row in results.iterrows():
        out.append(
            SymbolInfo(
                code=row["code"],
                name=row.get("name") or row["code"],
                market=row["market"],
                sector=None,
                market_cap=None,
                is_in_universe=True,
            )
        )
    return out


@router.get("/{symbol}/bars")
async def get_bars(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    days: int = Query(default=180, ge=5, le=4000),
) -> list[OHLCVBar]:
    timeframe = _validate_timeframe(timeframe)
    cache_key = f"bars:v2:{symbol}:{timeframe}:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return [OHLCVBar(**bar) for bar in cached]

    fetcher = get_data_fetcher()
    df = await fetcher.get_stock_ohlcv_by_timeframe(symbol, timeframe, lookback_days=days)
    ttl = settings.intraday_bars_ttl if is_intraday_timeframe(timeframe) else settings.daily_bars_ttl

    if df.empty:
        return []

    bars = _frame_to_bars(df, timeframe)
    await cache_set(cache_key, [bar.model_dump() for bar in bars], ttl)
    return bars


@router.get("/{symbol}/analysis")
async def get_analysis(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> AnalysisResult:
    timeframe = _validate_timeframe(timeframe)
    cache_key = f"analysis:v2:{symbol}:{timeframe}"
    cached = await cache_get(cache_key)
    if cached:
        return AnalysisResult(**cached)

    fetcher = get_data_fetcher()
    spec = get_timeframe_spec(timeframe)
    df = await fetcher.get_stock_ohlcv_by_timeframe(symbol, timeframe, lookback_days=spec.analysis_lookback_days)

    name = await fetcher.get_stock_name(symbol)
    market_cap = await fetcher.get_market_cap(symbol)
    universe = await fetcher.get_universe()
    market = "KRX"
    if not universe.empty and "code" in universe.columns:
        matched = universe.loc[universe["code"] == symbol]
        if not matched.empty:
            market = matched.iloc[0]["market"]

    symbol_info = SymbolInfo(
        code=symbol,
        name=name,
        market=market,
        sector=None,
        market_cap=market_cap,
        is_in_universe=market_cap is not None and market_cap >= 500,
    )

    result = AnalysisResult(**(await analyze_symbol_dataframe(symbol_info=symbol_info, timeframe=timeframe, df=df)))

    await cache_set(cache_key, result.model_dump(), settings.pattern_cache_ttl)
    return result


@router.get("/{symbol}/price")
async def get_price(symbol: str) -> PriceInfo:
    """Returns current price, previous close, and change information."""
    cache_key = f"price:{symbol}"
    cached = await cache_get(cache_key)
    if cached:
        return PriceInfo(**cached)

    fetcher = get_data_fetcher()

    # Try KIS first (real-time if configured)
    from ...services.kis_client import get_kis_client
    kis = get_kis_client()
    if kis.configured:
        try:
            kis_data = await kis.fetch_current_price(symbol)
            if kis_data and kis_data.get("close"):
                # Get prev close from pykrx for change calculation
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
        except Exception as exc:
            pass  # fall through to pykrx

    # pykrx fallback: get last 2 trading days
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
