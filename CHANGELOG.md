# Changelog

All notable changes to VaultKey are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

---

## [1.6.0] — Wave 10 cleanup (2026-04-06)

### Changed
- `pyproject.toml`: version bumped `1.5.0` → `1.6.0`; added `httpx>=0.27` runtime dependency (webhook HTTP client).
- `wallet/__init__.py`: `__version__` bumped to `1.6.0`.

### Removed
- `wallet/ui/cli_wave9.py`: staging file deleted — all Wave 9 commands (`profile`, `share`, `webhook`) are fully integrated into `cli.py`.

---

## [1.5.0] — Wave 8 + Wave 9 (2026-04-06)

### Added
- **Wave 8 — `rotate-all`, `watch-expiry`, `completion`**:
  - `wallet/core/rotate.py`: `rotate_all()` with `--tag` scope + `--dry-run` preview.
  - `wallet/utils/expiry_checker.py`: `ExpiryChecker` daemon thread with `on_expired` / `on_warning` callbacks.
  - `wallet/utils/shell_completion.py`: live completers for entry names, services, tags.
  - CLI: `rotate-all`, `watch-expiry --interval`, `completion` commands.
- **Wave 9 — profiles, share, webhook**:
  - `wallet/utils/vault_profiles.py`: `VaultProfiles` manager — `create`, `switch`, `list`, `delete` isolated wallets per profile.
  - `wallet/utils/share_token.py`: `ShareToken` — encrypted one-time share tokens with expiry and revocation.
  - `wallet/utils/webhook.py`: `WebhookManager` — add/list/remove/test webhooks; `httpx` POST with HMAC-SHA256 signature.
  - CLI sub-apps: `wallet profile` (create/switch/list/delete/current) and `wallet webhook` (add/list/remove/test).
  - CLI: `wallet share <name>`, `wallet share-receive <token>`, `wallet share-list`, `wallet share-revoke <id>`.
- **Tests**:
  - `tests/test_vault_profiles.py`: 12 tests (VP1–VP12).
  - `tests/test_share_token.py`: 10 tests (ST1–ST10).
  - `tests/test_webhook.py`: 10 tests (WH1–WH10).
- **GUI** (`wallet/ui/gui.py`): Health tab + Settings tab completed; clipboard clear timer integrated.
- **TUI** (`wallet/ui/tui.py`): Wave 9 full feature parity — all CLI commands reachable from keyboard.

### Changed
- `wallet/__init__.py`: `__version__` bumped `1.4.0` → `1.5.0`.
- `pyproject.toml`: version bumped `1.4.0` → `1.5.0`.
- `README.md`: full rewrite to v1.5.0 — CLI reference, security table, binary format schema, testing treelist, changelog.

---

## [1.4.0] — Wave 7 (2026-04-06)

### Added
- **`wallet/core/rotate.py`** — Bulk key rotation engine:
  - `rotate_single(payload, master_key, entry_id, new_value)` — re-criptează o intrare cu nonce proaspăt.
  - `rotate_all(payload, master_key, storage) -> RotateReport` — re-criptează TOATE intrările cu nonce-uri noi, salvează wallet atomic (numai dacă 0 erori).
  - `RotateReport` / `RotateResult` — dataclasses cu `succeeded`, `failed`, `total`, `finished_at`.
  - Audit log: `KEY_ROTATED`, `ROTATE_ALL` (OK / PARTIAL_FAIL).
- **`wallet/utils/shell_completion.py`** — Completare dinamică shell pentru CLI:
  - `entry_names_completer(incomplete)` — completare live după numele cheilor din wallet-ul deblocat.
  - `service_names_completer(incomplete)` — servicii unice.
  - `tag_completer(incomplete)` — tag-uri unice.
  - Returnează `[]` silențios dacă wallet-ul e blocat (nici o excepție în shell).
- **`wallet/utils/expiry_checker.py`** — rewrite complet:
  - `check_expiry(payload, warn_days) -> ExpiryReport` — scanare sincronă cu categorii expired / warning / ok / no_expiry.
  - `ExpiryChecker` — daemon thread cu `start()` / `stop()` / `check_now()`, callbacks `on_expired` + `on_warning`.
  - `watch_expiry()` — blocking loop CLI-friendly cu Ctrl+C.
  - `ExpiryReport.summary()` — string cu contoarele tuturor categoriilor.
