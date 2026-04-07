"""
mvx.py — MultiversX (EGLD) wallet key & seed phrase secure storage.

Design decisions:
- Seed phrases are treated as high-value secrets: stored encrypted with
  a unique per-entry AES-256-GCM subkey (same HKDF pattern as crypto.py).
- BIP-39 wordcount validation (12, 15, 18, 21, 24 words) is enforced on
  input to catch accidental truncation before encryption.
- Private keys are stored as hex strings (64 chars = 32 bytes Ed25519).
- Address (erd1...) is stored in plaintext as a lookup hint — it is a
  public key and carries no secret information.
- MultiversX addresses use bech32 with HRP 'erd', so basic format
  validation is performed without requiring the full SDK.
- SecureMemory from crypto.py is used to zero seed/key bytes after use.

No external MultiversX SDK dependency is required — this module stores
and retrieves keys only; signing is out of scope for VaultKey.
"""

from __future__ import annotations

import re
import secrets
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

# Valid BIP-39 seed phrase word counts
VALID_WORD_COUNTS = {12, 15, 18, 21, 24}

# MultiversX bech32 address pattern (erd1 + 58 alphanum chars)
_ERD_RE = re.compile(r'^erd1[0-9a-z]{58}$')

# Hex private key: 64 lowercase hex chars (32 bytes Ed25519)
_PRIVKEY_RE = re.compile(r'^[0-9a-fA-F]{64}$')


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# Model
# ------------------------------------------------------------------ #

class MvxKeyEntry(BaseModel):
    """
    Pydantic model for a stored MultiversX wallet entry.

    Fields prefixed `seed_` and `privkey_` hold AES-GCM ciphertext.
    The `address` field is plaintext (public key derived address).
    """
    model_config = ConfigDict(strict=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str                          # human-readable name
    address: Optional[str] = None       # erd1... public address (plaintext)
    network: str = "mainnet"            # mainnet | devnet | testnet
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

    # Encrypted seed phrase (may be None if only privkey is stored)
    seed_nonce_hex: Optional[str] = None
    seed_cipher_hex: Optional[str] = None

    # Encrypted private key hex (may be None if only seed is stored)
    privkey_nonce_hex: Optional[str] = None
    privkey_cipher_hex: Optional[str] = None

    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    @field_validator("address", mode="before")
    @classmethod
    def validate_address(cls, v: object) -> Optional[str]:
        if v is None or v == "":
            return None
        s = str(v).strip()
        if not _ERD_RE.match(s):
            raise ValueError(
                f"Invalid MultiversX address '{s}'. "
                "Expected format: erd1 followed by 58 lowercase alphanumeric chars."
            )
        return s

    @field_validator("network", mode="before")
    @classmethod
    def validate_network(cls, v: object) -> str:
        s = str(v).strip().lower()
        if s not in {"mainnet", "devnet", "testnet"}:
            raise ValueError(f"network must be mainnet, devnet, or testnet; got '{s}'")
        return s

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [t.strip().lower() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).lower().strip() for t in v if str(t).strip()]
        return []

    @property
    def has_seed(self) -> bool:
        return self.seed_nonce_hex is not None and self.seed_cipher_hex is not None

    @property
    def has_privkey(self) -> bool:
        return self.privkey_nonce_hex is not None and self.privkey_cipher_hex is not None


# ------------------------------------------------------------------ #
# Validation helpers
# ------------------------------------------------------------------ #

def validate_seed_phrase(phrase: str) -> str:
    """
    Validate a BIP-39 seed phrase.

    Args:
        phrase: Space-separated mnemonic words.

    Returns:
        The normalised (lowercase, single-space) phrase.

    Raises:
        ValueError: Word count is not in VALID_WORD_COUNTS.
    """
    normalised = " ".join(phrase.strip().lower().split())
    word_count = len(normalised.split())
    if word_count not in VALID_WORD_COUNTS:
        raise ValueError(
            f"Seed phrase has {word_count} words; "
            f"expected one of {sorted(VALID_WORD_COUNTS)}."
        )
    return normalised


def validate_private_key_hex(hex_key: str) -> str:
    """
    Validate a 64-char hex Ed25519 private key.

    Returns:
        Lowercase hex string.

    Raises:
        ValueError: Format invalid.
    """
    s = hex_key.strip()
    if not _PRIVKEY_RE.match(s):
        raise ValueError(
            f"Invalid private key. Expected 64 hex characters, got {len(s)} chars."
        )
    return s.lower()


# ------------------------------------------------------------------ #
# Encrypt / Decrypt
# ------------------------------------------------------------------ #

def encrypt_mvx_seed(
    master_key: bytes,
    entry_id: str,
    seed_phrase: str,
) -> tuple[str, str]:
    """
    Encrypt a BIP-39 seed phrase.

    Args:
        master_key:  AES-256 master key (from session).
        entry_id:    UUID of the MvxKeyEntry (domain-separates the subkey).
        seed_phrase: Raw mnemonic string (validated by caller).

    Returns:
        (nonce_hex, cipher_hex)
    """
    subkey = derive_entry_subkey(master_key, f"mvx:seed:{entry_id}")
    with SecureMemory(subkey) as sk:
        plaintext = seed_phrase.encode("utf-8")
        nonce, cipher = encrypt_aes_gcm(bytes(sk), plaintext)
    return nonce.hex(), cipher.hex()


