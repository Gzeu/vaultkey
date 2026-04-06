"""
tui.py — Complete full-screen Textual TUI for VaultKey.

Screens & Modals:
  UnlockScreen       — master password prompt with attempt counter
  MainApp            — 6-tab interface
  AddKeyModal        — add new API key entry
  EditKeyModal       — edit existing entry
  ConfirmDeleteModal — confirm before destructive action
  KeyDetailModal     — full metadata view for a single entry
  GeneratorModal     — secure random password/token generator

Tabs:
  [1] Keys    — DataTable, live search, add/edit/delete/copy/info
  [2] Health  — scores per entry + overall grade + recommendations
  [3] Expiry  — entries expiring soon or already expired
  [4] Audit   — filterable audit log (last 200 events)
  [5] Import  — bulk CSV import preview
  [6] Status  — live session countdown + security config

Key bindings:
  n          — new key
  e          — edit selected
  D          — delete selected (confirm dialog)
  Enter      — copy selected to clipboard
  i          — key detail modal
  g          — open password generator
  /          — focus search
  L          — manual lock
  r          — refresh current panel
  q          — quit (auto-locks)
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from wallet.core.crypto import decrypt_entry_value, encrypt_entry_value
from wallet.core.health import analyze_entry, analyze_wallet
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

_COMMON_CSS = """
Screen { background: $background; }

/* Modal base */
.modal-outer {
    align: center middle;
    background: $background 60%;
}
.modal-box {
    background: $surface;
    border: double $accent;
    padding: 1 2;
    width: 70;
    height: auto;
    max-height: 90%;
}
.modal-title {
    text-align: center;
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}
.modal-row {
    height: auto;
    margin-bottom: 1;
}
.modal-label {
    width: 18;
    content-align: left middle;
    color: $text-muted;
}
.modal-actions {
    margin-top: 1;
    height: auto;
    align: center middle;
}
.error-label {
    color: $error;
    text-align: center;
    height: 1;
}
.success-label {
    color: $success;
    text-align: center;
    height: 1;
}

/* Table panels */
.panel-help {
    dock: bottom;
    color: $text-muted;
    padding: 0 1;
    height: 1;
}
.panel-title {
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
    padding: 0 1;
}

/* Health */
.health-summary {
    padding: 0 1;
    margin-bottom: 1;
    background: $surface;
    border: solid $primary-background;
}
.grade-a { color: $success; }
.grade-b { color: $success; }
.grade-c { color: $warning; }
.grade-d { color: $warning; }
.grade-f { color: $error; }

/* Expiry */
.expiry-expired { color: $error; }
.expiry-warning { color: $warning; }
.expiry-ok { color: $success; }

/* Status */
.status-panel {
    padding: 1 2;
    height: 100%;
}
.status-row {
    height: 3;
    border-bottom: solid $primary-background;
}
.status-key {
    width: 22;
    color: $text-muted;
    content-align: left middle;
}
.status-val {
    color: $text;
    content-align: left middle;
}
.countdown-ok { color: $success; }
.countdown-warn { color: $warning; }
.countdown-crit { color: $error; }

