# `wallet.core.kdf`

Argon2id-based key derivation and master password hashing.

## Classes

### `KDFParams`

```python
@dataclass
class KDFParams:
    salt: bytes          # 32-byte random salt
    memory_cost: int     # Argon2id memory in KiB (default: 65536 = 64 MB)
    time_cost: int       # Argon2id iterations (default: 3)
    parallelism: int     # Argon2id parallelism (default: 4)
    hash_len: int        # Output key length in bytes (default: 32)
```

Holds all parameters needed to reproduce a key derivation. Stored (serialized) in `wallet.enc` alongside the ciphertext so the wallet can be decrypted on any machine.

#### `KDFParams.generate()`

```python
@classmethod
def generate(cls) -> KDFParams:
    ...
```

Create a new `KDFParams` with a fresh random salt and default cost parameters.

```python
params = KDFParams.generate()
```

#### Serialization

```python
params_dict = params.to_dict()   # -> dict (stored in wallet header)
params = KDFParams.from_dict(d)  # reconstruct from stored dict
```

---

## Functions

### `derive_key`

```python
def derive_key(password: str, params: KDFParams) -> bytes:
    ...
```

Derive a 32-byte AES master key from a password using Argon2id.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `password` | `str` | Master password (UTF-8 encoded internally) |
| `params` | `KDFParams` | KDF parameters including salt and cost |

**Returns:** 32-byte `bytes` master key.

**Example:**
```python
params = KDFParams.generate()
master_key = derive_key("my-strong-password", params)
assert len(master_key) == 32
```

---

### `hash_master_password`

```python
def hash_master_password(password: str) -> str:
    ...
```

Hash the master password for storage using Argon2id (via `argon2-cffi`). The hash is stored in the wallet payload to verify the password on unlock without re-deriving the full key.

**Returns:** An Argon2 PHC string (e.g. `$argon2id$v=19$m=65536,t=3,p=4$...`).

---

### `verify_master_password`

```python
def verify_master_password(password: str, hash_str: str) -> bool:
    ...
```

Verify a password against a stored Argon2 PHC hash.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `password` | `str` | Password to verify |
| `hash_str` | `str` | Stored Argon2 PHC hash string |

**Returns:** `True` if the password matches, `False` otherwise.

---

## Security Notes

- `derive_key` uses `argon2-cffi` bindings to the reference Argon2 C library.
- The salt is always fresh-generated (`os.urandom(32)`) — never reused.
- The `memory_cost` is expressed in **KiB** internally (65536 KiB = 64 MB).
- Changing `KDFParams` after wallet creation requires re-initialization (`wallet init --force`).
