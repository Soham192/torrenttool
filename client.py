import re
import time
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import parse_qs, urlparse

import qbittorrentapi

from models import TaskStatus


class QBitAuthError(Exception):
    pass


class TaskAddError(Exception):
    pass


class QBitClientError(Exception):
    pass


class BaseClientDriver(ABC):
    @abstractmethod
    def add_task(self, url: str, save_path: Optional[str] = None, tags: Optional[str] = None) -> str:
        ...

    @abstractmethod
    def get_status(self, torrent_hash: str) -> Optional[TaskStatus]:
        ...

    @abstractmethod
    def remove_task(self, torrent_hash: str, delete_files: bool = True) -> bool:
        ...

    @abstractmethod
    def is_active(self, torrent_hash: str) -> bool:
        ...


_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{32}$")


def _parse_hash_from_magnet(magnet_url: str) -> Optional[str]:
    parsed = urlparse(magnet_url)
    xt_values = parse_qs(parsed.query).get("xt", [])
    for xt in xt_values:
        if xt.lower().startswith("urn:btih:"):
            h = xt[len("urn:btih:"):]
            if _HASH_RE.match(h):
                return h.lower()
    return None


_ACTIVE_STATES = {"downloading", "stalledDL", "forcedDL", "metaDL", "allocating"}


class QBittorrentDriver(BaseClientDriver):
    def __init__(self, host: str, port: int, username: str, password: str):
        try:
            self._client = qbittorrentapi.Client(
                host=host, port=port, username=username, password=password,
            )
            self._client.auth_log_in()
        except qbittorrentapi.LoginFailed as exc:
            raise QBitAuthError(f"Login failed for {username}@{host}:{port}") from exc
        except Exception as exc:
            raise QBitClientError(f"Connection error: {exc}") from exc

    def add_task(self, url: str, save_path: Optional[str] = None, tags: Optional[str] = None) -> str:
        info_hash = _parse_hash_from_magnet(url)

        try:
            result = self._client.torrents_add(urls=url, save_path=save_path)
            if result == "Fails.":
                raise TaskAddError(f"qBittorrent rejected the torrent: {url}")
        except qbittorrentapi.APIError as exc:
            raise TaskAddError(f"Failed to add torrent: {exc}") from exc

        if info_hash:
            if tags:
                try:
                    self._client.torrents_add_tags(tags=tags, torrent_hashes=info_hash)
                except qbittorrentapi.APIError:
                    pass
            return info_hash

        for _ in range(10):
            time.sleep(0.5)
            try:
                torrents = self._client.torrents_info(sort="added_on", reverse=True, limit=5)
            except qbittorrentapi.APIError as exc:
                raise QBitClientError(f"Failed to list torrents: {exc}") from exc
            for t in torrents:
                if url in (t.get("magnet_uri", ""), t.get("content_path", "")):
                    resolved = t["hash"].lower()
                    if tags:
                        try:
                            self._client.torrents_add_tags(tags=tags, torrent_hashes=resolved)
                        except qbittorrentapi.APIError:
                            pass
                    return resolved
            if torrents:
                resolved = torrents[0]["hash"].lower()
                if tags:
                    try:
                        self._client.torrents_add_tags(tags=tags, torrent_hashes=resolved)
                    except qbittorrentapi.APIError:
                        pass
                return resolved

        raise TaskAddError(f"Could not resolve hash for added torrent: {url}")

    def get_status(self, torrent_hash: str) -> Optional[TaskStatus]:
        try:
            torrents = self._client.torrents_info(torrent_hashes=torrent_hash)
        except qbittorrentapi.APIError as exc:
            raise QBitClientError(f"Failed to query torrent status: {exc}") from exc

        if not torrents:
            return None

        t = torrents[0]
        return TaskStatus(
            task_id=t["hash"],
            name=t.get("name", ""),
            progress=t.get("progress", 0.0),
            download_speed=t.get("dlspeed", 0),
            state=t.get("state", "unknown"),
            eta_seconds=t.get("eta", 0),
        )

    def remove_task(self, torrent_hash: str, delete_files: bool = True) -> bool:
        try:
            existing = self._client.torrents_info(torrent_hashes=torrent_hash)
        except qbittorrentapi.APIError as exc:
            raise QBitClientError(f"Failed to check torrent: {exc}") from exc

        if not existing:
            return False

        try:
            self._client.torrents_delete(
                delete_files=delete_files, torrent_hashes=torrent_hash,
            )
        except qbittorrentapi.APIError as exc:
            raise QBitClientError(f"Failed to delete torrent: {exc}") from exc

        return True

    def is_active(self, torrent_hash: str) -> bool:
        status = self.get_status(torrent_hash)
        if status is None:
            return False
        if status.download_speed > 0:
            return True
        return status.state in _ACTIVE_STATES
