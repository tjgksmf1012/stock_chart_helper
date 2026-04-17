from fastapi import APIRouter, Query, HTTPException
from datetime import date, timedelta
import pandas as pd

from ..schemas import SymbolInfo, OHLCVBar, AnalysisResult, PatternInfo
from ...services.data_fetcher import get_data_fetcher
from ...services.pattern_engine import PatternEngine
from ...services.probability_engine import compute_probability
from ...core.redis import cache_get, cache_set
from ...core.config import get_settings

router = APIRouter(prefix="/symbols", tags=["symbols"])
settings = get_settings()


@router.get("/search")
async def search_symbols(q: str = Query(min_length=1)) -> list[SymbolInfo]:
    fetcher = get_data_fetcher()
    universe = await fetcher.get_universe()
    if universe.empty:
        return []
    mask = universe["code"].str.contains(q, case=False, na=False)
    results = universe[mask].head(20)
    out = []
    for _, row in results.iterrows():
        out.append(SymbolInfo(
            code=row["code"],
            name=row.get("name", row["code"]),
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
        return [OHLCVBar(**b) for b in cached]

    fetcher = get_data_fetcher()
    end = date.today()
    start = end - timedelta(days=days)

    if timeframe == "1d":
        df = await fetcher.get_stock_ohlcv(symbol, start, end)
        ttl = settings.daily_bars_ttl
    else:
        # Intraday via pykrx (일봉으로 fallback — 실시간은 KIS API 필요)
        df = await fetcher.get_stock_ohlcv(symbol, start, end)
        ttl = settings.intraday_bars_ttl

    if df.empty:
        return []

    bars = []
    for _, row in df.iterrows():
        bars.append(OHLCVBar(
            date=str(row["date"])[:10],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            amount=float(row["amount"]) if row.get("amount") is not None and str(row.get("amount")) != "nan" else None,
        ))

    await cache_set(cache_key, [b.model_dump() for b in bars], ttl)
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

    symbol_info = SymbolInfo(
        code=symbol,
        name=name,
        market="KOSPI",
        sector=None,
        market_cap=market_cap,
        is_in_universe=market_cap is not None and market_cap >= 500,
    )

    if df.empty or len(df) < 20:
        from datetime import datetime
        return AnalysisResult(
            symbol=symbol_info,
            timeframe=timeframe,
            p_up=0.5, p_down=0.5,
            textbook_similarity=0.0,
            pattern_confirmation_score=0.0,
            confidence=0.0,
            entry_score=0.0,
            no_signal_flag=True,
            no_signal_reason="데이터 부족",
            reason_summary="데이터가 충분하지 않아 분석을 수행할 수 없습니다.",
            sample_size=0,
            patterns=[],
            is_provisional=True,
            updated_at=datetime.utcnow().isoformat(),
        )

    engine = PatternEngine()
    pattern_results = engine.detect_all(df)

    patterns = [
        PatternInfo(
            pattern_type=p.pattern_type,
            state=p.state,
            grade=p.grade,
            textbook_similarity=p.textbook_similarity,
            geometry_fit=p.geometry_fit,
            neckline=p.neckline,
            invalidation_level=p.invalidation_level,
            target_level=p.target_level,
            key_points=p.key_points,
            is_provisional=p.is_provisional,
            start_dt=p.start_dt.isoformat(),
            end_dt=p.end_dt.isoformat() if p.end_dt else None,
        )
        for p in pattern_results
    ]

    best_pattern = max(pattern_results, key=lambda p: p.textbook_similarity) if pattern_results else None

    from datetime import datetime
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
            p_up=0.5, p_down=0.5,
            textbook_similarity=0.0,
            pattern_confirmation_score=0.0,
            confidence=0.0,
            entry_score=0.0,
            no_signal_flag=True,
            no_signal_reason="감지된 패턴 없음",
            reason_summary="현재 차트에서 교과서형 패턴이 감지되지 않았습니다.",
            sample_size=0,
            patterns=[],
            is_provisional=True,
            updated_at=datetime.utcnow().isoformat(),
        )

    await cache_set(cache_key, result.model_dump(), settings.pattern_cache_ttl)
    return result
