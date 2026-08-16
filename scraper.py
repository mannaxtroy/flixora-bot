import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional, List

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
        self.client = httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=25)
    
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

class ArchiveOrgScraper(BaseScraper):
    name = "archive"
    base_url = "https://archive.org"
    async def search(self, query):
        try:
            resp = await self.client.get(f"{self.base_url}/advancedsearch.php", params={
                "q": f'title:("{query}") AND mediatype:(movies)',
                "fl[]": ["identifier", "title", "year"],
                "rows": 10, "output": "json"
            })
            docs = resp.json().get("response", {}).get("docs", [])
            results = []
            for doc in docs:
                ident = doc.get("identifier", "")
                if not ident: continue
                meta = await self.client.get(f"{self.base_url}/metadata/{ident}")
                files = meta.json().get("files", [])
                links = [f"{self.base_url}/download/{ident}/{f['name']}" for f in files if f.get("format") in ("MPEG4", "Matroska", "Ogg Video", "MP3")]
                if links:
                    results.append(ScraperResult(
                        id=ident, title=doc.get("title", ident),
                        year=str(doc.get("year", "")), size="Multiple",
                        quality="Multiple", links=links, source="Archive.org", type="movie"
                    ))
            return results
        except: return []

class YtsScraper(BaseScraper):
    name = "yts"
    base_url = "https://yts.mx"
    async def search(self, query):
        try:
            resp = await self.client.get(f"{self.base_url}/api/v2/list_movies.json", params={"query_term": query, "limit": 25})
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
            return results
        except: return []

class LeetxScraper(BaseScraper):
    name = "1337x"
    base_url = "https://1337x.to"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/{query.replace(' ', '%20')}/1/"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for row in soup.select("table.table-list tbody tr"):
                name = row.select_one("td.name a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td.size").get_text()) if row.select_one("td.size") else ""
                seeds = int(self._clean(row.select_one("td.seeds").get_text()).replace(",", "")) if row.select_one("td.seeds") else 0
                leech = int(self._clean(row.select_one("td.leeches").get_text()).replace(",", "")) if row.select_one("td.leeches") else 0
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link], source="1337x",
                    type="movie", category=q, size_bytes=size_bytes
                ))
            return results
        except: return []

class PirateBayScraper(BaseScraper):
    name = "tpb"
    base_url = "https://thepiratebay.org"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search.php?q={query.replace(' ', '%20')}"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for row in soup.select("table#searchResult tbody tr"):
                name = row.select_one("td:nth-child(2) a.detLink")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td:nth-child(5)").get_text()) if row.select_one("td:nth-child(5)") else ""
                seeds = int(self._clean(row.select_one("td:nth-child(3)").get_text()).replace(",", "")) if row.select_one("td:nth-child(3)") else 0
                leech = int(self._clean(row.select_one("td:nth-child(4)").get_text()).replace(",", "")) if row.select_one("td:nth-child(4)") else 0
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link], source="ThePirateBay",
                    type="movie", category=q, size_bytes=size_bytes
                ))
            return results
        except: return []

class NyaaScraper(BaseScraper):
    name = "nyaa"
    base_url = "https://nyaa.si"
    async def search(self, query):
        try:
            url = f"{self.base_url}/?f=0&c=0_0&q={query.replace(' ', '+')}"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for row in soup.select("table.torrent-list tbody tr"):
                name = row.select_one("td:nth-child(2) a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td:nth-child(4)").get_text()) if row.select_one("td:nth-child(4)") else ""
                seeds = int(self._clean(row.select_one("td:nth-child(6)").get_text()).replace(",", "")) if row.select_one("td:nth-child(6)") else 0
                leech = int(self._clean(row.select_one("td:nth-child(7)").get_text()).replace(",", "")) if row.select_one("td:nth-child(7)") else 0
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size, quality=q,
                    seeders=seeds, leechers=leech, links=[link], source="Nyaa.si",
                    type="series", category=q, size_bytes=size_bytes
                ))
            return results
        except: return []

class LimeTorrentsScraper(BaseScraper):
    name = "lime"
    base_url = "https://www.limetorrents.lol"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/all/{query.replace(' ', '-')}/"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for row in soup.select("div.tt-ah table.table2 tbody tr"):
                name = row.select_one("td:nth-child(1) a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td:nth-child(2)").get_text()) if row.select_one("td:nth-child(2)") else ""
                seeds = int(self._clean(row.select_one("td:nth-child(3)").get_text()).replace(",", "")) if row.select_one("td:nth-child(3)") else 0
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-2] if link.endswith("/") else link.split("/")[-1],
                    title=title, size=size, quality=q, seeders=seeds,
                    links=[link], source="LimeTorrents", type="movie",
                    category=q, size_bytes=size_bytes
                ))
            return results
        except: return []

class TorlockScraper(BaseScraper):
    name = "torlock"
    base_url = "https://www.torlock.com"
    async def search(self, query):
        try:
            url = f"{self.base_url}/all/torrents/{query.replace(' ', '-')}.html"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for row in soup.select("table#torrents-table tbody tr"):
                name = row.select_one("td:nth-child(1) a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td:nth-child(3)").get_text()) if row.select_one("td:nth-child(3)") else ""
                seeds = int(self._clean(row.select_one("td:nth-child(5)").get_text()).replace(",", "")) if row.select_one("td:nth-child(5)") else 0
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1].replace(".html", ""), title=title,
                    size=size, quality=q, seeders=seeds, links=[link],
                    source="Torlock", type="movie", category=q, size_bytes=size_bytes
                ))
            return results
        except: return []

