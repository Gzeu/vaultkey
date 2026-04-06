# CLI Reference

VaultKey exposes a single `wallet` command with subcommands.

```bash
wallet [OPTIONS] COMMAND [ARGS]...
```

## Global Options

| Option | Description |
|---|---|
| `--version` | Show version and exit |
| `--help` | Show help message and exit |

---

## Lifecycle Commands

### `wallet init`

Create a new encrypted wallet.

```bash
wallet init [--force]
```

| Option | Description |
|---|---|
| `--force` | Overwrite existing wallet (creates backup first) |

Prompts for master password twice (confirmation). Generates fresh Argon2id KDF parameters and HMAC salt.

**Example:**
```bash
$ wallet init
🔐 Create master password: ••••••••••••
✓ Confirm password: ••••••••••••
✅ Wallet created at ~/.local/share/vaultkey/wallet.enc
   KDF: Argon2id  memory=64MB  iterations=3  parallelism=4
```

---

### `wallet unlock`

Derive and cache the session key from the master password.

```bash
wallet unlock
```

The key lives in memory only and is zeroed after `VAULTKEY_SESSION_TIMEOUT` minutes of inactivity.

---

### `wallet lock`

Immediately zero the session key from memory.

```bash
wallet lock
```

---

### `wallet status`

Show wallet and session status.

```bash
wallet status
```

**Output:**
```
🔐 VaultKey v1.2.0
   Wallet : ~/.local/share/vaultkey/wallet.enc  (48 KB)
   Session: UNLOCKED  —  auto-locks in 12 min
   Keys   : 7 total  (6 active, 1 expiring)
   Health : B  (82/100)
   Backups: 3 available
```

---

## Key Management Commands

### `wallet add`

Add a new API key entry.

```bash
wallet add [OPTIONS]
```

| Option | Description |
|---|---|
| `--name TEXT` | Key name (required, unique) |
| `--service TEXT` | Service identifier (`openai`, `anthropic`, ...) |
| `--tags TEXT` | Comma-separated tags |
| `--description TEXT` | Optional note |
| `--expires DATE` | Expiry date in `YYYY-MM-DD` format |

The key *value* is always prompted interactively (never passed as a CLI argument to avoid shell history exposure).

**Example:**
```bash
wallet add --name "OpenAI Production" --tags "ai,prod" --expires 2027-01-01
API key value: ••••••••••••••••••
✅ Key 'OpenAI Production' added (service: openai)
```

---

### `wallet get`

Copy a key's value to clipboard.

```bash
wallet get NAME
```

The decrypted value is sent to clipboard and auto-cleared after `VAULTKEY_CLIPBOARD_CLEAR` seconds (default: 30).

**Example:**
```bash
$ wallet get "OpenAI Production"
✅ Copied to clipboard  —  clears in 30 s
```

---

### `wallet list`

List all stored keys (values never shown).

```bash
wallet list [--service TEXT] [--tag TEXT] [--status {active,expiring,expired,revoked}]
```

| Option | Description |
|---|---|
| `--service` | Filter by service |
| `--tag` | Filter by tag |
| `--status` | Filter by status |

**Example output:**
```
 NAME                   SERVICE     STATUS     HEALTH   EXPIRES
 OpenAI Production      openai      active     A 95     2027-01-01
 Anthropic Claude       anthropic   active     B 84     —
 GitHub Actions Token   github      expiring   C 61     2026-04-30
```

---

### `wallet delete`

Delete a key entry (requires typed-name confirmation).

```bash
wallet delete NAME [--force]
```

| Option | Description |
|---|---|
| `--force` | Skip confirmation prompt |

---

### `wallet rename`

Rename an existing key entry.

```bash
wallet rename OLD_NAME NEW_NAME
```

---

### `wallet rotate`

Re-encrypt an entry under a new nonce (key value unchanged).

```bash
wallet rotate NAME
```

Useful after suspecting a nonce collision or after sharing the wallet file.

---

### `wallet revoke`

Mark a key as revoked without deleting it.

```bash
wallet revoke NAME
```

---

## Security Commands

### `wallet health`

Score all keys and show per-entry health grades.

```bash
wallet health [--grade {A,B,C,D,F}] [--json]
```

| Option | Description |
|---|---|
| `--grade` | Show only keys at or below this grade |
| `--json` | Output raw JSON |

**Scoring factors:**

| Factor | Points deducted | Condition |
|---|---|---|
| No expiry set | 20 | `expires_at` is None |
| Expired | 40 | `expires_at` < today |
| Expiring within 30 days | 15 | `expires_at` < today + 30 |
| No description | 10 | `description` is empty |
| Never accessed | 5 | `access_count == 0` |
| Not rotated in 90 days | 15 | `updated_at` > 90 days ago |
| No service tag | 5 | `service == "unknown"` |

---

### `wallet expiry-check`

Show keys expiring within a look-ahead window.

```bash
wallet expiry-check [--days INT]
```

| Option | Default | Description |
|---|---|---|
| `--days` | 30 | Look-ahead window in days |

---

### `wallet change-password`

Change the master password and re-encrypt all entries.

```bash
wallet change-password
```

Generates new Argon2id KDF parameters and re-derives all per-entry subkeys.

---

### `wallet wipe`

Securely delete the wallet and all backups.

```bash
wallet wipe [--confirm TEXT]
```

Requires typing `WIPE` to confirm. Performs 3-pass overwrite before unlinking.

---

## Backup Commands

### `wallet backup`

Create a timestamped encrypted backup.

```bash
wallet backup [--output PATH]
```

---

### `wallet restore`

Restore wallet from a backup file.

```bash
wallet restore BACKUP_FILE
```

---

### `wallet bulk-import`

Import keys from `.env`, `.json`, or `.csv` file.

```bash
wallet bulk-import FILE [--on-conflict {skip,overwrite,rename}] [--dry-run]
```

| Option | Default | Description |
|---|---|---|
| `--on-conflict` | `skip` | Conflict resolution strategy |
| `--dry-run` | false | Preview without writing |

See [Bulk Import guide](../guide/bulk-import.md) for file format details.

---

## Interface Commands

### `wallet tui`

Launch the terminal UI (Textual).

```bash
wallet tui
```

---

### `wallet gui`

Launch the desktop GUI (CustomTkinter).

```bash
wallet gui
```

---

## Audit Commands

### `wallet audit`

View the audit log.

```bash
wallet audit [--last INT] [--event TEXT] [--json]
```

| Option | Default | Description |
|---|---|---|
| `--last` | 50 | Number of recent events to show |
| `--event` | (all) | Filter by event type (GET, ADD, DELETE, ...) |
| `--json` | false | Output raw JSON Lines |

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error (wrong password, wallet not found, etc.) |
| `2` | Integrity check failed |
| `3` | Session locked |
| `130` | Interrupted (Ctrl+C) |
