# TOTP / 2FA Integration

VaultKey v2.0 adds native TOTP (Time-based One-Time Password) support, allowing you to store and generate 2FA codes alongside your API keys — all encrypted with the same AES-256-GCM + Argon2id pipeline.

## Overview

```
TOTP Entry
├── name: "GitHub 2FA"
├── account: "user@example.com"
├── issuer: "GitHub"
├── totp_secret: [AES-256-GCM encrypted]
├── scratch_codes: [8x SHA-256 hashed backup codes]
└── tags: ["github", "work"]
```

## CLI Usage

```bash
# Add a TOTP entry (interactive)
wallet totp add "GitHub 2FA" --account user@example.com --issuer GitHub

# From QR URI (exported from authenticator app)
wallet totp add "GitHub 2FA" --uri "otpauth://totp/GitHub:user@example.com?secret=JBSWY3DP..."

# Get current code
wallet totp code "GitHub 2FA"
# Output: 482 916  (expires in 18s)

# Copy to clipboard (auto-clears after 30s)
wallet totp copy "GitHub 2FA"

# List all TOTP entries
wallet totp list

# Show QR URI for re-scanning
wallet totp qr "GitHub 2FA"

# Regenerate scratch codes
wallet totp scratch-regen "GitHub 2FA"

# Delete
wallet totp delete "GitHub 2FA"
```

## TUI Usage

In the TUI (`wallet tui`), the **2FA** tab shows all TOTP entries with:
- Live countdown timer (updates every second)
- One-click copy to clipboard
- Color-coded urgency (green → yellow → red as code expires)

## Security Design

### Storage

TOTP secrets are stored encrypted with the same pipeline as API keys:

```
TOTP secret (plaintext)
    ↓
HKDF-SHA256(master_key, info=b"totp:<entry_id>")
    ↓  
 AES-256-GCM encrypt
    ↓
{nonce_hex, cipher_hex}  ← stored in wallet.enc
```

The TOTP secret never touches disk in plaintext.

### Scratch Codes

Backup codes are **8 characters each** (Crockford base32 charset), **SHA-256 hashed** before storage:

- Plaintext shown **once** at generation time
- Never stored in plaintext (not even in memory after display)
- Constant-time comparison (`hmac.compare_digest`) prevents timing attacks
- One-time use: consumed codes are permanently invalidated
- Warning shown when fewer than 3 codes remain

### Time Window

Verification accepts codes from `±1` time step (30-second tolerance) to handle clock skew between devices. This is the same tolerance used by Google, GitHub, and all major TOTP implementations.

## Compatible Authenticator Apps

VaultKey TOTP is compatible with all RFC 6238 apps:

| App | Platform | Notes |
|-----|----------|-------|
| Google Authenticator | iOS/Android | Standard SHA1/30s |
| Authy | iOS/Android/Desktop | Supports backup |
| 1Password | All | Built-in TOTP |
| Bitwarden | All | Built-in TOTP |
| Microsoft Authenticator | iOS/Android | Enterprise-ready |
| Aegis | Android | Open source |
| Raivo OTP | iOS | Open source |

## Import from Authenticator Apps

```bash
# From Google Authenticator export (QR URI)
wallet totp import --uri "otpauth://totp/..."

# From Aegis JSON backup
wallet totp import --aegis-json /path/to/aegis-backup.json

# From 2FAS backup
wallet totp import --2fas /path/to/2fas-backup.2fas
```

## Development API

```python
from wallet.core.totp import TOTPEngine, ScratchCodeManager

# Generate a new secret
secret = TOTPEngine.generate_secret()  # 32-char base32

# Create engine
engine = TOTPEngine(secret=secret, issuer="MyApp")

# Get current code
code = engine.now()  # e.g., "482916"

# Verify user input
if engine.verify(user_input):
    grant_access()

# Generate QR URI for authenticator app import
uri = engine.provisioning_uri("user@example.com")
# otpauth://totp/MyApp:user%40example.com?secret=...&issuer=MyApp

# Parse existing URI from another app
engine2 = TOTPEngine.from_uri("otpauth://totp/...")

# Scratch codes
manager, plaintext_codes = ScratchCodeManager.generate()
# Show plaintext_codes to user ONCE, then discard
# Store manager.to_dict() in the vault

# Recovery
if manager.verify_and_consume(user_input):
    grant_access()
    if manager.needs_scratch_regen:  # fewer than 3 left
        prompt_user_to_regenerate()
```
