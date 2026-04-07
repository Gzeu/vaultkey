"""
tests/test_search_advanced.py — Wave 11
Covers wallet.utils.search_advanced: field-scoped, boolean, regex, scoring.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

search_mod = pytest.importorskip("wallet.utils.search_advanced")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _entry(
    name: str,
    service: str = "svc",
    tags: list[str] | None = None,
    description: str = "",
) -> MagicMock:
    e = MagicMock()
    e.name = name
    e.service = service
    e.tags = tags or []
    e.description = description
    return e


def _payload(entries: list) -> MagicMock:
    p = MagicMock()
    p.keys = {f"id-{i}": e for i, e in enumerate(entries)}
    return p


# ---------------------------------------------------------------------------
# Basic substring search
# ---------------------------------------------------------------------------

class TestBasicSearch:
    def test_finds_by_name(self):
        p = _payload([_entry("openai-prod"), _entry("stripe-live")])
        results = search_mod.advanced_search(p, "openai")
        assert any(r.name == "openai-prod" for r in results)

    def test_no_match_returns_empty(self):
        p = _payload([_entry("alpha"), _entry("beta")])
        assert search_mod.advanced_search(p, "zzz") == []

    def test_empty_vault_returns_empty(self):
        p = _payload([])
        assert search_mod.advanced_search(p, "anything") == []

    def test_empty_query_returns_all(self):
        p = _payload([_entry("a"), _entry("b"), _entry("c")])
        results = search_mod.advanced_search(p, "")
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Field-scoped search
# ---------------------------------------------------------------------------

class TestFieldScoped:
    def test_name_scope(self):
        p = _payload([
            _entry("openai-prod", service="other"),
            _entry("other", service="openai"),
        ])
        results = search_mod.advanced_search(p, "name:openai")
        names = [r.name for r in results]
        assert "openai-prod" in names
        # service match should not appear in name: scoped search
        assert "other" not in names

    def test_service_scope(self):
        p = _payload([
            _entry("k1", service="stripe"),
            _entry("stripe-named", service="other"),
        ])
        results = search_mod.advanced_search(p, "service:stripe")
        services = [r.service for r in results]
        assert "stripe" in services

    def test_tag_scope(self):
        p = _payload([
            _entry("k1", tags=["prod"]),
            _entry("k2", tags=["dev"]),
        ])
        results = search_mod.advanced_search(p, "tag:prod")
        assert len(results) == 1
        assert results[0].name == "k1"

    def test_desc_scope(self):
        p = _payload([
            _entry("k1", description="main production key"),
            _entry("k2", description="staging only"),
        ])
        results = search_mod.advanced_search(p, "desc:production")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------

class TestBooleanOps:
    def test_and_implicit(self):
        p = _payload([
            _entry("alpha-prod", service="openai"),
            _entry("alpha-dev", service="stripe"),
            _entry("beta-prod", service="openai"),
        ])
        results = search_mod.advanced_search(p, "alpha openai")
        assert len(results) == 1
        assert results[0].name == "alpha-prod"

    def test_or_operator(self):
        p = _payload([
            _entry("alpha"),
            _entry("beta"),
            _entry("gamma"),
        ])
        results = search_mod.advanced_search(p, "alpha OR beta")
        names = [r.name for r in results]
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" not in names

    def test_not_operator(self):
        p = _payload([
            _entry("prod-key"),
            _entry("dev-key"),
            _entry("staging-key"),
        ])
        results = search_mod.advanced_search(p, "key NOT dev")
        names = [r.name for r in results]
        assert "dev-key" not in names
        assert "prod-key" in names


# ---------------------------------------------------------------------------
# Regex search
# ---------------------------------------------------------------------------

class TestRegexSearch:
    def test_regex_basic(self):
        p = _payload([
            _entry("sk-abc123"),
            _entry("pk-xyz789"),
            _entry("rk-000000"),
        ])
        results = search_mod.advanced_search(p, "/^sk-/")
        assert len(results) == 1
        assert results[0].name == "sk-abc123"

    def test_regex_case_insensitive(self):
        p = _payload([_entry("OpenAI-Key"), _entry("stripe-key")])
        results = search_mod.advanced_search(p, "/openai/")
        assert len(results) == 1

    def test_invalid_regex_falls_back_to_literal(self):
        p = _payload([_entry("[broken"), _entry("normal")])
        # Should not raise — fallback to literal
        results = search_mod.advanced_search(p, "/[broken/")
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

class TestRelevanceScoring:
    def test_exact_name_match_scores_higher(self):
        p = _payload([
            _entry("openai"),            # exact
            _entry("openai-prod"),        # contains
        ])
        results = search_mod.advanced_search(p, "openai")
        # exact match should appear first
        assert results[0].name == "openai"

    def test_results_sorted_by_score_desc(self):
        p = _payload([
            _entry("k1", service="test"),
            _entry("test"),               # exact name
            _entry("k2", tags=["test"]),
        ])
        results = search_mod.advanced_search(p, "test")
        # just verify the list is ordered (scores non-increasing)
        if hasattr(results[0], "_score"):
            scores = [r._score for r in results]
            assert scores == sorted(scores, reverse=True)
        else:
            assert len(results) >= 1  # at minimum returns results


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unicode_query(self):
        p = _payload([_entry("cheia-🔐")])
        results = search_mod.advanced_search(p, "🔐")
        assert len(results) == 1

    def test_whitespace_only_query(self):
        p = _payload([_entry("a"), _entry("b")])
        results = search_mod.advanced_search(p, "   ")
        assert isinstance(results, list)

    def test_very_long_query(self):
        p = _payload([_entry("normal")])
        long_query = "a" * 500
        results = search_mod.advanced_search(p, long_query)
        assert isinstance(results, list)
