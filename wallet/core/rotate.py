"""
rotate.py — Bulk key rotation helpers for VaultKey.

Provides:
  rotate_single(payload, master_key, entry_id, new_value) -> APIKeyEntry
      Re-encrypts one entry with a brand-new nonce.  Old cipher is
      overwritten; the rotation is recorded in the audit log.

  rotate_all(payload, master_key, storage) -> RotateReport
      Re-encrypts EVERY entry with fresh nonces and re-saves the wallet.
      Useful after a master-password change or suspected key material leak.

  RotateReport — dataclass with per-entry results.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from wallet.core.crypto import decrypt_entry_value, encrypt_entry_value
from wallet.core.storage import WalletStorage
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.audit import log_event


@dataclass
class RotateResult:
    entry_id: str
    name: str
    success: bool
    error: Optional[str] = None


@dataclass
class RotateReport:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    results: list[RotateResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def total(self) -> int:
        return len(self.results)


def rotate_single(
    payload: WalletPayload,
    master_key: bytes,
    entry_id: str,
    new_value: str,
) -> APIKeyEntry:
    """
    Re-encrypt a single entry with a new value and a fresh nonce.
    Raises KeyError if entry_id is not found.
    """
    entry = payload.get_entry(entry_id)
    if entry is None:
        raise KeyError(f"Entry not found: {entry_id}")

    nonce, cipher = encrypt_entry_value(master_key, entry_id, new_value)
    entry.nonce_hex = nonce.hex()
    entry.cipher_hex = cipher.hex()
    entry.rotated_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]

    log_event(
        event="KEY_ROTATED",
        status="OK",
        key_name=entry.name,
        extra=f"entry_id={entry_id[:8]}...",
    )
    return entry


def rotate_all(
    payload: WalletPayload,
    master_key: bytes,
    storage: WalletStorage,
) -> RotateReport:
    """
    Re-encrypt every entry with a fresh nonce and persist immediately.
    Safe to interrupt — partial progress is NOT saved; the wallet is
    only written once all entries succeed.
    """
    report = RotateReport()
    scratch: dict[str, tuple[bytes, bytes]] = {}  # entry_id -> (nonce, cipher)

    for entry in payload.entries:
        try:
            # Decrypt current value
            plain = decrypt_entry_value(
                master_key,
                entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
            # Re-encrypt with brand-new nonce
            nonce, cipher = encrypt_entry_value(master_key, entry.id, plain)
            scratch[entry.id] = (nonce, cipher)
            report.results.append(RotateResult(entry.id, entry.name, success=True))
        except Exception as exc:  # noqa: BLE001
            report.results.append(
                RotateResult(entry.id, entry.name, success=False, error=str(exc))
            )

    if report.failed == 0:
        # Apply all changes atomically in memory, then write once
        for entry in payload.entries:
            nonce, cipher = scratch[entry.id]
            entry.nonce_hex = nonce.hex()
            entry.cipher_hex = cipher.hex()
        storage.save(payload.to_dict(), master_key)
        log_event(
            event="ROTATE_ALL",
            status="OK",
            extra=f"rotated={report.total}",
        )
    else:
        log_event(
            event="ROTATE_ALL",
            status="PARTIAL_FAIL",
            extra=f"ok={report.succeeded} fail={report.failed}",
        )

    report.finished_at = datetime.now(timezone.utc)
    return report
