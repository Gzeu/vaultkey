"""
conftest.py — Shared pytest fixtures for VaultKey test suite.

All fixtures here are available to every test file without explicit import.

Fixtures:
  password          — standard test master password
  kdf_params        — KDFParams generated once per session (slow, Argon2id)
  master_key        — derived key bytes (session-scoped, keyed on params)
  fresh_storage     — WalletStorage in tmp_path (function-scoped)
  empty_payload     — WalletPayload with master_hash, no entries
  payload_with_keys — WalletPayload with 3 pre-populated APIKeyEntry objects
  fresh_session     — SessionManager reset to locked state
  saved_wallet      — Storage + key + payload already saved to disk

Design decisions:
- kdf_params is session-scoped: Argon2id at 64MB takes ~200ms, expensive per test.
  Session scope means it runs once per pytest invocation, not per test.
- master_key is also session-scoped for the same reason.
- Payloads and storage are function-scoped so tests are fully isolated.
- Session is reset (locked, counters cleared) in a fixture to prevent state
  leakage between tests (SessionManager is a process-wide singleton).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

import pytest

from wallet.core.crypto import encrypt_entry_value
from wallet.core.kdf import KDFParams, derive_key, hash_master_password
from wallet.core.session import SessionManager
from wallet.core.storage import WalletStorage
from wallet.models.wallet import APIKeyEntry, WalletPayload


# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

TEST_PASSWORD = "correct-horse-battery-staple-42"
FAKE_KEY_VALUE = "sk-test-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


# ------------------------------------------------------------------ #
# KDF (session-scoped — expensive Argon2id, run once per invocation)
# ------------------------------------------------------------------ #

@pytest.fixture(scope="session")
def password() -> str:
    return TEST_PASSWORD


@pytest.fixture(scope="session")
def kdf_params() -> KDFParams:
    """Generate KDFParams once per test session (Argon2id is slow)."""
    return KDFParams.generate()


@pytest.fixture(scope="session")
def master_key(kdf_params: KDFParams, password: str) -> bytes:
    """Derive master key once per session."""
    return derive_key(password, kdf_params)


# ------------------------------------------------------------------ #
# Storage (function-scoped — fresh tmp_path per test)
# ------------------------------------------------------------------ #

@pytest.fixture()
def fresh_storage(tmp_path: Path) -> WalletStorage:
    """WalletStorage pointing to a fresh temporary directory."""
    return WalletStorage(
        wallet_path=tmp_path / "wallet.enc",
        backup_dir=tmp_path / "backups",
    )


@pytest.fixture()
def empty_payload(password: str) -> WalletPayload:
    """WalletPayload with master_hash, zero entries."""
    return WalletPayload(master_hash=hash_master_password(password))


# ------------------------------------------------------------------ #
# Entries helper
# ------------------------------------------------------------------ #

def make_entry(
    master_key: bytes,
    *,
    name: str = "Test Key",
    service: str = "openai",
    value: str = FAKE_KEY_VALUE,
    tags: str = "test,ci",
    days_until_expiry: int | None = None,
    already_expired: bool = False,
    access_count: int = 0,
) -> APIKeyEntry:
    """Create a fully-encrypted APIKeyEntry for use in tests."""
    entry_id = str(uuid.uuid4())
    nonce, cipher = encrypt_entry_value(master_key, entry_id, value)
    expires_at = None
    if days_until_expiry is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=days_until_expiry)
    if already_expired:
        expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    entry = APIKeyEntry(
        id=entry_id,
        name=name,
        service=service,
        nonce_hex=nonce.hex(),
        cipher_hex=cipher.hex(),
        prefix=value[:8],
        tags=tags,
        expires_at=expires_at,
    )
    entry.access_count = access_count
    return entry


@pytest.fixture()
def payload_with_keys(master_key: bytes, password: str) -> WalletPayload:
    """WalletPayload pre-populated with 3 entries covering different states."""
    payload = WalletPayload(master_hash=hash_master_password(password))
    payload.add_entry(make_entry(master_key, name="Active Key", service="anthropic",
                                  tags="prod,ml"))
    payload.add_entry(make_entry(master_key, name="Expiring Key", service="openai",
                                  tags="staging", days_until_expiry=5))
    payload.add_entry(make_entry(master_key, name="Expired Key", service="cohere",
                                  tags="old", already_expired=True))
    return payload


# ------------------------------------------------------------------ #
# Session (function-scoped — always reset to locked)
# ------------------------------------------------------------------ #

@pytest.fixture()
def fresh_session() -> Generator[SessionManager, None, None]:
    """SessionManager reset to locked state with cleared failure counters."""
    sm = SessionManager()
    sm.lock(reason="conftest-reset")
    sm._failed_attempts = 0
    sm._last_failed_at = None
    yield sm
    sm.lock(reason="conftest-teardown")
    sm._failed_attempts = 0
    sm._last_failed_at = None


# ------------------------------------------------------------------ #
# Saved wallet (convenience: storage + key + payload on disk)
# ------------------------------------------------------------------ #

@pytest.fixture()
def saved_wallet(
    fresh_storage: WalletStorage,
    kdf_params: KDFParams,
    master_key: bytes,
    payload_with_keys: WalletPayload,
) -> tuple[WalletStorage, KDFParams, bytes, WalletPayload]:
    """Storage with payload_with_keys already saved to disk."""
    fresh_storage.save(master_key, kdf_params, payload_with_keys.to_dict())
    return fresh_storage, kdf_params, master_key, payload_with_keys
