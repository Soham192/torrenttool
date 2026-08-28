import logging
import time
from typing import Callable, Optional

from client import BaseClientDriver
from models import AcquireRequest, TaskStatus

logger = logging.getLogger(__name__)


class DownloadOrchestrator:
    def __init__(self, driver: BaseClientDriver):
        self._driver = driver

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

        elapsed = 0
        active = False
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
                logger.info("Activity detected for %s (progress=%.2f, speed=%d)",
                            task_hash, status.progress, status.download_speed)
                active = True
                break

        if not active:
            logger.warning("Torrent %s stalled after %ds, removing", task_hash, stall_timeout)
            self._driver.remove_task(task_hash, delete_files=True)
            return False

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
