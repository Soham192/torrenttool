import re

import streamlit as st
import config
from client import QBittorrentDriver, QBitAuthError, QBitClientError
from models import SearchQuery
from search import QBitSearchProvider, SearchJobError, SearchTimeoutError

st.set_page_config(page_title="qbit_pipeline", layout="wide")


def _format_size(size_bytes: int) -> str:
    gb = size_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.1f} MB"


def _format_speed(speed_bytes: int) -> str:
    kb = speed_bytes / 1024
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB/s"
    return f"{kb:.0f} KB/s"


@st.cache_resource
def get_driver():
    return QBittorrentDriver(
        host=config.QBIT_HOST,
        port=config.QBIT_PORT,
        username=config.QBIT_USERNAME,
        password=config.QBIT_PASSWORD,
    )


def _ensure_tag(driver, tag: str):
    try:
        existing = driver._client.torrents_tags()
        if tag not in existing:
            driver._client.torrents_create_tags(tags=tag)
    except Exception:
        pass


if "username" not in st.session_state:
    st.title("qbit_pipeline")
    st.subheader("Enter a username to get started")
    name = st.text_input("Username", placeholder="e.g. john")
    if st.button("Continue", type="primary", disabled=not name):
        clean = re.sub(r"[^a-z0-9_]", "", name.strip().lower().replace(" ", "_"))
        if not clean:
            st.error("Username must contain at least one letter or number.")
            st.stop()
        st.session_state["username"] = clean
        st.rerun()
    st.stop()

username = st.session_state["username"]
user_tag = f"user:{username}"

st.title("qbit_pipeline")
st.caption(f"Logged in as **{username}**")

try:
    driver = get_driver()
except (QBitAuthError, QBitClientError) as exc:
    st.error(f"Failed to connect to qBittorrent: {exc}")
    st.stop()

_ensure_tag(driver, user_tag)
search_provider = QBitSearchProvider(driver._client)

st.header("Search")
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    query_text = st.text_input("Query", placeholder="e.g. Ubuntu 24.04")
with col2:
    category = st.selectbox("Category", ["all", "software", "movies", "tv", "music", "books"])
with col3:
    min_seeds = st.number_input("Min Seeders", min_value=0, value=1, step=1)

if st.button("Search", type="primary", disabled=not query_text):
    query = SearchQuery(query=query_text, category=category, min_seeders=min_seeds)
    with st.spinner("Searching..."):
        try:
            results = search_provider.search(query)
        except (SearchJobError, SearchTimeoutError) as exc:
            st.error(f"Search failed: {exc}")
            results = []
    st.session_state["results"] = results

if "results" in st.session_state and st.session_state["results"]:
    st.subheader(f"Results ({len(st.session_state['results'])})")
    for i, r in enumerate(st.session_state["results"]):
        with st.container():
            rc1, rc2, rc3, rc4 = st.columns([4, 1, 1, 1])
            rc1.write(f"**{r.title}**")
            rc2.write(f"{r.seeders} seeds")
            rc3.write(_format_size(r.size_bytes))
            if rc4.button("Download", key=f"dl_{i}"):
                try:
                    task_hash = driver.add_task(
                        r.download_url, config.DEFAULT_SAVE_PATH,
                    )
                    driver._client.torrents_add_tags(tags=user_tag, torrent_hashes=task_hash)
                    st.success(f"Added: {r.title} ({task_hash[:12]}...)")
                except Exception as exc:
                    st.error(f"Failed to add: {exc}")
elif "results" in st.session_state:
    st.info("No results found.")

st.header("My Downloads")

try:
    all_torrents = driver._client.torrents_info()
    torrents = [t for t in all_torrents if user_tag in (t.get("tags", "") or "").split(", ")]
except Exception:
    torrents = []

if not torrents:
    st.info("No active transfers.")
else:
    for t in torrents:
        name = t.get("name", "Unknown")
        progress = t.get("progress", 0.0)
        dlspeed = t.get("dlspeed", 0)
        state = t.get("state", "unknown")
        eta = t.get("eta", 0)

        with st.container():
            st.write(f"**{name}**")
            tc1, tc2, tc3 = st.columns([3, 1, 1])
            tc1.progress(min(progress, 1.0), text=f"{progress * 100:.1f}%")
            tc2.metric("Speed", _format_speed(dlspeed))
            eta_str = f"{eta}s" if eta < 8640000 else "--"
            tc3.metric("ETA", eta_str)
            st.caption(f"State: {state}")
            st.divider()

if st.sidebar.button("Logout"):
    del st.session_state["username"]
    st.rerun()
