"""
Tests for wallet/utils/vault_profiles.py (Wave 9).
"""

import json
from pathlib import Path

import pytest

from wallet.utils.vault_profiles import ProfileRegistry, _validate_name


@pytest.fixture()
def registry(tmp_path: Path) -> ProfileRegistry:
    reg_file = tmp_path / "profiles.json"
    return ProfileRegistry(registry_path=reg_file)


class TestValidateName:
    def test_valid_names(self):
        for name in ("work", "my-vault", "vault_2", "A1"):
            _validate_name(name)  # should not raise

    def test_invalid_empty(self):
        with pytest.raises(ValueError):
            _validate_name("")

    def test_invalid_spaces(self):
        with pytest.raises(ValueError):
            _validate_name("my vault")

    def test_invalid_too_long(self):
        with pytest.raises(ValueError):
            _validate_name("a" * 33)


class TestProfileRegistry:
    def test_empty_registry(self, registry: ProfileRegistry):
        assert registry.active == "default"
        assert registry.profiles == {}
        assert registry.list_all() == []

    def test_add_profile(self, registry: ProfileRegistry, tmp_path: Path):
        wallet_path = tmp_path / "work.enc"
        registry.add("work", wallet_path)
        assert "work" in registry.profiles

    def test_add_duplicate_raises(self, registry: ProfileRegistry, tmp_path: Path):
        registry.add("work", tmp_path / "work.enc")
        with pytest.raises(ValueError, match="already exists"):
            registry.add("work", tmp_path / "other.enc")

    def test_add_duplicate_overwrite(self, registry: ProfileRegistry, tmp_path: Path):
        registry.add("work", tmp_path / "work.enc")
        registry.add("work", tmp_path / "new.enc", overwrite=True)
        assert "new.enc" in registry.profiles["work"]

    def test_use_switches_active(self, registry: ProfileRegistry, tmp_path: Path):
        registry.add("work", tmp_path / "work.enc")
        registry.use("work")
        assert registry.active == "work"

    def test_use_unknown_raises(self, registry: ProfileRegistry):
        with pytest.raises(KeyError):
            registry.use("nonexistent")

    def test_remove_profile(self, registry: ProfileRegistry, tmp_path: Path):
        registry.add("work", tmp_path / "work.enc")
        registry.add("personal", tmp_path / "personal.enc")
        registry.use("work")
        registry.remove("personal")
        assert "personal" not in registry.profiles

    def test_remove_active_raises(self, registry: ProfileRegistry, tmp_path: Path):
        registry.add("work", tmp_path / "work.enc")
        registry.use("work")
        with pytest.raises(ValueError, match="active"):
            registry.remove("work")

    def test_list_all_sorted(self, registry: ProfileRegistry, tmp_path: Path):
        registry.add("zzz", tmp_path / "z.enc")
        registry.add("aaa", tmp_path / "a.enc")
        names = [p["name"] for p in registry.list_all()]
        assert names == ["aaa", "zzz"]

    def test_persists_to_disk(self, tmp_path: Path):
        reg_file = tmp_path / "profiles.json"
        r1 = ProfileRegistry(registry_path=reg_file)
        r1.add("work", tmp_path / "work.enc")

        r2 = ProfileRegistry(registry_path=reg_file)
        assert "work" in r2.profiles
