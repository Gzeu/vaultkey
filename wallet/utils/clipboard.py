"""
clipboard.py — Secure clipboard operations with automatic clearing.

Clipboard is cleared after CLEAR_TIMEOUT_SECONDS (default: 30s) via a daemon timer.
atexit hook ensures clipboard is cleared even on abnormal program exit.
"""

import atexit
import threading
from typing import Optional

from rich.console import Console

from wallet.utils.audit import audit_log

console = Console()
CLEAR_TIMEOUT_SECONDS = 30

_timer: Optional[threading.Timer] = None


def copy_to_clipboard(value: str, key_name: str = "-", timeout: int = CLEAR_TIMEOUT_SECONDS) -> bool:
    """
    Copy value to clipboard and schedule automatic clearing.
    Returns False if clipboard is unavailable (headless system).
    """
    global _timer
    try:
        import pyperclip
        pyperclip.copy(value)
    except Exception as exc:
        console.print(
            f"[yellow]⚠  Clipboard unavailable: {exc}[/yellow]\n"
            "[dim]Use --show or --raw to retrieve the key value.[/dim]"
        )
        return False

    if _timer and _timer.is_alive():
        _timer.cancel()

    _timer = threading.Timer(timeout, _clear_clipboard)
    _timer.daemon = True
    _timer.start()

    console.print(
        f"[green]✓ Copied![/green] "
        f"[dim]Clipboard auto-clears in {timeout}s[/dim]"
    )
    audit_log("COPY_CLIPBOARD", key_name=key_name, status="OK")
    return True


def _clear_clipboard() -> None:
    try:
        import pyperclip
        pyperclip.copy("")
        console.print("\n[dim]🔒 Clipboard cleared.[/dim]")
    except Exception:
        pass


def clear_now() -> None:
    global _timer
    if _timer and _timer.is_alive():
        _timer.cancel()
        _timer = None
    _clear_clipboard()


atexit.register(clear_now)
