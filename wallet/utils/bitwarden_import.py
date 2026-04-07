"""
bitwarden_import.py — Import from Bitwarden JSON, 1Password CSV, and KeePass CSV.

Supported formats
-----------------
Bitwarden  — exported JSON (File > Export Vault > .json, unencrypted)
1Password  — exported CSV (File > Export > All Items > .csv)
KeePass    — exported CSV (File > Export > KeePass CSV (.csv))

All three formats are auto-detected from file extension and content.
Loginitems map to APIKeyEntry with the password as the secret value.
Secure-note items map with the note body as the secret value.
Fields not directly representable are stored in the description.

Returns a list[RawEntry] compatible with apply_bulk_import() in bulk_import.py
so the same conflict-resolution and encryption pipeline is reused.

Design decisions:
- Bitwarden JSON 'login.password' or 'notes' is used as the key value.
- 1Password CSV columns: Title, Username, Password, URL, Notes, Type.
- KeePass CSV columns: Title, UserName, Password, URL, Notes, Group.
- Passwords are the secret values — usernames and URLs go into description.
- TOTP seeds (if present in Bitwarden 'login.totp') are preserved in
  description as 'totp:<seed>' so they can be migrated manually.
- Folder/group names are mapped to tags for easy filtering.
- Items without a usable secret value are skipped with a warning.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Re-use RawEntry from bulk_import so apply_bulk_import() can consume our output
from wallet.utils.bulk_import import RawEntry

SourceFormat = Literal["bitwarden", "1password", "keepass", "auto"]


@dataclass
class ImportWarning:
    item_title: str
    reason: str


@dataclass
class ExternalImportResult:
    entries: list[RawEntry] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)


# ------------------------------------------------------------------ #
# Bitwarden JSON
# ------------------------------------------------------------------ #

def _parse_bitwarden_json(text: str) -> ExternalImportResult:
    """
    Parse a Bitwarden unencrypted JSON export.

    Bitwarden export schema (relevant fields):
    {
      "items": [
        {
          "name": str,
          "type": 1 (Login) | 2 (Secure Note) | 3 (Card) | 4 (Identity),
          "notes": str | null,
          "folderId": str | null,
          "login": {
            "username": str | null,
            "password": str | null,
            "uris": [{"uri": str}],
            "totp": str | null
          }
        }
      ],
      "folders": [{"id": str, "name": str}]
    }
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid Bitwarden JSON: {e}") from e

    if not isinstance(data, dict) or "items" not in data:
        raise ValueError(
            "Not a Bitwarden export: missing top-level 'items' key."
        )

    # Build folder id → name lookup
    folders: dict[str, str] = {}
    for folder in data.get("folders", []):
        fid = folder.get("id", "")
        fname = folder.get("name", "")
        if fid and fname:
            folders[fid] = fname

    result = ExternalImportResult()

    for item in data["items"]:
        title = str(item.get("name", "")).strip() or "Untitled"
        item_type = item.get("type", 0)
        notes = str(item.get("notes") or "").strip()
        folder_id = item.get("folderId", "")
        folder_name = folders.get(folder_id or "", "")

        # Determine secret value
        secret_value = ""
        description_parts: list[str] = []

        if item_type == 1:  # Login
            login = item.get("login") or {}
            secret_value = str(login.get("password") or "").strip()
            username = str(login.get("username") or "").strip()
            uris = login.get("uris") or []
            url = str(uris[0].get("uri", "")) if uris else ""
            totp_seed = str(login.get("totp") or "").strip()

            if username:
                description_parts.append(f"username:{username}")
            if url:
                description_parts.append(f"url:{url}")
            if totp_seed:
                description_parts.append(f"totp:{totp_seed}")
            if notes:
                description_parts.append(notes)

        elif item_type == 2:  # Secure Note
            secret_value = notes
            notes = ""  # already used as value

        else:
            # Cards (3) and Identities (4) — skip with warning
            result.warnings.append(ImportWarning(
                item_title=title,
                reason=f"Skipped: type {item_type} (Card/Identity) not supported.",
            ))
            continue

        if not secret_value:
            result.warnings.append(ImportWarning(
                item_title=title,
                reason="Skipped: no usable secret value (empty password/note).",
            ))
            continue

        tags = folder_name.lower().replace(" ", "-") if folder_name else ""
        description = " | ".join(description_parts) if description_parts else ""

        result.entries.append(RawEntry(
            name=title,
            value=secret_value,
            service=title.lower().replace(" ", "-"),
            tags=tags,
            description=description,
        ))

    return result


# ------------------------------------------------------------------ #
# 1Password CSV
# ------------------------------------------------------------------ #

