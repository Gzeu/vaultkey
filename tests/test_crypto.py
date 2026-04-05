"""
test_crypto.py — Tests for wallet/core/crypto.py.
"""

import secrets

import pytest
from cryptography.exceptions import InvalidTag

from wallet.core.crypto import (
    KEY_SIZE,
    NONCE_SIZE,
    SecureMemory,
    decrypt_aes_gcm,
    decrypt_entry_value,
    derive_entry_subkey,
    encrypt_aes_gcm,
    encrypt_entry_value,
    wallet_aad,
)


MASTER = secrets.token_bytes(32)


class TestAESGCM:
    def test_encrypt_decrypt_roundtrip(self):
        key = secrets.token_bytes(32)
        pt = b"hello, world"
        nonce, ct = encrypt_aes_gcm(key, pt)
        assert decrypt_aes_gcm(key, nonce, ct) == pt

    def test_unique_nonces(self):
        key = secrets.token_bytes(32)
        n1, _ = encrypt_aes_gcm(key, b"x")
        n2, _ = encrypt_aes_gcm(key, b"x")
        assert n1 != n2

    def test_nonce_is_12_bytes(self):
        key = secrets.token_bytes(32)
        nonce, _ = encrypt_aes_gcm(key, b"test")
        assert len(nonce) == NONCE_SIZE

    def test_wrong_key_raises(self):
        key = secrets.token_bytes(32)
        nonce, ct = encrypt_aes_gcm(key, b"secret")
        with pytest.raises(InvalidTag):
            decrypt_aes_gcm(secrets.token_bytes(32), nonce, ct)

    def test_tampered_ciphertext_raises(self):
        key = secrets.token_bytes(32)
        nonce, ct = encrypt_aes_gcm(key, b"secret")
        tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
        with pytest.raises(InvalidTag):
            decrypt_aes_gcm(key, nonce, tampered)

    def test_aad_mismatch_raises(self):
        key = secrets.token_bytes(32)
        nonce, ct = encrypt_aes_gcm(key, b"secret", aad=b"valid-aad")
        with pytest.raises(InvalidTag):
            decrypt_aes_gcm(key, nonce, ct, aad=b"wrong-aad")

    def test_wrong_key_size_asserts(self):
        with pytest.raises(AssertionError):
            encrypt_aes_gcm(b"short", b"data")


class TestHKDF:
    def test_subkey_is_32_bytes(self):
        sk = derive_entry_subkey(MASTER, "some-uuid")
        assert len(sk) == KEY_SIZE

    def test_different_entry_id_different_subkey(self):
        sk1 = derive_entry_subkey(MASTER, "uuid-1")
        sk2 = derive_entry_subkey(MASTER, "uuid-2")
        assert sk1 != sk2

    def test_same_inputs_deterministic(self):
        sk1 = derive_entry_subkey(MASTER, "uuid-abc")
        sk2 = derive_entry_subkey(MASTER, "uuid-abc")
        assert sk1 == sk2

    def test_different_master_different_subkey(self):
        m1 = secrets.token_bytes(32)
        m2 = secrets.token_bytes(32)
        assert derive_entry_subkey(m1, "uuid") != derive_entry_subkey(m2, "uuid")


class TestEntryEncryption:
    def test_encrypt_decrypt_entry(self):
        key = secrets.token_bytes(32)
        entry_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        secret = "sk-prod-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        nonce, cipher = encrypt_entry_value(key, entry_id, secret)
        result = decrypt_entry_value(key, entry_id, nonce, cipher)
        assert result == secret

    def test_wrong_entry_id_decryption_fails(self):
        key = secrets.token_bytes(32)
        nonce, cipher = encrypt_entry_value(key, "entry-1", "myvalue-xxxx")
        with pytest.raises(InvalidTag):
            decrypt_entry_value(key, "entry-2", nonce, cipher)

    def test_wrong_master_key_decryption_fails(self):
        k1 = secrets.token_bytes(32)
        k2 = secrets.token_bytes(32)
        nonce, cipher = encrypt_entry_value(k1, "entry-1", "secretvalue-xxx")
        with pytest.raises(InvalidTag):
            decrypt_entry_value(k2, "entry-1", nonce, cipher)


class TestSecureMemory:
    def test_value_accessible_inside_context(self):
        with SecureMemory(b"secret") as buf:
            assert buf[:6] == b"secret"

    def test_zeroed_after_context(self):
        sm = SecureMemory(b"secret")
        sm.__enter__()
        sm.__exit__(None, None, None)
        # Buffer should be all zeros after context exit
        assert all(b == 0 for b in sm._buf)


class TestWalletAAD:
    def test_same_path_same_aad(self):
        aad1 = wallet_aad("/home/user/.local/share/vaultkey/wallet.enc")
        aad2 = wallet_aad("/home/user/.local/share/vaultkey/wallet.enc")
        assert aad1 == aad2

    def test_different_paths_different_aad(self):
        aad1 = wallet_aad("/path/a/wallet.enc")
        aad2 = wallet_aad("/path/b/wallet.enc")
        assert aad1 != aad2

    def test_aad_is_32_bytes(self):
        assert len(wallet_aad("/any/path")) == 32
