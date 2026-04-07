"""
notes.py — Secure encrypted notes storage for VaultKey.

Each note's body is encrypted with AES-256-GCM using a per-note subkey
derived via HKDF-SHA256 from the master key and note UUID — the same
defense-in-depth pattern used for APIKeyEntry values.

The title and tags are stored in plaintext (they are metadata, not secrets).
The body is treated as a secret and never appears unencrypted on disk.

Design decisions:
- SecureNote is a standalone Pydantic v2 model stored in a separate
  `notes` dict in WalletPayload to avoid collision with the `keys` dict.
- Pinned notes float to the top of list_notes() results.
- Notes support Markdown body content (no size limit enforced here;
  callers may add their own limits).
- Max body size before encryption: 64 KB (enforced in validate_note_body).
- The HKDF info string is 'vaultkey:note:<uuid>' to domain-separate note
  subkeys from API key subkeys ('vaultkey:entry:<uuid>').
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wallet.core.crypto import (
    SecureMemory,
    decrypt_aes_gcm,
    derive_entry_subkey,
    encrypt_aes_gcm,
)

MAX_BODY_BYTES = 65_536  # 64 KB


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# Model
# ------------------------------------------------------------------ #

class SecureNote(BaseModel):
    """
    Pydantic v2 model for an encrypted secure note.

    Fields:
        id:           UUID primary key.
        title:        Plaintext title (1-256 chars).
        body_nonce_hex:  AES-GCM nonce for encrypted body.
        body_cipher_hex: AES-GCM ciphertext of the Markdown/text body.
        tags:         List of lowercase tag strings.
        pinned:       If True, floats to top of list.
        created_at:   Creation timestamp (UTC).
        updated_at:   Last modification timestamp (UTC).
    """
    model_config = ConfigDict(strict=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    body_nonce_hex: str
    body_cipher_hex: str
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: object) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("Note title cannot be empty.")
        if len(s) > 256:
            raise ValueError("Note title too long (max 256 characters).")
        return s

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


# ------------------------------------------------------------------ #
# Validation
# ------------------------------------------------------------------ #

def validate_note_body(body: str) -> str:
    """
    Validate a note body string.

    Args:
        body: Raw text/Markdown content.

    Returns:
        The body string (unchanged if valid).

    Raises:
        ValueError: Body exceeds MAX_BODY_BYTES when encoded as UTF-8.
    """
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES:
        raise ValueError(
            f"Note body too large ({len(encoded)} bytes). "
            f"Maximum is {MAX_BODY_BYTES} bytes (64 KB)."
        )
    return body


# ------------------------------------------------------------------ #
# Encrypt / Decrypt
# ------------------------------------------------------------------ #

def encrypt_note_body(
    master_key: bytes,
    note_id: str,
    body: str,
) -> tuple[str, str]:
    """
    Encrypt a note body with a per-note AES-256-GCM subkey.

    Args:
        master_key: AES-256 session key.
        note_id:    UUID of the note (HKDF domain separator).
        body:       Plaintext body string (UTF-8).

    Returns:
        (nonce_hex, cipher_hex)
    """
    subkey = derive_entry_subkey(master_key, f"note:{note_id}")
    with SecureMemory(subkey) as sk:
        nonce, cipher = encrypt_aes_gcm(bytes(sk), body.encode("utf-8"))
    return nonce.hex(), cipher.hex()


def decrypt_note_body(
    master_key: bytes,
    note_id: str,
    nonce_hex: str,
    cipher_hex: str,
) -> str:
    """
    Decrypt a note body.

    Returns:
        Plaintext body string.

    Raises:
        cryptography.exceptions.InvalidTag: Authentication failure.
    """
    subkey = derive_entry_subkey(master_key, f"note:{note_id}")
    with SecureMemory(subkey) as sk:
        plaintext = decrypt_aes_gcm(
            bytes(sk),
            bytes.fromhex(nonce_hex),
            bytes.fromhex(cipher_hex),
        )
    return plaintext.decode("utf-8")


# ------------------------------------------------------------------ #
# High-level CRUD API
# ------------------------------------------------------------------ #

def create_note(
    master_key: bytes,
    title: str,
    body: str,
    *,
    tags: list[str] | str = "",
    pinned: bool = False,
) -> SecureNote:
    """
    Create and encrypt a new SecureNote.

    Args:
        master_key: AES-256 session key.
        title:      Note title (plaintext).
        body:       Note body (encrypted).
        tags:       List or comma-separated string of tags.
        pinned:     Whether this note is pinned.

    Returns:
        A fully populated SecureNote ready for serialisation.

    Raises:
        ValueError: Title or body validation failure.
    """
    body = validate_note_body(body)
    note_id = str(uuid.uuid4())
    nonce_hex, cipher_hex = encrypt_note_body(master_key, note_id, body)
    return SecureNote(
        id=note_id,
        title=title.strip(),
        body_nonce_hex=nonce_hex,
        body_cipher_hex=cipher_hex,
        tags=tags,
        pinned=pinned,
    )


def update_note_body(
    master_key: bytes,
    note: SecureNote,
    new_body: str,
) -> SecureNote:
    """
    Re-encrypt a note's body with a fresh nonce.

    The note is mutated in-place and returned.

    Args:
        master_key: AES-256 session key.
        note:       The SecureNote to update.
        new_body:   New plaintext body.

    Returns:
        The updated SecureNote.
    """
    new_body = validate_note_body(new_body)
    nonce_hex, cipher_hex = encrypt_note_body(master_key, note.id, new_body)
    note.body_nonce_hex = nonce_hex
    note.body_cipher_hex = cipher_hex
    note.touch()
    return note


def retrieve_note_body(
    master_key: bytes,
    note: SecureNote,
) -> str:
    """
    Decrypt and return a note's body.

    Raises:
        cryptography.exceptions.InvalidTag: Decryption/auth failure.
    """
    return decrypt_note_body(
        master_key, note.id, note.body_nonce_hex, note.body_cipher_hex
    )


# ------------------------------------------------------------------ #
# Notes collection helpers (for use on WalletPayload.notes dict)
# ------------------------------------------------------------------ #

def list_notes(
    notes: dict[str, SecureNote],
    *,
    tag: str = "",
    query: str = "",
    pinned_first: bool = True,
) -> list[SecureNote]:
    """
    Filter and sort a notes dict.

    Args:
        notes:        The notes dict from WalletPayload.
        tag:          If set, return only notes with this tag.
        query:        Substring search on title and tags.
        pinned_first: If True, pinned notes appear first.

    Returns:
        Sorted list of SecureNote.
    """
    results = list(notes.values())

    if tag:
        t = tag.lower()
        results = [n for n in results if t in n.tags]

    if query:
        q = query.lower()
        results = [
            n for n in results
            if q in n.title.lower() or any(q in t for t in n.tags)
        ]

    if pinned_first:
        results.sort(key=lambda n: (not n.pinned, n.updated_at), reverse=False)
        # Secondary sort: by updated_at desc within each pin group
        pinned = sorted(
            [n for n in results if n.pinned],
            key=lambda n: n.updated_at, reverse=True
        )
        unpinned = sorted(
            [n for n in results if not n.pinned],
            key=lambda n: n.updated_at, reverse=True
        )
        results = pinned + unpinned
    else:
        results.sort(key=lambda n: n.updated_at, reverse=True)

    return results
