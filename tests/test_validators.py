"""
Tests for validators — including FIX #7 (max API key length).
"""

import pytest
from wallet.utils.validators import (
    MAX_API_KEY_LENGTH,
    MIN_API_KEY_LENGTH,
    parse_expiry_date,
    validate_api_key_value,
    validate_key_name,
)


class TestValidateApiKeyValue:
    def test_valid_key(self):
        key = "sk-" + "a" * 48
        assert validate_api_key_value(key) == key

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_api_key_value("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_api_key_value("   ")

    def test_internal_whitespace_raises(self):
        with pytest.raises(ValueError, match="whitespace"):
            validate_api_key_value("sk-abc def")

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="short"):
            validate_api_key_value("sk-abc")  # < MIN_API_KEY_LENGTH

    def test_exactly_min_length(self):
        val = "a" * MIN_API_KEY_LENGTH
        assert validate_api_key_value(val) == val

    def test_max_length_passes(self):
        val = "a" * MAX_API_KEY_LENGTH
        assert validate_api_key_value(val) == val

    def test_over_max_length_raises(self):
        """FIX #7 regression: values over MAX_API_KEY_LENGTH must be rejected."""
        with pytest.raises(ValueError, match="too long"):
            validate_api_key_value("a" * (MAX_API_KEY_LENGTH + 1))

    def test_one_mb_rejected(self):
        """FIX #7 regression: a 1MB payload must not pass validation."""
        with pytest.raises(ValueError, match="too long"):
            validate_api_key_value("x" * 1_000_000)


class TestValidateKeyName:
    def test_valid_name(self):
        assert validate_key_name("OpenAI Production") == "OpenAI Production"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_key_name("")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_key_name("a" * 101)

    def test_strips_whitespace(self):
        assert validate_key_name("  test  ") == "test"


class TestParseExpiryDate:
    def test_valid_date(self):
        dt = parse_expiry_date("2025-12-31")
        assert dt is not None
        assert dt.year == 2025

    def test_empty_returns_none(self):
        assert parse_expiry_date("") is None
        assert parse_expiry_date(None) is None

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            parse_expiry_date("31-12-2025")
