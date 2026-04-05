"""
config.py — Runtime configuration via pydantic-settings + .env support.

All paths default to XDG_DATA_HOME (~/.local/share/vaultkey on Linux,
~/Library/Application Support/vaultkey on macOS, %APPDATA%/vaultkey on Windows).

Configuration can be overridden via:
  1. Environment variables prefixed with VAULTKEY_ (highest priority)
  2. .env file in the current working directory
  3. Defaults below (lowest priority)

Security considerations:
- VAULTKEY_WALLET_PATH allows pointing to a custom wallet location
  (useful for encrypted volumes, network drives, or testing).
- SESSION_TIMEOUT_MINUTES should never be set above 60 in production.
- CLIPBOARD_CLEAR_SECONDS default of 30 matches 1Password and Bitwarden defaults.
"""

import os
import platform
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
    return base / "vaultkey"


_DATA_DIR = _default_data_dir()


class WalletConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VAULTKEY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    wallet_path: Path = Field(
        default=_DATA_DIR / "wallet.enc",
        description="Path to the encrypted wallet file.",
    )
    backup_dir: Path = Field(
        default=_DATA_DIR / "backups",
        description="Directory where timestamped backups are stored.",
    )
    audit_log_path: Path = Field(
        default=_DATA_DIR / "audit.log",
        description="Path to the append-only audit log.",
    )
    session_timeout_minutes: int = Field(
        default=15,
        ge=1,
        le=120,
        description="Minutes of inactivity before auto-lock.",
    )
    clipboard_clear_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Seconds before clipboard is automatically cleared.",
    )
    max_backups: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of backup files to keep.",
    )
    enable_integrity_check: bool = Field(
        default=True,
        description="Verify HMAC integrity manifest on every load.",
    )
