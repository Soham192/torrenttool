# qbit_pipeline

A CLI tool and Python library for downloading torrents via qBittorrent's Web API. Adds a torrent, monitors for activity, and either waits for completion or removes stalled downloads.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in your qBittorrent connection details:

| Variable | Description | Default |
|---|---|---|
| `QBIT_HOST` | qBittorrent Web UI host | `localhost` |
| `QBIT_PORT` | qBittorrent Web UI port | `8080` |
| `QBIT_USERNAME` | Login username | `admin` |
| `QBIT_PASSWORD` | Login password | *(empty)* |
| `DEFAULT_SAVE_PATH` | Default download directory | `/downloads` |

## Usage

```bash
python main.py "magnet:?xt=urn:btih:..." --save-path /data --timeout 60
```

Options:
- `--save-path PATH` — Override download directory
- `--timeout N` — Stall timeout in seconds (default: 30)
- `--poll-interval N` — Status check interval in seconds (default: 2)
- `-v / --verbose` — Enable debug logging

## Architecture

```
main.py (CLI)
  └─ DownloadOrchestrator (orchestrator.py)
       └─ QBittorrentDriver (client.py)
            └─ qbittorrent-api → qBittorrent Web API
```

- **models.py** — Pydantic v2 data contracts (`TaskStatus`, `AcquireRequest`)
- **config.py** — Environment variable loader via python-dotenv
- **client.py** — ABC `BaseClientDriver` + `QBittorrentDriver` implementation
- **orchestrator.py** — State machine: add → poll for activity → monitor to completion or remove on stall

## Tests

```bash
python -m pytest tests/ -v
```

All tests are fully mocked — no live qBittorrent instance required.
