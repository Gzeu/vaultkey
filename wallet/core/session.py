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
"""

import ctypes
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from wallet.utils.audit import audit_log

SESSION_TIMEOUT_MINUTES = 15
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_BASE_DELAY = 2   # seconds
HARD_LOCKOUT_SECONDS = 60


class WalletLockedException(Exception):
    """Raised when the wallet is locked and an operation requires it to be open."""


class TooManyAttemptsException(Exception):
    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(f"Too many failed attempts. Wait {wait_seconds}s.")


class SessionManager:
    """Thread-safe singleton managing the unlocked wallet session."""

    _instance: Optional["SessionManager"] = None
    _class_lock = threading.Lock()

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
                inst._op_lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def unlock(self, derived_key: bytes) -> None:
        """Store the derived key and start the inactivity timer."""
        with self._op_lock:
            self._derived_key = bytearray(derived_key)
            self._unlocked_at = datetime.now()
            self._last_activity = datetime.now()
            self._failed_attempts = 0
            self._reset_timer()
        audit_log("UNLOCK", status="OK")

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
        """Increment failure counter and apply exponential delay."""
        with self._op_lock:
            self._failed_attempts += 1
            self._last_failed_at = datetime.now()
        audit_log("UNLOCK_FAIL", extra=f"attempt={self._failed_attempts}", status="FAIL")
        if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
            time.sleep(HARD_LOCKOUT_SECONDS)
            raise TooManyAttemptsException(wait_seconds=HARD_LOCKOUT_SECONDS)
        delay = min(LOCKOUT_BASE_DELAY ** (self._failed_attempts - 1), 60)
        time.sleep(delay)

    @property
    def is_unlocked(self) -> bool:
        return self._derived_key is not None and not self._is_timed_out()

    @property
    def info(self) -> dict:
        return {
            "unlocked": self.is_unlocked,
            "unlocked_at": self._unlocked_at.isoformat() if self._unlocked_at else None,
            "last_activity": self._last_activity.isoformat() if self._last_activity else None,
            "timeout_minutes": SESSION_TIMEOUT_MINUTES,
            "failed_attempts": self._failed_attempts,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _zero_key(self) -> None:
        if self._derived_key:
            addr = ctypes.addressof(
                (ctypes.c_char * len(self._derived_key)).from_buffer(self._derived_key)
            )
            ctypes.memset(addr, 0, len(self._derived_key))
            self._derived_key = None

    def _cancel_timer(self) -> None:
        if self._timeout_timer and self._timeout_timer.is_alive():
            self._timeout_timer.cancel()
            self._timeout_timer = None

    def _reset_timer(self) -> None:
        self._cancel_timer()
        t = threading.Timer(SESSION_TIMEOUT_MINUTES * 60, self.lock, kwargs={"reason": "timeout"})
        t.daemon = True
        t.start()
        self._timeout_timer = t

    def _touch(self) -> None:
        self._last_activity = datetime.now()
        self._reset_timer()

    def _is_timed_out(self) -> bool:
        if self._last_activity is None:
            return True
        return datetime.now() - self._last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    def _check_lockout(self) -> None:
        if self._failed_attempts >= MAX_FAILED_ATTEMPTS and self._last_failed_at:
            elapsed = (datetime.now() - self._last_failed_at).total_seconds()
            remaining = max(0, HARD_LOCKOUT_SECONDS - int(elapsed))
            if remaining > 0:
                raise TooManyAttemptsException(wait_seconds=remaining)
            self._failed_attempts = 0
