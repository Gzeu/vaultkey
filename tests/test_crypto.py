"""
Tests for AES-256-GCM encryption, HKDF subkey derivation, and SecureMemory.

Includes FIX #6 regression: DOMAIN_SALT is applied — subkeys derived with
different app constants must differ.
"""

import secrets
import pytest
from cryptography.exceptions import InvalidTag
from hypothesis import given, settings, strategies as st

from wallet.core.crypto import (
    DOMAIN_SALT,
    SecureMemory,
    decrypt_aes_gcm,
    decrypt_entry_value,
    derive_entry_subkey,
    encrypt_aes_gcm,
    encrypt_entry_value,
    wallet_aad,
)


class TestAESGCM:
    def test_encrypt_decrypt_roundtrip(self):
        key = secrets.token_bytes(32)
        plaintext = b"sk-test-supersecretapikey12345"
        nonce, ct = encrypt_aes_gcm(key, plaintext)
        assert decrypt_aes_gcm(key, nonce, ct) == plaintext

    def test_decrypt_with_aad(self):
        key = secrets.token_bytes(32)
        aad = b"context-binding"
        nonce, ct = encrypt_aes_gcm(key, b"data", aad=aad)
        assert decrypt_aes_gcm(key, nonce, ct, aad=aad) == b"data"

    def test_wrong_aad_raises(self):
        key = secrets.token_bytes(32)
        nonce, ct = encrypt_aes_gcm(key, b"data", aad=b"correct")
        with pytest.raises(InvalidTag):
            decrypt_aes_gcm(key, nonce, ct, aad=b"wrong")

    def test_tamper_detection(self):
        key = secrets.token_bytes(32)
        nonce, ct = encrypt_aes_gcm(key, b"sensitive")
        tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
        with pytest.raises(InvalidTag):
            decrypt_aes_gcm(key, nonce, tampered)

    def test_wrong_key_fails(self):
        nonce, ct = encrypt_aes_gcm(secrets.token_bytes(32), b"secret")
        with pytest.raises(InvalidTag):
            decrypt_aes_gcm(secrets.token_bytes(32), nonce, ct)

    def test_nonce_uniqueness(self):
        key = secrets.token_bytes(32)
        nonces = {encrypt_aes_gcm(key, b"x")[0] for _ in range(500)}
        assert len(nonces) == 500

    def test_key_length_enforced(self):
        with pytest.raises(AssertionError):
            encrypt_aes_gcm(b"tooshort", b"data")

    @given(st.binary(min_size=1, max_size=4096))
    @settings(max_examples=100)
    def test_arbitrary_plaintext_roundtrip(self, plaintext: bytes):
        """Property: encrypt → decrypt = identity for any input."""
        key = secrets.token_bytes(32)
        nonce, ct = encrypt_aes_gcm(key, plaintext)
        assert decrypt_aes_gcm(key, nonce, ct) == plaintext


class TestHKDF:
    def test_subkey_deterministic(self):
        master = secrets.token_bytes(32)
        k1 = derive_entry_subkey(master, "uuid-123")
        k2 = derive_entry_subkey(master, "uuid-123")
        assert k1 == k2

    def test_different_ids_different_subkeys(self):
        master = secrets.token_bytes(32)
        assert derive_entry_subkey(master, "aaa") != derive_entry_subkey(master, "bbb")

    def test_different_masters_different_subkeys(self):
        assert (
            derive_entry_subkey(secrets.token_bytes(32), "same-id")
            != derive_entry_subkey(secrets.token_bytes(32), "same-id")
        )

    def test_domain_salt_is_32_bytes(self):
        """FIX #6 regression: DOMAIN_SALT must be exactly 32 bytes."""
        assert len(DOMAIN_SALT) == 32

    def test_domain_salt_affects_subkey(self):
        """
        FIX #6 regression: subkeys derived with explicit DOMAIN_SALT must
        differ from those that would be derived with the all-zero default salt.
        """
        from cryptography.hazmat.primitives.hashes import SHA256
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        master = secrets.token_bytes(32)
        entry_id = "test-entry"

        # Subkey from our code (uses DOMAIN_SALT)
        with_domain_salt = derive_entry_subkey(master, entry_id)

        # Subkey using zero salt (old behaviour)
        hkdf_zero = HKDF(
            algorithm=SHA256(),
            length=32,
            salt=None,   # defaults to zero-filled
            info=f"vaultkey:entry:{entry_id}".encode(),
        )
        with_zero_salt = hkdf_zero.derive(master)

        assert with_domain_salt != with_zero_salt


class TestEntryEncryption:
    def test_roundtrip(self):
        master = secrets.token_bytes(32)
        entry_id = "entry-uuid-001"
        original = "sk-prod-abcdefghijklmnopqrstuvwxyz"
        nonce, ct = encrypt_entry_value(master, entry_id, original)
        assert decrypt_entry_value(master, entry_id, nonce, ct) == original

    def test_wrong_master_fails(self):
        nonce, ct = encrypt_entry_value(secrets.token_bytes(32), "id", "secret")
        with pytest.raises(InvalidTag):
            decrypt_entry_value(secrets.token_bytes(32), "id", nonce, ct)


class TestSecureMemory:
    def test_zeroed_on_exit(self):
        data = b"supersecretkey123"
        sm = SecureMemory(data)
        buf = sm._buf
        with sm:
            assert bytes(buf) == data
        assert all(b == 0 for b in buf)

    def test_context_manager_returns_bytearray(self):
        with SecureMemory(b"hello") as buf:
            assert isinstance(buf, bytearray)


class TestWalletAAD:
    def test_aad_length(self):
        assert len(wallet_aad("/home/user/wallet.enc")) == 32

    def test_aad_path_binding(self):
        assert wallet_aad("/path/a") != wallet_aad("/path/b")
