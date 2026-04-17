"""
Korean market data fetcher.

Primary source: pykrx (daily)
Fallback: FinanceDataReader (daily)
Intraday: Yahoo Finance (15m / 60m)
Optional real-time: KIS API
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..core.redis import cache_get, cache_set
from .kis_client import KISClient, get_kis_client
from .timeframe_service import get_timeframe_spec, is_intraday_timeframe

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
    "1m": "1m",
    "60m": "60m",
    "30m": "15m",
    "15m": "15m",
}

INTRADAY_MAX_DAYS = {
    "1m": 7,
    "60m": 730,
    "30m": 60,
    "15m": 60,
}

INTRADAY_RESAMPLE_RULES = {
    "1m": "1min",
    "60m": "60min",
    "30m": "30min",
    "15m": "15min",
}

DAILY_RESAMPLE_RULES = {
    "1wk": "W-FRI",
    "1mo": "MS",
}


class KRXDataFetcher:
    """Fetches historical OHLCV and symbol metadata for the Korean market."""

    def __init__(self, kis_client: KISClient | None = None) -> None:
        self._kis_client = kis_client or get_kis_client()
        self._universe_lock = asyncio.Lock()

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
            df = await asyncio.wait_for(
                asyncio.to_thread(krx.get_market_ohlcv, start_str, end_str, code, adjusted=adjusted),
                timeout=15.0,
            )
            if df.empty:
                return pd.DataFrame()

            return self._with_source(
                self._normalize_daily_frame(df.rename(columns=KRX_OHLCV_COLUMNS)),
                "pykrx_daily",
            )
        except Exception as exc:
            logger.warning("pykrx failed for %s: %s; trying FinanceDataReader fallback", code, exc)
            return await self._fdr_fallback(code, start, end)

    async def get_stock_ohlcv_by_timeframe(
        self,
        code: str,
        timeframe: str,
        lookback_days: int | None = None,
    ) -> pd.DataFrame:
        spec = get_timeframe_spec(timeframe)
        period_days = lookback_days or spec.analysis_lookback_days

        if is_intraday_timeframe(timeframe):
            return await self.get_stock_intraday_ohlcv(code, timeframe, period_days)

        end = date.today()
        base_daily = await self.get_stock_ohlcv(code, end - timedelta(days=period_days), end)
        if base_daily.empty or timeframe == "1d":
            return base_daily
        return self._with_source(
            self._resample_daily_frame(base_daily, timeframe),
            str(base_daily.attrs.get("data_source") or "daily_resampled"),
        )

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
        yahoo_df, kis_df = await asyncio.gather(
            self._get_yahoo_intraday_ohlcv(code, timeframe, period_days),
            self._get_kis_intraday_ohlcv(code, timeframe),
        )
        return self._merge_intraday_sources(yahoo_df, kis_df)

    async def _get_yahoo_intraday_ohlcv(
        self,
        code: str,
        timeframe: str,
        period_days: int,
    ) -> pd.DataFrame:
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
                        return self._with_source(normalized, "yahoo_fallback")
                except Exception as exc:
                    exc_str = str(exc)
                    if "Too Many Requests" in exc_str or "Rate limit" in exc_str.lower():
                        logger.warning("yfinance rate-limited for %s; intraday unavailable", code)
                        return pd.DataFrame()
                    logger.warning(
                        "yfinance intraday failed for %s (%s, %s): %s",
                        code, yahoo_symbol, yahoo_interval, exc,
                    )

        return pd.DataFrame()

    async def _get_kis_intraday_ohlcv(self, code: str, timeframe: str) -> pd.DataFrame:
        if timeframe not in INTRADAY_RESAMPLE_RULES:
            return pd.DataFrame()

        try:
            minute_bars = await self._kis_client.fetch_today_minute_bars(code)
        except Exception as exc:
            logger.warning("KIS intraday failed for %s (%s): %s", code, timeframe, exc)
            return pd.DataFrame()

        if minute_bars.empty:
            return pd.DataFrame()

        if timeframe == "1m":
            return self._with_source(minute_bars.reset_index(drop=True), "kis_intraday")
        return self._with_source(self._resample_intraday_frame(minute_bars, timeframe), "kis_intraday")

    def _resample_intraday_frame(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        normalized = df.copy()
        normalized["datetime"] = pd.to_datetime(normalized["datetime"])
        normalized = (
            normalized.sort_values("datetime")
            .drop_duplicates(subset=["datetime"], keep="last")
            .set_index("datetime")
        )
        resampled = normalized.resample(INTRADAY_RESAMPLE_RULES[timeframe]).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        if resampled.empty:
            return pd.DataFrame()

        result = resampled.reset_index()
        result["amount"] = None
        return result[["datetime", "open", "high", "low", "close", "volume", "amount"]]

    def _resample_daily_frame(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        rule = DAILY_RESAMPLE_RULES.get(timeframe)
        if rule is None or df.empty:
            return df

        normalized = df.copy()
        normalized["date"] = pd.to_datetime(normalized["date"])
        normalized = normalized.sort_values("date").set_index("date")
        if "amount" not in normalized.columns:
            normalized["amount"] = 0.0

        resampled = normalized.resample(rule).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "amount": "sum",
            }
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        if resampled.empty:
            return pd.DataFrame()

        result = resampled.reset_index()
        result["date"] = pd.to_datetime(result["date"]).dt.tz_localize(None)
        return result[["date", "open", "high", "low", "close", "volume", "amount"]]

    def _merge_intraday_sources(self, yahoo_df: pd.DataFrame, kis_df: pd.DataFrame) -> pd.DataFrame:
        if yahoo_df.empty:
            return self._with_source(kis_df.reset_index(drop=True), str(kis_df.attrs.get("data_source") or "kis_intraday")) if not kis_df.empty else pd.DataFrame()
        if kis_df.empty:
            return self._with_source(yahoo_df.reset_index(drop=True), str(yahoo_df.attrs.get("data_source") or "yahoo_fallback"))

        today = pd.Timestamp.now(tz="Asia/Seoul").tz_convert(None).normalize()
        yahoo_dt = pd.to_datetime(yahoo_df["datetime"])
        if getattr(yahoo_dt.dt, "tz", None) is not None:
            yahoo_dt = yahoo_dt.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
        historical = yahoo_df.loc[yahoo_dt.dt.normalize() < today].copy()
        combined = pd.concat([historical, kis_df], ignore_index=True)
        combined = combined.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")
        return self._with_source(combined.reset_index(drop=True), "hybrid_intraday")

    async def _fdr_fallback(self, code: str, start: date, end: date) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr

            df = await asyncio.to_thread(fdr.DataReader, code, start, end)
            if df.empty:
                return pd.DataFrame()

            return self._with_source(
                self._normalize_daily_frame(df.rename(columns=FDR_OHLCV_COLUMNS)),
                "fdr_daily",
            )
        except Exception as exc:
            logger.error("FinanceDataReader also failed for %s: %s", code, exc)
            return pd.DataFrame()

    async def get_universe(self) -> pd.DataFrame:
        """Returns KOSPI/KOSDAQ symbol universe with names for search/autocomplete."""
        cached = await cache_get(UNIVERSE_CACHE_KEY)
        if cached:
            return pd.DataFrame(cached)

        async with self._universe_lock:
            # Re-check after acquiring lock — another coroutine may have populated it
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
                            rows.append({"code": code, "market": market, "name": name})
                    return rows

                rows = await asyncio.to_thread(build_rows)
                if not rows:
                    logger.warning("pykrx returned empty ticker list; falling back to FDR")
                    return await self._fdr_universe_fallback()
                df = pd.DataFrame(rows)
                await cache_set(UNIVERSE_CACHE_KEY, df.to_dict(orient="records"), ttl=3600)
                return df
            except Exception as exc:
                logger.error("pykrx universe failed (%s); falling back to FDR", exc)
                return await self._fdr_universe_fallback()

    async def _fdr_universe_fallback(self) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr

            def _fetch() -> pd.DataFrame:
                df = fdr.StockListing("KRX")
                df = df[df["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])].copy()
                df["market"] = df["Market"].map(
                    lambda m: "KOSDAQ" if "KOSDAQ" in m else "KOSPI"
                )
                df["code"] = df["Code"].astype(str).str.zfill(6)
                df["name"] = df["Name"].fillna(df["code"])
                return df[["code", "market", "name"]].reset_index(drop=True)

            result = await asyncio.to_thread(_fetch)
            if not result.empty:
                await cache_set(UNIVERSE_CACHE_KEY, result.to_dict(orient="records"), ttl=3600)
                logger.info("FDR universe fallback: %d stocks", len(result))
            return result
        except Exception as exc:
            logger.error("FDR universe fallback failed: %s", exc)
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
        if timeframe == "1m":
            return ["1m"]
        if timeframe == "60m":
            return ["60m", "1h"]
        if timeframe == "30m":
            return ["15m", "30m"]
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

    def _with_source(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        if df.empty:
            return df
        copied = df.copy()
        copied.attrs["data_source"] = source
        return copied


_fetcher: KRXDataFetcher | None = None


def get_data_fetcher() -> KRXDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = KRXDataFetcher()
    return _fetcher
