#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - Telegram Channel Scraper
Searches public channels via t.me/s/ pages.
Supports direct download URL resolution and forwarded channel auto-add.
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

# Default channels — @ipapkornS2botdatabase already included
DEFAULT_CHANNELS = ["ipapkornS2botdatabase"]

# In-memory channel list (initialized with default)
channel_list = list(DEFAULT_CHANNELS)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_text(t):
    return re.sub(r'\s+', ' ', t or '').strip()


def extract_post_full_text(post):
    """
    Extract searchable text from a Telegram web preview post.
    Includes message text, caption, document title, and media title.
    """
    parts = []

    # Message text
    text_elem = post.select_one("div.tgme_widget_message_text")
    if text_elem:
        parts.append(clean_text(text_elem.get_text()))

    # Caption
    caption_elem = post.select_one("div.tgme_widget_message_caption")
    if caption_elem:
        parts.append(clean_text(caption_elem.get_text()))

    # Document title (file name)
    doc_title = post.select_one("div.tgme_widget_message_document_title")
    if doc_title:
        parts.append(clean_text(doc_title.get_text()))

    # Media title (for audio/video)
    media_title = post.select_one("div.tgme_widget_message_media_title")
    if media_title:
        parts.append(clean_text(media_title.get_text()))

    # Fallback
    if not parts:
        for sel in [
            "a.tgme_widget_message_document_title",
            "span.tgme_widget_message_media_title",
            "div.tgme_widget_message_document_extra"
        ]:
            elem = post.select_one(sel)
            if elem:
                parts.append(clean_text(elem.get_text()))

    return " ".join(parts)


async def resolve_download_url(download_href: str) -> str:
    """
    Follow a Telegram download link and return the final CDN file URL.
    """
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            r = await client.get(download_href)
            return str(r.url)
    except Exception as e:
        logger.warning(f"Failed to resolve download URL {download_href}: {e}")
        return download_href


async def extract_post_links(post) -> list:
    """
    Extract direct download links from a Telegram post element.
    Resolves document download links to final CDN URLs.
    """
    links = []
    download_links = []

    # 1. Collect all ordinary links
    for a in post.select("a"):
        href = a.get("href", "")
        if not href:
            continue
        if href.startswith("/"):
            href = f"https://t.me{href}"
        if href not in links:
            links.append(href)

    # 2. Collect document download links separately
    for a in post.select("a.tgme_widget_message_download"):
        href = a.get("href", "")
        if not href:
            continue
        if href.startswith("/"):
            href = f"https://t.me{href}"
        if href not in download_links:
            download_links.append(href)

    # 3. Resolve download links to final CDN URLs
    direct_links = []
    for href in download_links:
        resolved = await resolve_download_url(href)
        if resolved and resolved not in direct_links:
            direct_links.append(resolved)

    # 4. Prefer direct CDN URLs. If none, fallback to ordinary links.
    if direct_links:
        return direct_links

    # 5. If no ordinary links either, try resolving the first document download link
    if download_links:
        return download_links

    return links


