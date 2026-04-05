"""
config.py — Non-secret wallet configuration via pydantic-settings.

Only non-sensitive settings live here. Secrets (keys, passwords) never touch this file.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WalletConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VAULTKEY_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    wallet_path: Path = Field(default=Path("wallet.enc"))
    backup_dir: Path = Field(default=Path("backups"))
    audit_log_path: Path = Field(default=Path("audit.log"))
    session_timeout_minutes: int = Field(default=15, ge=1, le=1440)
    clipboard_clear_seconds: int = Field(default=30, ge=5, le=300)
    max_backups: int = Field(default=20, ge=5, le=100)
    show_masked_on_get: bool = Field(default=True)
