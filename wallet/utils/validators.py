"""
validators.py — Input validation for CLI prompts.

Validation rules:
  - API key name: 1–128 chars, no leading/trailing whitespace, no control chars.
  - API key value: 8–512 chars, printable ASCII only, no whitespace.
  - Expiry date: ISO YYYY-MM-DD, must be in the future.

Design decisions:
- All validators raise typer.BadParameter for clean Typer error display.
- validate_api_key_value() deliberately rejects whitespace to prevent
  accidental copy-paste of surrounding whitespace with the key.
- We do NOT validate that the API key is a valid key for any specific service.
  That would require network calls, which is out of scope for an offline tool.
"""

from datetime import date, datetime, timezone
from typing import Optional

import typer


def validate_key_name(value: str) -> str:
    """Strip and validate a key name. Returns cleaned name."""
    value = value.strip()
    if not value:
        raise typer.BadParameter("Key name cannot be empty.")
    if len(value) > 128:
        raise typer.BadParameter("Key name too long (max 128 characters).")
    if any(ord(c) < 32 for c in value):
        raise typer.BadParameter("Key name contains invalid control characters.")
    return value


def validate_api_key_value(value: str) -> str:
    """Validate an API key value. Returns the value unchanged if valid."""
    # Strip surrounding whitespace only — leading/trailing spaces are common paste artifacts
    value = value.strip()
    if len(value) < 8:
        raise typer.BadParameter(
            "API key value too short (min 8 characters). "
            "Are you sure you pasted the full key?"
        )
    if len(value) > 512:
        raise typer.BadParameter(
            "API key value too long (max 512 characters). "
            "Are you storing the right thing?"
        )
    if not value.isprintable():
        raise typer.BadParameter(
            "API key value contains non-printable characters. "
            "Ensure you copied the raw key, not a formatted version."
        )
    if " " in value or "\t" in value:
        raise typer.BadParameter(
            "API key value contains whitespace. "
            "Keys should not contain spaces or tabs."
        )
    return value


def parse_expiry_date(value: str) -> Optional[datetime]:
    """
    Parse an optional expiry date string (YYYY-MM-DD).

    Returns:
        datetime with UTC timezone if a valid future date was provided.
        None if value is empty/blank.

    Raises:
        typer.BadParameter if the format is wrong or the date is in the past.
    """
    value = value.strip()
    if not value:
        return None

    try:
        d = date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(
            f"Invalid date format '{value}'. Use YYYY-MM-DD (e.g. 2026-12-31)."
        )

    expiry = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
    if expiry < datetime.now(timezone.utc):
        raise typer.BadParameter(
            f"Expiry date '{value}' is in the past. Use a future date."
        )
    return expiry


def validate_tag_list(value: str) -> list[str]:
    """Parse and validate a comma-separated tag list."""
    tags = [t.strip().lower() for t in value.split(",") if t.strip()]
    for tag in tags:
        if len(tag) > 32:
            raise typer.BadParameter(f"Tag '{tag}' is too long (max 32 characters).")
        if not tag.replace("-", "").replace("_", "").isalnum():
            raise typer.BadParameter(
                f"Tag '{tag}' contains invalid characters. Use letters, digits, hyphens, underscores."
            )
    return tags
