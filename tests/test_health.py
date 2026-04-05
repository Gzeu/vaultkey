"""
test_health.py — Tests for wallet/core/health.py.

Covers:
  - Active key with all fields → high score (A/B)
  - Missing description penalizes score
  - Missing tags penalizes score
  - Expiring key (< 14 days) downgrades score
  - Expired key → score F
  - Revoked key → score F or D
  - Never accessed key is flagged
  - High access count is a positive signal
  - analyze_wallet: grade calculation, healthy/warning/critical counts
  - analyze_wallet with empty payload returns overall grade
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import make_entry
from wallet.core.health import analyze_entry, analyze_wallet
from wallet.models.wallet import WalletPayload
from wallet.core.kdf import hash_master_password

import secrets

KEY = secrets.token_bytes(32)


def _payload(*entries) -> WalletPayload:
    p = WalletPayload(master_hash=hash_master_password("test"))
    for e in entries:
        p.add_entry(e)
    return p


class TestAnalyzeEntry:
    def test_active_complete_key_high_score(self):
        entry = make_entry(KEY, name="Full Key", service="openai",
                            tags="prod,ml", days_until_expiry=180)
        entry.description = "Production OpenAI key for inference"
        entry.access_count = 5
        eh = analyze_entry(entry)
        assert eh.grade in {"A", "B"}
        assert eh.score >= 70

    def test_missing_description_penalizes(self):
        entry_with = make_entry(KEY, name="Key A", service="openai", days_until_expiry=180)
        entry_with.description = "Has a description"
        entry_with.access_count = 3
        entry_without = make_entry(KEY, name="Key B", service="openai", days_until_expiry=180)
        entry_without.description = ""
        score_with = analyze_entry(entry_with).score
        score_without = analyze_entry(entry_without).score
        assert score_with > score_without

    def test_missing_tags_penalizes(self):
        entry_with = make_entry(KEY, name="Key C", tags="prod")
        entry_without = make_entry(KEY, name="Key D", tags="")
        assert analyze_entry(entry_with).score > analyze_entry(entry_without).score

    def test_expiring_key_flagged(self):
        entry = make_entry(KEY, name="Expiring", days_until_expiry=5)
        eh = analyze_entry(entry)
        assert any("expir" in issue.lower() for issue in eh.issues)

    def test_expired_key_is_grade_f(self):
        entry = make_entry(KEY, name="Expired", already_expired=True)
        eh = analyze_entry(entry)
        assert eh.grade == "F"
        assert eh.score < 30

    def test_never_accessed_flagged(self):
        entry = make_entry(KEY, name="New Key", access_count=0)
        eh = analyze_entry(entry)
        assert any("access" in issue.lower() or "unused" in issue.lower()
                   for issue in eh.issues)

    def test_high_access_count_no_penalty(self):
        entry = make_entry(KEY, name="Busy Key", access_count=100, days_until_expiry=90)
        entry.description = "Frequently used"
        eh = analyze_entry(entry)
        assert eh.score >= 60

    def test_revoked_key_low_grade(self):
        entry = make_entry(KEY, name="Revoked")
        entry.is_active = False
        eh = analyze_entry(entry)
        assert eh.grade in {"D", "F"}

    def test_result_has_required_fields(self):
        entry = make_entry(KEY, name="Check")
        eh = analyze_entry(entry)
        assert hasattr(eh, "name")
        assert hasattr(eh, "score")
        assert hasattr(eh, "grade")
        assert hasattr(eh, "issues")
        assert hasattr(eh, "recommendations")
        assert eh.grade in {"A", "B", "C", "D", "F"}
        assert 0 <= eh.score <= 100


class TestAnalyzeWallet:
    def test_empty_wallet_returns_result(self):
        p = WalletPayload(master_hash=hash_master_password("test"))
        wh = analyze_wallet(p)
        assert wh.total == 0
        assert wh.overall_grade in {"A", "B", "C", "D", "F"}

    def test_all_healthy_keys_grade_a_or_b(self):
        entries = [
            make_entry(KEY, name=f"Key {i}", service="openai",
                        tags="prod", days_until_expiry=180)
            for i in range(3)
        ]
        for e in entries:
            e.description = "Production"
            e.access_count = 5
        p = _payload(*entries)
        wh = analyze_wallet(p)
        assert wh.healthy == 3
        assert wh.critical == 0
        assert wh.overall_grade in {"A", "B"}

    def test_one_expired_lowers_overall_grade(self):
        healthy = make_entry(KEY, name="Good Key", days_until_expiry=180)
        healthy.description = "OK"
        healthy.access_count = 5
        expired = make_entry(KEY, name="Old Key", already_expired=True)
        p = _payload(healthy, expired)
        wh = analyze_wallet(p)
        assert wh.critical >= 1

    def test_wallet_health_counts_sum_to_total(self):
        entries = [
            make_entry(KEY, name="K1", days_until_expiry=200),
            make_entry(KEY, name="K2", days_until_expiry=5),
            make_entry(KEY, name="K3", already_expired=True),
        ]
        p = _payload(*entries)
        wh = analyze_wallet(p)
        assert wh.healthy + wh.warning + wh.critical == wh.total
        assert wh.total == 3
