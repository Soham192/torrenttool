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

            if not isinstance(status, dict):
                try:
                    status = status[0] if len(status) > 0 else {}
                except (TypeError, KeyError):
                    status = {}
            if hasattr(status, "get"):
                stopped = status.get("status") == "Stopped"
            else:
                stopped = getattr(status, "status", None) == "Stopped"
            if stopped:
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

        if isinstance(raw_results, dict):
            results_list = raw_results.get("results", [])
        elif hasattr(raw_results, "results"):
            results_list = raw_results.results
        else:
            results_list = raw_results

        def _get(obj, key, default=None):
            if hasattr(obj, "get"):
                return obj.get(key, default)
            return getattr(obj, key, default)

        results = []
        for r in results_list:
            sr = SearchResult(
                title=_get(r, "fileName", ""),
                download_url=_get(r, "fileUrl", ""),
                size_bytes=max(0, _get(r, "fileSize", 0)),
                seeders=max(0, _get(r, "nbSeeders", 0)),
                indexer=_get(r, "siteUrl", "qBitPlugin"),
            )
            if sr.seeders >= query.min_seeders:
                results.append(sr)

        results.sort(key=lambda r: r.seeders, reverse=True)
        return results[: query.max_results]
