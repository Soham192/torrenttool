import pytest
from unittest.mock import MagicMock


def _discord_is_authorized(ctx, allowed_user_id, channel_id):
    if channel_id and str(ctx.channel.id) == channel_id:
        return True
    if allowed_user_id and str(ctx.author.id) == allowed_user_id:
        return True
    if not allowed_user_id and not channel_id:
        return True
    return False


def _telegram_is_authorized(user_id, allowed_user_id):
    if not allowed_user_id:
        return True
    return str(user_id) == allowed_user_id


class TestDiscordAuth:
    def _make_ctx(self, author_id=123, channel_id=456):
        ctx = MagicMock()
        ctx.author.id = author_id
        ctx.channel.id = channel_id
        return ctx

    def test_open_when_no_restrictions(self):
        ctx = self._make_ctx()
        assert _discord_is_authorized(ctx, "", "") is True

    def test_allowed_by_user_id(self):
        ctx = self._make_ctx(author_id=999)
        assert _discord_is_authorized(ctx, "999", "") is True

    def test_denied_by_user_id(self):
        ctx = self._make_ctx(author_id=111)
        assert _discord_is_authorized(ctx, "999", "") is False

    def test_allowed_by_channel_id(self):
        ctx = self._make_ctx(channel_id=456)
        assert _discord_is_authorized(ctx, "", "456") is True

    def test_denied_by_channel_id(self):
        ctx = self._make_ctx(channel_id=789)
        assert _discord_is_authorized(ctx, "", "456") is False

    def test_channel_takes_priority(self):
        ctx = self._make_ctx(author_id=111, channel_id=456)
        assert _discord_is_authorized(ctx, "999", "456") is True


class TestTelegramAuth:
    def test_open_when_no_restriction(self):
        assert _telegram_is_authorized(123, "") is True

    def test_allowed_user(self):
        assert _telegram_is_authorized(999, "999") is True

    def test_denied_user(self):
        assert _telegram_is_authorized(111, "999") is False

    def test_id_compared_as_string(self):
        assert _telegram_is_authorized(999, "999") is True
