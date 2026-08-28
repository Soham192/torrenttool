import pytest
from pydantic import ValidationError
from models import TaskStatus, AcquireRequest, SearchQuery, SearchResult


class TestTaskStatus:
    def _valid_kwargs(self, **overrides):
        defaults = {
            "task_id": "abc123",
            "name": "Test Torrent",
            "progress": 0.5,
            "download_speed": 1024,
            "state": "downloading",
            "eta_seconds": 300,
        }
        defaults.update(overrides)
        return defaults

    def test_valid_creation(self):
        ts = TaskStatus(**self._valid_kwargs())
        assert ts.task_id == "abc123"
        assert ts.progress == 0.5

    def test_progress_at_boundaries(self):
        TaskStatus(**self._valid_kwargs(progress=0.0))
        TaskStatus(**self._valid_kwargs(progress=1.0))

    def test_progress_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            TaskStatus(**self._valid_kwargs(progress=-0.1))

    def test_progress_above_one_rejected(self):
        with pytest.raises(ValidationError):
            TaskStatus(**self._valid_kwargs(progress=1.1))

    def test_negative_download_speed_rejected(self):
        with pytest.raises(ValidationError):
            TaskStatus(**self._valid_kwargs(download_speed=-1))

    def test_zero_download_speed_accepted(self):
        ts = TaskStatus(**self._valid_kwargs(download_speed=0))
        assert ts.download_speed == 0

    def test_serialization_round_trip(self):
        ts = TaskStatus(**self._valid_kwargs())
        data = ts.model_dump()
        ts2 = TaskStatus(**data)
        assert ts == ts2

    def test_json_round_trip(self):
        ts = TaskStatus(**self._valid_kwargs())
        json_str = ts.model_dump_json()
        ts2 = TaskStatus.model_validate_json(json_str)
        assert ts == ts2


class TestAcquireRequest:
    def test_minimal(self):
        req = AcquireRequest(source_url="magnet:?xt=urn:btih:abc123")
        assert req.source_url == "magnet:?xt=urn:btih:abc123"
        assert req.display_name is None
        assert req.save_path is None

    def test_full(self):
        req = AcquireRequest(
            source_url="magnet:?xt=urn:btih:abc123",
            display_name="My Torrent",
            save_path="/downloads",
        )
        assert req.display_name == "My Torrent"
        assert req.save_path == "/downloads"

    def test_serialization_round_trip(self):
        req = AcquireRequest(
            source_url="magnet:?xt=urn:btih:abc123",
            display_name="My Torrent",
            save_path="/downloads",
        )
        data = req.model_dump()
        req2 = AcquireRequest(**data)
        assert req == req2


class TestTaskStatusRequiredFields:
    def test_missing_task_id_rejected(self):
        with pytest.raises(ValidationError):
            TaskStatus(
                name="Test", progress=0.5, download_speed=0,
                state="downloading", eta_seconds=0,
            )

    def test_missing_name_rejected(self):
        with pytest.raises(ValidationError):
            TaskStatus(
                task_id="abc", progress=0.5, download_speed=0,
                state="downloading", eta_seconds=0,
            )

    def test_missing_state_rejected(self):
        with pytest.raises(ValidationError):
            TaskStatus(
                task_id="abc", name="Test", progress=0.5,
                download_speed=0, eta_seconds=0,
            )


class TestSearchQuery:
    def test_defaults(self):
        q = SearchQuery(query="linux iso")
        assert q.query == "linux iso"
        assert q.category == "all"
        assert q.min_seeders == 1
        assert q.max_results == 20

    def test_custom_values(self):
        q = SearchQuery(query="test", category="music", min_seeders=5, max_results=10)
        assert q.category == "music"
        assert q.min_seeders == 5
        assert q.max_results == 10


class TestSearchResult:
    def test_defaults(self):
        r = SearchResult(title="Test", download_url="magnet:?a")
        assert r.size_bytes == 0
        assert r.seeders == 0
        assert r.indexer == "qBitPlugin"
        assert r.info_hash is None

    def test_negative_size_rejected(self):
        with pytest.raises(ValidationError):
            SearchResult(title="Test", download_url="magnet:?a", size_bytes=-1)

    def test_negative_seeders_rejected(self):
        with pytest.raises(ValidationError):
            SearchResult(title="Test", download_url="magnet:?a", seeders=-1)

    def test_serialization_round_trip(self):
        r = SearchResult(
            title="Test", download_url="magnet:?a",
            size_bytes=1024, seeders=50, indexer="idx",
        )
        data = r.model_dump()
        r2 = SearchResult(**data)
        assert r == r2
