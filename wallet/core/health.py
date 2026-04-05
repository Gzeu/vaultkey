"""
health.py — API key health analysis and rotation recommendations.

Provides per-entry health scoring and wallet-wide health summary.

Health score (0–100):
  - Starts at 100
  - -30 if expired
  - -20 if expiring within 30 days
  - -20 if not accessed in >90 days (stale)
  - -10 if never accessed
  - -10 if access_count == 0
  - -10 if no expiry set (undated key, harder to rotate on schedule)
  + small bonus for having tags and description (better metadata = lower neglect risk)

Design decisions:
- Health is computed purely from metadata — no decryption required.
- This means health checks can run even without session unlock (read-only).
- The score is advisory only. It does not block any operation.
- All thresholds are constants at module level — easy to tune or override via config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wallet.models.wallet import APIKeyEntry, WalletPayload

# Thresholds (all in days)
STALE_AFTER_DAYS: int = 90
EXPIRING_SOON_DAYS: int = 30
OLD_KEY_DAYS: int = 365


@dataclass(frozen=True)
class EntryHealth:
    entry_id: str
    name: str
    score: int              # 0–100
    grade: str              # A / B / C / D / F
    issues: list[str]
    recommendations: list[str]

    @property
    def is_healthy(self) -> bool:
        return self.score >= 70


@dataclass
class WalletHealth:
    total: int = 0
    healthy: int = 0        # score >= 70
    warning: int = 0        # score 40–69
    critical: int = 0       # score < 40
    entries: list[EntryHealth] = field(default_factory=list)

    @property
    def overall_score(self) -> int:
        if not self.entries:
            return 100
        return int(sum(e.score for e in self.entries) / len(self.entries))

    @property
    def overall_grade(self) -> str:
        return _score_to_grade(self.overall_score)


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 55:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def analyze_entry(entry: "APIKeyEntry") -> EntryHealth:
    """Compute a health score and recommendations for a single entry."""
    now = datetime.now(timezone.utc)
    score = 100
    issues: list[str] = []
    recs: list[str] = []

    # --- Expiry checks ---
    if entry.is_expired:
        score -= 30
        issues.append("Key is expired")
        recs.append("Revoke and replace with a new key immediately")
    elif entry.expires_soon:
        delta = (entry.expires_at - now).days  # type: ignore[operator]
        score -= 20
        issues.append(f"Expires in {delta} day(s)")
        recs.append(f"Rotate before expiry (within {delta} day(s))")
    elif entry.expires_at is None:
        score -= 10
        issues.append("No expiry date set")
        recs.append("Set an expiry date to enforce rotation schedule")

    # --- Staleness checks ---
    if entry.last_accessed_at is None:
        score -= 10
        issues.append("Never accessed")
        recs.append("Verify this key is still needed")
    else:
        days_since_access = (now - entry.last_accessed_at).days
        if days_since_access > STALE_AFTER_DAYS:
            score -= 20
            issues.append(f"Not accessed for {days_since_access} days")
            recs.append(
                f"Review if still in use (last used {days_since_access}d ago)"
            )

    # --- Age checks ---
    age_days = (now - entry.created_at).days
    if age_days > OLD_KEY_DAYS and not entry.expires_at:
        score -= 10
        issues.append(f"Key is {age_days} days old with no rotation policy")
        recs.append(
            f"Consider rotating — this key is over {OLD_KEY_DAYS // 365} year(s) old"
        )

    # --- Access count ---
    if entry.access_count == 0:
        score -= 5

    # --- Metadata quality (small bonus) ---
    if entry.tags:
        score = min(100, score + 3)
    if entry.description:
        score = min(100, score + 2)

    # --- Active check ---
    if not entry.is_active:
        score = 0
        issues = ["Key is revoked"]
        recs = ["Remove this entry if no longer needed"]

    score = max(0, score)

    return EntryHealth(
        entry_id=entry.id,
        name=entry.name,
        score=score,
        grade=_score_to_grade(score),
        issues=issues,
        recommendations=recs,
    )


def analyze_wallet(payload: "WalletPayload") -> WalletHealth:
    """Compute aggregate health for the entire wallet."""
    wh = WalletHealth(total=len(payload.keys))
    for entry in payload.keys.values():
        eh = analyze_entry(entry)
        wh.entries.append(eh)
        if eh.score >= 70:
            wh.healthy += 1
        elif eh.score >= 40:
            wh.warning += 1
        else:
            wh.critical += 1
    # Sort by score ascending (worst first)
    wh.entries.sort(key=lambda e: e.score)
    return wh
