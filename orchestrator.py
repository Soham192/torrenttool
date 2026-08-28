import logging
import time
from typing import Callable, Optional

from client import BaseClientDriver
from models import AcquireRequest, SearchQuery, TaskStatus
from search import BaseSearchProvider

logger = logging.getLogger(__name__)


class DownloadOrchestrator:
    def __init__(
        self,
        driver: BaseClientDriver,
        search_provider: Optional[BaseSearchProvider] = None,
    ):
        self._driver = driver
        self._search_provider = search_provider

    def acquire(
        self,
        request: AcquireRequest,
        stall_timeout: int = 30,
        poll_interval: int = 2,
        progress_callback: Optional[Callable[[TaskStatus], None]] = None,
    ) -> bool:
        logger.info("Adding torrent: %s", request.source_url)
        task_hash = self._driver.add_task(request.source_url, request.save_path)
        logger.info("Torrent added with hash: %s", task_hash)

        active = self._wait_for_activity(task_hash, stall_timeout, poll_interval, progress_callback)

        if not active:
            logger.warning("Torrent %s stalled after %ds, removing", task_hash, stall_timeout)
            self._driver.remove_task(task_hash, delete_files=True)
            return False

        return self._monitor_to_completion(task_hash, poll_interval, progress_callback)

    def acquire_from_search(
        self,
        query: SearchQuery,
        save_path: Optional[str] = None,
        stall_timeout: int = 30,
        poll_interval: int = 2,
        progress_callback: Optional[Callable[[TaskStatus], None]] = None,
    ) -> bool:
        if self._search_provider is None:
            raise RuntimeError("No search provider configured")

        logger.info("Searching for: '%s'", query.query)
        candidates = self._search_provider.search(query)
        logger.info("Found %d candidates", len(candidates))

        for i, candidate in enumerate(candidates):
            logger.info("Trying candidate %d/%d: %s", i + 1, len(candidates), candidate.title)
            task_hash = self._driver.add_task(candidate.download_url, save_path)
            logger.info("Added candidate with hash: %s", task_hash)

            active = self._wait_for_activity(task_hash, stall_timeout, poll_interval, progress_callback)

            if not active:
                logger.warning(
                    "Candidate %d/%d stalled (%s), removing and trying next",
                    i + 1, len(candidates), candidate.title,
                )
                self._driver.remove_task(task_hash, delete_files=True)
                continue

            result = self._monitor_to_completion(task_hash, poll_interval, progress_callback)
            if result:
                return True

        logger.warning("All %d candidates exhausted", len(candidates))
        return False

    def _wait_for_activity(
        self,
        task_hash: str,
        stall_timeout: int,
        poll_interval: int,
        progress_callback: Optional[Callable[[TaskStatus], None]] = None,
    ) -> bool:
        elapsed = 0
        while elapsed < stall_timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            status = self._driver.get_status(task_hash)
            if status is None:
                logger.warning("Torrent %s disappeared during stall check", task_hash)
                return False

            if progress_callback:
                progress_callback(status)

            if status.progress > 0 or status.download_speed > 0:
                logger.info(
                    "Activity detected for %s (progress=%.2f, speed=%d)",
                    task_hash, status.progress, status.download_speed,
                )
                return True

        return False

    def _monitor_to_completion(
        self,
        task_hash: str,
        poll_interval: int,
        progress_callback: Optional[Callable[[TaskStatus], None]] = None,
    ) -> bool:
        while True:
            time.sleep(poll_interval)
            status = self._driver.get_status(task_hash)
            if status is None:
                logger.warning("Torrent %s disappeared during download", task_hash)
                return False

            if progress_callback:
                progress_callback(status)

            if status.progress >= 1.0 or status.state in ("uploading", "pausedUP", "stalledUP"):
                logger.info("Torrent %s completed", task_hash)
                return True
