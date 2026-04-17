from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query

from ..schemas import AnalysisResult, OHLCVBar, PatternInfo, PriceInfo, SymbolInfo
from ...core.config import get_settings
from ...core.redis import cache_get, cache_set
from ...services.backtest_engine import get_win_rate
from ...services.data_fetcher import get_data_fetcher
from ...services.pattern_engine import PatternEngine
from ...services.probability_engine import compute_probability

router = APIRouter(prefix="/symbols", tags=["symbols"])
settings = get_settings()

TIMEFRAME_LABELS = {
    "1d": "일봉",
    "60m": "60분",
    "15m": "15분",
}


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
    timeframe: str = Query(default="1d", pattern="^(1d|60m|15m)$"),
    days: int = Query(default=180, ge=10, le=1000),
) -> list[OHLCVBar]:
    cache_key = f"bars:{symbol}:{timeframe}:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return [OHLCVBar(**bar) for bar in cached]

    fetcher = get_data_fetcher()
    end = date.today()

    if timeframe == "1d":
        start = end - timedelta(days=days)
        df = await fetcher.get_stock_ohlcv(symbol, start, end)
        ttl = settings.daily_bars_ttl
    else:
        df = await fetcher.get_stock_intraday_ohlcv(symbol, timeframe, days)
        ttl = settings.intraday_bars_ttl

    if df.empty:
        return []

    bars: list[OHLCVBar] = []
    for _, row in df.iterrows():
        amount = row.get("amount")
        timestamp = str(row["date"])[:10] if timeframe == "1d" else row["datetime"].isoformat()
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

    await cache_set(cache_key, [bar.model_dump() for bar in bars], ttl)
    return bars


@router.get("/{symbol}/analysis")
async def get_analysis(
    symbol: str,
    timeframe: str = Query(default="1d", pattern="^(1d|60m|15m)$"),
) -> AnalysisResult:
    cache_key = f"analysis:{symbol}:{timeframe}"
    cached = await cache_get(cache_key)
    if cached:
        return AnalysisResult(**cached)

    fetcher = get_data_fetcher()
    end = date.today()
    if timeframe == "1d":
        df = await fetcher.get_stock_ohlcv(symbol, end - timedelta(days=365), end)
    else:
        intraday_days = 90 if timeframe == "60m" else 30
        df = await fetcher.get_stock_intraday_ohlcv(symbol, timeframe, intraday_days)

    name = await fetcher.get_stock_name(symbol)
    market_cap = await fetcher.get_market_cap(symbol)
    universe = await fetcher.get_universe()
    matched = universe.loc[universe["code"] == symbol]
    market = matched.iloc[0]["market"] if not matched.empty else "KRX"

    symbol_info = SymbolInfo(
        code=symbol,
        name=name,
        market=market,
        sector=None,
        market_cap=market_cap,
        is_in_universe=market_cap is not None and market_cap >= 500,
    )

    if df.empty or len(df) < 20:
        timeframe_label = TIMEFRAME_LABELS[timeframe]
        return AnalysisResult(
            symbol=symbol_info,
            timeframe=timeframe,
            p_up=0.5,
            p_down=0.5,
            textbook_similarity=0.0,
            pattern_confirmation_score=0.0,
            confidence=0.0,
            entry_score=0.0,
            no_signal_flag=True,
            no_signal_reason="데이터 부족",
            reason_summary=f"{timeframe_label} 기준으로 패턴을 판단하기에 충분한 캔들이 아직 쌓이지 않았습니다.",
            sample_size=0,
            patterns=[],
            is_provisional=True,
            updated_at=datetime.utcnow().isoformat(),
        )

    engine = PatternEngine()
    pattern_results = engine.detect_all(df)

    patterns = [
        PatternInfo(
            pattern_type=pattern.pattern_type,
            state=pattern.state,
            grade=pattern.grade,
            textbook_similarity=pattern.textbook_similarity,
            geometry_fit=pattern.geometry_fit,
            neckline=pattern.neckline,
            invalidation_level=pattern.invalidation_level,
            target_level=pattern.target_level,
            key_points=pattern.key_points,
            is_provisional=pattern.is_provisional,
            start_dt=pattern.start_dt.isoformat(),
            end_dt=pattern.end_dt.isoformat() if pattern.end_dt else None,
        )
        for pattern in pattern_results
    ]

    best_pattern = max(pattern_results, key=lambda pattern: pattern.textbook_similarity) if pattern_results else None

    if best_pattern:
        win_rate = await get_win_rate(best_pattern.pattern_type)
        prob = compute_probability(best_pattern, similar_win_rate=win_rate, sample_size=50)
        result = AnalysisResult(
            symbol=symbol_info,
            timeframe=timeframe,
            p_up=prob.p_up,
            p_down=prob.p_down,
            textbook_similarity=prob.textbook_similarity,
            pattern_confirmation_score=prob.pattern_confirmation_score,
            confidence=prob.confidence,
            entry_score=prob.entry_score,
            no_signal_flag=prob.no_signal_flag,
            no_signal_reason=prob.no_signal_reason,
            reason_summary=prob.reason_summary,
            sample_size=prob.sample_size,
            patterns=patterns,
            is_provisional=best_pattern.is_provisional,
            updated_at=datetime.utcnow().isoformat(),
        )
    else:
        result = AnalysisResult(
            symbol=symbol_info,
            timeframe=timeframe,
            p_up=0.5,
            p_down=0.5,
            textbook_similarity=0.0,
            pattern_confirmation_score=0.0,
            confidence=0.0,
            entry_score=0.0,
            no_signal_flag=True,
            no_signal_reason="감지된 패턴 없음",
            reason_summary="현재 차트에서는 교과서형 패턴이 아직 선명하게 감지되지 않았습니다.",
            sample_size=0,
            patterns=[],
            is_provisional=True,
            updated_at=datetime.utcnow().isoformat(),
        )

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
