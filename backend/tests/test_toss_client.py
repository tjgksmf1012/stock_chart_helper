from __future__ import annotations

import json

import httpx
import pytest

import app.core.redis as cache
from app.services.toss_client import TossClient, settings


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "toss_client_id", "test_client_id")
    monkeypatch.setattr(settings, "toss_client_secret", "test_client_secret")
    monkeypatch.setattr(settings, "toss_token_cache_path", str(tmp_path / "toss_token_cache.json"))
    monkeypatch.setattr(settings, "toss_request_spacing_ms", 0)

    # Force the in-memory cache path so tests don't need a real Redis instance.
    monkeypatch.setattr(cache, "_mem_cache", {})

    async def _no_redis():
        return None

    monkeypatch.setattr(cache, "_try_get_redis", _no_redis)


def _token_response() -> httpx.Response:
    return httpx.Response(200, json={"access_token": "tok-123", "token_type": "Bearer", "expires_in": 86400})


@pytest.mark.anyio
async def test_not_configured_returns_empty(monkeypatch):
    # Explicitly blank out credentials rather than relying on ambient settings —
    # a real .env with live Toss keys (e.g. set for local manual testing) would
    # otherwise silently flip `configured` to True and break this assumption.
    monkeypatch.setattr(settings, "toss_client_id", "")
    monkeypatch.setattr(settings, "toss_client_secret", "")

    client = TossClient()
    assert client.configured is False
    assert await client.fetch_current_prices(["005930"]) == {}
    assert (await client.fetch_minute_candles("005930")).empty


@pytest.mark.anyio
async def test_fetch_current_prices_issues_token_once(configured):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return _token_response()
        if request.url.path == "/api/v1/prices":
            symbols = request.url.params.get("symbols")
            return httpx.Response(
                200,
                json={
                    "result": [
                        {"symbol": s, "timestamp": "2026-03-25T09:30:00+09:00", "lastPrice": "72000", "currency": "KRW"}
                        for s in symbols.split(",")
                    ]
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    client = TossClient(transport=httpx.MockTransport(handler))

    prices_1 = await client.fetch_current_prices(["005930"])
    prices_2 = await client.fetch_current_prices(["000660"])

    assert prices_1["005930"]["close"] == 72000.0
    assert prices_2["000660"]["close"] == 72000.0
    # token endpoint should only be hit once — the second call reuses the cached token
    assert calls.count("/oauth2/token") == 1


@pytest.mark.anyio
async def test_fetch_current_prices_batches_over_200_symbols(configured):
    seen_batch_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_response()
        symbols = request.url.params.get("symbols").split(",")
        seen_batch_sizes.append(len(symbols))
        return httpx.Response(
            200,
            json={
                "result": [
                    {"symbol": s, "timestamp": "2026-03-25T09:30:00+09:00", "lastPrice": "1000", "currency": "KRW"}
                    for s in symbols
                ]
            },
        )

    client = TossClient(transport=httpx.MockTransport(handler))
    codes = [f"{i:06d}" for i in range(250)]
    result = await client.fetch_current_prices(codes)

    assert seen_batch_sizes == [200, 50]
    assert len(result) == 250


@pytest.mark.anyio
async def test_fetch_minute_candles_paginates_with_before_cursor(configured):
    page1 = {
        "result": {
            "candles": [
                {
                    "timestamp": "2026-03-25T09:32:00+09:00",
                    "openPrice": "72000",
                    "highPrice": "72100",
                    "lowPrice": "71950",
                    "closePrice": "72050",
                    "volume": "15200",
                    "currency": "KRW",
                },
            ],
            "nextBefore": "2026-03-25T09:32:00+09:00",
        }
    }
    page2 = {
        "result": {
            "candles": [
                {
                    "timestamp": "2026-03-25T09:31:00+09:00",
                    "openPrice": "71950",
                    "highPrice": "72050",
                    "lowPrice": "71900",
                    "closePrice": "72000",
                    "volume": "18400",
                    "currency": "KRW",
                },
            ],
            "nextBefore": None,
        }
    }

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_response()
        call_count["n"] += 1
        if call_count["n"] == 1:
            assert "before" not in request.url.params
            return httpx.Response(200, json=page1)
        assert request.url.params.get("before") == "2026-03-25T09:32:00+09:00"
        return httpx.Response(200, json=page2)

    client = TossClient(transport=httpx.MockTransport(handler))
    df = await client.fetch_minute_candles("005930", count=200)

    assert len(df) == 2
    assert list(df["close"]) == [72000.0, 72050.0]  # sorted ascending by datetime


@pytest.mark.anyio
async def test_rate_limit_retries_after_429(configured):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_response()
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "rate-limit-exceeded"}})
        return httpx.Response(
            200,
            json={"result": [{"symbol": "005930", "timestamp": "t", "lastPrice": "72000", "currency": "KRW"}]},
        )

    client = TossClient(transport=httpx.MockTransport(handler))
    result = await client.fetch_current_prices(["005930"])

    assert attempts["n"] == 2
    assert result["005930"]["close"] == 72000.0


@pytest.mark.anyio
async def test_token_file_cache_is_reused_across_client_instances(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_response()
        return httpx.Response(
            200,
            json={"result": [{"symbol": "005930", "timestamp": "t", "lastPrice": "1000", "currency": "KRW"}]},
        )

    client_a = TossClient(transport=httpx.MockTransport(handler))
    await client_a.fetch_current_price("005930")

    cache_path = client_a._token_cache_file
    assert cache_path.exists()
    saved = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved["access_token"] == "tok-123"

    # A fresh client (simulating a new process) should read the token from the file cache
    # without issuing a fresh Redis-backed request. We simulate that by wiping the in-memory
    # cache manually.
    cache._mem_cache.clear()
    client_b = TossClient(transport=httpx.MockTransport(handler))
    token = await client_b._get_access_token()
    assert token == "tok-123"
