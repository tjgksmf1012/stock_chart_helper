"""AI-style recommendation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..schemas import AiRecommendationResponse
from ...services.ai_recommendation_service import build_ai_recommendations
from ...services.timeframe_service import DEFAULT_TIMEFRAME

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/recommendations", response_model=AiRecommendationResponse)
async def ai_recommendations(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
    limit: int = Query(default=8, ge=1, le=20),
) -> AiRecommendationResponse:
    return await build_ai_recommendations(timeframe=timeframe, limit=limit)
