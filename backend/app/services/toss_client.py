from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ..core.config import get_settings
from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()

TOKEN_TTL_FALLBACK = 60 * 60 * 12
MAX_SYMBOLS_PER_REQUEST = 200
MAX_CANDLES_PER_PAGE = 200


class TossClient:
    """Thin async client for the Toss Securities Open API (Market Data group only).

    This app only reads market data (price/candles) for pattern analysis — it never
    places orders, so Account/Asset/Order endpoints are intentionally not implemented.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = settings.toss_base_url.rstrip("/")
        self._transport = transport
        self._token_cache_file = Path(settings.toss_token_cache_path)
        self._token_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(max(1, int(settings.toss_max_concurrent_requests)))
        self._request_spacing_lock = asyncio.Lock()
        self._request_spacing_seconds = max(0.0, float(settings.toss_request_spacing_ms) / 1000.0)
        self._next_request_at = 0.0
        self.timeout = httpx.Timeout(10.0, connect=5.0)

    @property
    def configured(self) -> bool:
        return bool(settings.toss_client_id and settings.toss_client_secret)

    @property
    def _token_cache_key(self) -> str:
        suffix = settings.toss_client_id[-8:] if settings.toss_client_id else "default"
        return f"toss:access-token:{suffix}"

    async def fetch_current_prices(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        """Batch current-price lookup. Toss allows up to 200 symbols per call."""
        if not self.configured or not codes:
            return {}

        results: dict[str, dict[str, Any]] = {}
        for i in range(0, len(codes), MAX_SYMBOLS_PER_REQUEST):
            batch = codes[i : i + MAX_SYMBOLS_PER_REQUEST]
            payload = await self._authorized_get("/api/v1/prices", params={"symbols": ",".join(batch)})
            for row in payload.get("result") or []:
                symbol = str(row.get("symbol") or "")
                if not symbol:
                    continue
                results[symbol] = {
                    "symbol": symbol,
                    "close": self._to_float(row.get("lastPrice")),
                    "timestamp": row.get("timestamp"),
                    "currency": row.get("currency"),
                }
        return results

    async def fetch_current_price(self, code: str) -> dict[str, Any] | None:
        prices = await self.fetch_current_prices([code])
        return prices.get(code)

    async def fetch_minute_candles(self, code: str, count: int = 200, max_pages: int = 4) -> pd.DataFrame:
        return await self._fetch_candles(code, interval="1m", count=count, max_pages=max_pages)

    async def fetch_daily_candles(self, code: str, count: int = 200, max_pages: int = 2) -> pd.DataFrame:
        return await self._fetch_candles(code, interval="1d", count=count, max_pages=max_pages)

    async def _fetch_candles(self, code: str, interval: str, count: int, max_pages: int) -> pd.DataFrame:
        if not self.configured:
            return pd.DataFrame()

        pages: list[pd.DataFrame] = []
        before: str | None = None
        collected = 0

        for _ in range(max_pages):
            params: dict[str, Any] = {
                "symbol": code,
                "interval": interval,
                "count": min(MAX_CANDLES_PER_PAGE, max(1, count - collected)) if count else MAX_CANDLES_PER_PAGE,
            }
            if before:
                params["before"] = before

            payload = await self._authorized_get("/api/v1/candles", params=params)
            result = payload.get("result") or {}
            candles = result.get("candles") or []
            if not candles:
                break

            pages.append(self._normalize_candles(candles))
            collected += len(candles)

            next_before = result.get("nextBefore")
            if not next_before or (count and collected >= count):
                break
            before = next_before

        if not pages:
            return pd.DataFrame()

        merged = pd.concat(pages, ignore_index=True)
        merged = merged.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")
        return merged.reset_index(drop=True)

    def _normalize_candles(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            timestamp = self._parse_timestamp(row.get("timestamp"))
            open_price = self._to_float(row.get("openPrice"))
            high_price = self._to_float(row.get("highPrice"))
            low_price = self._to_float(row.get("lowPrice"))
            close_price = self._to_float(row.get("closePrice"))
            volume = self._to_int(row.get("volume")) or 0

            if timestamp is None or None in (open_price, high_price, low_price, close_price):
                continue

            normalized.append(
                {
                    "datetime": timestamp,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                    "amount": None,
                }
            )
        return pd.DataFrame(normalized)

    async def ensure_access_token(self) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Toss client is not configured.")
        await self._get_access_token()
        return {"configured": True, "base_url": self.base_url}

    async def get_cached_token_status(self) -> dict[str, Any]:
        token = await self._read_cached_token()
        return {"configured": self.configured, "token_cached": bool(token), "base_url": self.base_url}

    async def _authorized_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        return await self._request_json("GET", path, headers=headers, params=params)

    async def _get_access_token(self) -> str:
        cached_token = await self._read_cached_token()
        if cached_token:
            return cached_token

        async with self._token_lock:
            cached_token = await self._read_cached_token()
            if cached_token:
                return cached_token

            logger.info("Issuing a new Toss access token (client credentials grant).")
            payload = await self._request_json(
                "POST",
                "/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.toss_client_id,
                    "client_secret": settings.toss_client_secret,
                },
            )
            token = payload.get("access_token")
            if not token:
                raise RuntimeError("Toss access token was not returned.")

            ttl = self._get_token_ttl(payload)
            await cache_set(self._token_cache_key, {"access_token": token}, ttl)
            self._write_file_cached_token(str(token), ttl)
            return str(token)

    async def _read_cached_token(self) -> str | None:
        cached = await cache_get(self._token_cache_key)
        if isinstance(cached, dict) and cached.get("access_token"):
            return str(cached["access_token"])

        file_cached = self._read_file_cached_token()
        if file_cached:
            ttl_remaining = max(60, int(float(file_cached["expires_at"]) - datetime.now().timestamp()))
            await cache_set(self._token_cache_key, {"access_token": file_cached["access_token"]}, ttl_remaining)
            return str(file_cached["access_token"])
        return None

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self._request_semaphore:
            await self._respect_request_spacing()
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self._transport) as client:
                response = await client.request(method, path, headers=headers, params=params, data=data)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "1") or 1)
            logger.warning("Toss API rate limited on %s; retrying after %.1fs", path, retry_after)
            await asyncio.sleep(min(retry_after, 10.0))
            async with self._request_semaphore:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self._transport) as client:
                    response = await client.request(method, path, headers=headers, params=params, data=data)

        response.raise_for_status()
        return response.json()

    async def _respect_request_spacing(self) -> None:
        if self._request_spacing_seconds <= 0:
            return
        loop = asyncio.get_running_loop()
        async with self._request_spacing_lock:
            now = loop.time()
            wait_seconds = max(0.0, self._next_request_at - now)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                now = loop.time()
            self._next_request_at = max(now, self._next_request_at) + self._request_spacing_seconds

    def _get_token_ttl(self, payload: dict[str, Any]) -> int:
        expires_in = payload.get("expires_in")
        if expires_in:
            try:
                # 토스는 client당 활성 토큰이 1개뿐이고 재발급 시 기존 토큰이 즉시
                # 무효화되므로, 만료보다 여유 있게(10분) 일찍 갱신해 겹침을 피한다.
                return max(60, int(expires_in) - 600)
            except (TypeError, ValueError):
                pass
        return TOKEN_TTL_FALLBACK

    def _read_file_cached_token(self) -> dict[str, str | float] | None:
        try:
            if not self._token_cache_file.exists():
                return None
            payload = json.loads(self._token_cache_file.read_text(encoding="utf-8"))
            access_token = payload.get("access_token")
            expires_at = float(payload.get("expires_at", 0))
            if not access_token or expires_at <= datetime.now().timestamp():
                return None
            return {"access_token": str(access_token), "expires_at": expires_at}
        except Exception:
            return None

    def _write_file_cached_token(self, access_token: str, ttl: int) -> None:
        try:
            self._token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {"access_token": access_token, "expires_at": datetime.now().timestamp() + ttl}
            self._token_cache_file.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to write Toss token file cache: %s", exc)

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value))
            return dt.replace(tzinfo=None)
        except ValueError:
            return None

    def _to_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return None


_toss_client: TossClient | None = None


def get_toss_client() -> TossClient:
    global _toss_client
    if _toss_client is None:
        _toss_client = TossClient()
    return _toss_client
