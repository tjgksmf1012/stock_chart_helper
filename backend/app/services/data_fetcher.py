"""
Korean market data fetcher.

Primary source: pykrx (KRX official, free, no API key required)
Fallback: FinanceDataReader

Real-time / intraday: KIS API (optional, requires account & API key)
"""

import asyncio
import logging
from datetime import date, datetime

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)
UNIVERSE_CACHE_KEY = "symbols:universe"


class KRXDataFetcher:
    """Fetches historical OHLCV and symbol metadata for the Korean market."""

    async def get_stock_ohlcv(
        self,
        code: str,
        start: date,
        end: date,
        adjusted: bool = True,
    ) -> pd.DataFrame:
        try:
            from pykrx import stock as krx

            start_str = start.strftime("%Y%m%d")
            end_str = end.strftime("%Y%m%d")
            df = await asyncio.to_thread(
                krx.get_market_ohlcv, start_str, end_str, code, adjusted=adjusted
            )
            if df.empty:
                return pd.DataFrame()

            df = df.rename(columns={
                "시가": "open",
                "고가": "high",
                "저가": "low",
                "종가": "close",
                "거래량": "volume",
                "거래대금": "amount",
            })
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"])

            if "amount" not in df.columns:
                df["amount"] = None

            return df[["date", "open", "high", "low", "close", "volume", "amount"]]
        except Exception as e:
            logger.warning("pykrx failed for %s: %s; trying FinanceDataReader fallback", code, e)
            return await self._fdr_fallback(code, start, end)

    async def _fdr_fallback(self, code: str, start: date, end: date) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr

            df = await asyncio.to_thread(fdr.DataReader, code, start, end)
            if df.empty:
                return pd.DataFrame()

            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"])
            df["amount"] = None

            return df[["date", "open", "high", "low", "close", "volume", "amount"]]
        except Exception as e:
            logger.error("FinanceDataReader also failed for %s: %s", code, e)
            return pd.DataFrame()

    async def get_universe(self) -> pd.DataFrame:
        """Returns KOSPI/KOSDAQ symbol universe with names for search/autocomplete."""
        cached = await cache_get(UNIVERSE_CACHE_KEY)
        if cached:
            return pd.DataFrame(cached)

        try:
            from pykrx import stock as krx

            today = datetime.today().strftime("%Y%m%d")

            def build_rows() -> list[dict[str, str]]:
                rows: list[dict[str, str]] = []
                for market in ("KOSPI", "KOSDAQ"):
                    tickers = krx.get_market_ticker_list(today, market=market)
                    for code in tickers:
                        try:
                            name = krx.get_market_ticker_name(code)
                        except Exception:
                            name = code
                        rows.append({
                            "code": code,
                            "market": market,
                            "name": name,
                        })
                return rows

            rows = await asyncio.to_thread(build_rows)
            df = pd.DataFrame(rows)
            await cache_set(UNIVERSE_CACHE_KEY, df.to_dict(orient="records"), ttl=3600)
            return df
        except Exception as e:
            logger.error("Failed to fetch universe: %s", e)
            return pd.DataFrame(columns=["code", "market", "name"])

    async def get_market_cap(self, code: str) -> float | None:
        """Returns market cap in units of 100M KRW when available."""
        try:
            from pykrx import stock as krx

            today = datetime.today().strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_market_cap, today, today, code)
            if df.empty:
                return None
            val = df["시가총액"].iloc[0] / 1e8
            return float(val)
        except Exception:
            return None

    async def get_stock_name(self, code: str) -> str:
        try:
            from pykrx import stock as krx
            return await asyncio.to_thread(krx.get_market_ticker_name, code)
        except Exception:
            return code

    async def get_index_ohlcv(self, index_code: str, start: date, end: date) -> pd.DataFrame:
        """Fetches index OHLCV data such as KOSPI/KOSDAQ."""
        try:
            from pykrx import stock as krx

            start_str = start.strftime("%Y%m%d")
            end_str = end.strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_index_ohlcv, start_str, end_str, index_code)
            if df.empty:
                return pd.DataFrame()

            df = df.rename(columns={
                "시가": "open",
                "고가": "high",
                "저가": "low",
                "종가": "close",
                "거래량": "volume",
            })
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"])
            return df
        except Exception as e:
            logger.error("Index fetch failed %s: %s", index_code, e)
            return pd.DataFrame()


_fetcher: KRXDataFetcher | None = None


def get_data_fetcher() -> KRXDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = KRXDataFetcher()
    return _fetcher
