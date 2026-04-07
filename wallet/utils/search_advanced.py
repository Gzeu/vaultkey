"""
search_advanced.py — Advanced search engine for VaultKey entries.

Extends the basic substring search in WalletPayload.search() with:
    - Field-scoped queries:  name:<term>, service:<term>, tag:<term>, desc:<term>
    - Boolean operators:     AND (default), OR, NOT
    - Regex support:         /pattern/ syntax (case-insensitive)
    - Result ranking:        relevance score based on match quality
    - Multi-word support:    unquoted words joined with implicit AND

Query syntax examples:
    "github"                     → substring in any field
    "name:openai service:llm"    → both conditions (AND)
    "tag:production OR tag:prod" → either tag
    "NOT tag:deprecated"         → exclude deprecated
    "/^sk-/"                     → regex on all text fields
    "name:/^OpenAI/ NOT expired" → mixed

Design decisions:
- No external parser library required. The tokenizer handles simple cases.
- Regex patterns are always compiled with re.IGNORECASE.
- A regex that fails to compile is treated as a literal substring.
- Relevance scoring: exact name match = +10, name contains = +5,
  service match = +3, tag match = +4, description match = +1.
  Final list is sorted by score desc, then name asc.
- The engine never decrypts values — all fields are plaintext metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wallet.models.wallet import APIKeyEntry, WalletPayload


@dataclass
class SearchResult:
    """A single search result with relevance score."""
    entry: "APIKeyEntry"
    score: int = 0
    matched_fields: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ #
# Token types
# ------------------------------------------------------------------ #

@dataclass
class _Token:
    field: str | None    # 'name', 'service', 'tag', 'desc', or None (all)
    pattern: str
    is_regex: bool
    negate: bool


def _parse_query(query: str) -> tuple[list[_Token], str]:  # (tokens, mode)
    """
    Parse a search query string into tokens.

    Returns:
        (tokens, boolean_mode) where boolean_mode is 'AND' or 'OR'.
    """
    tokens: list[_Token] = []
    mode = "AND"

    # Detect top-level OR
    if " OR " in query.upper():
        mode = "OR"

    # Split on whitespace but respect /regex/ groups
    raw_parts: list[str] = []
    i = 0
    current = ""
    while i < len(query):
        if query[i] == "/":
            # Find closing /
            end = query.find("/", i + 1)
            if end == -1:
                current += query[i:]
                i = len(query)
            else:
                current += query[i:end + 1]
                i = end + 1
        elif query[i] == " ":
            if current.strip():
                raw_parts.append(current.strip())
            current = ""
            i += 1
        else:
            current += query[i]
            i += 1
    if current.strip():
        raw_parts.append(current.strip())

    skip_next = False
    for idx, part in enumerate(raw_parts):
        if skip_next:
            skip_next = False
            continue
        if part.upper() in ("AND", "OR"):
            continue
        if part.upper() == "NOT":
            # Next token is negated
            if idx + 1 < len(raw_parts):
                negate_part = raw_parts[idx + 1]
                skip_next = True
                tokens.append(_make_token(negate_part, negate=True))
            continue
        tokens.append(_make_token(part, negate=False))

    return tokens, mode


def _make_token(part: str, negate: bool) -> _Token:
    """Parse a single query part into a _Token."""
    field_name: str | None = None
    pattern = part

    # Field-scoped: name:foo, service:bar, tag:baz, desc:qux
    for prefix in ("name:", "service:", "tag:", "desc:"):
        if part.lower().startswith(prefix):
            field_name = prefix.rstrip(":")
            pattern = part[len(prefix):]
            break

    # Regex: /pattern/
    is_regex = False
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        is_regex = True
        pattern = pattern[1:-1]

    return _Token(field=field_name, pattern=pattern, is_regex=is_regex, negate=negate)


# ------------------------------------------------------------------ #
# Matching engine
# ------------------------------------------------------------------ #

def _compile(pattern: str, is_regex: bool) -> re.Pattern | None:
    if not is_regex:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None  # Fallback to literal


def _match_text(text: str, token: _Token) -> bool:
    """Return True if text matches the token's pattern."""
    if token.is_regex:
        compiled = _compile(token.pattern, True)
        if compiled:
            return bool(compiled.search(text))
    return token.pattern.lower() in text.lower()


