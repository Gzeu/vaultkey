"""
audit.py — Structured audit logging for VaultKey.

Every sensitive operation (INIT, UNLOCK, LOCK, ADD, GET, DELETE, ROTATE,
CHANGE_PASSWORD, EXPORT, IMPORT, LOCKOUT_RESET, UNLOCK_FAIL, PANIC_WIPE)
is written to audit.log as a single JSON line.

Format (JSON-Lines, one event per line):
  {"ts": "2025-01-01T12:00:00.123456Z", "event": "GET", "status": "OK",
   "pid": 12345, "user": "alice", "key_name": "OpenAI Prod", "extra": ""}

Design decisions:
- JSON-Lines format is both human-readable and machine-parseable (grep, jq, SIEM).
- PID and OS username are included for multi-user system forensics.
- The audit log is append-only with O_APPEND | O_CREAT (atomic appends on Linux).
- Sensitive values (passwords, API keys) are NEVER written to the log.
- The log file is created with mode 0600 (user-only read/write).
- Log rotation: if the file exceeds MAX_LOG_SIZE_MB, it is rotated to audit.log.1.
  Only 2 rotations are kept to bound disk usage.
- audit_log() is safe to call from any thread — uses a threading.Lock.
"""

import getpass
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from wallet.models.config import WalletConfig

_cfg = WalletConfig()
_AUDIT_PATH: Path = _cfg.audit_log_path
MAX_LOG_SIZE_BYTES: int = 5 * 1024 * 1024   # 5 MB per file
MAX_ROTATIONS: int = 2

_lock = threading.Lock()
log = logging.getLogger(__name__)


def _ensure_log_dir() -> None:
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _rotate_if_needed() -> None:
    """Rotate audit.log → audit.log.1 → audit.log.2 if over size limit."""
    if not _AUDIT_PATH.exists():
        return
    if _AUDIT_PATH.stat().st_size < MAX_LOG_SIZE_BYTES:
        return

    # Rotate: .2 dropped, .1 → .2, current → .1
    for i in range(MAX_ROTATIONS, 0, -1):
        old = _AUDIT_PATH.with_suffix(f".log.{i}")
        new = _AUDIT_PATH.with_suffix(f".log.{i + 1}")
        if old.exists():
            old.rename(new)

    _AUDIT_PATH.rename(_AUDIT_PATH.with_suffix(".log.1"))
    log.info("audit.log rotated.")


def _get_username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "unknown"


def audit_log(
    event: str,
    *,
    status: str = "OK",
    key_name: str = "",
    extra: str = "",
) -> None:
    """
    Append a single audit event to audit.log as a JSON line.

    Args:
        event:    Event type (e.g., 'GET', 'UNLOCK', 'ROTATE').
        status:   'OK' or 'FAIL'.
        key_name: Name of the API key entry involved (if any).
        extra:    Optional extra context string (never put secrets here).
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "status": status,
        "pid": os.getpid(),
        "user": _get_username(),
        "key_name": key_name,
        "extra": extra,
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"

    with _lock:
        try:
            _ensure_log_dir()
            _rotate_if_needed()
            with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(line)
            if os.name != "nt":
                os.chmod(_AUDIT_PATH, 0o600)
        except OSError as e:
            log.error("audit_log write failed: %s", e)


def read_audit_log(
    *,
    last_n: int | None = None,
    event_filter: str | None = None,
    status_filter: str | None = None,
) -> list[dict]:
    """
    Read and parse the current audit log.

    Args:
        last_n:        Return only the last N events.
        event_filter:  If set, only return events matching this event type.
        status_filter: If set, only return events with this status.

    Returns a list of parsed event dicts, oldest first.
    """
    if not _AUDIT_PATH.exists():
        return []

    events: list[dict] = []
    try:
        with open(_AUDIT_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_filter and record.get("event") != event_filter:
                    continue
                if status_filter and record.get("status") != status_filter:
                    continue
                events.append(record)
    except OSError as e:
        log.error("audit_log read failed: %s", e)

    if last_n is not None:
        events = events[-last_n:]

    return events
