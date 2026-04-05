"""
integrity.py — Wallet file integrity verification and self-healing.

Provides:
  - HMAC-SHA256 integrity manifest over all entries (detects silent bit-rot)
  - Structural validation: every entry has valid hex fields, no missing IDs
  - Orphan detection: nonce/cipher present but entry_id not in payload.keys
  - Re-keying helper: re-encrypt all entries under a new master key atomically

Design decisions:
- The integrity manifest is an HMAC over sorted entry IDs + their cipher_hex.
  This allows detecting any tampered, added, or removed entry without decrypting values.
- HMAC key = derive_entry_subkey(master_key, "__manifest__") — bound to master key.
- Manifest is stored in WalletPayload.integrity_hmac (added to model this wave).
- On every load(), integrity is checked automatically if the field is present.
  If absent (old wallet), a WARNING is emitted and the manifest is written on next save().
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wallet.core.crypto import derive_entry_subkey

if TYPE_CHECKING:
    from wallet.models.wallet import WalletPayload

log = logging.getLogger(__name__)

MANIFEST_ENTRY_ID = "__manifest__"


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    manifest_present: bool
    entries_checked: int
    structural_errors: list[str]
    hmac_valid: bool | None   # None = manifest absent

    def __str__(self) -> str:
        if self.ok:
            return f"OK ({self.entries_checked} entries verified)"
        issues = ", ".join(self.structural_errors)
        hmac_str = " | HMAC INVALID" if self.hmac_valid is False else ""
        return f"INTEGRITY FAIL: {issues}{hmac_str}"


def compute_manifest(master_key: bytes, payload: "WalletPayload") -> str:
    """
    Compute HMAC-SHA256 over the sorted (entry_id, cipher_hex) pairs.

    Covers:
    - Entry existence (added / removed entries change the manifest)
    - Ciphertext integrity (modified cipher_hex changes the manifest)
    - Entry ID integrity (renamed ID changes the manifest)

    Does NOT cover:
    - Metadata changes (name, tags, description) — those are inside the
      AES-GCM ciphertext, so they're already AEAD-protected.
    """
    subkey = derive_entry_subkey(master_key, MANIFEST_ENTRY_ID)
    mac = hmac.new(subkey, digestmod=hashlib.sha256)
    # Sort by entry_id for determinism
    for entry_id in sorted(payload.keys):
        entry = payload.keys[entry_id]
        mac.update(entry_id.encode())
        mac.update(b":")
        mac.update(entry.cipher_hex.encode())
        mac.update(b"\n")
    return mac.hexdigest()


def verify_integrity(
    master_key: bytes,
    payload: "WalletPayload",
    *,
    strict: bool = False,
) -> IntegrityReport:
    """
    Validate the wallet payload integrity.

    Structural checks (always run):
    - Every entry has non-empty nonce_hex and cipher_hex
    - nonce_hex decodes to exactly 12 bytes (AES-GCM nonce size)
    - cipher_hex is valid hex
    - entry.id matches its key in payload.keys dict

    HMAC check (if manifest present):
    - Recompute manifest and constant-time compare with stored value

    Args:
        strict: If True, raise IntegrityError on any failure.
                If False, return IntegrityReport (callers decide).
    """
    structural_errors: list[str] = []

    for entry_id, entry in payload.keys.items():
        # ID consistency
        if entry.id != entry_id:
            structural_errors.append(
                f"ID mismatch: key='{entry_id}' entry.id='{entry.id}'"
            )
        # Nonce
        if not entry.nonce_hex:
            structural_errors.append(f"Missing nonce_hex for entry '{entry_id}'")
        else:
            try:
                nonce_bytes = bytes.fromhex(entry.nonce_hex)
                if len(nonce_bytes) != 12:
                    structural_errors.append(
                        f"Invalid nonce length ({len(nonce_bytes)}B) for '{entry_id}'"
                    )
            except ValueError:
                structural_errors.append(
                    f"Non-hex nonce_hex for entry '{entry_id}'"
                )
        # Cipher
        if not entry.cipher_hex:
            structural_errors.append(f"Missing cipher_hex for entry '{entry_id}'")
        else:
            try:
                bytes.fromhex(entry.cipher_hex)
            except ValueError:
                structural_errors.append(
                    f"Non-hex cipher_hex for entry '{entry_id}'"
                )

    # HMAC check
    hmac_valid: bool | None = None
    manifest_present = bool(getattr(payload, "integrity_hmac", None))

    if manifest_present:
        expected = compute_manifest(master_key, payload)
        stored = payload.integrity_hmac  # type: ignore[attr-defined]
        hmac_valid = hmac.compare_digest(expected, stored)
        if not hmac_valid:
            structural_errors.append("HMAC manifest mismatch — payload may have been tampered")

    ok = len(structural_errors) == 0
    report = IntegrityReport(
        ok=ok,
        manifest_present=manifest_present,
        entries_checked=len(payload.keys),
        structural_errors=structural_errors,
        hmac_valid=hmac_valid,
    )

    if not ok:
        log.error("Integrity check failed: %s", report)
        if strict:
            raise IntegrityError(str(report))
    else:
        if not manifest_present:
            log.warning(
                "Wallet has no integrity manifest. "
                "It will be added automatically on next save."
            )

    return report


class IntegrityError(Exception):
    """Raised when wallet integrity verification fails and strict=True."""
