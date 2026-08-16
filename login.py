#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-time Telethon session generator for Flixora relay.
"""

import asyncio
from telethon import TelegramClient

API_ID = 32829360
API_HASH = "34d8ba335bd2b39c9cca0856f680f3d5"
SESSION_NAME = "relay_session"

async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"✅ Logged in as {me.first_name} (@{me.username})")
    print("Session file created: relay_session.session")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
