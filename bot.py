import os
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import cfg
from cache import get_cache
from scraper import global_search, test_sources, ScraperResult
from tmdb import TMDBLookup

logging.basicConfig(level=cfg.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=cfg.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
cache = get_cache()
user_prefs = {}
tmdb = TMDBLookup(cfg.TMDB_API_KEY)
start_time = datetime.now()

class SearchState(StatesGroup):
    waiting_for_query = State()

RENDER_APP_URL = cfg.RENDER_APP_URL
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{RENDER_APP_URL}{WEBHOOK_PATH}"

def format_result(r: ScraperResult, show_source=True):
    emoji = "🎬" if r.type == "movie" else "📺"
    seeds = f"👥 {r.seeders}" if r.seeders else ""
    leech = f"💀 {r.leechers}" if r.leechers else ""
    q = f" | 🎞 {r.quality}" if r.quality else ""
    size = f" | 📦 {r.size}" if r.size else ""
    text = (
        f"{emoji} <b>{r.title}</b>\n"
        f"📅 {r.year or 'Unknown'}{size}{q}\n"
    )
    if seeds or leech:
        text += f"{seeds} {leech}\n"
    if show_source:
        text += f"🌐 {r.source}\n"
    text += f"\n<b>Links:</b>\n"
    kb_buttons = []
    for i, link in enumerate(r.links[:5], 1):
        text += f"{i}. <a href='{link}'>Download {i}</a>\n"
        kb_buttons.append([InlineKeyboardButton(text=f"⬇️ Download {i}", url=link)])
    if r.magnet:
        text += f"\n🧲 <a href='{r.magnet}'>Magnet Link</a>\n"
        kb_buttons.append([InlineKeyboardButton(text="🧲 Magnet", url=r.magnet)])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    return text, kb

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🎬 <b>Flixora MovieBox</b>\n\n"
        "Send me any movie or series name and I'll find direct download and torrent links with posters and metadata.\n\n"
        "<b>Examples:</b>\n"
        "<code>Inception</code>\n"
        "<code>House of the Dragon S02E01</code>\n\n"
        "Commands:\n"
        "/quality - Set quality filter\n"
        "/sort - Sort order\n"
        "/sources - Active sources\n"
        "/test - Test sources\n"
        "/stats - Statistics\n"
        "/cancel - Stop search",
        parse_mode="HTML"
    )

@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Search cancelled.")

@router.message(Command("quality"))
async def set_quality(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="All", callback_data="quality_all")],
        [InlineKeyboardButton(text="720p", callback_data="quality_720p")],
        [InlineKeyboardButton(text="1080p", callback_data="quality_1080p")],
        [InlineKeyboardButton(text="4K", callback_data="quality_4K")],
    ])
    await message.answer("Select preferred quality:", reply_markup=kb)

@router.callback_query(lambda c: c.data.startswith("quality_"))
async def process_quality(callback: CallbackQuery):
    quality = callback.data.replace("quality_", "")
    if quality == "all":
        quality = ""
    user_prefs.setdefault(callback.from_user.id, {})["quality"] = quality
    await callback.answer(f"Quality: {quality or 'All'}")
    await callback.message.edit_text(f"✅ Quality: {quality or 'All'}")

@router.message(Command("sort"))
async def set_sort(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Seeds", callback_data="sort_seeds")],
        [InlineKeyboardButton(text="📦 Size", callback_data="sort_size")],
        [InlineKeyboardButton(text="🎞 Quality", callback_data="sort_quality")],
    ])
    await message.answer("Sort results by:", reply_markup=kb)

@router.callback_query(lambda c: c.data.startswith("sort_"))
async def process_sort(callback: CallbackQuery):
    sort_by = callback.data.replace("sort_", "")
    user_prefs.setdefault(callback.from_user.id, {})["sort_by"] = sort_by
    labels = {"seeds": "Seeds", "size": "Size", "quality": "Quality"}
    await callback.answer(f"Sort: {labels.get(sort_by)}")
    await callback.message.edit_text(f"✅ Sort: {labels.get(sort_by)}")

@router.message(Command("sources"))
async def list_sources(message: Message):
    sources = [
        "🎬 YTS.mx", "🏴 1337x", "🏴 TPB", "🍥 Nyaa",
        "🌍 TorrentGalaxy", "🌍 LimeTorrents", "🔍 DuckDuckGo"
    ]
    await message.answer("📋 <b>Active Sources:</b>\n\n" + "\n".join(sources), parse_mode="HTML")

