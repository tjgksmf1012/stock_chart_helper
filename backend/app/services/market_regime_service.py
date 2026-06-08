"""
Market regime detection for KOSPI and KOSDAQ.
Uses pykrx index OHLCV — same asyncio.to_thread pattern as data_fetcher.
Regime classification: bull / correction / bear / sideways / unknown
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

KOSPI_TICKER = "1001"
KOSDAQ_TICKER = "2001"
_CACHE_KEY = "market:regime:v1"
_CACHE_TTL = 1800  # 30분

# 동시 pykrx 호출 방지 — 한 번에 하나만 수행, 진행 중이면 즉시 unknown 반환
_fetch_lock: asyncio.Lock | None = None


def _get_fetch_lock() -> asyncio.Lock:
    global _fetch_lock
    if _fetch_lock is None:
        _fetch_lock = asyncio.Lock()
    return _fetch_lock


def _unknown_regime() -> dict:
    unk = {
        "regime": "unknown",
        "current": 0.0,
        "change_pct": 0.0,
        "ma20": None,
        "ma60": None,
        "ma120": None,
        "distance_from_ma120_pct": 0.0,
    }
    return {
        "kospi": unk,
        "kosdaq": unk,
        "overall_regime": "unknown",
        "generated_at": datetime.utcnow().isoformat(),
    }


def _classify_regime(close: pd.Series) -> dict:
    """OHLCV close 시리즈에서 체제를 판정해 dict로 반환."""
    if len(close) < 20:
        return {"regime": "unknown", "current": 0.0, "change_pct": 0.0, "ma20": None, "ma60": None, "ma120": None, "distance_from_ma120_pct": 0.0}

    current = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else current
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else ma20
    ma120 = float(close.rolling(120).mean().iloc[-1]) if len(close) >= 120 else ma60

    distance_pct = round((current - ma120) / ma120 * 100, 2) if ma120 else 0.0
    change_pct = round((current - prev) / prev * 100, 2) if prev else 0.0

    ma_max = max(ma20, ma60, ma120)
    ma_min = min(ma20, ma60, ma120)
    ma_spread_pct = (ma_max - ma_min) / current * 100 if current else 0

    # 체제 판정
    if ma_spread_pct < 3.0 and abs(current - ma60) / current * 100 < 3.0:
        regime = "sideways"
    elif current > ma20 and ma20 > ma60:
        regime = "bull"
    elif current < ma60:
        regime = "bear"
    else:
        regime = "correction"

    return {
        "regime": regime,
        "current": round(current, 2),
        "change_pct": change_pct,
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "ma120": round(ma120, 2),
        "distance_from_ma120_pct": distance_pct,
    }


async def _fetch_index_df(ticker: str, days: int = 180) -> pd.DataFrame | None:
    """pykrx 인덱스 OHLCV 비동기 수집."""
    try:
        from pykrx import stock as krx
        end = date.today()
        start = end - timedelta(days=days)
        df = await asyncio.wait_for(
            asyncio.to_thread(
                krx.get_index_ohlcv_by_date,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                ticker,
            ),
            timeout=10.0,  # 15→10초로 단축해 thread pool 빨리 반환
        )
        return df if df is not None else pd.DataFrame()
    except Exception as exc:
        logger.warning("index OHLCV fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()


def _close_series(df: pd.DataFrame | None) -> pd.Series:
    """pykrx 인덱스 DataFrame에서 종가 Series 추출."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    # pykrx 인덱스 컬럼: 시가, 고가, 저가, 종가, 거래량, 거래대금
    for col in ("종가", "close", "Close"):
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").dropna()
    # fallback: 4번째 컬럼
    if df.shape[1] >= 4:
        return pd.to_numeric(df.iloc[:, 3], errors="coerce").dropna()
    return pd.Series(dtype=float)


async def _do_fetch_market_regime() -> None:
    """실제 pykrx 호출 — 캐시에 저장만 하고 반환값 없음. 백그라운드 task용."""
    try:
        kospi_df, kosdaq_df = await asyncio.gather(
            _fetch_index_df(KOSPI_TICKER),
            _fetch_index_df(KOSDAQ_TICKER),
            return_exceptions=True,
        )
        kospi_close = _close_series(kospi_df if not isinstance(kospi_df, Exception) else None)
        kosdaq_close = _close_series(kosdaq_df if not isinstance(kosdaq_df, Exception) else None)

        kospi_regime = _classify_regime(kospi_close)
        kosdaq_regime = _classify_regime(kosdaq_close)

        rank = {"bull": 3, "sideways": 2, "correction": 1, "bear": 0, "unknown": -1}
        overall = min(
            [kospi_regime["regime"], kosdaq_regime["regime"]],
            key=lambda r: rank.get(r, -1),
        )
        result = {
            "kospi": kospi_regime,
            "kosdaq": kosdaq_regime,
            "overall_regime": overall,
            "generated_at": datetime.utcnow().isoformat(),
        }
        await cache_set(_CACHE_KEY, result, ttl=_CACHE_TTL)
        logger.info("market regime cached: %s", overall)
    except Exception as exc:
        logger.warning("market regime fetch failed: %s", exc)


async def get_market_regime() -> dict:
    """
    Returns MarketRegimeResponse-compatible dict.
    캐시 히트 → 즉시 반환.
    캐시 미스 → unknown 즉시 반환 + 백그라운드 갱신 (서버 블로킹 없음).
    동시 요청이 와도 락으로 중복 fetch 방지.
    """
    cached = await cache_get(_CACHE_KEY)
    if cached:
        return cached

    lock = _get_fetch_lock()
    if lock.locked():
        # 이미 다른 요청이 fetch 중 → 즉시 unknown 반환 (블로킹 없음)
        logger.debug("market regime fetch already in progress, returning unknown")
        return _unknown_regime()

    # 백그라운드 태스크로 실행 — 현재 요청은 즉시 unknown 반환
    async def _locked_fetch() -> None:
        async with lock:
            # double-check
            if await cache_get(_CACHE_KEY):
                return
            await _do_fetch_market_regime()

    asyncio.create_task(_locked_fetch())
    return _unknown_regime()
