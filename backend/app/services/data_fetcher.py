"""
Korean market data fetcher.

Primary source: pykrx (daily)
Fallback: FinanceDataReader (daily)
Intraday: Yahoo Finance (15m / 60m)
Optional real-time: KIS API
"""

import asyncio
import logging
from datetime import date, datetime

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)
UNIVERSE_CACHE_KEY = "symbols:universe"

KRX_OHLCV_COLUMNS = {
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
    "거래대금": "amount",
}

FDR_OHLCV_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}

INTRADAY_INTERVAL_MAP = {
    "60m": "60m",
    "15m": "15m",
}

INTRADAY_MAX_DAYS = {
    "60m": 730,
    "15m": 60,
}


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

            return self._normalize_daily_frame(df.rename(columns=KRX_OHLCV_COLUMNS))
        except Exception as exc:
            logger.warning("pykrx failed for %s: %s; trying FinanceDataReader fallback", code, exc)
            return await self._fdr_fallback(code, start, end)

    async def get_stock_intraday_ohlcv(
        self,
        code: str,
        timeframe: str,
        days: int,
    ) -> pd.DataFrame:
        interval = INTRADAY_INTERVAL_MAP.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported intraday timeframe: {timeframe}")

        period_days = max(5, min(days, INTRADAY_MAX_DAYS[timeframe]))
        candidates = await self._get_yahoo_symbol_candidates(code)
        if not candidates:
            return pd.DataFrame()

        for yahoo_symbol in candidates:
            for yahoo_interval in self._intraday_interval_candidates(timeframe):
                try:
                    import yfinance as yf

                    ticker = yf.Ticker(yahoo_symbol)
                    df = await asyncio.to_thread(
                        ticker.history,
                        period=f"{period_days}d",
                        interval=yahoo_interval,
                        auto_adjust=False,
                        prepost=False,
                    )
                    normalized = self._normalize_intraday_frame(df)
                    if not normalized.empty:
                        return normalized
                except Exception as exc:
                    logger.warning(
                        "yfinance intraday failed for %s (%s, %s): %s",
                        code,
                        yahoo_symbol,
                        yahoo_interval,
                        exc,
                    )

        return pd.DataFrame()

    async def _fdr_fallback(self, code: str, start: date, end: date) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr

            df = await asyncio.to_thread(fdr.DataReader, code, start, end)
            if df.empty:
                return pd.DataFrame()

            return self._normalize_daily_frame(df.rename(columns=FDR_OHLCV_COLUMNS))
        except Exception as exc:
            logger.error("FinanceDataReader also failed for %s: %s", code, exc)
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
                        rows.append(
                            {
                                "code": code,
                                "market": market,
                                "name": name,
                            }
                        )
                return rows

            rows = await asyncio.to_thread(build_rows)
            df = pd.DataFrame(rows)
            await cache_set(UNIVERSE_CACHE_KEY, df.to_dict(orient="records"), ttl=3600)
            return df
        except Exception as exc:
            logger.error("Failed to fetch universe: %s", exc)
            return pd.DataFrame(columns=["code", "market", "name"])

    async def get_market_cap(self, code: str) -> float | None:
        """Returns market cap in units of 100M KRW when available."""
        try:
            from pykrx import stock as krx

            today = datetime.today().strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_market_cap, today, today, code)
            if df.empty:
                return None
            return float(df["시가총액"].iloc[0] / 1e8)
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

            normalized = df.rename(
                columns={key: value for key, value in KRX_OHLCV_COLUMNS.items() if key != "거래대금"}
            )
            normalized.index.name = "date"
            normalized = normalized.reset_index()
            normalized["date"] = pd.to_datetime(normalized["date"]).dt.tz_localize(None)
            return normalized[["date", "open", "high", "low", "close", "volume"]]
        except Exception as exc:
            logger.error("Index fetch failed %s: %s", index_code, exc)
            return pd.DataFrame()

    async def _get_yahoo_symbol_candidates(self, code: str) -> list[str]:
        universe = await self.get_universe()
        if not universe.empty:
            matched = universe.loc[universe["code"] == code]
            if not matched.empty:
                market = matched.iloc[0]["market"]
                if market == "KOSPI":
                    return [f"{code}.KS", f"{code}.KQ"]
                if market == "KOSDAQ":
                    return [f"{code}.KQ", f"{code}.KS"]
        return [f"{code}.KS", f"{code}.KQ"]

    def _intraday_interval_candidates(self, timeframe: str) -> list[str]:
        if timeframe == "60m":
            return ["60m", "1h"]
        return [INTRADAY_INTERVAL_MAP[timeframe]]

    def _normalize_daily_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        normalized.index.name = "date"
        normalized = normalized.reset_index()
        normalized["date"] = pd.to_datetime(normalized["date"]).dt.tz_localize(None)
        if "amount" not in normalized.columns:
            normalized["amount"] = None
        return normalized[["date", "open", "high", "low", "close", "volume", "amount"]]

    def _normalize_intraday_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        normalized = df.copy()
        normalized.index.name = "datetime"
        normalized = normalized.reset_index()
        normalized = normalized.rename(
            columns={
                "Datetime": "datetime",
                "Date": "datetime",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        if "datetime" not in normalized.columns:
            return pd.DataFrame()

        timestamps = pd.to_datetime(normalized["datetime"])
        if getattr(timestamps.dt, "tz", None) is not None:
            timestamps = timestamps.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
        normalized["datetime"] = timestamps
        normalized["amount"] = None

        columns = ["datetime", "open", "high", "low", "close", "volume", "amount"]
        if any(column not in normalized.columns for column in columns):
            return pd.DataFrame()

        return normalized[columns].dropna(subset=["datetime", "open", "high", "low", "close"])


_fetcher: KRXDataFetcher | None = None


def get_data_fetcher() -> KRXDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = KRXDataFetcher()
    return _fetcher
