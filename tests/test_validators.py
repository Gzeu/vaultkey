"""
test_validators.py — Tests for wallet/utils/validators.py.

Covers:
  validate_key_name      — empty, too long, control chars, valid
  validate_api_key_value — too short, too long, non-printable, spaces, valid
  parse_expiry_date      — empty (None), wrong format, past date, future date
  validate_tag_list      — empty, valid tags, too-long tag, invalid chars
"""

from datetime import datetime, timedelta, timezone

import pytest
import typer

from wallet.utils.validators import (
    parse_expiry_date,
    validate_api_key_value,
    validate_key_name,
    validate_tag_list,
)


class TestValidateKeyName:
    def test_valid_name(self):
        assert validate_key_name("  OpenAI Production  ") == "OpenAI Production"

    def test_empty_raises(self):
        with pytest.raises(typer.BadParameter, match="empty"):
            validate_key_name("")

    def test_whitespace_only_raises(self):
        with pytest.raises(typer.BadParameter, match="empty"):
            validate_key_name("   ")

    def test_too_long_raises(self):
        with pytest.raises(typer.BadParameter, match="too long"):
            validate_key_name("x" * 129)

    def test_max_length_ok(self):
        assert len(validate_key_name("x" * 128)) == 128

    def test_control_chars_raise(self):
        with pytest.raises(typer.BadParameter, match="control"):
            validate_key_name("name\x00here")

    def test_newline_raises(self):
        with pytest.raises(typer.BadParameter, match="control"):
            validate_key_name("name\nhere")


class TestValidateApiKeyValue:
    def test_valid_key(self):
        key = "sk-prod-" + "x" * 40
        assert validate_api_key_value(key) == key

    def test_strips_surrounding_whitespace(self):
        key = "  sk-valid-12345678  "
        assert validate_api_key_value(key) == "sk-valid-12345678"

    def test_too_short_raises(self):
        with pytest.raises(typer.BadParameter, match="too short"):
            validate_api_key_value("short")

    def test_too_long_raises(self):
        with pytest.raises(typer.BadParameter, match="too long"):
            validate_api_key_value("x" * 513)

    def test_non_printable_raises(self):
        with pytest.raises(typer.BadParameter, match="non-printable"):
            validate_api_key_value("valid123\x00hidden")

    def test_internal_space_raises(self):
        with pytest.raises(typer.BadParameter, match="whitespace"):
            validate_api_key_value("sk-key with spaces")

    def test_tab_raises(self):
        with pytest.raises(typer.BadParameter, match="whitespace"):
            validate_api_key_value("sk-key\twith-tab")

    def test_min_length_8_ok(self):
        assert validate_api_key_value("12345678") == "12345678"


class TestParseExpiryDate:
    def test_empty_returns_none(self):
        assert parse_expiry_date("") is None
        assert parse_expiry_date("   ") is None

    def test_future_date_ok(self):
        future = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
        result = parse_expiry_date(future)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_past_date_raises(self):
        with pytest.raises(typer.BadParameter, match="past"):
            parse_expiry_date("2020-01-01")

    def test_wrong_format_raises(self):
        with pytest.raises(typer.BadParameter, match="format"):
            parse_expiry_date("01/01/2030")

    def test_invalid_date_raises(self):
        with pytest.raises(typer.BadParameter, match="format"):
            parse_expiry_date("2030-13-99")

    def test_result_is_utc(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        result = parse_expiry_date(future)
        assert result.tzinfo == timezone.utc


class TestValidateTagList:
    def test_valid_tags(self):
        assert validate_tag_list("prod, ml, billing") == ["prod", "ml", "billing"]

    def test_empty_string_returns_empty(self):
        assert validate_tag_list("") == []

    def test_whitespace_string_returns_empty(self):
        assert validate_tag_list("  ,  ,  ") == []

    def test_lowercased(self):
        assert validate_tag_list("PROD") == ["prod"]

    def test_too_long_tag_raises(self):
        with pytest.raises(typer.BadParameter, match="too long"):
            validate_tag_list("x" * 33)

    def test_invalid_chars_raise(self):
        with pytest.raises(typer.BadParameter, match="invalid characters"):
            validate_tag_list("tag with space")

    def test_hyphens_and_underscores_allowed(self):
        assert validate_tag_list("my-tag, my_tag") == ["my-tag", "my_tag"]
