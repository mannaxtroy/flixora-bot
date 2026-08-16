#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - single file, polling, health port for Render
"""

import os
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

@dataclass
class Result:
    title: str
    size: str
    seeds: int
    link: str
    source: str

async def search_tpb(query):
    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            resp = await client.get(f"https://tpb.party/search/{query.replace(' ', '%20')}/1/99/0")
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table#searchResult tr"):
                name = row.select_one("td:nth-child(2) a.detLink")
                if not name:
                    continue
                title = " ".join(name.get_text().split())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = "https://tpb.party" + link
                size_td = row.select_one("td:nth-child(5)")
                size = " ".join(size_td.get_text().split()) if size_td else "N/A"
                seed_td = row.select_one("td:nth-child(3)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(seed_td.get_text().strip().replace(",", ""))
                    except:
                        pass
                results.append(Result(title=title, size=size, seeds=seeds, link=link, source="TPB"))
    except Exception as e:
        logger.warning(f"TPB error: {e}")
    return results

async def search_nyaa(query):
    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            resp = await client.get(f"https://nyaa.si/?f=0&c=0_0&q={query.replace(' ', '+')}")
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table.torrent-list tbody tr"):
                name = row.select_one("td:nth-child(2) a")
                if not name:
                    continue
                title = " ".join(name.get_text().split())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = "https://nyaa.si" + link
                size_td = row.select_one("td:nth-child(4)")
                size = " ".join(size_td.get_text().split()) if size_td else "N/A"
                seed_td = row.select_one("td:nth-child(6)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(seed_td.get_text().strip().replace(",", ""))
                    except:
                        pass
                results.append(Result(title=title, size=size, seeds=seeds, link=link, source="Nyaa"))
    except Exception as e:
        logger.warning(f"Nyaa error: {e}")
    return results

async def search_yts(query):
    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            resp = await client.get("https://yts.mx/api/v2/list_movies.json", params={"query_term": query, "limit": 25})
            data = resp.json()
            for movie in data.get("data", {}).get("movies", []):
                for t in movie.get("torrents", []):
                    results.append(Result(
                        title=f"{movie['title']} ({t.get('quality', '')})",
                        size=t.get("size", "N/A"),
                        seeds=int(t.get("seeds", 0)),
                        link=t.get("url", ""),
                        source="YTS"
                    ))
    except Exception as e:
        logger.warning(f"YTS error: {e}")
    return results

async def search_lime(query):
    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            resp = await client.get(f"https://www.limetorrents.fun/search/all/{query.replace(' ', '-')}/")
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table.table2 tbody tr"):
                name = row.select_one("td:nth-child(1) a")
                if not name:
                    continue
                title = " ".join(name.get_text().split())
                link = name.get("href", "")
                if link.startswith("/"):
                    link = "https://www.limetorrents.fun" + link
                size_td = row.select_one("td:nth-child(2)")
                size = " ".join(size_td.get_text().split()) if size_td else "N/A"
                seed_td = row.select_one("td:nth-child(3)")
                seeds = 0
                if seed_td:
                    try:
                        seeds = int(seed_td.get_text().strip().replace(",", ""))
                    except:
                        pass
                results.append(Result(title=title, size=size, seeds=seeds, link=link, source="Lime"))
    except Exception as e:
        logger.warning(f"Lime error: {e}")
    return results

async def search_ddg(query):
    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            q = f"{query} mkv OR mp4 OR torrent download"
            resp = await client.get(f"https://html.duckduckgo.com/html/?q={q.replace(' ', '+')}")
            soup = BeautifulSoup(resp.text, "html.parser")
            seen = set()
            for item in soup.select("div.result"):
                a_tag = item.select_one("a.result__a")
                if not a_tag:
                    continue
                title = " ".join(a_tag.get_text().split())
                link = a_tag.get("href", "")
                if link and link not in seen:
                    seen.add(link)
                    results.append(Result(title=title, size="N/A", seeds=0, link=link, source="DDG"))
    except Exception as e:
        logger.warning(f"DDG error: {e}")
    return results

async def global_search(query):
    tasks = [
        search_tpb(query),
        search_nyaa(query),
        search_yts(query),
        search_lime(query),
        search_ddg(query),
    ]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    all_results = []
    for res in done:
        if isinstance(res, list):
            all_results.extend(res)
    all_results.sort(key=lambda r: (-r.seeds, r.title.lower()))
    return all_results[:25]

def format_results(results, query):
    lines = []
    lines.append(f"🎬 <b>Title : {query}</b>")
    lines.append("Your Files is Ready Now")
    lines.append("")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. <b>{r.title}</b>\n   📦 {r.size} | 🌐 {r.source} | 👥 {r.seeds}")
    text = "\n".join(lines)
    kb_buttons = []
    for i, r in enumerate(results[:10], 1):
        kb_buttons.append([InlineKeyboardButton(text=f"⬇️ Download {i}", url=r.link)])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    return text, kb

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Send me any <b>movie or series name</b> with proper spelling.\n"
        "I'll find direct download and torrent links.\n\n"
        "Example:\n"
        "<code>House of the Dragon</code>\n"
        "<code>Inception</code>",
        parse_mode="HTML"
    )

@router.message(Command("sources"))
async def sources(message: types.Message):
    await message.answer(
        "📋 <b>Active Sources:</b>\n\n"
        "🏴 ThePirateBay\n"
        "🍥 Nyaa\n"
        "🎬 YTS\n"
        "🌍 LimeTorrents\n"
        "🔍 DuckDuckGo",
        parse_mode="HTML"
    )

@router.message(F.text)
async def search(message: types.Message):
    query = message.text.strip()
    if not query:
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    results = await global_search(query)
    if not results:
        await message.answer(f"❌ No results found for <b>{query}</b>.\nTry proper spelling or add year.", parse_mode="HTML")
        return
    text, kb = format_results(results, query)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Health server running on port {PORT}")

async def main():
    # Start health server so Render sees an open port
    await start_web_server()
    # Register router and start polling
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())