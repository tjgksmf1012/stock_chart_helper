from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from ..schemas import CacheRuntimeStatus, KisRuntimeStatus, RuntimeStatusResponse
from ...core.config import get_settings
from ...core.redis import cache_backend_status
from ...services.kis_client import get_kis_client

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()


def _read_token_cache_status(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return {
            "token_cached": False,
            "token_expires_at": None,
            "token_expires_in_seconds": None,
            "resolved_base_url": None,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expires_at = float(payload.get("expires_at", 0))
        remaining = int(expires_at - datetime.now().timestamp())
        if remaining <= 0:
            return {
                "token_cached": False,
                "token_expires_at": datetime.fromtimestamp(expires_at).isoformat() if expires_at else None,
                "token_expires_in_seconds": 0,
                "resolved_base_url": payload.get("base_url"),
            }

        return {
            "token_cached": bool(payload.get("access_token")),
            "token_expires_at": datetime.fromtimestamp(expires_at).isoformat(),
            "token_expires_in_seconds": remaining,
            "resolved_base_url": payload.get("base_url"),
        }
    except Exception:
        return {
            "token_cached": False,
            "token_expires_at": None,
            "token_expires_in_seconds": None,
            "resolved_base_url": None,
        }


def _kis_guidance(configured: bool, token_cached: bool, token_remaining: int | None) -> list[str]:
    guidance: list[str] = []
    if not configured:
        guidance.append("KIS App Key/App Secret이 설정되지 않아 분봉은 저장/공개 데이터 위주로 동작합니다.")
    elif not token_cached:
        guidance.append("현재 저장된 KIS 토큰이 없습니다. 첫 실시간 요청 때 토큰을 1회 발급합니다.")
    elif token_remaining is not None and token_remaining < 60 * 60:
        guidance.append("KIS 토큰 만료가 1시간 이내입니다. 만료 후 다음 실시간 요청에서 새 토큰을 발급합니다.")
    else:
        guidance.append("KIS 토큰 캐시가 살아 있어 불필요한 재발급 없이 재사용할 수 있습니다.")

    guidance.append("KIS 토큰은 파일/Redis 캐시를 먼저 확인하므로 24시간 내 잦은 재발급을 피하도록 설계되어 있습니다.")
    guidance.append("분봉 정확도는 실시간 KIS 데이터와 로컬 분봉 저장 캐시가 쌓일수록 좋아집니다.")
    return guidance


@router.get("/status", response_model=RuntimeStatusResponse)
async def get_runtime_status() -> RuntimeStatusResponse:
    kis = get_kis_client()
    token_status = _read_token_cache_status(settings.kis_token_cache_path)
    cache_status = await cache_backend_status()
    configured = kis.configured
    token_cached = bool(token_status["token_cached"])
    token_remaining = token_status["token_expires_in_seconds"]

    return RuntimeStatusResponse(
        generated_at=datetime.utcnow().isoformat(),
        app_name=settings.app_name,
        debug=settings.debug,
        kis=KisRuntimeStatus(
            configured=configured,
            environment=settings.kis_env,
            token_cached=token_cached,
            token_expires_at=token_status["token_expires_at"],
            token_expires_in_seconds=token_remaining,
            resolved_base_url=token_status["resolved_base_url"] or kis._resolved_base_url,
            token_cache_path=settings.kis_token_cache_path,
            max_concurrent_requests=settings.kis_max_concurrent_requests,
            request_spacing_ms=settings.kis_request_spacing_ms,
            guidance=_kis_guidance(configured, token_cached, token_remaining),
        ),
        cache=CacheRuntimeStatus(**cache_status),
        scheduler_enabled=True,
        data_notes=[
            "일봉/주봉/월봉은 KRX 일봉을 기준으로 재샘플링합니다.",
            "분봉은 KIS 당일 분봉, Yahoo 공개 분봉, 로컬 저장 캐시를 조합합니다.",
            "스캐너는 KIS 호출을 아끼기 위해 모든 분봉 후보에 live 요청을 하지 않고 우선순위가 높은 후보부터 사용합니다.",
        ],
    )
