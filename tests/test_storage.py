"""Tests for WalletStorage: read/write, backup, corruption detection."""

import secrets
import pytest
from pathlib import Path
from cryptography.exceptions import InvalidTag

from wallet.core.kdf import KDFParams, derive_key, hash_master_password
from wallet.core.storage import WalletStorage, WalletCorruptError
from wallet.models.wallet import WalletPayload


@pytest.fixture
def tmp_wallet(tmp_path):
    return WalletStorage(
        wallet_path=tmp_path / "wallet.enc",
        backup_dir=tmp_path / "backups",
    )


@pytest.fixture
def sample_payload():
    return WalletPayload(master_hash=hash_master_password("test")).to_dict()


class TestStorageReadWrite:
    def test_save_and_load_roundtrip(self, tmp_wallet, sample_payload):
        params = KDFParams.generate()
        key = derive_key("testpass", params)
        tmp_wallet.save(key, params, sample_payload)
        loaded = tmp_wallet.load(key)
        assert loaded["version"] == sample_payload["version"]

    def test_file_exists_after_save(self, tmp_wallet, sample_payload):
        params = KDFParams.generate()
        key = derive_key("testpass", params)
        tmp_wallet.save(key, params, sample_payload)
        assert tmp_wallet.exists()

    def test_wrong_key_raises_value_error(self, tmp_wallet, sample_payload):
        params = KDFParams.generate()
        key = derive_key("correct", params)
        wrong_key = secrets.token_bytes(32)
        tmp_wallet.save(key, params, sample_payload)
        with pytest.raises(ValueError, match="Authentication failed"):
            tmp_wallet.load(wrong_key)

    def test_corrupted_file_raises(self, tmp_wallet, sample_payload):
        params = KDFParams.generate()
        key = derive_key("testpass", params)
        tmp_wallet.save(key, params, sample_payload)
        # Corrupt the file
        data = tmp_wallet.wallet_path.read_bytes()
        tmp_wallet.wallet_path.write_bytes(data[:-10] + b"\x00" * 10)
        with pytest.raises(ValueError):
            tmp_wallet.load(key)

    def test_invalid_magic_raises(self, tmp_wallet):
        tmp_wallet.wallet_path.write_bytes(b"XXXX" + b"\x00" * 100)
        with pytest.raises(WalletCorruptError):
            tmp_wallet.read_kdf_params()

    def test_not_found_raises(self, tmp_wallet):
        with pytest.raises(FileNotFoundError):
            tmp_wallet.load(secrets.token_bytes(32))


class TestBackup:
    def test_backup_created_on_save(self, tmp_wallet, sample_payload):
        params = KDFParams.generate()
        key = derive_key("testpass", params)
        tmp_wallet.save(key, params, sample_payload)
        backups = list((tmp_wallet.backup_dir).glob("wallet_*.enc"))
        assert len(backups) == 1

    def test_multiple_backups_pruned(self, tmp_wallet, sample_payload):
        params = KDFParams.generate()
        key = derive_key("testpass", params)
        import time
        for _ in range(25):
            tmp_wallet.save(key, params, sample_payload)
            time.sleep(0.01)
        backups = list(tmp_wallet.backup_dir.glob("wallet_*.enc"))
        assert len(backups) <= 20