async def search_channel(channel: str, query: str) -> list:
    """
    Scrape t.me/s/<channel> for posts matching query.
    First tries Telegram's own search (?q=), then paginates recent posts.
    """
    results = []
    try:
        username = channel.lstrip('@')
        base = f"https://t.me/s/{username}"

        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            # ── 1) Try Telegram built-in search ──
            search_url = f"{base}?q={query.replace(' ', '+')}"
            resp = await client.get(search_url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                posts = soup.select("div.tgme_widget_message")
                if posts:
                    for post in posts:
                        full_text = extract_post_full_text(post).lower()
                        if query.lower() not in full_text:
                            continue
                        links = await extract_post_links(post)
                        if links:
                            title = full_text[:150]
                            results.append({
                                "title": title,
                                "link": links[0],
                                "all_links": links,
                                "channel": channel,
                            })
                    if results:
                        return results

            # ── 2) Fallback: paginate recent posts up to 10 pages ──
            next_url = base
            for _ in range(10):
                resp = await client.get(next_url)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                posts = soup.select("div.tgme_widget_message")
                if not posts:
                    break

                found = False
                for post in posts:
                    full_text = extract_post_full_text(post).lower()
                    if query.lower() not in full_text:
                        continue
                    links = await extract_post_links(post)
                    if links:
                        title = full_text[:150]
                        results.append({
                            "title": title,
                            "link": links[0],
                            "all_links": links,
                            "channel": channel,
                        })
                        found = True

                if found:
                    break

                older = soup.select_one("a.tme_messages_more")
                if not older:
                    break
                href = older.get("href", "")
                if href.startswith("/"):
                    next_url = f"https://t.me{href}"
                elif href.startswith("http"):
                    next_url = href
                else:
                    break

            return results

    except Exception as e:
        logger.warning(f"Error searching channel {channel}: {e}")
        return results


async def global_channel_search(query: str, limit: int = 20) -> list:
    """Search all configured channels, merge results."""
    all_results = []
    for channel in channel_list:
        res = await search_channel(channel, query)
        all_results.extend(res)
        if len(all_results) >= limit:
            break
    return all_results[:limit]


def format_results(results, query):
    """Format results for Telegram with direct download buttons."""
    if not results:
        return None, None

    text = f"🎬 <b>Search Results for:</b> <code>{query}</code>\n\n"
    kb_buttons = []

    for i, r in enumerate(results[:10], 1):
        title = clean_text(r['title'])[:80]
        text += f"{i}. <b>{title}</b>\n   📁 {r['channel']}\n\n"

        for j, link in enumerate(r['all_links'][:3], 1):
            kb_buttons.append([InlineKeyboardButton(text=f"⬇️ {i}.{j}", url=link)])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    return text, kb


# ───────────── AIOGRAM HANDLERS ─────────────

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "I search public Telegram channels for direct download links.\n\n"
        "Commands:\n"
        "/addchannel @username - Add a channel\n"
        "/channels - List channels\n"
        "/removechannel @username - Remove channel\n"
        "/clear - Clear all channels\n\n"
        "You can also <b>forward a message from a public channel</b> to me and I'll auto-add it.\n\n"
        "Send me a movie or series name to search.",
        parse_mode="HTML"
    )


@router.message(Command("addchannel"))
async def add_channel(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "Usage: /addchannel @username\n"
            "Or forward a message from a public channel to auto-add.",
            parse_mode="HTML"
        )
        return
    channel = args[1].lstrip('@')
    if channel not in channel_list:
        channel_list.append(channel)
        await message.answer(f"✅ Added @{channel}")
    else:
        await message.answer(f"@{channel} already in list.")


@router.message(lambda m: m.forward_from_chat is not None)
async def forwarded_channel_add(message: types.Message):
    chat = message.forward_from_chat
    if not chat:
        return
    if chat.username:
        channel = chat.username
        if channel not in channel_list:
            channel_list.append(channel)
            await message.answer(f"✅ Auto-added channel: @{channel}\nNow send a movie name to search.")
        else:
            await message.answer(f"@{channel} already in list.")
    else:
        await message.answer("❌ That chat doesn't have a public username, so I can't scrape it.")


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


@router.message(Command("clear"))
async def clear_channels(message: types.Message):
    channel_list.clear()
    await message.answer("✅ Cleared all channels.")


@router.message(Command("channels"))
async def list_channels(message: types.Message):
    if not channel_list:
        await message.answer("No channels added. Use /addchannel @username or forward a message from a public channel.")
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
            "Use /addchannel @username or forward a message from a public channel.",
            parse_mode="HTML"
        )
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching channels for <b>{query}</b>...", parse_mode="HTML")

    results = await global_channel_search(query)
    text, kb = format_results(results, query)

    if not text:
        await message.answer(
            f"❌ No results found for <b>{query}</b> in configured channels.",
            parse_mode="HTML"
        )
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


# ───────────── HEALTH SERVER ─────────────

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


# ───────────── MAIN ─────────────

async def main():
    await start_web_server()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Flixora polling started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
