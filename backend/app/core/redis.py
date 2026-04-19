import json
import time
from typing import Any
from .config import get_settings

settings = get_settings()

# In-memory fallback cache (used when Redis is unavailable)
_mem_cache: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)

_redis = None
_redis_available: bool | None = None  # None = not yet tried


async def _try_get_redis():
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)
        await r.ping()
        _redis = r
        _redis_available = True
        return _redis
    except Exception:
        _redis_available = False
        return None


async def cache_get(key: str) -> Any | None:
    r = await _try_get_redis()
    if r:
        try:
            val = await r.get(key)
            return json.loads(val) if val else None
        except Exception:
            pass
    # in-memory fallback
    entry = _mem_cache.get(key)
    if entry and entry[1] > time.time():
        return entry[0]
    _mem_cache.pop(key, None)
    return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    r = await _try_get_redis()
    if r:
        try:
            await r.setex(key, ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass
    # in-memory fallback
    _mem_cache[key] = (value, time.time() + ttl)


async def cache_delete(key: str) -> None:
    r = await _try_get_redis()
    if r:
        try:
            await r.delete(key)
        except Exception:
            pass
    _mem_cache.pop(key, None)


async def cache_backend_status() -> dict[str, Any]:
    r = await _try_get_redis()
    now = time.time()
    live_mem_entries = sum(1 for _, expires_at in _mem_cache.values() if expires_at > now)
    if r:
        return {
            "backend": "redis",
            "redis_available": True,
            "memory_fallback_entries": live_mem_entries,
        }
    return {
        "backend": "memory",
        "redis_available": False,
        "memory_fallback_entries": live_mem_entries,
    }
