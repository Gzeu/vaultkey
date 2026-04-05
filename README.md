# VaultKey 🔐

> Ultra-secure local API key wallet — AES-256-GCM · Argon2id · HMAC Integrity · Zero cloud dependency

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Security](https://img.shields.io/badge/encryption-AES--256--GCM-red)](https://en.wikipedia.org/wiki/AES-GCM)

## Overview

VaultKey stores your API keys locally in an encrypted binary file (`wallet.enc`).  
No cloud sync. No telemetry. No vendor lock-in. Your keys never leave your machine.

## Security Architecture

| Layer | Technology | Parameters |
|---|---|---|
| Key Derivation | Argon2id | 64MB RAM · 3 iterations · 4 threads |
| Encryption | AES-256-GCM | 96-bit nonce · 128-bit AEAD tag |
| Per-entry subkeys | HKDF-SHA256 | Domain salt + entry UUID info |
| Password verification | Argon2id hash | Separate salt, stored encrypted |
| Integrity manifest | HMAC-SHA256 | Over all entry IDs + ciphertexts |
| AAD binding | SHA-256(wallet_path) | Prevents file relocation attacks |
| Memory security | ctypes.memset | Key zeroed on lock/timeout |
| File permissions | chmod 600 | User-only read/write |
| Atomic writes | temp + os.replace() | No partial writes on crash |
| Audit log | JSON-Lines | Per-event PID + user + timestamp |

## Quick Start

```bash
# Install
pip install vaultkey  # or: poetry install

# Initialize wallet
wallet init

# Unlock session (15-min auto-lock)
wallet unlock

# Add an API key
wallet add --name "OpenAI Production" --tags "ai,production"

# Copy to clipboard (auto-clears after 30s)
wallet get "OpenAI Production"

# Interactive TUI
wallet tui
```

## CLI Commands

| Command | Description |
|---|---|
| `wallet init` | Initialize a new encrypted wallet |
| `wallet unlock` | Unlock the wallet (derive session key) |
| `wallet lock` | Lock and zero the session key |
| `wallet status` | Show session status and key count |
| `wallet add` | Add a new API key |
| `wallet get <name>` | Copy key to clipboard |
| `wallet get <name> --show` | Show masked key value |
| `wallet get <name> --raw` | Print raw value (for piping) |
| `wallet get <name> --env` | Print as `export ENV_VAR=value` |
| `wallet list` | List all keys (no values) |
| `wallet list --tag ai` | Filter by tag |
| `wallet list --sort expires` | Sort by expiry |
| `wallet delete <name>` | Delete with double confirmation |
| `wallet rotate <name>` | Replace key value |
| `wallet info <name>` | Show detailed metadata |
| `wallet health` | Wallet-wide key health report |
| `wallet audit` | View recent audit log events |
| `wallet verify` | Run integrity check on wallet |
| `wallet change-password` | Re-key entire wallet |
| `wallet export` | Export encrypted backup |
| `wallet import <file>` | Import from backup |
| `wallet wipe` | Emergency secure destruction |
| `wallet tui` | Launch interactive TUI |
| `wallet gui` | Launch GUI |

## Security Guarantees

- **Keys never touch disk unencrypted** — encrypted before `save()` is called
- **Per-entry subkeys** — compromise of one entry does not leak others
- **Brute-force protection** — exponential backoff (1s → 2s → 4s → 60s hard lockout)
- **Anti-relocation** — AAD binding prevents moving `wallet.enc` to another path
- **Integrity detection** — HMAC manifest detects silent bit-rot or tampering
- **Audit trail** — every operation logged to `audit.log` (JSON-Lines, chmod 600)
- **Clipboard hygiene** — auto-clear after 30 seconds
- **Panic wipe** — 3-pass DoD overwrite of wallet + all backups

## File Layout

```
~/.local/share/vaultkey/
├── wallet.enc      # Encrypted wallet (chmod 600)
├── audit.log       # JSON-Lines audit trail (chmod 600)
└── backups/
    ├── wallet_20250101_120000.enc
    └── ...
```

## Configuration

Set via environment variables or `.env` file:

```bash
VAULTKEY_WALLET_PATH=/secure/volume/wallet.enc
VAULTKEY_SESSION_TIMEOUT_MINUTES=10
VAULTKEY_CLIPBOARD_CLEAR_SECONDS=15
VAULTKEY_MAX_BACKUPS=30
VAULTKEY_ENABLE_INTEGRITY_CHECK=true
```

## Development

```bash
poetry install
poetry run pytest
poetry run wallet --help
```
