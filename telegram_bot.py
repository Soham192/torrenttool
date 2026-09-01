import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import config
from client import QBittorrentDriver, QBitAuthError, QBitClientError
from models import AcquireRequest, SearchQuery
from orchestrator import DownloadOrchestrator
from search import QBitSearchProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_pipeline():
    driver = QBittorrentDriver(
        host=config.QBIT_HOST,
        port=config.QBIT_PORT,
        username=config.QBIT_USERNAME,
        password=config.QBIT_PASSWORD,
    )
    search_provider = QBitSearchProvider(driver._client)
    orchestrator = DownloadOrchestrator(driver, search_provider=search_provider)
    return driver, orchestrator


def _is_authorized(update: Update) -> bool:
    if not config.TELEGRAM_ALLOWED_USER_ID:
        return True
    return str(update.effective_user.id) == config.TELEGRAM_ALLOWED_USER_ID


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "qbit_pipeline bot\n\n"
        "/get <query> — Search and download\n"
        "/url <magnet/url> — Add a direct link\n"
        "/status — List active transfers"
    )


async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Usage: /get <query>")
        return

    msg = await update.message.reply_text(f"Searching for \"{query_text}\"...")
    driver, orchestrator = _build_pipeline()
    query = SearchQuery(query=query_text)

    try:
        success = await asyncio.to_thread(
            orchestrator.acquire_from_search,
            query,
            save_path=config.DEFAULT_SAVE_PATH,
            stall_timeout=60,
            poll_interval=3,
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

    msg = await update.message.reply_text(f"Adding torrent...")
    driver, orchestrator = _build_pipeline()
    request = AcquireRequest(source_url=url, save_path=config.DEFAULT_SAVE_PATH)

    try:
        success = await asyncio.to_thread(
            orchestrator.acquire,
            request,
            stall_timeout=60,
            poll_interval=3,
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

    driver, _ = _build_pipeline()
    try:
        torrents = driver._client.torrents_info()
    except Exception:
        await update.message.reply_text("Failed to query qBittorrent.")
        return

    if not torrents:
        await update.message.reply_text("No active transfers.")
        return

    lines = []
    for t in torrents[:10]:
        name = t.get("name", "?")
        pct = t.get("progress", 0) * 100
        speed = t.get("dlspeed", 0) / 1024
        state = t.get("state", "?")
        lines.append(f"{name}\n  {pct:.1f}% | {speed:.0f} KB/s | {state}")

    await update.message.reply_text("\n\n".join(lines))


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("status", cmd_status))

    logger.info("Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
