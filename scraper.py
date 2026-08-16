import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional, List

logger = logging.getLogger(__name__)

@dataclass
class ScraperResult:
    id: str
    title: str
    year: str = ""
    size: str = ""
    quality: str = ""
    seeders: int = 0
    leechers: int = 0
    magnet: str = ""
    links: list = field(default_factory=list)
    source: str = ""
    type: str = "movie"
    category: str = ""
    size_bytes: int = 0

class BaseScraper(ABC):
    name = "base"
    base_url = ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    def __init__(self):
        self.client = httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=12)
    
    @abstractmethod
    async def search(self, query: str) -> list:
        ...
    
    async def close(self):
        await self.client.aclose()
    
    def _clean(self, t):
        return re.sub(r'\s+', ' ', t or '').strip()
    
    def _quality(self, title):
        t = title.lower()
        if "4k" in t or "2160p" in t: return "4K"
        if "1080p" in t: return "1080p"
        if "720p" in t: return "720p"
        if "480p" in t: return "480p"
        return ""
    
    def _parse_size(self, s):
        if not s: return 0
        m = re.search(r'([\d.]+)\s*(kb|mb|gb|tb|b)', s.lower())
        if not m: return 0
        num = float(m.group(1))
        units = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
        return int(num * units.get(m.group(2), 1))

# ─── YTS.MX (API - MOST RELIABLE) ───
class YtsScraper(BaseScraper):
    name = "yts"
    base_url = "https://yts.mx"
    async def search(self, query):
        try:
            resp = await self.client.get(
                f"{self.base_url}/api/v2/list_movies.json",
                params={"query_term": query, "limit": 20}
            )
            data = resp.json()
            results = []
            for movie in data.get("data", {}).get("movies", []):
                for t in movie.get("torrents", []):
                    results.append(ScraperResult(
                        id=f"{movie['id']}-{t.get('quality', '')}",
                        title=movie["title"],
                        year=str(movie.get("year", "")),
                        size=t.get("size", ""),
                        quality=t.get("quality", ""),
                        seeders=int(t.get("seeds", 0)),
                        leechers=int(t.get("peers", 0)),
                        links=[t["url"]],
                        magnet=t.get("magnet", ""),
                        source="YTS.mx",
                        type="movie",
                        category=t.get("quality", "")
                    ))
            if results:
                logger.info(f"YTS: found {len(results)} results")
            else:
                logger.info(f"YTS: 0 results for '{query}'")
            return results
        except Exception as e:
            logger.warning(f"YTS error: {e}")
            return []

