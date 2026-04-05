"""
crypto.py — AES-256-GCM encryption/decryption and HKDF subkey derivation.

Design decisions:
- AES-256-GCM is chosen over Fernet because it provides authenticated encryption
  with associated data (AEAD), explicit nonce control, and is a NIST standard.
  Fernet uses AES-128-CBC + HMAC which is older and less flexible.
- Each API key entry is encrypted with a unique subkey derived via HKDF from the
  master key and the entry's UUID — this is defense-in-depth (double encryption).
- Nonces are always generated with secrets.token_bytes(12) — never reused.
- SecureMemory context manager uses ctypes.memset to zero memory on exit,
  bypassing Python's GC which does not guarantee timely memory cleanup.
"""

import ctypes
import hashlib
import secrets
from contextlib import contextmanager
from typing import Generator

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NONCE_SIZE = 12   # bytes — GCM standard
KEY_SIZE = 32     # bytes — AES-256
TAG_SIZE = 16     # bytes — GCM authentication tag (implicit in AESGCM)


class SecureMemory:
    """
    Wraps a mutable bytearray and zeros it out when the context exits.
    Use for any in-memory sensitive data (derived keys, plaintext API keys).
    """

    def __init__(self, data: bytes | bytearray):
        self._buf = bytearray(data)

    def __enter__(self) -> bytearray:
        return self._buf

    def __exit__(self, *_) -> None:
        self._zero()

    def _zero(self) -> None:
        if self._buf:
            addr = ctypes.addressof(
                (ctypes.c_char * len(self._buf)).from_buffer(self._buf)
            )
            ctypes.memset(addr, 0, len(self._buf))
            self._buf[:] = bytearray(len(self._buf))  # Python-level overwrite too

    @property
    def value(self) -> bytes:
        return bytes(self._buf)


def encrypt_aes_gcm(
    key: bytes,
    plaintext: bytes,
    aad: bytes | None = None,
) -> tuple[bytes, bytes]:
    """
    Encrypt plaintext with AES-256-GCM.

    Args:
        key:       32-byte encryption key.
        plaintext: Raw bytes to encrypt.
        aad:       Optional Associated Authenticated Data (not encrypted, but authenticated).

    Returns:
        (nonce, ciphertext_with_tag) — both needed for decryption.
    """
    assert len(key) == KEY_SIZE, f"Key must be {KEY_SIZE} bytes"
    nonce = secrets.token_bytes(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def decrypt_aes_gcm(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    aad: bytes | None = None,
) -> bytes:
    """
    Decrypt AES-256-GCM ciphertext. Raises cryptography.exceptions.InvalidTag
    if the key is wrong, the nonce is wrong, or the ciphertext was tampered with.
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)


def derive_entry_subkey(master_key: bytes, entry_id: str) -> bytes:
    """
    Derive a per-entry subkey using HKDF-SHA256.

    Each API key entry is encrypted with its own unique subkey derived from:
    - master_key: the wallet's AES-256 key (from Argon2id)
    - entry_id:   the UUID of the entry (used as HKDF 'info')

    This means even if one entry's subkey is somehow compromised, other entries
    remain secure (defense-in-depth / key separation).
    """
    hkdf = HKDF(
        algorithm=SHA256(),
        length=KEY_SIZE,
        salt=None,
        info=f"api_key:{entry_id}".encode(),
    )
    return hkdf.derive(master_key)


def wallet_aad(wallet_path: str) -> bytes:
    """
    Compute Associated Authenticated Data from the wallet file path.

    Binding the AAD to the file path prevents an attacker from copying
    wallet.enc to a different location and decrypting it there (context binding).
    """
    return hashlib.sha256(wallet_path.encode()).digest()


def encrypt_entry_value(master_key: bytes, entry_id: str, api_key_value: str) -> tuple[bytes, bytes]:
    """Encrypt a single API key value using its unique per-entry subkey."""
    subkey = derive_entry_subkey(master_key, entry_id)
    with SecureMemory(subkey) as sk:
        return encrypt_aes_gcm(bytes(sk), api_key_value.encode())


def decrypt_entry_value(master_key: bytes, entry_id: str, nonce: bytes, ciphertext: bytes) -> str:
    """Decrypt a single API key value using its unique per-entry subkey."""
    subkey = derive_entry_subkey(master_key, entry_id)
    with SecureMemory(subkey) as sk:
        plaintext = decrypt_aes_gcm(bytes(sk), nonce, ciphertext)
    return plaintext.decode()
