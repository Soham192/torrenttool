from unittest.mock import MagicMock, patch
import pytest
from client import (
    QBittorrentDriver,
    QBitAuthError,
    QBitClientError,
    TaskAddError,
    _parse_hash_from_magnet,
)
from models import TaskStatus


MAGNET = "magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709&dn=Test"
HASH = "da39a3ee5e6b4b0d3255bfef95601890afd80709"


@pytest.fixture
def mock_client():
    with patch("client.qbittorrentapi.Client") as MockClient:
        instance = MockClient.return_value
        instance.auth_log_in.return_value = None
        yield instance


@pytest.fixture
def driver(mock_client):
    return QBittorrentDriver(
        host="localhost", port=8080, username="admin", password="pass",
    )


class TestParseHash:
    def test_valid_magnet(self):
        assert _parse_hash_from_magnet(MAGNET) == HASH

    def test_no_xt_param(self):
        assert _parse_hash_from_magnet("magnet:?dn=Test") is None

    def test_non_btih_xt(self):
        assert _parse_hash_from_magnet("magnet:?xt=urn:sha1:abc") is None

    def test_uppercase_hash_normalized(self):
        upper_magnet = "magnet:?xt=urn:btih:DA39A3EE5E6B4B0D3255BFEF95601890AFD80709"
        assert _parse_hash_from_magnet(upper_magnet) == HASH

    def test_plain_url_returns_none(self):
        assert _parse_hash_from_magnet("https://example.com/file.torrent") is None


class TestQBittorrentDriverAuth:
    def test_login_failure(self):
        with patch("client.qbittorrentapi.Client") as MockClient:
            import qbittorrentapi
            MockClient.return_value.auth_log_in.side_effect = (
                qbittorrentapi.LoginFailed
            )
            with pytest.raises(QBitAuthError):
                QBittorrentDriver(
                    host="localhost", port=8080,
                    username="bad", password="bad",
                )

    def test_generic_connection_error_wraps_in_client_error(self):
        with patch("client.qbittorrentapi.Client") as MockClient:
            MockClient.return_value.auth_log_in.side_effect = ConnectionRefusedError(
                "Connection refused"
            )
            with pytest.raises(QBitClientError):
                QBittorrentDriver(
                    host="badhost", port=9999,
                    username="admin", password="pass",
                )


class TestAddTask:
    def test_add_magnet_returns_correct_hash(self, driver, mock_client):
        mock_client.torrents_add.return_value = "Ok."
        result = driver.add_task(MAGNET)
        assert result == HASH
        mock_client.torrents_add.assert_called_once_with(
            urls=MAGNET, save_path=None,
        )

    def test_add_failure_raises(self, driver, mock_client):
        mock_client.torrents_add.return_value = "Fails."
        with pytest.raises(TaskAddError):
            driver.add_task(MAGNET)

    def test_add_api_error_wraps_in_task_add_error(self, driver, mock_client):
        import qbittorrentapi
        mock_client.torrents_add.side_effect = qbittorrentapi.APIError("server error")
        with pytest.raises(TaskAddError):
            driver.add_task(MAGNET)

    @patch("client.time.sleep")
    def test_add_torrent_url_resolves_hash_by_polling(self, mock_sleep, driver, mock_client):
        torrent_url = "https://example.com/test.torrent"
        mock_client.torrents_add.return_value = "Ok."
        mock_client.torrents_info.return_value = [
            {"hash": "abcd1234" * 5, "magnet_uri": "", "content_path": ""}
        ]
        result = driver.add_task(torrent_url)
        assert result == ("abcd1234" * 5).lower()

    def test_add_with_save_path(self, driver, mock_client):
        mock_client.torrents_add.return_value = "Ok."
        driver.add_task(MAGNET, save_path="/custom/path")
        mock_client.torrents_add.assert_called_once_with(
            urls=MAGNET, save_path="/custom/path",
        )


class TestGetStatus:
    def test_maps_response_correctly(self, driver, mock_client):
        mock_client.torrents_info.return_value = [
            {
                "hash": HASH,
                "name": "Test Torrent",
                "progress": 0.42,
                "dlspeed": 512000,
                "state": "downloading",
                "eta": 120,
            }
        ]
        status = driver.get_status(HASH)
        assert isinstance(status, TaskStatus)
        assert status.task_id == HASH
        assert status.name == "Test Torrent"
        assert status.progress == 0.42
        assert status.download_speed == 512000
        assert status.state == "downloading"
        assert status.eta_seconds == 120

    def test_returns_none_for_unknown_hash(self, driver, mock_client):
        mock_client.torrents_info.return_value = []
        assert driver.get_status("nonexistent") is None

    def test_get_status_api_error_wraps_in_client_error(self, driver, mock_client):
        import qbittorrentapi
        mock_client.torrents_info.side_effect = qbittorrentapi.APIError("timeout")
        with pytest.raises(QBitClientError):
            driver.get_status(HASH)


class TestRemoveTask:
    def test_returns_true_for_existing(self, driver, mock_client):
        mock_client.torrents_info.return_value = [{"hash": HASH}]
        assert driver.remove_task(HASH) is True
        mock_client.torrents_delete.assert_called_once()

    def test_returns_false_for_unknown(self, driver, mock_client):
        mock_client.torrents_info.return_value = []
        assert driver.remove_task("nonexistent") is False
        mock_client.torrents_delete.assert_not_called()

    def test_remove_without_deleting_files(self, driver, mock_client):
        mock_client.torrents_info.return_value = [{"hash": HASH}]
        assert driver.remove_task(HASH, delete_files=False) is True
        mock_client.torrents_delete.assert_called_once_with(
            delete_files=False, torrent_hashes=HASH,
        )

    def test_remove_api_error_wraps_in_client_error(self, driver, mock_client):
        import qbittorrentapi
        mock_client.torrents_info.return_value = [{"hash": HASH}]
        mock_client.torrents_delete.side_effect = qbittorrentapi.APIError("fail")
        with pytest.raises(QBitClientError):
            driver.remove_task(HASH)


class TestIsActive:
    @pytest.mark.parametrize(
        "state,dlspeed,expected",
        [
            ("downloading", 0, True),
            ("stalledDL", 0, True),
            ("pausedDL", 1000, True),
            ("pausedDL", 0, False),
            ("uploading", 0, False),
            ("forcedDL", 0, True),
        ],
    )
    def test_active_states(self, driver, mock_client, state, dlspeed, expected):
        mock_client.torrents_info.return_value = [
            {
                "hash": HASH,
                "name": "Test",
                "progress": 0.5,
                "dlspeed": dlspeed,
                "state": state,
                "eta": 60,
            }
        ]
        assert driver.is_active(HASH) is expected

    def test_unknown_hash_returns_false(self, driver, mock_client):
        mock_client.torrents_info.return_value = []
        assert driver.is_active("nonexistent") is False
