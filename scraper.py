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
        self.client = httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=15)
    
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

# ─── YTS (API) ───
class YtsScraper(BaseScraper):
    name = "yts"
    base_url = "https://yts.mx"
    async def search(self, query):
        try:
            resp = await self.client.get(f"{self.base_url}/api/v2/list_movies.json", params={"query_term": query, "limit": 20})
            data = resp.json()
            results = []
            for movie in data.get("data", {}).get("movies", []):
                for t in movie.get("torrents", []):
                    results.append(ScraperResult(
                        id=f"{movie['id']}-{t.get('quality', '')}",
                        title=movie["title"], year=str(movie.get("year", "")),
                        size=t.get("size", ""), quality=t.get("quality", ""),
                        seeders=int(t.get("seeds", 0)), leechers=int(t.get("peers", 0)),
                        links=[t["url"]], magnet=t.get("magnet", ""),
                        source="YTS.mx", type="movie", category=t.get("quality", "")
                    ))
            logger.info(f"YTS: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"YTS error: {e}")
            return []

# ─── 1337X (via mirror) ───
class LeetxScraper(BaseScraper):
    name = "1337x"
    base_url = "https://1337x.gd"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/{query.replace(' ', '%20')}/1/"
            resp = await self.client.get(url)
            if resp.status_code == 403:
                logger.warning("1337x: 403")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            rows = soup.select("table.table-list tbody tr")
            for row in rows:
                name = row.select_one("td.name a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td.size").get_text()) if row.select_one("td.size") else ""
                seeds_td = row.select_one("td.seeds")
                seeds = int(self._clean(seeds_td.get_text()).replace(",", "")) if seeds_td else 0
                leech_td = row.select_one("td.leeches")
                leech = int(self._clean(leech_td.get_text()).replace(",", "")) if leech_td else 0
                q = self._quality(title)
                sb = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link],
                    source="1337x", type="movie", category=q, size_bytes=sb
                ))
            logger.info(f"1337x: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"1337x error: {e}")
            return []

# ─── TPB (via mirror) ───
class PirateBayScraper(BaseScraper):
    name = "tpb"
    base_url = "https://tpb.party"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/{query.replace(' ', '%20')}/1/99/0"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            rows = soup.select("table#searchResult tr")
            for row in rows:
                name = row.select_one("td:nth-child(2) a.detLink")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size_td = row.select_one("td:nth-child(5)")
                size = self._clean(size_td.get_text()) if size_td else ""
                seed_td = row.select_one("td:nth-child(3)")
                seeds = int(self._clean(seed_td.get_text()).replace(",", "")) if seed_td else 0
                leech_td = row.select_one("td:nth-child(4)")
                leech = int(self._clean(leech_td.get_text()).replace(",", "")) if leech_td else 0
                q = self._quality(title)
                sb = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link],
                    source="TPB", type="movie", category=q, size_bytes=sb
                ))
            logger.info(f"TPB: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"TPB error: {e}")
            return []

# ─── NYAA ───
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
            for row in rows:
                name = row.select_one("td:nth-child(2) a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size_td = row.select_one("td:nth-child(4)")
                size = self._clean(size_td.get_text()) if size_td else ""
                seed_td = row.select_one("td:nth-child(6)")
                seeds = int(self._clean(seed_td.get_text()).replace(",", "")) if seed_td else 0
                leech_td = row.select_one("td:nth-child(7)")
                leech = int(self._clean(leech_td.get_text()).replace(",", "")) if leech_td else 0
                q = self._quality(title)
                sb = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link],
                    source="Nyaa", type="series", category=q, size_bytes=sb
                ))
            logger.info(f"Nyaa: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"Nyaa error: {e}")
            return []

# ─── TORRENT GALAXY ───
class TorrentGalaxyScraper(BaseScraper):
    name = "tgx"
    base_url = "https://torrentgalaxy.to"
    async def search(self, query):
        try:
            url = f"{self.base_url}/torrents.php?search={query.replace(' ', '+')}&sort=seeders&order=desc"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            rows = soup.select("div.tgxtable div.tgxtablerow")
            for row in rows:
                name = row.select_one("a.tx-link")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size_td = row.select_one("span.badge-secondary")
                size = self._clean(size_td.get_text()) if size_td else ""
                seed_td = row.select_one("span.badge-success")
                seeds = int(self._clean(seed_td.get_text()).replace(",", "")) if seed_td else 0
                leech_td = row.select_one("span.badge-danger")
                leech = int(self._clean(leech_td.get_text()).replace(",", "")) if leech_td else 0
                q = self._quality(title)
                sb = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link],
                    source="TorrentGalaxy", type="movie", category=q, size_bytes=sb
                ))
            logger.info(f"TGX: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"TGX error: {e}")
            return []

# ─── LIME TORRENTS ───
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
            for row in rows:
                name = row.select_one("td:nth-child(1) a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size_td = row.select_one("td:nth-child(2)")
                size = self._clean(size_td.get_text()) if size_td else ""
                seed_td = row.select_one("td:nth-child(3)")
                seeds = int(self._clean(seed_td.get_text()).replace(",", "")) if seed_td else 0
                q = self._quality(title)
                sb = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-2] if link.endswith("/") else link.split("/")[-1],
                    title=title, size=size, quality=q,
                    seeders=seeds, links=[link],
                    source="LimeTorrents", type="movie", category=q, size_bytes=sb
                ))
            logger.info(f"Lime: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"Lime error: {e}")
            return []

# ─── DUCKDUCKGO FALLBACK (DDL) ───
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
            for item in items:
                title_tag = item.select_one("a.result__a")
                if not title_tag: continue
                title = self._clean(title_tag.get_text())
                link = title_tag.get("href", "")
                if link and link not in seen:
                    seen.add(link)
                    results.append(ScraperResult(
                        id=link[:80], title=title, links=[link],
                        source="DDG", type="movie"
                    ))
            logger.info(f"DDG: {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"DDG error: {e}")
            return []

def get_all_scrapers():
    return [
        YtsScraper(), LeetxScraper(), PirateBayScraper(),
        NyaaScraper(), TorrentGalaxyScraper(), LimeTorrentsScraper(),
        DuckDuckGoScraper(),
    ]

async def global_search(query, limit=20, quality_filter="", sort_by="seeds"):
    scrapers = get_all_scrapers()
    tasks = [asyncio.create_task(s.search(query)) for s in scrapers]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    all_results = []
    for scraper, res in zip(scrapers, done):
        if isinstance(res, Exception):
            logger.warning(f"{scraper.name} exception: {res}")
            continue
        all_results.extend(res)
    logger.info(f"Total before filter: {len(all_results)}")
    if quality_filter:
        all_results = [r for r in all_results if quality_filter.lower() in r.quality.lower() or quality_filter.lower() in r.title.lower()]
    if sort_by == "size":
        all_results.sort(key=lambda r: (-r.size_bytes, -r.seeders, r.title.lower()))
    elif sort_by == "quality":
        order = {"4K": 4, "1080p": 3, "720p": 2, "480p": 1, "": 0}
        all_results.sort(key=lambda r: (-order.get(r.quality, 0), -r.seeders, r.title.lower()))
    elif sort_by == "source":
        all_results.sort(key=lambda r: (r.source, -r.seeders, r.title.lower()))
    else:
        all_results.sort(key=lambda r: (-r.seeders, -r.size_bytes, r.title.lower()))
    return all_results[:limit]

async def test_sources():
    scrapers = get_all_scrapers()
    status = {}
    for s in scrapers:
        try:
            results = await s.search("test")
            status[s.name] = f"OK ({len(results)} results)"
        except Exception as e:
            status[s.name] = f"FAIL: {e}"
    return status