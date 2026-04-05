"""
test_kdf.py — Tests for wallet/core/kdf.py (Argon2id key derivation).
"""

import secrets

import pytest

from wallet.core.kdf import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    KDFParams,
    derive_key,
    hash_master_password,
    verify_master_password,
)


class TestKDFParams:
    def test_generate_creates_unique_salts(self):
        p1 = KDFParams.generate()
        p2 = KDFParams.generate()
        assert p1.salt_hex != p2.salt_hex

    def test_salt_is_32_bytes(self):
        p = KDFParams.generate()
        assert len(bytes.fromhex(p.salt_hex)) == 32

    def test_to_dict_roundtrip(self):
        p = KDFParams.generate()
        assert KDFParams.from_dict(p.to_dict()).salt_hex == p.salt_hex

    def test_default_params_are_owasp_compliant(self):
        p = KDFParams.generate()
        assert p.time_cost == ARGON2_TIME_COST
        assert p.memory_cost == ARGON2_MEMORY_COST  # 64MB
        assert p.parallelism == ARGON2_PARALLELISM


class TestDeriveKey:
    def test_deterministic(self):
        p = KDFParams.generate()
        k1 = derive_key("mypassword", p)
        k2 = derive_key("mypassword", p)
        assert k1 == k2

    def test_different_salt_different_key(self):
        pw = "mypassword"
        assert derive_key(pw, KDFParams.generate()) != derive_key(pw, KDFParams.generate())

    def test_different_password_different_key(self):
        p = KDFParams.generate()
        assert derive_key("password1", p) != derive_key("password2", p)

    def test_key_is_32_bytes(self):
        k = derive_key("test", KDFParams.generate())
        assert len(k) == 32


class TestPasswordHashing:
    def test_verify_correct_password(self):
        h = hash_master_password("correct")
        assert verify_master_password("correct", h)

    def test_reject_wrong_password(self):
        h = hash_master_password("correct")
        assert not verify_master_password("wrong", h)

    def test_hashes_are_unique(self):
        h1 = hash_master_password("same")
        h2 = hash_master_password("same")
        assert h1 != h2  # different salts

    def test_hash_format_is_argon2id(self):
        h = hash_master_password("test")
        assert h.startswith("$argon2id$")
