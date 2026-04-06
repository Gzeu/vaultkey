"""
expiry_checker.py — Expiry-warning utility for VaultKey (Wave 7).

Called automatically at unlock time and available as a standalone
`wallet expiry-check` command.

Returns a list of ExpiryWarning dataclasses sorted by urgency
(soonest expiry first). Warnings are emitted only for active,
non-expired entries that fall within `days` of their expiry date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wallet.models.wallet import WalletPayload


@dataclass(frozen=True, order=True)
class ExpiryWarning:
    """Single entry expiry warning, sortable by days_left."""
    days_left: int          # sort key — soonest first
    name: str
    service: str
    expires_at: datetime
    is_expired: bool

    @property
    def urgency(self) -> str:
        """Human-readable urgency label."""
        if self.is_expired:
            return "expired"
        if self.days_left <= 3:
            return "critical"
        if self.days_left <= 7:
            return "warning"
        return "info"


def check_expiry(
    payload: "WalletPayload",
    days: int = 7,
) -> list[ExpiryWarning]:
    """
    Return ExpiryWarning entries for all active keys expiring within `days`.

    Args:
        payload: The loaded WalletPayload.
        days:    Warning horizon in days (default 7).
                 Pass a higher value (e.g. 14 or 30) for broader sweeps.

    Returns:
        List of ExpiryWarning sorted by days_left ascending (soonest first).
        Empty list when no keys are near expiry.
    """
    now = datetime.now(timezone.utc)
    warnings: list[ExpiryWarning] = []

    for entry in payload.keys.values():
        if not entry.is_active or entry.expires_at is None:
            continue

        delta = entry.expires_at - now
        days_left = int(delta.total_seconds() // 86400)

        if days_left <= days:
            warnings.append(
                ExpiryWarning(
                    days_left=days_left,
                    name=entry.name,
                    service=entry.service,
                    expires_at=entry.expires_at,
                    is_expired=entry.is_expired,
                )
            )

    return sorted(warnings)
