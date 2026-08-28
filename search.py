import logging
import time
from abc import ABC, abstractmethod

import qbittorrentapi

from models import SearchQuery, SearchResult

logger = logging.getLogger(__name__)


class SearchJobError(Exception):
    pass


class SearchTimeoutError(Exception):
    pass


class BaseSearchProvider(ABC):
    @abstractmethod
    def search(self, query: SearchQuery) -> list[SearchResult]:
        ...


class QBitSearchProvider(BaseSearchProvider):
    def __init__(self, client: qbittorrentapi.Client):
        self._client = client

    def search(
        self,
        query: SearchQuery,
        timeout: int = 60,
        poll_interval: int = 2,
    ) -> list[SearchResult]:
        try:
            job = self._client.search_start(
                pattern=query.query,
                plugins="enabled",
                category=query.category,
            )
        except qbittorrentapi.APIError as exc:
            raise SearchJobError(f"Failed to start search: {exc}") from exc

        job_id = job["id"]
        logger.info("Search started (job %s) for '%s'", job_id, query.query)

        elapsed = 0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval
            try:
                status = self._client.search_status(search_id=job_id)
            except qbittorrentapi.APIError as exc:
                raise SearchJobError(f"Failed to poll search status: {exc}") from exc

            if isinstance(status, list):
                status = status[0] if status else {}
            if status.get("status") == "Stopped":
                logger.info("Search job %s completed", job_id)
                break
        else:
            try:
                self._client.search_delete(search_id=job_id)
            except qbittorrentapi.APIError:
                pass
            raise SearchTimeoutError(
                f"Search timed out after {timeout}s for '{query.query}'"
            )

        try:
            raw_results = self._client.search_results(search_id=job_id)
        except qbittorrentapi.APIError as exc:
            raise SearchJobError(f"Failed to fetch search results: {exc}") from exc
        finally:
            try:
                self._client.search_delete(search_id=job_id)
            except qbittorrentapi.APIError:
                pass

        results_list = raw_results
        if isinstance(raw_results, dict):
            results_list = raw_results.get("results", [])

        results = []
        for r in results_list:
            sr = SearchResult(
                title=r.get("fileName", ""),
                download_url=r.get("fileUrl", ""),
                size_bytes=max(0, r.get("fileSize", 0)),
                seeders=max(0, r.get("nbSeeders", 0)),
                indexer=r.get("siteUrl", "qBitPlugin"),
            )
            if sr.seeders >= query.min_seeders:
                results.append(sr)

        results.sort(key=lambda r: r.seeders, reverse=True)
        return results[: query.max_results]
