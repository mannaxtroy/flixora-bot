#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flixora MovieBox - Group Relay with iPapkornS2bot
No Telethon, no API, no session. Pure aiogram.
"""

import os
import re
import asyncio
import logging
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8914900872:AAHZVd2EHww1KwnGFQaEOjPeYI9l02nT7Ms"
IPAPKORN_USERNAME = "iPapkornS2bot"  # without @
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Runtime-set via /setgroup or forwarded message
GROUP_CHAT_ID = None
# Store which user is waiting: query_lower -> user_id
waiting_users = {}

@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Send me any movie or series name with proper spelling.\n"
        "I'll search through iPapkorn's library and return your files with download buttons.\n\n"
        "Example:\n"
        "<code>House of the Dragon</code>\n"
        "<code>Inception</code>\n\n"
        "Use /setgroup to connect the relay group.",
        parse_mode="HTML"
    )

@router.message(Command("setgroup"))
async def set_group(message: types.Message):
    global GROUP_CHAT_ID
    # If sent in a group, set directly
    if message.chat.type in ("group", "supergroup"):
        GROUP_CHAT_ID = message.chat.id
        await message.answer(f"✅ This group is now the relay group.\nChat ID: <code>{GROUP_CHAT_ID}</code>", parse_mode="HTML")
        return

    # If sent privately, ask for a forwarded message from the group
    await message.answer(
        "📨 Please <b>forward any message from the group</b> where both bots are present.\n"
        "Or send the group chat ID directly: <code>/setgroup -1001234567890</code>",
        parse_mode="HTML"
    )

@router.message(lambda m: m.forward_from_chat is not None)
async def forwarded_group(message: types.Message):
    global GROUP_CHAT_ID
    chat = message.forward_from_chat
    if chat and chat.type in ("group", "supergroup", "channel"):
        GROUP_CHAT_ID = chat.id
        await message.answer(f"✅ Relay group set!\nChat ID: <code>{GROUP_CHAT_ID}</code>\nNow send me a movie name.", parse_mode="HTML")
    else:
        await message.answer("❌ That doesn't look like a group. Forward a message from the actual relay group.")

@router.message(Command("status"))
async def status(message: types.Message):
    if GROUP_CHAT_ID:
        await message.answer(f"✅ Relay group connected.\nChat ID: <code>{GROUP_CHAT_ID}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Relay group not set.\nCreate a group, add @FlixoraScraperbot and @iPapkornS2bot, then forward a message from that group to me here.")

@router.message(F.text, lambda m: m.chat.type == "private")
async def user_search(message: types.Message):
    if not GROUP_CHAT_ID:
        await message.answer(
            "❌ Relay group not set.\n\n"
            "1. Create a group\n"
            "2. Add @FlixoraScraperbot and @iPapkornS2bot\n"
            "3. Forward any message from that group to me here\n"
            "4. Then send your search again.",
            parse_mode="HTML"
        )
        return

    query = message.text.strip()
    if not query:
        return

    waiting_users[query.lower()] = message.from_user.id
    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching for <b>{query}</b> via iPapkorn...", parse_mode="HTML")

    try:
        # Send query to group where iPapkorn will respond
        await bot.send_message(GROUP_CHAT_ID, query)
    except Exception as e:
        logger.error(f"Failed to send to group: {e}")
        await message.answer("❌ Failed to send query to relay group. Make sure @FlixoraScraperbot is a member of the group.")

@router.message(F.text, lambda m: m.chat.type in ("group", "supergroup"))
async def group_reply(message: types.Message):
    if not message.text:
        return

    # Only listen to replies from iPapkorn
    sender = message.from_user.username.lower() if message.from_user and message.from_user.username else ""
    if sender != IPAPKORN_USERNAME.lower():
        return

    # Find which user this reply belongs to
    user_id = None
    for query, uid in list(waiting_users.items()):
        if query in message.text.lower():
            user_id = uid
            del waiting_users[query]
            break

    # If no match, send to the last waiting user
    if not user_id and waiting_users:
        last_query = list(waiting_users.keys())[-1]
        user_id = waiting_users.pop(last_query)

    if not user_id:
        logger.warning("Reply from iPapkorn but no waiting user")
        return

    # Build inline keyboard from buttons
    kb = None
    if message.reply_markup and message.reply_markup.inline_keyboard:
        rows = []
        for row in message.reply_markup.inline_keyboard:
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

    try:
        await bot.send_message(
            user_id,
            message.text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True
        )
        logger.info(f"Relayed iPapkorn reply to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to relay to user: {e}")
        try:
            await bot.send_message(
                user_id,
                message.text,
                reply_markup=kb,
                disable_web_page_preview=True
            )
        except:
            pass

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
