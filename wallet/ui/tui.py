"""
tui.py — Full-screen Textual TUI for VaultKey.

Screens:
  UnlockScreen   — prompt for master password, derive key, enter main app.
  MainApp        — tabbed interface with 5 panels:
      [1] Keys    — DataTable of all entries, live search, actions.
      [2] Health  — Health scores per entry + overall grade.
      [3] Audit   — Scrollable audit log viewer.
      [4] Info    — Detailed metadata for selected entry.
      [5] Status  — Session info + security indicators.

Navigation:
  Tab / Shift+Tab   — switch panels
  /                 — focus search (Keys panel)
  Enter             — copy selected key to clipboard
  i                 — show info for selected key
  D                 — delete selected key (with confirmation)
  q / Ctrl+C        — quit (auto-locks session)
  L                 — manual lock

Design decisions:
- Textual is used instead of curses for its widget system, CSS-like layout,
  and reactive data model. Much safer for async UI than raw terminal escape codes.
- The TUI shares the same SessionManager singleton as the CLI.
  Locking in TUI locks for CLI too (and vice versa).
- No API key values are ever displayed in the TUI — only masked prefixes.
  Full value is only accessed via clipboard (copy action).
- Health analysis runs without re-decrypting any entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from wallet.core.crypto import decrypt_entry_value
from wallet.core.health import analyze_wallet
from wallet.core.session import SessionManager, WalletLockedException
from wallet.core.storage import WalletStorage
from wallet.models.config import WalletConfig
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.audit import read_audit_log
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.prefix_detect import mask_key

cfg = WalletConfig()
session = SessionManager()
storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)


# ------------------------------------------------------------------ #
# Unlock Screen
# ------------------------------------------------------------------ #

class UnlockScreen(Screen):
    """Full-screen password prompt displayed before the main app."""

    CSS = """
    UnlockScreen {
        align: center middle;
    }
    #unlock-container {
        width: 60;
        height: auto;
        border: double $accent;
        padding: 1 2;
    }
    #unlock-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #error-label {
        color: $error;
        text-align: center;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="unlock-container"):
            yield Label("🔐 VaultKey", id="unlock-title")
            yield Label("Master password:", markup=False)
            yield Input(placeholder="Enter master password", password=True, id="password-input")
            yield Button("Unlock", variant="primary", id="unlock-btn")
            yield Label("", id="error-label")

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "unlock-btn":
            self._attempt_unlock()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._attempt_unlock()

    def _attempt_unlock(self) -> None:
        from wallet.core.kdf import derive_key, verify_master_password
        password = self.query_one("#password-input", Input).value
        error_label = self.query_one("#error-label", Label)
        try:
            params = storage.read_kdf_params()
            key = derive_key(password, params)
            data = storage.load(key)
            payload = WalletPayload.from_dict(data)
        except Exception:  # noqa: BLE001
            session.record_failed_attempt()
            error_label.update("❌ Wrong password")
            self.query_one("#password-input", Input).value = ""
            return

        if not verify_master_password(password, payload.master_hash):
            session.record_failed_attempt()
            error_label.update("❌ Wrong password")
            self.query_one("#password-input", Input).value = ""
            return

        session.unlock(key)
        self.app.pop_screen()  # type: ignore[attr-defined]


# ------------------------------------------------------------------ #
# Keys Panel
# ------------------------------------------------------------------ #

