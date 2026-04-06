"""
Tests for wallet/utils/share_token.py (Wave 9).
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from wallet.utils.share_token import (
    export_share_token,
    import_share_token,
    read_token_file,
    write_token_file,
)


_PASSPHRASE = "test-passphrase-123"


@pytest.fixture()
def sample_token() -> str:
    return export_share_token(
        entry_name="TestKey",
        entry_service="openai",
        entry_tags=["ai", "prod"],
        entry_description="A test key",
        entry_expires_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
        raw_value="sk-test-value-1234",
        passphrase=_PASSPHRASE,
    )


class TestExportImport:
    def test_roundtrip(self, sample_token: str):
        data = import_share_token(sample_token, _PASSPHRASE)
        assert data["name"] == "TestKey"
        assert data["value"] == "sk-test-value-1234"
        assert data["service"] == "openai"
        assert "ai" in data["tags"]

    def test_wrong_passphrase_raises(self, sample_token: str):
        with pytest.raises(ValueError, match="Decryption failed"):
            import_share_token(sample_token, "wrong-passphrase")

    def test_corrupted_token_raises(self):
        with pytest.raises(ValueError):
            import_share_token("notvalidbase64!!!", _PASSPHRASE)

    def test_version_mismatch_raises(self):
        import base64, json
        bad = base64.b64encode(json.dumps({"version": "vk-share-v0"}).encode()).decode()
        with pytest.raises(ValueError, match="Unsupported token version"):
            import_share_token(bad, _PASSPHRASE)

    def test_no_expiry(self):
        token = export_share_token(
            entry_name="NoExpiry",
            entry_service="github",
            entry_tags=[],
            entry_description=None,
            entry_expires_at=None,
            raw_value="ghp_noexpiry",
            passphrase=_PASSPHRASE,
        )
        data = import_share_token(token, _PASSPHRASE)
        assert data["expires_at"] is None
        assert data["value"] == "ghp_noexpiry"


class TestFileIO:
    def test_write_and_read(self, tmp_path: Path, sample_token: str):
        p = tmp_path / "mykey.vkshare"
        write_token_file(sample_token, p)
        assert p.exists()
        loaded = read_token_file(p)
        assert loaded == sample_token

    def test_read_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_token_file(tmp_path / "ghost.vkshare")
