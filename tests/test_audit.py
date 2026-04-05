"""
test_audit.py — Tests for wallet/utils/audit.py.

Covers:
  - audit_log() writes a valid JSON line
  - read_audit_log() parses events correctly
  - event_filter and status_filter work
  - last_n slicing
  - Log rotation triggered at MAX_LOG_SIZE_BYTES
  - File permissions are 0600 on Unix
  - Thread-safe concurrent writes (100 threads)
  - Missing log returns empty list
"""

import json
import os
import stat
import threading
from pathlib import Path
from unittest.mock import patch

import pytest


# We monkeypatch the module-level _AUDIT_PATH so tests write to tmp_path


@pytest.fixture()
def audit_path(tmp_path: Path):
    log_file = tmp_path / "audit.log"
    with (
        patch("wallet.utils.audit._AUDIT_PATH", log_file),
        patch("wallet.utils.audit._cfg"),  # prevent WalletConfig from running
    ):
        yield log_file


class TestWrite:
    def test_writes_json_line(self, audit_path):
        from wallet.utils.audit import audit_log
        audit_log("TEST", status="OK", key_name="my-key", extra="hello")
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "TEST"
        assert record["status"] == "OK"
        assert record["key_name"] == "my-key"
        assert record["extra"] == "hello"
        assert "ts" in record
        assert "pid" in record
        assert "user" in record

    def test_multiple_events_multiple_lines(self, audit_path):
        from wallet.utils.audit import audit_log
        audit_log("A", status="OK")
        audit_log("B", status="FAIL")
        audit_log("C", status="OK")
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_no_secrets_in_log(self, audit_path):
        from wallet.utils.audit import audit_log
        audit_log("GET", status="OK", key_name="my-key", extra="")
        content = audit_path.read_text()
        # key_name is allowed, but no long secrets should appear
        assert "sk-" not in content  # API key prefix should never be logged

    @pytest.mark.skipif(os.name == "nt", reason="Unix chmod test")
    def test_file_permissions_600(self, audit_path):
        from wallet.utils.audit import audit_log
        audit_log("INIT", status="OK")
        mode = stat.S_IMODE(audit_path.stat().st_mode)
        assert mode == 0o600

    def test_concurrent_writes_no_corruption(self, audit_path):
        from wallet.utils.audit import audit_log
        errors = []

        def writer(i: int):
            try:
                audit_log(f"EVENT_{i}", status="OK", extra=f"thread={i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 100
        # Every line must be valid JSON
        for line in lines:
            json.loads(line)


class TestRead:
    def _write_events(self, audit_path, events):
        import getpass
        from datetime import datetime, timezone
        lines = []
        for ev in events:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": ev["event"],
                "status": ev.get("status", "OK"),
                "pid": 1234,
                "user": "testuser",
                "key_name": ev.get("key_name", ""),
                "extra": ev.get("extra", ""),
            }
            lines.append(json.dumps(record))
        audit_path.write_text("\n".join(lines) + "\n")

    def test_read_all(self, audit_path):
        from wallet.utils.audit import read_audit_log
        self._write_events(audit_path, [
            {"event": "INIT"}, {"event": "ADD"}, {"event": "GET"}
        ])
        events = read_audit_log()
        assert len(events) == 3

    def test_last_n(self, audit_path):
        from wallet.utils.audit import read_audit_log
        self._write_events(audit_path, [{"event": f"EV{i}"} for i in range(10)])
        events = read_audit_log(last_n=3)
        assert len(events) == 3
        assert events[-1]["event"] == "EV9"

    def test_event_filter(self, audit_path):
        from wallet.utils.audit import read_audit_log
        self._write_events(audit_path, [
            {"event": "GET", "status": "OK"},
            {"event": "UNLOCK", "status": "OK"},
            {"event": "GET", "status": "FAIL"},
        ])
        events = read_audit_log(event_filter="GET")
        assert len(events) == 2
        assert all(e["event"] == "GET" for e in events)

    def test_status_filter(self, audit_path):
        from wallet.utils.audit import read_audit_log
        self._write_events(audit_path, [
            {"event": "UNLOCK", "status": "OK"},
            {"event": "UNLOCK", "status": "FAIL"},
            {"event": "UNLOCK", "status": "FAIL"},
        ])
        events = read_audit_log(status_filter="FAIL")
        assert len(events) == 2

    def test_missing_log_returns_empty(self, tmp_path):
        from wallet.utils.audit import read_audit_log
        with patch("wallet.utils.audit._AUDIT_PATH", tmp_path / "nonexistent.log"):
            events = read_audit_log()
        assert events == []

    def test_corrupt_lines_skipped(self, audit_path):
        from wallet.utils.audit import read_audit_log
        audit_path.write_text(
            '{"event": "GOOD", "status": "OK", "ts": "x", "pid": 1, "user": "u", "key_name": "", "extra": ""}\n'
            'NOT JSON AT ALL\n'
            '{"event": "ALSO_GOOD", "status": "OK", "ts": "x", "pid": 1, "user": "u", "key_name": "", "extra": ""}\n'
        )
        events = read_audit_log()
        assert len(events) == 2
        assert events[0]["event"] == "GOOD"


class TestRotation:
    def test_rotation_triggered(self, audit_path, tmp_path):
        from wallet.utils.audit import MAX_LOG_SIZE_BYTES, audit_log
        # Pre-fill with data exceeding the limit
        big_content = ("x" * 1022 + "\n") * (MAX_LOG_SIZE_BYTES // 1023 + 1)
        audit_path.write_text(big_content)
        assert audit_path.stat().st_size >= MAX_LOG_SIZE_BYTES
        audit_log("ROTATE_TRIGGER", status="OK")
        # Original should now be small (new file)
        assert audit_path.stat().st_size < MAX_LOG_SIZE_BYTES
        # Rotated file should exist
        rotated = audit_path.with_suffix(".log.1")
        assert rotated.exists()
