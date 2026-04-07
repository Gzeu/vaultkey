"""
totp.py — TOTP / 2FA engine for VaultKey.

Provides:
- TOTPEngine: generate codes, verify codes, produce QR URIs, manage scratch codes.
- ScratchCodeManager: one-time emergency backup codes (hashed, never stored plain).

Security design:
- TOTP secrets are stored encrypted via the standard wallet crypto layer
  (AES-256-GCM + HKDF) — TOTPEngine never touches raw storage.
- Scratch codes are SHA-256 hashed before storage (analogous to password hashing
  for low-entropy codes; full Argon2id would be overkill for 8-char codes).
- Time window allows +/-1 step (30s tolerance) to handle clock skew.
- All secrets are validated as proper base32 before acceptance.

Requires: pyotp>=2.9

Usage:
    from wallet.core.totp import TOTPEngine

    engine = TOTPEngine(secret="BASE32SECRET")
    code = engine.now()                    # current 6-digit code
    ok = engine.verify("123456")           # True/False (+/-1 window)
    uri = engine.provisioning_uri("alice@example.com", issuer="VaultKey")
    qr_text = engine.qr_uri("alice@example.com")  # for terminal QR display
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import pyotp
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pyotp is required for TOTP support. "
        "Install with: pip install pyotp"
    ) from exc

log = logging.getLogger(__name__)

# TOTP configuration constants
_TOTP_DIGITS: int = 6
_TOTP_INTERVAL: int = 30     # seconds per step
_TOTP_ALGORITHM: str = "SHA1"  # RFC 6238 default; most authenticator apps require SHA1
_TOTP_VALID_WINDOW: int = 1   # allow +/- 1 time step (30s tolerance)
_SCRATCH_CODE_LENGTH: int = 8  # characters per scratch code
_SCRATCH_CODE_COUNT: int = 8   # codes generated per set
_SCRATCH_CODE_CHARSET: str = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32


class TOTPError(Exception):
    """Raised for TOTP configuration or verification errors."""


class TOTPEngine:
    """
    Wraps pyotp.TOTP with VaultKey-specific validation and helpers.

    Args:
        secret: Base32-encoded TOTP secret (case-insensitive, spaces allowed).
        digits: Code length (default 6; most apps use 6).
        interval: Time step in seconds (default 30).
        issuer: Optional issuer name for provisioning URIs.
    """

    def __init__(
        self,
        secret: str,
        digits: int = _TOTP_DIGITS,
        interval: int = _TOTP_INTERVAL,
        issuer: str = "VaultKey",
    ) -> None:
        self._secret = self._validate_secret(secret)
        self._digits = digits
        self._interval = interval
        self._issuer = issuer
        self._totp = pyotp.TOTP(
            self._secret,
            digits=digits,
            interval=interval,
            digest=hashlib.sha1,  # noqa: S324 — required by RFC 6238 / authenticator apps
        )

    # ────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────

    def now(self) -> str:
        """Return the current TOTP code as zero-padded string."""
        return self._totp.now()

    def at(self, timestamp: float) -> str:
        """Return the TOTP code for a specific Unix timestamp."""
        return self._totp.at(int(timestamp))

    def verify(
        self,
        code: str,
        for_time: Optional[float] = None,
        valid_window: int = _TOTP_VALID_WINDOW,
    ) -> bool:
        """
        Verify a TOTP code with timing window.

        Args:
            code:         The user-supplied code (spaces stripped automatically).
            for_time:     Unix timestamp to verify against (default: now).
            valid_window: Steps to accept either side of current step.

        Returns:
            True if valid, False otherwise.
        """
        code = re.sub(r"\s", "", code)
        if not code.isdigit() or len(code) != self._digits:
            return False
        t = for_time if for_time is not None else time.time()
        return self._totp.verify(code, for_time=t, valid_window=valid_window)

    def seconds_remaining(self) -> int:
        """Seconds until the current code expires."""
        return self._interval - (int(time.time()) % self._interval)

    def provisioning_uri(self, account_name: str, issuer: Optional[str] = None) -> str:
        """
        Generate an otpauth:// URI for QR code scanning.

        Args:
            account_name: User identifier (e.g., email or username).
            issuer:       Override the default issuer name.

        Returns:
            Full otpauth URI compatible with all TOTP apps.
        """
        return self._totp.provisioning_uri(
            name=account_name,
            issuer_name=issuer or self._issuer,
        )

    def qr_uri(self, account_name: str, issuer: Optional[str] = None) -> str:
        """Alias for provisioning_uri (kept for backward compat)."""
        return self.provisioning_uri(account_name, issuer)

    @property
    def secret(self) -> str:
        """The normalized base32 secret (uppercase, no spaces)."""
        return self._secret

    # ────────────────────────────────────────────
    # Class methods
    # ────────────────────────────────────────────

    @classmethod
    def generate_secret(cls, length: int = 32) -> str:
        """
        Generate a cryptographically secure base32 TOTP secret.

        Args:
            length: Output length in base32 chars (default 32 = 160 bits).

        Returns:
            Uppercase base32 string suitable for pyotp.
        """
        import base64
        raw = secrets.token_bytes((length * 5 + 7) // 8)
        return base64.b32encode(raw).decode().upper()[:length]

    @classmethod
    def from_uri(cls, otpauth_uri: str, issuer: str = "VaultKey") -> "TOTPEngine":
        """
        Construct a TOTPEngine from an otpauth:// URI.

        Supports URIs exported by Google Authenticator, Authy, etc.

        Args:
            otpauth_uri: Full otpauth:// URI.
            issuer:      Fallback issuer if not in URI.

        Returns:
            Configured TOTPEngine instance.

        Raises:
            TOTPError: If URI is malformed or secret is missing.
        """
        try:
            parsed = pyotp.parse_uri(otpauth_uri)
        except Exception as exc:
            raise TOTPError(f"Invalid otpauth URI: {exc}") from exc
        if not isinstance(parsed, pyotp.TOTP):
            raise TOTPError("URI is not a TOTP URI (HOTP not supported).")
        return cls(
            secret=parsed.secret,
            digits=parsed.digits,
            interval=parsed.interval,
            issuer=issuer,
        )

    # ────────────────────────────────────────────
    # Private helpers
    # ────────────────────────────────────────────

    @staticmethod
    def _validate_secret(secret: str) -> str:
        """
        Normalize and validate a base32 TOTP secret.

        Strips whitespace, uppercases, and pads to a multiple of 8
        (required by the base32 codec).

        Raises:
            TOTPError: If the secret contains invalid base32 characters.
        """
        import base64
        normalized = re.sub(r"[\s-]", "", secret).upper()
        # Pad to multiple of 8
        padding = (8 - len(normalized) % 8) % 8
        padded = normalized + "=" * padding
        try:
            base64.b32decode(padded)
        except Exception as exc:
            raise TOTPError(
                f"Invalid base32 TOTP secret: {exc}. "
                "Secrets must contain only A-Z and 2-7 characters."
            ) from exc
        return normalized


@dataclass
class ScratchCode:
    """A single one-time backup code (stored as SHA-256 hash)."""
    code_hash: str   # SHA-256 hex digest of the plain code
    used: bool = False


@dataclass
class ScratchCodeManager:
    """
    Manages one-time emergency backup codes for TOTP recovery.

    Codes are stored as SHA-256 hashes — the plaintext is shown once
    at generation time and never stored.

    Security note:
    Backup codes have low entropy (8 alphanumeric chars = ~40 bits).
    SHA-256 is sufficient here because:
    - Codes are long enough to resist brute-force in this context
    - They are one-time use (used codes are permanently invalidated)
    - Access to the hash list already requires vault unlock (Argon2id)
    For higher-entropy scenarios, replace with Argon2id.
    """

    codes: list[ScratchCode] = field(default_factory=list)

    @classmethod
    def generate(cls, count: int = _SCRATCH_CODE_COUNT) -> tuple["ScratchCodeManager", list[str]]:
        """
        Generate a fresh set of scratch codes.

        Returns:
            Tuple of (ScratchCodeManager, list_of_plaintext_codes).
            The plaintext list must be shown to the user ONCE and discarded.
        """
        manager = cls()
        plaintext_codes: list[str] = []

        for _ in range(count):
            plain = cls._generate_code()
            code_hash = hashlib.sha256(plain.encode()).hexdigest()
            manager.codes.append(ScratchCode(code_hash=code_hash, used=False))
            plaintext_codes.append(plain)

        log.info("Generated %d TOTP scratch codes.", count)
        return manager, plaintext_codes

    def verify_and_consume(self, plain_code: str) -> bool:
        """
        Verify a scratch code and mark it used if valid.

        This is a constant-time comparison to prevent timing attacks.

        Args:
            plain_code: The code entered by the user (case-insensitive).

        Returns:
            True if a valid, unused code was found and consumed.
        """
        code_hash = hashlib.sha256(plain_code.upper().strip().encode()).hexdigest()
        for sc in self.codes:
            if not sc.used and _hmac.compare_digest(sc.code_hash, code_hash):
                sc.used = True
                log.warning(
                    "TOTP scratch code consumed. Remaining: %d",
                    self.remaining_count,
                )
                return True
        return False

    @property
    def remaining_count(self) -> int:
        """Number of unused scratch codes remaining."""
        return sum(1 for sc in self.codes if not sc.used)

    @property
    def is_exhausted(self) -> bool:
        """True if all scratch codes have been used."""
        return self.remaining_count == 0

    def to_dict(self) -> list[dict]:
        """Serialize for storage in wallet payload."""
        return [{"code_hash": sc.code_hash, "used": sc.used} for sc in self.codes]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "ScratchCodeManager":
        """Deserialize from wallet payload."""
        manager = cls()
        manager.codes = [
            ScratchCode(code_hash=d["code_hash"], used=d.get("used", False))
            for d in data
        ]
        return manager

    @staticmethod
    def _generate_code() -> str:
        return "".join(
            secrets.choice(_SCRATCH_CODE_CHARSET)
            for _ in range(_SCRATCH_CODE_LENGTH)
        )
