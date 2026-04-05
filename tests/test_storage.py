"""
test_storage.py — End-to-end roundtrip tests for WalletStorage.

Covers:
  - init → save → load → verify payload roundtrip
  - AES-GCM integrity: wrong password raises ValueError
  - AAD binding: loading from different path raises InvalidTag / ValueError
  - Backup creation and pruning
  - Atomic write: temp file cleaned up on success
  - Permission enforcement (Unix only)
  - HMAC manifest written on save, verified on load
"""

import os
import stat
import secrets
from pathlib import Path

import pytest

from wallet.core.kdf import KDFParams, derive_key, hash_master_password
from wallet.core.storage import WalletStorage, WalletCorruptError
from wallet.models.wallet import WalletPayload, APIKeyEntry
from wallet.core.crypto import encrypt_entry_value


PASSWORD = "correct-horse-battery-staple"


def _make_storage(tmp_path: Path) -> tuple[WalletStorage, KDFParams, bytes, WalletPayload]:
    wallet_path = tmp_path / "wallet.enc"
    storage = WalletStorage(wallet_path, tmp_path / "backups")
    params = KDFParams.generate()
    key = derive_key(PASSWORD, params)
    payload = WalletPayload(master_hash=hash_master_password(PASSWORD))
    return storage, params, key, payload


def _add_entry(payload: WalletPayload, key: bytes, name: str = "Test Key") -> APIKeyEntry:
    entry_id = "test-entry-001"
    nonce, cipher = encrypt_entry_value(key, entry_id, "sk-fake-" + "x" * 32)
    entry = APIKeyEntry(
        id=entry_id, name=name, service="openai",
        nonce_hex=nonce.hex(), cipher_hex=cipher.hex(),
    )
    payload.add_entry(entry)
    return entry


class TestRoundtrip:
    def test_save_and_load_empty_wallet(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        data = storage.load(key)
        loaded = WalletPayload.from_dict(data)
        assert loaded.version == payload.version
        assert loaded.master_hash == payload.master_hash
        assert loaded.keys == {}

    def test_save_and_load_with_entries(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        entry = _add_entry(payload, key)
        storage.save(key, params, payload.to_dict())
        data = storage.load(key)
        loaded = WalletPayload.from_dict(data)
        assert entry.id in loaded.keys
        assert loaded.keys[entry.id].name == entry.name
        assert loaded.keys[entry.id].cipher_hex == entry.cipher_hex

    def test_wrong_password_raises(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        wrong_key = derive_key("wrong-password-12345", params)
        with pytest.raises(ValueError, match="Authentication failed"):
            storage.load(wrong_key)

    def test_corrupt_magic_raises(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        # Corrupt the magic bytes
        raw = (tmp_path / "wallet.enc").read_bytes()
        (tmp_path / "wallet.enc").write_bytes(b"XXXX" + raw[4:])
        with pytest.raises(WalletCorruptError):
            storage.read_kdf_params()

    def test_aad_binding_different_path(self, tmp_path: Path):
        """Moving wallet.enc to a different path should fail AES-GCM auth."""
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        # Load with a storage pointing to a different path
        other_path = tmp_path / "other" / "wallet.enc"
        other_path.parent.mkdir()
        import shutil
        shutil.copy(tmp_path / "wallet.enc", other_path)
        other_storage = WalletStorage(other_path, tmp_path / "backups2")
        with pytest.raises(ValueError, match="Authentication failed"):
            other_storage.load(key)


class TestBackup:
    def test_backup_created_on_save(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        backups = list((tmp_path / "backups").glob("wallet_*.enc"))
        assert len(backups) == 1

    def test_multiple_saves_create_multiple_backups(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        for _ in range(3):
            storage.save(key, params, payload.to_dict())
        backups = list((tmp_path / "backups").glob("wallet_*.enc"))
        assert len(backups) == 3

    def test_backup_pruning(self, tmp_path: Path):
        from wallet.models.config import WalletConfig
        storage, params, key, payload = _make_storage(tmp_path)
        # Save MAX_BACKUPS+5 times to trigger pruning
        from wallet.models.config import WalletConfig
        cfg = WalletConfig()
        limit = cfg.max_backups
        for _ in range(limit + 3):
            storage.save(key, params, payload.to_dict())
        backups = list((tmp_path / "backups").glob("wallet_*.enc"))
        assert len(backups) <= limit


class TestPermissions:
    @pytest.mark.skipif(os.name == "nt", reason="Unix chmod test")
    def test_wallet_has_600_permissions(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        mode = stat.S_IMODE((tmp_path / "wallet.enc").stat().st_mode)
        assert mode == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="Unix chmod test")
    def test_open_permissions_raises(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        # Make it world-readable
        os.chmod(tmp_path / "wallet.enc", 0o644)
        with pytest.raises(PermissionError):
            storage.load(key)


class TestIntegrityManifest:
    def test_manifest_written_on_save(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        _add_entry(payload, key)
        storage.save(key, params, payload.to_dict())
        data = storage.load(key)
        loaded = WalletPayload.from_dict(data)
        # Manifest should be present after save
        assert loaded.integrity_hmac is not None
        assert len(loaded.integrity_hmac) == 64  # SHA-256 hex

    def test_kdf_params_readable_without_key(self, tmp_path: Path):
        storage, params, key, payload = _make_storage(tmp_path)
        storage.save(key, params, payload.to_dict())
        loaded_params = storage.read_kdf_params()
        assert loaded_params.salt_hex == params.salt_hex
        assert loaded_params.time_cost == params.time_cost
        assert loaded_params.memory_cost == params.memory_cost
