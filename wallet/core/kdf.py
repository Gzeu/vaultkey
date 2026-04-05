"""
kdf.py — Argon2id key derivation and master password hashing.

Design decisions:
- Argon2id is chosen over PBKDF2 because it is memory-hard (resists GPU/ASIC
  brute-force attacks) and is the OWASP-recommended password hashing algorithm.
  PBKDF2 is only CPU-hard, making it ~100x cheaper to attack on modern hardware.
- Parameters follow OWASP 2024 recommendations:
    time_cost=3 (iterations), memory_cost=65536 (64MB), parallelism=4
- Two separate salts are used:
    1. kdf_salt: for key derivation (deterministic — stored in wallet.enc header)
    2. hash_salt: embedded in the Argon2id hash string (for password verification)
- The master password hash is stored in the encrypted payload for unlock verification.
"""

import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.low_level import Type, hash_secret_raw
from argon2.exceptions import VerifyMismatchError, VerificationError

SALT_SIZE = 32        # bytes
KEY_SIZE = 32         # bytes — AES-256

ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536   # 64 MB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32

# Shared PasswordHasher instance for password verification
_ph = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    type=Type.ID,
)


@dataclass(frozen=True)
class KDFParams:
    """Serializable Argon2id parameters stored in wallet.enc header."""
    salt_hex: str
    time_cost: int = ARGON2_TIME_COST
    memory_cost: int = ARGON2_MEMORY_COST
    parallelism: int = ARGON2_PARALLELISM
    hash_len: int = ARGON2_HASH_LEN

    def to_dict(self) -> dict:
        return {
            "salt_hex": self.salt_hex,
            "time_cost": self.time_cost,
            "memory_cost": self.memory_cost,
            "parallelism": self.parallelism,
            "hash_len": self.hash_len,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KDFParams":
        return cls(**d)

    @classmethod
    def generate(cls) -> "KDFParams":
        """Generate new KDFParams with a fresh random salt."""
        salt = secrets.token_bytes(SALT_SIZE)
        return cls(salt_hex=salt.hex())

    @property
    def salt(self) -> bytes:
        return bytes.fromhex(self.salt_hex)


def derive_key(password: str, params: KDFParams) -> bytes:
    """
    Derive a 32-byte AES key from a master password using Argon2id.

    This function is deterministic — same password + same params.salt = same key.
    The salt must be stored persistently (in wallet.enc header) so the key
    can be re-derived on subsequent unlocks.
    """
    raw_key = hash_secret_raw(
        secret=password.encode(),
        salt=params.salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=params.hash_len,
        type=Type.ID,
    )
    return raw_key


def hash_master_password(password: str) -> str:
    """
    Hash the master password for storage and verification.
    Returns an Argon2id hash string (includes salt, params, hash — self-contained).
    This hash is stored in the encrypted wallet payload.
    """
    return _ph.hash(password)


def verify_master_password(password: str, stored_hash: str) -> bool:
    """
    Verify a password against the stored Argon2id hash.
    Returns False on mismatch rather than raising — callers handle retry logic.
    """
    try:
        return _ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False
