"""
Korean market data fetcher.

Primary source: pykrx (daily)
Fallback: FinanceDataReader (daily)
Intraday: Yahoo Finance with persistent local storage fallback
Optional real-time: KIS API
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..core.config import get_settings
from ..core.redis import cache_get, cache_set
from .intraday_store import get_intraday_store
from .kis_client import KISClient, get_kis_client
from .timeframe_service import get_timeframe_spec, is_intraday_timeframe

logger = logging.getLogger(__name__)
settings = get_settings()
UNIVERSE_CACHE_KEY = "symbols:universe"
MARKET_CAP_CACHE_PREFIX = "symbols:market-cap:v1"
YAHOO_INTRADAY_COOLDOWN_PREFIX = "yahoo:intraday:cooldown"

KRX_OHLCV_COLUMNS = {
    "\uc2dc\uac00": "open",
    "\uace0\uac00": "high",
    "\uc800\uac00": "low",
    "\uc885\uac00": "close",
    "\uac70\ub798\ub7c9": "volume",
    "\uac70\ub798\ub300\uae08": "amount",
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

YAHOO_HISTORY_TIMEOUT_SECONDS = 12.0

DAILY_RESAMPLE_RULES = {
    "1wk": "W-FRI",
    "1mo": "MS",
}

FETCH_STATUS_MESSAGES = {
    "live_ok": "실시간 분봉을 정상적으로 불러왔습니다.",
    "live_augmented_by_store": "실시간 분봉을 불러왔고 누락 구간은 저장된 분봉으로 보완했습니다.",
    "stored_fallback": "실시간 제공처 응답이 불안정해 저장된 분봉을 대신 사용했습니다.",
    "stored_empty": "이 종목에 대해 이전에 저장된 분봉이 없습니다.",
    "intraday_rate_limited": "야후 분봉 요청 제한이 걸려 현재 응답이 불안정합니다.",
    "intraday_unavailable": "현재 사용 가능한 분봉 제공처에서 응답을 주지 않았습니다.",
    "intraday_empty": "요청한 종목과 타임프레임에 대해 제공된 분봉 바 수가 부족합니다.",
    "yahoo_symbol_missing": "이 종목의 야후 심볼 매핑을 찾지 못했습니다.",
    "yahoo_empty": "야후에서 해당 종목 분봉을 반환하지 않았습니다.",
    "kis_not_configured": "KIS API가 설정되지 않아 공개 분봉 소스만 사용 가능합니다.",
    "kis_error": "KIS API 요청이 실패해 무시했습니다.",
    "kis_empty": "KIS에서 해당 종목 분봉을 반환하지 않았습니다.",
}


FETCH_STATUS_MESSAGES.update(
    {
        "stored_recent": "최근 저장한 분봉을 우선 재사용했습니다.",
        "kis_cooldown": "KIS 오류 직후라 잠시 저장 분봉을 우선 사용하며 재시도를 늦추고 있습니다.",
    }
)

FETCH_STATUS_MESSAGES.update(
    {
        "scanner_store_only": "스캐너 절약 모드로 저장 분봉을 우선 사용했습니다.",
        "scanner_public_only": "스캐너 절약 모드로 KIS 대신 공개 분봉 소스를 사용했습니다.",
        "scanner_public_augmented": "스캐너 절약 모드로 공개 분봉과 저장 분봉을 함께 사용했습니다.",
    }
)


class KRXDataFetcher:
    """Fetches historical OHLCV and symbol metadata for the Korean market."""

    def __init__(self, kis_client: KISClient | None = None) -> None:
        self._kis_client = kis_client or get_kis_client()
        self._intraday_store = get_intraday_store()
        self._universe_lock = asyncio.Lock()

    def _kis_cooldown_key(self, code: str, timeframe: str) -> str:
        return f"kis:cooldown:{code}:{timeframe}"

    def _yahoo_cooldown_key(self, timeframe: str) -> str:
        return f"{YAHOO_INTRADAY_COOLDOWN_PREFIX}:{timeframe}"

    async def _kis_is_in_cooldown(self, code: str, timeframe: str) -> bool:
        return bool(await cache_get(self._kis_cooldown_key(code, timeframe)))

    async def _mark_kis_cooldown(self, code: str, timeframe: str, reason: str) -> None:
        await cache_set(
            self._kis_cooldown_key(code, timeframe),
            {"reason": reason, "at": datetime.utcnow().isoformat()},
            ttl=max(60, int(settings.kis_failure_cooldown_seconds)),
        )

    async def _yahoo_is_in_cooldown(self, timeframe: str) -> bool:
        return bool(await cache_get(self._yahoo_cooldown_key(timeframe)))

    async def _mark_yahoo_cooldown(self, timeframe: str, reason: str) -> None:
        await cache_set(
            self._yahoo_cooldown_key(timeframe),
            {"reason": reason, "at": datetime.utcnow().isoformat()},
            ttl=max(60, int(settings.yahoo_failure_cooldown_seconds)),
        )

    async def get_stock_ohlcv(self, code: str, start: date, end: date, adjusted: bool = True) -> pd.DataFrame:
        try:
            from pykrx import stock as krx

            start_str = start.strftime("%Y%m%d")
            end_str = end.strftime("%Y%m%d")
            df = await asyncio.wait_for(
                asyncio.to_thread(krx.get_market_ohlcv, start_str, end_str, code, adjusted=adjusted),
                timeout=15.0,
            )
            if df.empty:
                return self._empty_frame(data_source="pykrx_daily", fetch_status="daily_empty")

            return self._with_attrs(
                self._normalize_daily_frame(df.rename(columns=KRX_OHLCV_COLUMNS)),
                data_source="pykrx_daily",
                fetch_status="daily_ok",
            )
        except Exception as exc:
            logger.warning("pykrx failed for %s: %s; trying FinanceDataReader fallback", code, exc)
            return await self._fdr_fallback(code, start, end)

    async def get_stock_ohlcv_by_timeframe(
        self,
        code: str,
        timeframe: str,
        lookback_days: int | None = None,
        allow_live_intraday: bool = True,
    ) -> pd.DataFrame:
        spec = get_timeframe_spec(timeframe)
        period_days = lookback_days or spec.analysis_lookback_days

        if is_intraday_timeframe(timeframe):
            return await self.get_stock_intraday_ohlcv(
                code,
                timeframe,
                period_days,
                allow_live_intraday=allow_live_intraday,
            )

        end = date.today()
        base_daily = await self.get_stock_ohlcv(code, end - timedelta(days=period_days), end)
        if base_daily.empty or timeframe == "1d":
            return base_daily
        return self._with_attrs(self._resample_daily_frame(base_daily, timeframe), **base_daily.attrs)

    async def get_stock_intraday_ohlcv(
        self,
        code: str,
        timeframe: str,
        days: int,
        allow_live_intraday: bool = True,
    ) -> pd.DataFrame:
        if timeframe not in INTRADAY_INTERVAL_MAP:
            raise ValueError(f"Unsupported intraday timeframe: {timeframe}")

        period_days = max(5, min(days, INTRADAY_MAX_DAYS[timeframe]))
        stored_df = await self._intraday_store.load_bars(symbol=code, timeframe=timeframe, lookback_days=period_days)
        storage_age_minutes = stored_df.attrs.get("storage_age_minutes")
        if (
            not stored_df.empty
            and isinstance(storage_age_minutes, int)
            and storage_age_minutes <= max(0, int(settings.intraday_recent_store_reuse_minutes))
        ):
            stored_recent = stored_df.copy()
            stored_recent.attrs["data_source"] = str(stored_df.attrs.get("stored_source") or "intraday_store")
            stored_recent.attrs["fetch_status"] = "stored_recent"
            stored_recent.attrs["fetch_message"] = FETCH_STATUS_MESSAGES["stored_recent"]
            return stored_recent
        if not allow_live_intraday:
            return await self._get_intraday_without_kis(code, timeframe, period_days, stored_df)

        yahoo_df, kis_df = await asyncio.gather(
            self._get_yahoo_intraday_ohlcv(code, timeframe, period_days),
            self._get_kis_intraday_ohlcv(code, timeframe),
        )

        live_df = self._merge_intraday_sources(yahoo_df, kis_df)
        if not live_df.empty:
            combined = self._combine_intraday_frames(stored_df, live_df)
            await self._intraday_store.upsert_bars(
                symbol=code,
                timeframe=timeframe,
                df=combined,
                source=str(live_df.attrs.get("data_source") or "intraday_live"),
            )
            fetch_status = "live_ok"
            if not stored_df.empty and len(combined) > len(live_df):
                fetch_status = "live_augmented_by_store"
            combined.attrs["fetch_status"] = fetch_status
            combined.attrs["fetch_message"] = FETCH_STATUS_MESSAGES[fetch_status]
            return combined

        if not stored_df.empty:
            stored_only = stored_df.copy()
            stored_only.attrs["data_source"] = str(stored_df.attrs.get("stored_source") or "intraday_store")
            stored_only.attrs["fetch_status"] = "stored_fallback"
            stored_only.attrs["fetch_message"] = self._stored_fallback_message(yahoo_df, kis_df, stored_df)
            return stored_only

        failure_status, failure_message = self._combine_intraday_failure(yahoo_df, kis_df)
        return self._empty_frame(
            data_source="intraday_unavailable",
            fetch_status=failure_status,
            fetch_message=failure_message,
            available_bars=0,
        )

    async def _get_intraday_without_kis(
        self,
        code: str,
        timeframe: str,
        period_days: int,
        stored_df: pd.DataFrame,
    ) -> pd.DataFrame:
        yahoo_df = await self._get_yahoo_intraday_ohlcv(code, timeframe, period_days)

        if not yahoo_df.empty:
            combined = self._combine_intraday_frames(stored_df, yahoo_df)
            await self._intraday_store.upsert_bars(
                symbol=code,
                timeframe=timeframe,
                df=combined,
                source=str(yahoo_df.attrs.get("data_source") or "yahoo_fallback"),
            )
            fetch_status = "scanner_public_only"
            if not stored_df.empty and len(combined) > len(yahoo_df):
                fetch_status = "scanner_public_augmented"
            combined.attrs["data_source"] = str(yahoo_df.attrs.get("data_source") or "yahoo_fallback")
            combined.attrs["fetch_status"] = fetch_status
            combined.attrs["fetch_message"] = FETCH_STATUS_MESSAGES[fetch_status]
            return combined

        if not stored_df.empty:
            stored_only = stored_df.copy()
            stored_only.attrs["data_source"] = str(stored_df.attrs.get("stored_source") or "intraday_store")
            stored_only.attrs["fetch_status"] = "scanner_store_only"
            stored_only.attrs["fetch_message"] = FETCH_STATUS_MESSAGES["scanner_store_only"]
            return stored_only

        failure_status = str(yahoo_df.attrs.get("fetch_status") or "intraday_unavailable")
        failure_message = str(yahoo_df.attrs.get("fetch_message") or FETCH_STATUS_MESSAGES["intraday_unavailable"])
        return self._empty_frame(
            data_source=str(yahoo_df.attrs.get("data_source") or "yahoo_fallback"),
            fetch_status=failure_status,
            fetch_message=failure_message,
            available_bars=0,
        )

    async def _get_yahoo_intraday_ohlcv(self, code: str, timeframe: str, period_days: int) -> pd.DataFrame:
        if await self._yahoo_is_in_cooldown(timeframe):
            return self._empty_frame(
                data_source="yahoo_fallback",
                fetch_status="yahoo_rate_limited",
                fetch_message=FETCH_STATUS_MESSAGES["intraday_rate_limited"],
            )

        candidates = await self._get_yahoo_symbol_candidates(code)
        if not candidates:
            return self._empty_frame(
                data_source="yahoo_fallback",
                fetch_status="yahoo_symbol_missing",
                fetch_message=FETCH_STATUS_MESSAGES["yahoo_symbol_missing"],
            )

        for yahoo_symbol in candidates:
            for yahoo_interval in self._intraday_interval_candidates(timeframe):
                try:
                    import yfinance as yf

                    ticker = yf.Ticker(yahoo_symbol)
                    df = await asyncio.wait_for(
                        asyncio.to_thread(
                            ticker.history,
                            period=f"{period_days}d",
                            interval=yahoo_interval,
                            auto_adjust=False,
                            prepost=False,
                        ),
                        timeout=YAHOO_HISTORY_TIMEOUT_SECONDS,
                    )
                    normalized = self._normalize_intraday_frame(df)
                    if not normalized.empty:
                        return self._with_attrs(
                            normalized,
                            data_source="yahoo_fallback",
                            fetch_status="live_ok",
                            fetch_message="Yahoo Finance intraday bars loaded successfully.",
                        )
                except asyncio.TimeoutError:
                    logger.warning(
                        "yfinance intraday timed out for %s (%s, %s)",
                        code,
                        yahoo_symbol,
                        yahoo_interval,
                    )
                except Exception as exc:
                    exc_str = str(exc)
                    if "Too Many Requests" in exc_str or "Rate limit" in exc_str.lower():
                        await self._mark_yahoo_cooldown(timeframe, exc_str)
                        logger.warning("yfinance rate-limited for %s; intraday unavailable", code)
                        return self._empty_frame(
                            data_source="yahoo_fallback",
                            fetch_status="yahoo_rate_limited",
                            fetch_message=FETCH_STATUS_MESSAGES["intraday_rate_limited"],
                        )
                    logger.warning("yfinance intraday failed for %s (%s, %s): %s", code, yahoo_symbol, yahoo_interval, exc)

        return self._empty_frame(
            data_source="yahoo_fallback",
            fetch_status="yahoo_empty",
            fetch_message=FETCH_STATUS_MESSAGES["yahoo_empty"],
        )

    async def _get_kis_intraday_ohlcv(self, code: str, timeframe: str) -> pd.DataFrame:
        if timeframe not in INTRADAY_RESAMPLE_RULES:
            return self._empty_frame(data_source="kis_intraday", fetch_status="kis_unsupported")
        if not self._kis_client.configured:
            return self._empty_frame(
                data_source="kis_intraday",
                fetch_status="kis_not_configured",
                fetch_message=FETCH_STATUS_MESSAGES["kis_not_configured"],
            )
        if await self._kis_is_in_cooldown(code, timeframe):
            return self._empty_frame(
                data_source="kis_intraday",
                fetch_status="kis_cooldown",
                fetch_message=FETCH_STATUS_MESSAGES["kis_cooldown"],
            )

        try:
            minute_bars = await self._kis_client.fetch_today_minute_bars(code)
        except Exception as exc:
            logger.warning("KIS intraday failed for %s (%s): %s", code, timeframe, exc)
            await self._mark_kis_cooldown(code, timeframe, str(exc))
            return self._empty_frame(
                data_source="kis_intraday",
                fetch_status="kis_error",
                fetch_message=FETCH_STATUS_MESSAGES["kis_error"],
            )

        if minute_bars.empty:
            return self._empty_frame(
                data_source="kis_intraday",
                fetch_status="kis_empty",
                fetch_message=FETCH_STATUS_MESSAGES["kis_empty"],
            )

        if timeframe == "1m":
            return self._with_attrs(
                minute_bars.reset_index(drop=True),
                data_source="kis_intraday",
                fetch_status="live_ok",
                fetch_message="KIS 분봉을 정상적으로 불러왔습니다.",
            )
        return self._with_attrs(
            self._resample_intraday_frame(minute_bars, timeframe),
            data_source="kis_intraday",
            fetch_status="live_ok",
            fetch_message="KIS 분봉을 정상적으로 불러왔습니다.",
        )

    def _resample_intraday_frame(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        normalized = df.copy()
        normalized["datetime"] = pd.to_datetime(normalized["datetime"])
        normalized = normalized.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last").set_index("datetime")
        resampled = normalized.resample(INTRADAY_RESAMPLE_RULES[timeframe]).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
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
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "amount": "sum"}
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        if resampled.empty:
            return pd.DataFrame()

        result = resampled.reset_index()
        result["date"] = pd.to_datetime(result["date"]).dt.tz_localize(None)
        return result[["date", "open", "high", "low", "close", "volume", "amount"]]

    def _merge_intraday_sources(self, yahoo_df: pd.DataFrame, kis_df: pd.DataFrame) -> pd.DataFrame:
        if yahoo_df.empty and kis_df.empty:
            return pd.DataFrame()
        if yahoo_df.empty:
            return self._with_attrs(kis_df.reset_index(drop=True), **kis_df.attrs)
        if kis_df.empty:
            return self._with_attrs(yahoo_df.reset_index(drop=True), **yahoo_df.attrs)

        today = pd.Timestamp.now(tz="Asia/Seoul").tz_convert(None).normalize()
        yahoo_dt = pd.to_datetime(yahoo_df["datetime"])
        if getattr(yahoo_dt.dt, "tz", None) is not None:
            yahoo_dt = yahoo_dt.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
        historical = yahoo_df.loc[yahoo_dt.dt.normalize() < today].copy()
        combined = pd.concat([historical, kis_df], ignore_index=True)
        combined = combined.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")
        return self._with_attrs(
            combined.reset_index(drop=True),
            data_source="hybrid_intraday",
            fetch_status="live_ok",
            fetch_message="과거 구간은 야후, 최근 구간은 KIS를 사용해 분봉을 구성했습니다.",
        )

    def _combine_intraday_frames(self, stored_df: pd.DataFrame, live_df: pd.DataFrame) -> pd.DataFrame:
        if stored_df.empty:
            return self._with_attrs(live_df.reset_index(drop=True), **live_df.attrs)
        combined = pd.concat([stored_df, live_df], ignore_index=True)
        combined = combined.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")
        result = combined.reset_index(drop=True)
        attrs = dict(live_df.attrs)
        attrs["storage_age_minutes"] = stored_df.attrs.get("storage_age_minutes")
        return self._with_attrs(result, **attrs)

    def _combine_intraday_failure(self, yahoo_df: pd.DataFrame, kis_df: pd.DataFrame) -> tuple[str, str]:
        statuses = {str(yahoo_df.attrs.get("fetch_status") or ""), str(kis_df.attrs.get("fetch_status") or "")}
        if "yahoo_symbol_missing" in statuses:
            return "yahoo_symbol_missing", FETCH_STATUS_MESSAGES["yahoo_symbol_missing"]
        if "yahoo_rate_limited" in statuses:
            return "intraday_rate_limited", FETCH_STATUS_MESSAGES["intraday_rate_limited"]
        if "kis_cooldown" in statuses and "yahoo_empty" in statuses:
            return "stored_fallback", FETCH_STATUS_MESSAGES["kis_cooldown"]
        if "yahoo_empty" in statuses and "kis_not_configured" in statuses:
            return "intraday_empty", f"{FETCH_STATUS_MESSAGES['yahoo_empty']} {FETCH_STATUS_MESSAGES['kis_not_configured']}"
        if "yahoo_empty" in statuses and "kis_empty" in statuses:
            return "intraday_empty", f"{FETCH_STATUS_MESSAGES['yahoo_empty']} {FETCH_STATUS_MESSAGES['kis_empty']}"
        if "kis_cooldown" in statuses:
            return "intraday_unavailable", FETCH_STATUS_MESSAGES["kis_cooldown"]
        if "kis_error" in statuses and "yahoo_empty" in statuses:
            return "intraday_unavailable", f"{FETCH_STATUS_MESSAGES['yahoo_empty']} {FETCH_STATUS_MESSAGES['kis_error']}"
        if "yahoo_empty" in statuses:
            return "intraday_empty", FETCH_STATUS_MESSAGES["intraday_empty"]
        return "intraday_unavailable", FETCH_STATUS_MESSAGES["intraday_unavailable"]

    def _stored_fallback_message(self, yahoo_df: pd.DataFrame, kis_df: pd.DataFrame, stored_df: pd.DataFrame) -> str:
        age_minutes = stored_df.attrs.get("storage_age_minutes")
        age_text = f" 마지막 저장 갱신은 약 {age_minutes}분 전입니다." if isinstance(age_minutes, int) else ""
        failure_status, base_message = self._combine_intraday_failure(yahoo_df, kis_df)
        if failure_status == "intraday_rate_limited":
            return f"{FETCH_STATUS_MESSAGES['stored_fallback']} 야후 요청 제한이 감지됐습니다.{age_text}"
        return f"{FETCH_STATUS_MESSAGES['stored_fallback']} {base_message}{age_text}"

    async def _fdr_fallback(self, code: str, start: date, end: date) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr

            df = await asyncio.to_thread(fdr.DataReader, code, start, end)
            if df.empty:
                return self._empty_frame(data_source="fdr_daily", fetch_status="daily_empty")

            return self._with_attrs(
                self._normalize_daily_frame(df.rename(columns=FDR_OHLCV_COLUMNS)),
                data_source="fdr_daily",
                fetch_status="daily_ok",
            )
        except Exception as exc:
            logger.error("FinanceDataReader also failed for %s: %s", code, exc)
            return self._empty_frame(
                data_source="fdr_daily",
                fetch_status="daily_error",
                fetch_message="FinanceDataReader 일봉 보조 수집이 실패했습니다.",
            )

    async def get_universe(self) -> pd.DataFrame:
        cached = await cache_get(UNIVERSE_CACHE_KEY)
        if cached:
            return pd.DataFrame(cached)

        async with self._universe_lock:
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

                rows = await asyncio.wait_for(asyncio.to_thread(build_rows), timeout=20.0)
                if not rows:
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
                df["market"] = df["Market"].map(lambda m: "KOSDAQ" if "KOSDAQ" in m else "KOSPI")
                df["code"] = df["Code"].astype(str).str.zfill(6)
                df["name"] = df["Name"].fillna(df["code"])
                if "Marcap" in df.columns:
                    df["market_cap"] = pd.to_numeric(df["Marcap"], errors="coerce") / 1e8
                else:
                    df["market_cap"] = None
                return df[["code", "market", "name", "market_cap"]].reset_index(drop=True)

            result = await asyncio.to_thread(_fetch)
            if not result.empty:
                await cache_set(UNIVERSE_CACHE_KEY, result.to_dict(orient="records"), ttl=3600)
            return result
        except Exception as exc:
            logger.error("FDR universe fallback failed: %s", exc)
            return pd.DataFrame(columns=["code", "market", "name", "market_cap"])

    async def get_market_cap(self, code: str) -> float | None:
        cache_key = f"{MARKET_CAP_CACHE_PREFIX}:{code}"
        cached = await cache_get(cache_key)
        if isinstance(cached, dict) and "market_cap" in cached:
            value = cached["market_cap"]
            return float(value) if value is not None else None

        universe = await self.get_universe()
        if not universe.empty and "market_cap" in universe.columns:
            matched = universe.loc[universe["code"] == code]
            if not matched.empty:
                value = matched.iloc[0].get("market_cap")
                market_cap = float(value) if pd.notna(value) else None
                await cache_set(cache_key, {"market_cap": market_cap}, ttl=3600)
                return market_cap

        try:
            from pykrx import stock as krx

            today = datetime.today().strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_market_cap, today, today, code)
            if df.empty:
                await cache_set(cache_key, {"market_cap": None}, ttl=900)
                return None
            market_cap = float(df["\uc2dc\uac00\ucd1d\uc561"].iloc[0] / 1e8)
            await cache_set(cache_key, {"market_cap": market_cap}, ttl=3600)
            return market_cap
        except Exception:
            await cache_set(cache_key, {"market_cap": None}, ttl=900)
            return None

    async def get_stock_name(self, code: str) -> str:
        try:
            from pykrx import stock as krx

            result = await asyncio.to_thread(krx.get_market_ticker_name, code)
            return str(result) if result and not hasattr(result, 'empty') else code
        except Exception:
            return code

    async def get_index_ohlcv(self, index_code: str, start: date, end: date) -> pd.DataFrame:
        try:
            from pykrx import stock as krx

            start_str = start.strftime("%Y%m%d")
            end_str = end.strftime("%Y%m%d")
            df = await asyncio.to_thread(krx.get_index_ohlcv, start_str, end_str, index_code)
            if df.empty:
                return pd.DataFrame()

            normalized = df.rename(columns={key: value for key, value in KRX_OHLCV_COLUMNS.items() if value != "amount"})
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

    def _empty_frame(self, **attrs: object) -> pd.DataFrame:
        df = pd.DataFrame()
        df.attrs.update(attrs)
        return df

    def _with_attrs(self, df: pd.DataFrame, **attrs: object) -> pd.DataFrame:
        copied = df.copy()
        copied.attrs.update({key: value for key, value in attrs.items() if value is not None})
        return copied


_fetcher: KRXDataFetcher | None = None


def get_data_fetcher() -> KRXDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = KRXDataFetcher()
    return _fetcher
