"""
validators.py — Input validation helpers for CLI and GUI.
"""

import re
from datetime import datetime, timezone
from typing import Optional


def parse_expiry_date(value: str) -> Optional[datetime]:
    """
    Parse an expiry date string in YYYY-MM-DD format.
    Returns None if value is empty or None.
    Raises ValueError with a clear message on invalid format.
    """
    if not value or value.strip() == "":
        return None
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD format (e.g., 2025-12-31).")


def validate_key_name(name: str) -> str:
    """Ensure key name is non-empty and reasonably short."""
    name = name.strip()
    if not name:
        raise ValueError("Key name cannot be empty.")
    if len(name) > 100:
        raise ValueError("Key name too long (max 100 characters).")
    return name


def validate_api_key_value(value: str) -> str:
    """Basic sanity check — not empty, no whitespace, reasonable length."""
    value = value.strip()
    if not value:
        raise ValueError("API key value cannot be empty.")
    if re.search(r"\s", value):
        raise ValueError("API key value must not contain whitespace.")
    if len(value) < 8:
        raise ValueError("API key value is suspiciously short (min 8 chars).")
    return value