def decrypt_mvx_seed(
    master_key: bytes,
    entry_id: str,
    nonce_hex: str,
    cipher_hex: str,
) -> str:
    """
    Decrypt a stored BIP-39 seed phrase.

    Returns:
        The plaintext seed phrase.

    Raises:
        cryptography.exceptions.InvalidTag: Authentication failure.
    """
    subkey = derive_entry_subkey(master_key, f"mvx:seed:{entry_id}")
    with SecureMemory(subkey) as sk:
        plaintext = decrypt_aes_gcm(
            bytes(sk),
            bytes.fromhex(nonce_hex),
            bytes.fromhex(cipher_hex),
        )
    return plaintext.decode("utf-8")


def encrypt_mvx_privkey(
    master_key: bytes,
    entry_id: str,
    privkey_hex: str,
) -> tuple[str, str]:
    """
    Encrypt a 64-char hex Ed25519 private key.

    Returns:
        (nonce_hex, cipher_hex)
    """
    subkey = derive_entry_subkey(master_key, f"mvx:privkey:{entry_id}")
    with SecureMemory(subkey) as sk:
        nonce, cipher = encrypt_aes_gcm(bytes(sk), privkey_hex.encode())
    return nonce.hex(), cipher.hex()


def decrypt_mvx_privkey(
    master_key: bytes,
    entry_id: str,
    nonce_hex: str,
    cipher_hex: str,
) -> str:
    """
    Decrypt a stored private key hex string.

    Returns:
        The plaintext 64-char hex private key.
    """
    subkey = derive_entry_subkey(master_key, f"mvx:privkey:{entry_id}")
    with SecureMemory(subkey) as sk:
        plaintext = decrypt_aes_gcm(
            bytes(sk),
            bytes.fromhex(nonce_hex),
            bytes.fromhex(cipher_hex),
        )
    return plaintext.decode("utf-8")


# ------------------------------------------------------------------ #
# High-level store / retrieve API
# ------------------------------------------------------------------ #

def store_mvx_entry(
    master_key: bytes,
    label: str,
    *,
    seed_phrase: Optional[str] = None,
    privkey_hex: Optional[str] = None,
    address: Optional[str] = None,
    network: str = "mainnet",
    description: Optional[str] = None,
    tags: list[str] | str = "",
) -> MvxKeyEntry:
    """
    Create and encrypt a new MvxKeyEntry.

    At least one of seed_phrase or privkey_hex must be provided.

    Args:
        master_key:  AES-256 session key.
        label:       Human-readable name for this wallet entry.
        seed_phrase: BIP-39 mnemonic (12/15/18/21/24 words).
        privkey_hex: 64-char hex Ed25519 private key.
        address:     erd1... public address (optional, used as lookup hint).
        network:     mainnet | devnet | testnet.
        description: Free-text description.
        tags:        List or comma-separated string of tags.

    Returns:
        A fully populated MvxKeyEntry ready to be serialised.

    Raises:
        ValueError: If neither seed_phrase nor privkey_hex is provided,
                    or if validation of either fails.
    """
    if seed_phrase is None and privkey_hex is None:
        raise ValueError("Provide at least one of seed_phrase or privkey_hex.")

    entry_id = str(uuid.uuid4())
    entry = MvxKeyEntry(
        id=entry_id,
        label=label.strip(),
        address=address,
        network=network,
        description=description,
        tags=tags,
    )

    if seed_phrase is not None:
        phrase = validate_seed_phrase(seed_phrase)
        n_hex, c_hex = encrypt_mvx_seed(master_key, entry_id, phrase)
        entry.seed_nonce_hex = n_hex
        entry.seed_cipher_hex = c_hex

    if privkey_hex is not None:
        pk = validate_private_key_hex(privkey_hex)
        n_hex, c_hex = encrypt_mvx_privkey(master_key, entry_id, pk)
        entry.privkey_nonce_hex = n_hex
        entry.privkey_cipher_hex = c_hex

    return entry


def retrieve_mvx_seed(
    master_key: bytes,
    entry: MvxKeyEntry,
) -> str:
    """
    Decrypt and return the seed phrase for an entry.

    Raises:
        ValueError: Entry has no stored seed phrase.
        cryptography.exceptions.InvalidTag: Decryption/auth failure.
    """
    if not entry.has_seed:
        raise ValueError(f"Entry '{entry.label}' has no stored seed phrase.")
    return decrypt_mvx_seed(
        master_key,
        entry.id,
        entry.seed_nonce_hex,   # type: ignore[arg-type]
        entry.seed_cipher_hex,  # type: ignore[arg-type]
    )


def retrieve_mvx_privkey(
    master_key: bytes,
    entry: MvxKeyEntry,
) -> str:
    """
    Decrypt and return the private key hex for an entry.

    Raises:
        ValueError: Entry has no stored private key.
        cryptography.exceptions.InvalidTag: Decryption/auth failure.
    """
    if not entry.has_privkey:
        raise ValueError(f"Entry '{entry.label}' has no stored private key.")
    return decrypt_mvx_privkey(
        master_key,
        entry.id,
        entry.privkey_nonce_hex,   # type: ignore[arg-type]
        entry.privkey_cipher_hex,  # type: ignore[arg-type]
    )
