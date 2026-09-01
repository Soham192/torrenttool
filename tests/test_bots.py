import pytest
from unittest.mock import MagicMock, patch


def _discord_is_authorized(interaction, allowed_user_id, channel_id):
    if channel_id and str(interaction.channel_id) == channel_id:
        return True
    if allowed_user_id and str(interaction.user.id) == allowed_user_id:
        return True
    if not allowed_user_id and not channel_id:
        return True
    return False


def _telegram_is_authorized(effective_user, allowed_user_id):
    if effective_user is None:
        return False
    if not allowed_user_id:
        return True
    return str(effective_user.id) == allowed_user_id


class TestDiscordAuth:
    def _make_interaction(self, user_id=123, channel_id=456):
        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.channel_id = channel_id
        return interaction

    def test_open_when_no_restrictions(self):
        i = self._make_interaction()
        assert _discord_is_authorized(i, "", "") is True

    def test_allowed_by_user_id(self):
        i = self._make_interaction(user_id=999)
        assert _discord_is_authorized(i, "999", "") is True

    def test_denied_by_user_id(self):
        i = self._make_interaction(user_id=111)
        assert _discord_is_authorized(i, "999", "") is False

    def test_allowed_by_channel_id(self):
        i = self._make_interaction(channel_id=456)
        assert _discord_is_authorized(i, "", "456") is True

    def test_denied_by_channel_id(self):
        i = self._make_interaction(channel_id=789)
        assert _discord_is_authorized(i, "", "456") is False

    def test_channel_takes_priority(self):
        i = self._make_interaction(user_id=111, channel_id=456)
        assert _discord_is_authorized(i, "999", "456") is True


class TestTelegramAuth:
    def test_open_when_no_restriction(self):
        user = MagicMock()
        user.id = 123
        assert _telegram_is_authorized(user, "") is True

    def test_allowed_user(self):
        user = MagicMock()
        user.id = 999
        assert _telegram_is_authorized(user, "999") is True

    def test_denied_user(self):
        user = MagicMock()
        user.id = 111
        assert _telegram_is_authorized(user, "999") is False

    def test_null_user_denied(self):
        assert _telegram_is_authorized(None, "") is False

    def test_null_user_denied_with_restriction(self):
        assert _telegram_is_authorized(None, "999") is False


class TestBotCommonUserTag:
    def test_telegram_tag(self):
        from bot_common import user_tag
        assert user_tag("tg", 12345) == "user:tg_12345"

    def test_discord_tag(self):
        from bot_common import user_tag
        assert user_tag("dc", 99999) == "user:dc_99999"


class TestBotCommonFormatters:
    def test_format_size_mb(self):
        from bot_common import format_size
        assert format_size(500 * 1024 * 1024) == "500.0 MB"

    def test_format_size_gb(self):
        from bot_common import format_size
        assert format_size(2 * 1024 ** 3) == "2.00 GB"

    def test_format_speed_kb(self):
        from bot_common import format_speed
        assert format_speed(500 * 1024) == "500 KB/s"

    def test_format_speed_mb(self):
        from bot_common import format_speed
        assert format_speed(2 * 1024 * 1024) == "2.0 MB/s"


class TestBotCommonSingleton:
    @patch("bot_common.QBitSearchProvider")
    @patch("bot_common.QBittorrentDriver")
    def test_returns_same_instance(self, mock_driver_cls, mock_search_cls):
        import bot_common
        bot_common._driver = None
        bot_common._orchestrator = None

        d1, o1 = bot_common.get_pipeline()
        d2, o2 = bot_common.get_pipeline()

        assert d1 is d2
        assert o1 is o2
        mock_driver_cls.assert_called_once()

        bot_common._driver = None
        bot_common._orchestrator = None


class TestProgressMilestone:
    def test_fires_at_25_boundaries(self):
        milestones_hit = []
        last = [0]

        def check_milestone(progress: float):
            pct = int(progress * 100)
            milestone = (pct // 25) * 25
            if milestone > last[0]:
                last[0] = milestone
                milestones_hit.append(milestone)

        for p in [0.0, 0.05, 0.10, 0.20, 0.24, 0.25, 0.30, 0.50, 0.74, 0.75, 0.99, 1.0]:
            check_milestone(p)

        assert milestones_hit == [25, 50, 75, 100]

    def test_no_duplicate_milestones(self):
        milestones_hit = []
        last = [0]

        def check_milestone(progress: float):
            pct = int(progress * 100)
            milestone = (pct // 25) * 25
            if milestone > last[0]:
                last[0] = milestone
                milestones_hit.append(milestone)

        for p in [0.25, 0.26, 0.27, 0.25]:
            check_milestone(p)

        assert milestones_hit == [25]
