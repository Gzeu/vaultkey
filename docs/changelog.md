# Changelog

All notable changes to VaultKey are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

---

## [1.2.0] — 2026-04-06

### Added (Wave 7)
- **Expiry tab** in GUI — color-coded urgency levels (expired / critical / warning / info)
- **Bulk Import** panel in GUI Settings tab with dry-run and conflict strategy
- **Rename** button on key cards (GUI + TUI + CLI)
- `wallet bulk-import` CLI command supporting `.env`, `.json`, `.csv`
- `wallet expiry-check --days N` CLI command
- `wallet/utils/bulk_import.py` — parser + importer with conflict resolution
- `wallet/utils/expiry_checker.py` — expiry analysis with urgency levels
- `WalletPayload.rename_entry()` model method
- Full MkDocs documentation site with 12 content pages

### Changed
- GUI `MainWindow._on_data_changed()` now rebuilds both Expiry and Health tabs after any mutation
- `AddKeyDialog` generates UUID before first `encrypt_entry_value` call (fix from original)

### Fixed
- `RenameDialog` error path now shows user-facing error dialog instead of raising unhandled exception
- Duplicate `install.md` / `installation.md` unified into single `install.md`

---

## [1.1.0] — 2026-03-15

### Added (Wave 6)
- TUI built with Textual — full keyboard navigation
- `wallet/utils/prefix_detect.py` — auto-detect service from key prefix
- `wallet/utils/validators.py` — name and value validation
- `wallet/utils/clipboard.py` — clipboard copy with auto-clear countdown
- Health tab in GUI with per-entry breakdown
- `wallet audit` CLI command with `--last`, `--event`, `--json` filters
- HMAC-SHA256 integrity manifest (`wallet/core/integrity.py`)
- `wallet wipe` command with 3-pass overwrite
- GitHub Actions CI — test matrix (Python 3.11/3.12/3.13 × Ubuntu/macOS/Windows)
- Codecov coverage reporting
- Bandit security scan in CI

### Changed
- `WalletStorage.save()` now creates auto-backup before every write
- Session auto-lock timer resets on every key access
- `wallet health` output includes grade color coding in terminal

### Fixed
- `os.replace()` atomic write was not fsyncing temp file on Linux — fixed
- Argon2id parameters were not serialized to wallet header on first init — fixed

---

## [1.0.0] — 2026-02-01

### Added (Waves 1–5)
- `wallet init` — create encrypted wallet with Argon2id KDF
- `wallet unlock` / `wallet lock` — session management
- `wallet add` / `wallet get` / `wallet list` / `wallet delete` — key CRUD
- `wallet rotate` / `wallet revoke` — key lifecycle
- `wallet change-password` — re-encrypt all entries under new key
- `wallet backup` / `wallet restore` — backup management
- `wallet status` — wallet + session overview
- AES-256-GCM per-entry encryption with HKDF subkey isolation
- Per-entry AAD binding to wallet file path (relocation attack prevention)
- `SecureBytes` session key wrapper with `ctypes.memset` zeroing
- Auto-lock via `threading.Timer`
- Brute-force protection: exponential backoff + 60 s lockout
- Audit log (JSON-Lines, `chmod 600`, atomic append)
- Health scoring engine (0–100, grades A–F)
- GUI (CustomTkinter) — Keys, Health, Settings tabs
- `wallet/models/wallet.py` — `APIKeyEntry`, `WalletPayload` dataclasses
- `wallet/models/config.py` — `WalletConfig` with env-var overrides
- `pyproject.toml` with `[dev]` extras: pytest, ruff, mypy, bandit, mkdocs-material
- MIT License
- SECURITY.md vulnerability disclosure policy
- CONTRIBUTING.md contributor guide

---

## Unreleased

### Planned
- PyPI publication (`pip install vaultkey`)
- SSH key support (Wave 9)
- Secret sharing / team vaults (Wave 10)
- Browser extension for auto-fill (Wave 11)
