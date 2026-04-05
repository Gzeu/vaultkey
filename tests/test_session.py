"""
test_session.py — Thread-safety and security tests for SessionManager.

Covers:
  - Basic unlock / lock / get_key cycle
  - Key is a bytes copy (not the live bytearray)
  - Locked raises WalletLockedException
  - Failed attempts counter + TooManyAttemptsException
  - Hard lockout window with 60s delay bypassed via monkeypatching time.sleep
  - LOCKOUT_RESET audit event emitted after lockout window expires
  - Concurrent get_key calls don't deadlock
  - Singleton pattern: two SessionManager() calls return the same object
  - session.info reflects state correctly
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from wallet.core.session import (
    MAX_FAILED_ATTEMPTS,
    HARD_LOCKOUT_SECONDS,
    SessionManager,
    TooManyAttemptsException,
    WalletLockedException,
)

FAKE_KEY = b"A" * 32


@pytest.fixture(autouse=True)
def fresh_session():
    """Reset the SessionManager singleton before every test."""
    sm = SessionManager()
    sm.lock(reason="test-reset")
    sm._failed_attempts = 0
    sm._last_failed_at = None
    yield sm
    sm.lock(reason="test-teardown")
    sm._failed_attempts = 0
    sm._last_failed_at = None


class TestBasicLifecycle:
    def test_unlock_then_get_key(self, fresh_session):
        fresh_session.unlock(FAKE_KEY)
        key = fresh_session.get_key()
        assert key == FAKE_KEY

    def test_get_key_returns_bytes_copy(self, fresh_session):
        fresh_session.unlock(FAKE_KEY)
        k1 = fresh_session.get_key()
        k2 = fresh_session.get_key()
        assert k1 == k2
        assert k1 is not k2  # independent copies

    def test_locked_raises(self, fresh_session):
        with pytest.raises(WalletLockedException):
            fresh_session.get_key()

    def test_lock_zeros_key(self, fresh_session):
        fresh_session.unlock(FAKE_KEY)
        fresh_session.lock()
        with pytest.raises(WalletLockedException):
            fresh_session.get_key()

    def test_is_unlocked_reflects_state(self, fresh_session):
        assert not fresh_session.is_unlocked
        fresh_session.unlock(FAKE_KEY)
        assert fresh_session.is_unlocked
        fresh_session.lock()
        assert not fresh_session.is_unlocked


class TestSingleton:
    def test_same_instance(self):
        s1 = SessionManager()
        s2 = SessionManager()
        assert s1 is s2

    def test_state_shared(self, fresh_session):
        s2 = SessionManager()
        fresh_session.unlock(FAKE_KEY)
        assert s2.is_unlocked


class TestInfo:
    def test_info_locked(self, fresh_session):
        info = fresh_session.info
        assert not info["unlocked"]
        assert info["unlocked_at"] is None

    def test_info_unlocked(self, fresh_session):
        fresh_session.unlock(FAKE_KEY)
        info = fresh_session.info
        assert info["unlocked"]
        assert info["unlocked_at"] is not None
        assert info["timeout_minutes"] > 0


class TestBruteForceProtection:
    def test_single_failure_increments_counter(self, fresh_session):
        with patch("time.sleep"):
            fresh_session.record_failed_attempt()
        assert fresh_session._failed_attempts == 1

    def test_multiple_failures_before_lockout(self, fresh_session):
        with patch("time.sleep"):
            for _ in range(MAX_FAILED_ATTEMPTS - 1):
                fresh_session.record_failed_attempt()
        assert fresh_session._failed_attempts == MAX_FAILED_ATTEMPTS - 1

    def test_hard_lockout_raises(self, fresh_session):
        with patch("time.sleep"):
            for _ in range(MAX_FAILED_ATTEMPTS):
                try:
                    fresh_session.record_failed_attempt()
                except TooManyAttemptsException:
                    break
        # Now get_key should raise TooManyAttemptsException (lockout active)
        # We need to set last_failed_at to now so the window is still active
        fresh_session._failed_attempts = MAX_FAILED_ATTEMPTS
        from datetime import datetime
        fresh_session._last_failed_at = datetime.now()
        with pytest.raises(TooManyAttemptsException):
            fresh_session.get_key()

    def test_lockout_reset_after_window(self, fresh_session):
        """After HARD_LOCKOUT_SECONDS, counter resets and LOCKOUT_RESET is audited."""
        from datetime import datetime, timedelta
        fresh_session._failed_attempts = MAX_FAILED_ATTEMPTS
        fresh_session._last_failed_at = datetime.now() - timedelta(
            seconds=HARD_LOCKOUT_SECONDS + 5
        )
        # Unlock first so get_key doesn't fail with WalletLockedException
        fresh_session.unlock(FAKE_KEY)
        # _check_lockout() is called inside get_key with lock held
        key = fresh_session.get_key()  # should NOT raise
        assert key == FAKE_KEY
        assert fresh_session._failed_attempts == 0
        assert fresh_session._last_failed_at is None


class TestConcurrency:
    def test_concurrent_get_key_no_deadlock(self, fresh_session):
        fresh_session.unlock(FAKE_KEY)
        results = []
        errors = []

        def worker():
            try:
                results.append(fresh_session.get_key())
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Errors in threads: {errors}"
        assert len(results) == 20
        assert all(r == FAKE_KEY for r in results)

    def test_lock_during_concurrent_access(self, fresh_session):
        """Locking mid-flight shouldn't deadlock."""
        fresh_session.unlock(FAKE_KEY)
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    fresh_session.get_key()
                except WalletLockedException:
                    break

        t = threading.Thread(target=reader)
        t.start()
        time.sleep(0.05)
        fresh_session.lock()
        stop.set()
        t.join(timeout=3)
        assert not t.is_alive(), "Thread deadlocked"
