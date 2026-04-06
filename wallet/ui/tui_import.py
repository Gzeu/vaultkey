"""
tui_import.py — Standalone Textual screen for bulk CSV/JSON import preview.

Used as a ModalScreen pushed from the main TUI (MainApp):

    from wallet.ui.tui_import import ImportScreen
    self.push_screen(ImportScreen(master_key=key, payload=payload, storage=storage))

Flow:
  1. User pastes a file path or drag-drops a .csv / .json file path
  2. Preview DataTable shows parsed rows with validation status
  3. Rows with errors are highlighted in red; user can skip them
  4. "Import X valid rows" button calls bulk_import.import_from_csv / import_from_json
     and saves the wallet
  5. Screen returns the number of imported entries to the caller
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static

from wallet.core.crypto import encrypt_entry_value
from wallet.core.storage import WalletStorage
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.bulk_import import parse_csv, parse_json, ImportRow, ImportResult


CSS = """
ImportScreen {
    align: center middle;
    background: $background 60%;
}
.import-box {
    background: $surface;
    border: double $accent;
    padding: 1 2;
    width: 90;
    height: 40;
}
.import-title {
    text-align: center;
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}
.import-help {
    color: $text-muted;
    height: 1;
    margin-bottom: 1;
}
.import-stats {
    height: 1;
    color: $text;
    margin-top: 1;
}
.row-ok { color: $success; }
.row-err { color: $error; }
.import-actions {
    margin-top: 1;
    height: auto;
    align: center middle;
}
"""


class ImportScreen(ModalScreen[int]):
    """
    Bulk import screen.  Returns the count of imported entries on dismiss.
    Returns 0 if cancelled or no rows were imported.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    CSS_DEFAULT_CSS = CSS

    def __init__(
        self,
        master_key: bytes,
        payload: WalletPayload,
        storage: WalletStorage,
        **kw,
    ) -> None:
        super().__init__(**kw)
        self._master_key = master_key
        self._payload = payload
        self._storage = storage
        self._rows: list[ImportRow] = []
        self._valid_count = 0

    def compose(self) -> ComposeResult:
        with Container(classes="import-box"):
            with Vertical():
                yield Label("📥 Bulk Import", classes="import-title")
                yield Static(
                    "Enter path to .csv or .json file:",
                    classes="import-help",
                )
                with Horizontal():
                    yield Input(
                        placeholder="/path/to/keys.csv  or  /path/to/keys.json",
                        id="import-path",
                    )
                    yield Button("Preview", variant="primary", id="btn-preview")
                yield Label("", id="parse-error", classes="row-err")
                with ScrollableContainer():
                    yield DataTable(id="import-table", cursor_type="row")
                yield Static("", id="import-stats", classes="import-stats")
                with Horizontal(classes="import-actions"):
                    yield Button("Cancel", variant="default", id="btn-cancel")
                    yield Button(
                        "Import 0 valid rows",
                        variant="success",
                        id="btn-import",
                        disabled=True,
                    )

    def on_mount(self) -> None:
        table = self.query_one("#import-table", DataTable)
        table.add_columns("#", "Name", "Service", "Tags", "Expires", "Status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-preview":
            self._do_preview()
        elif event.button.id == "btn-import":
            self._do_import()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._do_preview()

    def action_cancel(self) -> None:
        self.dismiss(0)

    def _do_preview(self) -> None:
        raw_path = self.query_one("#import-path", Input).value.strip()
        err_label = self.query_one("#parse-error", Label)
        err_label.update("")

        path = Path(raw_path)
        if not path.exists():
            err_label.update(f"❌ File not found: {raw_path}")
            return

        try:
            if path.suffix.lower() == ".json":
                rows = parse_json(path)
            else:
                rows = parse_csv(path)
        except Exception as exc:  # noqa: BLE001
            err_label.update(f"❌ Parse error: {exc}")
            return

        self._rows = rows
        table = self.query_one("#import-table", DataTable)
        table.clear()

        self._valid_count = 0
        for i, row in enumerate(rows, 1):
            status_cls = "row-ok" if row.valid else "row-err"
            status_text = "✔ OK" if row.valid else f"✘ {row.error}"
            if row.valid:
                self._valid_count += 1
            table.add_row(
                str(i),
                row.name or "(missing)",
                row.service or "—",
                ", ".join(row.tags) if row.tags else "—",
                str(row.expires_at.date()) if row.expires_at else "—",
                f"[{status_cls}]{status_text}[/]",
            )

        stats = self.query_one("#import-stats", Static)
        stats.update(
            f"Found {len(rows)} rows — {self._valid_count} valid, "
            f"{len(rows) - self._valid_count} invalid (will be skipped)"
        )

        btn = self.query_one("#btn-import", Button)
        if self._valid_count > 0:
            btn.label = f"Import {self._valid_count} valid rows"  # type: ignore[assignment]
            btn.disabled = False
        else:
            btn.label = "Import 0 valid rows"  # type: ignore[assignment]
            btn.disabled = True

    def _do_import(self) -> None:
        imported = 0
        for row in self._rows:
            if not row.valid:
                continue
            try:
                nonce, cipher = encrypt_entry_value(
                    self._master_key, row.entry_id, row.value
                )
                entry = APIKeyEntry(
                    id=row.entry_id,
                    name=row.name,
                    service=row.service,
                    description=row.description,
                    tags=row.tags or [],
                    expires_at=row.expires_at,
                    nonce_hex=nonce.hex(),
                    cipher_hex=cipher.hex(),
                )
                self._payload.add_entry(entry)
                imported += 1
            except Exception:  # noqa: BLE001
                pass

        if imported > 0:
            self._storage.save(self._payload.to_dict(), self._master_key)

        self.dismiss(imported)
