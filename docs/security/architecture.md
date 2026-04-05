# Security Architecture

## Storage Format

The wallet file (`wallet.enc`) is a binary format with the following layout:

```
[4 bytes]  Magic: VKEY
[4 bytes]  Version: 0x0001 (LE uint32)
[2 bytes]  KDF params JSON length (LE uint16)
[N bytes]  KDF params JSON (UTF-8)
[12 bytes] AES-GCM nonce
[M bytes]  AES-GCM ciphertext + 16-byte GCM tag
```

The **ciphertext** decrypts to a JSON blob containing:
- `master_hash`: Argon2id hash of the master password (for verification)
- `keys`: dict of `{entry_id: APIKeyEntry}` 
- `integrity_hmac`: HMAC-SHA256 over all entry ciphertexts
- `version`, `created_at`, `updated_at`

## Key Hierarchy

```
Master Password
      │
      ▼  Argon2id (t=3, m=64MB, p=1, salt=32B random)
 Master Key (32 bytes, AES-256)
      │
      ├─► Wallet AES-GCM encryption (wallet.enc body)
      │
      └─► HKDF-SHA256(master_key, info=“vaultkey:entry:<uuid>”, salt=DOMAIN_SALT)
              │
              ▼
         Entry Sub-Key (32 bytes, unique per entry)
              │
              ▼  AES-256-GCM
         Encrypted API Key Value
```

## Why per-entry sub-keys?

If an attacker recovers one entry’s sub-key (e.g., via a side-channel),
they **cannot** derive other entries’ sub-keys without the master key.
HKDF with distinct `info` strings provides cryptographic domain separation.

## Associated Authenticated Data (AAD)

The outer AES-GCM encryption uses `SHA-256(wallet_path)` as AAD.
This binds the ciphertext to the exact file path.
Moving `wallet.enc` to a different path will cause AES-GCM authentication to fail—
preventing relocation attacks.

## Integrity Manifest

After decryption, VaultKey verifies:
```
HMAC-SHA256(master_key, sorted(entry.cipher_hex for entry in entries))
```
This detects any in-place modification of entry ciphertexts that bypasses
the outer AES-GCM layer (e.g., direct file editing after decryption).

## Memory Security

- The master key is stored as a `bytearray` (mutable).
- On lock: `ctypes.memset` zeros the buffer byte-by-byte, bypassing Python’s GC.
- `SecureMemory` context manager zeros intermediate keys (HKDF sub-keys) immediately after use.
- Sensitive CLI prompts use `echo=False` (never appear in terminal or shell history).
