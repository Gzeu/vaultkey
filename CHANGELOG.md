# Changelog

All notable changes to VaultKey are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — Wave 4

### Added
- **`gui.py` full rewrite** (Wave 4): 3-tab CustomTkinter GUI (Keys, Health, Settings).
  - `KeysTab`: live search, `KeyCard` with Copy/Info/Delete, `AddKeyDialog` (UUID-first encrypt, no `_tmp_` bug).
  - `HealthTab`: per-entry health scores + overall grade with color coding.
  - `SettingsTab`: change password (re-encrypt all entries), export backup, audit log viewer.
  - `InfoDialog`: full metadata + health analysis per entry.
  - `LoginWindow`: attempt counter, Show/Hide toggle, wrong-password feedback.
  - `on_closing` handler: session is locked on window close (not just on explicit Lock button).
- **`tests/test_session.py`**: 14 tests covering singleton, lifecycle, brute-force protection, lockout reset, 20-thread concurrent `get_key`, lock-during-concurrent-access deadlock check.
- **`tests/test_audit.py`**: 12 tests covering write format, permissions, 100-thread concurrent write, rotation trigger, `event_filter`, `status_filter`, `last_n`, corrupt-line skip.
- **`tests/test_validators.py`**: 20 tests covering `validate_key_name`, `validate_api_key_value`, `parse_expiry_date`, `validate_tag_list` with boundary and error cases.
- **`.github/workflows/ci.yml`**: GitHub Actions CI matrix (Ubuntu/Mac/Windows × Python 3.11/3.12/3.13): lint (ruff), type check (mypy), pytest with coverage, codecov upload, bandit security scan.
- **`SECURITY.md`**: Full security policy with threat model, cryptographic primitive table, dependency audit instructions.
- **`CHANGELOG.md`**: This file.

### Fixed
- `gui.py`: `AddKeyDialog._on_add_key` no longer encrypts with `'_tmp_'` sub-key then re-encrypts. UUID generated upfront — single `encrypt_entry_value` call (mirrors CLI FIX #2 from v1.1).
- `gui.py`: `MainWindow.on_closing` added — session is locked when the OS close button is clicked.
- `gui.py`: Failed unlock attempts now show attempt counter from `session.info['failed_attempts']`.

---

## [1.1.0] — Wave 3

### Added
- CLI commands: `health`, `audit`, `verify`, `wipe`, `tag`, `search`, `export`, `import`, `change-password`, `rotate`, `tui`, `gui`.
- **Full-screen Textual TUI** (`tui.py`): Keys, Health, Audit, Status tabs. Keybindings: `Enter` copy, `i` info, `D` delete, `L` lock, `q` quit.
- `tests/test_storage.py`: 12 end-to-end storage roundtrip tests.
- `tests/test_kdf.py`: 10 KDF and password-hashing tests.
- `tests/test_crypto.py`: 16 AES-GCM, HKDF, `SecureMemory`, AAD tests.
- `validators.py`: `validate_tag_list()` added; `validate_api_key_value` strips whitespace margins.

### Fixed
- `cli.py`: All commands consistently emit `audit_log()` events.
- `cli.py` `list_keys`: Sort by `expires` now uses `datetime.max` fallback for entries without expiry (no `AttributeError`).

---

## [1.0.0] — Wave 1 + Wave 2 (Initial Release)

### Added
- **Core cryptography**: AES-256-GCM + Argon2id + HKDF-SHA256 + HMAC-SHA256 integrity manifest.
- **Wallet storage**: Atomic write, 0600 permissions, AAD path-binding, rolling backups.
- **Session management**: Thread-safe singleton, `ctypes.memset` zeroing, exponential backoff brute-force protection, auto-lock timer.
- **CLI**: `init`, `unlock`, `lock`, `status`, `add`, `list`, `get`, `delete`, `info`, `rotate`.
- **Models**: `WalletPayload` v1, `APIKeyEntry` with health status properties.
- **Utils**: `audit.py`, `clipboard.py`, `prefix_detect.py` (16 services), `validators.py`.

### Security Fixes (v1.1 patch, included in v1.0.0 release)
- **FIX #1 (CRITICAL)**: `time.sleep()` moved outside `_op_lock` in `session.py` (deadlock prevention).
- **FIX #2 (CRITICAL)**: Entry UUID generated before first `encrypt_entry_value` call in `cli.py add` (no `_tmp_` sub-key waste).
- **FIX #3 (MODERATE)**: `LOCKOUT_RESET` audit event emitted when hard-lockout window expires.
- **FIX #4 (MODERATE)**: `datetime` import consolidated at module level in `cli.py`.
- **FIX #5 (MINOR)**: HMAC integrity manifest written on every `storage.save()`.
- **FIX #6 (MINOR)**: Explicit HKDF domain-separation salt (`DOMAIN_SALT`) per RFC 5869 §3.1.
