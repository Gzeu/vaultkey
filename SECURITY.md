# Security Policy

## Supported Versions

| Version | Supported |
|---------|:---------:|
| 1.x     | ✅        |
| < 1.0   | ❌        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities via **GitHub Security Advisories** (preferred):
→ https://github.com/Gzeu/vaultkey/security/advisories/new

Or via encrypted email — contact the maintainer through the profile listed on the repository.

You will receive an acknowledgement within **48 hours** and a status update within **7 days**.

---

## Security Design

### Encryption

- **AES-256-GCM** (NIST-approved AEAD) for all ciphertext storage.
- **Argon2id** (OWASP-recommended KDF) for master password derivation:
  - `t=3` iterations, `m=65536` KB (64 MB), `p=1` thread.
- **HKDF-SHA256** with explicit domain-separation salt for per-entry subkeys.
  Each API key is encrypted under its own unique sub-key derived from the master key + entry UUID.
- **HMAC-SHA256** integrity manifest over all entries, stored encrypted.

### Storage

- Wallet file stored at `~/.local/share/vaultkey/wallet.enc` (Linux/Mac) or `%APPDATA%/vaultkey/wallet.enc` (Windows).
- File permissions enforced to **0600** on Unix (user-only read/write).
- **AAD (Associated Authenticated Data)** binds the ciphertext to the wallet file path.
  Moving `wallet.enc` to a different path causes AES-GCM authentication to fail.
- Atomic write: content written to `.wallet.enc.tmp`, then renamed.
  Prevents partial writes from corrupting the wallet.
- Automatic rolling backups with configurable limit (`max_backups=10`).

### Session

- Derived key held as `bytearray` in memory (mutable).
  On lock: `ctypes.memset` zeros the buffer before releasing.
- Session auto-expires after 15 minutes of inactivity (configurable).
- Exponential backoff on failed unlock attempts: `2^(n−1)` seconds, capped at 60s.
- Hard lockout: 5 consecutive failures trigger a 60-second hard lockout window.
  Lockout state is audited (`LOCKOUT_RESET` event on expiry).

### Clipboard

- API key values copied to clipboard are **automatically cleared** after 30 seconds.
- Clipboard clearing is cross-platform (pyperclip with xclip/xsel on Linux, pbcopy on Mac, win32clipboard on Windows).

### Audit Log

- All sensitive operations logged to `audit.log` as JSON-Lines (append-only).
- Log file permissions: **0600** on Unix.
- Automatic rotation at 5 MB; 2 rotations kept.
- **Passwords and API key values are never written to the audit log.**
- Log entries include: timestamp (UTC), event type, status, PID, OS username, key name, extra context.

### No-network by design

VaultKey is a fully **offline** tool. It makes no network requests.
No telemetry, no auto-update, no cloud sync.

---

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Malware reading wallet file | AES-256-GCM; attacker needs master password to decrypt |
| Brute-force master password | Argon2id 64MB; exponential backoff; hard lockout |
| Cold-boot attack on memory | ctypes.memset zeros key on lock; short session timeout |
| Clipboard sniffing | Auto-clear after 30s |
| Wallet relocation attack | AAD bound to file path |
| Partial write corruption | Atomic write via tmp-file rename |
| Audit log tampering | HMAC-protected (TODO: append-only HMAC chain in v2) |
| Compromised single entry | Per-entry HKDF sub-keys: one compromise ≠ all compromised |

---

## Dependency Security

Dependencies are pinned in `pyproject.toml`. Run:

```bash
pip audit          # or: safety check
bandit -r wallet/  # static security scan
```

A GitHub Actions security scan job runs `bandit` on every push and PR.

---

## Cryptographic Primitives

| Primitive | Library | Standard |
|-----------|---------|----------|
| AES-256-GCM | `cryptography` (OpenSSL) | NIST SP 800-38D |
| Argon2id | `argon2-cffi` | RFC 9106 / OWASP |
| HKDF-SHA256 | `cryptography` | RFC 5869 |
| HMAC-SHA256 | `cryptography` | RFC 2104 |
| CSPRNG nonces | `secrets.token_bytes` | OS /dev/urandom |
