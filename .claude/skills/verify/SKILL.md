# Verify

After any code change, run this checklist before reporting done:

1. `python -m pytest qbit_pipeline/tests/ -q` — all tests must pass
2. If search.py or client.py changed: verify qbittorrent-api wrapper objects are handled (not just plain dicts)
3. If app.py changed: restart streamlit and confirm HTTP 200 on localhost:8501
4. If docker files changed: `docker compose config` to validate syntax
