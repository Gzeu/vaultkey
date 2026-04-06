"""
gui.py — CustomTkinter GUI for VaultKey (Wave 8 rewrite).

Tabs / Panels:
  Keys         — Scrollable card list, live search, Copy/Info/Rename/Delete per card.
  Expiry       — Expiry checker with urgency colours, days-left countdown.
  Bulk Import  — Import .env / .json / .csv with dry-run preview & conflict strategy.
  Health       — Per-entry health scores, overall grade, recommendations.
  Settings     — Change password, export/import, wallet info, audit viewer.

Wave 8 additions over Wave 4:
  - RenameDialog  : rename a key in-place (no re-encryption).
  - ExpiryTab     : wraps utils.expiry_checker; table with urgency badge.
  - BulkImportTab : file picker → dry-run preview table → apply with strategy.
  - StatusBar     : persistent footer with last-action text + clipboard countdown.
  - Sidebar nav   : icon + label sidebar replaces bare CTkTabview tabs.
  - Auto-expiry banner on unlock if any key expires within 7 days.

Security guarantees (unchanged from Wave 4):
  - No raw key values ever displayed — masked prefix only.
  - Copy → clipboard → auto-clear after cfg.clipboard_clear_seconds.
  - Destructive actions require typed-name confirmation.
  - GUI lock → session.lock(); MainWindow.on_closing() calls same.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from wallet.core.crypto import decrypt_entry_value, encrypt_entry_value
from wallet.core.health import analyze_wallet
from wallet.core.kdf import KDFParams, derive_key, hash_master_password, verify_master_password
from wallet.core.session import SessionManager
from wallet.core.storage import WalletStorage
from wallet.models.config import WalletConfig
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.audit import audit_log, read_audit_log
from wallet.utils.bulk_import import BulkImportResult, apply_bulk_import, parse_file
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.expiry_checker import check_expiry
from wallet.utils.prefix_detect import detect_service
from wallet.utils.validators import parse_expiry_date, validate_api_key_value, validate_key_name

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

cfg     = WalletConfig()
storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)
session = SessionManager()

# ------------------------------------------------------------------ #
# Colour constants
# ------------------------------------------------------------------ #

STATUS_COLORS = {
    "active":   "#4CAF50",
    "expiring": "#FF9800",
    "expired":  "#F44336",
    "revoked":  "#757575",
}
GRADE_COLORS = {
    "A": "#4CAF50",
    "B": "#8BC34A",
    "C": "#FFC107",
    "D": "#FF9800",
    "F": "#F44336",
}
URGENCY_COLORS = {
    "expired":  "#F44336",
    "critical": "#FF5722",
    "warning":  "#FF9800",
    "info":     "#29B6F6",
}

SIDEBAR_BG  = "#111827"
SIDEBAR_W   = 180
CONTENT_BG  = "#1a1a2e"
TOPBAR_H    = 48
STATUSBAR_H = 28

# ------------------------------------------------------------------ #
# Tiny helpers
# ------------------------------------------------------------------ #

def _label_row(parent, text: str, value: str, text_color: str = "gray") -> None:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=4, pady=1)
    ctk.CTkLabel(row, text=text, width=140, anchor="w").pack(side="left")
    ctk.CTkLabel(row, text=value, anchor="w", text_color=text_color).pack(
        side="left", fill="x", expand=True
    )


def _section_title(parent, text: str) -> None:
    ctk.CTkLabel(
        parent, text=text,
        font=("Helvetica", 13, "bold"),
        anchor="w",
    ).pack(fill="x", padx=12, pady=(10, 4))


# ------------------------------------------------------------------ #
# Status Bar
# ------------------------------------------------------------------ #

class StatusBar(ctk.CTkFrame):
    """Persistent footer: last action text + optional clipboard countdown."""

    def __init__(self, parent) -> None:
        super().__init__(parent, height=STATUSBAR_H, fg_color="#0d1117", corner_radius=0)
        self._text_var = ctk.StringVar(value="Ready")
        self._clip_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            self, textvariable=self._text_var,
            anchor="w", text_color="#aaa",
            font=("Helvetica", 11),
        ).pack(side="left", padx=10)
        ctk.CTkLabel(
            self, textvariable=self._clip_var,
            anchor="e", text_color="#FF9800",
            font=("Helvetica", 11),
        ).pack(side="right", padx=10)

    def set(self, msg: str) -> None:
        self._text_var.set(msg)

    def start_clipboard_countdown(self, seconds: int) -> None:
        self._countdown(seconds)

    def _countdown(self, remaining: int) -> None:
        if remaining <= 0:
            self._clip_var.set("")
            return
        self._clip_var.set(f"📋 Clipboard clears in {remaining}s")
        self.after(1000, lambda: self._countdown(remaining - 1))


# ------------------------------------------------------------------ #
# Login Window
# ------------------------------------------------------------------ #

class LoginWindow(ctk.CTk):
    """Master password entry screen."""

    def __init__(self) -> None:
        super().__init__()
        self.title("🔐 VaultKey — Unlock")
        self.geometry("420x320")
        self.resizable(False, False)
        self._authenticated = False
        self._master_key: Optional[bytes] = None
        self._payload: Optional[WalletPayload] = None
        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self, text="🔐 VaultKey",
            font=("Helvetica", 26, "bold"),
        ).pack(pady=(36, 4))
        ctk.CTkLabel(
            self, text="Enter master password to unlock",
            text_color="gray",
        ).pack()

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(pady=16, padx=40, fill="x")

        self._pass_var = ctk.StringVar()
        self._pass_entry = ctk.CTkEntry(
            frame, textvariable=self._pass_var,
            show="•", placeholder_text="Master password",
            width=280, height=40,
        )
        self._pass_entry.pack(side="left")
        self._pass_entry.bind("<Return>", lambda _: self._do_unlock())
        self._pass_entry.focus_set()

        ctk.CTkButton(
            frame, text="👁", width=40, height=40,
            command=self._toggle_show,
        ).pack(side="left", padx=(5, 0))

        self._status = ctk.CTkLabel(self, text="", text_color="#F44336", wraplength=360)
        self._status.pack()

        ctk.CTkButton(
            self, text="Unlock Wallet", height=40, width=200,
            command=self._do_unlock,
        ).pack(pady=12)

    def _toggle_show(self) -> None:
        self._pass_entry.configure(
            show="" if self._pass_entry.cget("show") else "•"
        )

    def _do_unlock(self) -> None:
        password = self._pass_var.get()
        if not password:
            self._status.configure(text="❌ Password cannot be empty.")
            return
        if not storage.exists():
            self._status.configure(text="❌ No wallet found. Run: wallet init")
            return
        try:
            params  = storage.read_kdf_params()
            key     = derive_key(password, params)
            data    = storage.load(key)
            payload = WalletPayload.from_dict(data)
        except Exception:  # noqa: BLE001
            session.record_failed_attempt()
            info = session.info
            self._status.configure(
                text=f"❌ Wrong password. (attempts: {info['failed_attempts']})"
            )
            self._pass_var.set("")
            return

        if not verify_master_password(password, payload.master_hash):
            session.record_failed_attempt()
            self._status.configure(text="❌ Wrong password.")
            self._pass_var.set("")
            return

        session.unlock(key)
        self._master_key = key
        self._payload    = payload
        self._authenticated = True
        self.destroy()


# ------------------------------------------------------------------ #
# Add Key Dialog
# ------------------------------------------------------------------ #

class AddKeyDialog(ctk.CTkToplevel):
    """Modal dialog for adding a new API key entry."""

    def __init__(self, parent, on_save) -> None:
        super().__init__(parent)
        self.title("Add API Key")
        self.geometry("500x480")
        self.resizable(False, False)
        self.grab_set()
        self._on_save = on_save
        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self, text="New API Key",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(16, 8))

        fields = [
            ("Name *",               "name",        False, "e.g. OpenAI Production"),
            ("API Key Value *",       "value",        True,  "sk-..."),
            ("Service",               "service",      False, "openai, anthropic, ..."),
            ("Tags",                  "tags",          False, "prod, ml, billing"),
            ("Description",          "description",   False, "Optional note"),
            ("Expires (YYYY-MM-DD)", "expires",       False, "2027-01-01"),
        ]
        self._vars: dict[str, ctk.StringVar] = {}
        for label, key, secret, placeholder in fields:
            ctk.CTkLabel(self, text=label, anchor="w").pack(fill="x", padx=20, pady=(6, 0))
            var = ctk.StringVar()
            self._vars[key] = var
            ctk.CTkEntry(
                self, textvariable=var,
                placeholder_text=placeholder,
                show="•" if secret else "",
            ).pack(fill="x", padx=20)

        self._error = ctk.CTkLabel(self, text="", text_color="#F44336", wraplength=440)
        self._error.pack(pady=6)
        ctk.CTkButton(self, text="✓ Save", height=38, width=180, command=self._save).pack(pady=4)

    def _save(self) -> None:
        try:
            name  = validate_key_name(self._vars["name"].get())
            value = validate_api_key_value(self._vars["value"].get())
        except Exception as e:  # noqa: BLE001
            self._error.configure(text=str(e))
            return
        self._on_save({
            "name":        name,
            "value":       value,
            "service":     self._vars["service"].get().strip(),
            "tags":        self._vars["tags"].get().strip(),
            "description": self._vars["description"].get().strip(),
            "expires":     self._vars["expires"].get().strip(),
        })
        self.destroy()


# ------------------------------------------------------------------ #
# Rename Dialog  (Wave 8)
# ------------------------------------------------------------------ #

class RenameDialog(ctk.CTkToplevel):
    """Rename a key in-place — no re-encryption, metadata-only."""

    def __init__(self, parent, entry: APIKeyEntry, on_rename) -> None:
        super().__init__(parent)
        self.title("Rename Key")
        self.geometry("420x200")
        self.resizable(False, False)
        self.grab_set()
        self._entry     = entry
        self._on_rename = on_rename
        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self, text=f'Rename  "{self._entry.name}"',
            font=("Helvetica", 14, "bold"),
        ).pack(pady=(20, 8))

        ctk.CTkLabel(self, text="New name:", anchor="w").pack(fill="x", padx=24)
        self._var = ctk.StringVar(value=self._entry.name)
        entry_widget = ctk.CTkEntry(self, textvariable=self._var, width=360)
        entry_widget.pack(padx=24, pady=4)
        entry_widget.select_range(0, "end")
        entry_widget.focus_set()
        entry_widget.bind("<Return>", lambda _: self._save())

        self._error = ctk.CTkLabel(self, text="", text_color="#F44336")
        self._error.pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(btn_row, text="Rename", width=120, command=self._save).pack(
            side="left", padx=6
        )
        ctk.CTkButton(
            btn_row, text="Cancel", width=100, fg_color="#333",
            command=self.destroy,
        ).pack(side="left", padx=6)

    def _save(self) -> None:
        new_name = self._var.get().strip()
        if not new_name:
            self._error.configure(text="Name cannot be empty.")
            return
        if new_name == self._entry.name:
            self.destroy()
            return
        try:
            new_name = validate_key_name(new_name)
        except Exception as e:  # noqa: BLE001
            self._error.configure(text=str(e))
            return
        self._on_rename(self._entry, new_name)
        self.destroy()


# ------------------------------------------------------------------ #
# Key Card Widget
# ------------------------------------------------------------------ #

class KeyCard(ctk.CTkFrame):
    """One row per API key entry — masked info + action buttons."""

    def __init__(
        self, parent, entry: APIKeyEntry,
        on_copy, on_info, on_rename, on_delete,
    ) -> None:
        super().__init__(parent, corner_radius=8, border_width=1, border_color="#2a2a3e")
        color = STATUS_COLORS.get(entry.status_label, "#ffffff")

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(
            left, text=entry.name,
            font=("Helvetica", 13, "bold"), anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            left,
            text=f"{entry.service}  •  {entry.prefix or ''}  •  {entry.status_label}",
            text_color=color, anchor="w",
        ).pack(fill="x")
        if entry.tags:
            ctk.CTkLabel(
                left,
                text=" ".join(f"#{t}" for t in entry.tags),
                text_color="gray", anchor="w",
            ).pack(fill="x")

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=8, pady=4)

        btn_cfg = dict(width=72, height=28)
        ctk.CTkButton(right, text="Copy",   **btn_cfg, command=lambda: on_copy(entry)).pack(pady=2)
        ctk.CTkButton(right, text="Info",   **btn_cfg, command=lambda: on_info(entry)).pack(pady=2)
        ctk.CTkButton(right, text="Rename", **btn_cfg, command=lambda: on_rename(entry)).pack(pady=2)
        ctk.CTkButton(
            right, text="Delete", **btn_cfg,
            fg_color="#7a2020", hover_color="#c0392b",
            command=lambda: on_delete(entry),
        ).pack(pady=2)


# ------------------------------------------------------------------ #
# Info Dialog
# ------------------------------------------------------------------ #

class InfoDialog(ctk.CTkToplevel):
    """Read-only metadata + health analysis for one entry."""

    def __init__(self, parent, entry: APIKeyEntry) -> None:
        super().__init__(parent)
        self.title(f"Key Info — {entry.name}")
        self.geometry("480x520")
        self.grab_set()
        self._build_ui(entry)

    def _build_ui(self, entry: APIKeyEntry) -> None:
        from wallet.core.health import analyze_entry
        eh = analyze_entry(entry)
        gc = GRADE_COLORS.get(eh.grade, "white")
        sc = STATUS_COLORS.get(entry.status_label, "white")

        ctk.CTkLabel(
            self, text=entry.name,
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(16, 4))

        frame = ctk.CTkScrollableFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=8)

        rows = [
            ("Service",     entry.service),
            ("Prefix",      entry.prefix or "—"),
            ("Description", entry.description or "—"),
            ("Tags",        ", ".join(entry.tags) or "—"),
            ("Created",     entry.created_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Updated",     entry.updated_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Expires",     entry.expires_at.strftime("%Y-%m-%d") if entry.expires_at else "—"),
            ("Last access",
             entry.last_accessed_at.strftime("%Y-%m-%d %H:%M UTC")
             if entry.last_accessed_at else "Never"),
            ("Access count", str(entry.access_count)),
        ]
        for label, value in rows:
            _label_row(frame, label, value)
        _label_row(frame, "Status", entry.status_label, text_color=sc)
        _label_row(frame, "Health", f"{eh.grade}  ({eh.score}/100)", text_color=gc)

        if eh.issues:
            ctk.CTkLabel(frame, text="Issues:", anchor="w").pack(fill="x", padx=4, pady=(8, 0))
            for issue in eh.issues:
                ctk.CTkLabel(
                    frame, text=f"  ⚠ {issue}",
                    text_color="#FF9800", anchor="w",
                ).pack(fill="x", padx=4)
        if eh.recommendations:
            ctk.CTkLabel(frame, text="Recommendations:", anchor="w").pack(
                fill="x", padx=4, pady=(8, 0)
            )
            for rec in eh.recommendations:
                ctk.CTkLabel(
                    frame, text=f"  → {rec}",
                    text_color="gray", anchor="w",
                ).pack(fill="x", padx=4)


# ------------------------------------------------------------------ #
# Keys Tab
# ------------------------------------------------------------------ #

class KeysTab(ctk.CTkFrame):
    """Scrollable list of key cards with live search and full CRUD."""

    def __init__(
        self, parent,
        payload: WalletPayload,
        master_key: bytes,
        on_data_changed,
        status_bar: StatusBar,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload         = payload
        self._master_key      = master_key
        self._params          = storage.read_kdf_params()
        self._on_data_changed = on_data_changed
        self._status          = status_bar
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkEntry(
            top, textvariable=self._search_var,
            placeholder_text="🔍 Search keys…",
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(top, text="+ Add Key", width=100, command=self._open_add).pack(
            side="right", padx=(8, 0)
        )

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._count_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._count_label.pack(pady=2)

    def _refresh(self, *_) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        q = self._search_var.get().lower()
        entries = [
            e for e in self._payload.keys.values()
            if not q
            or q in e.name.lower()
            or q in e.service.lower()
            or any(q in t for t in e.tags)
        ]
        entries.sort(key=lambda e: e.name.lower())
        for entry in entries:
            KeyCard(
                self._scroll, entry,
                on_copy=self._copy_key,
                on_info=self._show_info,
                on_rename=self._rename_key,
                on_delete=self._delete_key,
            ).pack(fill="x", pady=3)
        self._count_label.configure(text=f"{len(entries)} key(s)")

    # — Actions —

    def _copy_key(self, entry: APIKeyEntry) -> None:
        try:
            value = decrypt_entry_value(
                self._master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
        except Exception as e:  # noqa: BLE001
            self._status.set(f"❌ Copy failed: {e}")
            return
        entry.access_count += 1
        entry.last_accessed_at = datetime.now(timezone.utc)
        storage.save(self._master_key, self._params, self._payload.to_dict())
        copy_to_clipboard(value, key_name=entry.name, timeout=cfg.clipboard_clear_seconds)
        audit_log("GET", key_name=entry.name, status="OK")
        self._status.set(f'✓ Copied "{entry.name}" to clipboard')
        self._status.start_clipboard_countdown(cfg.clipboard_clear_seconds)

    def _show_info(self, entry: APIKeyEntry) -> None:
        InfoDialog(self, entry)

    def _rename_key(self, entry: APIKeyEntry) -> None:
        RenameDialog(self, entry, self._do_rename)

    def _do_rename(self, entry: APIKeyEntry, new_name: str) -> None:
        try:
            self._payload.rename_entry(entry.id, new_name)
        except (KeyError, ValueError) as e:
            self._status.set(f"❌ Rename failed: {e}")
            return
        storage.save(self._master_key, self._params, self._payload.to_dict())
        audit_log("RENAME", key_name=new_name, status="OK")
        self._status.set(f'✓ Renamed to "{new_name}"')
        self._refresh()
        self._on_data_changed()

    def _delete_key(self, entry: APIKeyEntry) -> None:
        dialog = ctk.CTkInputDialog(
            text=f"Type '{entry.name}' to confirm deletion:",
            title="Confirm Delete",
        )
        confirmed = dialog.get_input()
        if confirmed != entry.name:
            return
        self._payload.delete_entry(entry.id)
        storage.save(self._master_key, self._params, self._payload.to_dict())
        audit_log("DELETE", key_name=entry.name, status="OK")
        self._status.set(f'✓ Deleted "{entry.name}"')
        self._refresh()
        self._on_data_changed()

    def _open_add(self) -> None:
        AddKeyDialog(self, self._on_add_key)

    def _on_add_key(self, data: dict) -> None:
        svc_info = detect_service(data["value"])
        service  = data["service"] or (svc_info.service_id if svc_info else "unknown")
        prefix   = data["value"][:8]

        entry_id      = str(uuid.uuid4())
        nonce, cipher = encrypt_entry_value(self._master_key, entry_id, data["value"])

        entry = APIKeyEntry(
            id=entry_id,
            name=data["name"],
            service=service,
            nonce_hex=nonce.hex(),
            cipher_hex=cipher.hex(),
            prefix=prefix,
            description=data["description"],
            tags=data["tags"],
            expires_at=parse_expiry_date(data["expires"]),
        )
        self._payload.add_entry(entry)
        storage.save(self._master_key, self._params, self._payload.to_dict())
        audit_log("ADD", key_name=data["name"], status="OK")
        self._status.set(f'✓ Added "{data["name"]}"')
        self._refresh()
        self._on_data_changed()


# ------------------------------------------------------------------ #
# Expiry Tab  (Wave 8)
# ------------------------------------------------------------------ #

class ExpiryTab(ctk.CTkFrame):
    """Expiry checker — shows keys expiring soon or already expired."""

    def __init__(self, parent, payload: WalletPayload, status_bar: StatusBar) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload  = payload
        self._status   = status_bar
        self._days_var = ctk.IntVar(value=30)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(top, text="Show keys expiring within:").pack(side="left")
        ctk.CTkEntry(top, textvariable=self._days_var, width=60).pack(side="left", padx=6)
        ctk.CTkLabel(top, text="days").pack(side="left")
        ctk.CTkButton(top, text="Check", width=80, command=self._refresh).pack(
            side="left", padx=10
        )

        # Header row
        hdr = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=4)
        hdr.pack(fill="x", padx=8, pady=(4, 0))
        for col, w in [
            ("Key Name", 220), ("Service", 120),
            ("Expires", 110),  ("Days Left", 90), ("Urgency", 90),
        ]:
            ctk.CTkLabel(
                hdr, text=col, width=w, anchor="w",
                font=("Helvetica", 11, "bold"), text_color="#aaa",
            ).pack(side="left", padx=4, pady=4)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._summary = ctk.CTkLabel(self, text="", text_color="gray")
        self._summary.pack(pady=2)

    def _refresh(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        try:
            days = int(self._days_var.get())
        except (ValueError, Exception):
            days = 30

        warnings = check_expiry(self._payload, days=days)

        if not warnings:
            ctk.CTkLabel(
                self._scroll,
                text="✅  No keys expiring within the selected window.",
                text_color="#4CAF50",
            ).pack(pady=20)
            self._summary.configure(text="All clear.")
            self._status.set("Expiry check: all clear")
            return

        for w in warnings:
            row = ctk.CTkFrame(
                self._scroll, corner_radius=6,
                border_width=1, border_color="#2a2a3e",
            )
            row.pack(fill="x", pady=2)
            uc        = URGENCY_COLORS.get(w.urgency, "white")
            days_text = "EXPIRED" if w.days_left < 0 else str(w.days_left)

            for text, width, colored in [
                (w.key_name,   220, False),
                (w.service,    120, False),
                (w.expires_on.strftime("%Y-%m-%d") if w.expires_on else "—", 110, False),
                (days_text,    90,  True),
                (w.urgency.upper(), 90, True),
            ]:
                ctk.CTkLabel(
                    row, text=text, width=width, anchor="w",
                    text_color=uc if colored else None,
                ).pack(side="left", padx=4, pady=6)

        expired_count = sum(1 for w in warnings if w.urgency == "expired")
        self._summary.configure(
            text=f"{len(warnings)} key(s) in window — {expired_count} already expired"
        )
        self._status.set(f"Expiry: {len(warnings)} warning(s)")


# ------------------------------------------------------------------ #
# Bulk Import Tab  (Wave 8)
# ------------------------------------------------------------------ #

class BulkImportTab(ctk.CTkFrame):
    """Import keys from .env / .json / .csv with dry-run preview."""

    def __init__(
        self, parent,
        payload: WalletPayload,
        master_key: bytes,
        on_data_changed,
        status_bar: StatusBar,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload         = payload
        self._master_key      = master_key
        self._params          = storage.read_kdf_params()
        self._on_data_changed = on_data_changed
        self._status          = status_bar
        self._parsed: list    = []
        self._file_path: Optional[Path] = None
        self._build_ui()

    def _build_ui(self) -> None:
        # File picker
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(10, 4))
        self._file_label = ctk.CTkLabel(top, text="No file selected", text_color="gray", anchor="w")
        self._file_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(top, text="Browse…", width=90, command=self._pick_file).pack(side="right")

        # Conflict strategy
        opt_row = ctk.CTkFrame(self, fg_color="transparent")
        opt_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(opt_row, text="On conflict:").pack(side="left")
        self._conflict_var = ctk.StringVar(value="skip")
        for opt in ("skip", "overwrite", "rename"):
            ctk.CTkRadioButton(
                opt_row, text=opt, value=opt,
                variable=self._conflict_var,
            ).pack(side="left", padx=10)

        # Preview header
        hdr = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=4)
        hdr.pack(fill="x", padx=8, pady=(6, 0))
        for col, w in [("Name", 200), ("Service", 120), ("Prefix", 110), ("Action", 90)]:
            ctk.CTkLabel(
                hdr, text=col, width=w, anchor="w",
                font=("Helvetica", 11, "bold"), text_color="#aaa",
            ).pack(side="left", padx=4, pady=4)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=4)

        # Bottom action row
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=8, pady=6)
        self._summary_label = ctk.CTkLabel(bot, text="", text_color="gray", anchor="w")
        self._summary_label.pack(side="left", fill="x", expand=True)
        self._apply_btn = ctk.CTkButton(
            bot, text="✓ Apply Import", width=140, state="disabled",
            command=self._apply,
        )
        self._apply_btn.pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            bot, text="Dry Run", width=100, fg_color="#333",
            command=self._dry_run,
        ).pack(side="right")

    def _pick_file(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select import file",
            filetypes=[
                ("Supported formats", "*.env *.json *.csv"),
                ("ENV file",  "*.env"),
                ("JSON file", "*.json"),
                ("CSV file",  "*.csv"),
            ],
        )
        if not path:
            return
        self._file_path = Path(path)
        self._file_label.configure(text=self._file_path.name, text_color="white")
        self._parsed = []
        self._apply_btn.configure(state="disabled")
        self._summary_label.configure(text="")
        self._status.set(f"File selected: {self._file_path.name}")

    def _dry_run(self) -> None:
        if not self._file_path:
            self._status.set("❌ Select a file first.")
            return
        try:
            self._parsed = parse_file(self._file_path)
        except Exception as e:  # noqa: BLE001
            self._status.set(f"❌ Parse error: {e}")
            return

        for w in self._scroll.winfo_children():
            w.destroy()

        conflict       = self._conflict_var.get()
        existing_names = {e.name for e in self._payload.keys.values()}

        new_count = skip_count = rename_count = 0
        for item in self._parsed:
            name   = item.get("name", "?")
            svc    = item.get("service", "unknown")
            prefix = item.get("value", "")[:8] + "…"

            if name in existing_names:
                if conflict == "skip":
                    action = "SKIP";      action_color = "#757575"; skip_count  += 1
                elif conflict == "overwrite":
                    action = "OVERWRITE"; action_color = "#FF9800"; new_count   += 1
                else:
                    action = "RENAME";    action_color = "#29B6F6"; rename_count += 1
            else:
                action = "ADD"; action_color = "#4CAF50"; new_count += 1

            row = ctk.CTkFrame(
                self._scroll, corner_radius=4,
                border_width=1, border_color="#2a2a3e",
            )
            row.pack(fill="x", pady=2)
            for text, width, color in [
                (name,   200, None),
                (svc,    120, None),
                (prefix, 110, "gray"),
                (action, 90,  action_color),
            ]:
                ctk.CTkLabel(
                    row, text=text, width=width, anchor="w",
                    text_color=color,
                ).pack(side="left", padx=4, pady=5)

        total = len(self._parsed)
        self._summary_label.configure(
            text=(
                f"Preview: {total} entries — {new_count} add/overwrite, "
                f"{skip_count} skip, {rename_count} rename"
            )
        )
        self._apply_btn.configure(state="normal" if total > 0 else "disabled")
        self._status.set(f"Dry run: {total} entries parsed")

    def _apply(self) -> None:
        if not self._parsed:
            return
        try:
            result: BulkImportResult = apply_bulk_import(
                self._payload,
                self._master_key,
                self._parsed,
                on_conflict=self._conflict_var.get(),
            )
        except Exception as e:  # noqa: BLE001
            self._status.set(f"❌ Import failed: {e}")
            return

        storage.save(self._master_key, self._params, self._payload.to_dict())
        audit_log("BULK_IMPORT", status="OK", extra=str(result))

        msg = (
            f"✓ Import done — "
            f"{result.added} added, {result.overwritten} overwritten, "
            f"{result.renamed} renamed, {result.skipped} skipped"
        )
        if result.errors:
            msg += f", {len(result.errors)} errors"
        self._summary_label.configure(text=msg)
        self._status.set(msg)
        self._apply_btn.configure(state="disabled")
        self._parsed = []
        self._on_data_changed()


# ------------------------------------------------------------------ #
# Health Tab
# ------------------------------------------------------------------ #

class HealthTab(ctk.CTkFrame):
    """Wallet-wide health scores with per-entry breakdown."""

    def __init__(self, parent, payload: WalletPayload) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload = payload
        self._build_ui()

    def _build_ui(self) -> None:
        wh = analyze_wallet(self._payload)
        gc = GRADE_COLORS.get(wh.overall_grade, "white")

        summary = ctk.CTkFrame(self)
        summary.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(
            summary,
            text=f"Overall Grade: {wh.overall_grade}   Score: {wh.overall_score}/100",
            font=("Helvetica", 16, "bold"), text_color=gc,
        ).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            summary,
            text=(
                f"✅ {wh.healthy} Healthy   "
                f"⚠️ {wh.warning} Warning   "
                f"🔴 {wh.critical} Critical"
            ),
        ).pack(side="right", padx=12)

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=8, pady=4)

        for eh in sorted(wh.entries, key=lambda e: e.score):
            card = ctk.CTkFrame(
                scroll, corner_radius=6,
                border_width=1, border_color="#2a2a3e",
            )
            card.pack(fill="x", pady=3)
            gc2 = GRADE_COLORS.get(eh.grade, "white")

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=6)
            ctk.CTkLabel(
                row, text=eh.name,
                font=("Helvetica", 12, "bold"),
                width=200, anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=f"{eh.grade}  {eh.score}/100",
                text_color=gc2, width=80, anchor="w",
            ).pack(side="left")
            if eh.issues:
                ctk.CTkLabel(
                    row,
                    text=" | ".join(eh.issues),
                    text_color="#FF9800", anchor="w",
                ).pack(side="left")


# ------------------------------------------------------------------ #
# Settings Tab
# ------------------------------------------------------------------ #

class SettingsTab(ctk.CTkFrame):
    """Change password, export backup, wallet info, audit viewer."""

    def __init__(
        self, parent,
        payload: WalletPayload,
        master_key: bytes,
        status_bar: StatusBar,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload    = payload
        self._master_key = master_key
        self._params     = storage.read_kdf_params()
        self._status     = status_bar
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True)

        # — Change Password —
        sec1 = ctk.CTkFrame(scroll)
        sec1.pack(fill="x", padx=8, pady=(12, 4))
        _section_title(sec1, "Change Master Password")

        for label, attr, secret in [
            ("Current password", "_cur_pass",     True),
            ("New password",     "_new_pass",     True),
            ("Confirm new",      "_confirm_pass", True),
        ]:
            row = ctk.CTkFrame(sec1, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
            var = ctk.StringVar()
            setattr(self, attr + "_var", var)
            ctk.CTkEntry(row, textvariable=var, show="•").pack(side="left", fill="x", expand=True)

        self._pw_status = ctk.CTkLabel(sec1, text="", text_color="#F44336")
        self._pw_status.pack(anchor="w", padx=10)
        ctk.CTkButton(
            sec1, text="Change Password", width=180,
            command=self._change_password,
        ).pack(padx=10, pady=6)

        # — Export —
        sec2 = ctk.CTkFrame(scroll)
        sec2.pack(fill="x", padx=8, pady=4)
        _section_title(sec2, "Export Encrypted Backup")
        ctk.CTkButton(sec2, text="Export…", width=120, command=self._export).pack(
            padx=10, pady=4
        )

        # — Wallet Info —
        sec3 = ctk.CTkFrame(scroll)
        sec3.pack(fill="x", padx=8, pady=4)
        _section_title(sec3, "Wallet Info")
        total   = len(self._payload.keys)
        version = getattr(self._payload, "version", "—")
        _label_row(sec3, "Total keys",     str(total))
        _label_row(sec3, "Wallet version", version)

        # — Audit Log —
        sec4 = ctk.CTkFrame(scroll)
        sec4.pack(fill="both", expand=True, padx=8, pady=4)
        _section_title(sec4, "Recent Audit Events (last 20)")

        audit_scroll = ctk.CTkScrollableFrame(sec4, height=180)
        audit_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        events = read_audit_log(last_n=20)
        for ev in reversed(events):
            ts       = ev.get("ts", "")[:19].replace("T", " ")
            event    = ev.get("event", "")
            status   = ev.get("status", "")
            key_name = ev.get("key_name", "") or ""
            mark     = "✓" if status == "OK" else "❌"
            line     = f"{ts}  {mark} {event:<20}  {key_name}"
            ctk.CTkLabel(
                audit_scroll, text=line, anchor="w",
                font=("Courier", 11),
            ).pack(fill="x")

    def _change_password(self) -> None:
        cur     = self._cur_pass_var.get()      # type: ignore[attr-defined]
        new     = self._new_pass_var.get()      # type: ignore[attr-defined]
        confirm = self._confirm_pass_var.get()  # type: ignore[attr-defined]

        if not verify_master_password(cur, self._payload.master_hash):
            self._pw_status.configure(text="❌ Wrong current password.")
            return
        if len(new) < 8:
            self._pw_status.configure(text="❌ New password too short (min 8).")
            return
        if new != confirm:
            self._pw_status.configure(text="❌ Passwords do not match.")
            return

        new_params = KDFParams.generate()
        new_key    = derive_key(new, new_params)
        self._payload.master_hash = hash_master_password(new)
        for entry in self._payload.keys.values():
            old_val = decrypt_entry_value(
                self._master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
            nonce, cipher = encrypt_entry_value(new_key, entry.id, old_val)
            entry.nonce_hex  = nonce.hex()
            entry.cipher_hex = cipher.hex()
        storage.save(new_key, new_params, self._payload.to_dict())
        session.unlock(new_key)
        self._master_key = new_key
        self._params     = new_params
        audit_log("CHANGE_PASSWORD", status="OK")
        self._pw_status.configure(text="✓ Password changed.", text_color="#4CAF50")
        self._status.set("✓ Master password changed")

    def _export(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".enc",
            filetypes=[("Encrypted backup", "*.enc")],
            title="Save encrypted backup",
        )
        if not path:
            return
        dialog = ctk.CTkInputDialog(text="Enter export password:", title="Export Password")
        export_pass = dialog.get_input()
        if not export_pass or len(export_pass) < 8:
            return
        exp_params = KDFParams.generate()
        exp_key    = derive_key(export_pass, exp_params)
        WalletStorage(Path(path)).save(exp_key, exp_params, self._payload.to_dict())
        audit_log("EXPORT", status="OK", extra=path)
        self._status.set(f"✓ Backup exported to {Path(path).name}")


# ------------------------------------------------------------------ #
# Sidebar Navigation  (Wave 8)
# ------------------------------------------------------------------ #

NAV_ITEMS = [
    ("🗝️",  "Keys"),
    ("⏰",  "Expiry"),
    ("📥",  "Bulk Import"),
    ("📊",  "Health"),
    ("⚙️",  "Settings"),
]


class Sidebar(ctk.CTkFrame):
    """Icon + label vertical nav sidebar."""

    def __init__(self, parent, on_select) -> None:
        super().__init__(
            parent, width=SIDEBAR_W, fg_color=SIDEBAR_BG,
            corner_radius=0,
        )
        self.pack_propagate(False)
        self._on_select           = on_select
        self._buttons: list       = []
        self._active              = 0
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="🔐 VaultKey",
            font=("Helvetica", 15, "bold"),
            text_color="white",
        ).pack(pady=(20, 16), padx=12, anchor="w")

        for idx, (icon, label) in enumerate(NAV_ITEMS):
            btn = ctk.CTkButton(
                self,
                text=f"  {icon}  {label}",
                anchor="w",
                fg_color="#1e2738" if idx == 0 else "transparent",
                hover_color="#1e2738",
                text_color="white",
                height=40,
                corner_radius=6,
                command=lambda i=idx: self._select(i),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._buttons.append(btn)

    def _select(self, idx: int) -> None:
        self._buttons[self._active].configure(fg_color="transparent")
        self._active = idx
        self._buttons[idx].configure(fg_color="#1e2738")
        self._on_select(idx)


# ------------------------------------------------------------------ #
# Main Window
# ------------------------------------------------------------------ #

class MainWindow(ctk.CTk):
    """Main window with sidebar + content panels."""

    def __init__(self, payload: WalletPayload, master_key: bytes) -> None:
        super().__init__()
        self.title("VaultKey")
        self.geometry("920x660")
        self.minsize(720, 520)
        self._payload        = payload
        self._master_key     = master_key
        self._panels: list   = []
        self._active_panel   = 0
        self._build_ui()
        self._show_expiry_banner()

    def _build_ui(self) -> None:
        # Top bar
        topbar = ctk.CTkFrame(self, height=TOPBAR_H, fg_color="#0d1117", corner_radius=0)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        info = session.info
        ctk.CTkLabel(
            topbar,
            text=f"Unlocked  •  auto-locks in {info['timeout_minutes']} min",
            text_color="#4CAF50", font=("Helvetica", 11),
        ).pack(side="left", padx=16)
        ctk.CTkButton(
            topbar, text="🔒 Lock", width=80, height=30,
            fg_color="#333", hover_color="#c0392b",
            command=self._lock,
        ).pack(side="right", padx=16, pady=8)

        # Status bar
        self._status_bar = StatusBar(self)
        self._status_bar.pack(fill="x", side="bottom")

        # Body: sidebar + content
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self._sidebar = Sidebar(body, on_select=self._show_panel)
        self._sidebar.pack(side="left", fill="y")

        self._content = ctk.CTkFrame(body, fg_color=CONTENT_BG, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        # Build all panels
        self._panels = [
            KeysTab(
                self._content, self._payload, self._master_key,
                on_data_changed=self._on_data_changed,
                status_bar=self._status_bar,
            ),
            ExpiryTab(self._content, self._payload, status_bar=self._status_bar),
            BulkImportTab(
                self._content, self._payload, self._master_key,
                on_data_changed=self._on_data_changed,
                status_bar=self._status_bar,
            ),
            HealthTab(self._content, self._payload),
            SettingsTab(
                self._content, self._payload, self._master_key,
                status_bar=self._status_bar,
            ),
        ]
        self._panels[0].pack(fill="both", expand=True)

    def _show_panel(self, idx: int) -> None:
        self._panels[self._active_panel].pack_forget()
        self._active_panel = idx
        self._panels[idx].pack(fill="both", expand=True)

    def _on_data_changed(self) -> None:
        """Rebuild Health tab after any mutation."""
        old = self._panels[3]
        old.pack_forget()
        new_health = HealthTab(self._content, self._payload)
        self._panels[3] = new_health
        if self._active_panel == 3:
            new_health.pack(fill="both", expand=True)

    def _show_expiry_banner(self) -> None:
        warnings = check_expiry(self._payload, days=7)
        if not warnings:
            return
        critical = [w for w in warnings if w.urgency in ("expired", "critical")]
        if critical:
            self._status_bar.set(
                f"⚠️  {len(critical)} key(s) expired or expiring within 3 days! "
                "→ Check Expiry tab."
            )
        else:
            self._status_bar.set(
                f"ℹ️  {len(warnings)} key(s) expiring within 7 days. "
                "→ Check Expiry tab."
            )

    def _lock(self) -> None:
        session.lock(reason="gui_manual_lock")
        self.destroy()

    def on_closing(self) -> None:
        session.lock(reason="gui_close")
        self.destroy()


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

def run_gui() -> None:
    """Entry point called by `wallet gui` CLI command."""
    if not storage.exists():
        print("❌ No wallet found. Run: wallet init")
        return

    login = LoginWindow()
    login.mainloop()

    if not login._authenticated or not login._master_key or not login._payload:
        return

    main = MainWindow(login._payload, login._master_key)
    main.protocol("WM_DELETE_WINDOW", main.on_closing)
    main.mainloop()
