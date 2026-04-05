"""
clipboard.py — Secure clipboard operations with auto-clear.

Design decisions:
- pyperclip is used as the cross-platform clipboard backend.
  It supports X11 (xclip/xsel), Wayland (wl-clipboard), macOS (pbcopy), Windows.
- The clear timer runs in a daemon thread so it doesn't prevent process exit.
- The clipboard is cleared by overwriting with an empty string, not by
  killing the clipboard manager — this is more compatible across environments.
- We deliberately do NOT store what was copied — the callback just writes "".
- On Wayland without wl-clipboard, pyperclip will raise. We catch and warn.
"""

import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)


def copy_to_clipboard(
    value: str,
    *,
    key_name: str = "",
    timeout: int = 30,
    on_clear: Callable[[], None] | None = None,
) -> bool:
    """
    Copy a value to the clipboard and schedule auto-clear.

    Args:
        value:    The string to copy (e.g., API key).
        key_name: Display name for log messages.
        timeout:  Seconds until clipboard is cleared.
        on_clear: Optional callback invoked after clearing.

    Returns:
        True if copied successfully, False if clipboard unavailable.
    """
    try:
        import pyperclip
        pyperclip.copy(value)
        log.info(
            "Copied '%s' to clipboard. Auto-clear in %ds.",
            key_name or "key",
            timeout,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Clipboard unavailable: %s", e)
        return False

    def _clear() -> None:
        try:
            import pyperclip
            pyperclip.copy("")
            log.info("Clipboard cleared (auto, %ds timeout).", timeout)
            if on_clear:
                on_clear()
        except Exception as e:  # noqa: BLE001
            log.warning("Clipboard clear failed: %s", e)

    timer = threading.Timer(timeout, _clear)
    timer.daemon = True
    timer.start()
    return True


def clear_clipboard() -> bool:
    """Immediately clear the clipboard. Returns True on success."""
    try:
        import pyperclip
        pyperclip.copy("")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Clipboard clear failed: %s", e)
        return False
