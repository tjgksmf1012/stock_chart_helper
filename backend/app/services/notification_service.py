"""텔레그램 알림 발송 — 토큰/chat_id 미설정 시 조용히 no-op."""
from __future__ import annotations

import logging

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def telegram_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


async def send_telegram_message(text: str) -> bool:
    """텔레그램 메시지 발송. 실패해도 예외를 올리지 않는다 (알림은 부가 기능)."""
    if not telegram_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("telegram send failed: %s", exc)
        return False
