from datetime import date, timedelta

from fastapi import APIRouter, Query

from ..schemas import AnalysisResult, OHLCVBar, PatternInfo, SymbolInfo
from ...core.config import get_settings
from ...core.redis import cache_get, cache_set
from ...services.data_fetcher import get_data_fetcher
from ...services.pattern_engine import PatternEngine
from ...services.probability_engine import compute_probability

router = APIRouter(prefix="/symbols", tags=["symbols"])
settings = get_settings()


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
        out.append(SymbolInfo(
            code=row["code"],
            name=row.get("name") or row["code"],
            market=row["market"],
            sector=None,
            market_cap=None,
            is_in_universe=True,
        ))
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
    start = end - timedelta(days=days)

    if timeframe == "1d":
        df = await fetcher.get_stock_ohlcv(symbol, start, end)
        ttl = settings.daily_bars_ttl
    else:
        df = await fetcher.get_stock_ohlcv(symbol, start, end)
        ttl = settings.intraday_bars_ttl

    if df.empty:
        return []

    bars: list[OHLCVBar] = []
    for _, row in df.iterrows():
        amount = row.get("amount")
        bars.append(OHLCVBar(
            date=str(row["date"])[:10],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            amount=float(amount) if amount is not None and str(amount) != "nan" else None,
        ))

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
    start = end - timedelta(days=365)

    df = await fetcher.get_stock_ohlcv(symbol, start, end)
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

    from datetime import datetime

    if df.empty or len(df) < 20:
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
            reason_summary="분석에 필요한 캔들 수가 충분하지 않아 아직 판단할 수 없습니다.",
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
        prob = compute_probability(best_pattern, sample_size=50)
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
            reason_summary="현재 차트에서는 교과서형 패턴을 아직 뚜렷하게 감지하지 못했습니다.",
            sample_size=0,
            patterns=[],
            is_provisional=True,
            updated_at=datetime.utcnow().isoformat(),
        )

    await cache_set(cache_key, result.model_dump(), settings.pattern_cache_ttl)
    return result
