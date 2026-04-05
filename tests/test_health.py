"""
Tests for wallet/core/health.py — key health scoring and analysis.
"""

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from wallet.core.health import (
    EXPIRING_SOON_DAYS,
    STALE_AFTER_DAYS,
    EntryHealth,
    WalletHealth,
    analyze_entry,
    analyze_wallet,
)
from wallet.models.wallet import APIKeyEntry, WalletPayload


def _make_entry(**kwargs) -> APIKeyEntry:
    defaults = {
        "name": "Test Key",
        "service": "test",
        "nonce_hex": secrets.token_bytes(12).hex(),
        "cipher_hex": secrets.token_bytes(48).hex(),
    }
    defaults.update(kwargs)
    return APIKeyEntry(**defaults)


class TestAnalyzeEntry:
    def test_perfect_entry_scores_high(self):
        entry = _make_entry(
            tags=["production"],
            description="Main key",
            expires_at=datetime.now(timezone.utc) + timedelta(days=180),
            last_accessed_at=datetime.now(timezone.utc) - timedelta(days=1),
            access_count=10,
        )
        eh = analyze_entry(entry)
        assert eh.score >= 90
        assert eh.grade == "A"
        assert eh.is_healthy

    def test_expired_entry_penalized(self):
        entry = _make_entry(
            expires_at=datetime.now(timezone.utc) - timedelta(days=5)
        )
        eh = analyze_entry(entry)
        assert eh.score <= 70
        assert any("expired" in i.lower() for i in eh.issues)

    def test_expiring_soon_penalized(self):
        entry = _make_entry(
            expires_at=datetime.now(timezone.utc) + timedelta(days=10)
        )
        eh = analyze_entry(entry)
        assert any("expire" in i.lower() for i in eh.issues)

    def test_stale_entry_penalized(self):
        entry = _make_entry(
            last_accessed_at=datetime.now(timezone.utc) - timedelta(
                days=STALE_AFTER_DAYS + 10
            )
        )
        eh = analyze_entry(entry)
        assert any("accessed" in i.lower() for i in eh.issues)

    def test_never_accessed_penalized(self):
        entry = _make_entry(last_accessed_at=None)
        eh = analyze_entry(entry)
        assert any("never" in i.lower() for i in eh.issues)

    def test_revoked_scores_zero(self):
        entry = _make_entry(is_active=False)
        eh = analyze_entry(entry)
        assert eh.score == 0
        assert eh.grade == "F"

    def test_no_expiry_penalized(self):
        entry = _make_entry(expires_at=None)
        eh = analyze_entry(entry)
        assert any("expiry" in i.lower() for i in eh.issues)


class TestAnalyzeWallet:
    def test_empty_wallet_100(self):
        payload = WalletPayload(master_hash="dummy")
        wh = analyze_wallet(payload)
        assert wh.overall_score == 100
        assert wh.total == 0

    def test_mixed_wallet_categorized(self):
        payload = WalletPayload(master_hash="dummy")
        # Healthy entry
        payload.add_entry(_make_entry(
            name="Healthy",
            tags=["prod"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=180),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=5,
        ))
        # Critical entry
        payload.add_entry(_make_entry(
            name="Expired",
            expires_at=datetime.now(timezone.utc) - timedelta(days=30),
            is_active=False,
        ))
        wh = analyze_wallet(payload)
        assert wh.total == 2
        assert wh.critical >= 1
        # Worst entry should be first
        assert wh.entries[0].score <= wh.entries[-1].score
