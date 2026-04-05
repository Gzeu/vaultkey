# 🔐 VaultKey

**Secure, fast, offline API Key Wallet** — AES-256-GCM encrypted, Argon2id key derivation, CLI + TUI + GUI.

## Security Architecture

- **AES-256-GCM** encryption for the entire wallet and per-entry sub-keys
- **Argon2id** (64MB RAM, 3 iterations) for master password key derivation
- **HKDF-SHA256** per-entry sub-key derivation (defense-in-depth)
- **AAD binding** — wallet is cryptographically bound to its file path
- **SecureMemory** — sensitive data zeroed in RAM via `ctypes.memset` on cleanup
- **Auto-lock** after 15 minutes of inactivity
- **Clipboard auto-clear** after 30 seconds
- **Atomic writes** — no partial corruption on power loss
- **Audit log** — append-only, zero sensitive data logged
- **Anti-brute-force** — exponential delay + 60s hard lockout after 5 failures

## Installation

```bash
# With Poetry
poetry install

# Or with pip
pip install -e .
```

## Quick Start

```bash
# 1. Initialize your wallet
wallet init

# 2. Unlock (enter master password once per session)
wallet unlock

# 3. Add your first API key
wallet add --name "OpenAI Production" --tags "ai,production"

# 4. List all keys
wallet list

# 5. Copy a key to clipboard (clears in 30s)
wallet get openai-production

# 6. Show masked key value
wallet get openai-production --show

# 7. Export as shell env var
wallet get openai-production --env

# 8. View details (no key value shown)
wallet info openai-production

# 9. Rotate a key
wallet rotate openai-production

# 10. Delete a key
wallet delete openai-production

# 11. Launch TUI
wallet tui

# 12. Launch GUI
wallet gui

# 13. Lock wallet
wallet lock
```

## All CLI Commands

| Command | Description |
|---|---|
| `wallet init` | Create new wallet |
| `wallet unlock` | Unlock with master password |
| `wallet lock` | Lock and clear session |
| `wallet status` | Show wallet status |
| `wallet add` | Add new API key (interactive or flags) |
| `wallet list` | List all keys (no values) |
| `wallet get <name>` | Copy to clipboard |
| `wallet get <name> --show` | Show masked value |
| `wallet get <name> --env` | Print as `export VAR=value` |
| `wallet get <name> --raw` | Raw stdout (for piping) |
| `wallet info <name>` | Show full metadata |
| `wallet delete <name>` | Delete with double confirm |
| `wallet rotate <name>` | Replace key value |
| `wallet change-password` | Re-encrypt with new password |
| `wallet export` | Export encrypted backup |
| `wallet import <file>` | Import from backup |
| `wallet tui` | Full-screen TUI |
| `wallet gui` | Graphical GUI |

## Project Structure

```
vaultkey/
├── wallet/
│   ├── core/
│   │   ├── crypto.py      # AES-GCM, HKDF, SecureMemory
│   │   ├── kdf.py         # Argon2id KDF
│   │   ├── storage.py     # Binary format, atomic write, backup
│   │   └── session.py     # SessionManager, timeout, brute-force
│   ├── models/
│   │   ├── wallet.py      # Pydantic v2 models
│   │   └── config.py      # Non-secret settings
│   ├── ui/
│   │   ├── cli.py         # Typer CLI (all commands)
│   │   ├── tui.py         # Textual TUI
│   │   └── gui.py         # CustomTkinter GUI
│   └── utils/
│       ├── audit.py       # Append-only audit logger
│       ├── clipboard.py   # Clipboard + auto-clear
│       ├── prefix_detect.py # API key prefix auto-detection
│       └── validators.py  # Input validation
├── tests/
│   ├── test_crypto.py
│   ├── test_kdf.py
│   ├── test_storage.py
│   └── test_session.py
├── backups/           # Auto-created, auto-pruned
├── wallet.enc         # ⚠️  NOT committed (in .gitignore)
├── audit.log          # ⚠️  NOT committed
├── pyproject.toml
├── .env.example
└── .gitignore
```

## Running Tests

```bash
poetry run pytest
# With coverage report:
poetry run pytest --cov=wallet/core --cov-report=html
```

## Security Notes

- `wallet.enc` and `audit.log` are in `.gitignore` — **never commit them**
- Run `chmod 600 wallet.enc` to restrict file permissions
- Use a strong master password (min 16 chars recommended)
- Rotate API keys regularly (use `wallet rotate <name>`)
- Export backups with a **different** strong password
