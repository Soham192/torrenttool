import asyncio
import logging

import discord
from discord import app_commands

import config
import bot_common
from models import AcquireRequest, SearchQuery, TaskStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True


class QBitBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._search_cache: dict[int, list] = {}

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Slash commands synced")


bot = QBitBot()


def _is_authorized(interaction: discord.Interaction) -> bool:
    if config.DISCORD_CHANNEL_ID and str(interaction.channel_id) == config.DISCORD_CHANNEL_ID:
        return True
    if config.DISCORD_ALLOWED_USER_ID and str(interaction.user.id) == config.DISCORD_ALLOWED_USER_ID:
        return True
    if not config.DISCORD_ALLOWED_USER_ID and not config.DISCORD_CHANNEL_ID:
        return True
    return False


def _tag_for(interaction: discord.Interaction) -> str:
    return bot_common.user_tag("dc", interaction.user.id)


class ResultSelect(discord.ui.Select):
    def __init__(self, results: list, user_id: int):
        self._results = results
        self._user_id = user_id
        options = []
        for i, r in enumerate(results[:25]):
            size = bot_common.format_size(r.size_bytes)
            options.append(discord.SelectOption(
                label=r.title[:95],
                description=f"{r.seeders} seeders | {size}",
                value=str(i),
            ))
        super().__init__(placeholder="Pick a result to download...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("Not your search.", ephemeral=True)
            return

        idx = int(self.values[0])
        result = self._results[idx]
        tag = _tag_for(interaction)

        await interaction.response.edit_message(
            content=f"Downloading: {result.title[:50]}...", view=None,
        )

        driver, _ = bot_common.get_pipeline()
        bot_common.ensure_tag(driver, tag)

        try:
            task_hash = await asyncio.to_thread(
                driver.add_task, result.download_url, config.DEFAULT_SAVE_PATH, tags=tag,
            )
        except Exception as exc:
            await interaction.edit_original_response(content=f"Failed: {exc}")
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
                    interaction.edit_original_response(
                        content=f"Downloading: {result.title[:40]}\n{milestone}% | {speed}",
                    ),
                    loop,
                )

        def blocking_monitor():
            _, orch = bot_common.get_pipeline()
            return orch._monitor_to_completion(task_hash, poll_interval=3, progress_callback=progress_cb)

        try:
            completed = await asyncio.to_thread(blocking_monitor)
        except Exception as exc:
            await interaction.edit_original_response(content=f"Error: {exc}")
            return

        if completed:
            await interaction.edit_original_response(content=f"Complete: {result.title[:50]}")
        else:
            await interaction.edit_original_response(content=f"Download failed: {result.title[:50]}")


