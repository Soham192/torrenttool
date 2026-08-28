from unittest.mock import MagicMock, patch
import pytest
import qbittorrentapi
from search import QBitSearchProvider, SearchJobError, SearchTimeoutError
from models import SearchQuery


@pytest.fixture
def mock_client():
    return MagicMock(spec=qbittorrentapi.Client)


@pytest.fixture
def provider(mock_client):
    return QBitSearchProvider(mock_client)


RAW_RESULTS = [
    {"fileName": "Torrent A", "fileUrl": "magnet:?a", "fileSize": 1000, "nbSeeders": 50, "siteUrl": "indexer1"},
    {"fileName": "Torrent B", "fileUrl": "magnet:?b", "fileSize": 2000, "nbSeeders": 10, "siteUrl": "indexer2"},
    {"fileName": "Torrent C", "fileUrl": "magnet:?c", "fileSize": 500, "nbSeeders": 100, "siteUrl": "indexer3"},
    {"fileName": "Dead Torrent", "fileUrl": "magnet:?d", "fileSize": 300, "nbSeeders": 0, "siteUrl": "indexer4"},
]


@patch("search.time.sleep")
class TestSearchLifecycle:
    def test_full_lifecycle(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 42}
        mock_client.search_status.return_value = [{"status": "Stopped"}]
        mock_client.search_results.return_value = {"results": RAW_RESULTS}

        query = SearchQuery(query="test", min_seeders=1)
        results = provider.search(query)

        mock_client.search_start.assert_called_once_with(
            pattern="test", plugins="enabled", category="all",
        )
        mock_client.search_results.assert_called_once_with(search_id=42)
        mock_client.search_delete.assert_called_once_with(search_id=42)
        assert len(results) == 3

    def test_polling_until_stopped(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 7}
        mock_client.search_status.side_effect = [
            [{"status": "Running"}],
            [{"status": "Running"}],
            [{"status": "Stopped"}],
        ]
        mock_client.search_results.return_value = {"results": RAW_RESULTS[:1]}

        query = SearchQuery(query="poll test")
        results = provider.search(query, timeout=20, poll_interval=2)

        assert mock_client.search_status.call_count == 3
        assert mock_sleep.call_count == 3
        assert len(results) == 1


@patch("search.time.sleep")
class TestSeedFiltering:
    def test_filters_below_min_seeders(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.return_value = [{"status": "Stopped"}]
        mock_client.search_results.return_value = {"results": RAW_RESULTS}

        query = SearchQuery(query="test", min_seeders=15)
        results = provider.search(query)

        assert len(results) == 2
        assert all(r.seeders >= 15 for r in results)

    def test_zero_seeders_excluded_with_default_min(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.return_value = [{"status": "Stopped"}]
        mock_client.search_results.return_value = {"results": RAW_RESULTS}

        query = SearchQuery(query="test")
        results = provider.search(query)

        assert all(r.seeders >= 1 for r in results)
        titles = [r.title for r in results]
        assert "Dead Torrent" not in titles


@patch("search.time.sleep")
class TestSortOrder:
    def test_sorted_by_seeders_descending(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.return_value = [{"status": "Stopped"}]
        mock_client.search_results.return_value = {"results": RAW_RESULTS}

        query = SearchQuery(query="test", min_seeders=1)
        results = provider.search(query)

        seeders = [r.seeders for r in results]
        assert seeders == sorted(seeders, reverse=True)
        assert results[0].seeders == 100
        assert results[-1].seeders == 10


@patch("search.time.sleep")
class TestMaxResults:
    def test_respects_max_results(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.return_value = [{"status": "Stopped"}]
        mock_client.search_results.return_value = {"results": RAW_RESULTS}

        query = SearchQuery(query="test", min_seeders=1, max_results=2)
        results = provider.search(query)

        assert len(results) == 2


@patch("search.time.sleep")
class TestExceptionWrapping:
    def test_start_api_error(self, mock_sleep, provider, mock_client):
        mock_client.search_start.side_effect = qbittorrentapi.APIError("fail")
        with pytest.raises(SearchJobError, match="Failed to start search"):
            provider.search(SearchQuery(query="test"))

    def test_status_api_error(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.side_effect = qbittorrentapi.APIError("fail")
        with pytest.raises(SearchJobError, match="Failed to poll search status"):
            provider.search(SearchQuery(query="test"))

    def test_results_api_error(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.return_value = [{"status": "Stopped"}]
        mock_client.search_results.side_effect = qbittorrentapi.APIError("fail")
        with pytest.raises(SearchJobError, match="Failed to fetch search results"):
            provider.search(SearchQuery(query="test"))
        mock_client.search_delete.assert_called_once_with(search_id=1)


@patch("search.time.sleep")
class TestSearchTimeout:
    def test_raises_on_timeout(self, mock_sleep, provider, mock_client):
        mock_client.search_start.return_value = {"id": 1}
        mock_client.search_status.return_value = [{"status": "Running"}]

        with pytest.raises(SearchTimeoutError):
            provider.search(SearchQuery(query="test"), timeout=4, poll_interval=2)

        mock_client.search_delete.assert_called_once_with(search_id=1)
