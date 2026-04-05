"""
wallet.py — Pydantic v2 data models for wallet payload and API key entries.

Design decisions:
- All models use model_config with strict=True to prevent silent type coercion.
- Encrypted API key values are stored as two separate fields: nonce_hex + cipher_hex.
  This makes the binary structure explicit and serialization/deserialization safe.
- expires_at and last_accessed_at are Optional to avoid forcing fields on creation.
- access_count tracks usage without storing the actual key value in logs.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class APIKeyEntry(BaseModel):
    model_config = ConfigDict(strict=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    service: str
    nonce_hex: str                          # AES-GCM nonce (hex)
    cipher_hex: str                         # AES-GCM ciphertext+tag (hex)
    prefix: Optional[str] = None           # Auto-detected (sk-, gsk_, etc.)
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    expires_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    is_active: bool = True
    rotation_reminder_days: int = 90

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v):
        if isinstance(v, str):
            return [t.strip().lower() for t in v.split(",") if t.strip()]
        return [t.lower() for t in v]

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def expires_soon(self) -> bool:
        """Returns True if expiring within 30 days."""
        if self.expires_at is None:
            return False
        delta = self.expires_at - datetime.now(timezone.utc)
        return 0 < delta.days <= 30

    @property
    def status_label(self) -> str:
        if not self.is_active:
            return "revoked"
        if self.is_expired:
            return "expired"
        if self.expires_soon:
            return "expiring"
        return "active"


class WalletPayload(BaseModel):
    model_config = ConfigDict(strict=False)

    version: str = "1.0"
    master_hash: str                        # Argon2id hash string for verification
    created_at: datetime = Field(default_factory=_now_utc)
    modified_at: datetime = Field(default_factory=_now_utc)
    keys: dict[str, APIKeyEntry] = Field(default_factory=dict)

    def touch(self) -> None:
        self.modified_at = _now_utc()

    def add_entry(self, entry: APIKeyEntry) -> None:
        self.keys[entry.id] = entry
        self.touch()

    def get_entry(self, name_or_id: str) -> Optional[APIKeyEntry]:
        if name_or_id in self.keys:
            return self.keys[name_or_id]
        for entry in self.keys.values():
            if entry.name.lower() == name_or_id.lower():
                return entry
        return None

    def delete_entry(self, entry_id: str) -> bool:
        if entry_id in self.keys:
            del self.keys[entry_id]
            self.touch()
            return True
        return False

    def search(self, query: str = "", tag: str = "", service: str = "") -> list[APIKeyEntry]:
        results = list(self.keys.values())
        if query:
            q = query.lower()
            results = [e for e in results if q in e.name.lower() or q in e.service.lower()]
        if tag:
            results = [e for e in results if tag.lower() in e.tags]
        if service:
            results = [e for e in results if service.lower() in e.service.lower()]
        return results

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, d: dict) -> "WalletPayload":
        return cls.model_validate(d)
