"""
storage.py — Binary wallet file I/O, backup management, and atomic writes.

Binary format of wallet.enc:
  [4 bytes]  magic: b'VKEY'
  [2 bytes]  version: uint16 big-endian (current: 1)
  [4 bytes]  kdf_params_len: uint32 big-endian (length of JSON blob)
  [N bytes]  kdf_params_json: UTF-8 JSON with Argon2id params + salt_hex
  [12 bytes] nonce: AES-GCM nonce
  [M bytes]  ciphertext: AES-GCM encrypted+authenticated payload (JSON wallet data)

Design decisions:
- Atomic writes via temp file + os.replace() prevent partial writes from
  corrupting the wallet even on power loss.
- chmod 600 is enforced on every write (Unix).
- Timestamped backups are created in backups/ on every write.
- AAD (Associated Authenticated Data) = SHA-256(wallet_path) binds the
  ciphertext to its intended location, preventing file relocation attacks.
"""

import json
import os
import shutil
import stat
import struct
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag

from wallet.core.crypto import decrypt_aes_gcm, encrypt_aes_gcm, wallet_aad
from wallet.core.kdf import KDFParams

MAGIC = b"VKEY"
VERSION = 1
NONCE_SIZE = 12


class WalletCorruptError(Exception):
    """Raised when wallet.enc has an invalid magic, version, or AES-GCM tag."""


class WalletStorage:
    """Handles all disk I/O for the encrypted wallet file."""

    def __init__(self, wallet_path: Path, backup_dir: Path | None = None):
        self.wallet_path = wallet_path.resolve()
        self.backup_dir = backup_dir or (wallet_path.parent / "backups")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def exists(self) -> bool:
        return self.wallet_path.exists()

    def read_kdf_params(self) -> KDFParams:
        """Read only the KDF params header without decrypting the payload."""
        with open(self.wallet_path, "rb") as f:
            self._read_magic_version(f)
            return self._read_kdf_params(f)

    def load(self, derived_key: bytes) -> dict:
        """Read and decrypt the full wallet payload."""
        self._check_permissions()
        try:
            with open(self.wallet_path, "rb") as f:
                self._read_magic_version(f)
                _params = self._read_kdf_params(f)
                nonce = f.read(NONCE_SIZE)
                ciphertext = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Wallet not found at {self.wallet_path}.\nRun: wallet init"
            )

        aad = wallet_aad(str(self.wallet_path))
        try:
            plaintext = decrypt_aes_gcm(derived_key, nonce, ciphertext, aad)
        except InvalidTag:
            raise ValueError(
                "Authentication failed. Wrong password or wallet file is corrupted."
            )

        return json.loads(plaintext.decode())

    def save(self, derived_key: bytes, kdf_params: KDFParams, payload: dict) -> None:
        """Encrypt and write the wallet payload atomically."""
        aad = wallet_aad(str(self.wallet_path))
        plaintext = json.dumps(payload, ensure_ascii=False).encode()
        nonce, ciphertext = encrypt_aes_gcm(derived_key, plaintext, aad)

        raw = self._pack(kdf_params, nonce, ciphertext)

        tmp_path = self.wallet_path.with_suffix(".enc.tmp")
        try:
            tmp_path.write_bytes(raw)
            self._set_secure_permissions(tmp_path)
            os.replace(tmp_path, self.wallet_path)   # atomic on POSIX
            self._set_secure_permissions(self.wallet_path)
        except OSError as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if "No space left" in str(exc):
                raise OSError(
                    "Disk full. Wallet NOT saved. Free space and retry. Previous version intact."
                ) from exc
            raise

        self._create_backup(raw)

    # ------------------------------------------------------------------ #
    # Binary packing/unpacking
    # ------------------------------------------------------------------ #

    def _pack(self, kdf_params: KDFParams, nonce: bytes, ciphertext: bytes) -> bytes:
        kdf_json = json.dumps(kdf_params.to_dict()).encode()
        header = (
            MAGIC
            + struct.pack(">H", VERSION)
            + struct.pack(">I", len(kdf_json))
            + kdf_json
        )
        return header + nonce + ciphertext

    def _read_magic_version(self, f) -> None:
        magic = f.read(4)
        if magic != MAGIC:
            raise WalletCorruptError(f"Invalid wallet magic: {magic!r}")
        (version,) = struct.unpack(">H", f.read(2))
        if version != VERSION:
            raise WalletCorruptError(f"Unsupported wallet version: {version}")

    def _read_kdf_params(self, f) -> KDFParams:
        (kdf_len,) = struct.unpack(">I", f.read(4))
        kdf_json = f.read(kdf_len)
        return KDFParams.from_dict(json.loads(kdf_json.decode()))

    # ------------------------------------------------------------------ #
    # Backup
    # ------------------------------------------------------------------ #

    def _create_backup(self, raw: bytes) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"wallet_{ts}.enc"
        backup_path.write_bytes(raw)
        self._set_secure_permissions(backup_path)
        self._prune_old_backups(keep=20)

    def _prune_old_backups(self, keep: int = 20) -> None:
        backups = sorted(self.backup_dir.glob("wallet_*.enc"))
        for old in backups[:-keep]:
            old.unlink(missing_ok=True)

    # ------------------------------------------------------------------ #
    # Permission helpers
    # ------------------------------------------------------------------ #

    def _check_permissions(self) -> None:
        if os.name == "nt" or not self.wallet_path.exists():
            return
        mode = stat.S_IMODE(self.wallet_path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"Wallet file has unsafe permissions ({oct(mode)}).\n"
                f"Fix with: chmod 600 {self.wallet_path}"
            )

    @staticmethod
    def _set_secure_permissions(path: Path) -> None:
        if os.name != "nt":
            os.chmod(path, 0o600)
