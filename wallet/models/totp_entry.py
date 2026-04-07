"""
totp_entry.py — Pydantic model for TOTP/2FA entries in the wallet.

TOTP entries are stored encrypted with the same AES-256-GCM + HKDF pipeline
as API key entries. The TOTP secret field (totp_secret_nonce_hex +
totp_secret_cipher_hex) follows the same nonce/cipher pattern as APIKeyEntry.

The scratch codes list stores SHA-256 hashed codes only (never plaintext).

Integration with WalletPayload:
    payload.totp_entries: dict[str, TOTPEntry]  # keyed by entry.id

Wave 11 addition — fully backward compatible (new field with default_factory).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ScratchCodeEntry(BaseModel):
    """Serializable representation of a single scratch code (hashed)."""
    model_config = ConfigDict(strict=False)

    code_hash: str
    used: bool = False


class TOTPEntry(BaseModel):
    """
    Represents one TOTP / 2FA entry stored in the vault.

    The TOTP secret is stored encrypted (same pipeline as API keys):
        totp_secret_nonce_hex + totp_secret_cipher_hex

    After decryption, pass the plaintext secret to TOTPEngine().

    Fields:
        id:          UUID, primary key.
        name:        Human-readable label (e.g., "GitHub 2FA").
        account:     Account identifier shown in authenticator apps (e.g., email).
        issuer:      Service name (e.g., "GitHub").
        digits:      Code length, almost always 6.
        interval:    Time step in seconds, almost always 30.
        algorithm:   Hash algorithm (SHA1 required by most apps).
        totp_secret_nonce_hex:  Encryption nonce for the TOTP secret.
        totp_secret_cipher_hex: AES-256-GCM ciphertext of the TOTP secret.
        scratch_codes: Hashed one-time backup codes.
        tags:        Searchable labels.
        notes:       Optional free-text notes.
        created_at:  Creation timestamp.
        updated_at:  Last modification timestamp.
        last_used_at: Last time a code was copied/shown.
    """

    model_config = ConfigDict(strict=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    account: str = ""
    issuer: str = "VaultKey"
    digits: int = Field(default=6, ge=6, le=8)
    interval: int = Field(default=30, ge=15, le=60)
    algorithm: str = "SHA1"

    # Encrypted TOTP secret (same nonce+cipher pattern as APIKeyEntry)
    totp_secret_nonce_hex: str
    totp_secret_cipher_hex: str

    # Backup codes (hashed)
    scratch_codes: list[ScratchCodeEntry] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    last_used_at: Optional[datetime] = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("algorithm", mode="before")
    @classmethod
    def normalize_algorithm(cls, v: object) -> str:
        allowed = {"SHA1", "SHA256", "SHA512"}
        upper = str(v).upper().replace("-", "")
        if upper not in allowed:
            raise ValueError(f"Algorithm must be one of {allowed}, got '{v}'")
        return upper

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [t.strip().lower() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).lower().strip() for t in v if str(t).strip()]
        return []

    def touch(self) -> None:
        self.updated_at = _now_utc()

    def mark_used(self) -> None:
        self.last_used_at = _now_utc()
        self.touch()

    @property
    def scratch_remaining(self) -> int:
        return sum(1 for sc in self.scratch_codes if not sc.used)

    @property
    def needs_scratch_regen(self) -> bool:
        """True if fewer than 3 scratch codes remain (warn user)."""
        return 0 < self.scratch_remaining < 3
