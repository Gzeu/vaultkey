"""
tui.py — Textual-based full-screen TUI for VaultKey.

Layout:
  - Left panel: searchable list of all API keys with status badges
  - Right panel: key detail view
  - Footer: keyboard shortcut hints
  - Color coding: green=active, yellow=expiring, red=expired, dim=revoked

Keyboard shortcuts:
  Ctrl+A  — Add new key
  Ctrl+D  — Delete selected key
  Ctrl+C  — Copy selected key to clipboard
  Ctrl+R  — Rotate selected key
  Ctrl+Q  — Quit
  /       — Focus search bar
"""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Input, ListView, ListItem,
    Label, Button, Static, RichLog
)
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from rich.text import Text

from wallet.core.crypto import decrypt_entry_value
from wallet.core.session import SessionManager, WalletLockedException
from wallet.core.storage import WalletStorage
from wallet.models.config import WalletConfig
from wallet.models.wallet import WalletPayload, APIKeyEntry
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.prefix_detect import mask_key

cfg = WalletConfig()
storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)
session = SessionManager()

STATUS_COLORS = {
    "active": "green",
    "expiring": "yellow",
    "expired": "red",
    "revoked": "bright_black",
}


class KeyListItem(ListItem):
    def __init__(self, entry: APIKeyEntry):
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        color = STATUS_COLORS.get(self.entry.status_label, "white")
        text = Text()
        text.append(f" {self.entry.name:<30}", style="bold")
        text.append(f"{self.entry.service:<15}")
        text.append(f"[{self.entry.status_label}]", style=color)
        yield Label(text)


class DetailPanel(Static):
    def show_entry(self, entry: APIKeyEntry) -> None:
        color = STATUS_COLORS.get(entry.status_label, "white")
        self.update(
            f"[bold]{entry.name}[/bold]\n"
            f"Service:    {entry.service}\n"
            f"Prefix:     {entry.prefix or '—'}\n"
            f"Tags:       {', '.join(entry.tags) or '—'}\n"
            f"Desc:       {entry.description or '—'}\n"
            f"Created:    {entry.created_at.strftime('%Y-%m-%d')}\n"
            f"Expires:    {entry.expires_at.strftime('%Y-%m-%d') if entry.expires_at else '—'}\n"
            f"Accesses:   {entry.access_count}\n"
            f"Status:     [{color}]{entry.status_label}[/{color}]"
        )

    def clear(self) -> None:
        self.update("[dim]Select a key to view details[/dim]")


class VaultKeyTUI(App):
    CSS = """
    Screen { background: $surface; }
    #left-panel { width: 55%; border-right: solid $primary; padding: 1; }
    #right-panel { width: 45%; padding: 1; }
    #search { margin-bottom: 1; }
    #detail { padding: 1; border: solid $accent; height: auto; }
    #action-bar { height: 3; dock: bottom; align: center middle; }
    KeyListItem { height: 1; }
    KeyListItem:focus { background: $accent 30%; }
    """

    BINDINGS = [
        Binding("ctrl+a", "add_key", "Add"),
        Binding("ctrl+d", "delete_key", "Delete"),
        Binding("ctrl+c", "copy_key", "Copy"),
        Binding("ctrl+r", "rotate_key", "Rotate"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("/", "focus_search", "Search"),
    ]

    query_filter: reactive[str] = reactive("")

    def __init__(self, payload: WalletPayload, master_key: bytes):
        super().__init__()
        self.payload = payload
        self.master_key = master_key
        self._all_entries: list[APIKeyEntry] = list(payload.keys.values())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left-panel"):
                yield Input(placeholder="/ to search...", id="search")
                yield ListView(*[KeyListItem(e) for e in self._all_entries], id="key-list")
            with Vertical(id="right-panel"):
                yield DetailPanel("[dim]Select a key to view details[/dim]", id="detail")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, KeyListItem):
            self.query_one("#detail", DetailPanel).show_entry(event.item.entry)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self._filter_list(event.value)

    def _filter_list(self, query: str) -> None:
        lv = self.query_one("#key-list", ListView)
        lv.clear()
        filtered = [
            e for e in self._all_entries
            if query.lower() in e.name.lower() or query.lower() in e.service.lower()
        ]
        for e in filtered:
            lv.append(KeyListItem(e))

    def _selected_entry(self) -> APIKeyEntry | None:
        lv = self.query_one("#key-list", ListView)
        if lv.highlighted_child and isinstance(lv.highlighted_child, KeyListItem):
            return lv.highlighted_child.entry
        return None

    def action_copy_key(self) -> None:
        entry = self._selected_entry()
        if not entry:
            self.notify("No key selected", severity="warning")
            return
        value = decrypt_entry_value(
            self.master_key, entry.id,
            bytes.fromhex(entry.nonce_hex),
            bytes.fromhex(entry.cipher_hex)
        )
        copy_to_clipboard(value, key_name=entry.name)
        self.notify(f"Copied: {entry.name}")

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_delete_key(self) -> None:
        entry = self._selected_entry()
        if entry:
            self.notify(f"Use CLI: wallet delete '{entry.name}'", severity="warning")

    def action_add_key(self) -> None:
        self.notify("Use CLI: wallet add", severity="information")

    def action_rotate_key(self) -> None:
        entry = self._selected_entry()
        if entry:
            self.notify(f"Use CLI: wallet rotate '{entry.name}'", severity="information")


def run_tui() -> None:
    try:
        key = session.get_key()
    except WalletLockedException:
        print("Wallet is locked. Run: wallet unlock")
        return
    data = storage.load(key)
    payload = WalletPayload.from_dict(data)
    app = VaultKeyTUI(payload, key)
    app.run()
