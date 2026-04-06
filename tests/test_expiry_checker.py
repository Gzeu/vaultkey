"""
tests/test_expiry_checker.py — Tests for wallet.utils.expiry_checker

Covers:
  E1  check_expiry: expired entries are categorised correctly
  E2  check_expiry: entries within warn_days go to .warning
  E3  check_expiry: entries beyond warn_days go to .ok
  E4  check_expiry: entries with no expires_at go to .no_expiry
  E5  ExpiryReport.summary() contains correct counts
  E6  ExpiryReport.total == sum of all categories
  E7  ExpiryChecker.check_now() fires on_expired callback
  E8  ExpiryChecker.check_now() fires on_warning callback
  E9  ExpiryChecker: callbacks NOT fired for .ok entries
  E10 ExpiryChecker.start/stop: daemon thread lifecycle
  E11 check_expiry: custom warn_days=7 — tighter warning window
  E12 check_expiry: mixed wallet — counts add up to total entries
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wallet.utils.expiry_checker import ExpiryChecker, ExpiryReport, check_expiry


# ------------------------------------------------------------------ fixtures

@pytest.fixture()
def mixed_payload(make_entry, payload_with_keys):
    """Payload with expired, warning, ok, and no-expiry entries."""
    payload, _ = payload_with_keys  # already has expired + soon entries
    return payload


# ------------------------------------------------------------------ E1
def test_expired_categorised(mixed_payload):
    """E1: expired entries land in report.expired."""
    report = check_expiry(mixed_payload, warn_days=30)
    for e in report.expired:
        assert e.expires_at is not None
        assert e.expires_at <= datetime.now(timezone.utc)


# ------------------------------------------------------------------ E2
def test_warning_categorised(mixed_payload):
    """E2: entries within warn_days land in report.warning."""
    report = check_expiry(mixed_payload, warn_days=30)
    now = datetime.now(timezone.utc)
    for e in report.warning:
        assert e.expires_at is not None
        assert e.expires_at > now
        assert (e.expires_at - now).days <= 30


# ------------------------------------------------------------------ E3
def test_ok_categorised(make_entry, mixed_payload):
    """E3: entries far in the future land in report.ok."""
    future = datetime.now(timezone.utc) + timedelta(days=365)
    mixed_payload.add_entry(make_entry(name="far-future", expires_at=future))
    report = check_expiry(mixed_payload, warn_days=30)
    ok_names = [e.name for e in report.ok]
    assert "far-future" in ok_names


# ------------------------------------------------------------------ E4
def test_no_expiry_categorised(make_entry, mixed_payload):
    """E4: entries without expires_at land in report.no_expiry."""
    mixed_payload.add_entry(make_entry(name="no-expiry-entry", expires_at=None))
    report = check_expiry(mixed_payload, warn_days=30)
    no_exp_names = [e.name for e in report.no_expiry]
    assert "no-expiry-entry" in no_exp_names


# ------------------------------------------------------------------ E5
def test_summary_correct(mixed_payload):
    """E5: summary() reflects actual counts."""
    report = check_expiry(mixed_payload, warn_days=30)
    summary = report.summary()
    assert str(len(report.expired)) in summary
    assert str(len(report.warning)) in summary


# ------------------------------------------------------------------ E6
def test_total_equals_all_categories(mixed_payload):
    """E6: report.total == sum of all category lists."""
    report = check_expiry(mixed_payload, warn_days=30)
    assert report.total == (
        len(report.expired) + len(report.warning)
        + len(report.ok) + len(report.no_expiry)
    )


# ------------------------------------------------------------------ E7
def test_checker_on_expired_callback(make_entry):
    """E7: on_expired callback fired for expired entries."""
    from wallet.models.wallet import WalletPayload
    payload = WalletPayload(entries=[])
    past = datetime.now(timezone.utc) - timedelta(days=1)
    payload.add_entry(make_entry(name="old-key", expires_at=past))

    fired = []
    checker = ExpiryChecker(payload, warn_days=30, on_expired=fired.append)
    checker.check_now()
    assert any(e.name == "old-key" for e in fired)


# ------------------------------------------------------------------ E8
def test_checker_on_warning_callback(make_entry):
    """E8: on_warning callback fired for entries expiring soon."""
    from wallet.models.wallet import WalletPayload
    payload = WalletPayload(entries=[])
    soon = datetime.now(timezone.utc) + timedelta(days=10)
    payload.add_entry(make_entry(name="soon-key", expires_at=soon))

    fired = []
    checker = ExpiryChecker(payload, warn_days=30, on_warning=fired.append)
    checker.check_now()
    assert any(e.name == "soon-key" for e in fired)


# ------------------------------------------------------------------ E9
def test_checker_no_callback_for_ok(make_entry):
    """E9: neither callback fires for entries far in the future."""
    from wallet.models.wallet import WalletPayload
    payload = WalletPayload(entries=[])
    far = datetime.now(timezone.utc) + timedelta(days=999)
    payload.add_entry(make_entry(name="safe-key", expires_at=far))

    exp_fired, warn_fired = [], []
    checker = ExpiryChecker(
        payload, warn_days=30,
        on_expired=exp_fired.append, on_warning=warn_fired.append,
    )
    checker.check_now()
    assert exp_fired == []
    assert warn_fired == []


# ------------------------------------------------------------------ E10
def test_checker_thread_lifecycle(mixed_payload):
    """E10: start() spawns a daemon thread; stop() joins it cleanly."""
    checker = ExpiryChecker(mixed_payload, interval_secs=3600)
    checker.start()
    assert checker._thread is not None
    assert checker._thread.is_alive()
    checker.stop()
    assert not checker._thread.is_alive()


# ------------------------------------------------------------------ E11
def test_warn_days_7(make_entry):
    """E11: custom warn_days=7 — 10-day-away entry lands in .ok."""
    from wallet.models.wallet import WalletPayload
    payload = WalletPayload(entries=[])
    ten_days = datetime.now(timezone.utc) + timedelta(days=10)
    payload.add_entry(make_entry(name="ten-day", expires_at=ten_days))

    report = check_expiry(payload, warn_days=7)
    ok_names = [e.name for e in report.ok]
    assert "ten-day" in ok_names


# ------------------------------------------------------------------ E12
def test_total_counts_match_payload(mixed_payload):
    """E12: report.total == len(payload.entries)."""
    report = check_expiry(mixed_payload, warn_days=30)
    assert report.total == len(mixed_payload.entries)
