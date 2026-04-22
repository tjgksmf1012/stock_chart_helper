"""Cached OpenAI overlay for recommendation commentary.

The API key is read only from server-side environment variables. Nothing here is
safe to run in the browser.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import Any

import httpx
import structlog

from ..api.schemas import AiRecommendationResponse
from ..core.config import get_settings
from ..core.redis import cache_get, cache_set

logger = structlog.get_logger()

_OVERLAY_CACHE_PREFIX = "ai:recommendation-overlay:v4"
_IN_FLIGHT_REFRESHES: set[str] = set()


async def apply_openai_recommendation_overlay(response: AiRecommendationResponse) -> AiRecommendationResponse:
    settings = get_settings()
    if not settings.openai_enable_recommendations:
        return response.model_copy(
            update={
                "llm_enabled": False,
                "llm_model": settings.openai_model or None,
                "llm_status": "disabled",
                "llm_source": "rule_based",
            }
        )
    if not settings.openai_api_key:
        return response.model_copy(
            update={
                "llm_enabled": False,
                "llm_model": settings.openai_model or None,
                "llm_status": "missing_api_key",
                "llm_source": "rule_based",
            }
        )

    payload = _make_prompt_payload(response)
    cache_key = _overlay_cache_key(payload)
    refresh_after = max(60, int(settings.openai_overlay_refresh_after_seconds))
    cache_ttl = max(refresh_after + 60, int(settings.openai_overlay_cache_ttl_seconds))

    cached = await _read_cached_overlay(cache_key)
    if cached.get("overlay"):
        stale = _is_stale(cached.get("cached_at"), refresh_after)
        if stale:
            await _schedule_overlay_refresh(cache_key=cache_key, payload=payload, cache_ttl=cache_ttl)
        return _apply_overlay(response, cached["overlay"]).model_copy(
            update={
                "llm_enabled": True,
                "llm_model": settings.openai_model,
                "llm_error": cached.get("last_error"),
                "llm_status": "cached_refreshing" if stale else "cached",
                "llm_cached_at": cached.get("cached_at"),
                "llm_refreshing": bool(stale or cached.get("refreshing")),
                "llm_source": "openai_cache",
            }
        )

    should_retry = _is_stale(cached.get("last_attempt_at"), refresh_after)
    scheduled = False
    if should_retry:
        scheduled = await _schedule_overlay_refresh(cache_key=cache_key, payload=payload, cache_ttl=cache_ttl)
    return response.model_copy(
        update={
            "llm_enabled": False,
            "llm_model": settings.openai_model or None,
            "llm_error": cached.get("last_error"),
            "llm_status": "refreshing" if scheduled or cached.get("refreshing") else "rule_only",
            "llm_cached_at": cached.get("cached_at"),
            "llm_refreshing": bool(scheduled or cached.get("refreshing")),
            "llm_source": "rule_based",
        }
    )


async def _request_overlay(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    body = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a cautious Korean equity portfolio assistant. "
                    "Rewrite the supplied rule-based scan commentary into concise Korean portfolio notes for daily execution. "
                    "Keep the tone operational, concrete, and slightly conservative. "
                    "Avoid vague phrasing. Do not promise returns and do not use direct buy or sell imperatives. "
                    "For each item, produce these exact fields in Korean: summary, action_line, do_now, avoid_if, review_price, skip_reason, overlap_risk, position_hint, next_actions. "
                    "Formatting rules: "
                    "action_line must start with '지금 할 일:' and include a condition or price zone followed by the next action. "
                    "avoid_if must clearly state the entry-ban condition. "
                    "review_price must be a re-check price or condition. "
                    "skip_reason must say why this can be ignored today. "
                    "overlap_risk must mention duplicate exposure or concentration when relevant, otherwise return an empty string. "
                    "next_actions should be a short 2-4 step operator checklist."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        "reasoning": {
            "effort": "minimal",
        },
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "recommendation_overlay",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "market_brief": {"type": "string"},
                        "portfolio_guidance": {"type": "string"},
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "symbol_code": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "action_line": {"type": "string"},
                                    "do_now": {"type": "string"},
                                    "avoid_if": {"type": "string"},
                                    "review_price": {"type": "string"},
                                    "skip_reason": {"type": "string"},
                                    "overlap_risk": {"type": "string"},
                                    "position_hint": {"type": "string"},
                                    "next_actions": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "maxItems": 4,
                                    },
                                },
                                "required": [
                                    "symbol_code",
                                    "summary",
                                    "action_line",
                                    "do_now",
                                    "avoid_if",
                                    "review_price",
                                    "skip_reason",
                                    "overlap_risk",
                                    "position_hint",
                                    "next_actions",
                                ],
                            },
                            "maxItems": settings.openai_overlay_item_limit,
                        },
                    },
                    "required": ["market_brief", "portfolio_guidance", "items"],
                },
                "strict": True,
            }
        },
        "max_output_tokens": settings.openai_max_output_tokens,
    }

    async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
        result = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        result.raise_for_status()
        data = result.json()

    text = data.get("output_text") or _extract_output_text(data)
    if not text:
        raise ValueError("OpenAI response did not include text output")
    return _parse_overlay_json(text)


def _make_prompt_payload(response: AiRecommendationResponse) -> dict[str, Any]:
    settings = get_settings()
    item_limit = max(1, int(settings.openai_overlay_item_limit))
    items = []
    for item in response.items[:item_limit]:
        items.append(
            {
                "symbol_code": item.symbol.code,
                "symbol_name": item.symbol.name,
                "stance": item.stance_label,
                "score": round(item.score, 1),
                "confidence": round(item.confidence, 3),
                "pattern_type": item.pattern_type,
                "state": item.state,
                "p_up": round(item.p_up, 3),
                "trade_readiness": round(item.trade_readiness_score, 3),
                "entry_window": round(item.entry_window_score, 3),
                "reward_risk_ratio": round(item.reward_risk_ratio, 2),
                "data_quality": round(item.data_quality, 3),
                "risk_flags": item.risk_flags[:3],
                "rule_summary": item.summary,
                "rule_action_line": item.action_line,
                "rule_do_now": item.do_now,
                "rule_avoid_if": item.avoid_if,
                "rule_review_price": item.review_price,
                "rule_skip_reason": item.skip_reason,
                "rule_overlap_risk": item.overlap_risk,
                "watchlist_priority": item.watchlist_priority,
                "next_trigger": item.next_trigger,
            }
        )
    return {
        "timeframe": response.timeframe,
        "timeframe_label": response.timeframe_label,
        "rule_market_brief": response.market_brief,
        "rule_portfolio_guidance": response.portfolio_guidance,
        "items": items,
    }


def _apply_overlay(response: AiRecommendationResponse, overlay: dict[str, Any]) -> AiRecommendationResponse:
    updates = {str(item.get("symbol_code")): item for item in overlay.get("items", []) if item.get("symbol_code")}

    def apply_item(item):
        update = updates.get(item.symbol.code)
        if not update:
            return item
        return item.model_copy(
            update={
                "summary": str(update.get("summary") or item.summary),
                "action_line": str(update.get("action_line") or item.action_line),
                "do_now": str(update.get("do_now") or item.do_now),
                "avoid_if": str(update.get("avoid_if") or item.avoid_if),
                "review_price": str(update.get("review_price") or item.review_price),
                "skip_reason": str(update.get("skip_reason") or item.skip_reason),
                "overlap_risk": str(update.get("overlap_risk") or item.overlap_risk),
                "position_hint": str(update.get("position_hint") or item.position_hint),
                "next_actions": [str(action) for action in update.get("next_actions", item.next_actions)][:5],
            }
        )

    return response.model_copy(
        update={
            "market_brief": str(overlay.get("market_brief") or response.market_brief),
            "portfolio_guidance": str(overlay.get("portfolio_guidance") or response.portfolio_guidance),
            "items": [apply_item(item) for item in response.items],
            "priority_items": [apply_item(item) for item in response.priority_items],
            "watch_items": [apply_item(item) for item in response.watch_items],
            "risk_items": [apply_item(item) for item in response.risk_items],
            "watchlist_focus_items": [apply_item(item) for item in response.watchlist_focus_items],
        }
    )


async def _read_cached_overlay(cache_key: str) -> dict[str, Any]:
    cached = await cache_get(cache_key)
    if isinstance(cached, dict):
        return cached
    return {}


async def _schedule_overlay_refresh(*, cache_key: str, payload: dict[str, Any], cache_ttl: int) -> bool:
    if cache_key in _IN_FLIGHT_REFRESHES:
        return False

    cached = await _read_cached_overlay(cache_key)
    _IN_FLIGHT_REFRESHES.add(cache_key)
    now = _utcnow_iso()
    await cache_set(
        cache_key,
        {
            "overlay": cached.get("overlay"),
            "cached_at": cached.get("cached_at"),
            "last_error": cached.get("last_error"),
            "last_attempt_at": now,
            "refreshing": True,
        },
        ttl=cache_ttl,
    )

    async def _runner() -> None:
        previous = await _read_cached_overlay(cache_key)
        try:
            overlay = await _request_overlay(payload)
        except Exception as exc:  # pragma: no cover - network/provider dependent
            error_code = _classify_openai_error(exc)
            logger.warning("OpenAI recommendation overlay failed", error=str(exc), error_code=error_code)
            await cache_set(
                cache_key,
                {
                    "overlay": previous.get("overlay"),
                    "cached_at": previous.get("cached_at"),
                    "last_error": error_code,
                    "last_attempt_at": _utcnow_iso(),
                    "refreshing": False,
                },
                ttl=cache_ttl,
            )
        else:
            cached_at = _utcnow_iso()
            await cache_set(
                cache_key,
                {
                    "overlay": overlay,
                    "cached_at": cached_at,
                    "last_error": None,
                    "last_attempt_at": cached_at,
                    "refreshing": False,
                },
                ttl=cache_ttl,
            )
        finally:
            _IN_FLIGHT_REFRESHES.discard(cache_key)

    asyncio.create_task(_runner())
    return True


def _overlay_cache_key(payload: dict[str, Any]) -> str:
    items = payload.get("items", [])
    signature = {
        "timeframe": payload.get("timeframe"),
        "items": [
            {
                "symbol_code": item.get("symbol_code"),
                "stance": item.get("stance"),
                "score": item.get("score"),
                "confidence": item.get("confidence"),
                "p_up": item.get("p_up"),
                "trade_readiness": item.get("trade_readiness"),
                "entry_window": item.get("entry_window"),
                "rule_do_now": item.get("rule_do_now"),
                "rule_review_price": item.get("rule_review_price"),
            }
            for item in items
        ],
    }
    digest = hashlib.sha1(json.dumps(signature, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:16]
    return f"{_OVERLAY_CACHE_PREFIX}:{payload.get('timeframe', '1d')}:{digest}"


def _is_stale(timestamp: str | None, refresh_after_seconds: int) -> bool:
    if not timestamp:
        return True
    try:
        cached_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if cached_at.tzinfo is not None:
            cached_at = cached_at.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return True
    return cached_at < datetime.utcnow() - timedelta(seconds=refresh_after_seconds)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _extract_output_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "".join(chunks)


def _parse_overlay_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    candidates = [raw]

    if raw.startswith("```"):
        stripped = raw.strip("`")
        if "\n" in stripped:
            _, _, remainder = stripped.partition("\n")
            candidates.append(remainder.strip())

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1].strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except JSONDecodeError:
            continue

    raise JSONDecodeError("Unable to parse OpenAI overlay JSON", raw, 0)


def _classify_openai_error(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "openai_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return "openai_auth_error"
        if status == 429:
            return "openai_rate_limited"
        if 400 <= status < 500:
            return "openai_bad_request"
        return "openai_provider_error"
    if isinstance(exc, JSONDecodeError):
        return "openai_output_parse_error"
    return "openai_unavailable"
