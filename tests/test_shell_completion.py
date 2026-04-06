"""
tests/test_shell_completion.py — Tests for wallet.utils.shell_completion

Covers:
  SC1  entry_names_completer: returns names matching prefix
  SC2  entry_names_completer: empty prefix returns all names
  SC3  entry_names_completer: case-insensitive matching
  SC4  entry_names_completer: no matches returns empty list
  SC5  service_names_completer: returns unique services matching prefix
  SC6  service_names_completer: deduplicates repeated services
  SC7  tag_completer: returns tags matching prefix
  SC8  tag_completer: returns empty list when wallet locked
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from wallet.utils.shell_completion import (
    entry_names_completer,
    service_names_completer,
    tag_completer,
)


@pytest.fixture()
def _mock_payload(payload_with_keys):
    """Patch _load_payload to return the test payload."""
    payload, _ = payload_with_keys
    with patch(
        "wallet.utils.shell_completion._load_payload",
        return_value=payload,
    ) as m:
        yield m


@pytest.fixture()
def _mock_locked():
    """Patch _load_payload to simulate a locked wallet."""
    with patch(
        "wallet.utils.shell_completion._load_payload",
        return_value=None,
    ) as m:
        yield m


# SC1
def test_entry_names_prefix(_mock_payload, payload_with_keys):
    """SC1: completions start with the given prefix."""
    payload, _ = payload_with_keys
    first_char = payload.entries[0].name[0].lower()
    results = entry_names_completer(first_char)
    assert all(r.lower().startswith(first_char) for r in results)


# SC2
def test_entry_names_empty_prefix(_mock_payload, payload_with_keys):
    """SC2: empty prefix returns all entry names."""
    payload, _ = payload_with_keys
    results = entry_names_completer("")
    assert len(results) == len(payload.entries)


# SC3
def test_entry_names_case_insensitive(_mock_payload, payload_with_keys):
    """SC3: matching is case-insensitive."""
    payload, _ = payload_with_keys
    first_name = payload.entries[0].name
    results = entry_names_completer(first_name.upper())
    assert first_name in results


# SC4
def test_entry_names_no_match(_mock_payload):
    """SC4: no match returns empty list."""
    results = entry_names_completer("zzzzzz-no-match")
    assert results == []


# SC5
def test_service_names_prefix(_mock_payload, payload_with_keys):
    """SC5: service completions match prefix."""
    payload, _ = payload_with_keys
    services = [e.service for e in payload.entries if e.service]
    if not services:
        pytest.skip("No services in fixture")
    prefix = services[0][0].lower()
    results = service_names_completer(prefix)
    assert all(r.lower().startswith(prefix) for r in results)


# SC6
def test_service_names_deduplicated(_mock_payload, payload_with_keys, make_entry):
    """SC6: repeated services only appear once."""
    payload, _ = payload_with_keys
    # Add a duplicate service
    existing_svc = payload.entries[0].service or "TestSvc"
    payload.add_entry(make_entry(name="dup-svc-key", service=existing_svc))
    results = service_names_completer("")
    assert len(results) == len(set(results))


# SC7
def test_tag_completer(_mock_payload, payload_with_keys, make_entry):
    """SC7: tag completions match prefix."""
    payload, _ = payload_with_keys
    payload.add_entry(make_entry(name="tagged-key", tags=["production", "openai"]))
    with patch(
        "wallet.utils.shell_completion._load_payload", return_value=payload
    ):
        results = tag_completer("prod")
    assert "production" in results


# SC8
def test_tag_completer_locked(_mock_locked):
    """SC8: returns empty list when wallet is locked."""
    results = tag_completer("any")
    assert results == []
