#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - Telegram Channel Scraper
Searches public channels via t.me/s/ pages.
"""

import os
import re
import asyncio
import logging
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
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

# Default channels — add more with /addchannel
DEFAULT_CHANNELS = [
    # Add known public movie/series channels here (optional)
]

# In-memory channel list (lost on restart; use a file if needed)
channel_list = list(DEFAULT_CHANNELS)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def clean_text(t):
    return re.sub(r'\s+', ' ', t or '').strip()

async def search_channel(channel: str, query: str) -> list:
    """
    Scrape t.me/s/<channel>?q=<query> for posts with download links.
    Returns list of dicts: {title, link}
    """
    results = []
    try:
        username = channel.lstrip('@')
        url = f"https://t.me/s/{username}?q={query.replace(' ', '+')}"
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"Channel {channel} returned {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            # Telegram web preview posts are in div.tgme_widget_message
            posts = soup.select("div.tgme_widget_message")
            for post in posts:
                # Extract text from post
                text_elem = post.select_one("div.tgme_widget_message_text")
                text = clean_text(text_elem.get_text()) if text_elem else ""
                if not text:
                    continue
                # Match query in text (Telegram web does filtering already, but double-check)
                if query.lower() not in text.lower():
                    continue
                # Extract all links from post
                links = []
                for a in post.select("a.tgme_widget_message_link"):
                    href = a.get("href", "")
                    if href and href not in links:
                        links.append(href)
                # Also check inline text for URLs
                if text_elem:
                    for a in text_elem.select("a"):
                        href = a.get("href", "")
                        if href and href not in links:
                            links.append(href)
                if links:
                    results.append({
                        "title": text[:150],
                        "link": links[0],  # primary link
                        "all_links": links,
                        "channel": channel,
                    })
    except Exception as e:
        logger.warning(f"Error searching channel {channel}: {e}")
    return results

async def global_channel_search(query: str, limit: int = 20) -> list:
    """Search all channels in list, merge results."""
    all_results = []
    for channel in channel_list:
        res = await search_channel(channel, query)
        all_results.extend(res)
        if len(all_results) >= limit:
            break
    return all_results[:limit]

def format_results(results, query):
    """Format for Telegram with buttons."""
    if not results:
        return None, None
    text = f"🎬 <b>Search Results for:</b> <code>{query}</code>\n\n"
    kb_buttons = []
    for i, r in enumerate(results[:10], 1):
        title = clean_text(r['title'])[:80]
        text += f"{i}. <b>{title}</b>\n   📁 {r['channel']}\n\n"
        # Add button for each link (up to 3 per result)
        for j, link in enumerate(r['all_links'][:3], 1):
            kb_buttons.append([InlineKeyboardButton(text=f"⬇️ {i}.{j}", url=link)])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    return text, kb

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "I search public Telegram channels for direct download links.\n\n"
        "Commands:\n"
        "/addchannel @username - Add a channel\n"
        "/channels - List channels\n"
        "/removechannel @username - Remove channel\n\n"
        "Send me a movie or series name to search.",
        parse_mode="HTML"
    )

@router.message(Command("addchannel"))
async def add_channel(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /addchannel @username")
        return
    channel = args[1].lstrip('@')
    if channel not in channel_list:
        channel_list.append(channel)
        await message.answer(f"✅ Added @{channel}")
    else:
        await message.answer(f"@{channel} already in list.")

@router.message(Command("removechannel"))
async def remove_channel(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /removechannel @username")
        return
    channel = args[1].lstrip('@')
    if channel in channel_list:
        channel_list.remove(channel)
        await message.answer(f"✅ Removed @{channel}")
    else:
        await message.answer(f"@{channel} not in list.")

@router.message(Command("channels"))
async def list_channels(message: types.Message):
    if not channel_list:
        await message.answer("No channels added. Use /addchannel to add one.")
        return
    text = "📋 <b>Channels:</b>\n\n" + "\n".join([f"@{c}" for c in channel_list])
    await message.answer(text, parse_mode="HTML")

@router.message(F.text, lambda m: m.chat.type == "private")
async def search(message: types.Message):
    query = message.text.strip()
    if not query:
        return
    if not channel_list:
        await message.answer(
            "❌ No channels configured.\n\n"
            "Use /addchannel @channelname to add public channels that share download links.",
            parse_mode="HTML"
        )
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching channels for <b>{query}</b>...", parse_mode="HTML")
    results = await global_channel_search(query)
    text, kb = format_results(results, query)
    if not text:
        await message.answer(f"❌ No results found for <b>{query}</b> in configured channels.", parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

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
