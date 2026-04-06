"""
expiry_checker.py — Background expiry watcher for VaultKey.

Public API:
  ExpiryChecker(payload, warn_days, on_expired, on_warning)
      .start()   — launch background daemon thread
      .stop()    — signal thread to stop
      .check_now() -> ExpiryReport  — run synchronous check

  ExpiryReport   — dataclass with expired / warning / ok lists
  watch_expiry() — CLI-friendly blocking loop (Ctrl+C to stop)

The checker polls once per `interval_seconds` (default: 3600).
It calls `on_expired(entry)` / `on_warning(entry)` callbacks so
callers decide how to surface the alerts (notify, log, TUI banner, etc.).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.audit import audit_log


@dataclass
class ExpiryReport:
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expired: list[APIKeyEntry] = field(default_factory=list)
    warning: list[APIKeyEntry] = field(default_factory=list)
    ok: list[APIKeyEntry] = field(default_factory=list)
    no_expiry: list[APIKeyEntry] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.expired) + len(self.warning) + len(self.ok) + len(self.no_expiry)

    def summary(self) -> str:
        return (
            f"Checked {self.total} entries: "
            f"{len(self.expired)} expired, "
            f"{len(self.warning)} expiring soon, "
            f"{len(self.ok)} valid, "
            f"{len(self.no_expiry)} no expiry set."
        )


def check_expiry(
    payload: WalletPayload,
    warn_days: int = 30,
) -> ExpiryReport:
    """
    Synchronous, single-pass expiry scan.
    Returns an ExpiryReport with all entries categorised.
    """
    report = ExpiryReport()
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(days=warn_days)

    for entry in payload.entries:
        if entry.expires_at is None:
            report.no_expiry.append(entry)
        elif entry.expires_at <= now:
            report.expired.append(entry)
            audit_log(
                event="EXPIRY_ALERT",
                status="EXPIRED",
                key_name=entry.name,
                extra=f"expired={entry.expires_at.date()}",
            )
        elif entry.expires_at <= threshold:
            report.warning.append(entry)
            days_left = (entry.expires_at - now).days
            audit_log(
                event="EXPIRY_WARNING",
                status="WARNING",
                key_name=entry.name,
                extra=f"days_left={days_left}",
            )
        else:
            report.ok.append(entry)

    return report


class ExpiryChecker:
    """
    Background daemon thread that calls check_expiry() periodically.

    Parameters
    ----------
    payload       : Live WalletPayload reference (reads current state each poll)
    warn_days     : Days before expiry to trigger on_warning callback (default 30)
    interval_secs : Polling interval in seconds (default 3600 = 1 hour)
    on_expired    : Callback(entry) called for each expired entry
    on_warning    : Callback(entry) called for each entry expiring within warn_days
    """

    def __init__(
        self,
        payload: WalletPayload,
        warn_days: int = 30,
        interval_secs: int = 3600,
        on_expired: Optional[Callable[[APIKeyEntry], None]] = None,
        on_warning: Optional[Callable[[APIKeyEntry], None]] = None,
    ) -> None:
        self._payload = payload
        self._warn_days = warn_days
        self._interval = interval_secs
        self._on_expired = on_expired or (lambda e: None)
        self._on_warning = on_warning or (lambda e: None)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_report: Optional[ExpiryReport] = None

    @property
    def last_report(self) -> Optional[ExpiryReport]:
        return self._last_report

    def check_now(self) -> ExpiryReport:
        """Run a synchronous check and store the result."""
        report = check_expiry(self._payload, self._warn_days)
        self._last_report = report
        for entry in report.expired:
            self._on_expired(entry)
        for entry in report.warning:
            self._on_warning(entry)
        return report

    def start(self) -> None:
        """Launch the background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="vaultkey-expiry-checker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_now()
            except Exception:  # noqa: BLE001
                pass
            self._stop_event.wait(timeout=self._interval)


def watch_expiry(
    payload: WalletPayload,
    warn_days: int = 30,
    interval_secs: int = 3600,
) -> None:
    """
    Blocking expiry-watch loop.  Prints a summary each poll cycle.
    Exit with Ctrl+C.
    """
    import time

    print(f"[VaultKey] Watching for expiry every {interval_secs}s. Ctrl+C to stop.")
    checker = ExpiryChecker(payload, warn_days=warn_days, interval_secs=interval_secs)
    try:
        while True:
            report = checker.check_now()
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {report.summary()}")
            if report.expired:
                for e in report.expired:
                    print(f"  \ud83d\udd34 EXPIRED: {e.name} (expired {e.expires_at})")
            if report.warning:
                for e in report.warning:
                    days = (e.expires_at - datetime.now(timezone.utc)).days  # type: ignore
                    print(f"  \u26a0\ufe0f  WARNING: {e.name} expires in {days}d")
            time.sleep(interval_secs)
    except KeyboardInterrupt:
        print("\n[VaultKey] Watch stopped.")
