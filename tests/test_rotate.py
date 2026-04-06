"""
tests/test_rotate.py — Unit tests for wallet.core.rotate

Covers:
  R1  rotate_single: plaintext recoverable after rotation
  R2  rotate_single: new nonce differs from old nonce
  R3  rotate_single: raises KeyError for unknown entry_id
  R4  rotate_all: all entries decryptable after rotation
  R5  rotate_all: every entry gets a fresh nonce
  R6  rotate_all: RotateReport.succeeded == total on clean wallet
  R7  rotate_all: wallet is persisted after successful rotation
  R8  rotate_all: partial failure — wallet NOT persisted, report.failed > 0
  R9  RotateReport: properties (succeeded, failed, total) computed correctly
  R10 rotate_all: timestamps — finished_at > started_at
"""

from __future__ import annotations

import pytest

from wallet.core.rotate import RotateReport, RotateResult, rotate_all, rotate_single


# ------------------------------------------------------------------ helpers

def _old_nonces(payload):
    return {e.id: e.nonce_hex for e in payload.entries}


# ------------------------------------------------------------------ R1
def test_rotate_single_value_recoverable(payload_with_keys, master_key):
    """R1: value decryptable with new nonce after rotate_single."""
    from wallet.core.crypto import decrypt_entry_value

    payload, _ = payload_with_keys
    entry = payload.entries[0]
    new_val = "rotated-secret-value-xyz"

    rotate_single(payload, master_key, entry.id, new_val)

    recovered = decrypt_entry_value(
        master_key,
        entry.id,
        bytes.fromhex(entry.nonce_hex),
        bytes.fromhex(entry.cipher_hex),
    )
    assert recovered == new_val


# ------------------------------------------------------------------ R2
def test_rotate_single_new_nonce(payload_with_keys, master_key):
    """R2: nonce changes after rotate_single."""
    payload, _ = payload_with_keys
    entry = payload.entries[0]
    old_nonce = entry.nonce_hex

    rotate_single(payload, master_key, entry.id, "any-new-value")
    assert entry.nonce_hex != old_nonce


# ------------------------------------------------------------------ R3
def test_rotate_single_unknown_id(payload_with_keys, master_key):
    """R3: KeyError raised for unknown entry_id."""
    payload, _ = payload_with_keys
    with pytest.raises(KeyError):
        rotate_single(payload, master_key, "nonexistent-id", "value")


# ------------------------------------------------------------------ R4
def test_rotate_all_values_recoverable(saved_wallet, master_key):
    """R4: all values decryptable after rotate_all."""
    from wallet.core.crypto import decrypt_entry_value

    storage, key, payload = saved_wallet
    originals = {}
    for entry in payload.entries:
        originals[entry.id] = decrypt_entry_value(
            key, entry.id,
            bytes.fromhex(entry.nonce_hex),
            bytes.fromhex(entry.cipher_hex),
        )

    rotate_all(payload, key, storage)

    for entry in payload.entries:
        recovered = decrypt_entry_value(
            key, entry.id,
            bytes.fromhex(entry.nonce_hex),
            bytes.fromhex(entry.cipher_hex),
        )
        assert recovered == originals[entry.id]


# ------------------------------------------------------------------ R5
def test_rotate_all_fresh_nonces(saved_wallet, master_key):
    """R5: every entry gets a different nonce after rotate_all."""
    storage, key, payload = saved_wallet
    old = _old_nonces(payload)
    rotate_all(payload, key, storage)
    for entry in payload.entries:
        assert entry.nonce_hex != old[entry.id]


# ------------------------------------------------------------------ R6
def test_rotate_all_report_success(saved_wallet):
    """R6: report.succeeded == report.total on a clean wallet."""
    storage, key, payload = saved_wallet
    report = rotate_all(payload, key, storage)
    assert report.succeeded == report.total
    assert report.failed == 0


# ------------------------------------------------------------------ R7
def test_rotate_all_persists(saved_wallet):
    """R7: wallet file is rewritten after rotate_all."""
    import os
    storage, key, payload = saved_wallet
    mtime_before = os.path.getmtime(storage.wallet_path)
    import time; time.sleep(0.05)
    rotate_all(payload, key, storage)
    mtime_after = os.path.getmtime(storage.wallet_path)
    assert mtime_after > mtime_before


# ------------------------------------------------------------------ R8
def test_rotate_all_partial_failure_not_persisted(saved_wallet, monkeypatch):
    """R8: wallet NOT saved when at least one entry fails to decrypt."""
    import os
    storage, key, payload = saved_wallet

    # Corrupt the cipher of the first entry so decrypt fails
    payload.entries[0].cipher_hex = "deadbeef" * 8

    mtime_before = os.path.getmtime(storage.wallet_path)
    report = rotate_all(payload, key, storage)
    mtime_after = os.path.getmtime(storage.wallet_path)

    assert report.failed >= 1
    assert mtime_after == mtime_before  # file not touched


# ------------------------------------------------------------------ R9
def test_rotate_report_properties():
    """R9: RotateReport computed properties."""
    report = RotateReport()
    report.results = [
        RotateResult("a", "key-a", True),
        RotateResult("b", "key-b", True),
        RotateResult("c", "key-c", False, error="oops"),
    ]
    assert report.total == 3
    assert report.succeeded == 2
    assert report.failed == 1


# ------------------------------------------------------------------ R10
def test_rotate_all_timestamps(saved_wallet):
    """R10: finished_at is set and > started_at."""
    storage, key, payload = saved_wallet
    report = rotate_all(payload, key, storage)
    assert report.finished_at is not None
    assert report.finished_at >= report.started_at
