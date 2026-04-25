import json
import redis.asyncio as aioredis
from app.config import settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get(key: str) -> dict | list | str | int | None:
    r = await get_redis()
    val = await r.get(key)
    return json.loads(val) if val is not None else None


async def cache_set(key: str, value, ttl: int) -> None:
    r = await get_redis()
    await r.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def cache_sadd(key: str, *members: str, ttl: int | None = None) -> None:
    r = await get_redis()
    await r.sadd(key, *members)
    if ttl is not None:
        await r.expire(key, ttl)


async def cache_smembers(key: str) -> set[str]:
    r = await get_redis()
    return await r.smembers(key)
