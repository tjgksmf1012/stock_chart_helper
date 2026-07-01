from __future__ import annotations

import json

import httpx
import pytest

import app.core.redis as cache
from app.services.kis_client import KISClient, settings


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "kis_app_key", "test_app_key")
    monkeypatch.setattr(settings, "kis_app_secret", "test_app_secret")
    monkeypatch.setattr(settings, "kis_env", "prod")
    monkeypatch.setattr(settings, "kis_token_cache_path", str(tmp_path / "kis_token_cache.json"))
    monkeypatch.setattr(settings, "kis_request_spacing_ms", 0)

    monkeypatch.setattr(cache, "_mem_cache", {})

    async def _no_redis():
        return None

    monkeypatch.setattr(cache, "_try_get_redis", _no_redis)


def _token_response() -> dict:
    return {"access_token": "kis-tok-123", "token_type": "Bearer", "expires_in": 86400}


def _patch_client(client: KISClient, handler) -> None:
    """KISClient builds a fresh httpx.AsyncClient(base_url=...) per request instead of
    accepting an injected transport, so we monkeypatch the AsyncClient constructor it uses.
    """
    import app.services.kis_client as kis_module

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    import unittest.mock

    return unittest.mock.patch.object(kis_module.httpx, "AsyncClient", _Client)


@pytest.mark.anyio
async def test_not_configured_short_circuits():
    client = KISClient()
    assert client.configured is False
    assert await client.fetch_current_price("005930") is None
    assert (await client.fetch_today_minute_bars("005930")).empty
    assert await client.fetch_investor_trends("005930") == []


@pytest.mark.anyio
async def test_fetch_current_price_issues_token_once(configured):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json=_token_response())
        if request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            return httpx.Response(
                200,
                json={
                    "rt_cd": "0",
                    "output": {
                        "stck_prpr": "72000",
                        "stck_oprc": "71500",
                        "stck_hgpr": "72300",
                        "stck_lwpr": "71400",
                        "acml_vol": "1000000",
                        "stck_cntg_hour": "093000",
                    },
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    client = KISClient()
    with _patch_client(client, handler):
        price_1 = await client.fetch_current_price("005930")
        price_2 = await client.fetch_current_price("000660")

    assert price_1["close"] == 72000.0
    assert price_2["close"] == 72000.0
    assert calls.count("/oauth2/tokenP") == 1


@pytest.mark.anyio
async def test_fetch_current_price_returns_none_when_output_empty(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json={"rt_cd": "0", "output": {}})

    client = KISClient()
    with _patch_client(client, handler):
        result = await client.fetch_current_price("005930")

    assert result is None


@pytest.mark.anyio
async def test_non_zero_rt_cd_raises(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json={"rt_cd": "1", "msg1": "invalid request"})

    client = KISClient()
    with _patch_client(client, handler):
        with pytest.raises(RuntimeError, match="invalid request"):
            await client.fetch_current_price("005930")


@pytest.mark.anyio
async def test_fetch_investor_trends_converts_units_and_sorts_ascending(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json=_token_response())
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output": [
                    {"stck_bsop_date": "20260625", "frgn_ntby_tr_pbmn": "500", "orgn_ntby_tr_pbmn": "-200", "prsn_ntby_tr_pbmn": "0"},
                    {"stck_bsop_date": "20260624", "frgn_ntby_tr_pbmn": "100", "orgn_ntby_tr_pbmn": "50", "prsn_ntby_tr_pbmn": "0"},
                ],
            },
        )

    client = KISClient()
    with _patch_client(client, handler):
        trends = await client.fetch_investor_trends("005930")

    assert [t["date"] for t in trends] == ["2026-06-24", "2026-06-25"]
    assert trends[-1]["foreign_value_million"] == 500.0
    assert trends[-1]["institution_value_million"] == -200.0


@pytest.mark.anyio
async def test_fetch_today_minute_bars_stops_on_short_page(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json=_token_response())
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output2": [
                    {
                        "stck_bsop_date": "20260625",
                        "stck_cntg_hour": "093100",
                        "stck_oprc": "100",
                        "stck_hgpr": "101",
                        "stck_lwpr": "99",
                        "stck_prpr": "100.5",
                        "cntg_vol": "10",
                    },
                    {
                        "stck_bsop_date": "20260625",
                        "stck_cntg_hour": "093000",
                        "stck_oprc": "99",
                        "stck_hgpr": "100",
                        "stck_lwpr": "98",
                        "stck_prpr": "99.5",
                        "cntg_vol": "20",
                    },
                ],
            },
        )

    client = KISClient()
    with _patch_client(client, handler):
        df = await client.fetch_today_minute_bars("005930", max_pages=5)

    # Only 2 rows returned (< 30), so paging should stop after the first page.
    assert len(df) == 2
    assert list(df["close"]) == [99.5, 100.5]


@pytest.mark.anyio
async def test_token_file_cache_survives_new_client_instance(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json=_token_response())
        return httpx.Response(200, json={"rt_cd": "0", "output": {"stck_prpr": "1000"}})

    client_a = KISClient()
    with _patch_client(client_a, handler):
        await client_a.fetch_current_price("005930")

    cache_path = client_a._token_cache_file
    assert cache_path.exists()
    saved = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved["access_token"] == "kis-tok-123"

    cache._mem_cache.clear()
    client_b = KISClient()
    token = await client_b._get_access_token()
    assert token == "kis-tok-123"