class CancelSelect(discord.ui.Select):
    def __init__(self, torrents: list, user_id: int):
        self._torrents = torrents
        self._user_id = user_id
        options = []
        for t in torrents[:25]:
            name = t.get("name", "?")[:95]
            pct = t.get("progress", 0) * 100
            options.append(discord.SelectOption(
                label=name,
                description=f"{pct:.0f}%",
                value=t.get("hash", ""),
            ))
        super().__init__(placeholder="Pick a torrent to cancel...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("Not your downloads.", ephemeral=True)
            return

        torrent_hash = self.values[0]
        driver, _ = bot_common.get_pipeline()

        try:
            removed = await asyncio.to_thread(driver.remove_task, torrent_hash, True)
        except Exception as exc:
            await interaction.response.edit_message(content=f"Failed: {exc}", view=None)
            return

        if removed:
            await interaction.response.edit_message(content="Torrent cancelled and files removed.", view=None)
        else:
            await interaction.response.edit_message(content="Torrent not found.", view=None)


@bot.tree.command(name="search", description="Search for torrents and pick one to download")
@app_commands.describe(
    query="Search query",
    category="Category filter",
    min_seeders="Minimum seeders",
)
async def cmd_search(
    interaction: discord.Interaction,
    query: str,
    category: str = "all",
    min_seeders: int = 1,
):
    if not _is_authorized(interaction):
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return

    await interaction.response.defer()

    driver, orchestrator = bot_common.get_pipeline()
    sq = SearchQuery(query=query, category=category, min_seeders=min_seeders)

    try:
        results = await asyncio.to_thread(orchestrator.search_only, sq)
    except Exception as exc:
        await interaction.followup.send(f"Search failed: {exc}")
        return

    if not results:
        await interaction.followup.send("No results found.")
        return

    bot._search_cache[interaction.user.id] = results

    view = discord.ui.View(timeout=120)
    view.add_item(ResultSelect(results, interaction.user.id))
    await interaction.followup.send(f"Found {len(results)} results:", view=view)


@bot.tree.command(name="get", description="Auto-download the best match for a query")
@app_commands.describe(query="Search query")
async def cmd_get(interaction: discord.Interaction, query: str):
    if not _is_authorized(interaction):
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return

    await interaction.response.defer()
    tag = _tag_for(interaction)

    driver, orchestrator = bot_common.get_pipeline()
    bot_common.ensure_tag(driver, tag)
    sq = SearchQuery(query=query)

    loop = asyncio.get_event_loop()
    last_milestone = [0]

    def progress_cb(status: TaskStatus):
        pct = int(status.progress * 100)
        milestone = (pct // 25) * 25
        if milestone > last_milestone[0]:
            last_milestone[0] = milestone
            speed = bot_common.format_speed(status.download_speed)
            asyncio.run_coroutine_threadsafe(
                interaction.edit_original_response(
                    content=f"Downloading \"{query}\"... {milestone}% | {speed}",
                ),
                loop,
            )

    try:
        success = await asyncio.to_thread(
            orchestrator.acquire_from_search,
            sq,
            save_path=config.DEFAULT_SAVE_PATH,
            stall_timeout=60,
            poll_interval=3,
            progress_callback=progress_cb,
        )
    except Exception as exc:
        await interaction.followup.send(f"Error: {exc}")
        return

    if success:
        await interaction.edit_original_response(content=f"Download complete: \"{query}\"")
    else:
        await interaction.edit_original_response(content=f"Download failed/stalled: \"{query}\"")


@bot.tree.command(name="url", description="Add a torrent by magnet link or URL")
@app_commands.describe(url="Magnet link or torrent URL")
async def cmd_url(interaction: discord.Interaction, url: str):
    if not _is_authorized(interaction):
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return

    await interaction.response.defer()
    tag = _tag_for(interaction)

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
                interaction.edit_original_response(
                    content=f"Downloading... {milestone}% | {speed}",
                ),
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
        await interaction.followup.send(f"Error: {exc}")
        return

    if success:
        await interaction.edit_original_response(content="Download complete.")
    else:
        await interaction.edit_original_response(content="Download failed — torrent stalled.")


@bot.tree.command(name="status", description="Show your active transfers")
async def cmd_status(interaction: discord.Interaction):
    if not _is_authorized(interaction):
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return

    await interaction.response.defer()
    tag = _tag_for(interaction)
    driver, _ = bot_common.get_pipeline()
    torrents = await asyncio.to_thread(bot_common.get_user_torrents, driver, tag)

    if not torrents:
        await interaction.followup.send("No active transfers.")
        return

    embed = discord.Embed(title="Your Transfers", color=0x2d7a4f)
    for t in torrents[:10]:
        name = t.get("name", "?")[:50]
        pct = t.get("progress", 0) * 100
        speed = bot_common.format_speed(t.get("dlspeed", 0))
        state = t.get("state", "?")
        eta = t.get("eta", 0)
        eta_str = f"{eta}s" if eta < 8640000 else "--"
        bar_filled = int(pct / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        embed.add_field(
            name=name,
            value=f"`{bar}` {pct:.1f}%\n{speed} | ETA {eta_str} | {state}",
            inline=False,
        )

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="cancel", description="Cancel one of your downloads")
async def cmd_cancel(interaction: discord.Interaction):
    if not _is_authorized(interaction):
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return

    await interaction.response.defer()
    tag = _tag_for(interaction)
    driver, _ = bot_common.get_pipeline()
    torrents = await asyncio.to_thread(bot_common.get_user_torrents, driver, tag)

    if not torrents:
        await interaction.followup.send("No active transfers to cancel.")
        return

    view = discord.ui.View(timeout=60)
    view.add_item(CancelSelect(torrents, interaction.user.id))
    await interaction.followup.send("Select a torrent to cancel:", view=view)


@bot.event
async def on_ready():
    logger.info("Discord bot logged in as %s", bot.user)


def main() -> None:
    if not config.DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not set")
        return
    logger.info("Discord bot starting...")
    bot.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
