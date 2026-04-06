"""
bulk_import.py — Import API keys from .env / JSON / CSV files (Wave 7).

Supported formats
-----------------
.env  — KEY_NAME=value (lines starting with # are skipped)
.json — [{"name": ..., "value": ..., "service": ..., "tags": ...,
           "description": ..., "expires": "YYYY-MM-DD"}]
.csv  — header row: name,value,service,tags,description,expires
        All columns except name and value are optional.

Conflict strategies
-------------------
skip       — silently ignore duplicates
overwrite  — replace existing entry in-place (new nonce)
rename     — append _imported_N suffix until name is free

Returns a BulkImportResult with per-entry outcomes for reporting.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from wallet.models.wallet import WalletPayload

ConflictStrategy = Literal["skip", "overwrite", "rename"]


@dataclass
class RawEntry:
    """Parsed entry before encryption."""
    name: str
    value: str
    service: str = ""
    tags: str = ""
    description: str = ""
    expires: str = ""       # YYYY-MM-DD string; empty = no expiry


@dataclass
class BulkImportResult:
    added: int = 0
    skipped: int = 0
    overwritten: int = 0
    renamed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.added + self.skipped + self.overwritten + self.renamed


# ------------------------------------------------------------------ #
# Parsers
# ------------------------------------------------------------------ #

def _parse_env(text: str) -> list[RawEntry]:
    """Parse KEY=value lines. KEY becomes both name and (lowercased) service."""
    entries: list[RawEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            entries.append(RawEntry(
                name=key,
                value=value,
                service=key.lower().replace("_api_key", "").replace("_", "-"),
            ))
    return entries


def _parse_json(text: str) -> list[RawEntry]:
    """Parse a JSON array of objects."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    if not isinstance(data, list):
        raise ValueError("JSON must be an array of objects.")
    entries: list[RawEntry] = []
    for i, obj in enumerate(data):
        if not isinstance(obj, dict):
            raise ValueError(f"Item {i} is not an object.")
        name = str(obj.get("name", "")).strip()
        value = str(obj.get("value", "")).strip()
        if not name or not value:
            raise ValueError(f"Item {i} missing required 'name' or 'value'.")
        entries.append(RawEntry(
            name=name,
            value=value,
            service=str(obj.get("service", "")).strip(),
            tags=str(obj.get("tags", "")).strip(),
            description=str(obj.get("description", "")).strip(),
            expires=str(obj.get("expires", "")).strip(),
        ))
    return entries


def _parse_csv(text: str) -> list[RawEntry]:
    """Parse CSV with header row. Required columns: name, value."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV file is empty.")
    fieldnames_lower = [f.lower().strip() for f in reader.fieldnames]
    if "name" not in fieldnames_lower or "value" not in fieldnames_lower:
        raise ValueError("CSV must have 'name' and 'value' columns.")
    entries: list[RawEntry] = []
    for i, row in enumerate(reader, start=2):
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        name = row_lower.get("name", "").strip()
        value = row_lower.get("value", "").strip()
        if not name or not value:
            raise ValueError(f"Row {i}: missing 'name' or 'value'.")
        entries.append(RawEntry(
            name=name,
            value=value,
            service=row_lower.get("service", ""),
            tags=row_lower.get("tags", ""),
            description=row_lower.get("description", ""),
            expires=row_lower.get("expires", ""),
        ))
    return entries


def parse_file(path: Path) -> list[RawEntry]:
    """
    Auto-detect format from extension and parse file.

    Raises:
        ValueError: Unknown extension or parse error.
    """
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".env" or path.name.startswith(".env"):
        return _parse_env(text)
    if suffix == ".json":
        return _parse_json(text)
    if suffix == ".csv":
        return _parse_csv(text)
    raise ValueError(
        f"Unsupported file type '{suffix}'. Use .env, .json, or .csv."
    )


# ------------------------------------------------------------------ #
# Importer
# ------------------------------------------------------------------ #

def apply_bulk_import(
    raw_entries: list[RawEntry],
    payload: "WalletPayload",
    encryption_key: bytes,
    strategy: ConflictStrategy = "rename",
) -> BulkImportResult:
    """
    Encrypt and insert raw entries into `payload`.

    Mutates `payload` in-place. Caller is responsible for saving.

    Args:
        raw_entries:    Parsed entries from parse_file().
        payload:        The loaded WalletPayload to insert into.
        encryption_key: Session-derived key for encrypt_entry_value().
        strategy:       Conflict resolution: skip | overwrite | rename.

    Returns:
        BulkImportResult with counters and any error messages.
    """
    import uuid
    from datetime import datetime, timezone

    from wallet.core.crypto import encrypt_entry_value
    from wallet.models.wallet import APIKeyEntry
    from wallet.utils.validators import parse_expiry_date, validate_key_name

    result = BulkImportResult()

    for raw in raw_entries:
        try:
            name = validate_key_name(raw.name)
        except ValueError as e:
            result.errors.append(f"{raw.name!r}: invalid name — {e}")
            continue

        existing = payload.get_entry(name)
        final_name = name

        if existing:
            if strategy == "skip":
                result.skipped += 1
                continue
            elif strategy == "overwrite":
                # Re-encrypt in-place under existing UUID
                nonce, cipher = encrypt_entry_value(
                    encryption_key, existing.id, raw.value
                )
                existing.nonce_hex = nonce.hex()
                existing.cipher_hex = cipher.hex()
                existing.updated_at = datetime.now(timezone.utc)
                if raw.service:
                    existing.service = raw.service
                payload.touch()
                result.overwritten += 1
                continue
            else:  # rename
                n = 1
                final_name = f"{name}_imported_1"
                while payload.get_entry(final_name):
                    n += 1
                    final_name = f"{name}_imported_{n}"
                result.renamed += 1
        else:
            result.added += 1

        entry_id = str(uuid.uuid4())
        nonce, cipher = encrypt_entry_value(encryption_key, entry_id, raw.value)

        entry = APIKeyEntry(
            id=entry_id,
            name=final_name,
            service=raw.service or final_name.lower().replace(" ", "-"),
            nonce_hex=nonce.hex(),
            cipher_hex=cipher.hex(),
            prefix=raw.value[:8] if raw.value else "",
            description=raw.description or None,
            tags=raw.tags,
            expires_at=parse_expiry_date(raw.expires) if raw.expires else None,
        )
        payload.add_entry(entry)

    return result
