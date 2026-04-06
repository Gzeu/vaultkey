# `wallet.core.integrity`

HMAC-SHA256 integrity manifest to detect wallet tampering.

## Overview

After every write, VaultKey computes a HMAC-SHA256 over all entry UUIDs and their ciphertexts in sorted (deterministic) order. On every load, the manifest is recomputed and compared. Any mutation — added entries, removed entries, modified ciphertexts, or bit-rot — causes an `IntegrityError`.

## Functions

### `compute_manifest`

```python
def compute_manifest(
    master_key: bytes,
    entries: dict[str, APIKeyEntry],
    hmac_salt: bytes,
) -> str:
    ...
```

Compute the HMAC-SHA256 integrity manifest.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `master_key` | `bytes` | 32-byte master key |
| `entries` | `dict[str, APIKeyEntry]` | All entries in the wallet, keyed by UUID |
| `hmac_salt` | `bytes` | 32-byte salt stored in the wallet header |

**Returns:** A hex-encoded HMAC-SHA256 string.

**Algorithm:**
```python
# Sort entries deterministically
sorted_ids = sorted(entries.keys())
message = b"".join(
    entry_id.encode() + bytes.fromhex(entries[entry_id].cipher_hex)
    for entry_id in sorted_ids
)
hmac_key = HKDF(info=b"vaultkey:integrity:v1", ...).derive(master_key)
manifest = hmac.new(hmac_key, message, digestmod=sha256).hexdigest()
```

---

### `verify_manifest`

```python
def verify_manifest(
    master_key: bytes,
    entries: dict[str, APIKeyEntry],
    hmac_salt: bytes,
    stored_manifest: str,
) -> None:
    ...
```

Verify the stored manifest against the current wallet state.

**Raises:** `IntegrityError` if the computed manifest does not match the stored one.

**Note:** Uses `hmac.compare_digest()` for constant-time comparison to prevent timing attacks.

---

## Exceptions

### `IntegrityError`

```python
class IntegrityError(Exception):
    """Raised when the HMAC integrity check fails."""
```

Raised by `verify_manifest()` and by `WalletStorage.load()` when the manifest does not match.

**Causes:**
- File was tampered with outside VaultKey
- Bit-rot or filesystem corruption
- Partial write that bypassed atomic save
- Entry UUID list modified without updating the manifest

---

## Example

```python
from wallet.core.integrity import compute_manifest, verify_manifest, IntegrityError

# On save (done internally by WalletStorage)
manifest = compute_manifest(master_key, payload.keys, hmac_salt)

# On load (done internally by WalletStorage)
try:
    verify_manifest(master_key, payload.keys, hmac_salt, stored_manifest)
except IntegrityError:
    print("❌ Wallet integrity check failed — file may have been tampered with")
    sys.exit(2)
```
