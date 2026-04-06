"""
shell_completion.py — Dynamic shell completion helpers for VaultKey CLI.

Used by Typer's completion machinery via the `--install-completion` flag.
Also exposes `entry_names_completer` and `service_names_completer` so that
CLI commands which accept <name> or <service> arguments get live tab-completion
from the current (unlocked) wallet.

Usage in cli.py:
    from wallet.utils.shell_completion import entry_names_completer

    @app.command()
    def get(name: str = typer.Argument(..., autocompletion=entry_names_completer)):
        ...
"""

from __future__ import annotations

from typing import Any


def _load_payload() -> Any | None:  # type: ignore[return]
    """Try to load the wallet payload via the live session. Returns None on failure."""
    try:
        from wallet.core.session import SessionManager
        from wallet.core.storage import WalletStorage
        from wallet.models.config import WalletConfig
        from wallet.models.wallet import WalletPayload

        cfg = WalletConfig()
        session = SessionManager()
        key = session.get_key()  # raises if locked
        storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)
        data = storage.load(key)
        return WalletPayload.from_dict(data)
    except Exception:  # noqa: BLE001
        return None


def entry_names_completer(incomplete: str) -> list[str]:
    """Return entry names starting with *incomplete* for shell completion."""
    payload = _load_payload()
    if payload is None:
        return []
    return [
        e.name for e in payload.entries if e.name.lower().startswith(incomplete.lower())
    ]


def service_names_completer(incomplete: str) -> list[str]:
    """Return unique service names starting with *incomplete*."""
    payload = _load_payload()
    if payload is None:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for e in payload.entries:
        svc = e.service or ""
        if svc and svc.lower().startswith(incomplete.lower()) and svc not in seen:
            seen.add(svc)
            result.append(svc)
    return result


def tag_completer(incomplete: str) -> list[str]:
    """Return unique tags starting with *incomplete*."""
    payload = _load_payload()
    if payload is None:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for e in payload.entries:
        for tag in e.tags:
            if tag.lower().startswith(incomplete.lower()) and tag not in seen:
                seen.add(tag)
                result.append(tag)
    return result
