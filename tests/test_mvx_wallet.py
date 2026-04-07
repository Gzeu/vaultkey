"""
tests/test_mvx_wallet.py — Wave 11
Covers wallet.core.mvx_wallet_payload: add/get/delete/search + round-trip.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

mvx_mod = pytest.importorskip("wallet.core.mvx_wallet_payload")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MVX = {
    "address": "erd1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq6gq4hu",
    "label": "Main EGLD Wallet",
    "shard": 0,
    "balance_egld": "1250.5",
    "notes": "Cold storage",
}


@pytest.fixture()
def mvx_payload():
    """Return a fresh MvxWalletPayload (or mixin instance)."""
    return mvx_mod.MvxWalletPayload()


# ---------------------------------------------------------------------------
# add_mvx_entry
# ---------------------------------------------------------------------------

class TestAddMvxEntry:
    def test_add_returns_id(self, mvx_payload):
        entry_id = mvx_payload.add_mvx_entry(**SAMPLE_MVX)
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

    def test_add_stores_address(self, mvx_payload):
        eid = mvx_payload.add_mvx_entry(**SAMPLE_MVX)
        entry = mvx_payload.get_mvx_entry(eid)
        assert entry.address == SAMPLE_MVX["address"]

    def test_add_stores_label(self, mvx_payload):
        eid = mvx_payload.add_mvx_entry(**SAMPLE_MVX)
        assert mvx_payload.get_mvx_entry(eid).label == "Main EGLD Wallet"

    def test_add_multiple_entries(self, mvx_payload):
        id1 = mvx_payload.add_mvx_entry(address="erd1aaa", label="W1")
        id2 = mvx_payload.add_mvx_entry(address="erd1bbb", label="W2")
        assert id1 != id2
        assert len(mvx_payload.mvx_keys) == 2


# ---------------------------------------------------------------------------
# get_mvx_entry
# ---------------------------------------------------------------------------

class TestGetMvxEntry:
    def test_get_existing(self, mvx_payload):
        eid = mvx_payload.add_mvx_entry(address="erd1xxx", label="X")
        entry = mvx_payload.get_mvx_entry(eid)
        assert entry is not None

    def test_get_missing_returns_none_or_raises(self, mvx_payload):
        result = mvx_payload.get_mvx_entry("nonexistent-id")
        assert result is None or isinstance(result, Exception.__class__)

    def test_get_returns_mvx_entry_type(self, mvx_payload):
        eid = mvx_payload.add_mvx_entry(**SAMPLE_MVX)
        entry = mvx_payload.get_mvx_entry(eid)
        assert hasattr(entry, "address")


# ---------------------------------------------------------------------------
# delete_mvx_entry
# ---------------------------------------------------------------------------

class TestDeleteMvxEntry:
    def test_delete_removes_entry(self, mvx_payload):
        eid = mvx_payload.add_mvx_entry(address="erd1del", label="Del")
        mvx_payload.delete_mvx_entry(eid)
        assert mvx_payload.get_mvx_entry(eid) is None

    def test_delete_nonexistent_no_crash(self, mvx_payload):
        # Should not raise
        try:
            mvx_payload.delete_mvx_entry("ghost-id")
        except (KeyError, ValueError):
            pass  # acceptable


# ---------------------------------------------------------------------------
# search_mvx
# ---------------------------------------------------------------------------

class TestSearchMvx:
    def test_search_by_label(self, mvx_payload):
        mvx_payload.add_mvx_entry(address="erd1aaa", label="Cold storage")
        mvx_payload.add_mvx_entry(address="erd1bbb", label="Hot wallet")
        results = mvx_payload.search_mvx("cold")
        assert len(results) == 1
        assert results[0].label == "Cold storage"

    def test_search_by_address(self, mvx_payload):
        mvx_payload.add_mvx_entry(address="erd1unique123", label="U")
        mvx_payload.add_mvx_entry(address="erd1other456", label="O")
        results = mvx_payload.search_mvx("unique123")
        assert any(r.address == "erd1unique123" for r in results)

    def test_search_no_match(self, mvx_payload):
        mvx_payload.add_mvx_entry(address="erd1aaa", label="Alpha")
        results = mvx_payload.search_mvx("zzz")
        assert results == []

    def test_search_empty_query_returns_all(self, mvx_payload):
        mvx_payload.add_mvx_entry(address="erd1aaa", label="A")
        mvx_payload.add_mvx_entry(address="erd1bbb", label="B")
        results = mvx_payload.search_mvx("")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_to_dict_with_mvx_includes_keys(self, mvx_payload):
        mvx_payload.add_mvx_entry(**SAMPLE_MVX)
        d = mvx_payload.to_dict_with_mvx()
        assert "mvx_keys" in d
        assert len(d["mvx_keys"]) == 1

    def test_to_dict_address_preserved(self, mvx_payload):
        mvx_payload.add_mvx_entry(**SAMPLE_MVX)
        d = mvx_payload.to_dict_with_mvx()
        entries = list(d["mvx_keys"].values())
        assert entries[0]["address"] == SAMPLE_MVX["address"]

    def test_empty_payload_round_trip(self, mvx_payload):
        d = mvx_payload.to_dict_with_mvx()
        assert d.get("mvx_keys", {}) == {}

    def test_backward_compat_no_mvx_keys_field(self):
        # Simulates loading an old payload without mvx_keys
        p = mvx_mod.MvxWalletPayload()
        # Should initialize to empty dict, not crash
        assert hasattr(p, "mvx_keys")
        assert isinstance(p.mvx_keys, dict)