- **`wallet/ui/tui_import.py`** — `ImportScreen(ModalScreen)` pentru TUI.
- **`tests/test_rotate.py`** — 10 teste (R1–R10).
- **`tests/test_expiry_checker.py`** — 12 teste (E1–E12).
- **`tests/test_shell_completion.py`** — 8 teste (SC1–SC8).

### Changed
- `wallet/__init__.py`: `__version__` bumped `1.3.0` → `1.4.0`.
- `pyproject.toml`: `version` bumped `1.3.0` → `1.4.0`.

---

## [1.3.0] — Wave 6 (2026-04-06)

### Added
- **Complete TUI rewrite** (`wallet/ui/tui.py`) — 950 → 1,400 LOC, full feature parity with CLI.
- Tab `⏰ Expiry` (`ExpiryPanel`): toate cheile grupate în 4 secțiuni colorate.
- `StatusPanel` cu countdown live: timer 1s cu `set_interval`.
- `KeysPanel` toolbar vizual cu butoane inline.
- `AuditPanel` upgrade: filtru live + buton Refresh.
- Keyboard bindings complete (n/e/D/Enter/c/i/g/r/L/q).

### Changed
- `wallet/__init__.py`: `__version__` bumped `1.2.0` → `1.3.0`.
- `pyproject.toml`: `version` bumped `1.2.0` → `1.3.0`.

### Fixed
- `KeysPanel.selected_entry()`: guard pentru `cursor_row >= len(filtered)`.
- `ExpiryPanel.on_mount`: try/except per-table.
- `StatusPanel._update_display`: try/except per-widget.

---

## [1.2.0] — Wave 5 (2026-04-05)

### Added
- `tests/conftest.py`: Shared fixtures for entire test suite.
- `tests/test_hypothesis.py`: 13 property-based tests.
- `tests/test_health.py`: 12 tests.
- `tests/test_prefix_detect.py`: 8 tests.
- `tests/test_integrity.py`: 6 tests.
- `pyproject.toml` complete rewrite: migrated from Poetry to Hatchling.
- MkDocs documentation site (`docs/`).

### Changed
- `wallet/__init__.py`: version bumped to 1.2.0.

---

## [1.1.0] — Wave 3 + Wave 4 (2026-04-05)

### Added
- CLI: `health`, `audit`, `verify`, `wipe`, `tag`, `search`, `export`, `import`, `change-password`, `rotate`, `tui`, `gui`.
- Textual TUI (`tui.py`): Keys, Health, Audit, Status panels.
- CustomTkinter GUI (`gui.py`): Keys, Health, Settings tabs.
- 6 test files totalling 84 tests.
- `.github/workflows/ci.yml`: 9-combination matrix + bandit.
- `SECURITY.md`, `CHANGELOG.md`.

### Fixed
- `gui.py`: `_tmp_` encrypt bug, `on_closing` lock.
- `cli.py`: `list_keys` sort fallback.

---

## [1.0.0] — Wave 1 + Wave 2 (2026-04-05)

### Added
- AES-256-GCM + Argon2id + HKDF-SHA256 + HMAC-SHA256 core.
- Atomic write, 0600 permissions, AAD path-binding, rolling backups.
- Thread-safe `SessionManager` with `ctypes.memset` zeroing and brute-force protection.
- CLI: `init`, `unlock`, `lock`, `status`, `add`, `list`, `get`, `delete`, `info`, `rotate`.
- `WalletPayload` v1, `APIKeyEntry` with health properties.
- `audit.py`, `clipboard.py`, `prefix_detect.py`, `validators.py`.

### Security fixes (v1.1 patch)
- FIX #1 (CRITICAL): `time.sleep()` outside `_op_lock`.
- FIX #2 (CRITICAL): UUID before first encrypt in `add`.
- FIX #3 (MODERATE): `LOCKOUT_RESET` audit event.
- FIX #4 (MODERATE): `datetime` import consolidated.
- FIX #5 (MINOR): HMAC manifest on every `storage.save()`.
- FIX #6 (MINOR): Explicit HKDF domain-separation salt.