# ─── THE PIRATE BAY ───
class PirateBayScraper(BaseScraper):
    name = "tpb"
    base_url = "https://thepiratebay.org"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search.php?q={query.replace(' ', '%20')}"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            
            # TPB rows: <tr> inside table#searchResult
            rows = soup.select("table#searchResult tr")
            logger.info(f"TPB: {len(rows)} rows found in HTML")
            
            for row in rows:
                name = row.select_one("td:nth-child(2) a.detLink")
                if not name:
                    continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = f"{self.base_url}{link}"
                
                size_td = row.select_one("td:nth-child(5)")
                size = self._clean(size_td.get_text()) if size_td else ""
                
                seed_td = row.select_one("td:nth-child(3)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(self._clean(seed_td.get_text()).replace(",", ""))
                    except:
                        seeds = 0
                
                leech_td = row.select_one("td:nth-child(4)")
                leech = 0
                if leech_td:
                    try:
                        leech = int(self._clean(leech_td.get_text()).replace(",", ""))
                    except:
                        leech = 0
                
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                
                results.append(ScraperResult(
                    id=link.split("/")[-1] if link else str(len(results)),
                    title=title,
                    size=size,
                    quality=q,
                    seeders=seeds,
                    leechers=leech,
                    links=[link],
                    source="ThePirateBay",
                    type="movie",
                    category=q,
                    size_bytes=size_bytes
                ))
            
            logger.info(f"TPB: parsed {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.warning(f"TPB error: {e}")
            return []

# ─── NYAA.SI ───
class NyaaScraper(BaseScraper):
    name = "nyaa"
    base_url = "https://nyaa.si"
    async def search(self, query):
        try:
            url = f"{self.base_url}/?f=0&c=0_0&q={query.replace(' ', '+')}"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            
            rows = soup.select("table.torrent-list tbody tr")
            logger.info(f"Nyaa: {len(rows)} rows found in HTML")
            
            for row in rows:
                name = row.select_one("td:nth-child(2) a")
                if not name:
                    continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = f"{self.base_url}{link}"
                
                size_td = row.select_one("td:nth-child(4)")
                size = self._clean(size_td.get_text()) if size_td else ""
                
                seed_td = row.select_one("td:nth-child(6)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(self._clean(seed_td.get_text()).replace(",", ""))
                    except:
                        seeds = 0
                
                leech_td = row.select_one("td:nth-child(7)")
                leech = 0
                if leech_td:
                    try:
                        leech = int(self._clean(leech_td.get_text()).replace(",", ""))
                    except:
                        leech = 0
                
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                
                results.append(ScraperResult(
                    id=link.split("/")[-1] if link else str(len(results)),
                    title=title,
                    size=size,
                    quality=q,
                    seeders=seeds,
                    leechers=leech,
                    links=[link],
                    source="Nyaa.si",
                    type="series",
                    category=q,
                    size_bytes=size_bytes
                ))
            
            logger.info(f"Nyaa: parsed {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.warning(f"Nyaa error: {e}")
            return []

# ─── LIMETORRENTS ───
class LimeTorrentsScraper(BaseScraper):
    name = "lime"
    base_url = "https://www.limetorrents.fun"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/all/{query.replace(' ', '-')}/"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            
            rows = soup.select("table.table2 tbody tr")
            logger.info(f"Lime: {len(rows)} rows found in HTML")
            
            for row in rows:
                name = row.select_one("td:nth-child(1) a")
                if not name:
                    continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = f"{self.base_url}{link}"
                
                size_td = row.select_one("td:nth-child(2)")
                size = self._clean(size_td.get_text()) if size_td else ""
                
                seed_td = row.select_one("td:nth-child(3)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(self._clean(seed_td.get_text()).replace(",", ""))
                    except:
                        seeds = 0
                
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                
                results.append(ScraperResult(
                    id=link.split("/")[-2] if link.endswith("/") else link.split("/")[-1],
                    title=title,
                    size=size,
                    quality=q,
                    seeders=seeds,
                    links=[link],
                    source="LimeTorrents",
                    type="movie",
                    category=q,
                    size_bytes=size_bytes
                ))
            
            logger.info(f"Lime: parsed {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.warning(f"Lime error: {e}")
            return []

# ─── TORLOCK ───
class TorlockScraper(BaseScraper):
    name = "torlock"
    base_url = "https://www.torlock.com"
    async def search(self, query):
        try:
            url = f"{self.base_url}/all/torrents/{query.replace(' ', '-')}.html"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            
            rows = soup.select("table#torrents-table tbody tr")
            logger.info(f"Torlock: {len(rows)} rows found in HTML")
            
            for row in rows:
                name = row.select_one("td:nth-child(1) a")
                if not name:
                    continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = f"{self.base_url}{link}"
                
                size_td = row.select_one("td:nth-child(3)")
                size = self._clean(size_td.get_text()) if size_td else ""
                
                seed_td = row.select_one("td:nth-child(5)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(self._clean(seed_td.get_text()).replace(",", ""))
                    except:
                        seeds = 0
                
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                
                results.append(ScraperResult(
                    id=link.split("/")[-1].replace(".html", ""),
                    title=title,
                    size=size,
                    quality=q,
                    seeders=seeds,
                    links=[link],
                    source="Torlock",
                    type="movie",
                    category=q,
                    size_bytes=size_bytes
                ))
            
            logger.info(f"Torlock: parsed {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.warning(f"Torlock error: {e}")
            return []

# ─── DUCKDUCKGO FALLBACK ───
class DuckDuckGoScraper(BaseScraper):
    name = "ddl"
    base_url = "https://html.duckduckgo.com"
    async def search(self, query):
        try:
            search_term = f"{query} mkv OR mp4 OR torrent download"
            url = f"{self.base_url}/html/?q={search_term.replace(' ', '+')}"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            seen = set()
            
            items = soup.select("div.result")
            logger.info(f"DDG: {len(items)} results found in HTML")
            
            for item in items:
                title_tag = item.select_one("a.result__a")
                if not title_tag:
                    continue
                title = self._clean(title_tag.get_text())
                link = title_tag.get("href", "")
                snippet_tag = item.select_one("a.result__snippet")
                snippet = self._clean(snippet_tag.get_text()) if snippet_tag else ""
                
                if link and link not in seen:
                    # Accept any reasonable result since we're desperate
                    seen.add(link)
                    results.append(ScraperResult(
                        id=link[:80],
                        title=title,
                        links=[link],
                        source="DuckDuckGo",
                        type="movie"
                    ))
            
            logger.info(f"DDG: parsed {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.warning(f"DDG error: {e}")
            return []

# ─── SKIP ARCHIVE.ORG (TOO SLOW / USELESS FOR TV) ───

def get_all_scrapers():
    return [
        YtsScraper(),
        PirateBayScraper(),
        NyaaScraper(),
        LimeTorrentsScraper(),
        TorlockScraper(),
        DuckDuckGoScraper(),
    ]

async def global_search(query: str, limit: int = 30, quality_filter: str = "", sort_by: str = "seeds"):
    scrapers = get_all_scrapers()
    tasks = [asyncio.create_task(s.search(query)) for s in scrapers]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_results = []
    for scraper, res in zip(scrapers, done):
        if isinstance(res, Exception):
            logger.warning(f"{scraper.name} exception: {res}")
            continue
        all_results.extend(res)
    
    logger.info(f"Total results before filter: {len(all_results)}")
    
    if quality_filter:
        all_results = [r for r in all_results if quality_filter.lower() in r.quality.lower() or quality_filter.lower() in r.title.lower()]
    
    if sort_by == "size":
        all_results.sort(key=lambda r: (-r.size_bytes, -r.seeders, r.title.lower()))
    elif sort_by == "quality":
        quality_order = {"4K": 4, "1080p": 3, "720p": 2, "480p": 1, "": 0}
        all_results.sort(key=lambda r: (-quality_order.get(r.quality, 0), -r.seeders, r.title.lower()))
    elif sort_by == "source":
        all_results.sort(key=lambda r: (r.source, -r.seeders, r.title.lower()))
    else:
        all_results.sort(key=lambda r: (-r.seeders, -r.size_bytes, r.title.lower()))
    
    logger.info(f"Returning {min(len(all_results), limit)} results")
    return all_results[:limit]