"""
mvx_wallet_payload.py — WalletPayload mixin for MultiversX entries.

This module provides a drop-in dict extension that adds `mvx_keys` to any
WalletPayload instance loaded from disk, keeping MultiversX entries stored
alongside API key entries in the same encrypted wallet file.

Integration pattern (in session / CLI code):

    payload = WalletPayload.from_dict(data)
    mvx = MvxPayloadMixin(payload)        # wraps existing payload
    mvx.add_mvx_entry(entry)              # stores in payload.mvx_keys
    storage.save(key, params, payload.to_dict())

The `mvx_keys` field is backward-compatible: wallets created before this
module was added will simply have an empty `mvx_keys` dict on load.

Design decisions:
- MvxKeyEntry is stored as a plain dict in the JSON payload (model_dump),
  same as APIKeyEntry. It is re-hydrated into MvxKeyEntry on access.
- All mutating methods call payload.touch() to update modified_at.
- The mixin does NOT subclass WalletPayload to avoid Pydantic conflicts.
  It wraps the payload and delegates to it.
"""

from __future__ import annotations

from typing import Optional

from wallet.core.mvx import MvxKeyEntry
from wallet.models.wallet import WalletPayload


class MvxPayloadMixin:
    """
    Wraps a WalletPayload to add MultiversX key management.

    Usage:
        payload = WalletPayload.from_dict(data)
        mvx = MvxPayloadMixin(payload)
        entry = store_mvx_entry(master_key, label="My EGLD", seed_phrase="...")
        mvx.add_mvx_entry(entry)
        data = payload.to_dict()  # includes mvx_keys automatically
    """

    def __init__(self, payload: WalletPayload) -> None:
        self._payload = payload
        # Ensure mvx_keys field exists in the underlying model extra
        if not hasattr(payload, "mvx_keys") or payload.__dict__.get("mvx_keys") is None:
            # Inject as a plain attribute (Pydantic v2 ConfigDict strict=False allows extra)
            object.__setattr__(payload, "mvx_keys", {})

    @property
    def mvx_keys(self) -> dict[str, MvxKeyEntry]:
        """Live dict of MvxKeyEntry objects, keyed by entry.id."""
        raw = getattr(self._payload, "mvx_keys", {})
        # Hydrate raw dicts back to MvxKeyEntry if needed
        hydrated: dict[str, MvxKeyEntry] = {}
        for k, v in raw.items():
            if isinstance(v, MvxKeyEntry):
                hydrated[k] = v
            elif isinstance(v, dict):
                hydrated[k] = MvxKeyEntry.model_validate(v)
        return hydrated

    def add_mvx_entry(self, entry: MvxKeyEntry) -> None:
        """Add a MultiversX key entry to the payload."""
        keys = self.mvx_keys
        keys[entry.id] = entry
        object.__setattr__(self._payload, "mvx_keys", keys)
        self._payload.touch()

    def get_mvx_entry(self, label_or_id: str) -> Optional[MvxKeyEntry]:
        """
        Look up an entry by exact ID or case-insensitive label.

        Returns None if not found.
        """
        keys = self.mvx_keys
        if label_or_id in keys:
            return keys[label_or_id]
        needle = label_or_id.lower()
        for entry in keys.values():
            if entry.label.lower() == needle:
                return entry
        return None

    def delete_mvx_entry(self, label_or_id: str) -> bool:
        """
        Delete a MultiversX entry by ID or label.

        Returns True if deleted, False if not found.
        """
        entry = self.get_mvx_entry(label_or_id)
        if entry is None:
            return False
        keys = self.mvx_keys
        del keys[entry.id]
        object.__setattr__(self._payload, "mvx_keys", keys)
        self._payload.touch()
        return True

    def search_mvx(
        self,
        query: str = "",
        tag: str = "",
        network: str = "",
    ) -> list[MvxKeyEntry]:
        """
        Filter MultiversX entries by query, tag, or network.

        Args:
            query:   Substring match on label, address, description.
            tag:     Exact tag match.
            network: 'mainnet' | 'devnet' | 'testnet'.

        Returns:
            Filtered list sorted by label.
        """
        results = list(self.mvx_keys.values())

        if query:
            q = query.lower()
            results = [
                e for e in results
                if q in e.label.lower()
                or (e.address and q in e.address.lower())
                or (e.description and q in e.description.lower())
            ]

        if tag:
            t = tag.lower()
            results = [e for e in results if t in e.tags]

        if network:
            results = [e for e in results if e.network == network.lower()]

        return sorted(results, key=lambda e: e.label.lower())

    def to_dict_with_mvx(self) -> dict:
        """
        Serialize the full payload including mvx_keys.

        Use this instead of payload.to_dict() when MVX entries are present.
        """
        base = self._payload.to_dict()
        base["mvx_keys"] = {
            k: v.model_dump(mode="json")
            for k, v in self.mvx_keys.items()
        }
        return base
