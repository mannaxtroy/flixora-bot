import json
import time
import asyncio
from typing import Any, Optional
from config import cfg

class InMemoryCache:
    def __init__(self):
        self.store = {}
        self.expiry = {}
    
    async def get(self, key: str) -> Optional[Any]:
        if key in self.store and time.time() < self.expiry.get(key, 0):
            return self.store[key]
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        self.store[key] = value
        self.expiry[key] = time.time() + ttl
    
    async def delete(self, key: str):
        if key in self.store:
            del self.store[key]
            del self.expiry[key]

class RedisCache:
    def __init__(self, url: str):
        import redis.asyncio as redis
        self.redis = redis.from_url(url, decode_responses=True)
    
    async def get(self, key: str) -> Optional[Any]:
        try:
            val = await self.redis.get(key)
            if val:
                return json.loads(val)
        except Exception:
            pass
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        try:
            await self.redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception:
            pass
    
    async def delete(self, key: str):
        try:
            await self.redis.delete(key)
        except Exception:
            pass

def get_cache():
    if cfg.REDIS_URL:
        return RedisCache(cfg.REDIS_URL)
    return InMemoryCache()