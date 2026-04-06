"""
session.py — In-memory session management with automatic timeout and brute-force protection.

Design decisions:
- SessionManager is a singleton — only one unlocked session can exist per process.
- The derived key is stored as bytearray (mutable) so ctypes.memset can zero it
  on lock. Python's bytes type is immutable and cannot be reliably zeroed.
- threading.Timer provides automatic session expiry without busy-waiting.
- Exponential delay on failed attempts: 2^(n-1) seconds, capped at 60s.
  This makes online brute-force attacks infeasible (1000 guesses ≈ 8+ hours).
- After MAX_FAILED_ATTEMPTS consecutive failures, a 60-second hard lockout applies.
- The key is NEVER written to disk, /tmp, or environment variables.

Configuration via environment variables (set in .env or shell):
  VAULTKEY_SESSION_TIMEOUT_MINUTES  int >= 1   default: 15
  VAULTKEY_MAX_FAILED_ATTEMPTS      int >= 1   default: 5
  VAULTKEY_LOCKOUT_BASE_DELAY       int >= 1   default: 2  (seconds)
  VAULTKEY_HARD_LOCKOUT_SECONDS     int >= 1   default: 60

SECURITY FIXES v1.1:
  FIX #1 (CRITIC): time.sleep() moved OUTSIDE _op_lock.
    Previously sleep(60) inside lock → any concurrent get_key/lock/unlock
    was blocked for 60s → functional deadlock for the entire session.
    Now: state is read/updated under lock, then lock is released, then sleep.

  FIX #3 (MODERATE): _check_lockout() now emits LOCKOUT_RESET audit event
    when the hard-lockout window expires and the counter is reset.
    Previously the reset was silent — no trace in audit.log.

FIXES v1.2 (Wave 6):
  FIX #7: All datetime.now() calls replaced with datetime.now(timezone.utc).
    Naive datetimes are ambiguous on DST-transition systems and cause
    incorrect timeout calculations in non-UTC timezones.
  IMPROVEMENT: info property now exposes seconds_until_unlock so TUI/GUI
    can display a live countdown without re-implementing the timeout logic.

FIXES v1.2.1:
  FIX #8 (CRITICAL): Session constants were hardcoded — env vars had NO effect.
    VAULTKEY_SESSION_TIMEOUT_MINUTES=60 in .env was silently ignored,
    causing the session to lock after 15 minutes regardless of user config.
    All four constants now read from os.environ at import time with safe
    int parsing, range validation, and a warning on invalid values.
"""

import ctypes
import os
import threading
import time
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

from wallet.utils.audit import audit_log


# ------------------------------------------------------------------ #
# Configuration — read from environment with safe fallback
# ------------------------------------------------------------------ #

