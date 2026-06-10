from __future__ import annotations

import time

import pytest

import app.core.redis as cache


@pytest.fixture
def memory_only(monkeypatch):
    """Force the in-memory fallback path with a small cap and a clean cache."""
    monkeypatch.setattr(cache, "_mem_cache", {})

    async def _no_redis():
        return None

    monkeypatch.setattr(cache, "_try_get_redis", _no_redis)
    monkeypatch.setattr(cache, "_MEM_CACHE_MAX_ENTRIES", 100)


@pytest.mark.anyio
async def test_memory_cache_is_bounded(memory_only):
    for i in range(250):
        await cache.cache_set(f"k{i}", i, ttl=3600)

    assert len(cache._mem_cache) <= 100
    # most-recent keys survive, earliest were evicted
    assert await cache.cache_get("k249") == 249
    assert await cache.cache_get("k0") is None


@pytest.mark.anyio
async def test_expired_entries_are_evicted(memory_only):
    await cache.cache_set("live", 1, ttl=3600)
    cache._mem_cache["dead"] = ("stale", time.time() - 10)  # already expired

    assert await cache.cache_get("dead") is None
    assert "dead" not in cache._mem_cache
    assert await cache.cache_get("live") == 1


@pytest.mark.anyio
async def test_eviction_prefers_expired_over_live(memory_only):
    # Fill with already-expired junk, then add one live entry past the cap.
    for i in range(150):
        cache._mem_cache[f"old{i}"] = ("x", time.time() - 1)
    await cache.cache_set("fresh", 42, ttl=3600)

    assert len(cache._mem_cache) <= 100
    assert await cache.cache_get("fresh") == 42
