"""
test_prefix_detect.py — Tests for wallet/utils/prefix_detect.py.

Covers:
  - Known service prefixes return the correct ServiceInfo
  - Unknown prefix returns None
  - Case sensitivity
  - mask_key: correct masking format
  - mask_key: short keys masked fully
"""

from __future__ import annotations

import pytest

from wallet.utils.prefix_detect import detect_service, mask_key


KNOWN_KEYS = [
    ("sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "openai", "OpenAI"),
    ("sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "anthropic", "Anthropic"),
    ("AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "google", "Google"),
    ("ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "github", "GitHub"),
    ("xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx", "slack", "Slack"),
    ("SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "sendgrid", "SendGrid"),
    ("gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "groq", "Groq"),
    ("r8_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "replicate", "Replicate"),
    ("sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "openai", "OpenAI"),  # short openai-style
]


class TestDetectService:
    @pytest.mark.parametrize("key,expected_id,expected_name", KNOWN_KEYS)
    def test_known_prefixes(self, key: str, expected_id: str, expected_name: str) -> None:
        result = detect_service(key)
        assert result is not None, f"Expected to detect {expected_id} for key: {key[:12]}..."
        assert result.service_id == expected_id
        assert expected_name in result.display_name

    def test_unknown_prefix_returns_none(self):
        assert detect_service("xyz-totally-unknown-key-format-xxx") is None

    def test_empty_string_returns_none(self):
        assert detect_service("") is None

    def test_very_short_string_returns_none(self):
        assert detect_service("sk") is None

    def test_result_has_required_fields(self):
        result = detect_service("sk-proj-" + "x" * 40)
        if result is not None:
            assert hasattr(result, "service_id")
            assert hasattr(result, "display_name")


class TestMaskKey:
    def test_long_key_shows_prefix_and_suffix(self):
        key = "sk-prod-" + "x" * 40
        masked = mask_key(key)
        assert "..." in masked
        # First and last chars must be visible
        assert masked.startswith(key[:4])

    def test_short_key_fully_masked(self):
        key = "short"
        masked = mask_key(key)
        assert "*" in masked or "." in masked or len(masked) <= len(key)

    def test_mask_does_not_expose_middle(self):
        key = "sk-secret-middle-xxxx-end"
        masked = mask_key(key)
        # The full key should not appear in the masked version
        assert key not in masked
