from __future__ import annotations

import asyncio
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ..core.config import get_settings
from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()

TOKEN_TTL_FALLBACK = 60 * 60 * 6


class KISClient:
    """Thin async client for the KIS quotation endpoints used by the app."""

    def __init__(self) -> None:
        self.prod_base_url = settings.kis_base_url.rstrip("/")
        self.mock_base_url = settings.kis_mock_base_url.rstrip("/")
        self.environment = (settings.kis_env or "auto").strip().lower()
        self._resolved_base_url: str | None = None
        self._token_cache_file = Path(settings.kis_token_cache_path)
        self._token_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(max(1, int(settings.kis_max_concurrent_requests)))
        self._request_spacing_lock = asyncio.Lock()
        self._request_spacing_seconds = max(0.0, float(settings.kis_request_spacing_ms) / 1000.0)
        self._next_request_at = 0.0
        self.timeout = httpx.Timeout(10.0, connect=5.0)

    @property
    def configured(self) -> bool:
        return bool(settings.kis_app_key and settings.kis_app_secret)

    @property
    def _token_cache_key(self) -> str:
        suffix = settings.kis_app_key[-8:] if settings.kis_app_key else "default"
        return f"kis:access-token:{suffix}"

    async def fetch_current_price(self, code: str, market_div_code: str = "J") -> dict[str, Any] | None:
        if not self.configured:
            return None

        payload = await self._authorized_get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={
                "FID_COND_MRKT_DIV_CODE": market_div_code,
                "FID_INPUT_ISCD": code,
            },
        )
        output = payload.get("output") or {}
        if not output:
            return None

        return {
            "symbol": code,
            "close": self._to_float(output.get("stck_prpr")),
            "open": self._to_float(output.get("stck_oprc")),
            "high": self._to_float(output.get("stck_hgpr")),
            "low": self._to_float(output.get("stck_lwpr")),
            "volume": self._to_int(output.get("acml_vol")),
            "timestamp": output.get("stck_cntg_hour"),
        }

    async def fetch_today_minute_bars(
        self,
        code: str,
        market_div_code: str = "J",
        max_pages: int = 16,
    ) -> pd.DataFrame:
        """
        Fetch today's minute bars from KIS and walk backward in time.

        The official API returns today's data only and a single response contains up to
        30 rows, so we move the time cursor backward page by page to assemble a fuller day.
        """
        if not self.configured:
            return pd.DataFrame()

        cursor = "153000"
        seen_cursors: set[str] = set()
        pages: list[pd.DataFrame] = []

        for _ in range(max_pages):
            if cursor in seen_cursors:
                break
            seen_cursors.add(cursor)

            try:
                payload = await self._authorized_get(
                    "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                    tr_id="FHKST03010200",
                    params={
                        "FID_ETC_CLS_CODE": "",
                        "FID_COND_MRKT_DIV_CODE": market_div_code,
                        "FID_INPUT_ISCD": code,
                        "FID_INPUT_HOUR_1": cursor,
                        "FID_PW_DATA_INCU_YN": "Y",
                    },
                )
            except Exception as exc:
                if pages:
                    logger.warning("KIS minute paging stopped early for %s at %s: %s", code, cursor, exc)
                    break
                raise
            batch = self._normalize_minute_rows(payload.get("output2") or payload.get("output") or [])
            if batch.empty:
                break

            pages.append(batch)
            oldest_timestamp = batch["datetime"].min()
            next_cursor = (oldest_timestamp - timedelta(minutes=1)).strftime("%H%M%S")
            if next_cursor >= cursor or len(batch) < 30:
                break
            cursor = next_cursor

        if not pages:
            return pd.DataFrame()

        merged = pd.concat(pages, ignore_index=True)
        merged = merged.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")
        merged["amount"] = None
        return merged.reset_index(drop=True)[["datetime", "open", "high", "low", "close", "volume", "amount"]]

    async def _authorized_get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        return await self._request_json("GET", path, headers=headers, params=params)

    async def _get_access_token(self) -> str:
        cached_token = await self._read_cached_token()
        if cached_token:
            return cached_token

        async with self._token_lock:
            cached_token = await self._read_cached_token()
            if cached_token:
                return cached_token

            logger.info("Issuing a new KIS access token. This should be rare because the token is reused until expiry.")
            last_error: Exception | None = None
            for base_url in self._candidate_base_urls():
                try:
                    payload = await self._request_json(
                        "POST",
                        "/oauth2/tokenP",
                        json_body={
                            "grant_type": "client_credentials",
                            "appkey": settings.kis_app_key,
                            "appsecret": settings.kis_app_secret,
                        },
                        base_url=base_url,
                    )
                    token = payload.get("access_token")
                    if not token:
                        raise RuntimeError("KIS access token was not returned.")

                    ttl = self._get_token_ttl(payload)
                    self._resolved_base_url = base_url
                    await cache_set(self._token_cache_key, {"access_token": token, "base_url": base_url}, ttl)
                    self._write_file_cached_token(str(token), base_url, ttl)
                    return str(token)
                except Exception as exc:
                    last_error = exc
                    logger.warning("KIS token issuance failed via %s: %s", base_url, exc)

            if last_error is not None:
                if isinstance(last_error, httpx.HTTPStatusError) and last_error.response.status_code == 403:
                    raise RuntimeError(
                        "KIS token issuance returned 403 Forbidden. Check whether Open API service enrollment is completed, "
                        "the app key/secret is activated, and whether the key is for prod or mock(vps)."
                    ) from last_error
                raise last_error
            raise RuntimeError("KIS access token could not be issued.")

    async def _read_cached_token(self) -> str | None:
        cached = await cache_get(self._token_cache_key)
        if isinstance(cached, dict) and cached.get("access_token"):
            cached_base_url = cached.get("base_url")
            if isinstance(cached_base_url, str) and cached_base_url:
                self._resolved_base_url = cached_base_url
            return str(cached["access_token"])

        file_cached = self._read_file_cached_token()
        if file_cached:
            self._resolved_base_url = str(file_cached["base_url"])
            ttl_remaining = max(60, int(float(file_cached["expires_at"]) - datetime.now().timestamp()))
            await cache_set(
                self._token_cache_key,
                {"access_token": file_cached["access_token"], "base_url": file_cached["base_url"]},
                ttl_remaining,
            )
            return str(file_cached["access_token"])
        return None

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        target_base_url = base_url or self._resolved_base_url or self.prod_base_url
        async with self._request_semaphore:
            await self._respect_request_spacing()
            async with httpx.AsyncClient(base_url=target_base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, headers=headers, params=params, json=json_body)

        response.raise_for_status()
        payload = response.json()
        rt_cd = payload.get("rt_cd")
        if rt_cd and rt_cd != "0":
            message = payload.get("msg1") or payload.get("msg_cd") or "KIS API request failed."
            raise RuntimeError(f"{message} (rt_cd={rt_cd})")
        return payload

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
                return max(60, int(expires_in) - 300)
            except (TypeError, ValueError):
                pass

        expired_at = payload.get("access_token_token_expired")
        if isinstance(expired_at, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
                try:
                    delta = datetime.strptime(expired_at, fmt) - datetime.now()
                    return max(60, int(delta.total_seconds()) - 300)
                except ValueError:
                    continue

        return TOKEN_TTL_FALLBACK

    def _candidate_base_urls(self) -> list[str]:
        if self.environment in {"prod", "live"}:
            return [self.prod_base_url]
        if self.environment in {"vps", "mock", "paper"}:
            return [self.mock_base_url]
        return [self.prod_base_url, self.mock_base_url]

    def _read_file_cached_token(self) -> dict[str, str | float] | None:
        try:
            if not self._token_cache_file.exists():
                return None
            payload = json.loads(self._token_cache_file.read_text(encoding="utf-8"))
            access_token = payload.get("access_token")
            base_url = payload.get("base_url")
            expires_at = float(payload.get("expires_at", 0))
            if not access_token or not base_url or expires_at <= datetime.now().timestamp():
                return None
            return {"access_token": str(access_token), "base_url": str(base_url), "expires_at": expires_at}
        except Exception:
            return None

    def _write_file_cached_token(self, access_token: str, base_url: str, ttl: int) -> None:
        try:
            self._token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "access_token": access_token,
                "base_url": base_url,
                "expires_at": datetime.now().timestamp() + ttl,
            }
            self._token_cache_file.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to write KIS token file cache: %s", exc)

    def _normalize_minute_rows(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        current_date = datetime.now().strftime("%Y%m%d")
        normalized_rows: list[dict[str, Any]] = []

        for row in rows:
            date_text = str(self._pick(row, "stck_bsop_date", "bsop_date") or current_date)
            time_text = str(self._pick(row, "stck_cntg_hour", "cntg_hour") or "").zfill(6)
            timestamp = self._parse_timestamp(date_text, time_text)
            open_price = self._to_float(self._pick(row, "stck_oprc", "open"))
            high_price = self._to_float(self._pick(row, "stck_hgpr", "high"))
            low_price = self._to_float(self._pick(row, "stck_lwpr", "low"))
            close_price = self._to_float(self._pick(row, "stck_prpr", "close"))
            volume = self._to_int(self._pick(row, "cntg_vol", "volume", "acml_vol")) or 0

            if not timestamp or None in (open_price, high_price, low_price, close_price):
                continue

            normalized_rows.append(
                {
                    "datetime": timestamp,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        if not normalized_rows:
            return pd.DataFrame()

        return pd.DataFrame(normalized_rows)

    def _parse_timestamp(self, date_text: str, time_text: str) -> datetime | None:
        if len(date_text) != 8 or len(time_text) != 6:
            return None
        try:
            return datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M%S")
        except ValueError:
            return None

    def _pick(self, row: dict[str, Any], *keys: str) -> Any | None:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
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


_kis_client: KISClient | None = None


def get_kis_client() -> KISClient:
    global _kis_client
    if _kis_client is None:
        _kis_client = KISClient()
    return _kis_client