class EztvScraper(BaseScraper):
    name = "eztv"
    base_url = "https://eztvx.to"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/{query.replace(' ', '-')}"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for row in soup.select("table.forum_header_border tbody tr.forum_header_border"):
                name = row.select_one("td:nth-child(2) a")
                if not name: continue
                title = self._clean(name.get_text())
                link = name.get("href", "")
                if link.startswith("/"): link = f"{self.base_url}{link}"
                size = self._clean(row.select_one("td:nth-child(4)").get_text()) if row.select_one("td:nth-child(4)") else ""
                seeds = int(self._clean(row.select_one("td:nth-child(6)").get_text()).replace(",", "")) if row.select_one("td:nth-child(6)") else 0
                q = self._quality(title)
                size_bytes = self._parse_size(size)
                results.append(ScraperResult(
                    id=link.split("/")[-1], title=title, size=size,
                    quality=q, seeders=seeds, links=[link], source="EZTV",
                    type="series", category=q, size_bytes=size_bytes
                ))
            return results
        except: return []

class DuckDuckGoScraper(BaseScraper):
    name = "ddg"
    base_url = "https://html.duckduckgo.com"
    async def search(self, query):
        try:
            url = f"{self.base_url}/html/?q={query.replace(' ', '+')}+direct+download+mkv+OR+mp4"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for item in soup.select("div.result")[:10]:
                title_tag = item.select_one("a.result__a")
                if not title_tag: continue
                title = self._clean(title_tag.get_text())
                link = title_tag.get("href", "")
                snippet = self._clean(item.select_one("a.result__snippet").get_text()) if item.select_one("a.result__snippet") else ""
                if "mkv" in snippet.lower() or "mp4" in snippet.lower():
                    results.append(ScraperResult(
                        id=link[:50], title=title, links=[link],
                        source="DuckDuckGo", type="movie"
                    ))
            return results
        except: return []

class DirectDownloadScraper(BaseScraper):
    name = "ddl"
    base_url = "https://html.duckduckgo.com"
    async def search(self, query):
        try:
            ddl_sites = [
                "site:olamovies.cloud", "site:bolly4u.org",
                "site:mkvcinemas.live", "site:filmyzilla.xyz",
                "site:vevamovie.xyz", "site:moviezaddiction.xyz",
                "site:hindilinks4u.to", "site:downloadhub.boats",
            ]
            results = []
            for site in ddl_sites:
                search_term = f"{query} {site}"
                url = f"{self.base_url}/html/?q={search_term.replace(' ', '+')}"
                resp = await self.client.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select("div.result")[:5]:
                    title_tag = item.select_one("a.result__a")
                    if not title_tag: continue
                    title = self._clean(title_tag.get_text())
                    link = title_tag.get("href", "")
                    snippet = self._clean(item.select_one("a.result__snippet").get_text()) if item.select_one("a.result__snippet") else ""
                    if "download" in snippet.lower() and ("mkv" in snippet.lower() or "mp4" in snippet.lower()):
                        results.append(ScraperResult(
                            id=link[:50], title=title, links=[link],
                            source="DirectDownload", type="movie"
                        ))
            return results
        except: return []

class SolarMovieScraper(BaseScraper):
    name = "solarmovie"
    base_url = "https://wwv.solarmovie.one"
    async def search(self, query):
        try:
            url = f"{self.base_url}/search/{query.replace(' ', '-')}/"
            resp = await self.client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for item in soup.select("div.ml-item")[:10]:
                link_tag = item.select_one("a.ml-mask")
                if not link_tag: continue
                link = link_tag.get("href", "")
                title = self._clean(link_tag.get("title", ""))
                quality_tag = item.select_one("span.mli-quality")
                quality = self._clean(quality_tag.get_text()) if quality_tag else ""
                if link and title:
                    results.append(ScraperResult(
                        id=link.split("/")[-2] if link.endswith("/") else link.split("/")[-1],
                        title=title, quality=quality, links=[link],
                        source="SolarMovie", type="movie", category=quality
                    ))
            return results
        except: return []

def get_all_scrapers():
    return [
        ArchiveOrgScraper(), YtsScraper(), LeetxScraper(),
        PirateBayScraper(), NyaaScraper(), LimeTorrentsScraper(),
        TorlockScraper(), EztvScraper(), DuckDuckGoScraper(),
        DirectDownloadScraper(), SolarMovieScraper(),
    ]

async def global_search(query: str, limit: int = 30, quality_filter: str = "", sort_by: str = "seeds"):
    scrapers = get_all_scrapers()
    tasks = [asyncio.create_task(s.search(query)) for s in scrapers]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_results = []
    for scraper, res in zip(scrapers, done):
        if isinstance(res, Exception):
            continue
        all_results.extend(res)
    
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
    
    return all_results[:limit]