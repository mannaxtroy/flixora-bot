import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
    REDIS_URL: str = "redis://default:gQAAAAAAAg1oAAIgcDJiN2I5OTQ0MjcxMmU0NmVlYTU4NmYxYjI3ZThhYmZiNw@powerful-alien-134504.upstash.io:6379"
    TMDB_API_KEY: str = "a0a6d5683fba540c701631e68bbcc117"
    MAX_RESULTS: int = 20
    CACHE_TTL: int = 300
    PORT: int = int(os.getenv("PORT", "8000"))
    HEALTH_CHECK_INTERVAL: int = 60
    LOG_LEVEL: str = "INFO"
    RENDER_APP_URL: str = os.getenv("RENDER_APP_URL", "https://flixora-bot-xtzp.onrender.com")

cfg = Config()