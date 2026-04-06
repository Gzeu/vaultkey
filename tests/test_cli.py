"""Integration tests for the Typer CLI using CliRunner."""

import json
import secrets
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wallet.ui.cli import app
from wallet.core.session import SessionManager
from wallet.core.kdf import KDFParams, derive_key, hash_master_password
from wallet.core.storage import WalletStorage
from wallet.models.wallet import WalletPayload

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_session():
    SessionManager._instance = None
    yield
    SessionManager._instance = None


@pytest.fixture
def initialized_wallet(tmp_path, monkeypatch):
    """Create an initialized wallet in a temp directory."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"], input="testpass123\ntestpass123\ny\n")
    assert result.exit_code == 0
    return tmp_path


class TestInitCommand:
    def test_init_creates_wallet(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"], input="mypassword\nmypassword\ny\n")
        assert result.exit_code == 0
        assert (tmp_path / "wallet.enc").exists()

    def test_init_password_mismatch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"], input="pass1\npass2\n")
        assert result.exit_code != 0
        assert "do not match" in result.output


class TestUnlockCommand:
    def test_unlock_success(self, initialized_wallet):
        result = runner.invoke(app, ["unlock"], input="testpass123\n")
        assert result.exit_code == 0
        assert "unlocked" in result.output.lower()

    def test_unlock_wrong_password(self, initialized_wallet):
        from unittest.mock import patch
        with patch("time.sleep"):
            result = runner.invoke(app, ["unlock"], input="wrongpass\n")
        assert result.exit_code != 0
        assert "Wrong" in result.output


class TestStatusCommand:
    def test_status_locked(self, initialized_wallet):
        result = runner.invoke(app, ["status"])
        assert "ocked" in result.output  # Locked or locked


class TestAddAndGet:
    def test_add_and_list(self, initialized_wallet):
        runner.invoke(app, ["unlock"], input="testpass123\n")
        result = runner.invoke(
            app,
            ["add", "--name", "Test OpenAI", "--service", "openai"],
            input="sk-test123456789abcdef\n"
        )
        assert result.exit_code == 0
        list_result = runner.invoke(app, ["list"])
        assert "Test OpenAI" in list_result.output
