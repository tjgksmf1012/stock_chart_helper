from __future__ import annotations

import httpx
import pytest

from app.services.notification_service import send_telegram_message, settings, telegram_configured


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")


def test_not_configured_when_token_missing(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    assert telegram_configured() is False


def test_not_configured_when_chat_id_missing(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    assert telegram_configured() is False


def test_configured_when_both_present(configured):
    assert telegram_configured() is True


@pytest.mark.anyio
async def test_send_message_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    assert await send_telegram_message("hello") is False


@pytest.mark.anyio
async def test_send_message_posts_to_telegram_api(configured):
    import json as json_module
    import unittest.mock

    import app.services.notification_service as notif_module

    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    with unittest.mock.patch.object(notif_module.httpx, "AsyncClient", _Client):
        result = await send_telegram_message("hello world")

    assert result is True
    assert "test-token" in captured_request["url"]
    body = json_module.loads(captured_request["body"])
    assert body["chat_id"] == "12345"
    assert body["text"] == "hello world"


@pytest.mark.anyio
async def test_send_message_returns_false_on_http_error(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"ok": False, "description": "forbidden"})

    import app.services.notification_service as notif_module
    import unittest.mock

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    with unittest.mock.patch.object(notif_module.httpx, "AsyncClient", _Client):
        result = await send_telegram_message("hello")

    assert result is False
