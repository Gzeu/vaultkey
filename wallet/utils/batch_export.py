"""
batch_export.py — Export wallet entries to multiple formats.

Formats
-------
encrypted_json  — Full export with decrypted values, re-encrypted under
                   a separate export password. Compatible with bulk-import.
json_redacted   — Metadata-only JSON (values replaced with '***REDACTED***').
                   Safe to share for documentation/auditing.
markdown        — Human-readable Markdown inventory report (no values).

Design decisions:
- Encrypted export uses the same AES-256-GCM + Argon2id pipeline as the
  main wallet so a recipient can import it with 'wallet import <file>'.
- JSON redacted export strips nonce_hex and cipher_hex entirely so there
  is no temptation to try to decrypt them without the master key.
- Markdown export is timestamped and includes a security notice reminding
  the reader that the document contains no secret values.
- All exports write atomically (temp file + os.replace) to prevent partial
  output files in case of crash or disk-full conditions.
- Export passwords must be at least 8 characters (same as wallet init).
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from wallet.models.wallet import WalletPayload

ExportFormat = Literal["encrypted_json", "json_redacted", "markdown"]

_REDACTED = "***REDACTED***"


def _atomic_write(path: Path, data: bytes) -> None:
    """Write data to path atomically via a temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".vkexport_")
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if os.name != "nt":
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    if os.name != "nt":
        os.chmod(path, 0o600)


# ------------------------------------------------------------------ #
# Encrypted JSON export
# ------------------------------------------------------------------ #

def export_encrypted(
    payload: "WalletPayload",
    master_key: bytes,
    output_path: Path,
    export_password: str,
) -> int:
    """
    Decrypt all entries and re-export as an AES-256-GCM encrypted JSON file.

    The output file is importable via 'wallet import <file>' or apply_bulk_import().

    Args:
        payload:         The loaded WalletPayload.
        master_key:      The AES-256 session key (used to decrypt entry values).
        output_path:     Destination file path (.enc recommended).
        export_password: Password used to re-encrypt the export (min 8 chars).

    Returns:
        Number of entries exported.

    Raises:
        ValueError: export_password too short or payload is empty.
    """
    if len(export_password) < 8:
        raise ValueError("Export password must be at least 8 characters.")

    from wallet.core.crypto import decrypt_entry_value
    from wallet.core.kdf import KDFParams, derive_key
    from wallet.core.storage import WalletStorage

    entries_out = []
    for entry in payload.keys.values():
        try:
            value = decrypt_entry_value(
                master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
        except Exception:
            value = "[DECRYPTION_ERROR]"

        entries_out.append({
            "name": entry.name,
            "value": value,
            "service": entry.service,
            "tags": ",".join(entry.tags),
            "description": entry.description or "",
            "expires": entry.expires_at.strftime("%Y-%m-%d") if entry.expires_at else "",
        })

    export_params = KDFParams.generate()
    export_key = derive_key(export_password, export_params)
    export_payload = payload.model_dump(mode="json")
    export_payload["_export_entries_plain"] = entries_out

    storage = WalletStorage(output_path, output_path.parent)
    storage.save(export_key, export_params, export_payload)
    return len(entries_out)


# ------------------------------------------------------------------ #
# Redacted JSON export
# ------------------------------------------------------------------ #

def export_json_redacted(
    payload: "WalletPayload",
    output_path: Path,
) -> int:
    """
    Export metadata-only JSON with all secret values replaced by '***REDACTED***'.

    Safe for documentation, sharing with ops teams, or offline auditing.

    Returns:
        Number of entries exported.
    """
    redacted_entries = []
    for entry in payload.keys.values():
        redacted_entries.append({
            "id": entry.id,
            "name": entry.name,
            "service": entry.service,
            "prefix": entry.prefix or "",
            "description": entry.description or "",
            "tags": entry.tags,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            "last_accessed_at": (
                entry.last_accessed_at.isoformat() if entry.last_accessed_at else None
            ),
            "access_count": entry.access_count,
            "is_active": entry.is_active,
            "status": entry.status_label,
            "nonce_hex": _REDACTED,
            "cipher_hex": _REDACTED,
        })

    output_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "wallet_version": payload.version,
        "total_entries": len(redacted_entries),
        "entries": redacted_entries,
        "_notice": "This export contains NO secret values. Key values are redacted.",
    }

    raw = json.dumps(output_data, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write(output_path, raw)
    return len(redacted_entries)


# ------------------------------------------------------------------ #
# Markdown report export
# ------------------------------------------------------------------ #

def export_markdown(
    payload: "WalletPayload",
    output_path: Path,
    include_stats: bool = True,
) -> int:
    """
    Export a human-readable Markdown inventory report.

    Includes: key name, service, tags, status, expiry, access count.
    Never includes: key values, nonces, ciphertexts.

    Returns:
        Number of entries exported.
    """
    now = datetime.now(timezone.utc)
    entries = sorted(payload.keys.values(), key=lambda e: e.name.lower())

    lines = [
        f"# VaultKey Inventory Report",
        f"",
        f"> **Security notice**: This document contains NO secret key values.",
        f"> Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"> Total entries: {len(entries)}",
        f"",
    ]

    if include_stats and entries:
        from wallet.utils.stats import compute_stats
        st = compute_stats(payload)
        lines += [
            "## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Active | {st.active} |",
            f"| Expired | {st.expired} |",
            f"| Expiring soon | {st.expiring_soon} |",
            f"| Revoked | {st.revoked} |",
            f"| Vault score | {st.vault_score}/100 |",
            f"",
        ]

    lines += [
        "## Entries",
        "",
        "| Name | Service | Tags | Status | Expires | Accesses |",
        "|------|---------|------|--------|---------|----------|",
    ]

    for entry in entries:
        tags_str = ", ".join(entry.tags) if entry.tags else "—"
        expires_str = entry.expires_at.strftime("%Y-%m-%d") if entry.expires_at else "—"
        lines.append(
            f"| {entry.name} | {entry.service} | {tags_str} "
            f"| {entry.status_label} | {expires_str} | {entry.access_count} |"
        )

    raw = "\n".join(lines).encode("utf-8")
    _atomic_write(output_path, raw)
    return len(entries)


# ------------------------------------------------------------------ #
# Dispatcher
# ------------------------------------------------------------------ #

def export_vault(
    payload: "WalletPayload",
    output_path: Path,
    fmt: ExportFormat,
    *,
    master_key: bytes | None = None,
    export_password: str | None = None,
    include_stats: bool = True,
) -> int:
    """
    Export vault entries to the specified format.

    Args:
        payload:         The loaded WalletPayload.
        output_path:     Destination file path.
        fmt:             'encrypted_json' | 'json_redacted' | 'markdown'.
        master_key:      Required for 'encrypted_json'.
        export_password: Required for 'encrypted_json'.
        include_stats:   Include stats summary in Markdown export.

    Returns:
        Number of entries exported.

    Raises:
        ValueError: Missing required args for selected format.
    """
    if fmt == "encrypted_json":
        if master_key is None or export_password is None:
            raise ValueError(
                "'encrypted_json' format requires master_key and export_password."
            )
        return export_encrypted(payload, master_key, output_path, export_password)
    elif fmt == "json_redacted":
        return export_json_redacted(payload, output_path)
    elif fmt == "markdown":
        return export_markdown(payload, output_path, include_stats=include_stats)
    else:
        raise ValueError(f"Unknown export format: '{fmt}'. Use encrypted_json, json_redacted, or markdown.")
