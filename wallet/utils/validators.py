"""
validators.py — Input validation helpers for CLI and GUI.

FIX #7 (MINOR) v1.1 — API key length cap:
  Previously validate_api_key_value() had no upper-bound check.
  A 1MB+ string would pass validation, get encrypted, and be stored.
  Added MAX_API_KEY_LENGTH = 8192 bytes — well above any real API key
  (longest known: GitHub fine-grained PATs ~230 chars; JWTs up to ~2KB).
  8192 chars covers all realistic use-cases while rejecting payloads
  that could be used for abuse (e.g., accidentally pasting an entire
  private key file instead of an API key).
"""

import re
from datetime import datetime, timezone
from typing import Optional

MAX_API_KEY_LENGTH = 8192   # chars — covers all real API keys + JWTs
MIN_API_KEY_LENGTH = 8      # chars — reject obvious garbage


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
        raise ValueError(
            f"Invalid date '{value}'. Use YYYY-MM-DD format (e.g., 2025-12-31)."
        )


def validate_key_name(name: str) -> str:
    """Ensure key name is non-empty and reasonably short."""
    name = name.strip()
    if not name:
        raise ValueError("Key name cannot be empty.")
    if len(name) > 100:
        raise ValueError("Key name too long (max 100 characters).")
    return name


def validate_api_key_value(value: str) -> str:
    """
    Validate an API key value before encryption.

    Checks:
    - Non-empty after strip
    - No internal whitespace (API keys never contain spaces/tabs/newlines)
    - Minimum length of MIN_API_KEY_LENGTH (rejects obvious garbage)
    - Maximum length of MAX_API_KEY_LENGTH (FIX #7: prevents giant payload abuse)
    """
    value = value.strip()
    if not value:
        raise ValueError("API key value cannot be empty.")
    if re.search(r"\s", value):
        raise ValueError(
            "API key value must not contain whitespace. "
            "Did you accidentally paste extra content?"
        )
    if len(value) < MIN_API_KEY_LENGTH:
        raise ValueError(
            f"API key value is suspiciously short (min {MIN_API_KEY_LENGTH} chars)."
        )
    if len(value) > MAX_API_KEY_LENGTH:
        raise ValueError(
            f"API key value is too long ({len(value)} chars, max {MAX_API_KEY_LENGTH}). "
            "This doesn't look like an API key. Did you paste the wrong content?"
        )
    return value