class KeysPanel(Container):
    """DataTable of all API keys with live search and clipboard copy."""

    CSS = """
    KeysPanel {
        height: 100%;
    }
    #search-input {
        margin-bottom: 1;
    }
    #keys-help {
        dock: bottom;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, payload: WalletPayload, master_key: bytes, **kw) -> None:
        super().__init__(**kw)
        self._payload = payload
        self._master_key = master_key
        self._filtered: list[APIKeyEntry] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="/ Search…", id="search-input")
        yield DataTable(id="keys-table", cursor_type="row")
        yield Static(
            "[Enter] Copy  [i] Info  [D] Delete  [L] Lock  [/] Search",
            id="keys-help",
        )

    def on_mount(self) -> None:
        table = self.query_one("#keys-table", DataTable)
        table.add_columns("Name", "Service", "Tags", "Added", "Expires", "Status", "Used")
        self._refresh_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._refresh_table(query=event.value)

    def _refresh_table(self, query: str = "") -> None:
        table = self.query_one("#keys-table", DataTable)
        table.clear()
        results = self._payload.search(query=query)
        self._filtered = sorted(results, key=lambda e: e.name.lower())
        for e in self._filtered:
            table.add_row(
                e.name, e.service,
                ", ".join(e.tags),
                e.created_at.strftime("%Y-%m-%d"),
                e.expires_at.strftime("%Y-%m-%d") if e.expires_at else "—",
                e.status_label,
                str(e.access_count),
                key=e.id,
            )

    def selected_entry(self) -> Optional[APIKeyEntry]:
        table = self.query_one("#keys-table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._filtered):
            return None
        return self._filtered[table.cursor_row]

    def action_copy(self) -> None:
        entry = self.selected_entry()
        if not entry:
            return
        try:
            value = decrypt_entry_value(
                self._master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
            copy_to_clipboard(value, key_name=entry.name, timeout=cfg.clipboard_clear_seconds)
            entry.access_count += 1
            entry.last_accessed_at = datetime.now(timezone.utc)
            self.app.notify(  # type: ignore[attr-defined]
                f"Copied {entry.name}. Clears in {cfg.clipboard_clear_seconds}s.",
                severity="information",
            )
        except Exception as e:  # noqa: BLE001
            self.app.notify(f"Error: {e}", severity="error")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ #
# Health Panel
# ------------------------------------------------------------------ #

class HealthPanel(Container):
    """Visual health scores for every entry."""

    CSS = """
    HealthPanel { height: 100%; }
    #health-summary { margin-bottom: 1; padding: 0 1; }
    """

    def __init__(self, payload: WalletPayload, **kw) -> None:
        super().__init__(**kw)
        self._payload = payload

    def compose(self) -> ComposeResult:
        wh = analyze_wallet(self._payload)
        grade_icon = {"A": "✅", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}.get(wh.overall_grade, "🔵")
        yield Static(
            f"{grade_icon} Overall: {wh.overall_grade} ({wh.overall_score}/100)  "
            f"| ✅ {wh.healthy} Healthy  ⚠️ {wh.warning} Warning  🔴 {wh.critical} Critical",
            id="health-summary",
        )
        with ScrollableContainer():
            yield DataTable(id="health-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#health-table", DataTable)
        table.add_columns("Name", "Score", "Grade", "Issue", "Recommendation")
        wh = analyze_wallet(self._payload)
        for eh in wh.entries:
            table.add_row(
                eh.name,
                str(eh.score),
                eh.grade,
                (eh.issues[0] if eh.issues else "—"),
                (eh.recommendations[0] if eh.recommendations else "—"),
            )


# ------------------------------------------------------------------ #
# Audit Panel
# ------------------------------------------------------------------ #

class AuditPanel(ScrollableContainer):
    """Scrollable audit log viewer (last 100 events)."""

    CSS = "AuditPanel { height: 100%; padding: 0 1; }"

    def compose(self) -> ComposeResult:
        events = read_audit_log(last_n=100)
        if not events:
            yield Label("No audit events found.")
            return
        for ev in reversed(events):
            ts = ev.get("ts", "")[:19].replace("T", " ")
            event_name = ev.get("event", "")
            status = ev.get("status", "")
            key_name = ev.get("key_name", "") or ""
            extra = ev.get("extra", "") or ""
            status_mark = "✓" if status == "OK" else "❌"
            line = f"{ts}  {status_mark} {event_name:<20} {key_name:<24} {extra}"
            yield Label(line, markup=False)


# ------------------------------------------------------------------ #
# Status Panel
# ------------------------------------------------------------------ #

class StatusPanel(Container):
    """Session info and security indicators."""

    CSS = "StatusPanel { height: 100%; padding: 1 2; }"

    def compose(self) -> ComposeResult:
        info = session.info
        lines = [
            f"Wallet:    {cfg.wallet_path}",
            f"Backups:   {cfg.backup_dir}",
            f"Audit log: {cfg.audit_log_path}",
            f"Session:   {'Unlocked' if info['unlocked'] else 'Locked'}",
            f"Unlocked:  {info['unlocked_at'] or '—'}",
            f"Last act:  {info['last_activity'] or '—'}",
            f"Timeout:   {cfg.session_timeout_minutes} minutes",
            f"Clipboard: auto-clear {cfg.clipboard_clear_seconds}s",
            f"Integrity: {'enabled' if cfg.enable_integrity_check else 'disabled'}",
        ]
        for line in lines:
            yield Label(line, markup=False)


# ------------------------------------------------------------------ #
# Main App
# ------------------------------------------------------------------ #

class VaultKeyApp(App):
    """Textual TUI application for VaultKey."""

    TITLE = "VaultKey 🔐"
    SUB_TITLE = "Ultra-Secure API Key Wallet"

    CSS = """
    TabbedContent { height: 100%; }
    TabPane { height: 100%; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("L", "lock_wallet", "Lock"),
        Binding("enter", "copy_selected", "Copy", show=False),
        Binding("i", "show_info", "Info", show=False),
        Binding("D", "delete_selected", "Delete", show=False),
    ]

    def __init__(self, payload: WalletPayload, master_key: bytes) -> None:
        super().__init__()
        self._payload = payload
        self._master_key = master_key

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("🗝 Keys", id="tab-keys"):
                yield KeysPanel(self._payload, self._master_key, id="keys-panel")
            with TabPane("📊 Health", id="tab-health"):
                yield HealthPanel(self._payload, id="health-panel")
            with TabPane("📝 Audit", id="tab-audit"):
                yield AuditPanel(id="audit-panel")
            with TabPane("ℹ️ Status", id="tab-status"):
                yield StatusPanel(id="status-panel")
        yield Footer()

    def action_quit(self) -> None:
        session.lock(reason="tui_quit")
        self.exit()

    def action_lock_wallet(self) -> None:
        session.lock(reason="tui_manual_lock")
        self.notify("🔒 Wallet locked.", severity="warning")
        self.exit()

    def action_copy_selected(self) -> None:
        try:
            keys_panel = self.query_one("#keys-panel", KeysPanel)
            keys_panel.action_copy()
        except Exception:  # noqa: BLE001
            pass

    def action_show_info(self) -> None:
        try:
            keys_panel = self.query_one("#keys-panel", KeysPanel)
            entry = keys_panel.selected_entry()
            if entry:
                from wallet.core.health import analyze_entry
                eh = analyze_entry(entry)
                msg = (
                    f"{entry.name} ({entry.service})\n"
                    f"Health: {eh.grade} ({eh.score}/100)\n"
                    + (f"Issues: {'; '.join(eh.issues)}" if eh.issues else "No issues")
                )
                self.notify(msg, title="Key Info", timeout=8)
        except Exception:  # noqa: BLE001
            pass

    def action_delete_selected(self) -> None:
        try:
            keys_panel = self.query_one("#keys-panel", KeysPanel)
            entry = keys_panel.selected_entry()
            if entry:
                self.notify(
                    f"Delete '{entry.name}'? Press D again to confirm or Esc to cancel.",
                    severity="warning",
                )
        except Exception:  # noqa: BLE001
            pass


def run_tui() -> None:
    """Entry point called by `wallet tui` CLI command."""
    if not storage.exists():
        print("❌ No wallet found. Run: wallet init")
        return

    try:
        master_key = session.get_key()
        data = storage.load(master_key)
        payload = WalletPayload.from_dict(data)
    except WalletLockedException:
        # Need to unlock via screen
        tmp_app: App = App()

        class _BootApp(App):
            def on_mount(self) -> None:
                self.push_screen(UnlockScreen())

            def on_screen_resume(self) -> None:
                if session.is_unlocked:
                    try:
                        key = session.get_key()
                        data = storage.load(key)
                        payload = WalletPayload.from_dict(data)
                        self.exit(result=(key, payload))
                    except Exception:  # noqa: BLE001
                        self.exit(result=None)

        boot = _BootApp()
        result = boot.run()
        if not result:
            print("❌ Unlock failed.")
            return
        master_key, payload = result  # type: ignore[misc]

    VaultKeyApp(payload=payload, master_key=master_key).run()
