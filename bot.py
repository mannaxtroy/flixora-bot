#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - MovieBox API Integration
Searches MovieBox and returns direct stream/download links.
"""

import os
import re
import asyncio
import logging
import httpx
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
PORT = int(os.getenv("PORT", "10000"))

# MovieBox API base URL — change if you deploy your own instance
MOVIEBOX_API = os.getenv("MOVIEBOX_API", "https://moviebox-api.vercel.app")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

def clean_text(t):
    return re.sub(r'\s+', ' ', t or '').strip()

async def moviebox_search(query: str) -> list:
    """Call Moviebox API search endpoint."""
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(f"{MOVIEBOX_API}/search", params={"q": query})
            if resp.status_code != 200:
                logger.warning(f"Moviebox search returned {resp.status_code}")
                return []
            data = resp.json()
            # The API may return {results: [...]} or a list directly
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("results", "data", "items", "movies"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
            return []
    except Exception as e:
        logger.warning(f"Moviebox search error: {e}")
        return []

async def moviebox_detail(slug: str) -> dict:
    """Call Moviebox API detail endpoint."""
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(f"{MOVIEBOX_API}/detail/{slug}")
            if resp.status_code != 200:
                logger.warning(f"Moviebox detail returned {resp.status_code}")
                return {}
            return resp.json()
    except Exception as e:
        logger.warning(f"Moviebox detail error: {e}")
        return {}

async def moviebox_stream(media_id: str, slug: str) -> str:
    """Extract direct stream URL."""
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(f"{MOVIEBOX_API}/api/stream/{media_id}", params={"detail_path": slug})
            if resp.status_code != 200:
                logger.warning(f"Moviebox stream returned {resp.status_code}")
                return ""
            data = resp.json()
            # Extract first available stream URL
            if isinstance(data, dict):
                for key in ("url", "stream_url", "play_url", "video_url", "link"):
                    if data.get(key):
                        return data[key]
                # Maybe nested
                for key in ("sources", "streams", "files"):
                    if key in data and isinstance(data[key], list) and data[key]:
                        return data[key][0].get("url", data[key][0].get("file", "")) if isinstance(data[key][0], dict) else str(data[key][0])
            return ""
    except Exception as e:
        logger.warning(f"Moviebox stream error: {e}")
        return ""

def format_result(item: dict, stream_url: str = "") -> tuple:
    """Build text and buttons for one result."""
    title = clean_text(item.get("title") or item.get("name") or "Unknown")
    slug = clean_text(item.get("slug") or item.get("id") or "")
    year = clean_text(item.get("year") or item.get("release_date", "")[:4])
    poster = item.get("poster") or item.get("poster_url") or item.get("image") or ""
    rating = item.get("rating") or item.get("imdb_rating") or ""

    text = f"🎬 <b>{title}</b>"
    if year:
        text += f" ({year})"
    if rating:
        text += f"\n⭐ {rating}/10"
    text += "\n"

    kb_buttons = []
    if stream_url:
        text += f"\n✅ <b>Stream/Download:</b>\n<a href='{stream_url}'>Direct Link</a>"
        kb_buttons.append([InlineKeyboardButton(text="▶️ Stream/Download", url=stream_url)])
    if poster:
        kb_buttons.append([InlineKeyboardButton(text="🖼 Poster", url=poster)])
    if slug:
        kb_buttons.append([InlineKeyboardButton(text="📄 Details", url=f"{MOVIEBOX_API}/detail/{slug}")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    return text, kb

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Powered by MovieBox API.\n"
        "Send me any movie or series name and I'll find direct stream/download links.\n\n"
        "Example:\n"
        "<code>Inception</code>\n"
        "<code>House of the Dragon</code>",
        parse_mode="HTML"
    )

@router.message(Command("api"))
async def set_api(message: types.Message):
    global MOVIEBOX_API
    args = message.text.split()
    if len(args) > 1:
        MOVIEBOX_API = args[1].rstrip('/')
        await message.answer(f"✅ MovieBox API set to:\n<code>{MOVIEBOX_API}</code>", parse_mode="HTML")
    else:
        await message.answer(
            f"Current API: <code>{MOVIEBOX_API}</code>\n\n"
            "Usage: /api https://your-api-url.com",
            parse_mode="HTML"
        )

@router.message(F.text, lambda m: m.chat.type == "private")
async def search(message: types.Message):
    query = message.text.strip()
    if not query:
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching MovieBox for <b>{query}</b>...", parse_mode="HTML")

    results = await moviebox_search(query)

    if not results:
        await message.answer(
            f"❌ No results found for <b>{query}</b>.\n\n"
            "Check spelling or try another title.",
            parse_mode="HTML"
        )
        return

    # Show first result with stream
    for item in results[:5]:
        slug = item.get("slug") or item.get("id") or ""
        media_id = item.get("id") or item.get("media_id") or slug

        # Try to get stream URL
        stream_url = ""
        if slug:
            stream_url = await moviebox_stream(media_id, slug)
            if not stream_url:
                # Try detail endpoint
                detail = await moviebox_detail(slug)
                if detail:
                    stream_url = detail.get("stream_url") or detail.get("play_url") or ""

        text, kb = format_result(item, stream_url)
        await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        await asyncio.sleep(0.3)

    # If more than 5, show summary
    if len(results) > 5:
        await message.answer(
            f"📋 Showing first 5 of {len(results)} results.\n"
            "Search with a more specific title to narrow down.",
            parse_mode="HTML"
        )

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
    logger.info(f"Health server on port {PORT}")

async def main():
    await start_web_server()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Flixora polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
