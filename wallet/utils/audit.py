"""
audit.py — Append-only audit logger.

Logs all sensitive operations WITHOUT including key values or passwords.
The audit log is plaintext and append-only — no rotation (use logrotate externally).
"""

import os
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG_PATH = Path(os.environ.get("VAULTKEY_AUDIT_LOG_PATH", "audit.log"))

VALID_ACTIONS = {
    "UNLOCK", "UNLOCK_FAIL", "LOCK", "ADD", "GET",
    "DELETE", "EXPORT", "IMPORT", "ROTATE", "COPY_CLIPBOARD",
    "CHANGE_PASSWORD", "INIT", "RENAME", "TAG_UPDATE",
}


def audit_log(
    action: str,
    key_name: str = "-",
    status: str = "OK",
    extra: str = "",
) -> None:
    """
    Append one audit line to the log file.
    Format: [ISO8601 UTC] ACTION key_name STATUS [extra]
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    extra_part = f" [{extra}]" if extra else ""
    line = f"[{ts}] {action:<20} {key_name:<30} {status}{extra_part}\n"
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass  # Never crash on audit log failure
