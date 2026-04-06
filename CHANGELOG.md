# Changelog

All notable changes to VaultKey are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

---

## [1.3.0] — Wave 6 (2026-04-06)

### Added
- **Complete TUI rewrite** (`wallet/ui/tui.py`) — 950 → 1,400 LOC, full feature parity with CLI:
  - `AddKeyModal`: formular complet cu name, value (mascat), service, description, tags, expiry (YYYY-MM-DD), environment + buton **🎲 Generate** inline.
  - `EditKeyModal`: editare service, description, tags, expiry, environment + dropdown status (active / revoked / expired / deprecated).
  - `ConfirmDeleteModal`: dialog de confirmare cu text entry name înainte de ștergere destructivă.
  - `KeyDetailModal`: view complet cu toate metadatele (health score, access count, last accessed, created, expiry) + buton **Copy Value** cu clipboard clear timer.
  - `GeneratorModal`: generator criptografic (`secrets`) — lungime configurabilă (8–256), charset (all / alphanum / hex / alpha), copy direct la clipboard.
- **Tab `⏰ Expiry`** (`ExpiryPanel`): toate cheile grupate în 4 secțiuni colorate — EXPIRED (roșu), Expiring ≤30 zile (galben), Valid (verde), Fără expiry — sortate după urgență.
- **`StatusPanel` cu countdown live**: timer 1s cu `set_interval`, culori verde/galben/roșu la <5 min / <1 min; afișează unlock time, last activity, failed attempts, full config.
- **`KeysPanel` toolbar vizual**: butoane `[+ Add]` `[✏ Edit]` `[🗑 Delete]` `[📋 Copy]` `[ℹ Info]` `[🎲 Generate]` direct deasupra tabelului.
- **`AuditPanel`** upgrade: filtru live + buton Refresh; afișează ultimele 200 evenimente.
- **Persistență add/edit/delete**: toate acțiunile apelează `storage.save()` imediat după modificare.
- **Keyboard bindings complete**:
  - `n` → AddKeyModal
  - `e` → EditKeyModal pentru intrarea selectată
  - `D` → ConfirmDeleteModal
  - `Enter` / `c` → copy to clipboard
  - `i` → KeyDetailModal
  - `g` → GeneratorModal
  - `/` → focus search input
  - `r` → refresh keys table
  - `L` → lock wallet și exit
  - `q` / `Ctrl+C` → quit cu auto-lock

### Changed
- `wallet/__init__.py`: `__version__` bumped `1.2.0` → `1.3.0`.
- `pyproject.toml`: `version` bumped `1.2.0` → `1.3.0`.
- `TabbedContent` extins de la 4 la 5 tab-uri (Keys / Health / Expiry / Audit / Status).
- `UnlockScreen` afișează acum contorul de tentative eșuate (`failed_attempts / max`).

### Fixed
- `KeysPanel.selected_entry()`: guard pentru `cursor_row >= len(filtered)` (IndexError prevention).
- `ExpiryPanel.on_mount`: try/except per-table pentru robustețe când tab-urile lipsesc.
- `StatusPanel._update_display`: try/except per-widget pentru stabilitate la resize rapid.

---

## [1.2.0] — Wave 5 (2026-04-05)

### Added
- **`tests/conftest.py`**: Shared fixtures for entire test suite.
  - `kdf_params` / `master_key`: session-scoped (Argon2id runs once, not per-test).
  - `payload_with_keys`: 3 pre-populated entries (active, expiring, expired).
  - `saved_wallet`: storage + key + payload already saved to disk.
  - `make_entry()`: factory for `APIKeyEntry` with controlled state.
- **`tests/test_hypothesis.py`**: 13 property-based tests (Hypothesis).
  - P1–P5: AES-GCM invariants (roundtrip, nonce uniqueness, HKDF domain separation, tamper detection).
  - P6–P8: Validator invariants (no-raise on valid inputs, whitespace rejection, future date acceptance).
  - P9–P11: Model invariants (payload roundtrip, search subset, status_label validity).
  - P12–P13: KDF determinism and password distinguishability.
- **`tests/test_health.py`**: 12 tests covering score signals, grade thresholds, wallet-level aggregation.
- **`tests/test_prefix_detect.py`**: 8 tests for 8 known service prefixes + mask_key.
- **`tests/test_integrity.py`**: 6 tests for clean/tampered/empty/strict verify_integrity.
- **`pyproject.toml` complete rewrite**: migrated from Poetry to Hatchling.
  - PEP 621 compliant `[project]` table with classifiers, keywords, URLs.
  - `[tool.ruff.lint]` extended: `S`, `ANN`, `BLE`, `W` rule sets.
  - `[tool.ruff.lint.per-file-ignores]` for tests and UI.
  - `[tool.mypy]` strict config (excluding UI and tests).
  - `[tool.bandit]` integrated into pyproject (no separate config file).
  - `[tool.hypothesis]` settings: deadline=5000, suppress too_slow.
  - `[tool.coverage.run]` with `branch = true`.
  - `[project.urls]` with Homepage, Repository, Bug Tracker, Changelog, Security.
- **`wallet/__init__.py`**: `__version__ = "1.2.0"`, hatch version source.
- **MkDocs documentation site** (`docs/`):
  - `mkdocs.yml`: Material theme, dark/light toggle, mkdocstrings plugin.
  - `docs/index.md`: Overview, quick install, quick start, security table.
  - `docs/guide/install.md`: Platform notes, clipboard backends, wallet location.
  - `docs/guide/quickstart.md`: Step-by-step 8-command walkthrough.
  - `docs/security/architecture.md`: Storage format layout, key hierarchy diagram, AAD, HMAC manifest, memory security.

### Changed
- `pyproject.toml`: build backend changed from Poetry to Hatchling (PEP 621).
- `wallet/__init__.py`: version bumped to 1.2.0.

---

## [1.1.0] — Wave 3 + Wave 4 (2026-04-05)

### Added
- CLI: `health`, `audit`, `verify`, `wipe`, `tag`, `search`, `export`, `import`, `change-password`, `rotate`, `tui`, `gui`.
- **Textual TUI** (`tui.py`): Keys, Health, Audit, Status panels.
- **CustomTkinter GUI** (`gui.py`): Keys, Health, Settings tabs (Wave 4 rewrite).
- `tests/test_storage.py` (12), `test_kdf.py` (10), `test_crypto.py` (16), `test_session.py` (14), `test_audit.py` (12), `test_validators.py` (20).
- `.github/workflows/ci.yml`: 9-combination matrix + bandit security scan.
- `SECURITY.md`: Threat model, crypto primitives table.
- `CHANGELOG.md`: This file.

### Fixed
- `gui.py`: `_tmp_` encrypt bug — UUID generated before first `encrypt_entry_value`.
- `gui.py`: `on_closing` locks session on OS window close.
- `cli.py`: `list_keys` sort by expires uses `datetime.max` fallback.

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
- FIX #1 (CRITICAL): `time.sleep()` outside `_op_lock` (deadlock prevention).
- FIX #2 (CRITICAL): UUID before first encrypt in `add` (no `_tmp_` sub-key).
- FIX #3 (MODERATE): `LOCKOUT_RESET` audit event on lockout expiry.
- FIX #4 (MODERATE): `datetime` import consolidated at module level.
- FIX #5 (MINOR): HMAC manifest written on every `storage.save()`.
- FIX #6 (MINOR): Explicit HKDF domain-separation salt (RFC 5869 §3.1).
