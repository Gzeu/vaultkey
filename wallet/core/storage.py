"""
storage.py — Encrypted wallet binary I/O with atomic writes and auto-backup.

Binary format (wallet.enc):
  [4B]  magic:           b'VKEY'
  [2B]  version:         uint16 big-endian (current: 1)
  [4B]  kdf_params_len:  uint32 big-endian
  [NB]  kdf_params_json: Argon2id parameters + salt_hex
  [12B] nonce:           AES-GCM nonce
  [MB]  ciphertext:      AES-GCM encrypted+authenticated payload

Design decisions:
- Atomic writes: data is written to a temp file, then os.replace() renames it.
  This guarantees wallet.enc is never left in a partially-written state on crash.
- Backups: every save() rotates the previous wallet.enc to a timestamped backup.
  Backup pruning is configurable (default: keep last 20).
- chmod 600: wallet.enc and all backups are set to user-only read/write.
- AAD (Additional Authenticated Data): SHA-256 of the resolved wallet path is
  used as AAD in AES-GCM. Moving wallet.enc to another path makes it unreadable.
  This prevents relocation attacks.

FIX (Wave 6 / I4):
  _prune_old_backups() now logs each deleted backup at DEBUG level so operators
  can diagnose unexpected backup loss without silent deletes.
"""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from wallet.core.kdf import KDFParams, derive_key
from wallet.models.config import WalletConfig

log = logging.getLogger(__name__)

MAGIC = b"VKEY"
VERSION = 1
NONCE_SIZE = 12
_cfg = WalletConfig()


class WalletCorruptError(Exception):
    """Raised when wallet.enc cannot be parsed or has wrong magic/version."""


class WalletStorage:
    """Handles encrypted binary I/O for wallet.enc."""

    def __init__(self, wallet_path: Path, backup_dir: Path) -> None:
        self.wallet_path = wallet_path.resolve()
        self.backup_dir = backup_dir
        self._aad = hashlib.sha256(str(self.wallet_path).encode()).digest()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def exists(self) -> bool:
        return self.wallet_path.exists()

    def read_kdf_params(self) -> KDFParams:
        """Read and return the KDFParams from the wallet header (no decryption)."""
        raw = self._read_raw()
        _, params, _, _ = self._parse(raw)
        return params

    def load(self, key: bytes) -> dict[str, Any]:
        """Decrypt and return the wallet payload as a dict."""
        raw = self._read_raw()
        _, params, nonce, ciphertext = self._parse(raw)
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, self._aad)
        except Exception as exc:
            raise ValueError("Decryption failed — wrong key or corrupted file.") from exc
        return json.loads(plaintext.decode())

    def save(self, key: bytes, params: KDFParams, payload: dict[str, Any]) -> None:
        """Encrypt payload and atomically write to wallet.enc. Backs up previous."""
        import secrets
        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(key)
        plaintext = json.dumps(payload, ensure_ascii=False).encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext, self._aad)

        params_bytes = json.dumps(params.to_dict(), ensure_ascii=False).encode()
        version_bytes = VERSION.to_bytes(2, "big")
        params_len_bytes = len(params_bytes).to_bytes(4, "big")

        data = MAGIC + version_bytes + params_len_bytes + params_bytes + nonce + ciphertext

        self.wallet_path.parent.mkdir(parents=True, exist_ok=True)

        # Backup the previous file
        if self.wallet_path.exists():
            self._backup()

        # Atomic write
        fd, tmp_path_str = tempfile.mkstemp(
            dir=self.wallet_path.parent, prefix=".vkey_tmp_"
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            if os.name != "nt":
                os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self.wallet_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        if os.name != "nt":
            os.chmod(self.wallet_path, 0o600)

        self._prune_old_backups()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _read_raw(self) -> bytes:
        if not self.wallet_path.exists():
            raise WalletCorruptError(f"Wallet not found: {self.wallet_path}")
        return self.wallet_path.read_bytes()

    def _parse(self, raw: bytes) -> tuple[int, KDFParams, bytes, bytes]:
        """Parse the binary format and return (version, params, nonce, ciphertext)."""
        if len(raw) < 4 or raw[:4] != MAGIC:
            raise WalletCorruptError("Invalid magic bytes — not a VaultKey wallet.")
        offset = 4
        version = int.from_bytes(raw[offset:offset + 2], "big")
        offset += 2
        if version != VERSION:
            raise WalletCorruptError(f"Unsupported wallet version: {version}")
        params_len = int.from_bytes(raw[offset:offset + 4], "big")
        offset += 4
        params_bytes = raw[offset:offset + params_len]
        offset += params_len
        nonce = raw[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE
        ciphertext = raw[offset:]
        params = KDFParams.from_dict(json.loads(params_bytes.decode()))
        return version, params, nonce, ciphertext

    def _backup(self) -> None:
        """Copy wallet.enc to timestamped backup."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"wallet_{ts}.enc"
        import shutil
        shutil.copy2(self.wallet_path, dest)
        if os.name != "nt":
            os.chmod(dest, 0o600)
        log.debug("Backup created: %s", dest)

    def _prune_old_backups(self) -> None:
        """Remove oldest backups beyond MAX_BACKUPS limit.

        FIX (Wave 6 / I4): each deleted backup is now logged at DEBUG level.
        Previously silent deletes made it impossible to diagnose unexpected
        backup loss in production or on constrained storage devices.
        """
        max_backups: int = _cfg.max_backups
        backups = sorted(self.backup_dir.glob("wallet_*.enc"))
        to_delete = backups[: max(0, len(backups) - max_backups)]
        for path in to_delete:
            try:
                path.unlink()
                log.debug("Pruned old backup: %s", path.name)
            except OSError as exc:
                log.warning("Failed to prune backup %s: %s", path.name, exc)
