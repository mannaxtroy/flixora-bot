#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - Direct iPapkorn Relay
Aiogram bot + Telethon user account bridge
"""

import os
import re
import asyncio
import logging
from datetime import datetime

# ─── CREDENTIALS ───
BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
API_ID = 32829360        # ← replace with your api_id
API_HASH = "34d8ba335bd2b39c9cca0856f680f3d5"     # ← replace with your api_hash
SESSION_NAME = "relay_session"
IPAPKORN_USERNAME = "@iPapkornS2bot"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# ─── AIOGRAM HANDLERS ───
@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Send me any movie or series name with proper spelling.\n"
        "I'll search through iPapkorn's massive library and return your files with download buttons.\n\n"
        "Example:\n"
        "<code>House of the Dragon</code>\n"
        "<code>Inception</code>",
        parse_mode="HTML"
    )

@router.message(Command("status"))
async def status(message: types.Message):
    if client.is_connected():
        await message.answer("✅ Relay account connected")
    else:
        await message.answer("❌ Relay account not connected")

@router.message(F.text)
async def search(message: types.Message):
    query = message.text.strip()
    if not query:
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching for <b>{query}</b> via iPapkorn...", parse_mode="HTML")

    try:
        # Send query to iPapkorn using relay account
        await client.send_message(IPAPKORN_USERNAME, query)
        logger.info(f"Sent query to iPapkorn: {query}")

        # Wait for response
        await asyncio.sleep(8)

        # Get latest messages from iPapkorn
        async for msg in client.iter_messages(IPAPKORN_USERNAME, limit=5):
            if msg.out or not msg.text:
                continue

            # Build inline keyboard from buttons if present
            kb = None
            if msg.buttons:
                rows = []
                for row in msg.buttons:
                    btn_row = []
                    for btn in row:
                        if btn.url:
                            btn_row.append(InlineKeyboardButton(text=btn.text, url=btn.url))
                        elif btn.data:
                            btn_row.append(InlineKeyboardButton(text=btn.text, callback_data=btn.data))
                    if btn_row:
                        rows.append(btn_row)
                if rows:
                    kb = InlineKeyboardMarkup(inline_keyboard=rows)

            # Send response to Flixora user
            try:
                await bot.send_message(
                    message.chat.id,
                    msg.text,
                    parse_mode="HTML",
                    reply_markup=kb,
                    disable_web_page_preview=True
                )
            except Exception:
                # Fallback without parse_mode
                await bot.send_message(
                    message.chat.id,
                    msg.text,
                    reply_markup=kb,
                    disable_web_page_preview=True
                )
            return

        await message.answer("⚠️ No response from iPapkorn. Try again.")
    except Exception as e:
        logger.error(f"Relay error: {e}")
        await message.answer(f"⚠️ Relay error: {e}")

# ─── HEALTH SERVER ───
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

# ─── MAIN ───
async def main():
    await start_web_server()
    # Start Telethon client
    await client.start()
    logger.info("Relay userbot started")
    # Start aiogram
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Flixora polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
