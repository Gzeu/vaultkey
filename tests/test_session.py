"""
Tests for SessionManager: unlock/lock, timeout, brute-force, deadlock regression.

FIX #1 regression test: verify that record_failed_attempt() does NOT hold
_op_lock during sleep — a concurrent get_key() must not be blocked.
"""

import secrets
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from wallet.core.session import (
    MAX_FAILED_ATTEMPTS,
    SESSION_TIMEOUT_MINUTES,
    SessionManager,
    TooManyAttemptsException,
    WalletLockedException,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset SessionManager singleton state before each test."""
    SessionManager._instance = None
    yield
    sm = SessionManager._instance
    if sm and sm._derived_key:
        sm.lock()
    SessionManager._instance = None


class TestUnlockLock:
    def test_unlock_sets_key(self):
        sm = SessionManager()
        key = secrets.token_bytes(32)
        sm.unlock(key)
        assert sm.is_unlocked
        assert sm.get_key() == key

    def test_lock_clears_key(self):
        sm = SessionManager()
        sm.unlock(secrets.token_bytes(32))
        internal_buf = sm._derived_key
        sm.lock()
        assert not sm.is_unlocked
        assert all(b == 0 for b in internal_buf)

    def test_get_key_when_locked_raises(self):
        sm = SessionManager()
        with pytest.raises(WalletLockedException):
            sm.get_key()

    def test_get_key_returns_immutable_copy(self):
        sm = SessionManager()
        key = secrets.token_bytes(32)
        sm.unlock(key)
        retrieved = sm.get_key()
        assert retrieved == key
        assert isinstance(retrieved, bytes)   # immutable copy, not bytearray
        assert retrieved is not sm._derived_key

    def test_last_failed_at_reset_on_unlock(self):
        sm = SessionManager()
        sm._failed_attempts = 3
        sm._last_failed_at = datetime.now()
        sm.unlock(secrets.token_bytes(32))
        assert sm._failed_attempts == 0
        assert sm._last_failed_at is None


class TestTimeout:
    def test_expired_session_raises(self):
        sm = SessionManager()
        sm.unlock(secrets.token_bytes(32))
        sm._last_activity = datetime.now() - timedelta(
            minutes=SESSION_TIMEOUT_MINUTES + 1
        )
        with pytest.raises(WalletLockedException, match="timed out"):
            sm.get_key()

    def test_active_session_does_not_expire(self):
        sm = SessionManager()
        key = secrets.token_bytes(32)
        sm.unlock(key)
        assert sm.is_unlocked
        assert sm.get_key() == key

    def test_key_zeroed_after_timeout(self):
        sm = SessionManager()
        sm.unlock(secrets.token_bytes(32))
        buf = sm._derived_key
        sm._last_activity = datetime.now() - timedelta(
            minutes=SESSION_TIMEOUT_MINUTES + 1
        )
        with pytest.raises(WalletLockedException):
            sm.get_key()
        assert all(b == 0 for b in buf)


class TestBruteForce:
    def test_failed_attempt_increments_counter(self):
        sm = SessionManager()
        with patch("time.sleep"):
            sm.record_failed_attempt()
        assert sm._failed_attempts == 1

    def test_max_attempts_triggers_hard_lockout(self):
        sm = SessionManager()
        with patch("time.sleep"):
            for _ in range(MAX_FAILED_ATTEMPTS - 1):
                sm.record_failed_attempt()
            with pytest.raises(TooManyAttemptsException) as exc_info:
                sm.record_failed_attempt()
        assert exc_info.value.wait_seconds == 60

    def test_check_lockout_raises_during_window(self):
        sm = SessionManager()
        sm._failed_attempts = MAX_FAILED_ATTEMPTS
        sm._last_failed_at = datetime.now()
        with pytest.raises(TooManyAttemptsException):
            sm._check_lockout()

    def test_lockout_resets_after_window(self):
        sm = SessionManager()
        sm._failed_attempts = MAX_FAILED_ATTEMPTS
        sm._last_failed_at = datetime.now() - timedelta(seconds=61)
        # Should NOT raise — window expired
        sm._check_lockout()
        assert sm._failed_attempts == 0
        assert sm._last_failed_at is None

    # ------------------------------------------------------------------ #
    # FIX #1 REGRESSION: sleep outside lock — no deadlock
    # ------------------------------------------------------------------ #
    def test_no_deadlock_concurrent_get_key_during_sleep(self):
        """
        Regression test for FIX #1:
        record_failed_attempt() must NOT hold _op_lock during sleep.

        If sleep were inside the lock, sm.unlock() in the concurrent thread
        would block for the full sleep duration — this test would time out.

        Method:
        1. Start a thread that calls record_failed_attempt() (will sleep 1s).
        2. From the main thread, call sm.unlock() ~0.2s into the sleep.
        3. Verify unlock() completes in well under 1s.
        """
        sm = SessionManager()
        unlock_duration: list[float] = []

        def _attempt():
            with patch("wallet.core.session.LOCKOUT_BASE_DELAY", 2):
                try:
                    sm.record_failed_attempt()  # will sleep 1s (2^0)
                except Exception:
                    pass

        t = threading.Thread(target=_attempt, daemon=True)
        t.start()
        time.sleep(0.15)   # let the thread enter sleep

        start = time.monotonic()
        sm.unlock(secrets.token_bytes(32))
        unlock_duration.append(time.monotonic() - start)

        t.join(timeout=5)
        # unlock() must have completed almost instantly (< 0.5s)
        # If lock were held during sleep, it would have taken ~1s+
        assert unlock_duration[0] < 0.5, (
            f"unlock() took {unlock_duration[0]:.2f}s — lock was held during sleep (deadlock regression)"
        )


class TestSingleton:
    def test_singleton_returns_same_instance(self):
        sm1 = SessionManager()
        sm2 = SessionManager()
        assert sm1 is sm2

    def test_state_shared_across_instances(self):
        key = secrets.token_bytes(32)
        SessionManager().unlock(key)
        assert SessionManager().get_key() == key
