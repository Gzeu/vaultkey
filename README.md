# VaultKey 🔐

> Ultra-secure local API key wallet — AES-256-GCM · Argon2id · HMAC Integrity · Zero cloud dependency

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Security](https://img.shields.io/badge/encryption-AES--256--GCM-red)](https://en.wikipedia.org/wiki/AES-GCM)
[![Tests](https://img.shields.io/badge/tests-156%20passing-brightgreen)](#testing)
[![Version](https://img.shields.io/badge/version-1.4.0-blue)](#changelog)

---

## What is VaultKey?

VaultKey stores your API keys locally in an encrypted binary file (`wallet.enc`).  
No cloud sync. No telemetry. No vendor lock-in. Your keys never leave your machine.

Every key is encrypted with a **unique per-entry subkey** derived via HKDF-SHA256 from your master key.  
Compromising one entry reveals nothing about any other.

**Three interfaces — one vault:**  
`wallet` CLI for scripts · `wallet tui` full-screen terminal · `wallet gui` desktop app

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
wallet add --name "OpenAI Production" --tags "ai,production" --expires 2026-12-31

# Copy to clipboard (auto-clears after 30 s)
wallet get "OpenAI Production"

# Rotate all keys in bulk
wallet rotate-all --tag production --dry-run

# Watch for expiry in the background (daemon)
wallet watch-expiry --interval 3600

# Enable shell completions (bash/zsh/fish)
wallet completion install

# Health report across all keys
wallet health

# Launch interactive TUI
wallet tui

# Launch desktop GUI
wallet gui
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
| `wallet rotate-all` | Rotate all keys in bulk (prompts per-key) |
| `wallet rotate-all --tag <tag>` | Rotate only keys matching a tag |
| `wallet rotate-all --dry-run` | Preview which keys would be rotated |
| `wallet rename <name> --to <new>` | Rename a key (metadata-only, no re-encryption) |
| `wallet delete <name>` | Delete with double confirmation |
| `wallet tag <name> --add prod` | Add tags without re-encryption |
| `wallet tag <name> --remove old` | Remove tags |
| `wallet search <query>` | Fuzzy search across name, service, tags, description |

### Security & Maintenance

| Command | Description |
|---|---|
| `wallet health` | Wallet-wide health scores + rotation recommendations |
| `wallet health --all` | Show all entries, not just problematic ones |
| `wallet expiry-check` | List keys expiring within 7 days (color-coded urgency) |
| `wallet expiry-check --days 30` | Custom look-ahead window |
| `wallet expiry-check --all` | Show all expiry status, not just warnings |
| `wallet watch-expiry` | Background daemon — polls expiry, prints warnings |
| `wallet watch-expiry --interval N` | Poll interval in seconds (default: 3600) |
| `wallet audit` | View structured audit log (last 50 events) |
| `wallet audit --event GET` | Filter by event type |
| `wallet audit --failed` | Show only FAIL events |
| `wallet verify` | Structural + HMAC integrity check |

### Shell Completion

| Command | Description |
|---|---|
| `wallet completion install` | Auto-detect shell and install completions |
| `wallet completion install --shell bash` | Install for a specific shell (bash/zsh/fish) |
| `wallet completion show` | Print completion script to stdout |

### Backup & Portability

| Command | Description |
|---|---|
| `wallet export --output backup.enc` | Encrypted export with separate password |
| `wallet import <file>` | Import keys from encrypted backup |
| `wallet import <file> --on-conflict rename` | Conflict strategy: `skip` / `overwrite` / `rename` |
| `wallet bulk-import <file>` | Import from `.env`, `.json`, or `.csv` |
| `wallet bulk-import <file> --dry-run` | Preview what would be imported |
| `wallet bulk-import <file> --on-conflict overwrite` | Conflict strategy for bulk ops |

### UI Launchers

| Command | Description |
|---|---|
| `wallet tui` | Full-screen interactive TUI (Textual) |
| `wallet gui` | Desktop GUI (CustomTkinter, dark mode) |

---

## Interfaces

### CLI
Standard terminal interface. All commands scriptable. `--raw` and `--env` flags for shell integration.

### TUI (`wallet tui`)
Full-screen Textual app — keyboard-driven, works over SSH. Live search, key detail pane, health view, and a dedicated **Import Panel** (`wallet/ui/tui_import.py`) for in-TUI bulk import with format detection and conflict resolution.

### GUI (`wallet gui`)
Desktop app built with CustomTkinter. **Dark mode only** — secrets should not be visible in bright environments.

| Tab | Features |
|---|---|
| 🗝️ **Keys** | Scrollable card list · live search · Copy / Info / Delete · Add Key dialog |
| 📊 **Health** | Overall grade (A–F) · per-entry scores · issues + recommendations |
| ⚙️ **Settings** | Change password (full re-encryption) · Export encrypted backup · Audit log viewer |

> API key values are **never displayed** in the GUI — only a masked prefix (`sk-...`).  
> Copy sends directly to clipboard; clipboard auto-clears after `clipboard_clear_seconds`.

---

## Bulk Import

Import keys from existing secrets files without manual entry:

```bash
# From a .env file
wallet bulk-import .env --dry-run
wallet bulk-import .env --on-conflict rename

# From a JSON array
wallet bulk-import keys.json

# From a CSV with name,value columns
wallet bulk-import secrets.csv --on-conflict skip
```

**Supported formats:**

| Format | Detection | Expected shape |
|---|---|---|
| `.env` | Extension | `KEY=value` lines; service inferred from key name |
| `.json` | Extension | Array of `{name, value, service?, tags?, description?}` |
| `.csv` | Extension | Header row with `name` + `value` columns (others optional) |

Conflict strategies: `skip` (default) · `overwrite` · `rename` (appends `_1`, `_2`…)

---

## Expiry Checker

Auto-runs silently on `wallet unlock` — warns only if keys are near expiry.

```bash
wallet expiry-check            # keys expiring within 7 days (default)
wallet expiry-check --days 30  # custom window
wallet expiry-check --all      # full status table
wallet watch-expiry            # persistent daemon, re-checks every hour
wallet watch-expiry --interval 1800  # check every 30 minutes
```

| Urgency | Threshold | Color |
|---|---|---|
| `expired` | past due | 🔴 red |
| `critical` | ≤ 3 days | 🟠 orange |
| `warning` | ≤ 7 days | 🟡 yellow |
| `info` | > 7 days | ⚪ gray |

---

## Bulk Rotate

Rotate multiple keys in one pass without touching unrelated entries:

```bash
wallet rotate-all                   # rotate every key interactively
wallet rotate-all --tag production  # scope to a tag
wallet rotate-all --dry-run         # preview — no writes
```

Each key is prompted individually; pressing **Enter** skips it. The HMAC manifest is rewritten once after all rotations complete.

---

## Shell Completions

Tab-completion for all commands, flags, and key names:

```bash
wallet completion install           # auto-detects bash / zsh / fish
wallet completion install --shell zsh
wallet completion show              # pipe into your own rc file
```

The completion script sources dynamic key names from the live wallet, so `wallet get <TAB>` shows your actual stored key names.

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
    ├── wallet_20260101_120000.enc
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

## Project Structure

```
wallet/
├── core/
│   ├── crypto.py        # AES-256-GCM encrypt/decrypt, HKDF subkey derivation
│   ├── health.py        # Per-entry + wallet-wide health scoring (A–F)
│   ├── integrity.py     # HMAC-SHA256 manifest, structural checks
│   ├── kdf.py           # Argon2id derive_key, hash/verify master password
│   ├── rotate.py        # rotate-all bulk rotation logic (v1.4)
│   ├── session.py       # SessionManager — unlock, lock, timeout, brute-force
│   ├── storage.py       # Binary wallet I/O, atomic writes, backups
│   └── wipe.py          # Secure panic wipe
├── models/
│   ├── config.py        # WalletConfig — env vars, paths, timeouts
│   └── wallet.py        # WalletPayload, APIKeyEntry dataclasses (v1.4)
├── ui/
│   ├── cli.py           # Typer CLI — all commands
│   ├── gui.py           # CustomTkinter desktop GUI
│   ├── tui.py           # Textual full-screen TUI
│   └── tui_import.py    # TUI ImportPanel — in-app bulk import (v1.4)
└── utils/
    ├── audit.py         # JSON-Lines audit log writer + reader
    ├── bulk_import.py   # .env / .json / .csv bulk import
    ├── clipboard.py     # Cross-platform copy + auto-clear timer
    ├── expiry_checker.py# Expiry warnings + watch-expiry daemon (v1.4)
    ├── prefix_detect.py # API key prefix → service auto-detection
    ├── shell_completion.py # bash/zsh/fish completion script generator (v1.4)
    └── validators.py    # Key name, value, expiry date validators
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

VaultKey has a comprehensive test suite with **156 tests** across 14 files:

```
tests/
├── conftest.py              # Shared fixtures (session + function scope)
├── test_crypto.py           # 16 tests — AES-GCM, HKDF, SecureMemory
├── test_kdf.py              # 10 tests — Argon2id derive, hash, verify
├── test_storage.py          # 12 tests — binary format, atomic write, backups
├── test_session.py          # 14 tests — unlock, lock, timeout, brute-force
├── test_audit.py            # 12 tests — JSON-Lines, rotation, filtering
├── test_validators.py       # 20 tests — key name, API key value, expiry date
├── test_health.py           # 12 tests — health scoring, grading, recommendations
├── test_prefix_detect.py    #  8 tests — service detection (OpenAI, Anthropic, GitHub…)
├── test_integrity.py        #  6 tests — HMAC manifest, structural checks
├── test_hypothesis.py       # 13 property-based tests (Hypothesis)
│                            #    P1–P5: crypto correctness + tamper detection
│                            #    P6–P8: validator contracts
│                            #    P9–P13: model round-trip + KDF determinism
├── test_rotate.py           # 16 tests — rotate-all, dry-run, tag scoping (v1.4)
├── test_expiry_checker.py   # 17 tests — watch-expiry daemon, urgency levels (v1.4)
└── test_shell_completion.py # 12 tests — bash/zsh/fish completion scripts (v1.4)
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

### v1.4.0 — Wave 8 (current)
- `wallet rotate-all [--tag <tag>] [--dry-run]` — bulk rotate multiple keys in one pass
- `wallet watch-expiry [--interval N]` — persistent background daemon, re-checks expiry on schedule
- `wallet completion install [--shell bash|zsh|fish]` — shell tab-completion for all commands + key names
- TUI **ImportPanel** (`wallet/ui/tui_import.py`) — in-app bulk import with format detection + conflict resolution
- `wallet/core/rotate.py` — isolated rotate-all logic with per-key prompt and single HMAC rewrite
- `wallet/utils/shell_completion.py` — completion script generator (bash/zsh/fish)
- `wallet/utils/expiry_checker.py` extended with `WatchExpiry` daemon class
- 33 new tests: `test_rotate` (16) · `test_expiry_checker` (17) · `test_shell_completion` (12) — **156 total**

### v1.3.0 — Wave 7
- `wallet rename <name> --to <new>` — metadata-only rename, zero re-encryption
- `wallet expiry-check [--days N] [--all]` — color-coded expiry warnings with urgency levels
- `wallet bulk-import <file> [--on-conflict] [--dry-run]` — `.env` / `.json` / `.csv` import
- Auto expiry check on `wallet unlock` — silent unless keys are near expiry
- `WalletPayload.rename_entry()` — clean `KeyError` / `ValueError` on conflicts
- `ExpiryWarning` frozen dataclass with sortable `urgency` property
- `BulkImportResult` counters: added / skipped / overwritten / renamed / errors

### v1.2.0 — Wave 5–6
- 39 new tests: `test_health`, `test_prefix_detect`, `test_integrity`, 13 Hypothesis properties
- Shared `conftest.py` with session-scoped Argon2id fixtures
- Full MkDocs documentation site with Material theme + mkdocstrings
- `pyproject.toml` migrated to Hatchling / PEP 621 with full `ruff`, `mypy`, `bandit`, `hypothesis` config
- Badges: version, tests passing

### v1.1.0 — Wave 3–4
- `wallet health` — per-entry health scores + rotation recommendations
- `wallet audit` — structured audit log viewer with filtering
- `wallet verify` — structural + HMAC integrity check
- `wallet wipe` — panic wipe with multi-step confirmation
- `wallet tag`, `wallet search`, `wallet rotate` — key lifecycle commands
- Desktop GUI (CustomTkinter) — Keys / Health / Settings tabs
- TUI rewrite (Textual) — keyboard-driven full-screen interface
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
