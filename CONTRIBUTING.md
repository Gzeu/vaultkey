# Contributing to VaultKey

Thank you for your interest in contributing! This guide covers everything you need to get started.

---

## Getting Started

```bash
git clone https://github.com/Gzeu/vaultkey.git
cd vaultkey
pip install -e ".[dev]"
```

---

## Development Workflow

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Write code** following the existing style (see Code Standards below).

3. **Run the full check suite** before pushing:
   ```bash
   ruff check wallet/ tests/          # lint
   mypy wallet/ --ignore-missing-imports   # types
   bandit -r wallet/ -c pyproject.toml --severity-level medium  # security
   pytest tests/ -v --cov=wallet      # tests
   ```

4. **Open a Pull Request** against `main` with a clear title and description.

---

## Code Standards

- **Python 3.11+** — use modern typing (`X | Y`, `match`, `@dataclass(frozen=True)`)
- **Formatter**: `ruff format` (Black-compatible, line length 100)
- **Linter**: `ruff check` — all rules enabled in `pyproject.toml`
- **Types**: every public function must have full type annotations
- **Tests**: new features require new tests; aim to keep coverage ≥ 90%
- **Docstrings**: one-liner for simple functions, full Google-style for complex ones

---

## Security Rules (Non-Negotiable)

- **Never log or print plaintext key values** — masked prefix only
- **Never store derived keys or plaintexts in global state**
- **Always call `ctypes.memset` / `SecureBytes.wipe()`** after using sensitive buffers
- **All file writes must be atomic** — write to `.tmp`, then `os.replace()`
- **Every new operation must emit an audit log entry** via `audit_log()`
- Run `bandit` before every PR — zero medium/high findings allowed

---

## Project Structure

```
wallet/core/      — cryptographic primitives, session, storage
wallet/models/    — dataclasses (WalletPayload, APIKeyEntry, WalletConfig)
wallet/ui/        — CLI (Typer), TUI (Textual), GUI (CustomTkinter)
wallet/utils/     — clipboard, audit, validators, prefix detection, bulk import
tests/            — pytest suite (123+ tests, Hypothesis property tests)
docs/             — MkDocs Material documentation
```

---

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scope): short description
fix(scope): short description
docs(scope): short description
refactor(scope): short description
test(scope): short description
```

Examples:
```
feat(cli): add wallet rename command
fix(session): resolve deadlock on concurrent lock/unlock
docs(readme): update CLI reference for Wave 7
test(bulk_import): add dry-run and conflict strategy tests
```

---

## Reporting Security Vulnerabilities

Do **not** open a public issue for security vulnerabilities.  
See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
