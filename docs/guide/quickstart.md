# Quickstart

Get from zero to encrypted API key storage in under 2 minutes.

## 1. Initialize a Wallet

```bash
wallet init
```

This creates `~/.local/share/vaultkey/wallet.enc` and prompts you to set a master password.  
The password is hashed with Argon2id — it is never stored in plaintext.

## 2. Unlock the Session

```bash
wallet unlock
```

Derives the session key from your master password. The key lives in memory only and is automatically zeroed after 15 minutes of inactivity (configurable).

## 3. Add a Key

```bash
wallet add --name "OpenAI Production" --tags "ai,production" --expires 2027-01-01
```

You will be prompted for the API key value. It is encrypted immediately and never written to disk in plaintext.

## 4. Copy to Clipboard

```bash
wallet get "OpenAI Production"
```

The decrypted value is sent to your clipboard and **auto-cleared after 30 seconds**.

## 5. List All Keys

```bash
wallet list
```

Keys are listed with name, service, status, and health score. Values are never shown.

## 6. Check Health

```bash
wallet health
```

Scores each key from 0–100 and assigns a grade (A–F) based on age, rotation, expiry, and description completeness.

## 7. Check Expiry

```bash
wallet expiry-check --days 30
```

Shows all keys expiring within 30 days, color-coded by urgency.

## 8. Launch the GUI

```bash
wallet gui
```

Opens the CustomTkinter desktop app with Keys, Expiry, Health, and Settings tabs.

## 9. Lock When Done

```bash
wallet lock
```

Zeroes the session key from memory immediately.
