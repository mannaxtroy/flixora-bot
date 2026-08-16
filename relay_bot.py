#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora Relay Bot
Flixora (aiogram) + Relay userbot (Telethon) -> iPopkornbot bridge
"""

import os
import re
import asyncio
import logging

BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
API_ID = 32829360
API_HASH = "34d8ba335bd2b39c9cca0856f680f3d5"
SESSION_NAME = "relay_session"
IPAPKORN_USERNAME = "@iPopkornbot"
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from telethon import TelegramClient, events

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

RELAY_CHAT_ID = None
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

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

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Send me any movie or series name with proper spelling.\n"
        "I'll search through iPapkorn's massive library and return your files.\n\n"
        "Example:\n"
        "<code>House of the Dragon</code>\n"
        "<code>Inception</code>",
        parse_mode="HTML"
    )

@router.message(Command("register"))
async def register(message: types.Message):
    global RELAY_CHAT_ID
    RELAY_CHAT_ID = message.chat.id
    await message.answer(f"✅ Relay registered with chat ID: <code>{RELAY_CHAT_ID}</code>", parse_mode="HTML")
    logger.info(f"Relay chat ID set to {RELAY_CHAT_ID}")

@router.message(Command("status"))
async def status(message: types.Message):
    if RELAY_CHAT_ID:
        await message.answer(f"✅ Relay connected\nChat ID: <code>{RELAY_CHAT_ID}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Relay not connected yet.\nSend /register from your relay account.")

@router.message(F.text)
async def search(message: types.Message):
    query = message.text.strip()
    if not query:
        return
    if not RELAY_CHAT_ID:
        await message.answer(
            "❌ Relay not connected.\n\n"
            "From your spare Telegram account, send /register to this bot first.",
            parse_mode="HTML"
        )
        return
    await message.answer(f"🔍 Searching for <b>{query}</b> via iPapkorn...", parse_mode="HTML")
    try:
        await bot.send_message(RELAY_CHAT_ID, f"RELAY_QUERY:{message.from_user.id}:{query}")
    except Exception as e:
        logger.error(f"Failed to send relay query: {e}")
        await message.answer("❌ Relay communication failed.")

@client.on(events.NewMessage(pattern=r'RELAY_QUERY:'))
async def relay_query_handler(event):
    text = event.raw_text
    try:
        parts = text.split(":", 2)
        user_id = int(parts[1])
        query = parts[2]
    except:
        return

    logger.info(f"Relay: processing query '{query}' for user {user_id}")

    try:
        await client.send_message(IPAPKORN_USERNAME, query)
        logger.info(f"Relay: sent to iPopkorn")

        await asyncio.sleep(7)

        async for msg in client.iter_messages(IPAPKORN_USERNAME, limit=5):
            if msg.text and not msg.out:
                response = msg.text
                logger.info(f"Relay: got response, forwarding to user {user_id}")
                try:
                    await bot.send_message(user_id, response, parse_mode="html")
                except:
                    await bot.send_message(user_id, response)
                return

        await bot.send_message(user_id, "⚠️ No response from iPopkornbot. Try again.")
    except Exception as e:
        logger.error(f"Relay error: {e}")
        try:
            await bot.send_message(user_id, f"⚠️ Relay error: {e}")
        except:
            pass

async def run_flixora():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot polling started")
    await dp.start_polling(bot)

async def run_relay():
    await client.start()
    logger.info("Relay userbot started")
    await client.run_until_disconnected()

async def main():
    await start_web_server()
    await asyncio.gather(
        run_flixora(),
        run_relay(),
    )

if __name__ == "__main__":
    asyncio.run(main())
