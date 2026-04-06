# Threat Model

VaultKey's threat model defines which adversaries and attack vectors the system is designed to resist, and which are explicitly out of scope.

## In-Scope Threats

### T1 — Disk Theft / File Exfiltration

**Attack:** Adversary obtains a copy of `wallet.enc`.

**Mitigation:**
- `wallet.enc` is an AES-256-GCM ciphertext. The plaintext is never written to disk.
- The decryption key is derived via Argon2id (64 MB memory, 3 iterations) from the master password. Without the password, brute-force is computationally infeasible on current hardware.
- Each entry uses its own HKDF-derived subkey, so compromise of one entry does not help decrypt others.

**Residual risk:** Weak master passwords. Mitigated by minimum-length enforcement (8 chars) and Argon2id cost.

---

### T2 — File Relocation / Swap Attack

**Attack:** Adversary moves `wallet.enc` to a different path and tricks VaultKey into decrypting a different wallet under a known password.

**Mitigation:**
- Each entry's AES-256-GCM AAD (Additional Authenticated Data) includes `SHA-256(wallet_path)`. Decrypting at a different path produces an authentication tag mismatch → `InvalidTag` exception.

---

### T3 — Silent File Tampering

**Attack:** Adversary modifies bytes in `wallet.enc` without knowing the master password (bit-flip, partial overwrite).

**Mitigation:**
- AES-256-GCM's 128-bit authentication tag detects any modification to ciphertext or AAD.
- A HMAC-SHA256 integrity manifest covers all entry UUIDs and ciphertexts in sorted order. Any structural change (added/removed/reordered entry) is detected on load.

---

### T4 — Clipboard Sniffing

**Attack:** Malicious process reads clipboard contents after `wallet get`.

**Mitigation:**
- Clipboard is automatically cleared after `VAULTKEY_CLIPBOARD_CLEAR` seconds (default: 30).
- A countdown is displayed so the user knows the window.
- The clear is best-effort; some clipboard managers cache history. Users in high-security environments should disable clipboard history.

---

### T5 — Brute-Force Login

**Attack:** Adversary with local access attempts many master passwords via the CLI.

**Mitigation:**
- Failed attempts are counted per session.
- After 5 failures, a 60-second lockout is enforced.
- Argon2id adds ~300 ms per attempt regardless of lockout.
- There is no remote attack surface; the wallet is local-only.

---

### T6 — Memory Dump

**Attack:** Adversary dumps process memory while VaultKey holds the session key.

**Mitigation:**
- The session key is stored in a `SecureBytes` wrapper that calls `ctypes.memset(0)` on cleanup, bypassing Python's garbage collector.
- `SessionManager.lock()` zeros the key immediately.
- Auto-lock timer zeros the key after inactivity.

**Residual risk:** Python's GC may copy objects before zeroing occurs. `SecureBytes` minimizes the window but cannot guarantee zero copies.

---

### T7 — Partial Write / Power Loss

**Attack:** Process is killed mid-write, leaving a corrupted wallet file.

**Mitigation:**
- All writes use `os.replace()` (atomic rename): a new temp file is written and fsynced before replacing the original.
- If the process dies before `os.replace()`, the original file is untouched.

---

### T8 — Unauthorized File Copying

**Attack:** Unprivileged process reads `wallet.enc` or `audit.log`.

**Mitigation:**
- Both files are set to `chmod 600` (owner read/write only) on creation.
- On Windows, ACLs restrict access to the creating user.

---

### T9 — Shell History Exposure

**Attack:** API key value appears in shell history via a command-line argument.

**Mitigation:**
- Key values are **never** accepted as CLI arguments. All key value inputs use interactive prompts (`getpass`-style), which do not appear in shell history.

---

### T10 — Backup Exfiltration

**Attack:** Adversary obtains a backup `.enc` file.

**Mitigation:**
- Backup files use the same AES-256-GCM + Argon2id scheme.
- Export prompts for a separate export password, so a backup has different credentials from the live wallet.

---

## Out-of-Scope Threats

| Threat | Reason |
|---|---|
| **Kernel-level keylogger** | VaultKey cannot defend against a compromised OS kernel |
| **Root / admin access** | `chmod 600` does not protect against root |
| **Side-channel attacks** (timing, cache) | Not mitigated at the application layer |
| **Screen capture / shoulder surfing** | Social / physical threat |
| **Compromised Python interpreter** | Supply-chain threat outside project scope |
| **Hardware attacks** (cold boot, DMA) | Physical security is the user's responsibility |
| **Clipboard history managers** | Third-party software; auto-clear is best-effort |

---

## Security Boundaries

```
 ┌─────────────────────────────────────────────────────┐
 │                   TRUST BOUNDARY                     │
 │                                                     │
 │  VaultKey process                                   │
 │    ├── Argon2id KDF (password → master key)        │
 │    ├── HKDF (master key → per-entry subkeys)       │
 │    ├── AES-256-GCM encrypt/decrypt                 │
 │    ├── HMAC-SHA256 integrity check                 │
 │    └── SecureBytes session key (ctypes zeroing)    │
 │                                                     │
 │  Protected at rest: wallet.enc  (AES-256-GCM)      │
 │  Protected in transit: N/A (local-only)            │
 │  Protected in memory: SecureBytes + auto-lock      │
 └─────────────────────────────────────────────────────┘
         │
         │  (untrusted)
         ▼
  Filesystem / OS / clipboard / screen
```

---

## Reporting Vulnerabilities

See [SECURITY.md](https://github.com/Gzeu/vaultkey/blob/main/SECURITY.md) for the vulnerability disclosure process.
