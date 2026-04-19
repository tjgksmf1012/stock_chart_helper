"""Watchlist backend persistence — stores to Redis so the list survives browser clears."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.redis import cache_get, cache_set

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

_KEY = "watchlist:v1:default"
_TTL = 60 * 60 * 24 * 365  # 1 year


class WatchlistItemIn(BaseModel):
    code: str
    name: str
    market: str
    addedAt: str | None = None


@router.get("")
async def get_watchlist() -> list[dict]:
    """Return the stored watchlist."""
    return await cache_get(_KEY) or []


@router.post("")
async def sync_watchlist(items: list[WatchlistItemIn]) -> list[dict]:
    """Full-replace: overwrite the stored watchlist with the given list."""
    data = [item.model_dump() for item in items]
    await cache_set(_KEY, data, _TTL)
    return data


@router.post("/add")
async def add_to_watchlist(item: WatchlistItemIn) -> list[dict]:
    """Add a single symbol — idempotent (duplicates are ignored)."""
    items: list[dict] = await cache_get(_KEY) or []
    if not any(w["code"] == item.code for w in items):
        items.append(item.model_dump())
        await cache_set(_KEY, items, _TTL)
    return items


@router.delete("/{code}")
async def remove_from_watchlist(code: str) -> list[dict]:
    """Remove a symbol by code."""
    items: list[dict] = await cache_get(_KEY) or []
    items = [w for w in items if w["code"] != code]
    await cache_set(_KEY, items, _TTL)
    return items
