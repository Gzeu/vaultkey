"""Tests for SessionManager: unlock/lock, timeout, brute-force protection."""

import secrets
import time
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from wallet.core.session import (
    SessionManager, WalletLockedException, TooManyAttemptsException,
    SESSION_TIMEOUT_MINUTES, MAX_FAILED_ATTEMPTS
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

    def test_get_key_returns_copy(self):
        sm = SessionManager()
        key = secrets.token_bytes(32)
        sm.unlock(key)
        retrieved = sm.get_key()
        assert retrieved == key
        assert retrieved is not sm._derived_key


class TestTimeout:
    def test_expired_session_raises(self):
        sm = SessionManager()
        sm.unlock(secrets.token_bytes(32))
        # Manually set last_activity to the past
        sm._last_activity = datetime.now() - timedelta(minutes=SESSION_TIMEOUT_MINUTES + 1)
        with pytest.raises(WalletLockedException, match="timed out"):
            sm.get_key()

    def test_active_session_does_not_expire(self):
        sm = SessionManager()
        key = secrets.token_bytes(32)
        sm.unlock(key)
        # Still within timeout
        assert sm.is_unlocked
        assert sm.get_key() == key


class TestBruteForce:
    def test_failed_attempt_increments_counter(self):
        sm = SessionManager()
        with patch("time.sleep"):  # Skip actual delays in tests
            try:
                sm.record_failed_attempt()
            except TooManyAttemptsException:
                pass
        assert sm._failed_attempts >= 1

    def test_max_attempts_raises_lockout(self):
        sm = SessionManager()
        with patch("time.sleep"):
            for _ in range(MAX_FAILED_ATTEMPTS - 1):
                sm.record_failed_attempt()
            with pytest.raises(TooManyAttemptsException):
                sm.record_failed_attempt()

    def test_lockout_clears_after_period(self):
        sm = SessionManager()
        with patch("time.sleep"):
            sm._failed_attempts = MAX_FAILED_ATTEMPTS
            sm._last_failed_at = datetime.now() - timedelta(seconds=61)
            # Should reset and allow get_key after unlock
            sm.unlock(secrets.token_bytes(32))
            assert sm.is_unlocked


class TestSingleton:
    def test_singleton_returns_same_instance(self):
        sm1 = SessionManager()
        sm2 = SessionManager()
        assert sm1 is sm2

    def test_state_shared_across_instances(self):
        key = secrets.token_bytes(32)
        SessionManager().unlock(key)
        assert SessionManager().get_key() == key
