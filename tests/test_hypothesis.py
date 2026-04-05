"""
test_hypothesis.py — Property-based tests using Hypothesis.

These tests verify invariants that must hold for ALL valid inputs,
not just the handful of examples covered by example-based tests.

Strategies used:
  st.binary(min_size=32, max_size=32)    — random 32-byte AES keys
  st.binary(min_size=1, max_size=512)    — arbitrary plaintext
  st.text(printable ASCII, min=8, max=256) — API key-like strings
  st.uuids()                              — random entry IDs

Properties verified:
  Crypto:
    P1. decrypt(encrypt(key, pt)) == pt   (for any key, any pt)
    P2. encrypt() always produces unique nonces (no nonce reuse)
    P3. HKDF subkeys: different entry_id ⇒ different subkey
    P4. tampered ciphertext always raises InvalidTag
    P5. tampered nonce always raises InvalidTag

  Validators:
    P6. validate_key_name(valid) never raises for any printable 1-128 char string
    P7. validate_api_key_value rejects strings with embedded whitespace
    P8. parse_expiry_date(YYYY-MM-DD in future) always returns non-None datetime

  Models:
    P9. WalletPayload.to_dict() → from_dict() roundtrip preserves all entry fields
    P10. payload.search(query) always returns a subset of payload.keys.values()
    P11. APIKeyEntry.status_label is always one of {active, expiring, expired, revoked}

  Storage:
    P12. derive_key(password, params) is deterministic (same params ⇒ same key)
    P13. Different passwords ⇒ different keys (birthday bound negligible)
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.exceptions import InvalidTag
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from wallet.core.crypto import (
    decrypt_aes_gcm,
    decrypt_entry_value,
    derive_entry_subkey,
    encrypt_aes_gcm,
    encrypt_entry_value,
)
from wallet.core.kdf import KDFParams, derive_key
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.validators import (
    parse_expiry_date,
    validate_api_key_value,
    validate_key_name,
)


# ------------------------------------------------------------------ #
# Shared strategies
# ------------------------------------------------------------------ #

aes_key = st.binary(min_size=32, max_size=32)
printable_no_ws = st.text(
    alphabet=string.printable.replace(" ", "").replace("\t", "").replace("\n", "")
    .replace("\r", "").replace("\x0b", "").replace("\x0c", ""),
    min_size=1,
    max_size=512,
)
api_key_str = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.+/",
    min_size=8,
    max_size=256,
)
entry_id_str = st.uuids().map(str)

# Key name: printable, 1-128 chars, no control chars
key_name_str = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=128,
).filter(lambda s: s.strip() != "")


# ------------------------------------------------------------------ #
# P1 — encrypt/decrypt roundtrip for arbitrary plaintext
# ------------------------------------------------------------------ #

@given(key=aes_key, plaintext=st.binary(min_size=0, max_size=4096))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_p1_encrypt_decrypt_roundtrip(key: bytes, plaintext: bytes) -> None:
    nonce, ct = encrypt_aes_gcm(key, plaintext)
    assert decrypt_aes_gcm(key, nonce, ct) == plaintext


# ------------------------------------------------------------------ #
# P2 — nonce uniqueness across calls with the same key
# ------------------------------------------------------------------ #

@given(key=aes_key, plaintext=st.binary(min_size=1, max_size=64))
@settings(max_examples=100)
def test_p2_no_nonce_reuse(key: bytes, plaintext: bytes) -> None:
    nonces = {encrypt_aes_gcm(key, plaintext)[0] for _ in range(8)}
    assert len(nonces) == 8, "Nonce collision detected — CSPRNG failure"


# ------------------------------------------------------------------ #
# P3 — HKDF: different entry IDs produce different subkeys
# ------------------------------------------------------------------ #

@given(
    master=aes_key,
    id1=entry_id_str,
    id2=entry_id_str,
)
@settings(max_examples=100)
def test_p3_hkdf_domain_separation(master: bytes, id1: str, id2: str) -> None:
    if id1 == id2:
        return  # trivially equal
    sk1 = derive_entry_subkey(master, id1)
    sk2 = derive_entry_subkey(master, id2)
    assert sk1 != sk2


# ------------------------------------------------------------------ #
# P4 — tampered ciphertext always raises InvalidTag
# ------------------------------------------------------------------ #

@given(
    key=aes_key,
    plaintext=st.binary(min_size=4, max_size=256),
    byte_index=st.integers(min_value=0, max_value=15),
    flip_mask=st.integers(min_value=1, max_value=255),
)
@settings(max_examples=150)
def test_p4_tampered_ciphertext_raises(key, plaintext, byte_index, flip_mask):
    nonce, ct = encrypt_aes_gcm(key, plaintext)
    # Only tamper bytes before the GCM tag (last 16 bytes) if ct is long enough
    if len(ct) <= 16:
        return
    idx = byte_index % (len(ct) - 16)  # stay within body, not tag
    tampered = bytearray(ct)
    tampered[idx] ^= flip_mask
    with pytest.raises(InvalidTag):
        decrypt_aes_gcm(key, nonce, bytes(tampered))


# ------------------------------------------------------------------ #
# P5 — tampered nonce always raises InvalidTag
# ------------------------------------------------------------------ #

@given(
    key=aes_key,
    plaintext=st.binary(min_size=4, max_size=256),
    flip_mask=st.integers(min_value=1, max_value=255),
)
@settings(max_examples=100)
def test_p5_tampered_nonce_raises(key, plaintext, flip_mask):
    nonce, ct = encrypt_aes_gcm(key, plaintext)
    tampered_nonce = bytes([nonce[0] ^ flip_mask]) + nonce[1:]
    if tampered_nonce == nonce:
        return
    with pytest.raises(InvalidTag):
        decrypt_aes_gcm(key, tampered_nonce, ct)


# ------------------------------------------------------------------ #
# P6 — validate_key_name never raises for valid inputs
# ------------------------------------------------------------------ #

@given(name=key_name_str)
@settings(max_examples=200)
def test_p6_validate_key_name_accepts_valid(name: str) -> None:
    import typer
    try:
        result = validate_key_name(name)
        assert result == name.strip()
        assert len(result) <= 128
    except typer.BadParameter:
        # Only acceptable if name contains control chars or is empty after strip
        stripped = name.strip()
        assert stripped == "" or any(ord(c) < 32 for c in stripped)


# ------------------------------------------------------------------ #
# P7 — validate_api_key_value rejects strings with embedded whitespace
# ------------------------------------------------------------------ #

@given(
    prefix=api_key_str,
    suffix=api_key_str,
)
@settings(max_examples=100)
def test_p7_embedded_whitespace_rejected(prefix: str, suffix: str) -> None:
    import typer
    key_with_space = prefix + " " + suffix
    with pytest.raises(typer.BadParameter):
        validate_api_key_value(key_with_space)


# ------------------------------------------------------------------ #
# P8 — parse_expiry_date always returns UTC datetime for future dates
# ------------------------------------------------------------------ #

@given(
    days_ahead=st.integers(min_value=1, max_value=3650),
)
@settings(max_examples=100)
def test_p8_future_date_always_ok(days_ahead: int) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    result = parse_expiry_date(future)
    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result > datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# P9 — WalletPayload to_dict/from_dict roundtrip
# ------------------------------------------------------------------ #

@given(
    master=aes_key,
    names=st.lists(
        st.text(alphabet=string.ascii_letters + string.digits + " -",
                min_size=1, max_size=30),
        min_size=0,
        max_size=10,
        unique=True,
    ),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_p9_payload_roundtrip(master: bytes, names: list[str]) -> None:
    from wallet.core.kdf import hash_master_password
    payload = WalletPayload(master_hash=hash_master_password("test"))
    api_val = "sk-hypothesis-" + "x" * 20
    created_entries = []
    for name in names:
        import uuid as _uuid
        eid = str(_uuid.uuid4())
        nonce, cipher = encrypt_entry_value(master, eid, api_val)
        entry = APIKeyEntry(
            id=eid, name=name, service="test",
            nonce_hex=nonce.hex(), cipher_hex=cipher.hex(),
        )
        payload.add_entry(entry)
        created_entries.append(entry)

    restored = WalletPayload.from_dict(payload.to_dict())
    assert len(restored.keys) == len(payload.keys)
    for entry in created_entries:
        assert entry.id in restored.keys
        restored_entry = restored.keys[entry.id]
        assert restored_entry.name == entry.name
        assert restored_entry.service == entry.service
        assert restored_entry.nonce_hex == entry.nonce_hex
        assert restored_entry.cipher_hex == entry.cipher_hex


# ------------------------------------------------------------------ #
# P10 — search always returns a subset of payload.keys.values()
# ------------------------------------------------------------------ #

@given(
    query=st.text(min_size=0, max_size=20),
)
@settings(max_examples=100)
def test_p10_search_subset(query: str) -> None:
    """search() result is always a subset of all entries."""
    from wallet.core.kdf import hash_master_password
    key = secrets.token_bytes(32)
    payload = WalletPayload(master_hash=hash_master_password("x"))
    api_val = "sk-prop-test-" + "x" * 20
    for service in ["openai", "anthropic", "cohere"]:
        import uuid as _uuid
        eid = str(_uuid.uuid4())
        nonce, cipher = encrypt_entry_value(key, eid, api_val)
        entry = APIKeyEntry(id=eid, name=f"{service} key", service=service,
                             nonce_hex=nonce.hex(), cipher_hex=cipher.hex())
        payload.add_entry(entry)

    results = payload.search(query=query)
    all_ids = set(payload.keys.keys())
    result_ids = {e.id for e in results}
    assert result_ids.issubset(all_ids)


# ------------------------------------------------------------------ #
# P11 — status_label always one of the 4 valid states
# ------------------------------------------------------------------ #

@given(
    days_offset=st.one_of(
        st.just(None),
        st.integers(min_value=-365, max_value=365),
    ),
    is_active=st.booleans(),
)
@settings(max_examples=100)
def test_p11_status_label_valid(days_offset, is_active: bool) -> None:
    key = secrets.token_bytes(32)
    eid = "test-entry-id"
    nonce, cipher = encrypt_entry_value(key, eid, "sk-test-12345678")
    expires_at = None
    if days_offset is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=days_offset)
    entry = APIKeyEntry(
        id=eid, name="Test", service="test",
        nonce_hex=nonce.hex(), cipher_hex=cipher.hex(),
        expires_at=expires_at,
    )
    entry.is_active = is_active
    assert entry.status_label in {"active", "expiring", "expired", "revoked"}


# ------------------------------------------------------------------ #
# P12 — derive_key is deterministic for same password + params
# ------------------------------------------------------------------ #

@given(
    password=st.text(min_size=1, max_size=64),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=10000)
def test_p12_derive_key_deterministic(password: str) -> None:
    params = KDFParams.generate()
    k1 = derive_key(password, params)
    k2 = derive_key(password, params)
    assert k1 == k2
    assert len(k1) == 32


# ------------------------------------------------------------------ #
# P13 — different passwords produce different keys
# ------------------------------------------------------------------ #

@given(
    pw1=st.text(min_size=1, max_size=32),
    pw2=st.text(min_size=1, max_size=32),
)
@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow], deadline=10000)
def test_p13_different_passwords_different_keys(pw1: str, pw2: str) -> None:
    if pw1 == pw2:
        return
    params = KDFParams.generate()
    k1 = derive_key(pw1, params)
    k2 = derive_key(pw2, params)
    assert k1 != k2
