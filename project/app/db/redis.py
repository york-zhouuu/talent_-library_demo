import json
from app.core import get_settings

settings = get_settings()

# In-memory fallback when Redis is not available
_memory_store: dict[str, str] = {}
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as redis
            _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        except:
            _redis_client = None
    return _redis_client


class MemoryFallback:
    """In-memory fallback when Redis is unavailable"""
    async def setex(self, key: str, ttl: int, value: str):
        _memory_store[key] = value

    async def set(self, key: str, value: str):
        _memory_store[key] = value

    async def get(self, key: str) -> str | None:
        return _memory_store.get(key)

    async def delete(self, key: str):
        _memory_store.pop(key, None)

    async def close(self):
        pass


async def get_redis():
    client = _get_redis()
    if client:
        try:
            await client.ping()
            return client
        except:
            pass
    return MemoryFallback()


redis_client = MemoryFallback()  # Default to memory fallback
