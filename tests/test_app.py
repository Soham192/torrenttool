import re

import pytest


def _format_size(size_bytes: int) -> str:
    gb = size_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.1f} MB"


def _format_speed(speed_bytes: int) -> str:
    kb = speed_bytes / 1024
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB/s"
    return f"{kb:.0f} KB/s"


def _sanitize_username(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", name.strip().lower().replace(" ", "_"))


class TestFormatSize:
    def test_bytes_as_mb(self):
        assert _format_size(500 * 1024 * 1024) == "500.0 MB"

    def test_bytes_as_gb(self):
        assert _format_size(2 * 1024 ** 3) == "2.00 GB"

    def test_zero(self):
        assert _format_size(0) == "0.0 MB"

    def test_boundary_just_under_1gb(self):
        assert "MB" in _format_size(1024 ** 3 - 1)

    def test_exactly_1gb(self):
        assert _format_size(1024 ** 3) == "1.00 GB"


class TestFormatSpeed:
    def test_kb_range(self):
        assert _format_speed(500 * 1024) == "500 KB/s"

    def test_mb_range(self):
        assert _format_speed(2 * 1024 * 1024) == "2.0 MB/s"

    def test_zero(self):
        assert _format_speed(0) == "0 KB/s"

    def test_boundary_just_under_1mb(self):
        assert "KB/s" in _format_speed(1024 * 1024 - 1)

    def test_exactly_1mb(self):
        assert _format_speed(1024 * 1024) == "1.0 MB/s"


class TestSanitizeUsername:
    def test_normal_name(self):
        assert _sanitize_username("john") == "john"

    def test_strips_whitespace(self):
        assert _sanitize_username("  alice  ") == "alice"

    def test_lowercases(self):
        assert _sanitize_username("Bob") == "bob"

    def test_spaces_become_underscores(self):
        assert _sanitize_username("john doe") == "john_doe"

    def test_strips_special_chars(self):
        assert _sanitize_username("user:admin") == "useradmin"

    def test_strips_commas(self):
        assert _sanitize_username("a, b") == "a_b"

    def test_empty_after_sanitize(self):
        assert _sanitize_username("!!!") == ""

    def test_unicode_stripped(self):
        assert _sanitize_username("héllo") == "hllo"

    def test_tag_injection_prevented(self):
        result = _sanitize_username("user:other, user:admin")
        assert ":" not in result
        assert ", " not in result
