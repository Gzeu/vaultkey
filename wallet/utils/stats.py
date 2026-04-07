"""
stats.py — Wallet statistics and analytics engine.

Provides a snapshot of vault health, usage patterns, and security posture
without ever decrypting key values. All analysis is metadata-only.

Modules:
    VaultStats        — main result dataclass with all computed metrics.
    compute_stats()   — entry point: accepts WalletPayload, returns VaultStats.

Metrics computed:
    - Total, active, expired, expiring-soon, revoked counts.
    - Tag distribution (tag → count mapping).
    - Service distribution (service → count).
    - Unused keys (access_count == 0 AND created more than threshold days ago).
    - Most accessed keys (top N by access_count).
    - Rotation lag: days since last update for active keys.
    - Keys never rotated (updated_at == created_at, older than threshold).
    - Average key age (days since creation).
    - Overall vault security score (0–100).

Scoring algorithm (simple, auditable):
    Start at 100. Deduct:
        -5 per expired key (capped at -30)
        -3 per key expiring soon (capped at -15)
        -2 per unused key older than UNUSED_THRESHOLD_DAYS (capped at -20)
        -2 per key never rotated older than STALE_THRESHOLD_DAYS (capped at -20)
    Floor at 0. Round to nearest int.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wallet.models.wallet import WalletPayload

UNUSED_THRESHOLD_DAYS = 30      # key older than this with 0 accesses is "unused"
STALE_THRESHOLD_DAYS = 90       # key not updated in this many days is "stale"
TOP_ACCESSED_N = 10             # top N most-accessed keys to report


@dataclass
class KeyAgeStat:
    """Age/rotation data for a single key."""
    name: str
    service: str
    days_since_created: int
    days_since_updated: int
    access_count: int
    status: str


@dataclass
class VaultStats:
    """
    Aggregated statistics snapshot for a WalletPayload.

    All counts are integers. All lists are sorted by relevance.
    """
    # Counts
    total: int = 0
    active: int = 0
    expired: int = 0
    expiring_soon: int = 0
    revoked: int = 0
    unused: int = 0
    never_rotated: int = 0

    # Distributions
    tag_distribution: dict[str, int] = field(default_factory=dict)
    service_distribution: dict[str, int] = field(default_factory=dict)

    # Lists
    most_accessed: list[KeyAgeStat] = field(default_factory=list)
    unused_keys: list[KeyAgeStat] = field(default_factory=list)
    stale_keys: list[KeyAgeStat] = field(default_factory=list)

    # Averages
    average_age_days: float = 0.0
    average_rotation_lag_days: float = 0.0

    # Score
    vault_score: int = 100

    # Metadata
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def compute_stats(payload: "WalletPayload") -> VaultStats:
    """
    Compute comprehensive statistics from a WalletPayload.

    Args:
        payload: The loaded, decrypted WalletPayload (not the raw dict).

    Returns:
        A VaultStats dataclass with all metrics populated.
    """
    now = datetime.now(timezone.utc)
    entries = list(payload.keys.values())
    stats = VaultStats(total=len(entries))

    if not entries:
        stats.vault_score = 100
        return stats

    age_data: list[KeyAgeStat] = []
    total_age = 0.0
    total_lag = 0.0

    for entry in entries:
        # Status counts
        if not entry.is_active:
            stats.revoked += 1
        elif entry.is_expired:
            stats.expired += 1
        elif entry.expires_soon:
            stats.expiring_soon += 1
        else:
            stats.active += 1

        # Age
        days_created = max(0, (now - entry.created_at).days)
        days_updated = max(0, (now - entry.updated_at).days)
        total_age += days_created
        total_lag += days_updated

        # Unused (zero accesses AND old enough)
        if entry.access_count == 0 and days_created >= UNUSED_THRESHOLD_DAYS:
            stats.unused += 1

        # Never rotated (updated_at == created_at within 60 seconds AND old)
        delta_seconds = abs((entry.updated_at - entry.created_at).total_seconds())
        if delta_seconds < 60 and days_created >= STALE_THRESHOLD_DAYS:
            stats.never_rotated += 1

        # Tag distribution
        for tag in entry.tags:
            stats.tag_distribution[tag] = stats.tag_distribution.get(tag, 0) + 1

        # Service distribution
        svc = entry.service.lower()
        stats.service_distribution[svc] = stats.service_distribution.get(svc, 0) + 1

        age_data.append(KeyAgeStat(
            name=entry.name,
            service=entry.service,
            days_since_created=days_created,
            days_since_updated=days_updated,
            access_count=entry.access_count,
            status=entry.status_label,
        ))

    # Averages
    n = len(entries)
    stats.average_age_days = round(total_age / n, 1)
    stats.average_rotation_lag_days = round(total_lag / n, 1)

    # Most accessed
    stats.most_accessed = sorted(
        age_data, key=lambda x: x.access_count, reverse=True
    )[:TOP_ACCESSED_N]

    # Unused keys
    stats.unused_keys = [
        a for a in age_data
        if a.access_count == 0 and a.days_since_created >= UNUSED_THRESHOLD_DAYS
    ]

    # Stale (never rotated and old)
    stats.stale_keys = [
        a for a in age_data
        if a.days_since_updated >= STALE_THRESHOLD_DAYS
    ]

    # Sort distributions by count desc
    stats.tag_distribution = dict(
        sorted(stats.tag_distribution.items(), key=lambda x: x[1], reverse=True)
    )
    stats.service_distribution = dict(
        sorted(stats.service_distribution.items(), key=lambda x: x[1], reverse=True)
    )

    # Vault score
    score = 100
    score -= min(30, stats.expired * 5)
    score -= min(15, stats.expiring_soon * 3)
    score -= min(20, stats.unused * 2)
    score -= min(20, stats.never_rotated * 2)
    stats.vault_score = max(0, score)

    return stats


def format_stats_report(stats: VaultStats) -> str:
    """
    Render a plain-text statistics summary (for CLI output or Markdown export).

    Returns:
        Multi-line string suitable for console.print() or file writing.
    """
    lines = [
        f"VaultKey Statistics  —  {stats.computed_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 55,
        f"Total keys:         {stats.total}",
        f"Active:             {stats.active}",
        f"Expired:            {stats.expired}",
        f"Expiring soon:      {stats.expiring_soon}",
        f"Revoked:            {stats.revoked}",
        f"Unused (30d+):      {stats.unused}",
        f"Never rotated:      {stats.never_rotated}",
        f"Avg age (days):     {stats.average_age_days}",
        f"Avg rotation lag:   {stats.average_rotation_lag_days} days",
        f"Vault score:        {stats.vault_score}/100",
        "",
        "Top tags:",
    ]
    for tag, count in list(stats.tag_distribution.items())[:10]:
        lines.append(f"  {tag:30s} {count}")
    lines.append("")
    lines.append("Top services:")
    for svc, count in list(stats.service_distribution.items())[:10]:
        lines.append(f"  {svc:30s} {count}")
    if stats.most_accessed:
        lines.append("")
        lines.append("Most accessed:")
        for a in stats.most_accessed[:5]:
            lines.append(f"  {a.name:30s} {a.access_count} accesses")
    if stats.stale_keys:
        lines.append("")
        lines.append(f"Stale keys ({len(stats.stale_keys)}) — not rotated in 90+ days:")
        for a in stats.stale_keys[:5]:
            lines.append(
                f"  {a.name:30s} {a.days_since_updated}d since last rotation"
            )
    return "\n".join(lines)
