# qbit_pipeline

A torrent download pipeline powered by qBittorrent's Web API. Search, download, and monitor torrents via a **Streamlit dashboard**, **Telegram bot**, **Discord bot**, or **CLI**.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `QBIT_HOST` | qBittorrent Web UI host | `localhost` |
| `QBIT_PORT` | qBittorrent Web UI port | `8080` |
| `QBIT_USERNAME` | Login username | `admin` |
| `QBIT_PASSWORD` | Login password | *(empty)* |
| `DEFAULT_SAVE_PATH` | Download directory | `/downloads` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (optional) | |
| `TELEGRAM_ALLOWED_USER_ID` | Restrict to one Telegram user (optional) | |
| `DISCORD_BOT_TOKEN` | Discord bot token (optional) | |
| `DISCORD_ALLOWED_USER_ID` | Restrict to one Discord user (optional) | |
| `DISCORD_CHANNEL_ID` | Restrict to one Discord channel (optional) | |

## Streamlit Dashboard

```bash
streamlit run app.py --server.headless true
```

Open `http://localhost:8501`. Enter a username, search, pick results, and watch downloads.

## Telegram Bot

### Setup
1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → get your token
2. Get your user ID: message [@userinfobot](https://t.me/userinfobot)
3. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your-token-here
   TELEGRAM_ALLOWED_USER_ID=your-user-id
   ```
4. Run: `python telegram_bot.py`

### Commands
| Command | Description |
|---|---|
| `/search <query>` | Browse results with inline buttons — pick one to download |
| `/get <query>` | Auto-download the best match |
| `/url <magnet>` | Add a torrent by magnet link or URL |
| `/status` | Show your active transfers |
| `/cancel` | Cancel a download |

Optional filters: `/search ubuntu category=software seeds=5`

## Discord Bot

### Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications) → New Application
2. Bot tab → Reset Token → copy it
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. OAuth2 → URL Generator → select `bot` + `applications.commands` scopes → select permissions: Send Messages, Embed Links, Use Slash Commands → copy invite URL → open in browser to add bot to your server
5. Add to `.env`:
   ```
   DISCORD_BOT_TOKEN=your-token-here
   DISCORD_ALLOWED_USER_ID=your-user-id
   ```
6. Run: `python discord_bot.py`

### Slash Commands
| Command | Description |
|---|---|
| `/search <query> [category] [min_seeders]` | Browse results in a dropdown — pick one |
| `/get <query>` | Auto-download the best match |
| `/url <url>` | Add a torrent by magnet link |
| `/status` | Show your active transfers |
| `/cancel` | Cancel a download from a dropdown |

## CLI

```bash
python main.py --url "magnet:?xt=urn:btih:..."
python main.py --search "ubuntu 24.04" --category software --min-seeds 5
```

## Docker Deployment

Deploy the full stack (qBittorrent + Streamlit + Telegram bot + Discord bot):

```bash
cp .env.example .env   # edit with your tokens and password
docker compose up -d
```

## Architecture

```
Frontends                          Core                        Backend
─────────                          ────                        ───────
app.py (Streamlit)  ─┐
telegram_bot.py     ─┤             orchestrator.py             qBittorrent
discord_bot.py      ─┤── bot_common.py ──┤                     Web API
main.py (CLI)       ─┘             client.py ─── search.py ──────┘
                                   models.py    config.py
```

## Tests

```bash
python -m pytest tests/ -v
```

All tests are fully mocked — no live qBittorrent instance required.