@router.message(Command("test"))
async def test(message: Message):
    await message.answer("🔍 Testing sources...")
    status = await test_sources()
    text = "📊 <b>Source Status:</b>\n\n"
    for name, st in status.items():
        text += f"• {name}: {st}\n"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("stats"))
async def stats(message: Message):
    uptime = datetime.now() - start_time
    await message.answer(
        f"📊 <b>Stats</b>\n\n"
        f"⏱ Uptime: {uptime}\n"
        f"🧠 Cache: {'Redis' if cfg.REDIS_URL else 'Memory'}\n"
        f"📦 Max results: {cfg.MAX_RESULTS}",
        parse_mode="HTML"
    )

@router.message(SearchState.waiting_for_query, F.text)
async def chat_search(message: Message, state: FSMContext):
    q = message.text.strip()
    if not q:
        await message.answer("Please send a movie or series name.")
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 Searching for <b>{q}</b>...", parse_mode="HTML")
    
    pref = user_prefs.get(message.from_user.id, {})
    quality = pref.get("quality", "")
    sort_by = pref.get("sort_by", "seeds")
    
    metadata = await tmdb.get_metadata(q, "movie") or await tmdb.get_metadata(q, "tv")
    if metadata and metadata.get("poster_url"):
        caption = (
            f"🎬 <b>{metadata['title']}</b> ({metadata['year']})\n"
            f"⭐ {metadata['rating']}/10\n\n"
            f"{metadata['overview'][:300]}..."
        )
        await message.answer_photo(photo=metadata["poster_url"], caption=caption, parse_mode="HTML")
    
    cache_key = f"chat:{q}:{quality}:{sort_by}"
    cached = await cache.get(cache_key)
    if cached:
        for item in cached[:10]:
            await message.answer(item[0], parse_mode="HTML", reply_markup=item[1])
        return
    
    results = await global_search(q, limit=cfg.MAX_RESULTS, quality_filter=quality, sort_by=sort_by)
    if not results:
        await message.answer(f"❌ No results found for <b>{q}</b>.\nTry adding year or S01E01.", parse_mode="HTML")
        return
    
    formatted = []
    for r in results[:10]:
        text, kb = format_result(r)
        formatted.append((text, kb))
    await cache.set(cache_key, formatted, ttl=cfg.CACHE_TTL)
    await message.answer(f"✅ Found {len(results)} results. Showing top {len(formatted)}:")
    for text, kb in formatted:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        await asyncio.sleep(0.2)

@router.inline_query()
async def inline_handler(query: InlineQuery):
    q = query.query.strip()
    if not q:
        await query.answer([], cache_time=0)
        return
    pref = user_prefs.get(query.from_user.id, {})
    quality = pref.get("quality", "")
    sort_by = pref.get("sort_by", "seeds")
    cache_key = f"inline:{q}:{quality}:{sort_by}"
    cached = await cache.get(cache_key)
    if cached:
        await query.answer(cached, cache_time=cfg.CACHE_TTL)
        return
    await query.answer([InlineQueryResultArticle(
        id="searching", title="🔍 Searching...",
        input_message_content=InputTextMessageContent(message_text="🔍 Searching...")
    )], cache_time=0)
    results = await global_search(q, limit=20, quality_filter=quality, sort_by=sort_by)
    inline_results = []
    for i, r in enumerate(results):
        text, kb = format_result(r)
        inline_results.append(InlineQueryResultArticle(
            id=f"{r.source}-{r.id}-{i}",
            title=r.title,
            description=f"{r.source} | {r.size} | {r.quality or 'N/A'} | Seeds: {r.seeders}",
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
            reply_markup=kb,
        ))
    await cache.set(cache_key, inline_results, ttl=cfg.CACHE_TTL)
    await query.answer(inline_results, cache_time=cfg.CACHE_TTL)

async def health_check(request):
    return web.Response(text="OK", status=200)

async def main():
    # CRITICAL: register router with dispatcher
    dp.include_router(router)
    
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook set to {WEBHOOK_URL}")
    
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", cfg.PORT)
    await site.start()
    logger.info(f"Server started on port {cfg.PORT}")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())