# Quick Start

## 1. Initialize

```bash
wallet init
```

Creates `wallet.enc` with your chosen master password.
Uses **Argon2id** with 64 MB memory cost — takes ~200ms deliberately.

## 2. Unlock

```bash
wallet unlock
```

Derives the session key and stores it in memory.
Auto-locks after **15 minutes** of inactivity (configurable).

## 3. Add keys

```bash
# Interactive prompts
wallet add

# Fully specified
wallet add --name "Anthropic Prod" --service anthropic --tags prod,ml --expires 2027-06-01
```

## 4. Copy to clipboard

```bash
wallet get "Anthropic Prod"
# ✓ Copied to clipboard. Clears in 30s.
```

## 5. List keys

```bash
wallet list                          # all keys
wallet list --tag prod               # filter by tag
wallet list --sort expires           # sort by expiry
wallet list ai                       # fuzzy search
```

## 6. Health check

```bash
wallet health          # show only problem keys
wallet health --all    # show all with scores
```

## 7. Rotate a key

```bash
wallet rotate "Anthropic Prod"
# Prompts for new value, re-encrypts in-place
```

## 8. Emergency wipe

```bash
wallet wipe
# Requires: type WIPE → type CONFIRM
# Overwrites and deletes wallet.enc + all backups
```
