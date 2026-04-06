# Configuration

VaultKey uses a layered configuration system: environment variables override built-in defaults. No configuration file is needed for basic usage.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VAULTKEY_WALLET_PATH` | `~/.local/share/vaultkey/wallet.enc` | Path to encrypted wallet file |
| `VAULTKEY_BACKUP_DIR` | `~/.local/share/vaultkey/backups/` | Directory for auto-backups |
| `VAULTKEY_AUDIT_LOG` | `~/.local/share/vaultkey/audit.log` | Audit log file path |
| `VAULTKEY_SESSION_TIMEOUT` | `15` | Session auto-lock timeout in minutes |
| `VAULTKEY_CLIPBOARD_CLEAR` | `30` | Clipboard auto-clear delay in seconds |
| `VAULTKEY_MAX_FAILED_ATTEMPTS` | `5` | Failed login attempts before lockout |
| `VAULTKEY_LOCKOUT_SECONDS` | `60` | Lockout duration after max failed attempts |
| `VAULTKEY_ARGON2_MEMORY_MB` | `64` | Argon2id memory cost (MB) |
| `VAULTKEY_ARGON2_ITERATIONS` | `3` | Argon2id iteration count |
| `VAULTKEY_ARGON2_PARALLELISM` | `4` | Argon2id parallelism factor |

## Platform Default Paths

| Platform | Wallet file | Backup dir | Audit log |
|---|---|---|---|
| **Linux** | `~/.local/share/vaultkey/wallet.enc` | `~/.local/share/vaultkey/backups/` | `~/.local/share/vaultkey/audit.log` |
| **macOS** | `~/Library/Application Support/vaultkey/wallet.enc` | same dir `/backups/` | same dir `/audit.log` |
| **Windows** | `%APPDATA%\vaultkey\wallet.enc` | `%APPDATA%\vaultkey\backups\` | `%APPDATA%\vaultkey\audit.log` |

## `.env.example`

A sample `.env.example` is included at the repo root:

```bash
# VaultKey environment configuration
# Copy to .env and adjust as needed (never commit .env)

# Wallet storage
# VAULTKEY_WALLET_PATH=/custom/path/wallet.enc
# VAULTKEY_BACKUP_DIR=/custom/path/backups

# Security tuning
# VAULTKEY_SESSION_TIMEOUT=15       # minutes
# VAULTKEY_CLIPBOARD_CLEAR=30       # seconds
# VAULTKEY_MAX_FAILED_ATTEMPTS=5
# VAULTKEY_LOCKOUT_SECONDS=60

# Argon2id KDF tuning (increase for stronger security, decrease for faster unlock)
# VAULTKEY_ARGON2_MEMORY_MB=64
# VAULTKEY_ARGON2_ITERATIONS=3
# VAULTKEY_ARGON2_PARALLELISM=4
```

## Argon2id Tuning Guide

The default parameters (64 MB, 3 iterations, 4 threads) take ~200–400 ms on modern hardware. Adjust based on your threat model:

| Use case | Memory | Iterations | Unlock time |
|---|---|---|---|
| Developer laptop (fast unlock) | 32 MB | 2 | ~100 ms |
| **Default (recommended)** | **64 MB** | **3** | **~300 ms** |
| High-security server | 128 MB | 4 | ~600 ms |
| Maximum security | 256 MB | 5 | ~1.5 s |

!!! warning
    Changing KDF parameters after wallet creation requires re-initializing the wallet with `wallet init --force`. Existing wallet files are not automatically re-encrypted.

## Session Timeout

The session key is zeroed from memory after `VAULTKEY_SESSION_TIMEOUT` minutes of inactivity. The timer resets on every key access. Set to `0` to disable auto-lock (not recommended).

```bash
# 30-minute session for extended work sessions
export VAULTKEY_SESSION_TIMEOUT=30

# Aggressive 5-minute lock for high-security environments
export VAULTKEY_SESSION_TIMEOUT=5
```

## Clipboard Auto-Clear

When you run `wallet get <name>`, the decrypted key is copied to clipboard and cleared after `VAULTKEY_CLIPBOARD_CLEAR` seconds. A countdown is shown in the terminal.

```bash
# Longer window for slow paste operations
export VAULTKEY_CLIPBOARD_CLEAR=60

# Immediate clear after copy (clipboard is wiped in ~1 s)
export VAULTKEY_CLIPBOARD_CLEAR=1
```