def _parse_1password_csv(text: str) -> ExternalImportResult:
    """
    Parse a 1Password CSV export.

    Expected columns (case-insensitive): Title, Username, Password, URL, Notes, Type
    The 'Type' column may contain: Login, Secure Note, etc.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("1Password CSV is empty.")

    # Normalise column names to lowercase
    norm_fields = {f.strip().lower() for f in reader.fieldnames}
    required = {"title", "password"}
    if not required.issubset(norm_fields):
        raise ValueError(
            f"1Password CSV missing required columns. "
            f"Found: {sorted(norm_fields)}. Required: {sorted(required)}."
        )

    result = ExternalImportResult()

    for row in reader:
        norm_row = {k.strip().lower(): v for k, v in row.items()}
        title = norm_row.get("title", "").strip() or "Untitled"
        password = norm_row.get("password", "").strip()
        username = norm_row.get("username", "").strip()
        url = norm_row.get("url", "").strip()
        notes = norm_row.get("notes", "").strip()
        item_type = norm_row.get("type", "login").strip().lower()

        if item_type == "secure note":
            secret_value = notes
            notes = ""
        else:
            secret_value = password

        if not secret_value:
            result.warnings.append(ImportWarning(
                item_title=title,
                reason="Skipped: no usable secret value.",
            ))
            continue

        description_parts = []
        if username:
            description_parts.append(f"username:{username}")
        if url:
            description_parts.append(f"url:{url}")
        if notes:
            description_parts.append(notes)

        result.entries.append(RawEntry(
            name=title,
            value=secret_value,
            service=title.lower().replace(" ", "-"),
            description=" | ".join(description_parts),
        ))

    return result


# ------------------------------------------------------------------ #
# KeePass CSV
# ------------------------------------------------------------------ #

def _parse_keepass_csv(text: str) -> ExternalImportResult:
    """
    Parse a KeePass CSV export.

    Expected columns: Title, UserName, Password, URL, Notes, Group (optional)
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("KeePass CSV is empty.")

    norm_fields = {f.strip().lower() for f in reader.fieldnames}
    if "title" not in norm_fields or "password" not in norm_fields:
        raise ValueError(
            "KeePass CSV must have 'Title' and 'Password' columns."
        )

    result = ExternalImportResult()

    for row in reader:
        norm_row = {k.strip().lower(): v for k, v in row.items()}
        title = norm_row.get("title", "").strip() or "Untitled"
        password = norm_row.get("password", "").strip()
        username = norm_row.get("username", "").strip()
        url = norm_row.get("url", "").strip()
        notes = norm_row.get("notes", "").strip()
        group = norm_row.get("group", "").strip()

        if not password:
            result.warnings.append(ImportWarning(
                item_title=title,
                reason="Skipped: empty password.",
            ))
            continue

        description_parts = []
        if username:
            description_parts.append(f"username:{username}")
        if url:
            description_parts.append(f"url:{url}")
        if notes:
            description_parts.append(notes)

        tags = group.lower().replace("/", ",").replace(" ", "-") if group else ""

        result.entries.append(RawEntry(
            name=title,
            value=password,
            service=title.lower().replace(" ", "-"),
            tags=tags,
            description=" | ".join(description_parts),
        ))

    return result


# ------------------------------------------------------------------ #
# Auto-detect and public API
# ------------------------------------------------------------------ #

def _detect_format(path: Path, text: str) -> SourceFormat:
    """Heuristically detect the export format."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "bitwarden"
    if suffix == ".csv":
        # Distinguish 1Password from KeePass by header
        first_line = text.splitlines()[0].lower() if text else ""
        if "type" in first_line and "username" in first_line and "title" in first_line:
            # 1Password CSV always has a 'type' column
            if "type" in first_line:
                return "1password"
        if "username" in first_line or "group" in first_line:
            return "keepass"
        return "1password"  # fallback for generic CSV
    raise ValueError(f"Cannot detect format for extension '{suffix}'. Use .json or .csv.")


def parse_external_export(
    path: Path,
    fmt: SourceFormat = "auto",
) -> ExternalImportResult:
    """
    Parse a Bitwarden, 1Password, or KeePass export file.

    Args:
        path: Path to the export file.
        fmt:  Source format. Use 'auto' to detect from extension/content.

    Returns:
        ExternalImportResult with entries list and any import warnings.

    Raises:
        ValueError: Unknown format, missing columns, or parse error.
        FileNotFoundError: File does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Export file not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")

    if fmt == "auto":
        fmt = _detect_format(path, text)

    if fmt == "bitwarden":
        return _parse_bitwarden_json(text)
    if fmt == "1password":
        return _parse_1password_csv(text)
    if fmt == "keepass":
        return _parse_keepass_csv(text)

    raise ValueError(f"Unknown format: '{fmt}'. Use bitwarden, 1password, keepass, or auto.")
