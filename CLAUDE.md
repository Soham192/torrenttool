# qbit_pipeline

## Project layout
All source code lives in `qbit_pipeline/`. Tests in `qbit_pipeline/tests/`.

## Commands
```bash
# activate venv (required before any python command)
source qbit_pipeline/.venv/bin/activate

# run tests
python -m pytest qbit_pipeline/tests/ -q

# start streamlit dashboard
cd qbit_pipeline && streamlit run app.py --server.headless true

# start qbittorrent (must be running for app to work)
qbittorrent-nox --webui-port=8080

# docker deploy
cd qbit_pipeline && docker compose up -d
```

## Conventions
- All qbittorrent-api exceptions must be wrapped in custom types (QBitAuthError, TaskAddError, QBitClientError, SearchJobError, SearchTimeoutError) — never let raw API exceptions leak.
- qbittorrent-api returns wrapper objects (SearchStatusesList, TorrentDictionary, etc.), not plain dicts — always handle both `.get()` and `getattr()` access patterns.
- `import time` must be at module top level (not inside functions) so tests can patch it.
- Orchestrator uses `time.sleep()` poll loops — no busy-waiting.
- Bot frontends (Telegram, Discord) run blocking pipeline work in `asyncio.to_thread()`.
- Discord bot uses milestone-only message edits (ack + completion) — no progress-bar polling that triggers HTTP 429.
- Per-user isolation via qBittorrent tags (`user:<username>`).

## Style
- Pydantic v2 models with field validation constraints.
- ABC base classes for drivers and providers.
- Logging module throughout, no print statements.