/* Generator */
.gen-output {
    height: 3;
    margin-bottom: 1;
    border: solid $accent;
    padding: 0 1;
    text-style: bold;
}
"""


# ================================================================== #
# Utility
# ================================================================== #

def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


def _expiry_status(entry: APIKeyEntry) -> tuple[str, str]:
    """Return (label, css_class) for expiry."""
    if entry.expires_at is None:
        return ("—", "expiry-ok")
    now = datetime.now(timezone.utc)
    delta = entry.expires_at - now
    if delta.total_seconds() < 0:
        return ("EXPIRED", "expiry-expired")
    if delta.days <= 30:
        return (f"{delta.days}d left", "expiry-warning")
    return (f"{delta.days}d", "expiry-ok")


def _generate_secret(length: int = 32, charset: str = "all") -> str:
    """Cryptographically secure random secret."""
    charsets = {
        "alpha": string.ascii_letters,
        "alphanum": string.ascii_letters + string.digits,
        "hex": string.hexdigits[:16],  # lowercase hex
        "all": string.ascii_letters + string.digits + "!@#$%^&*",
    }
    chars = charsets.get(charset, charsets["all"])
    return "".join(secrets.choice(chars) for _ in range(length))


# ================================================================== #
# Modals
# ================================================================== #

class ConfirmDeleteModal(ModalScreen[bool]):
    """Ask user to confirm deletion. Returns True if confirmed."""

    CSS = _COMMON_CSS

    def __init__(self, entry_name: str) -> None:
        super().__init__()
        self._name = entry_name

    def compose(self) -> ComposeResult:
        with Container(classes="modal-outer"):
            with Vertical(classes="modal-box"):
                yield Label("🗑️ Delete Key", classes="modal-title")
                yield Label(
                    f"Are you sure you want to permanently delete:\n\n    [bold]{self._name}[/bold]\n\nThis cannot be undone.",
                    markup=True,
                )
                with Horizontal(classes="modal-actions"):
                    yield Button("Cancel", variant="default", id="btn-cancel")
                    yield Button("Delete", variant="error", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")


class KeyDetailModal(ModalScreen):
    """Full metadata view for a single entry."""

    CSS = _COMMON_CSS

    def __init__(self, entry: APIKeyEntry, master_key: bytes) -> None:
        super().__init__()
        self._entry = entry
        self._master_key = master_key

    def compose(self) -> ComposeResult:
        e = self._entry
        eh = analyze_entry(e)
        exp_label, _ = _expiry_status(e)

        rows = [
            ("Name", e.name),
            ("Service", e.service or "—"),
            ("Description", e.description or "—"),
            ("Tags", ", ".join(e.tags) or "—"),
            ("Status", e.status_label),
            ("Health", f"{eh.grade} ({eh.score}/100)"),
            ("Issues", ("\n".join(eh.issues) if eh.issues else "✔ None")),
            ("Recommendation", (eh.recommendations[0] if eh.recommendations else "—")),
            ("Created", _fmt_dt(e.created_at)),
            ("Expires", exp_label),
            ("Last accessed", _fmt_dt(e.last_accessed_at)),
            ("Access count", str(e.access_count)),
            ("Key preview", mask_key("?" * 32)),  # never show real value
        ]

        with Container(classes="modal-outer"):
            with Vertical(classes="modal-box"):
                yield Label(f"🔑 {e.name}", classes="modal-title")
                with ScrollableContainer():
                    for k, v in rows:
                        with Horizontal(classes="modal-row"):
                            yield Label(f"{k}:", classes="modal-label")
                            yield Label(v, markup=False)
                with Horizontal(classes="modal-actions"):
                    yield Button("Copy Value", variant="primary", id="btn-copy")
                    yield Button("Close", variant="default", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-copy":
            try:
                value = decrypt_entry_value(
                    self._master_key, self._entry.id,
                    bytes.fromhex(self._entry.nonce_hex),
                    bytes.fromhex(self._entry.cipher_hex),
                )
                copy_to_clipboard(value, key_name=self._entry.name,
                                  timeout=cfg.clipboard_clear_seconds)
                self._entry.access_count += 1
                self._entry.last_accessed_at = datetime.now(timezone.utc)
                self.app.notify(  # type: ignore[attr-defined]
                    f"Copied. Clears in {cfg.clipboard_clear_seconds}s.",
                    severity="information",
                )
            except Exception as ex:  # noqa: BLE001
                self.app.notify(f"Error: {ex}", severity="error")  # type: ignore[attr-defined]
        elif event.button.id == "btn-close":
            self.dismiss()


class AddKeyModal(ModalScreen[Optional[dict]]):
    """
    Modal to add a new API key entry.
    Returns a dict with form data, or None on cancel.
    """

    CSS = _COMMON_CSS

    def compose(self) -> ComposeResult:
        with Container(classes="modal-outer"):
            with Vertical(classes="modal-box"):
                yield Label("➕ Add New Key", classes="modal-title")
                with ScrollableContainer():
                    with Horizontal(classes="modal-row"):
                        yield Label("Name *", classes="modal-label")
                        yield Input(placeholder="my-openai-key", id="f-name")
                    with Horizontal(classes="modal-row"):
                        yield Label("Value *", classes="modal-label")
                        yield Input(placeholder="sk-...", password=True, id="f-value")
                    with Horizontal(classes="modal-row"):
                        yield Label("Service", classes="modal-label")
                        yield Input(placeholder="OpenAI", id="f-service")
                    with Horizontal(classes="modal-row"):
                        yield Label("Description", classes="modal-label")
                        yield Input(placeholder="Production key", id="f-description")
                    with Horizontal(classes="modal-row"):
                        yield Label("Tags", classes="modal-label")
                        yield Input(placeholder="prod, openai, ml", id="f-tags")
                    with Horizontal(classes="modal-row"):
                        yield Label("Expires (YYYY-MM-DD)", classes="modal-label")
                        yield Input(placeholder="2026-12-31", id="f-expires")
                    with Horizontal(classes="modal-row"):
                        yield Label("Environment", classes="modal-label")
                        yield Input(placeholder="production", id="f-environment")
                yield Label("", id="add-error", classes="error-label")
                with Horizontal(classes="modal-actions"):
                    yield Button("Cancel", variant="default", id="btn-cancel")
                    yield Button("🔒 Generate", variant="default", id="btn-generate")
                    yield Button("➕ Add", variant="primary", id="btn-add")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-generate":
            self.query_one("#f-value", Input).value = _generate_secret(32, "alphanum")
        elif event.button.id == "btn-add":
            self._submit()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        name = self.query_one("#f-name", Input).value.strip()
        value = self.query_one("#f-value", Input).value.strip()
        error = self.query_one("#add-error", Label)

        if not name:
            error.update("❌ Name is required")
            return
        if not value:
            error.update("❌ Value is required")
            return

        expires_raw = self.query_one("#f-expires", Input).value.strip()
        expires_at: Optional[datetime] = None
        if expires_raw:
            try:
                expires_at = datetime.strptime(expires_raw, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                error.update("❌ Invalid date format (use YYYY-MM-DD)")
                return

        tags_raw = self.query_one("#f-tags", Input).value
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        self.dismiss({
            "name": name,
            "value": value,
            "service": self.query_one("#f-service", Input).value.strip(),
            "description": self.query_one("#f-description", Input).value.strip(),
            "tags": tags,
            "expires_at": expires_at,
            "environment": self.query_one("#f-environment", Input).value.strip(),
        })


class EditKeyModal(ModalScreen[Optional[dict]]):
    """Edit an existing entry (cannot change value here — security)."""

    CSS = _COMMON_CSS

    def __init__(self, entry: APIKeyEntry) -> None:
        super().__init__()
        self._entry = entry

    def compose(self) -> ComposeResult:
        e = self._entry
        expires_str = e.expires_at.strftime("%Y-%m-%d") if e.expires_at else ""
        with Container(classes="modal-outer"):
            with Vertical(classes="modal-box"):
                yield Label(f"✏️ Edit: {e.name}", classes="modal-title")
                with ScrollableContainer():
                    with Horizontal(classes="modal-row"):
                        yield Label("Service", classes="modal-label")
                        yield Input(value=e.service or "", id="f-service")
                    with Horizontal(classes="modal-row"):
                        yield Label("Description", classes="modal-label")
                        yield Input(value=e.description or "", id="f-description")
                    with Horizontal(classes="modal-row"):
                        yield Label("Tags", classes="modal-label")
                        yield Input(value=", ".join(e.tags), id="f-tags")
                    with Horizontal(classes="modal-row"):
                        yield Label("Expires (YYYY-MM-DD)", classes="modal-label")
                        yield Input(value=expires_str, id="f-expires")
                    with Horizontal(classes="modal-row"):
                        yield Label("Environment", classes="modal-label")
                        yield Input(value=getattr(e, "environment", "") or "", id="f-environment")
                    with Horizontal(classes="modal-row"):
                        yield Label("Status", classes="modal-label")
                        yield Select(
                            [("active", "active"), ("revoked", "revoked"),
                             ("expired", "expired"), ("deprecated", "deprecated")],
                            value=e.status_label,
                            id="f-status",
                        )
                yield Label("", id="edit-error", classes="error-label")
                with Horizontal(classes="modal-actions"):
                    yield Button("Cancel", variant="default", id="btn-cancel")
                    yield Button("✅ Save", variant="primary", id="btn-save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._submit()

    def _submit(self) -> None:
        error = self.query_one("#edit-error", Label)
        expires_raw = self.query_one("#f-expires", Input).value.strip()
        expires_at: Optional[datetime] = None
        if expires_raw:
            try:
                expires_at = datetime.strptime(expires_raw, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                error.update("❌ Invalid date format (use YYYY-MM-DD)")
                return

        tags_raw = self.query_one("#f-tags", Input).value
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        status_sel = self.query_one("#f-status", Select)

        self.dismiss({
            "service": self.query_one("#f-service", Input).value.strip(),
            "description": self.query_one("#f-description", Input).value.strip(),
            "tags": tags,
            "expires_at": expires_at,
            "environment": self.query_one("#f-environment", Input).value.strip(),
            "status": str(status_sel.value) if status_sel.value else "active",
        })


class GeneratorModal(ModalScreen):
    """Secure random password / API token generator."""

    CSS = _COMMON_CSS
    _generated: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        with Container(classes="modal-outer"):
            with Vertical(classes="modal-box"):
                yield Label("🎲 Secret Generator", classes="modal-title")
                with Horizontal(classes="modal-row"):
                    yield Label("Length", classes="modal-label")
                    yield Input(value="32", id="g-length")
                with Horizontal(classes="modal-row"):
                    yield Label("Charset", classes="modal-label")
                    yield Select(
                        [("All (letters+digits+symbols)", "all"),
                         ("Alphanumeric", "alphanum"),
                         ("Hex (lowercase)", "hex"),
                         ("Letters only", "alpha")],
                        value="all",
                        id="g-charset",
                    )
                yield Static("(output)", id="g-output", classes="gen-output")
                with Horizontal(classes="modal-actions"):
                    yield Button("Close", variant="default", id="btn-close")
                    yield Button("🔄 Generate", variant="primary", id="btn-generate")
                    yield Button("📋 Copy", variant="success", id="btn-copy")

    def on_mount(self) -> None:
        self._do_generate()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-generate":
            self._do_generate()
        elif event.button.id == "btn-copy":
            if self._generated:
                copy_to_clipboard(self._generated, key_name="generated",
                                  timeout=cfg.clipboard_clear_seconds)
                self.app.notify("Copied to clipboard!", severity="information")  # type: ignore
        elif event.button.id == "btn-close":
            self.dismiss()

    def _do_generate(self) -> None:
        try:
            length = int(self.query_one("#g-length", Input).value or "32")
            length = max(8, min(256, length))
        except ValueError:
            length = 32
        charset_sel = self.query_one("#g-charset", Select)
        charset = str(charset_sel.value) if charset_sel.value else "all"
        self._generated = _generate_secret(length, charset)
        self.query_one("#g-output", Static).update(self._generated)


# ================================================================== #
# Unlock Screen
# ================================================================== #

class UnlockScreen(Screen):
    """Full-screen password prompt with brute-force counter."""

    CSS = _COMMON_CSS + """
    UnlockScreen { align: center middle; }
    #unlock-container {
        width: 64;
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
    #attempts-label {
        text-align: center;
        color: $warning;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="unlock-container"):
            yield Label("🔐 VaultKey", id="unlock-title")
            yield Label("Master password:", markup=False)
            yield Input(placeholder="Enter master password",
                        password=True, id="password-input")
            yield Button("Unlock ▶", variant="primary", id="unlock-btn")
            yield Label("", id="error-label", classes="error-label")
            yield Label("", id="attempts-label")

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "unlock-btn":
            self._attempt_unlock()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._attempt_unlock()

    def _attempt_unlock(self) -> None:
        from wallet.core.kdf import derive_key, verify_master_password
        password = self.query_one("#password-input", Input).value
        error_label = self.query_one("#error-label", Label)
        attempts_label = self.query_one("#attempts-label", Label)

        try:
            params = storage.read_kdf_params()
            key = derive_key(password, params)
            data = storage.load(key)
            payload = WalletPayload.from_dict(data)
        except Exception:  # noqa: BLE001
            session.record_failed_attempt()
            fa = session.info["failed_attempts"]
            error_label.update("❌ Wrong password")
            attempts_label.update(f"Failed attempts: {fa} / {session.info['max_failed_attempts']}")
            self.query_one("#password-input", Input).value = ""
            return

        from wallet.core.kdf import verify_master_password
        if not verify_master_password(password, payload.master_hash):
            session.record_failed_attempt()
            fa = session.info["failed_attempts"]
            error_label.update("❌ Wrong password")
            attempts_label.update(f"Failed attempts: {fa} / {session.info['max_failed_attempts']}")
            self.query_one("#password-input", Input).value = ""
            return

        session.unlock(key)
        self.app.pop_screen()  # type: ignore[attr-defined]


