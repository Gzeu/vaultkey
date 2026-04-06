"""
Tests for wallet/utils/webhook.py (Wave 9).
"""

from pathlib import Path

import pytest

from wallet.utils.webhook import (
    WebhookConfig,
    _build_payload,
    clear_webhook_config,
    load_webhook_config,
    save_webhook_config,
)


@pytest.fixture()
def cfg_path(tmp_path: Path) -> Path:
    return tmp_path / "webhook.json"


class TestConfigIO:
    def test_load_missing_returns_none(self, cfg_path: Path):
        assert load_webhook_config(cfg_path) is None

    def test_save_and_load_roundtrip(self, cfg_path: Path):
        cfg = WebhookConfig(
            url="https://hooks.slack.com/test",
            format="slack",
            enabled=True,
            min_days=14,
        )
        save_webhook_config(cfg, cfg_path)
        loaded = load_webhook_config(cfg_path)
        assert loaded is not None
        assert loaded.url == cfg.url
        assert loaded.format == "slack"
        assert loaded.min_days == 14

    def test_clear_removes_file(self, cfg_path: Path):
        cfg = WebhookConfig(url="https://example.com/hook", format="generic")
        save_webhook_config(cfg, cfg_path)
        removed = clear_webhook_config(cfg_path)
        assert removed is True
        assert not cfg_path.exists()

    def test_clear_nonexistent_returns_false(self, cfg_path: Path):
        assert clear_webhook_config(cfg_path) is False


class TestPayloadBuilders:
    _WARNINGS = [
        {"name": "OpenAI Key", "service": "openai", "days_left": 2, "is_expired": False},
        {"name": "Stripe Key", "service": "stripe", "days_left": 0, "is_expired": True},
    ]

    def test_generic_payload_structure(self):
        p = _build_payload("generic", self._WARNINGS)
        assert p["event"] == "expiry_alert"
        assert p["count"] == 2
        assert len(p["keys"]) == 2

    def test_slack_payload_has_blocks(self):
        p = _build_payload("slack", self._WARNINGS)
        assert "blocks" in p
        assert "text" in p

    def test_discord_payload_has_content(self):
        p = _build_payload("discord", self._WARNINGS)
        assert "content" in p
        assert "username" in p

    def test_expired_label_in_output(self):
        p = _build_payload("generic", self._WARNINGS)
        # Generic format passes through is_expired flag
        expired_entries = [k for k in p["keys"] if k.get("is_expired")]
        assert len(expired_entries) == 1
