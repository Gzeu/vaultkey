# Changelog

All notable changes to VaultKey are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

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
- **`wallet/ui/tui_import.py`** — `ImportScreen(ModalScreen)` pentru TUI:
  - Input path fișier CSV sau JSON.
  - `DataTable` preview cu validare per-rând (verde = OK, roșu = eroare).
  - Statistici „X valid, Y invalid (skipped)".
  - Buton „Import X valid rows" activ doar când există rânduri valide.
  - Salvare wallet după import reușit.
- **`tests/test_rotate.py`** — 10 teste (R1–R10):
  - R1–R3: `rotate_single` (valoare recuperabilă, nonce schimbat, KeyError pe ID inexistent).
  - R4–R8: `rotate_all` (valori intacte, nonce-uri noi, raport corect, persistență, no-save la eșec parțial).
  - R9–R10: `RotateReport` properties și timestamps.
- **`tests/test_expiry_checker.py`** — 12 teste (E1–E12):
  - E1–E6: `check_expiry` categorii + `summary()` + `total`.
  - E7–E9: callbacks `on_expired` / `on_warning` / niciun callback pentru .ok.
  - E10: lifecycle thread (start/stop).
  - E11–E12: `warn_days` personalizat + total == len(payload.entries).
- **`tests/test_shell_completion.py`** — 8 teste (SC1–SC8):
  - SC1–SC4: `entry_names_completer` (prefix, empty, case-insensitive, no match).
  - SC5–SC6: `service_names_completer` (prefix, deduplicare).
  - SC7–SC8: `tag_completer` (prefix, locked wallet).

### Changed
- `wallet/__init__.py`: `__version__` bumped `1.3.0` → `1.4.0`.
- `pyproject.toml`: `version` bumped `1.3.0` → `1.4.0`.

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
- **`tests/test_hypothesis.py`**: 13 property-based tests (Hypothesis).
- **`tests/test_health.py`**: 12 tests.
- **`tests/test_prefix_detect.py`**: 8 tests.
- **`tests/test_integrity.py`**: 6 tests.
- **`pyproject.toml` complete rewrite**: migrated from Poetry to Hatchling.
- **MkDocs documentation site** (`docs/`).

### Changed
- `pyproject.toml`: build backend changed from Poetry to Hatchling (PEP 621).
- `wallet/__init__.py`: version bumped to 1.2.0.

---

## [1.1.0] — Wave 3 + Wave 4 (2026-04-05)

### Added
- CLI: `health`, `audit`, `verify`, `wipe`, `tag`, `search`, `export`, `import`, `change-password`, `rotate`, `tui`, `gui`.
- **Textual TUI** (`tui.py`): Keys, Health, Audit, Status panels.
- **CustomTkinter GUI** (`gui.py`): Keys, Health, Settings tabs.
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
