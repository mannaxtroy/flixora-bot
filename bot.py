#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - Telegram Userbot Channel Search
Uses your Telegram account to search protected channels.
"""

import os
import re
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument
from aiohttp import web

BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
API_ID = 0        # ← put your api_id here
API_HASH = ""     # ← put your api_hash here
SESSION_NAME = "relay_session"
CHANNEL_USERNAME = "@ipapkornS2botdatabase"  # the channel your account is in
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Send me a movie or series name and I'll search the connected channel.\n\n"
        "Example:\n"
        "<code>The Incredible Hulk</code>\n"
        "<code>House of the Dragon</code>",
        parse_mode="HTML"
    )

@router.message(F.text, lambda m: m.chat.type == "private")
async def search(message: types.Message):
    query = message.text.strip()
    if not query:
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching channel for <b>{query}</b>...", parse_mode="HTML")

    try:
        # Get channel entity using your account's access
        channel = await client.get_entity(CHANNEL_USERNAME)

        # Try Telegram's search first
        results = []
        async for msg in client.iter_messages(channel, search=query, limit=20):
            if msg.message and msg.message.lower().find(query.lower()) != -1 or (msg.file and msg.file.name and query.lower() in msg.file.name.lower()):
                title = msg.message or (msg.file.name if msg.file else "File")
                # Get download link or file ID
                link = None
                if msg.media:
                    # For documents, use t.me link to the message
                    link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}/{msg.id}"
                results.append({
                    "title": title,
                    "link": link,
                    "message_id": msg.id,
                })
                if len(results) >= 10:
                    break

        if not results:
            # Fallback: scan recent messages
            async for msg in client.iter_messages(channel, limit=100):
                title = ""
                if msg.message:
                    title = msg.message
                elif msg.file and msg.file.name:
                    title = msg.file.name
                else:
                    continue
                if query.lower() in title.lower():
                    link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}/{msg.id}"
                    results.append({
                        "title": title,
                        "link": link,
                        "message_id": msg.id,
                    })
                    if len(results) >= 10:
                        break

        if not results:
            await message.answer(f"❌ No results found for <b>{query}</b>.", parse_mode="HTML")
            return

        text = f"🎬 <b>Search Results for:</b> <code>{query}</code>\n\n"
        kb_buttons = []
        for i, r in enumerate(results[:10], 1):
            title = r["title"][:120]
            text += f"{i}. <b>{title}</b>\n\n"
            kb_buttons.append([InlineKeyboardButton(text=f"⬇️ Download {i}", url=r["link"])])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Search error: {e}")
        await message.answer(f"⚠️ Search error: {e}")

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
    await client.start()
    logger.info("Userbot connected")
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Flixora polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
