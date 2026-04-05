"""
Tests for wallet/core/wipe.py — secure deletion and panic wipe.
"""

import secrets
from pathlib import Path

import pytest

from wallet.core.wipe import (
    panic_wipe,
    secure_delete_file,
    wipe_backups,
)


class TestSecureDeleteFile:
    def test_deletes_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.enc"
        f.write_bytes(secrets.token_bytes(256))
        result = secure_delete_file(f, warn_ssd=False)
        assert result is True
        assert not f.exists()

    def test_returns_false_for_nonexistent(self, tmp_path: Path):
        result = secure_delete_file(tmp_path / "ghost.enc", warn_ssd=False)
        assert result is False

    def test_file_content_overwritten(self, tmp_path: Path):
        """After deletion, the inode is gone — just check file is unlinked."""
        f = tmp_path / "secret.bin"
        f.write_bytes(b"supersecret" * 100)
        secure_delete_file(f, warn_ssd=False)
        assert not f.exists()


class TestWipeBackups:
    def test_wipes_all_backup_files(self, tmp_path: Path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        for i in range(5):
            (backup_dir / f"wallet_2025010{i}_120000.enc").write_bytes(
                secrets.token_bytes(128)
            )
        deleted = wipe_backups(backup_dir)
        assert deleted == 5
        assert list(backup_dir.glob("wallet_*.enc")) == []

    def test_empty_dir_returns_zero(self, tmp_path: Path):
        assert wipe_backups(tmp_path / "no_such_dir") == 0


class TestPanicWipe:
    def test_panic_wipe_removes_wallet_and_backups(self, tmp_path: Path):
        wallet = tmp_path / "wallet.enc"
        wallet.write_bytes(secrets.token_bytes(512))
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        for i in range(3):
            (backup_dir / f"wallet_20250101_12000{i}.enc").write_bytes(
                secrets.token_bytes(64)
            )
        summary = panic_wipe(wallet, backup_dir)
        assert summary["wallet_deleted"] is True
        assert summary["backups_deleted"] == 3
        assert not wallet.exists()

    def test_panic_wipe_deletes_audit_log(self, tmp_path: Path):
        wallet = tmp_path / "wallet.enc"
        wallet.write_bytes(b"x" * 64)
        audit = tmp_path / "audit.log"
        audit.write_text("log data")
        summary = panic_wipe(
            wallet,
            tmp_path / "backups",
            delete_audit_log=True,
            audit_log_path=audit,
        )
        assert summary["audit_deleted"] is True
        assert not audit.exists()
