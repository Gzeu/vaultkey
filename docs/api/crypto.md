# `wallet.core.crypto`

AES-256-GCM encryption and decryption for individual API key values.

## Overview

Each API key entry is encrypted under a unique per-entry subkey derived via HKDF from the master key. A fresh 96-bit nonce is generated for every write. The wallet file path is bound into the AAD to prevent relocation attacks.

## Functions

### `encrypt_entry_value`

```python
def encrypt_entry_value(
    master_key: bytes,
    entry_id: str,
    plaintext: str,
) -> tuple[bytes, bytes]:
    ...
```

Encrypt a plaintext API key value.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `master_key` | `bytes` | 32-byte master key from `derive_key()` |
| `entry_id` | `str` | UUID of the entry (used as HKDF info) |
| `plaintext` | `str` | The raw API key value |

**Returns:** `(nonce, ciphertext)` — both as raw `bytes`.

- `nonce`: 12 bytes, generated fresh via `os.urandom(12)`
- `ciphertext`: AES-256-GCM output, includes 16-byte authentication tag

**Raises:**
- `ValueError`: if `master_key` is not 32 bytes

**Example:**
```python
from wallet.core.kdf import derive_key, KDFParams
from wallet.core.crypto import encrypt_entry_value, decrypt_entry_value

params = KDFParams.generate()
master_key = derive_key("my-password", params)

nonce, cipher = encrypt_entry_value(master_key, entry_id, "sk-abc123...")
```

---

### `decrypt_entry_value`

```python
def decrypt_entry_value(
    master_key: bytes,
    entry_id: str,
    nonce: bytes,
    ciphertext: bytes,
) -> str:
    ...
```

Decrypt a stored ciphertext back to the plaintext API key value.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `master_key` | `bytes` | 32-byte master key |
| `entry_id` | `str` | UUID of the entry (must match the UUID used at encryption time) |
| `nonce` | `bytes` | 12-byte nonce stored alongside the ciphertext |
| `ciphertext` | `bytes` | AES-256-GCM ciphertext (with authentication tag) |

**Returns:** The plaintext API key value as a `str`.

**Raises:**
- `cryptography.exceptions.InvalidTag`: if the ciphertext was tampered with, or `entry_id`/`master_key` do not match
- `ValueError`: if inputs are malformed

---

## Internal: Per-Entry Subkey Derivation

Internally, `encrypt_entry_value` and `decrypt_entry_value` derive a per-entry subkey via HKDF-SHA256:

```python
subkey = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=b"vaultkey-entry-v1",
    info=f"wallet:entry:{entry_id}".encode(),
).derive(master_key)
```

This means compromising the subkey of one entry reveals nothing about any other entry or the master key.

## Internal: AAD Construction

The AAD passed to AES-256-GCM is:

```python
aad = hashlib.sha256(str(wallet_path).encode()).digest()
```

This binds the ciphertext to the specific wallet file path. Moving `wallet.enc` to a different path makes decryption fail.
