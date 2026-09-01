import asyncio
import logging

import discord
from discord.ext import commands

import config
from client import QBittorrentDriver, QBitClientError
from models import AcquireRequest, SearchQuery
from orchestrator import DownloadOrchestrator
from search import QBitSearchProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


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


def _is_authorized(ctx: commands.Context) -> bool:
    if config.DISCORD_CHANNEL_ID and str(ctx.channel.id) == config.DISCORD_CHANNEL_ID:
        return True
    if config.DISCORD_ALLOWED_USER_ID and str(ctx.author.id) == config.DISCORD_ALLOWED_USER_ID:
        return True
    if not config.DISCORD_ALLOWED_USER_ID and not config.DISCORD_CHANNEL_ID:
        return True
    return False


@bot.event
async def on_ready():
    logger.info("Discord bot logged in as %s", bot.user)


@bot.command(name="get")
async def cmd_get(ctx: commands.Context, *, query_text: str = ""):
    if not _is_authorized(ctx):
        return
    if not query_text:
        await ctx.send("Usage: `!get <query>`")
        return

    ack = await ctx.send(f"Searching & acquiring candidate for \"{query_text}\"...")

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
        await ack.edit(content=f"Error: {exc}")
        return

    if success:
        await ack.edit(content=f"Download Complete: \"{query_text}\"")
    else:
        await ack.edit(content=f"Download Failed / Stalled: \"{query_text}\"")


@bot.command(name="url")
async def cmd_url(ctx: commands.Context, *, url: str = ""):
    if not _is_authorized(ctx):
        return
    if not url:
        await ctx.send("Usage: `!url <magnet or torrent URL>`")
        return

    ack = await ctx.send("Adding torrent...")

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
        await ack.edit(content=f"Error: {exc}")
        return

    if success:
        await ack.edit(content="Download Complete.")
    else:
        await ack.edit(content="Download Failed — torrent stalled.")


@bot.command(name="status")
async def cmd_status(ctx: commands.Context):
    if not _is_authorized(ctx):
        return

    driver, _ = _build_pipeline()
    try:
        torrents = driver._client.torrents_info()
    except Exception:
        await ctx.send("Failed to query qBittorrent.")
        return

    if not torrents:
        await ctx.send("No active transfers.")
        return

    embed = discord.Embed(title="Active Transfers", color=0x2d7a4f)
    for t in torrents[:10]:
        name = t.get("name", "?")[:50]
        pct = t.get("progress", 0) * 100
        speed = t.get("dlspeed", 0) / 1024
        state = t.get("state", "?")
        bar_filled = int(pct / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        embed.add_field(
            name=name,
            value=f"`{bar}` {pct:.1f}%\n{speed:.0f} KB/s | {state}",
            inline=False,
        )

    await ctx.send(embed=embed)


def main() -> None:
    if not config.DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set")
        return
    logger.info("Discord bot starting...")
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
