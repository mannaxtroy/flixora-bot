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
from telethon import TelegramClient
from aiohttp import web

BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
API_ID = 32829360
API_HASH = "34d8ba335bd2b39c9cca0856f680f3d5"
SESSION_NAME = "relay_session"
CHANNEL_USERNAME = "@ipapkornS2botdatabase"
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
        channel = await client.get_entity(CHANNEL_USERNAME)

        results = []

        # Try Telegram's search first
        async for msg in client.iter_messages(channel, search=query, limit=20):
            title = ""
            if msg.message:
                title = msg.message
            elif msg.file and msg.file.name:
                title = msg.file.name
            else:
                continue

            if query.lower() not in title.lower():
                continue

            link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}/{msg.id}"
            results.append({"title": title, "link": link})
            if len(results) >= 10:
                break

        # Fallback: scan recent 100 messages
        if not results:
            async for msg in client.iter_messages(channel, limit=100):
                title = ""
                if msg.message:
                    title = msg.message
                elif msg.file and msg.file.name:
                    title = msg.file.name
                else:
                    continue

                if query.lower() not in title.lower():
                    continue

                link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}/{msg.id}"
                results.append({"title": title, "link": link})
                if len(results) >= 10:
                    break

        if not results:
            await message.answer(f"❌ No results found for <b>{query}</b>.", parse_mode="HTML")
            return

        text = f"🎬 <b>Search Results for:</b> <code>{query}</code>\n\n"
        kb_buttons = []
        for i, r in enumerate(results[:10], 1):
            clean_title = re.sub(r'<[^>]+>', '', r['title'])[:120]
            text += f"{i}. <b>{clean_title}</b>\n\n"
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
