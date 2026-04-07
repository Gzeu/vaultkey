"""
tests/test_stats.py — Wave 11
Covers wallet.utils.stats: counts, distributions, vault score, format_report.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

stats_mod = pytest.importorskip("wallet.utils.stats")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_entry(
    name: str = "key",
    service: str = "svc",
    tags: list[str] | None = None,
    is_active: bool = True,
    access_count: int = 5,
    days_until_expiry: int | None = None,
    days_since_rotation: int = 10,
    last_accessed_days_ago: int | None = 5,
) -> MagicMock:
    e = MagicMock()
    e.name = name
    e.service = service
    e.tags = tags or []
    e.is_active = is_active
    e.access_count = access_count
    now = datetime.now(timezone.utc)
    if days_until_expiry is not None:
        e.expires_at = now + timedelta(days=days_until_expiry)
        e.is_expired = days_until_expiry < 0
        e.expires_soon = 0 <= days_until_expiry <= 30
    else:
        e.expires_at = None
        e.is_expired = False
        e.expires_soon = False
    e.updated_at = now - timedelta(days=days_since_rotation)
    e.last_accessed_at = (
        now - timedelta(days=last_accessed_days_ago)
        if last_accessed_days_ago is not None
        else None
    )
    return e


def _make_payload(entries: list) -> MagicMock:
    p = MagicMock()
    p.keys = {f"id-{i}": e for i, e in enumerate(entries)}
    return p


# ---------------------------------------------------------------------------
# Basic counts
# ---------------------------------------------------------------------------

class TestBasicCounts:
    def test_active_count(self):
        payload = _make_payload([
            _make_entry("k1", is_active=True),
            _make_entry("k2", is_active=True),
            _make_entry("k3", is_active=False),
        ])
        s = stats_mod.compute_stats(payload)
        assert s.active >= 2

    def test_revoked_count(self):
        payload = _make_payload([
            _make_entry("k1", is_active=False),
            _make_entry("k2", is_active=False),
            _make_entry("k3", is_active=True),
        ])
        s = stats_mod.compute_stats(payload)
        assert s.revoked >= 2

    def test_expired_count(self):
        payload = _make_payload([
            _make_entry("k1", days_until_expiry=-5),
            _make_entry("k2", days_until_expiry=10),
        ])
        s = stats_mod.compute_stats(payload)
        assert s.expired >= 1

    def test_expiring_soon_count(self):
        payload = _make_payload([
            _make_entry("k1", days_until_expiry=5),
            _make_entry("k2", days_until_expiry=100),
        ])
        s = stats_mod.compute_stats(payload)
        assert s.expiring_soon >= 1

    def test_total_count(self):
        entries = [_make_entry(f"k{i}") for i in range(7)]
        payload = _make_payload(entries)
        s = stats_mod.compute_stats(payload)
        assert s.total == 7

    def test_empty_vault(self):
        payload = _make_payload([])
        s = stats_mod.compute_stats(payload)
        assert s.total == 0
        assert s.active == 0


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

class TestDistributions:
    def test_tag_distribution(self):
        payload = _make_payload([
            _make_entry("k1", tags=["prod", "infra"]),
            _make_entry("k2", tags=["prod"]),
            _make_entry("k3", tags=["dev"]),
        ])
        s = stats_mod.compute_stats(payload)
        tag_map = dict(s.tag_distribution)
        assert tag_map.get("prod", 0) == 2
        assert tag_map.get("dev", 0) == 1

    def test_service_distribution(self):
        payload = _make_payload([
            _make_entry("k1", service="openai"),
            _make_entry("k2", service="openai"),
            _make_entry("k3", service="stripe"),
        ])
        s = stats_mod.compute_stats(payload)
        svc_map = dict(s.service_distribution)
        assert svc_map.get("openai", 0) == 2
        assert svc_map.get("stripe", 0) == 1

    def test_distribution_sorted_desc(self):
        payload = _make_payload([
            _make_entry("k1", service="a"),
            _make_entry("k2", service="b"),
            _make_entry("k3", service="b"),
            _make_entry("k4", service="b"),
        ])
        s = stats_mod.compute_stats(payload)
        counts = [v for _, v in s.service_distribution]
        assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# most_accessed / stale / unused
# ---------------------------------------------------------------------------

class TestAccessMetrics:
    def test_most_accessed_top_n(self):
        entries = [_make_entry(f"k{i}", access_count=i) for i in range(10)]
        payload = _make_payload(entries)
        s = stats_mod.compute_stats(payload)
        top = s.most_accessed[:3]
        assert all(top[i].access_count >= top[i + 1].access_count for i in range(len(top) - 1))

    def test_stale_keys_over_90_days(self):
        payload = _make_payload([
            _make_entry("old", days_since_rotation=100),
            _make_entry("fresh", days_since_rotation=10),
        ])
        s = stats_mod.compute_stats(payload)
        stale_names = [e.name for e in s.stale_keys]
        assert "old" in stale_names
        assert "fresh" not in stale_names

    def test_unused_keys_zero_access(self):
        payload = _make_payload([
            _make_entry("never", access_count=0, last_accessed_days_ago=None),
            _make_entry("used", access_count=3),
        ])
        s = stats_mod.compute_stats(payload)
        unused_names = [e.name for e in s.unused_keys]
        assert "never" in unused_names
        assert "used" not in unused_names


# ---------------------------------------------------------------------------
# Vault Score
# ---------------------------------------------------------------------------

class TestVaultScore:
    def test_perfect_vault_high_score(self):
        entries = [
            _make_entry(f"k{i}", days_since_rotation=5, access_count=10,
                        days_until_expiry=90)
            for i in range(5)
        ]
        payload = _make_payload(entries)
        s = stats_mod.compute_stats(payload)
        assert s.vault_score >= 60

    def test_terrible_vault_low_score(self):
        entries = [
            _make_entry(f"k{i}", is_active=False, access_count=0,
                        days_until_expiry=-10, days_since_rotation=200)
            for i in range(5)
        ]
        payload = _make_payload(entries)
        s = stats_mod.compute_stats(payload)
        assert s.vault_score <= 60

    def test_score_in_range(self):
        payload = _make_payload([_make_entry("k1")])
        s = stats_mod.compute_stats(payload)
        assert 0 <= s.vault_score <= 100

    def test_empty_vault_score(self):
        payload = _make_payload([])
        s = stats_mod.compute_stats(payload)
        assert 0 <= s.vault_score <= 100


# ---------------------------------------------------------------------------
# format_stats_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_returns_string(self):
        payload = _make_payload([_make_entry("k1")])
        s = stats_mod.compute_stats(payload)
        report = stats_mod.format_stats_report(s)
        assert isinstance(report, str)

    def test_contains_total(self):
        payload = _make_payload([_make_entry("k1"), _make_entry("k2")])
        s = stats_mod.compute_stats(payload)
        report = stats_mod.format_stats_report(s)
        assert "2" in report

    def test_contains_vault_score(self):
        payload = _make_payload([_make_entry("k1")])
        s = stats_mod.compute_stats(payload)
        report = stats_mod.format_stats_report(s)
        # Should mention score somewhere
        assert any(kw in report.lower() for kw in ["score", "vault"])
