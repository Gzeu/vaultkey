"""
theme.py — Unified theme manager for all three VaultKey interfaces.

Provides a single source of truth for dark/light/auto theme across:
  - GUI (CustomTkinter): calls ctk.set_appearance_mode()
  - TUI (Textual):       writes TEXTUAL_THEME env var + returns CSS variable set
  - CLI (Rich):          returns rich.Theme() instance with correct palette

Theme is persisted in the VaultKey config directory (~/.local/share/vaultkey/theme).
OS auto-detection is supported on Windows, macOS, and Linux (GTK/KDE).

Usage:
    from wallet.ui.theme import ThemeManager, ThemeMode

    mgr = ThemeManager()
    mgr.set(ThemeMode.DARK)
    mgr.apply_to_gui()    # CustomTkinter
    mgr.apply_to_cli()    # returns rich.Theme
    mgr.effective_mode    # 'dark' or 'light' (resolved auto)
"""

from __future__ import annotations

import logging
import os
import platform
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_THEME_FILE_NAME = "theme"


class ThemeMode(str, Enum):
    """Available theme modes."""
    DARK = "dark"
    LIGHT = "light"
    AUTO = "auto"   # follow OS preference


# ────────────────────────────────────────────
# Palette definitions
# Same tokens as the design system in SKILL.md — ported to Python constants
# ────────────────────────────────────────────

_PALETTE_DARK = {
    "bg":              "#171614",
    "surface":         "#1c1b19",
    "surface_2":       "#201f1d",
    "border":          "#393836",
    "text":            "#cdccca",
    "text_muted":      "#797876",
    "primary":         "#4f98a3",
    "primary_hover":   "#227f8b",
    "success":         "#6daa45",
    "error":           "#d163a7",
    "warning":         "#bb653b",
    "gold":            "#e8af34",
}

_PALETTE_LIGHT = {
    "bg":              "#f7f6f2",
    "surface":         "#f9f8f5",
    "surface_2":       "#fbfbf9",
    "border":          "#d4d1ca",
    "text":            "#28251d",
    "text_muted":      "#7a7974",
    "primary":         "#01696f",
    "primary_hover":   "#0c4e54",
    "success":         "#437a22",
    "error":           "#a12c7b",
    "warning":         "#964219",
    "gold":            "#d19900",
}


