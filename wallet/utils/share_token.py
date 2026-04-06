"""
share_token.py — Per-entry encrypted share tokens for VaultKey.

Wave 9 addition.

Allows a user to export a single API key as a self-contained encrypted blob
(a "share token") that can be transferred securely to another person or
machine. The recipient imports it with `wallet share import <token_file>`.

Security model:
  - Token is encrypted with AES-256-GCM using a key derived from a
    one-time passphrase via Argon2id (same parameters as the main wallet).
  - The plaintext never touches disk; decryption happens in memory.
  - Token includes the entry metadata (name, service, tags, description,
    expiry) plus the raw API key value — re-encrypted under the share key.
  - Token is a base64-encoded JSON envelope (portable, pasteable).
  - Token format version is included to allow future migration.

Usage:
    wallet share export <name>  → prompts for passphrase, writes token file
    wallet share import <file>  → prompts for passphrase, adds entry to wallet
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from wallet.core.kdf import KDFParams, derive_key

_TOKEN_VERSION = "vk-share-v1"


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def export_share_token(
    entry_name: str,
    entry_service: str,
    entry_tags: list[str],
    entry_description: Optional[str],
    entry_expires_at: Optional[datetime],
    raw_value: str,
    passphrase: str,
) -> str:
    """Encrypt an entry into a portable share token string.

    Args:
        entry_*:    Metadata fields of the APIKeyEntry.
        raw_value:  Plaintext API key value (already decrypted from the wallet).
        passphrase: One-time passphrase the recipient must know.

    Returns:
        A base64-encoded JSON string suitable for saving to a .vkshare file.
    """
    params = KDFParams.generate()
    share_key = derive_key(passphrase, params)

    payload = json.dumps(
        {
            "name": entry_name,
            "service": entry_service,
            "tags": entry_tags,
            "description": entry_description,
            "expires_at": entry_expires_at.isoformat() if entry_expires_at else None,
            "value": raw_value,
        },
        ensure_ascii=False,
    ).encode()

    nonce = os.urandom(12)
    cipher_bytes = AESGCM(share_key).encrypt(nonce, payload, None)

    envelope = {
        "version": _TOKEN_VERSION,
        "kdf": {
            "salt_hex": params.salt.hex(),
            "time_cost": params.time_cost,
            "memory_cost": params.memory_cost,
            "parallelism": params.parallelism,
            "hash_len": params.hash_len,
        },
        "nonce_hex": nonce.hex(),
        "cipher_b64": base64.b64encode(cipher_bytes).decode(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return base64.b64encode(
        json.dumps(envelope, ensure_ascii=False).encode()
    ).decode()


def import_share_token(token_str: str, passphrase: str) -> dict:
    """Decrypt a share token and return the entry metadata + value.

    Args:
        token_str:  Base64-encoded share token (from export_share_token).
        passphrase: Passphrase used during export.

    Returns:
        Dict with keys: name, service, tags, description, expires_at, value.

    Raises:
        ValueError: On format errors, version mismatch, or wrong passphrase.
    """
    try:
        raw_json = base64.b64decode(token_str.strip())
        envelope = json.loads(raw_json)
    except Exception as exc:
        raise ValueError(f"Invalid share token format: {exc}") from exc

    if envelope.get("version") != _TOKEN_VERSION:
        raise ValueError(
            f"Unsupported token version: {envelope.get('version')!r}"
        )

    kdf_data = envelope["kdf"]
    params = KDFParams(
        salt=bytes.fromhex(kdf_data["salt_hex"]),
        time_cost=kdf_data["time_cost"],
        memory_cost=kdf_data["memory_cost"],
        parallelism=kdf_data["parallelism"],
        hash_len=kdf_data["hash_len"],
    )
    share_key = derive_key(passphrase, params)

    nonce = bytes.fromhex(envelope["nonce_hex"])
    cipher_bytes = base64.b64decode(envelope["cipher_b64"])

    try:
        plaintext = AESGCM(share_key).decrypt(nonce, cipher_bytes, None)
    except Exception as exc:
        raise ValueError("Decryption failed — wrong passphrase or corrupted token.") from exc

    data = json.loads(plaintext.decode())
    return data


def write_token_file(token_str: str, path: Path) -> None:
    """Write a share token to a .vkshare file."""
    path.write_text(token_str, encoding="utf-8")


def read_token_file(path: Path) -> str:
    """Read a share token from a .vkshare file."""
    if not path.exists():
        raise FileNotFoundError(f"Token file not found: {path}")
    return path.read_text(encoding="utf-8").strip()
