"""
wallet.py — Pydantic v2 data models for wallet payload and API key entries.

Design decisions:
- All models use strict=False for forward-compat with extra fields on load.
- Encrypted API key values stored as nonce_hex + cipher_hex (explicit, safe serialization).
- integrity_hmac: optional HMAC-SHA256 manifest over all entries (added Wave 2).
  - Absent on wallets created before v1.1 (auto-migrated on next save).
  - Verified on load when enable_integrity_check=True.
- WalletPayload.search() supports fuzzy substring matching on name, service, tags.
- rotation_reminder_days: default 90 — triggers 'expiring' status label warning.
- WalletPayload.rename_entry() added in Wave 7: renames an entry without
  re-encrypting the key value (metadata-only change).
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
    nonce_hex: str
    cipher_hex: str
    prefix: Optional[str] = None
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
    def normalize_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [t.strip().lower() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).lower().strip() for t in v if str(t).strip()]
        return []

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> str:
        return str(v).strip()

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def expires_soon(self) -> bool:
        """Returns True if expiring within rotation_reminder_days days."""
        if self.expires_at is None:
            return False
        delta = self.expires_at - datetime.now(timezone.utc)
        return 0 < delta.days <= self.rotation_reminder_days

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

    version: str = "1.2"
    master_hash: str
    created_at: datetime = Field(default_factory=_now_utc)
    modified_at: datetime = Field(default_factory=_now_utc)
    keys: dict[str, APIKeyEntry] = Field(default_factory=dict)
    integrity_hmac: Optional[str] = None   # HMAC-SHA256 manifest (Wave 2)

    def touch(self) -> None:
        self.modified_at = _now_utc()

    def add_entry(self, entry: APIKeyEntry) -> None:
        self.keys[entry.id] = entry
        self.touch()

    def get_entry(self, name_or_id: str) -> Optional[APIKeyEntry]:
        """Lookup by exact ID first, then case-insensitive name match."""
        if name_or_id in self.keys:
            return self.keys[name_or_id]
        needle = name_or_id.lower()
        for entry in self.keys.values():
            if entry.name.lower() == needle:
                return entry
        return None

    def delete_entry(self, entry_id: str) -> bool:
        if entry_id in self.keys:
            del self.keys[entry_id]
            self.touch()
            return True
        return False

    def rename_entry(self, name_or_id: str, new_name: str) -> APIKeyEntry:
        """
        Rename an entry in-place without touching encrypted data.

        This is a metadata-only operation — nonce_hex and cipher_hex are
        unchanged because the encryption domain is keyed by UUID, not name.

        Args:
            name_or_id: Current name or UUID of the entry.
            new_name:   Target name (must pass validate_key_name before calling).

        Returns:
            The mutated APIKeyEntry.

        Raises:
            KeyError: Entry not found.
            ValueError: new_name already taken by another entry.
        """
        entry = self.get_entry(name_or_id)
        if entry is None:
            raise KeyError(f"Entry '{name_or_id}' not found.")
        conflict = self.get_entry(new_name)
        if conflict and conflict.id != entry.id:
            raise ValueError(f"An entry named '{new_name}' already exists.")
        entry.name = new_name
        entry.updated_at = _now_utc()
        self.touch()
        return entry

    def search(
        self,
        query: str = "",
        tag: str = "",
        service: str = "",
    ) -> list[APIKeyEntry]:
        """Filter entries by substring query, tag, and/or service name."""
        results = list(self.keys.values())
        if query:
            q = query.lower()
            results = [
                e for e in results
                if q in e.name.lower()
                or q in e.service.lower()
                or any(q in t for t in e.tags)
                or (e.description and q in e.description.lower())
            ]
        if tag:
            t = tag.lower()
            results = [e for e in results if t in e.tags]
        if service:
            s = service.lower()
            results = [e for e in results if s in e.service.lower()]
        return results

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, d: dict) -> "WalletPayload":
        return cls.model_validate(d)
