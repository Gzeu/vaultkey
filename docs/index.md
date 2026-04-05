# VaultKey 🔐

**Ultra-secure local API key wallet.** Store, organize, and access your API keys without ever trusting the cloud.

---

## Why VaultKey?

- 🔐 **AES-256-GCM** encryption with **Argon2id** key derivation (OWASP recommended, 64 MB memory cost)
- 🔑 **Per-entry sub-keys** via HKDF-SHA256 — compromise one key, keep all others safe
- 🧠 **HMAC-SHA256** integrity manifest — detect any tampering before decryption
- ⏲️ **Session auto-lock** with configurable timeout and memory-safe key zeroing
- 📋 **Three interfaces**: CLI, full-screen TUI (Textual), and desktop GUI (CustomTkinter)
- 🚨 **Exponential backoff + hard lockout** against brute-force attacks
- ☁️ **100% offline** — no network calls, no telemetry, no cloud sync

---

## Quick Install

```bash
pip install vaultkey
```

Or from source:

```bash
git clone https://github.com/Gzeu/vaultkey
cd vaultkey
pip install -e .
```

---

## Quick Start

```bash
# 1. Create your wallet
wallet init

# 2. Unlock it (derives session key in memory)
wallet unlock

# 3. Add your first key
wallet add --name "OpenAI Production" --service openai

# 4. Copy to clipboard (clears automatically after 30s)
wallet get "OpenAI Production"

# 5. Check health of all keys
wallet health

# 6. Launch full-screen TUI
wallet tui
```

---

## Interfaces

=== "CLI"
    ```
    wallet list
    wallet get "My Key" --show
    wallet health --all
    wallet audit --last 20
    wallet verify
    ```

=== "TUI"
    ```bash
    wallet tui
    # Tab — switch panels
    # Enter — copy to clipboard
    # i — show info + health
    # D — delete
    # L — lock
    # q — quit
    ```

=== "GUI"
    ```bash
    wallet gui
    # Tabs: Keys | Health | Settings
    # Copy/Info/Delete buttons per entry
    # Change password with full re-encryption
    ```

---

## Security at a glance

| Layer | Technology | Standard |
|-------|-----------|----------|
| Encryption | AES-256-GCM | NIST SP 800-38D |
| Key derivation | Argon2id 64MB | RFC 9106 / OWASP |
| Sub-key derivation | HKDF-SHA256 | RFC 5869 |
| Integrity | HMAC-SHA256 | RFC 2104 |
| Nonce generation | `secrets.token_bytes` | OS /dev/urandom |

See the full [Security Architecture](security/architecture.md) and [Threat Model](security/threats.md).
