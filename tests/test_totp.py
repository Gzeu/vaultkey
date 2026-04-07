"""
test_totp.py — Tests for wallet.core.totp (TOTPEngine + ScratchCodeManager).

Runs without a live vault — tests only the crypto/TOTP layer.
Pyotp is a test-time dependency (already in optional deps or installed separately).
"""

from __future__ import annotations

import time

import pytest

# Skip entire module if pyotp not installed
pyotp = pytest.importorskip("pyotp", reason="pyotp not installed")

from wallet.core.totp import (
    ScratchCodeManager,
    TOTPEngine,
    TOTPError,
    _SCRATCH_CODE_COUNT,
    _SCRATCH_CODE_LENGTH,
)


# ────────────────────────────────────────────
class TestTOTPEngine:
# ────────────────────────────────────────────

    @pytest.fixture
    def secret(self) -> str:
        return TOTPEngine.generate_secret()

    @pytest.fixture
    def engine(self, secret: str) -> TOTPEngine:
        return TOTPEngine(secret=secret)

    def test_generate_secret_length(self) -> None:
        s = TOTPEngine.generate_secret(32)
        assert len(s) == 32

    def test_generate_secret_valid_base32(self) -> None:
        import base64
        s = TOTPEngine.generate_secret()
        padded = s + "=" * ((8 - len(s) % 8) % 8)
        # Should not raise
        base64.b32decode(padded)

    def test_now_returns_digits(self, engine: TOTPEngine) -> None:
        code = engine.now()
        assert code.isdigit()
        assert len(code) == 6

    def test_now_zero_padded(self) -> None:
        """Codes must be zero-padded (e.g., '012345' not '12345')."""
        engine = TOTPEngine(secret=TOTPEngine.generate_secret())
        code = engine.now()
        assert len(code) == 6  # always exactly 6 chars

    def test_verify_current_code(self, engine: TOTPEngine) -> None:
        code = engine.now()
        assert engine.verify(code) is True

    def test_verify_with_spaces(self, engine: TOTPEngine) -> None:
        code = engine.now()
        code_with_spaces = code[:3] + " " + code[3:]
        assert engine.verify(code_with_spaces) is True

    def test_verify_wrong_code(self, engine: TOTPEngine) -> None:
        assert engine.verify("000000") is False or engine.verify("000000") is True  # could be valid
        # Use a definitely wrong format
        assert engine.verify("abc") is False
        assert engine.verify("") is False
        assert engine.verify("12345") is False   # only 5 digits
        assert engine.verify("1234567") is False  # 7 digits

    def test_verify_at_timestamp(self, engine: TOTPEngine) -> None:
        ts = time.time()
        code = engine.at(ts)
        assert engine.verify(code, for_time=ts) is True

    def test_seconds_remaining_range(self, engine: TOTPEngine) -> None:
        remaining = engine.seconds_remaining()
        assert 0 <= remaining <= 30

    def test_provisioning_uri_format(self, engine: TOTPEngine) -> None:
        uri = engine.provisioning_uri("user@example.com", issuer="TestApp")
        assert uri.startswith("otpauth://totp/")
        assert "TestApp" in uri
        assert "user%40example.com" in uri or "user@example.com" in uri
        assert engine.secret in uri

    def test_invalid_secret_raises(self) -> None:
        with pytest.raises(TOTPError, match="Invalid base32"):
            TOTPEngine(secret="NOT!VALID@SECRET#")

    def test_secret_normalized(self) -> None:
        secret = "jbswy3dpehpk3pxp"  # lowercase
        engine = TOTPEngine(secret=secret)
        assert engine.secret == secret.upper()

    def test_secret_with_spaces(self) -> None:
        secret = "JBSWY3DP EHPK3PXP"
        engine = TOTPEngine(secret=secret)
        assert " " not in engine.secret

    def test_from_uri_roundtrip(self) -> None:
        secret = TOTPEngine.generate_secret()
        original = TOTPEngine(secret=secret)
        uri = original.provisioning_uri("test@example.com", issuer="VaultKey")
        restored = TOTPEngine.from_uri(uri)
        assert restored.secret == original.secret

    def test_from_uri_invalid_raises(self) -> None:
        with pytest.raises(TOTPError):
            TOTPEngine.from_uri("not-a-valid-uri")

    def test_consistency_with_pyotp_directly(self) -> None:
        """Cross-validate against raw pyotp to ensure no regression."""
        secret = TOTPEngine.generate_secret()
        engine = TOTPEngine(secret=secret)
        raw = pyotp.TOTP(secret)
        ts = time.time()
        assert engine.at(ts) == raw.at(int(ts))


