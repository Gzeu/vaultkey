"""
tests/helpers.py — Shared test factory helpers.

Kept separate from conftest.py so pytest does not try to auto-collect
this module as a test file, and so it can be imported cleanly from
any test module: `from tests.helpers import make_entry`.

FIX (Wave 6 / F4): make_entry moved here from test_health.py inline
definition. Previously each file that needed an APIKeyEntry had to
define its own factory. Centralising avoids drift between test files.
"""

import uuid
from datetime import datetime, timezone

from wallet.models.wallet import APIKeyEntry


def make_entry(
    *,
    name: str = "Test Key",
    service: str = "test",
    is_active: bool = True,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
    last_used_at: datetime | None = None,
    rotation_days: int = 90,
    tags: str = "",
    description: str = "",
) -> APIKeyEntry:
    """
    Create a minimal APIKeyEntry for use in tests.

    Crypto fields (nonce_hex, cipher_hex, prefix) are set to valid
    placeholder values so structural integrity checks pass without
    requiring a real encryption round-trip.
    """
    entry_id = str(uuid.uuid4())
    nonce = bytes(12)  # 12-byte zero nonce — structurally valid
    cipher = bytes(32)  # 32-byte zero ciphertext — structurally valid
    return APIKeyEntry(
        id=entry_id,
        name=name,
        service=service,
        nonce_hex=nonce.hex(),
        cipher_hex=cipher.hex(),
        prefix="sk-test12",
        description=description,
        tags=tags,
        expires_at=expires_at,
        created_at=created_at or datetime.now(timezone.utc),
        last_used_at=last_used_at,
        is_active=is_active,
        rotation_days=rotation_days,
    )
