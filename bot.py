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
from aiohttp import web
from config import cfg
from cache import get_cache
from scraper import global_search, ScraperResult

logging.basicConfig(level=cfg.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=cfg.BOT_TOKEN)
dp = Dispatcher()
router = Router()
cache = get_cache()
user_prefs = {}
start_time = datetime.now()

# ─── FSM: chat search state ───
class SearchState(StatesGroup):
    waiting_for_query = State()

def format_result(r: ScraperResult, show_source: bool = True) -> tuple:
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
        "🎥 <b>Flixora Max Ultra</b>\n\n"
        "Enter a <b>movie or series name</b> below and I'll search 12+ sources worldwide for direct download and torrent links.\n\n"
        "<b>Examples:</b>\n"
        "<code>Inception</code>\n"
        "<code>House of the Dragon S02E01</code>\n"
        "<code>Attack on Titan</code>\n\n"
        "⚙️ Commands:\n"
        "/quality - Set quality filter\n"
        "/sort - Set sort order\n"
        "/sources - List sources\n"
        "/stats - Bot statistics\n"
        "/cancel - Stop current search",
        parse_mode="HTML"
    )

@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Search cancelled. Send /start to search again.")

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
    await callback.message.edit_text(f"✅ Quality set to: {quality or 'All'}")

@router.message(Command("sort"))
async def set_sort(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌱 Seeds (Best)", callback_data="sort_seeds")],
        [InlineKeyboardButton(text="📦 Size (Largest)", callback_data="sort_size")],
        [InlineKeyboardButton(text="🎞 Quality (Highest)", callback_data="sort_quality")],
        [InlineKeyboardButton(text="🌐 Source", callback_data="sort_source")],
    ])
    await message.answer("Sort results by:", reply_markup=kb)

@router.callback_query(lambda c: c.data.startswith("sort_"))
async def process_sort(callback: CallbackQuery):
    sort_by = callback.data.replace("sort_", "")
    user_prefs.setdefault(callback.from_user.id, {})["sort_by"] = sort_by
    labels = {"seeds": "Seeds", "size": "Size", "quality": "Quality", "source": "Source"}
    await callback.answer(f"Sort: {labels.get(sort_by, sort_by)}")
    await callback.message.edit_text(f"✅ Sort set to: {labels.get(sort_by, sort_by)}")

@router.message(Command("sources"))
async def list_sources(message: Message):
    sources = [
        "🌍 Archive.org - Direct files",
        "🎬 YTS.mx - Movies",
        "🏴 1337x - Movies/Series",
        "🏴 ThePirateBay - Movies/Series",
        "🍥 Nyaa.si - Anime/Series",
        "🌍 LimeTorrents - Movies/Series",
        "🌍 Torlock - Movies/Series",
        "📺 EZTV - TV Series",
        "🔍 DuckDuckGo - Web fallback",
        "📥 DirectDownload - DDL hosts",
        "🎬 SolarMovie - Direct stream",
    ]
    await message.answer("📋 <b>Active Sources (12+):</b>\n\n" + "\n".join(sources), parse_mode="HTML")

@router.message(Command("stats"))
async def stats(message: Message):
    users = len(user_prefs)
    uptime = datetime.now() - start_time
    await message.answer(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Users with preferences: {users}\n"
        f"🌐 Sources: 11\n"
        f"⏱ Uptime: {uptime}\n"
        f"🧠 Cache: {'Redis' if cfg.REDIS_URL else 'In-Memory'}\n"
        f"📦 Max results: {cfg.MAX_RESULTS}",
        parse_mode="HTML"
    )

# ─── CHAT SEARCH: catches any text when waiting_for_query ───
@router.message(SearchState.waiting_for_query, F.text)
async def chat_search(message: Message, state: FSMContext):
    q = message.text.strip()
    if not q:
        await message.answer("Please enter a movie or series name.")
        return
    
    # Keep state so user can search again immediately
    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(f"🔍 <b>Searching 12+ sources for:</b> <code>{q}</code>\nPlease wait...", parse_mode="HTML")
    
    user_id = message.from_user.id
    pref = user_prefs.get(user_id, {})
    quality_pref = pref.get("quality", "")
    sort_pref = pref.get("sort_by", "seeds")
    
    cache_key = f"chat:{q}:{quality_pref}:{sort_pref}"
    cached = await cache.get(cache_key)
    
    if cached:
        await message.answer("✅ <b>Results from cache:</b>", parse_mode="HTML")
        for item in cached[:10]:  # max 10 results per chat response
            await message.answer(item[0], parse_mode="HTML", reply_markup=item[1])
        return
    
    results = await global_search(q, limit=cfg.MAX_RESULTS, quality_filter=quality_pref, sort_by=sort_pref)
    
    if not results:
        await message.answer(
            f"❌ <b>No results found for:</b> <code>{q}</code>\n\n"
            "Try:\n"
            "• Check spelling\n"
            "• Use English title\n"
            "• Add year (e.g., <code>Dune 2021</code>)\n"
            "• For series add S01E01",
            parse_mode="HTML"
        )
        return
    
    # Cache formatted results
    formatted = []
    for r in results[:10]:
        text, kb = format_result(r, show_source=True)
        formatted.append((text, kb))
    
    await cache.set(cache_key, formatted, ttl=cfg.CACHE_TTL)
    
    await message.answer(f"✅ <b>Found {len(results)} results for:</b> <code>{q}</code>\nShowing top {len(formatted)}:", parse_mode="HTML")
    
    for text, kb in formatted:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        await asyncio.sleep(0.3)  # avoid Telegram rate limit

# ─── INLINE SEARCH (still works) ───
@router.inline_query()
async def inline_handler(query: InlineQuery):
    q = query.query.strip()
    if not q:
        await query.answer([], cache_time=0)
        return
    
    user_id = query.from_user.id
    pref = user_prefs.get(user_id, {})
    quality_pref = pref.get("quality", "")
    sort_pref = pref.get("sort_by", "seeds")
    
    cache_key = f"search:{q}:{quality_pref}:{sort_pref}"
    cached = await cache.get(cache_key)
    if cached:
        await query.answer(cached, cache_time=cfg.CACHE_TTL)
        return
    
    await query.answer(
        [InlineQueryResultArticle(
            id="searching",
            title="🔍 Searching 12+ sources...",
            description="Hang tight, this takes a few seconds",
            input_message_content=InputTextMessageContent(message_text="🔍 Searching all sources..."),
        )],
        cache_time=0
    )
    
    results = await global_search(q, limit=cfg.MAX_RESULTS, quality_filter=quality_pref, sort_by=sort_pref)
    
    inline_results = []
    for i, r in enumerate(results):
        text, kb = format_result(r, show_source=True)
        inline_results.append(
            InlineQueryResultArticle(
                id=f"{r.source}-{r.id}-{i}",
                title=r.title,
                description=f"{r.source} | {r.size} | {r.quality or 'N/A'} | Seeds: {r.seeders}",
                input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
                reply_markup=kb,
            )
        )
    
    await cache.set(cache_key, inline_results, ttl=cfg.CACHE_TTL)
    await query.answer(inline_results, cache_time=cfg.CACHE_TTL)

async def keep_alive():
    while True:
        try:
            await bot.get_me()
            logger.debug("Keep-alive ping sent")
        except Exception as e:
            logger.warning(f"Keep-alive failed: {e}")
        await asyncio.sleep(cfg.HEALTH_CHECK_INTERVAL)

async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", cfg.PORT)
    await site.start()
    logger.info(f"Health check server running on port {cfg.PORT}")

async def main():
    await start_web_server()
    asyncio.create_task(keep_alive())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())