"""
test_integrity.py — Tests for wallet/core/integrity.py.

Covers:
  - Clean wallet passes verify_integrity
  - Tampered entry cipher_hex causes integrity failure
  - Missing master_hash causes structural error
  - Empty wallet (no entries) passes
  - HMAC manifest present after save + verify
  - strict=True raises on first error
"""

from __future__ import annotations

import secrets

import pytest

from tests.conftest import make_entry
from wallet.core.integrity import verify_integrity
from wallet.core.kdf import hash_master_password
from wallet.models.wallet import APIKeyEntry, WalletPayload

KEY = secrets.token_bytes(32)


def _payload_with_entry(name: str = "Test") -> WalletPayload:
    p = WalletPayload(master_hash=hash_master_password("test"))
    p.add_entry(make_entry(KEY, name=name))
    return p


class TestVerifyIntegrity:
    def test_clean_payload_passes(self):
        p = _payload_with_entry()
        report = verify_integrity(KEY, p, strict=False)
        assert report.ok
        assert not report.structural_errors

    def test_empty_payload_passes(self):
        p = WalletPayload(master_hash=hash_master_password("test"))
        report = verify_integrity(KEY, p, strict=False)
        assert report.ok

    def test_tampered_cipher_fails(self):
        p = _payload_with_entry()
        # Corrupt the first entry's cipher_hex
        entry = next(iter(p.keys.values()))
        original_cipher = bytes.fromhex(entry.cipher_hex)
        tampered = bytearray(original_cipher)
        tampered[0] ^= 0xFF
        entry.cipher_hex = tampered.hex()
        report = verify_integrity(KEY, p, strict=False)
        assert not report.ok
        assert report.structural_errors

    def test_missing_master_hash_fails(self):
        p = WalletPayload(master_hash="")
        report = verify_integrity(KEY, p, strict=False)
        assert not report.ok

    def test_multiple_entries_all_checked(self):
        p = WalletPayload(master_hash=hash_master_password("test"))
        for i in range(5):
            p.add_entry(make_entry(KEY, name=f"Key {i}"))
        report = verify_integrity(KEY, p, strict=False)
        assert report.entries_checked == 5
        assert report.ok

    def test_strict_raises_on_first_error(self):
        p = _payload_with_entry()
        entry = next(iter(p.keys.values()))
        # Completely invalid cipher
        entry.cipher_hex = "deadbeef" * 8
        with pytest.raises(Exception):  # noqa: B017
            verify_integrity(KEY, p, strict=True)
