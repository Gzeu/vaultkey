# `wallet.core.storage`

Encrypted wallet file read/write with atomic saves and automatic backup.

## Overview

`WalletStorage` handles all filesystem I/O. It never touches plaintext — it receives a serialized `dict` (from `WalletPayload.to_dict()`), serializes it to JSON, encrypts with AES-256-GCM, and writes atomically via `os.replace()`.

## Classes

### `WalletStorage`

```python
class WalletStorage:
    def __init__(
        self,
        wallet_path: Path,
        backup_dir: Path | None = None,
    ) -> None: ...
```

| Parameter | Description |
|---|---|
| `wallet_path` | Path to the `.enc` wallet file |
| `backup_dir` | Optional directory for automatic backups. If `None`, backups are disabled |

---

### `WalletStorage.exists`

```python
def exists(self) -> bool:
    ...
```

Return `True` if the wallet file exists on disk.

---

### `WalletStorage.save`

```python
def save(
    self,
    master_key: bytes,
    params: KDFParams,
    data: dict,
) -> None:
    ...
```

Encrypt `data` with `master_key` and write atomically to `wallet_path`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `master_key` | `bytes` | 32-byte master key |
| `params` | `KDFParams` | KDF params to embed in file header |
| `data` | `dict` | Serializable wallet payload from `WalletPayload.to_dict()` |

**Side effects:**
- If `backup_dir` is set, creates a timestamped copy before overwriting
- Sets file permissions to `0o600`
- Uses `os.replace()` for atomicity

---

### `WalletStorage.load`

```python
def load(self, master_key: bytes) -> dict:
    ...
```

Read and decrypt the wallet file.

**Returns:** The decrypted wallet payload as a `dict`.

**Raises:**
- `FileNotFoundError`: wallet does not exist
- `cryptography.exceptions.InvalidTag`: wrong password or tampered file
- `IntegrityError`: HMAC manifest check failed

---

### `WalletStorage.read_kdf_params`

```python
def read_kdf_params(self) -> KDFParams:
    ...
```

Read only the KDF parameters from the file header (does not decrypt the payload). Used to derive the key before loading.

---

## File Format

The `.enc` file is a binary structure:

```
Offset   Size    Field
──────   ────    ─────
0        4       Magic bytes: b"VKEY"
4        1       Format version: 0x01
5        2       Header length (little-endian uint16)
7        N       Header JSON (KDF params + HMAC salt)
7+N      12      AES-GCM nonce
7+N+12   16      AES-GCM authentication tag
7+N+28   *       AES-256-GCM ciphertext (JSON payload)
```

All byte offsets are from the start of the file.

---

## Backup Naming

Backups are stored as:
```
{backup_dir}/wallet_{YYYYMMDD_HHMMSS}.enc
```

Example: `~/.local/share/vaultkey/backups/wallet_20260406_143022.enc`
