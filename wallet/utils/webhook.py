"""
webhook.py — Webhook notifier for VaultKey expiry alerts.

Wave 9 addition.

Sends HTTP POST notifications to a configured URL when API keys are
expiring or have expired. Useful for CI/CD pipelines, Slack/Discord
incoming webhooks, or custom monitoring endpoints.

Configuration stored in ~/.vaultkey/webhook.json:
  {
    "url":        "https://hooks.slack.com/...",
    "format":     "slack" | "discord" | "generic",
    "enabled":    true,
    "min_days":   7        // only notify if days_left <= min_days
  }

Usage:
    wallet webhook set <url> [--format slack|discord|generic]
    wallet webhook test
    wallet webhook clear
    wallet webhook status

The notifier is called automatically after `wallet expiry-check` if
webhooks are configured and enabled.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

_DEFAULT_CONFIG = Path.home() / ".vaultkey" / "webhook.json"
_TIMEOUT_SECONDS = 8


@dataclass
class WebhookConfig:
    url: str
    format: str = "generic"  # slack | discord | generic
    enabled: bool = True
    min_days: int = 7


# ------------------------------------------------------------------ #
# Config I/O
# ------------------------------------------------------------------ #


def load_webhook_config(
    config_path: Path = _DEFAULT_CONFIG,
) -> Optional[WebhookConfig]:
    """Load webhook config from disk. Returns None if not configured."""
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return WebhookConfig(
            url=data["url"],
            format=data.get("format", "generic"),
            enabled=data.get("enabled", True),
            min_days=data.get("min_days", 7),
        )
    except (KeyError, json.JSONDecodeError):
        return None


def save_webhook_config(
    cfg: WebhookConfig,
    config_path: Path = _DEFAULT_CONFIG,
) -> None:
    """Persist webhook config to disk."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "url": cfg.url,
                "format": cfg.format,
                "enabled": cfg.enabled,
                "min_days": cfg.min_days,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_webhook_config(config_path: Path = _DEFAULT_CONFIG) -> bool:
    """Delete webhook config. Returns True if a file was removed."""
    if config_path.exists():
        config_path.unlink()
        return True
    return False


# ------------------------------------------------------------------ #
# Payload builders
# ------------------------------------------------------------------ #


def _build_payload(format: str, warnings: list[dict]) -> dict:
    count = len(warnings)
    lines = []
    for w in warnings:
        status = "EXPIRED" if w.get("is_expired") else f"{w['days_left']}d left"
        lines.append(f"• *{w['name']}* ({w['service']}) — {status}")
    body = "\n".join(lines)

    if format == "slack":
        return {
            "text": f":warning: VaultKey: {count} API key(s) expiring soon",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":warning: *VaultKey Expiry Alert*\n{body}",
                    },
                }
            ],
        }
    elif format == "discord":
        return {
            "username": "VaultKey",
            "content": f"⚠️ **VaultKey Expiry Alert** — {count} key(s)\n{body}",
        }
    else:  # generic
        return {
            "source": "vaultkey",
            "event": "expiry_alert",
            "count": count,
            "keys": warnings,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


# ------------------------------------------------------------------ #
# Notifier
# ------------------------------------------------------------------ #


def send_expiry_notification(
    warnings: list[dict],
    cfg: Optional[WebhookConfig] = None,
    config_path: Path = _DEFAULT_CONFIG,
) -> tuple[bool, str]:
    """POST expiry alerts to the configured webhook URL.

    Args:
        warnings:    List of dicts with keys: name, service, days_left, is_expired.
        cfg:         Pre-loaded WebhookConfig (loads from disk if None).
        config_path: Override path for config file.

    Returns:
        Tuple of (success: bool, message: str).
    """
    if cfg is None:
        cfg = load_webhook_config(config_path)
    if cfg is None or not cfg.enabled:
        return False, "Webhook not configured or disabled."
    if not warnings:
        return True, "No warnings to send."

    filtered = [w for w in warnings if w.get("is_expired") or w.get("days_left", 999) <= cfg.min_days]
    if not filtered:
        return True, "No warnings within min_days threshold."

    payload = _build_payload(cfg.format, filtered)
    body = json.dumps(payload).encode()

    req = urllib.request.Request(
        cfg.url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "VaultKey/1.3"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            status = resp.status
            return status < 400, f"HTTP {status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection error: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return False, f"Unexpected error: {e}"


def send_test_notification(
    cfg: WebhookConfig,
) -> tuple[bool, str]:
    """Send a test payload to verify the webhook URL."""
    test_warnings = [
        {"name": "TestKey", "service": "vaultkey-test", "days_left": 3, "is_expired": False}
    ]
    return send_expiry_notification(test_warnings, cfg=cfg)
