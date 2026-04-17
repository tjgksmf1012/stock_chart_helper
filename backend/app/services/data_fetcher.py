"""
Korean market data fetcher.

Primary source: pykrx (KRX official, free, no API key required)
Fallback: FinanceDataReader

Real-time / intraday: KIS API (optional, requires account & API key)
"""

import asyncio
from datetime import date, datetime, timedelta
from functools import lru_cache
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class KRXDataFetcher:
    """Fetches historical OHLCV data from KRX via pykrx."""

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
                "시가": "open", "고가": "high", "저가": "low",
                "종가": "close", "거래량": "volume", "거래대금": "amount",
            })
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"])
            return df[["date", "open", "high", "low", "close", "volume", "amount"]]
        except Exception as e:
            logger.warning("pykrx failed for %s: %s — trying FinanceDataReader", code, e)
            return await self._fdr_fallback(code, start, end)

    async def _fdr_fallback(self, code: str, start: date, end: date) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr
            df = await asyncio.to_thread(fdr.DataReader, code, start, end)
            if df.empty:
                return pd.DataFrame()
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
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
        """KOSPI + KOSDAQ 상장 종목 전체 목록 + 시가총액."""
        try:
            from pykrx import stock as krx
            today = datetime.today().strftime("%Y%m%d")

            kospi = await asyncio.to_thread(krx.get_market_ticker_list, today, market="KOSPI")
            kosdaq = await asyncio.to_thread(krx.get_market_ticker_list, today, market="KOSDAQ")

            rows = []
            for code in kospi:
                rows.append({"code": code, "market": "KOSPI"})
            for code in kosdaq:
                rows.append({"code": code, "market": "KOSDAQ"})

            df = pd.DataFrame(rows)
            return df
        except Exception as e:
            logger.error("Failed to fetch universe: %s", e)
            return pd.DataFrame(columns=["code", "market"])

    async def get_market_cap(self, code: str) -> float | None:
        """시가총액 (억 원) 반환."""
        try:
            from pykrx import stock as krx
            today = datetime.today().strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_market_cap, today, today, code)
            if df.empty:
                return None
            val = df["시가총액"].iloc[0] / 1e8  # 원 → 억 원
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
        """지수 데이터 (예: 코스피=1, 코스닥=2)."""
        try:
            from pykrx import stock as krx
            start_str = start.strftime("%Y%m%d")
            end_str = end.strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_index_ohlcv, start_str, end_str, index_code)
            if df.empty:
                return pd.DataFrame()
            df = df.rename(columns={
                "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume",
            })
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"])
            return df
        except Exception as e:
            logger.error("Index fetch failed %s: %s", index_code, e)
            return pd.DataFrame()


# Singleton
_fetcher: KRXDataFetcher | None = None


def get_data_fetcher() -> KRXDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = KRXDataFetcher()
    return _fetcher