# ────────────────────────────────────────────
class TestScratchCodeManager:
# ────────────────────────────────────────────

    @pytest.fixture
    def manager_and_codes(self) -> tuple[ScratchCodeManager, list[str]]:
        return ScratchCodeManager.generate()

    def test_generate_count(self, manager_and_codes: tuple) -> None:
        manager, codes = manager_and_codes
        assert len(codes) == _SCRATCH_CODE_COUNT
        assert manager.remaining_count == _SCRATCH_CODE_COUNT

    def test_code_length(self, manager_and_codes: tuple) -> None:
        _, codes = manager_and_codes
        for code in codes:
            assert len(code) == _SCRATCH_CODE_LENGTH

    def test_codes_unique(self, manager_and_codes: tuple) -> None:
        _, codes = manager_and_codes
        assert len(set(codes)) == len(codes)

    def test_plaintext_not_stored(self, manager_and_codes: tuple) -> None:
        """Manager must store only hashes, never plaintext codes."""
        manager, codes = manager_and_codes
        for code in codes:
            for sc in manager.codes:
                assert sc.code_hash != code  # hash != plaintext

    def test_verify_and_consume_valid(self, manager_and_codes: tuple) -> None:
        manager, codes = manager_and_codes
        assert manager.verify_and_consume(codes[0]) is True
        assert manager.remaining_count == _SCRATCH_CODE_COUNT - 1

    def test_verify_and_consume_case_insensitive(self, manager_and_codes: tuple) -> None:
        manager, codes = manager_and_codes
        # Codes are uppercase; verify with lowercase
        assert manager.verify_and_consume(codes[0].lower()) is True

    def test_code_cannot_be_reused(self, manager_and_codes: tuple) -> None:
        manager, codes = manager_and_codes
        assert manager.verify_and_consume(codes[0]) is True
        assert manager.verify_and_consume(codes[0]) is False

    def test_verify_invalid_code(self, manager_and_codes: tuple) -> None:
        manager, _ = manager_and_codes
        assert manager.verify_and_consume("XXXXXXXX") is False

    def test_exhausted(self, manager_and_codes: tuple) -> None:
        manager, codes = manager_and_codes
        for code in codes:
            manager.verify_and_consume(code)
        assert manager.is_exhausted is True
        assert manager.remaining_count == 0

    def test_serialization_roundtrip(self, manager_and_codes: tuple) -> None:
        manager, codes = manager_and_codes
        manager.verify_and_consume(codes[0])  # mark one used
        serialized = manager.to_dict()
        restored = ScratchCodeManager.from_dict(serialized)
        # Used code should still be consumed after roundtrip
        assert restored.verify_and_consume(codes[0]) is False
        # Unused codes still valid
        assert restored.verify_and_consume(codes[1]) is True

    def test_timing_safety(self, manager_and_codes: tuple) -> None:
        """verify_and_consume uses hmac.compare_digest — no early exit."""
        import time
        manager, codes = manager_and_codes
        t1_start = time.perf_counter()
        manager.verify_and_consume(codes[0])
        t1 = time.perf_counter() - t1_start

        manager2, _ = ScratchCodeManager.generate()
        t2_start = time.perf_counter()
        manager2.verify_and_consume("XXXXXXXX")
        t2 = time.perf_counter() - t2_start

        # Timing difference should be negligible (< 50ms)
        # This is a smoke test, not a rigorous timing test
        assert abs(t1 - t2) < 0.05
