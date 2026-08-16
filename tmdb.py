import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TMDBLookup:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base = "https://image.tmdb.org/t/p/w500"
        self.client = httpx.AsyncClient(timeout=10)
    
    async def search_movie(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await self.client.get(
                f"{self.base_url}/search/movie",
                params={"api_key": self.api_key, "query": query, "limit": 1}
            )
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results[0]
            return None
        except Exception as e:
            logger.warning(f"TMDB movie error: {e}")
            return None
    
    async def search_series(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            resp = await self.client.get(
                f"{self.base_url}/search/tv",
                params={"api_key": self.api_key, "query": query, "limit": 1}
            )
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results[0]
            return None
        except Exception as e:
            logger.warning(f"TMDB series error: {e}")
            return None
    
    async def get_metadata(self, query: str, media_type: str = "movie") -> Optional[Dict[str, Any]]:
        """Returns formatted metadata or None."""
        if media_type == "movie":
            data = await self.search_movie(query)
        else:
            data = await self.search_series(query)
        if not data:
            return None
        title = data.get("title") or data.get("name", "Unknown")
        year = (data.get("release_date") or data.get("first_air_date") or "")[:4]
        poster_path = data.get("poster_path", "")
        poster_url = f"{self.image_base}{poster_path}" if poster_path else ""
        rating = data.get("vote_average", 0)
        overview = data.get("overview", "")
        media_id = data.get("id")
        return {
            "title": title,
            "year": year,
            "poster_url": poster_url,
            "rating": rating,
            "overview": overview,
            "media_id": media_id,
        }