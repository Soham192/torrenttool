import logging
from typing import Optional

import config
from client import QBittorrentDriver
from orchestrator import DownloadOrchestrator
from search import QBitSearchProvider

logger = logging.getLogger(__name__)

_driver: Optional[QBittorrentDriver] = None
_orchestrator: Optional[DownloadOrchestrator] = None


def get_pipeline() -> tuple[QBittorrentDriver, DownloadOrchestrator]:
    global _driver, _orchestrator
    if _driver is None:
        _driver = QBittorrentDriver(
            host=config.QBIT_HOST,
            port=config.QBIT_PORT,
            username=config.QBIT_USERNAME,
            password=config.QBIT_PASSWORD,
        )
        search_provider = QBitSearchProvider(_driver._client)
        _orchestrator = DownloadOrchestrator(_driver, search_provider=search_provider)
    return _driver, _orchestrator


def user_tag(platform: str, user_id) -> str:
    return f"user:{platform}_{user_id}"


def ensure_tag(driver: QBittorrentDriver, tag: str):
    try:
        existing = driver._client.torrents_tags()
        if tag not in existing:
            driver._client.torrents_create_tags(tags=tag)
    except Exception:
        pass


def get_user_torrents(driver: QBittorrentDriver, tag: str) -> list:
    try:
        all_torrents = driver._client.torrents_info()
        return [t for t in all_torrents if tag in (t.get("tags", "") or "").split(", ")]
    except Exception:
        return []


def format_size(size_bytes: int) -> str:
    gb = size_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.1f} MB"


def format_speed(speed_bytes: int) -> str:
    kb = speed_bytes / 1024
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB/s"
    return f"{kb:.0f} KB/s"