class ThemeManager:
    """
    Manages VaultKey theme state across all three interfaces.

    Args:
        config_dir: Path to VaultKey data directory (for theme persistence).
                    Defaults to XDG_DATA_HOME/vaultkey.
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._config_dir = config_dir or self._default_config_dir()
        self._theme_file = self._config_dir / _THEME_FILE_NAME
        self._mode: ThemeMode = self._load_persisted() or ThemeMode.AUTO

    # ────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────

    @property
    def mode(self) -> ThemeMode:
        """The configured mode (may be AUTO)."""
        return self._mode

    @property
    def effective_mode(self) -> ThemeMode:
        """
        The resolved theme mode (never AUTO).

        Resolves AUTO by detecting OS preference.
        Falls back to DARK if detection fails.
        """
        if self._mode != ThemeMode.AUTO:
            return self._mode
        return self._detect_os_theme()

    def set(self, mode: ThemeMode, persist: bool = True) -> None:
        """
        Set the active theme mode.

        Args:
            mode:    Target theme mode.
            persist: Write to disk (default True).
        """
        self._mode = mode
        if persist:
            self._persist(mode)
        log.info("Theme set to '%s' (effective: '%s').", mode.value, self.effective_mode.value)

    def palette(self) -> dict[str, str]:
        """Return the active color palette dict."""
        return _PALETTE_DARK if self.effective_mode == ThemeMode.DARK else _PALETTE_LIGHT

    def apply_to_gui(self) -> None:
        """
        Apply theme to CustomTkinter.

        Safe to call before CTk window creation — CTk reads appearance_mode
        lazily. Also sets the VAULTKEY_THEME env var for subprocess consistency.
        """
        try:
            import customtkinter as ctk
            ctk_mode = "Dark" if self.effective_mode == ThemeMode.DARK else "Light"
            ctk.set_appearance_mode(ctk_mode)
            log.debug("Applied '%s' theme to CustomTkinter.", ctk_mode)
        except ImportError:
            log.debug("customtkinter not available — GUI theme not applied.")

        os.environ["VAULTKEY_THEME"] = self.effective_mode.value

    def apply_to_tui(self) -> dict[str, str]:
        """
        Prepare theme for Textual TUI.

        Returns the active palette dict for use in Textual CSS variables.
        Also sets VAULTKEY_THEME env var and TEXTUAL_THEME for subprocess launch.

        Returns:
            Color palette dict for injection into Textual CSS variables.
        """
        os.environ["VAULTKEY_THEME"] = self.effective_mode.value
        # Textual reads TEXTUAL_THEME for built-in dark/light switching
        os.environ["TEXTUAL_THEME"] = self.effective_mode.value
        log.debug("Applied '%s' theme to TUI environment.", self.effective_mode.value)
        return self.palette()

    def apply_to_cli(self) -> object:
        """
        Return a Rich Theme object for CLI output.

        Returns:
            rich.theme.Theme configured for the active palette.
        """
        try:
            from rich.theme import Theme as RichTheme
            p = self.palette()
            return RichTheme({
                "info":     f"{p['primary']}",
                "success":  f"{p['success']}",
                "warning":  f"{p['warning']}",
                "error":    f"{p['error']}",
                "muted":    f"{p['text_muted']}",
                "gold":     f"{p['gold']}",
                "key.name": f"bold {p['primary']}",
                "key.value":f"{p['text']}",
                "header":   f"bold {p['text']}",
            })
        except ImportError:
            return None  # type: ignore[return-value]

    # ────────────────────────────────────────────
    # Private helpers
    # ────────────────────────────────────────────

    def _detect_os_theme(self) -> ThemeMode:
        """
        Detect OS dark/light mode preference.

        Platforms:
            - Windows 10/11: Registry AppsUseLightTheme
            - macOS:         defaults read AppleInterfaceStyle
            - Linux:         GTK theme name / KDE colorscheme / GNOME gsettings
        """
        system = platform.system()
        try:
            if system == "Windows":
                return self._detect_windows()
            elif system == "Darwin":
                return self._detect_macos()
            else:
                return self._detect_linux()
        except Exception as exc:  # noqa: BLE001
            log.debug("OS theme detection failed (%s), defaulting to dark.", exc)
            return ThemeMode.DARK

    @staticmethod
    def _detect_windows() -> ThemeMode:
        import winreg  # noqa: PLC0415
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return ThemeMode.LIGHT if value == 1 else ThemeMode.DARK

    @staticmethod
    def _detect_macos() -> ThemeMode:
        import subprocess  # noqa: PLC0415
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2,
        )
        return ThemeMode.DARK if "Dark" in result.stdout else ThemeMode.LIGHT

    @staticmethod
    def _detect_linux() -> ThemeMode:
        # Method 1: GNOME/GTK via gsettings
        try:
            import subprocess  # noqa: PLC0415
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True, timeout=2,
            )
            if "dark" in result.stdout.lower():
                return ThemeMode.DARK
            if "light" in result.stdout.lower() or result.returncode == 0:
                return ThemeMode.LIGHT
        except Exception:  # noqa: BLE001
            pass

        # Method 2: GTK_THEME env var
        gtk_theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in gtk_theme:
            return ThemeMode.DARK
        if gtk_theme and "dark" not in gtk_theme:
            return ThemeMode.LIGHT

        # Method 3: KDE color scheme
        kde_colors = os.environ.get("KDE_SESSION_VERSION", "")
        if kde_colors:
            try:
                import subprocess  # noqa: PLC0415
                result = subprocess.run(
                    ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
                    capture_output=True, text=True, timeout=2,
                )
                if "dark" in result.stdout.lower():
                    return ThemeMode.DARK
            except Exception:  # noqa: BLE001
                pass

        # Default: dark (most developer-friendly)
        return ThemeMode.DARK

    def _persist(self, mode: ThemeMode) -> None:
        """Write theme preference to disk."""
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            self._theme_file.write_text(mode.value, encoding="utf-8")
        except OSError as exc:
            log.warning("Could not persist theme setting: %s", exc)

    def _load_persisted(self) -> Optional[ThemeMode]:
        """Load persisted theme from disk, return None if not found."""
        try:
            raw = self._theme_file.read_text(encoding="utf-8").strip().lower()
            return ThemeMode(raw)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _default_config_dir() -> Path:
        system = platform.system()
        if system == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif system == "Darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / "vaultkey"
