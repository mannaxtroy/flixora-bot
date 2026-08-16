import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
    REDIS_URL: str = "redis://default:gQAAAAAAAg1oAAIgcDJiN2I5OTQ0MjcxMmU0NmVlYTU4NmYxYjI3ZThhYmZiNw@powerful-alien-134504.upstash.io:6379"
    MAX_RESULTS: int = 30
    CACHE_TTL: int = 300
    PORT: int = int(os.getenv("PORT", "8000"))
    HEALTH_CHECK_INTERVAL: int = 60
    LOG_LEVEL: str = "INFO"

cfg = Config()