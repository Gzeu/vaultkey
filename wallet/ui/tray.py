"""
tray.py — System tray integration for VaultKey GUI.

Provides a cross-platform system tray icon with quick actions:
  - Show / Hide main window
  - Quick Copy (most recently accessed key)
  - Lock vault
  - Open settings
  - Quit

Platform support:
  - Windows:   Native Win32 tray via pystray (requires Pillow)
  - macOS:     NSStatusBar via pystray
  - Linux:     AppIndicator / XEmbed via pystray

Fallback: If pystray or Pillow are unavailable, TrayManager silently
disables itself (graceful degradation — GUI still works without tray).

Usage (from GUI main window):
    from wallet.ui.tray import TrayManager

    tray = TrayManager(
        on_show=lambda: root.deiconify(),
        on_lock=lambda: session.lock(),
        on_quit=lambda: app.quit(),
    )
    tray.start()     # non-blocking, runs in daemon thread
    tray.stop()      # call on app exit
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Attempt to import pystray — graceful fallback if missing
try:
    import pystray
    from pystray import MenuItem as Item, Menu
    _PYSTRAY_AVAILABLE = True
except ImportError:
    _PYSTRAY_AVAILABLE = False
    log.debug("pystray not available — system tray disabled.")

# Attempt to import Pillow for icon generation
try:
    from PIL import Image, ImageDraw
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    log.debug("Pillow not available — tray icon will use fallback.")


class TrayManager:
    """
    Cross-platform system tray icon manager.

    All callbacks are called from the tray thread — GUI operations
    must be dispatched back to the main thread (e.g., via
    root.after(0, callback) in tkinter).

    Args:
        on_show:     Callback to show/restore the main window.
        on_hide:     Callback to hide the main window.
        on_lock:     Callback to lock the vault.
        on_settings: Callback to open settings window.
        on_quit:     Callback to quit the application.
        tooltip:     Tray icon tooltip text.
        app_name:    Application name shown in menu.
    """

    def __init__(
        self,
        on_show: Optional[Callable[[], None]] = None,
        on_hide: Optional[Callable[[], None]] = None,
        on_lock: Optional[Callable[[], None]] = None,
        on_settings: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        tooltip: str = "VaultKey — Secure API Key Manager",
        app_name: str = "VaultKey",
    ) -> None:
        self._on_show = on_show or (lambda: None)
        self._on_hide = on_hide or (lambda: None)
        self._on_lock = on_lock or (lambda: None)
        self._on_settings = on_settings or (lambda: None)
        self._on_quit = on_quit or (lambda: None)
        self._tooltip = tooltip
        self._app_name = app_name
        self._icon: Optional[object] = None  # pystray.Icon
        self._thread: Optional[threading.Thread] = None
        self._available = _PYSTRAY_AVAILABLE and _PIL_AVAILABLE
        self._window_visible: bool = True

    # ────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """True if pystray and Pillow are installed and tray is running."""
        return self._available

    def start(self) -> bool:
        """
        Start the tray icon in a daemon thread.

        Returns:
            True if tray started successfully, False if unavailable.
        """
        if not self._available:
            log.info("System tray not available on this platform/installation.")
            return False

        try:
            icon_image = self._create_icon_image()
            menu = self._build_menu()

            self._icon = pystray.Icon(
                name="vaultkey",
                icon=icon_image,
                title=self._tooltip,
                menu=menu,
            )

            self._thread = threading.Thread(
                target=self._run_tray,
                daemon=True,
                name="VaultKey-Tray",
            )
            self._thread.start()
            log.info("System tray icon started.")
            return True

        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to start system tray: %s", exc)
            self._available = False
            return False

    def stop(self) -> None:
        """Stop and remove the tray icon."""
        if self._icon is not None:
            try:
                self._icon.stop()
                log.info("System tray icon stopped.")
            except Exception as exc:  # noqa: BLE001
                log.debug("Tray stop error (ignored): %s", exc)
            self._icon = None

    def notify(self, title: str, message: str, duration: float = 3.0) -> None:
        """
        Show a system notification balloon from the tray icon.

        Args:
            title:    Notification title.
            message:  Notification body.
            duration: Seconds to display (platform-dependent support).
        """
        if self._icon is None or not self._available:
            return
        try:
            self._icon.notify(message=message, title=title)
        except Exception as exc:  # noqa: BLE001
            log.debug("Tray notification failed: %s", exc)

    def update_locked_state(self, locked: bool) -> None:
        """
        Update the tray menu to reflect vault lock state.

        Args:
            locked: True if vault is currently locked.
        """
        if self._icon is None:
            return
        self._icon.menu = self._build_menu(locked=locked)
        try:
            self._icon.update_menu()
        except Exception as exc:  # noqa: BLE001
            log.debug("Tray menu update failed: %s", exc)

    # ────────────────────────────────────────────
    # Private helpers
    # ────────────────────────────────────────────

    def _run_tray(self) -> None:
        """Entry point for the tray daemon thread."""
        try:
            self._icon.run()  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            log.warning("Tray thread exited with error: %s", exc)

    def _build_menu(self, locked: bool = False) -> "Menu":
        """Build the context menu for the tray icon."""
        items: list = []

        # App name header (non-clickable)
        items.append(Item(f"🔑 {self._app_name}", None, enabled=False))
        items.append(Menu.SEPARATOR)

        if locked:
            items.append(Item("Unlock Vault", self._handle_show, default=True))
        else:
            # Toggle show/hide
            label = "Hide Window" if self._window_visible else "Show Window"
            items.append(Item(label, self._handle_toggle_window, default=True))
            items.append(Menu.SEPARATOR)
            items.append(Item("Lock Vault", self._handle_lock))
            items.append(Item("Settings", self._handle_settings))

        items.append(Menu.SEPARATOR)
        items.append(Item("Quit", self._handle_quit))

        return Menu(*items)

    def _handle_toggle_window(self, icon: object, item: object) -> None:  # noqa: ARG002
        if self._window_visible:
            self._window_visible = False
            self._on_hide()
        else:
            self._window_visible = True
            self._on_show()
        # Rebuild menu to update label
        self._icon.menu = self._build_menu()  # type: ignore[union-attr]

    def _handle_show(self, icon: object, item: object) -> None:  # noqa: ARG002
        self._window_visible = True
        self._on_show()

    def _handle_lock(self, icon: object, item: object) -> None:  # noqa: ARG002
        self._on_lock()
        self.update_locked_state(locked=True)

    def _handle_settings(self, icon: object, item: object) -> None:  # noqa: ARG002
        self._on_settings()

    def _handle_quit(self, icon: object, item: object) -> None:  # noqa: ARG002
        self._on_quit()
        self.stop()

    def _create_icon_image(self) -> "Image.Image":
        """
        Generate a simple programmatic tray icon.

        Draws a dark shield shape with a key symbol.
        Replace with a real icon by passing a PIL Image to pystray.Icon(icon=...).
        """
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Shield background (dark teal)
        shield_color = (1, 105, 111, 255)  # matches --color-primary from design system
        draw.ellipse([4, 4, size - 4, size - 4], fill=shield_color)

        # Key symbol (white)
        cx, cy = size // 2, size // 2
        # Key bow (circle)
        draw.ellipse([cx - 10, cy - 16, cx + 6, cy], outline=(255, 255, 255, 220), width=3)
        # Key shaft
        draw.rectangle([cx - 2, cy, cx + 2, cy + 16], fill=(255, 255, 255, 220))
        # Key teeth
        draw.rectangle([cx + 2, cy + 6, cx + 8, cy + 10], fill=(255, 255, 255, 220))
        draw.rectangle([cx + 2, cy + 12, cx + 6, cy + 15], fill=(255, 255, 255, 220))

        return img