def _score_entry(entry: "APIKeyEntry", tokens: list[_Token]) -> tuple[bool, int, list[str]]:
    """
    Evaluate all tokens against an entry.

    Returns:
        (matches: bool, score: int, matched_fields: list[str])
    """
    score = 0
    matched_fields: list[str] = []

    for token in tokens:
        hit = False
        hit_fields: list[str] = []

        if token.field is None or token.field == "name":
            name_lower = entry.name.lower()
            pat_lower = token.pattern.lower()
            if _match_text(entry.name, token):
                hit = True
                hit_fields.append("name")
                if name_lower == pat_lower:
                    score += 10
                elif pat_lower in name_lower:
                    score += 5

        if token.field is None or token.field == "service":
            if _match_text(entry.service, token):
                hit = True
                hit_fields.append("service")
                score += 3

        if token.field is None or token.field == "tag":
            for tag in entry.tags:
                if _match_text(tag, token):
                    hit = True
                    hit_fields.append(f"tag:{tag}")
                    score += 4
                    break

        if token.field is None or token.field == "desc":
            if entry.description and _match_text(entry.description, token):
                hit = True
                hit_fields.append("description")
                score += 1

        # Handle NOT
        if token.negate:
            if hit:
                return False, 0, []
            # Negation matched (no hit = pass)
        else:
            if not hit:
                return False, 0, []
            matched_fields.extend(hit_fields)

    return True, score, matched_fields


def _score_entry_or(entry: "APIKeyEntry", tokens: list[_Token]) -> tuple[bool, int, list[str]]:
    """OR mode: entry matches if ANY non-negated token matches."""
    total_score = 0
    all_fields: list[str] = []
    any_hit = False

    for token in tokens:
        if token.negate:
            # NOT always applies regardless of mode
            _, hit_score, hit_fields = _score_entry(entry, [token])
            if hit_score == 0 and not hit_fields:
                # Negation passed
                continue
            else:
                return False, 0, []
        else:
            dummy_token = _Token(token.field, token.pattern, token.is_regex, False)
            matched, score, fields = _score_entry(entry, [dummy_token])
            if matched:
                any_hit = True
                total_score += score
                all_fields.extend(fields)

    if any_hit:
        return True, total_score, all_fields
    return False, 0, []


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def advanced_search(
    payload: "WalletPayload",
    query: str,
    *,
    include_revoked: bool = False,
    include_expired: bool = True,
) -> list[SearchResult]:
    """
    Execute an advanced search query against a WalletPayload.

    Args:
        payload:          The loaded WalletPayload.
        query:            Search query string (see module docstring for syntax).
        include_revoked:  If False, revoked entries are excluded from results.
        include_expired:  If False, expired entries are excluded from results.

    Returns:
        List of SearchResult sorted by relevance (score desc, then name asc).
        Empty list if no matches or query is blank.
    """
    query = query.strip()
    if not query:
        return []

    tokens, mode = _parse_query(query)
    if not tokens:
        return []

    results: list[SearchResult] = []

    for entry in payload.keys.values():
        # Pre-filters
        if not include_revoked and not entry.is_active:
            continue
        if not include_expired and entry.is_expired:
            continue

        if mode == "OR":
            matched, score, fields = _score_entry_or(entry, tokens)
        else:
            matched, score, fields = _score_entry(entry, tokens)

        if matched:
            results.append(SearchResult(entry=entry, score=score, matched_fields=fields))

    results.sort(key=lambda r: (-r.score, r.entry.name.lower()))
    return results
