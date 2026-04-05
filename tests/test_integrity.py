"""
Tests for wallet/core/integrity.py — HMAC manifest and structural validation.
"""

import secrets

import pytest

from wallet.core.crypto import derive_entry_subkey, encrypt_entry_value
from wallet.core.integrity import (
    IntegrityError,
    compute_manifest,
    verify_integrity,
)
from wallet.models.wallet import APIKeyEntry, WalletPayload


def _make_payload(num_entries: int = 2) -> tuple[bytes, WalletPayload]:
    master = secrets.token_bytes(32)
    payload = WalletPayload(master_hash="dummy")
    for i in range(num_entries):
        nonce, cipher = encrypt_entry_value(master, f"entry-{i}", f"sk-fake-key-{i}" + "x" * 32)
        entry = APIKeyEntry(
            id=f"entry-{i}",
            name=f"Key {i}",
            service=f"svc{i}",
            nonce_hex=nonce.hex(),
            cipher_hex=cipher.hex(),
        )
        payload.keys[entry.id] = entry
    return master, payload


class TestComputeManifest:
    def test_deterministic(self):
        master, payload = _make_payload()
        assert compute_manifest(master, payload) == compute_manifest(master, payload)

    def test_different_master_different_manifest(self):
        _, payload = _make_payload()
        m1 = compute_manifest(secrets.token_bytes(32), payload)
        m2 = compute_manifest(secrets.token_bytes(32), payload)
        assert m1 != m2

    def test_adding_entry_changes_manifest(self):
        master, payload = _make_payload(1)
        m1 = compute_manifest(master, payload)
        nonce, cipher = encrypt_entry_value(master, "extra", "new-key-xxxxxxxxxxx" + "x" * 20)
        payload.keys["extra"] = APIKeyEntry(
            id="extra", name="Extra", service="svc",
            nonce_hex=nonce.hex(), cipher_hex=cipher.hex()
        )
        m2 = compute_manifest(master, payload)
        assert m1 != m2

    def test_tampered_cipher_changes_manifest(self):
        master, payload = _make_payload(1)
        m1 = compute_manifest(master, payload)
        entry = next(iter(payload.keys.values()))
        entry.cipher_hex = "ff" * 48
        m2 = compute_manifest(master, payload)
        assert m1 != m2


class TestVerifyIntegrity:
    def test_valid_manifest_passes(self):
        master, payload = _make_payload()
        payload.integrity_hmac = compute_manifest(master, payload)
        report = verify_integrity(master, payload)
        assert report.ok
        assert report.hmac_valid is True

    def test_tampered_manifest_fails(self):
        master, payload = _make_payload()
        payload.integrity_hmac = "deadbeef" * 8
        report = verify_integrity(master, payload)
        assert not report.ok
        assert report.hmac_valid is False

    def test_no_manifest_warns_but_passes_structurally(self):
        master, payload = _make_payload()
        payload.integrity_hmac = None
        report = verify_integrity(master, payload)
        assert report.ok  # structural ok
        assert report.hmac_valid is None
        assert not report.manifest_present

    def test_strict_mode_raises(self):
        master, payload = _make_payload()
        payload.integrity_hmac = "badhash" * 8
        with pytest.raises(IntegrityError):
            verify_integrity(master, payload, strict=True)

    def test_structural_bad_nonce_detected(self):
        master, payload = _make_payload(1)
        entry = next(iter(payload.keys.values()))
        entry.nonce_hex = "zzzz"   # invalid hex
        report = verify_integrity(master, payload)
        assert not report.ok
        assert any("nonce" in e.lower() for e in report.structural_errors)

    def test_structural_id_mismatch_detected(self):
        master, payload = _make_payload(1)
        entry = next(iter(payload.keys.values()))
        entry.id = "wrong-id"  # doesn't match dict key
        report = verify_integrity(master, payload)
        assert not report.ok
        assert any("mismatch" in e.lower() for e in report.structural_errors)
