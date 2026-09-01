import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import config
import bot_common
from models import AcquireRequest, SearchQuery, TaskStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_search_cache: dict[int, list] = {}


def _is_authorized(update: Update) -> bool:
    if update.effective_user is None:
        return False
    if not config.TELEGRAM_ALLOWED_USER_ID:
        return True
    return str(update.effective_user.id) == config.TELEGRAM_ALLOWED_USER_ID


def _tag_for(update: Update) -> str:
    return bot_common.user_tag("tg", update.effective_user.id)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "qbit_pipeline bot\n\n"
        "/search <query> — Browse results and pick one\n"
        "/get <query> — Auto-download best match\n"
        "/url <magnet/url> — Add a direct link\n"
        "/status — List your active transfers\n"
        "/cancel — Cancel a download"
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /search <query>")
        return

    category = "all"
    min_seeders = 1
    query_words = []
    for arg in args:
        if arg.startswith("category="):
            category = arg.split("=", 1)[1]
        elif arg.startswith("seeds="):
            try:
                min_seeders = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        else:
            query_words.append(arg)

    query_text = " ".join(query_words)
    if not query_text:
        await update.message.reply_text("Usage: /search <query>")
        return

    msg = await update.message.reply_text(f"Searching for \"{query_text}\"...")

    driver, orchestrator = bot_common.get_pipeline()
    query = SearchQuery(query=query_text, category=category, min_seeders=min_seeders)

    try:
        results = await asyncio.to_thread(orchestrator.search_only, query)
    except Exception as exc:
        await msg.edit_text(f"Search failed: {exc}")
        return

    if not results:
        await msg.edit_text("No results found.")
        return

    user_id = update.effective_user.id
    _search_cache[user_id] = results

    buttons = []
    for i, r in enumerate(results[:10]):
        size = bot_common.format_size(r.size_bytes)
        label = f"{r.title[:40]} | {r.seeders}s | {size}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"dl:{i}")])

    await msg.edit_text(
        f"Found {len(results)} results — pick one:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not _is_authorized(update):
        return

    user_id = update.effective_user.id
    tag = _tag_for(update)

    idx = int(query.data.split(":")[1])
    results = _search_cache.get(user_id, [])
    if idx >= len(results):
        await query.edit_message_text("Result expired — run /search again.")
        return

    result = results[idx]
    await query.edit_message_text(f"Downloading: {result.title[:50]}...")

    driver, _ = bot_common.get_pipeline()
    bot_common.ensure_tag(driver, tag)

    try:
        task_hash = await asyncio.to_thread(
            driver.add_task, result.download_url, config.DEFAULT_SAVE_PATH, tags=tag,
        )
    except Exception as exc:
        await query.edit_message_text(f"Failed: {exc}")
        return

    loop = asyncio.get_event_loop()
    last_milestone = [0]

    def progress_cb(status: TaskStatus):
        pct = int(status.progress * 100)
        milestone = (pct // 25) * 25
        if milestone > last_milestone[0]:
            last_milestone[0] = milestone
            speed = bot_common.format_speed(status.download_speed)
            asyncio.run_coroutine_threadsafe(
                query.edit_message_text(f"Downloading: {result.title[:40]}\n{milestone}% | {speed}"),
                loop,
            )

    def blocking_monitor():
        _, orch = bot_common.get_pipeline()
        return orch._monitor_to_completion(task_hash, poll_interval=3, progress_callback=progress_cb)

    try:
        completed = await asyncio.to_thread(blocking_monitor)
    except Exception as exc:
        await query.edit_message_text(f"Error during download: {exc}")
        return

    if completed:
        await query.edit_message_text(f"Complete: {result.title[:50]}")
    else:
        await query.edit_message_text(f"Download failed: {result.title[:50]}")


async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Usage: /get <query>")
        return

    tag = _tag_for(update)
    msg = await update.message.reply_text(f"Searching & downloading \"{query_text}\"...")

    driver, orchestrator = bot_common.get_pipeline()
    bot_common.ensure_tag(driver, tag)
    query = SearchQuery(query=query_text)

    loop = asyncio.get_event_loop()
    last_milestone = [0]

    def progress_cb(status: TaskStatus):
        pct = int(status.progress * 100)
        milestone = (pct // 25) * 25
        if milestone > last_milestone[0]:
            last_milestone[0] = milestone
            speed = bot_common.format_speed(status.download_speed)
            asyncio.run_coroutine_threadsafe(
                msg.edit_text(f"Downloading... {milestone}% | {speed}"),
                loop,
            )

    try:
        success = await asyncio.to_thread(
            orchestrator.acquire_from_search,
            query,
            save_path=config.DEFAULT_SAVE_PATH,
            stall_timeout=60,
            poll_interval=3,
            progress_callback=progress_cb,
        )
    except Exception as exc:
        await msg.edit_text(f"Error: {exc}")
        return

    if success:
        await msg.edit_text(f"Download complete: \"{query_text}\"")
    else:
        await msg.edit_text(f"Download failed/stalled: \"{query_text}\"")


async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text("Usage: /url <magnet or torrent URL>")
        return

    tag = _tag_for(update)
    msg = await update.message.reply_text("Adding torrent...")

    driver, orchestrator = bot_common.get_pipeline()
    bot_common.ensure_tag(driver, tag)
    request = AcquireRequest(source_url=url, save_path=config.DEFAULT_SAVE_PATH)

    loop = asyncio.get_event_loop()
    last_milestone = [0]

    def progress_cb(status: TaskStatus):
        pct = int(status.progress * 100)
        milestone = (pct // 25) * 25
        if milestone > last_milestone[0]:
            last_milestone[0] = milestone
            speed = bot_common.format_speed(status.download_speed)
            asyncio.run_coroutine_threadsafe(
                msg.edit_text(f"Downloading... {milestone}% | {speed}"),
                loop,
            )

    try:
        success = await asyncio.to_thread(
            orchestrator.acquire,
            request,
            stall_timeout=60,
            poll_interval=3,
            progress_callback=progress_cb,
        )
    except Exception as exc:
        await msg.edit_text(f"Error: {exc}")
        return

    if success:
        await msg.edit_text("Download complete.")
    else:
        await msg.edit_text("Download failed — torrent stalled.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    tag = _tag_for(update)
    driver, _ = bot_common.get_pipeline()
    torrents = await asyncio.to_thread(bot_common.get_user_torrents, driver, tag)

    if not torrents:
        await update.message.reply_text("No active transfers.")
        return

    lines = []
    for t in torrents[:10]:
        name = t.get("name", "?")[:50]
        pct = t.get("progress", 0) * 100
        speed = bot_common.format_speed(t.get("dlspeed", 0))
        state = t.get("state", "?")
        eta = t.get("eta", 0)
        eta_str = f"{eta}s" if eta < 8640000 else "--"
        lines.append(f"{name}\n  {pct:.1f}% | {speed} | ETA {eta_str} | {state}")

    await update.message.reply_text("\n\n".join(lines))


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    tag = _tag_for(update)
    driver, _ = bot_common.get_pipeline()
    torrents = await asyncio.to_thread(bot_common.get_user_torrents, driver, tag)

    if not torrents:
        await update.message.reply_text("No active transfers to cancel.")
        return

    buttons = []
    for i, t in enumerate(torrents[:10]):
        name = t.get("name", "?")[:45]
        pct = t.get("progress", 0) * 100
        buttons.append([InlineKeyboardButton(
            f"{name} ({pct:.0f}%)",
            callback_data=f"cancel:{t.get('hash', '')}",
        )])

    await update.message.reply_text(
        "Select a torrent to cancel:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not _is_authorized(update):
        return

    torrent_hash = query.data.split(":")[1]
    driver, _ = bot_common.get_pipeline()

    try:
        removed = await asyncio.to_thread(driver.remove_task, torrent_hash, True)
    except Exception as exc:
        await query.edit_message_text(f"Failed to cancel: {exc}")
        return

    if removed:
        await query.edit_message_text("Torrent cancelled and files removed.")
    else:
        await query.edit_message_text("Torrent not found — may have already finished.")


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(callback_download, pattern=r"^dl:"))
    app.add_handler(CallbackQueryHandler(callback_cancel, pattern=r"^cancel:"))

    logger.info("Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