# ================================================================== #
# Tab Panels
# ================================================================== #

class KeysPanel(Container):
    """DataTable of all API keys with live search, add/edit/delete/copy."""

    CSS = """
    KeysPanel { height: 100%; }
    #search-bar { height: 3; margin-bottom: 0; }
    #keys-actions { height: 3; padding: 0 1; }
    """

    def __init__(self, payload: WalletPayload, master_key: bytes, **kw) -> None:
        super().__init__(**kw)
        self._payload = payload
        self._master_key = master_key
        self._filtered: list[APIKeyEntry] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar"):
            yield Input(placeholder="🔍  Search by name, service, or tag…",
                        id="search-input")
        with Horizontal(id="keys-actions"):
            yield Button("➕ Add", variant="success", id="btn-add")
            yield Button("✏️ Edit", variant="default", id="btn-edit")
            yield Button("🗑️ Delete", variant="error", id="btn-delete")
            yield Button("📋 Copy", variant="primary", id="btn-copy")
            yield Button("ℹ️ Info", variant="default", id="btn-info")
            yield Button("🎲 Generate", variant="default", id="btn-gen")
        yield DataTable(id="keys-table", cursor_type="row")
        yield Static(
            "[Enter/C] Copy  [I] Info  [N] Add  [E] Edit  [D] Delete  [G] Generator  [/] Search",
            classes="panel-help",
        )

    def on_mount(self) -> None:
        table = self.query_one("#keys-table", DataTable)
        table.add_columns(
            "Name", "Service", "Tags", "Added",
            "Expires", "Health", "Times Used",
        )
        self._refresh_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._refresh_table(query=event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-add":
            self.app.action_add_key()  # type: ignore
        elif btn_id == "btn-edit":
            self.app.action_edit_selected()  # type: ignore
        elif btn_id == "btn-delete":
            self.app.action_delete_selected()  # type: ignore
        elif btn_id == "btn-copy":
            self.action_copy()
        elif btn_id == "btn-info":
            self.app.action_show_info()  # type: ignore
        elif btn_id == "btn-gen":
            self.app.action_generator()  # type: ignore

    def _refresh_table(self, query: str = "") -> None:
        table = self.query_one("#keys-table", DataTable)
        table.clear()
        results = self._payload.search(query=query)
        self._filtered = sorted(results, key=lambda e: e.name.lower())
        for e in self._filtered:
            eh = analyze_entry(e)
            exp_label, _ = _expiry_status(e)
            table.add_row(
                e.name,
                e.service or "—",
                ", ".join(e.tags) or "—",
                e.created_at.strftime("%Y-%m-%d"),
                exp_label,
                f"{eh.grade} ({eh.score})",
                str(e.access_count),
                key=e.id,
            )

    def selected_entry(self) -> Optional[APIKeyEntry]:
        table = self.query_one("#keys-table", DataTable)
        if not self._filtered or table.cursor_row < 0:
            return None
        if table.cursor_row >= len(self._filtered):
            return None
        return self._filtered[table.cursor_row]

    def action_copy(self) -> None:
        entry = self.selected_entry()
        if not entry:
            self.app.notify("No entry selected.", severity="warning")  # type: ignore
            return
        try:
            value = decrypt_entry_value(
                self._master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
            copy_to_clipboard(value, key_name=entry.name,
                              timeout=cfg.clipboard_clear_seconds)
            entry.access_count += 1
            entry.last_accessed_at = datetime.now(timezone.utc)
            self.app.notify(  # type: ignore
                f"📋 Copied '{entry.name}'. Clears in {cfg.clipboard_clear_seconds}s.",
                severity="information",
            )
        except Exception as ex:  # noqa: BLE001
            self.app.notify(f"Error copying: {ex}", severity="error")  # type: ignore

    def reload(self) -> None:
        self._refresh_table(
            self.query_one("#search-input", Input).value
        )


class HealthPanel(Container):
    """Health scores per entry + overall wallet grade."""

    CSS = "HealthPanel { height: 100%; }"

    def __init__(self, payload: WalletPayload, **kw) -> None:
        super().__init__(**kw)
        self._payload = payload

    def compose(self) -> ComposeResult:
        wh = analyze_wallet(self._payload)
        grade_icon = {
            "A": "✅", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"
        }.get(wh.overall_grade, "🔵")
        grade_css = f"grade-{wh.overall_grade.lower()}"
        yield Static(
            f"{grade_icon}  Overall grade: [{grade_css}]{wh.overall_grade}[/]  "
            f"({wh.overall_score}/100) │ "
            f"✅ {wh.healthy} healthy │ "
            f"⚠️ {wh.warning} warning │ "
            f"🔴 {wh.critical} critical",
            classes="health-summary",
        )
        with ScrollableContainer():
            yield DataTable(id="health-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#health-table", DataTable)
        table.add_columns("Name", "Score", "Grade", "Top Issue", "Recommendation")
        wh = analyze_wallet(self._payload)
        for eh in sorted(wh.entries, key=lambda x: x.score):
            table.add_row(
                eh.name,
                str(eh.score),
                eh.grade,
                (eh.issues[0] if eh.issues else "✔ OK"),
                (eh.recommendations[0] if eh.recommendations else "—"),
            )
        yield Static(
            "Entries sorted by score (lowest first)",
            classes="panel-help",
        )


class ExpiryPanel(Container):
    """All entries with expiry status, sorted urgent-first."""

    CSS = "ExpiryPanel { height: 100%; }"

    def __init__(self, payload: WalletPayload, **kw) -> None:
        super().__init__(**kw)
        self._payload = payload

    def compose(self) -> ComposeResult:
        entries = self._payload.entries
        now = datetime.now(timezone.utc)
        expired = [e for e in entries if e.expires_at and e.expires_at < now]
        soon = [e for e in entries if e.expires_at and
                timedelta(0) <= e.expires_at - now <= timedelta(days=30)]
        ok = [e for e in entries if e.expires_at and e.expires_at - now > timedelta(days=30)]
        no_expiry = [e for e in entries if not e.expires_at]

        with ScrollableContainer():
            if expired:
                yield Static(f"🔴 EXPIRED ({len(expired)})",
                             classes="panel-title expiry-expired")
                yield DataTable(id="table-expired", cursor_type="row")
            if soon:
                yield Static(f"⚠️ Expiring soon — within 30 days ({len(soon)})",
                             classes="panel-title expiry-warning")
                yield DataTable(id="table-soon", cursor_type="row")
            if ok:
                yield Static(f"✅ Valid ({len(ok)})",
                             classes="panel-title expiry-ok")
                yield DataTable(id="table-ok", cursor_type="row")
            if no_expiry:
                yield Static(f"— No expiry set ({len(no_expiry)})",
                             classes="panel-title")
                yield DataTable(id="table-noexpiry", cursor_type="row")

        self._expired = expired
        self._soon = soon
        self._ok = ok
        self._no_expiry = no_expiry

    def on_mount(self) -> None:
        cols = ("Name", "Service", "Expires", "Days Left")
        for table_id, entries in [
            ("#table-expired", self._expired),
            ("#table-soon", self._soon),
            ("#table-ok", self._ok),
            ("#table-noexpiry", self._no_expiry),
        ]:
            try:
                table = self.query_one(table_id, DataTable)
                table.add_columns(*cols)
                now = datetime.now(timezone.utc)
                for e in sorted(entries, key=lambda x: x.expires_at or datetime.max.replace(tzinfo=timezone.utc)):
                    exp_str = e.expires_at.strftime("%Y-%m-%d") if e.expires_at else "—"
                    days_left = (
                        str((e.expires_at - now).days)
                        if e.expires_at else "—"
                    )
                    table.add_row(e.name, e.service or "—", exp_str, days_left)
            except Exception:  # noqa: BLE001
                pass


class AuditPanel(Container):
    """Filterable audit log viewer (last 200 events)."""

    CSS = "AuditPanel { height: 100%; }"

    _filter: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        with Horizontal(id="audit-search-bar"):
            yield Input(placeholder="🔍  Filter by event name or key…",
                        id="audit-filter")
            yield Button("🔄 Refresh", variant="default", id="btn-audit-refresh")
        yield DataTable(id="audit-table", cursor_type="row")
        yield Static(
            f"Showing last 200 events from {cfg.audit_log_path}",
            classes="panel-help",
        )

    def on_mount(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.add_columns("Timestamp", "Event", "Status", "Key", "Extra")
        self._load_events()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "audit-filter":
            self._filter = event.value
            self._load_events(query=event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-audit-refresh":
            self._load_events(self.query_one("#audit-filter", Input).value)

    def _load_events(self, query: str = "") -> None:
        table = self.query_one("#audit-table", DataTable)
        table.clear()
        events = read_audit_log(last_n=200)
        q = query.lower()
        for ev in reversed(events):
            event_name = ev.get("event", "")
            key_name = ev.get("key_name", "") or ""
            extra = ev.get("extra", "") or ""
            if q and q not in event_name.lower() and q not in key_name.lower():
                continue
            ts = ev.get("ts", "")[:19].replace("T", " ")
            status = ev.get("status", "")
            status_mark = "✓" if status == "OK" else "❌"
            table.add_row(ts, event_name, status_mark, key_name, extra)


class StatusPanel(Container):
    """Live session countdown + security configuration overview."""

    CSS = _COMMON_CSS + """
    StatusPanel { height: 100%; }
    #countdown-bar { margin-bottom: 1; }
    """

    _tick: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Label("📊 Session Status", classes="panel-title")
        yield Static("", id="countdown-display")
        yield Static("", id="session-details")
        yield Label("⚙️ Configuration", classes="panel-title")
        yield Static("", id="config-details")

    def on_mount(self) -> None:
        self._update_display()
        self.set_interval(1.0, self._tick_handler)

    def _tick_handler(self) -> None:
        self._tick += 1

    def watch__tick(self, _: int) -> None:
        self._update_display()

    def _update_display(self) -> None:
        info = session.info
        secs = info.get("seconds_until_lock")

        # Countdown
        if secs is not None:
            mins, s = divmod(secs, 60)
            if secs <= 60:
                css_class = "countdown-crit"
                icon = "🔴"
            elif secs <= 300:
                css_class = "countdown-warn"
                icon = "⚠️"
            else:
                css_class = "countdown-ok"
                icon = "🟢"
            countdown_text = (
                f"{icon}  Session locks in: [{css_class}]{mins:02d}:{s:02d}[/]  "
                f"(timeout: {info['timeout_minutes']} min)"
            )
        else:
            countdown_text = "🔒 Session is [bold red]LOCKED[/]"

        try:
            self.query_one("#countdown-display", Static).update(countdown_text)
        except Exception:  # noqa: BLE001
            pass

        # Session details
        session_text = "\n".join([
            f"  Unlocked at:    {info.get('unlocked_at') or '—'}",
            f"  Last activity:  {info.get('last_activity') or '—'}",
            f"  Failed attempts:{info.get('failed_attempts', 0)} / {info.get('max_failed_attempts', 5)}",
        ])
        try:
            self.query_one("#session-details", Static).update(session_text)
        except Exception:  # noqa: BLE001
            pass

        # Config
        config_text = "\n".join([
            f"  Wallet file:    {cfg.wallet_path}",
            f"  Backup dir:     {cfg.backup_dir}",
            f"  Audit log:      {cfg.audit_log_path}",
            f"  Clipboard clear:{cfg.clipboard_clear_seconds}s",
            f"  Integrity check:{'enabled' if cfg.enable_integrity_check else 'disabled'}",
            f"  Max backups:    {cfg.max_backups}",
        ])
        try:
            self.query_one("#config-details", Static).update(config_text)
        except Exception:  # noqa: BLE001
            pass


# ================================================================== #
# Main App
# ================================================================== #

class VaultKeyApp(App):
    """Complete Textual TUI application for VaultKey."""

    TITLE = "VaultKey 🔐"
    SUB_TITLE = "Ultra-Secure API Key Wallet"

    CSS = _COMMON_CSS + """
    TabbedContent { height: 1fr; }
    TabPane { height: 100%; padding: 0; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("l", "lock_wallet", "Lock"),
        Binding("n", "add_key", "New Key"),
        Binding("e", "edit_selected", "Edit", show=False),
        Binding("enter", "copy_selected", "Copy", show=False),
        Binding("c", "copy_selected", "Copy", show=False),
        Binding("i", "show_info", "Info", show=False),
        Binding("d", "delete_selected", "Delete", show=False),
        Binding("g", "generator", "Generator", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("/", "focus_search", "Search", show=False),
    ]

    def __init__(self, payload: WalletPayload, master_key: bytes) -> None:
        super().__init__()
        self._payload = payload
        self._master_key = master_key

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("🗝️ Keys", id="tab-keys"):
                yield KeysPanel(
                    self._payload, self._master_key, id="keys-panel"
                )
            with TabPane("📊 Health", id="tab-health"):
                yield HealthPanel(self._payload, id="health-panel")
            with TabPane("⏰ Expiry", id="tab-expiry"):
                yield ExpiryPanel(self._payload, id="expiry-panel")
            with TabPane("📝 Audit", id="tab-audit"):
                yield AuditPanel(id="audit-panel")
            with TabPane("📁 Status", id="tab-status"):
                yield StatusPanel(id="status-panel")
        yield Footer()

    # ---- Actions -------------------------------------------------- #

    def action_quit(self) -> None:
        session.lock(reason="tui_quit")
        self.exit()

    def action_lock_wallet(self) -> None:
        session.lock(reason="tui_manual_lock")
        self.notify("🔒 Wallet locked.", severity="warning")
        self.exit()

    def action_focus_search(self) -> None:
        try:
            self.query_one("#search-input", Input).focus()
        except Exception:  # noqa: BLE001
            pass

    def action_refresh(self) -> None:
        try:
            self.query_one("#keys-panel", KeysPanel).reload()
            self.notify("🔄 Refreshed.", severity="information")
        except Exception:  # noqa: BLE001
            pass

    def action_copy_selected(self) -> None:
        try:
            self.query_one("#keys-panel", KeysPanel).action_copy()
        except Exception:  # noqa: BLE001
            pass

    def action_show_info(self) -> None:
        try:
            entry = self.query_one("#keys-panel", KeysPanel).selected_entry()
            if entry:
                self.push_screen(KeyDetailModal(entry, self._master_key))
            else:
                self.notify("No entry selected.", severity="warning")
        except Exception:  # noqa: BLE001
            pass

    def action_generator(self) -> None:
        self.push_screen(GeneratorModal())

    def action_add_key(self) -> None:
        def _handle(result: Optional[dict]) -> None:
            if not result:
                return
            try:
                nonce, cipher = encrypt_entry_value(
                    self._master_key, result["value"]
                )
                entry = APIKeyEntry(
                    name=result["name"],
                    service=result["service"],
                    description=result["description"],
                    tags=result["tags"],
                    expires_at=result["expires_at"],
                    nonce_hex=nonce.hex(),
                    cipher_hex=cipher.hex(),
                    environment=result.get("environment", ""),
                )
                self._payload.add_entry(entry)
                key = session.get_key()
                storage.save(self._payload.to_dict(), key)
                self.query_one("#keys-panel", KeysPanel).reload()
                self.notify(f"✅ Added '{result['name']}'", severity="information")
            except Exception as ex:  # noqa: BLE001
                self.notify(f"Error: {ex}", severity="error")

        self.push_screen(AddKeyModal(), callback=_handle)

    def action_edit_selected(self) -> None:
        try:
            entry = self.query_one("#keys-panel", KeysPanel).selected_entry()
        except Exception:  # noqa: BLE001
            return
        if not entry:
            self.notify("No entry selected.", severity="warning")
            return

        def _handle(result: Optional[dict]) -> None:
            if not result:
                return
            try:
                entry.service = result["service"]
                entry.description = result["description"]
                entry.tags = result["tags"]
                entry.expires_at = result["expires_at"]
                if hasattr(entry, "environment"):
                    entry.environment = result.get("environment", "")
                key = session.get_key()
                storage.save(self._payload.to_dict(), key)
                self.query_one("#keys-panel", KeysPanel).reload()
                self.notify(f"✅ Updated '{entry.name}'", severity="information")
            except Exception as ex:  # noqa: BLE001
                self.notify(f"Error: {ex}", severity="error")

        self.push_screen(EditKeyModal(entry), callback=_handle)

    def action_delete_selected(self) -> None:
        try:
            entry = self.query_one("#keys-panel", KeysPanel).selected_entry()
        except Exception:  # noqa: BLE001
            return
        if not entry:
            self.notify("No entry selected.", severity="warning")
            return

        def _handle(confirmed: bool) -> None:
            if not confirmed:
                return
            try:
                self._payload.remove_entry(entry.id)
                key = session.get_key()
                storage.save(self._payload.to_dict(), key)
                self.query_one("#keys-panel", KeysPanel).reload()
                self.notify(f"🗑️ Deleted '{entry.name}'", severity="warning")
            except Exception as ex:  # noqa: BLE001
                self.notify(f"Error: {ex}", severity="error")

        self.push_screen(ConfirmDeleteModal(entry.name), callback=_handle)


# ================================================================== #
# Entry Point
# ================================================================== #

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
