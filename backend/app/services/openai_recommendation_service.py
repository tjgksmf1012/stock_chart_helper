"""OpenAI overlay for recommendation commentary.

The API key is read only from server-side environment variables. Nothing here is
safe to run in the browser.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from ..api.schemas import AiRecommendationResponse
from ..core.config import get_settings

logger = structlog.get_logger()


async def apply_openai_recommendation_overlay(response: AiRecommendationResponse) -> AiRecommendationResponse:
    settings = get_settings()
    if not settings.openai_enable_recommendations or not settings.openai_api_key:
        return response.model_copy(update={"llm_enabled": False, "llm_model": settings.openai_model or None})

    payload = _make_prompt_payload(response)
    try:
        overlay = await _request_overlay(payload)
    except Exception as exc:  # pragma: no cover - network/provider dependent
        logger.warning("OpenAI recommendation overlay failed", error=str(exc))
        return response.model_copy(
            update={
                "llm_enabled": False,
                "llm_model": settings.openai_model,
                "llm_error": "openai_unavailable",
            }
        )

    return _apply_overlay(response, overlay).model_copy(
        update={"llm_enabled": True, "llm_model": settings.openai_model, "llm_error": None}
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
                    "Write concise Korean commentary from the supplied quantitative scan data. "
                    "Do not promise returns, do not say 'buy now', and always keep the tone as analysis support."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
        "text": {
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
                                    "position_hint": {"type": "string"},
                                    "next_actions": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "maxItems": 4,
                                    },
                                },
                                "required": ["symbol_code", "summary", "position_hint", "next_actions"],
                            },
                            "maxItems": 8,
                        },
                    },
                    "required": ["market_brief", "portfolio_guidance", "items"],
                },
                "strict": True,
            }
        },
        "max_output_tokens": 1400,
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
    return json.loads(text)


def _make_prompt_payload(response: AiRecommendationResponse) -> dict[str, Any]:
    items = []
    for item in response.items[:8]:
        items.append(
            {
                "symbol_code": item.symbol.code,
                "symbol_name": item.symbol.name,
                "stance": item.stance_label,
                "score": item.score,
                "confidence": item.confidence,
                "pattern_type": item.pattern_type,
                "state": item.state,
                "p_up": item.p_up,
                "p_down": item.p_down,
                "trade_readiness_score": item.trade_readiness_score,
                "entry_window_score": item.entry_window_score,
                "freshness_score": item.freshness_score,
                "reward_risk_ratio": item.reward_risk_ratio,
                "data_quality": item.data_quality,
                "confluence_score": item.confluence_score,
                "risk_flags": item.risk_flags[:4],
                "next_trigger": item.next_trigger,
                "rule_summary": item.summary,
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
        }
    )


def _extract_output_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "".join(chunks)
