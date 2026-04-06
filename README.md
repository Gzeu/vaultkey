# VaultKey 🔐

> Ultra-secure local API key wallet — AES-256-GCM · Argon2id · HMAC Integrity · Zero cloud dependency

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Security](https://img.shields.io/badge/encryption-AES--256--GCM-red)](https://en.wikipedia.org/wiki/AES-GCM)
[![Tests](https://img.shields.io/badge/tests-123%20passing-brightgreen)](#testing)
[![Version](https://img.shields.io/badge/version-1.2.0-blue)](#changelog)

---

## What is VaultKey?

VaultKey stores your API keys locally in an encrypted binary file (`wallet.enc`).  
No cloud sync. No telemetry. No vendor lock-in. Your keys never leave your machine.

Every key is encrypted with a **unique per-entry subkey** derived via HKDF-SHA256 from your master key.  
Compromising one entry reveals nothing about any other.

---

## Security Architecture

| Layer | Technology | Parameters |
|---|---|---|
| Key Derivation | Argon2id | 64 MB RAM · 3 iterations · 4 threads |
| Encryption | AES-256-GCM | 96-bit nonce · 128-bit AEAD tag |
| Per-entry subkeys | HKDF-SHA256 | Domain salt + entry UUID info |
| Password verification | Argon2id hash | Separate salt, stored encrypted |
| Integrity manifest | HMAC-SHA256 | Over all entry IDs + ciphertexts |
| AAD binding | SHA-256(wallet_path) | Prevents file relocation attacks |
| Memory security | ctypes.memset | Key zeroed on lock / timeout |
| File permissions | chmod 600 | User-only read/write |
| Atomic writes | temp + os.replace() | No partial writes on crash |
| Audit log | JSON-Lines | Per-event PID + user + timestamp |
| Brute-force protection | Exponential backoff | 1 → 2 → 4 → 60 s hard lockout |
| Clipboard hygiene | Auto-clear | Cleared after 30 s (configurable) |

---

## Quick Start

```bash
# Install
pip install vaultkey

# Initialize a new wallet (sets master password, creates wallet.enc)
wallet init

# Unlock the session (15-min auto-lock)
wallet unlock

# Add an API key
wallet add --name "OpenAI Production" --tags "ai,production" --expires 2025-12-31

# Copy to clipboard (auto-clears after 30 s)
wallet get "OpenAI Production"

# Health report across all keys
wallet health

# Launch interactive TUI
wallet tui
```

---

## CLI Reference

### Wallet Lifecycle

| Command | Description |
|---|---|
| `wallet init` | Create a new encrypted wallet |
| `wallet unlock` | Unlock — derive session key from master password |
| `wallet lock` | Lock and zero the session key from memory |
| `wallet status` | Session state, key counts, pending warnings |
| `wallet change-password` | Re-key entire wallet under new master password |
| `wallet wipe` | **Emergency** — 3-step confirmation → secure destroy wallet + backups |

### Key Management

| Command | Description |
|---|---|
| `wallet add` | Add a new API key (prompts for value, never stored raw) |
| `wallet get <name>` | Copy key to clipboard (auto-clear 30 s) |
| `wallet get <name> --show` | Show masked value in terminal |
| `wallet get <name> --raw` | Print raw value (for piping / scripts) |
| `wallet get <name> --env` | Print as `export SERVICE_API_KEY=value` |
| `wallet list` | List all keys — no values ever shown |
| `wallet list --tag ai` | Filter by tag |
| `wallet list --service openai` | Filter by service |
| `wallet list --sort expires` | Sort by expiry date |
| `wallet list --expired` | Show only expired keys |
| `wallet info <name>` | Full metadata + health score for one key |
| `wallet rotate <name>` | Replace key value (new nonce, same entry ID) |
| `wallet delete <name>` | Delete with double confirmation |
| `wallet tag <name> --add prod` | Add tags without re-encryption |
| `wallet tag <name> --remove old` | Remove tags |
| `wallet search <query>` | Fuzzy search across name, service, tags, description |

### Security & Maintenance

| Command | Description |
|---|---|
| `wallet health` | Wallet-wide health scores + rotation recommendations |
| `wallet health --all` | Show all entries, not just problematic ones |
| `wallet audit` | View structured audit log (last 50 events) |
| `wallet audit --event GET` | Filter by event type |
| `wallet audit --failed` | Show only FAIL events |
| `wallet verify` | Structural + HMAC integrity check |

### Backup & Portability

| Command | Description |
|---|---|
| `wallet export --output backup.enc` | Encrypted export with separate password |
| `wallet import <file>` | Import keys from encrypted backup |
| `wallet import <file> --on-conflict rename` | Conflict strategy: `skip` / `overwrite` / `rename` |

### UI Launchers

| Command | Description |
|---|---|
| `wallet tui` | Full-screen interactive TUI (Textual) |
| `wallet gui` | Desktop GUI (customtkinter) |

---

## Security Guarantees

- **Keys never touch disk unencrypted** — encrypted in memory before `save()` is called
- **Per-entry subkey isolation** — each key encrypted under its own HKDF-derived subkey
- **Anti-relocation** — AAD binding (SHA-256 of wallet path) prevents moving `wallet.enc`
- **Integrity detection** — HMAC-SHA256 manifest detects silent bit-rot or tampering
- **Memory zeroing** — `ctypes.memset` wipes derived key on lock, timeout, or process exit
- **Audit trail** — every operation logged: event · status · PID · user · timestamp (chmod 600)
- **Panic wipe** — triple-confirmed secure destruction of wallet + all backups
- **Session timeout** — auto-lock after 15 minutes of inactivity (configurable)
- **Brute-force resistance** — exponential delay per failed attempt + 60 s hard lockout after 5 failures

---

## File Layout

```
~/.local/share/vaultkey/
├── wallet.enc          # Encrypted wallet binary (magic VKEY + Argon2 header + AES-GCM payload)
├── audit.log           # JSON-Lines audit trail (chmod 600)
└── backups/
    ├── wallet_20250101_120000.enc
    └── ...             # Auto-pruned to last 20 backups (configurable)
```

### wallet.enc Binary Format

```
[4 bytes]  magic: b'VKEY'
[2 bytes]  version: uint16 big-endian (current: 1)
[4 bytes]  kdf_params_len: uint32 big-endian
[N bytes]  kdf_params_json: Argon2id params + salt_hex
[12 bytes] nonce: AES-GCM nonce
[M bytes]  ciphertext: AES-GCM encrypted+authenticated payload
```

---

## Configuration

Configure via environment variables or `.env` file at project root:

```bash
VAULTKEY_WALLET_PATH=/secure/volume/wallet.enc
VAULTKEY_SESSION_TIMEOUT_MINUTES=10
VAULTKEY_CLIPBOARD_CLEAR_SECONDS=15
VAULTKEY_MAX_BACKUPS=30
VAULTKEY_ENABLE_INTEGRITY_CHECK=true
```

---

## Testing

VaultKey has a comprehensive test suite with **123 tests** across 11 files:

```
tests/
├── conftest.py           # Shared fixtures (session + function scope)
├── test_crypto.py        # 16 tests — AES-GCM, HKDF, SecureMemory
├── test_kdf.py           # 10 tests — Argon2id derive, hash, verify
├── test_storage.py       # 12 tests — binary format, atomic write, backups
├── test_session.py       # 14 tests — unlock, lock, timeout, brute-force
├── test_audit.py         # 12 tests — JSON-Lines, rotation, filtering
├── test_validators.py    # 20 tests — key name, API key value, expiry date
├── test_health.py        # 12 tests — health scoring, grading, recommendations
├── test_prefix_detect.py #  8 tests — service detection (OpenAI, Anthropic, GitHub…)
├── test_integrity.py     #  6 tests — HMAC manifest, structural checks
└── test_hypothesis.py    # 13 property-based tests (Hypothesis)
                          #    P1–P5: crypto correctness + tamper detection
                          #    P6–P8: validator contracts
                          #    P9–P13: model round-trip + KDF determinism
```

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests with coverage
pytest tests/ -v --cov=wallet --cov-report=term-missing

# Run only fast tests (skip Hypothesis)
pytest tests/ -v --ignore=tests/test_hypothesis.py

# Run a specific file
pytest tests/test_crypto.py -v
```

---

## Development

```bash
# Clone and install
git clone https://github.com/Gzeu/vaultkey.git
cd vaultkey
pip install -e ".[dev]"

# Lint
ruff check wallet/ tests/

# Type check
mypy wallet/ --ignore-missing-imports

# Security scan
bandit -r wallet/ -c pyproject.toml --severity-level medium

# Build and serve docs locally
mkdocs serve
```

---

## Documentation

Full documentation available at **[gzeu.github.io/vaultkey](https://gzeu.github.io/vaultkey)** (deploy with `mkdocs gh-deploy`).

- **Installation guide** — platform notes, clipboard backends, XDG paths
- **Quickstart** — 8-command walk-through from `init` to `wipe`
- **Security architecture** — key hierarchy, AAD, HMAC, memory security

---

## Changelog

### v1.2.0 — Wave 5 (current)
- 39 new tests: `test_health`, `test_prefix_detect`, `test_integrity`, 13 Hypothesis properties
- Shared `conftest.py` with session-scoped Argon2id fixtures (Argon2id runs once per `pytest` invocation)
- Full MkDocs documentation site with Material theme + mkdocstrings
- `pyproject.toml` migrated to Hatchling / PEP 621 with full `ruff`, `mypy`, `bandit`, `hypothesis` config

### v1.1.0 — Wave 3–4
- `wallet health` — per-entry health scores + rotation recommendations
- `wallet audit` — structured audit log viewer with filtering
- `wallet verify` — structural + HMAC integrity check
- `wallet wipe` — panic wipe with multi-step confirmation
- `wallet tag`, `wallet search`, `wallet rotate` — key lifecycle commands
- Session brute-force protection (exponential backoff, FIX #1 deadlock resolved)
- HKDF explicit domain salt (FIX #6, RFC 5869 §3.1)
- Windows permission check via `icacls` (FIX #5)

### v1.0.0 — Wave 1–2
- Core AES-256-GCM encryption + Argon2id KDF
- HMAC-SHA256 integrity manifest
- CLI with `init`, `unlock`, `lock`, `add`, `get`, `list`, `delete`, `info`
- TUI + GUI launchers
- Atomic writes, timestamped backups, audit log

---

## License

MIT — see [LICENSE](LICENSE).
