# Security Architecture

## Key Hierarchy

```
Master Password
    │
    ├── Argon2id (64 MB, 3 iter, 4 threads)
    │       └── Master Key (32 bytes)
    │               ├── HKDF-SHA256(info="wallet:entry:<uuid>")
    │               │       └── Entry Subkey (32 bytes)
    │               │               └── AES-256-GCM(nonce, AAD) → ciphertext
    │               └── HMAC-SHA256 over all entry IDs + ciphertexts
    │                       └── Integrity Manifest
    └── Argon2id (separate salt)
            └── Master Hash (stored encrypted, used to verify password)
```

## AES-256-GCM Details

- **Nonce**: 96-bit (12 bytes), generated fresh per entry per write via `os.urandom(12)`
- **AAD (Additional Authenticated Data)**: `SHA-256(wallet_path)` — binds the ciphertext to the specific wallet file path, preventing relocation attacks
- **Tag**: 128-bit authentication tag, verified before any plaintext is returned
- **Key rotation**: Rotating an entry generates a new nonce and re-encrypts under the same master key

## Argon2id Parameters

| Parameter | Value | Rationale |
|---|---|---|
| Memory | 64 MB | Makes GPU/ASIC attacks expensive |
| Iterations | 3 | Time hardness on top of memory |
| Parallelism | 4 | Matches typical CPU core count |
| Salt | 32 bytes random | Unique per wallet |
| Output | 32 bytes | AES-256 key |

## Per-Entry Subkey Isolation

Each API key is encrypted under its own subkey derived via HKDF-SHA256:

```python
subkey = HKDF(
    algorithm=SHA256,
    length=32,
    salt=domain_salt,       # "vaultkey-entry-v1" encoded
    info=f"wallet:entry:{entry_uuid}".encode(),
).derive(master_key)
```

Compromising one entry's subkey reveals nothing about any other entry or the master key.

## Memory Security

- Derived keys are stored in `SecureBytes` wrapper that calls `ctypes.memset` on cleanup
- `SessionManager.lock()` zeros the key immediately regardless of GC timing
- Auto-lock runs via `threading.Timer` — the key is zeroed even if the process is idle
- Python's GC is non-deterministic; `ctypes.memset` bypasses it for guaranteed zeroing

## HMAC Integrity Manifest

After every write, a HMAC-SHA256 is computed over the concatenation of all entry UUIDs and their ciphertexts, in sorted order. On load, the manifest is recomputed and compared. Any mutation (added/removed/modified entry, bit-rot) fails verification and raises `IntegrityError`.

## Audit Log

Every operation is appended to `audit.log` as a JSON-Lines record:

```json
{"ts": "2026-04-06T12:00:00Z", "event": "GET", "key_name": "OpenAI Prod", "status": "OK", "pid": 12345, "user": "george"}
```

The audit log file is set to `chmod 600` and uses atomic append to prevent corruption under concurrent access.

## Threat Model

| Threat | Mitigation |
|---|---|
| Disk theft | AES-256-GCM + Argon2id: brute-force infeasible |
| File relocation | AAD binding to `SHA-256(wallet_path)` |
| Silent tampering | HMAC-SHA256 integrity manifest |
| Clipboard sniffing | Auto-clear after 30 s |
| Brute-force login | Exponential backoff + 60 s lockout after 5 failures |
| Memory dump | `ctypes.memset` zeroing on lock/timeout |
| Partial write crash | Atomic `os.replace()` — no half-written files |
| Unauthorized copy | chmod 600 on wallet + audit log |
