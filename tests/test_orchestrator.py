from unittest.mock import MagicMock, patch, call
import pytest
from client import TaskAddError
from orchestrator import DownloadOrchestrator
from models import AcquireRequest, TaskStatus


HASH = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
REQUEST = AcquireRequest(source_url="magnet:?xt=urn:btih:" + HASH)


def _make_status(progress=0.0, download_speed=0, state="downloading"):
    return TaskStatus(
        task_id=HASH,
        name="Test",
        progress=progress,
        download_speed=download_speed,
        state=state,
        eta_seconds=60,
    )


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.add_task.return_value = HASH
    return driver


@patch("orchestrator.time.sleep")
class TestImmediateActivity:
    def test_returns_true_on_immediate_progress(self, mock_sleep, mock_driver):
        mock_driver.get_status.side_effect = [
            _make_status(progress=0.1, download_speed=1000),
            _make_status(progress=1.0, state="uploading"),
        ]
        orch = DownloadOrchestrator(mock_driver)
        assert orch.acquire(REQUEST, stall_timeout=10, poll_interval=2) is True
        mock_driver.remove_task.assert_not_called()

    def test_returns_true_on_speed_only(self, mock_sleep, mock_driver):
        mock_driver.get_status.side_effect = [
            _make_status(progress=0.0, download_speed=5000),
            _make_status(progress=0.5, download_speed=5000),
            _make_status(progress=1.0, state="pausedUP"),
        ]
        orch = DownloadOrchestrator(mock_driver)
        assert orch.acquire(REQUEST, stall_timeout=10, poll_interval=2) is True


@patch("orchestrator.time.sleep")
class TestStalledTimeout:
    def test_removes_and_returns_false(self, mock_sleep, mock_driver):
        mock_driver.get_status.return_value = _make_status(
            progress=0.0, download_speed=0,
        )
        orch = DownloadOrchestrator(mock_driver)
        result = orch.acquire(REQUEST, stall_timeout=6, poll_interval=2)
        assert result is False
        mock_driver.remove_task.assert_called_once_with(HASH, delete_files=True)

    def test_sleep_called_between_polls(self, mock_sleep, mock_driver):
        mock_driver.get_status.return_value = _make_status(
            progress=0.0, download_speed=0,
        )
        orch = DownloadOrchestrator(mock_driver)
        orch.acquire(REQUEST, stall_timeout=4, poll_interval=2)
        assert mock_sleep.call_count >= 2
        mock_sleep.assert_any_call(2)


@patch("orchestrator.time.sleep")
class TestCompletionDetection:
    def test_progress_reaches_one(self, mock_sleep, mock_driver):
        mock_driver.get_status.side_effect = [
            _make_status(progress=0.3, download_speed=1000),
            _make_status(progress=0.6, download_speed=800),
            _make_status(progress=1.0, state="uploading"),
        ]
        orch = DownloadOrchestrator(mock_driver)
        assert orch.acquire(REQUEST, stall_timeout=10, poll_interval=1) is True

    def test_state_indicates_completion(self, mock_sleep, mock_driver):
        mock_driver.get_status.side_effect = [
            _make_status(progress=0.5, download_speed=1000),
            _make_status(progress=0.99, download_speed=100, state="stalledUP"),
        ]
        orch = DownloadOrchestrator(mock_driver)
        assert orch.acquire(REQUEST, stall_timeout=10, poll_interval=1) is True


@patch("orchestrator.time.sleep")
class TestProgressCallback:
    def test_callback_invoked(self, mock_sleep, mock_driver):
        statuses = [
            _make_status(progress=0.2, download_speed=1000),
            _make_status(progress=1.0, state="uploading"),
        ]
        mock_driver.get_status.side_effect = statuses
        callback = MagicMock()
        orch = DownloadOrchestrator(mock_driver)
        orch.acquire(REQUEST, stall_timeout=10, poll_interval=1, progress_callback=callback)
        assert callback.call_count == 2


@patch("orchestrator.time.sleep")
class TestTorrentDisappears:
    def test_returns_false_during_stall_check(self, mock_sleep, mock_driver):
        mock_driver.get_status.return_value = None
        orch = DownloadOrchestrator(mock_driver)
        assert orch.acquire(REQUEST, stall_timeout=10, poll_interval=2) is False

    def test_returns_false_during_download(self, mock_sleep, mock_driver):
        mock_driver.get_status.side_effect = [
            _make_status(progress=0.5, download_speed=1000),
            None,
        ]
        orch = DownloadOrchestrator(mock_driver)
        assert orch.acquire(REQUEST, stall_timeout=10, poll_interval=1) is False


@patch("orchestrator.time.sleep")
class TestSavePathPassthrough:
    def test_save_path_forwarded_to_driver(self, mock_sleep, mock_driver):
        request = AcquireRequest(
            source_url="magnet:?xt=urn:btih:" + HASH,
            save_path="/custom/path",
        )
        mock_driver.get_status.side_effect = [
            _make_status(progress=0.5, download_speed=1000),
            _make_status(progress=1.0, state="uploading"),
        ]
        orch = DownloadOrchestrator(mock_driver)
        orch.acquire(request, stall_timeout=10, poll_interval=1)
        mock_driver.add_task.assert_called_once_with(
            "magnet:?xt=urn:btih:" + HASH, "/custom/path",
        )


@patch("orchestrator.time.sleep")
class TestAddTaskFailure:
    def test_exception_propagates(self, mock_sleep, mock_driver):
        mock_driver.add_task.side_effect = TaskAddError("rejected")
        orch = DownloadOrchestrator(mock_driver)
        with pytest.raises(TaskAddError):
            orch.acquire(REQUEST, stall_timeout=10, poll_interval=1)
