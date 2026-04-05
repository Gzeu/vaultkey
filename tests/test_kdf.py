"""Tests for Argon2id key derivation and password hashing."""

import pytest
from wallet.core.kdf import (
    KDFParams, derive_key, hash_master_password, verify_master_password
)


class TestKDFParams:
    def test_generate_creates_unique_salts(self):
        p1 = KDFParams.generate()
        p2 = KDFParams.generate()
        assert p1.salt_hex != p2.salt_hex

    def test_roundtrip_serialization(self):
        params = KDFParams.generate()
        assert KDFParams.from_dict(params.to_dict()) == params

    def test_salt_property(self):
        params = KDFParams.generate()
        assert len(params.salt) == 32


class TestDeriveKey:
    def test_deterministic_same_salt(self):
        params = KDFParams.generate()
        k1 = derive_key("mypassword", params)
        k2 = derive_key("mypassword", params)
        assert k1 == k2

    def test_different_salt_different_key(self):
        p1 = KDFParams.generate()
        p2 = KDFParams.generate()
        k1 = derive_key("mypassword", p1)
        k2 = derive_key("mypassword", p2)
        assert k1 != k2

    def test_different_password_different_key(self):
        params = KDFParams.generate()
        k1 = derive_key("password1", params)
        k2 = derive_key("password2", params)
        assert k1 != k2

    def test_key_length_is_32(self):
        key = derive_key("test", KDFParams.generate())
        assert len(key) == 32


class TestPasswordHashing:
    def test_hash_and_verify(self):
        h = hash_master_password("correct-horse-battery")
        assert verify_master_password("correct-horse-battery", h) is True

    def test_wrong_password_fails(self):
        h = hash_master_password("correct")
        assert verify_master_password("wrong", h) is False

    def test_hashes_are_unique(self):
        h1 = hash_master_password("same")
        h2 = hash_master_password("same")
        assert h1 != h2  # Different salts each time