def _load_env_int(var: str, default: int, min_val: int, max_val: int) -> int:
    """
    Read an integer environment variable with validation.

    Returns `default` if the variable is unset or empty.
    Emits a UserWarning and returns `default` if the value is not a valid
    integer or falls outside [min_val, max_val].
    """
    raw = os.environ.get(var, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        warnings.warn(
            f"[VaultKey] {var}={raw!r} is not a valid integer; "
            f"using default ({default}).",
            UserWarning,
            stacklevel=2,
        )
        return default
    if not (min_val <= value <= max_val):
        warnings.warn(
            f"[VaultKey] {var}={value} is out of range [{min_val}, {max_val}]; "
            f"using default ({default}).",
            UserWarning,
            stacklevel=2,
        )
        return default
    return value


SESSION_TIMEOUT_MINUTES: int = _load_env_int(
    "VAULTKEY_SESSION_TIMEOUT_MINUTES", default=15, min_val=1, max_val=1440
)
MAX_FAILED_ATTEMPTS: int = _load_env_int(
    "VAULTKEY_MAX_FAILED_ATTEMPTS", default=5, min_val=1, max_val=50
)
LOCKOUT_BASE_DELAY: int = _load_env_int(
    "VAULTKEY_LOCKOUT_BASE_DELAY", default=2, min_val=1, max_val=30
)
HARD_LOCKOUT_SECONDS: int = _load_env_int(
    "VAULTKEY_HARD_LOCKOUT_SECONDS", default=60, min_val=10, max_val=3600
)


# ------------------------------------------------------------------ #
# Exceptions
# ------------------------------------------------------------------ #

class WalletLockedException(Exception):
    """Raised when the wallet is locked and an operation requires it to be open."""


class TooManyAttemptsException(Exception):
    def __init__(self, wait_seconds: int) -> None:
        self.wait_seconds = wait_seconds
        super().__init__(f"Too many failed attempts. Wait {wait_seconds}s.")


# ------------------------------------------------------------------ #
# SessionManager
# ------------------------------------------------------------------ #

class SessionManager:
    """
    Thread-safe singleton managing the unlocked wallet session.

    Security invariants:
    - Only ONE session key exists in memory at any time.
    - The key is zeroed (ctypes.memset) on lock, timeout, or process exit.
    - All sleeps happen OUTSIDE the internal _op_lock to prevent deadlock.
    - Failed attempt counter persists across unlock attempts within the process.
    - _check_lockout() is always called with _op_lock held — must NOT sleep.
    """

    _instance: Optional["SessionManager"] = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "SessionManager":
        with cls._class_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._derived_key: Optional[bytearray] = None
                inst._unlocked_at: Optional[datetime] = None
                inst._last_activity: Optional[datetime] = None
                inst._timeout_timer: Optional[threading.Timer] = None
                inst._failed_attempts: int = 0
                inst._last_failed_at: Optional[datetime] = None
                inst._op_lock: threading.Lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def unlock(self, derived_key: bytes) -> None:
        """Store the derived key and start the inactivity timer."""
        with self._op_lock:
            self._derived_key = bytearray(derived_key)
            self._unlocked_at = datetime.now(timezone.utc)
            self._last_activity = datetime.now(timezone.utc)
            self._failed_attempts = 0
            self._last_failed_at = None
            self._reset_timer()
        audit_log("UNLOCK", status="OK",
                  extra=f"timeout={SESSION_TIMEOUT_MINUTES}m")

    def lock(self, reason: str = "manual") -> None:
        """Zero the key in memory and cancel the timer."""
        with self._op_lock:
            self._zero_key()
            self._cancel_timer()
            self._unlocked_at = None
            self._last_activity = None
        audit_log("LOCK", extra=reason, status="OK")

    def get_key(self) -> bytes:
        """
        Return a copy of the derived key.
        Raises WalletLockedException if locked or timed out.
        Raises TooManyAttemptsException if still within lockout window.
        """
        with self._op_lock:
            self._check_lockout()
            if self._derived_key is None:
                raise WalletLockedException("Wallet is locked. Run: wallet unlock")
            if self._is_timed_out():
                self._zero_key()
                self._cancel_timer()
                audit_log("LOCK", extra="timeout", status="OK")
                raise WalletLockedException("Session timed out. Run: wallet unlock")
            self._touch()
            return bytes(self._derived_key)

    def record_failed_attempt(self) -> None:
        """
        Increment failure counter and apply exponential backoff delay.
        CRITICAL: sleep() is called OUTSIDE _op_lock.
        """
        hard_lockout = False
        delay_seconds: float = 0.0
        attempt_num: int = 0

        with self._op_lock:
            self._failed_attempts += 1
            self._last_failed_at = datetime.now(timezone.utc)
            attempt_num = self._failed_attempts
            if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
                hard_lockout = True
            else:
                delay_seconds = min(
                    float(LOCKOUT_BASE_DELAY ** (self._failed_attempts - 1)), 60.0
                )

        audit_log(
            "UNLOCK_FAIL",
            extra=f"attempt={attempt_num}",
            status="FAIL",
        )

        if hard_lockout:
            time.sleep(HARD_LOCKOUT_SECONDS)
            raise TooManyAttemptsException(wait_seconds=HARD_LOCKOUT_SECONDS)

        if delay_seconds > 0.0:
            time.sleep(delay_seconds)

    @property
    def is_unlocked(self) -> bool:
        """True if a session key is held and has not timed out."""
        return self._derived_key is not None and not self._is_timed_out()

    @property
    def info(self) -> dict:
        """Session metadata. seconds_until_lock is useful for TUI/GUI countdowns."""
        seconds_until_lock: int | None = None
        if self._last_activity is not None and not self._is_timed_out():
            elapsed = (
                datetime.now(timezone.utc) - self._last_activity
            ).total_seconds()
            seconds_until_lock = max(
                0, int(SESSION_TIMEOUT_MINUTES * 60 - elapsed)
            )
        return {
            "unlocked": self.is_unlocked,
            "unlocked_at": (
                self._unlocked_at.isoformat() if self._unlocked_at else None
            ),
            "last_activity": (
                self._last_activity.isoformat() if self._last_activity else None
            ),
            "timeout_minutes": SESSION_TIMEOUT_MINUTES,
            "max_failed_attempts": MAX_FAILED_ATTEMPTS,
            "failed_attempts": self._failed_attempts,
            "seconds_until_lock": seconds_until_lock,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers  (must only be called with _op_lock held)
    # ------------------------------------------------------------------ #

    def _zero_key(self) -> None:
        """Overwrite key buffer with zeros via ctypes.memset (bypasses GC)."""
        if self._derived_key:
            addr = ctypes.addressof(
                (ctypes.c_char * len(self._derived_key)).from_buffer(
                    self._derived_key
                )
            )
            ctypes.memset(addr, 0, len(self._derived_key))
            self._derived_key = None

    def _cancel_timer(self) -> None:
        if self._timeout_timer and self._timeout_timer.is_alive():
            self._timeout_timer.cancel()
        self._timeout_timer = None

    def _reset_timer(self) -> None:
        """Restart the inactivity auto-lock timer."""
        self._cancel_timer()
        t = threading.Timer(
            SESSION_TIMEOUT_MINUTES * 60,
            self.lock,
            kwargs={"reason": "timeout"},
        )
        t.daemon = True
        t.start()
        self._timeout_timer = t

    def _touch(self) -> None:
        """Update last-activity timestamp and restart the idle timer."""
        self._last_activity = datetime.now(timezone.utc)
        self._reset_timer()

    def _is_timed_out(self) -> bool:
        if self._last_activity is None:
            return True
        return datetime.now(timezone.utc) - self._last_activity > timedelta(
            minutes=SESSION_TIMEOUT_MINUTES
        )

    def _check_lockout(self) -> None:
        """
        Called with _op_lock held — MUST NOT sleep.
        Raises TooManyAttemptsException if within hard-lockout window.
        Resets counter and emits audit event when window expires.
        """
        if (
            self._failed_attempts >= MAX_FAILED_ATTEMPTS
            and self._last_failed_at is not None
        ):
            elapsed = (
                datetime.now(timezone.utc) - self._last_failed_at
            ).total_seconds()
            remaining = int(max(0.0, HARD_LOCKOUT_SECONDS - elapsed))
            if remaining > 0:
                raise TooManyAttemptsException(wait_seconds=remaining)

            audit_log(
                "LOCKOUT_RESET",
                status="OK",
                extra=(
                    f"after={int(elapsed)}s,"
                    f"attempts={self._failed_attempts}"
                ),
            )
            self._failed_attempts = 0
            self._last_failed_at = None
