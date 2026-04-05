"""Tests for AES-256-GCM encryption and HKDF subkey derivation."""

import secrets
import pytest
from cryptography.exceptions import InvalidTag
from hypothesis import given, settings, strategies as st

from wallet.core.crypto import (
    SecureMemory,
    decrypt_aes_gcm,
    decrypt_entry_value,
    encrypt_aes_gcm,
    encrypt_entry_value,
    derive_entry_subkey,
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
        k1 = derive_entry_subkey(master, "uuid-aaa")
        k2 = derive_entry_subkey(master, "uuid-bbb")
        assert k1 != k2

    def test_different_masters_different_subkeys(self):
        k1 = derive_entry_subkey(secrets.token_bytes(32), "same-id")
        k2 = derive_entry_subkey(secrets.token_bytes(32), "same-id")
        assert k1 != k2


class TestEntryEncryption:
    def test_roundtrip(self):
        master = secrets.token_bytes(32)
        entry_id = "entry-uuid-001"
        original = "sk-prod-abcdefghijklmnopqrstuvwxyz"
        nonce, ct = encrypt_entry_value(master, entry_id, original)
        result = decrypt_entry_value(master, entry_id, nonce, ct)
        assert result == original

    def test_wrong_master_fails(self):
        master1 = secrets.token_bytes(32)
        master2 = secrets.token_bytes(32)
        nonce, ct = encrypt_entry_value(master1, "id", "secret")
        with pytest.raises(InvalidTag):
            decrypt_entry_value(master2, "id", nonce, ct)


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
            assert buf == bytearray(b"hello")


class TestWalletAAD:
    def test_aad_is_bytes(self):
        aad = wallet_aad("/home/user/wallet.enc")
        assert isinstance(aad, bytes)
        assert len(aad) == 32

    def test_aad_different_paths(self):
        a = wallet_aad("/path/a/wallet.enc")
        b = wallet_aad("/path/b/wallet.enc")
        assert a != b
