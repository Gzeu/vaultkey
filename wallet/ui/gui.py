"""
gui.py — CustomTkinter GUI for VaultKey.

Features:
- Dark mode by default
- Master password screen with Show/Hide toggle
- Scrollable list of API key cards
- Copy button with 30-second clipboard auto-clear countdown
- Add/Delete/Export dialog windows
- always_on_top option configurable
- Auto-minimize on focus loss (optional, toggle in settings)
"""

import threading
from datetime import datetime, timezone
from typing import Optional

import customtkinter as ctk

from wallet.core.crypto import decrypt_entry_value, encrypt_entry_value
from wallet.core.kdf import KDFParams, derive_key, hash_master_password, verify_master_password
from wallet.core.session import SessionManager, WalletLockedException
from wallet.core.storage import WalletStorage
from wallet.models.config import WalletConfig
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.prefix_detect import detect_service
from wallet.utils.validators import validate_api_key_value, validate_key_name

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

cfg = WalletConfig()
storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)
session = SessionManager()

STATUS_COLORS = {
    "active": "#4CAF50",
    "expiring": "#FF9800",
    "expired": "#F44336",
    "revoked": "#757575",
}


class LoginWindow(ctk.CTk):
    """Master password entry screen."""

    def __init__(self):
        super().__init__()
        self.title("VaultKey — Unlock")
        self.geometry("420x280")
        self.resizable(False, False)
        self._build_ui()
        self._authenticated = False
        self._master_key: Optional[bytes] = None
        self._payload: Optional[WalletPayload] = None

    def _build_ui(self) -> None:
        ctk.CTkLabel(self, text="🔐 VaultKey", font=("Helvetica", 26, "bold")).pack(pady=(30, 5))
        ctk.CTkLabel(self, text="Enter master password to unlock", text_color="gray").pack()

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(pady=20, padx=40, fill="x")

        self._pass_var = ctk.StringVar()
        self._pass_entry = ctk.CTkEntry(
            frame, textvariable=self._pass_var,
            show="•", placeholder_text="Master password",
            width=280, height=40
        )
        self._pass_entry.pack(side="left")
        self._pass_entry.bind("<Return>", lambda _: self._do_unlock())

        self._show_btn = ctk.CTkButton(
            frame, text="👁", width=40, height=40,
            command=self._toggle_show
        )
        self._show_btn.pack(side="left", padx=(5, 0))

        self._error_label = ctk.CTkLabel(self, text="", text_color="#F44336")
        self._error_label.pack()

        ctk.CTkButton(
            self, text="Unlock", height=40, width=200,
            command=self._do_unlock
        ).pack(pady=10)

    def _toggle_show(self) -> None:
        current = self._pass_entry.cget("show")
        self._pass_entry.configure(show="" if current else "•")

    def _do_unlock(self) -> None:
        password = self._pass_var.get()
        if not password:
            self._error_label.configure(text="Password cannot be empty.")
            return
        try:
            params = storage.read_kdf_params()
            key = derive_key(password, params)
            data = storage.load(key)
            payload = WalletPayload.from_dict(data)
        except Exception:
            session.record_failed_attempt()
            self._error_label.configure(text="Wrong password or corrupted wallet.")
            self._pass_var.set("")
            return

        if not verify_master_password(password, payload.master_hash):
            session.record_failed_attempt()
            self._error_label.configure(text="Wrong password.")
            self._pass_var.set("")
            return

        session.unlock(key)
        self._master_key = key
        self._payload = payload
        self._authenticated = True
        self.destroy()


class AddKeyDialog(ctk.CTkToplevel):
    """Dialog for adding a new API key."""

    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.title("Add API Key")
        self.geometry("480x420")
        self.grab_set()
        self._on_save = on_save
        self._build_ui()

    def _build_ui(self) -> None:
        fields = [
            ("Name", "name", False),
            ("API Key Value", "value", True),
            ("Service", "service", False),
            ("Tags (comma-sep)", "tags", False),
            ("Description", "description", False),
            ("Expires (YYYY-MM-DD)", "expires", False),
        ]
        self._vars = {}
        for label, key, secret in fields:
            ctk.CTkLabel(self, text=label, anchor="w").pack(fill="x", padx=20, pady=(8, 0))
            var = ctk.StringVar()
            self._vars[key] = var
            ctk.CTkEntry(self, textvariable=var, show="•" if secret else "").pack(
                fill="x", padx=20
            )

        self._error = ctk.CTkLabel(self, text="", text_color="#F44336")
        self._error.pack(pady=5)

        ctk.CTkButton(self, text="Save", command=self._save).pack(pady=10)

    def _save(self) -> None:
        try:
            name = validate_key_name(self._vars["name"].get())
            value = validate_api_key_value(self._vars["value"].get())
        except ValueError as e:
            self._error.configure(text=str(e))
            return
        self._on_save({
            "name": name,
            "value": value,
            "service": self._vars["service"].get(),
            "tags": self._vars["tags"].get(),
            "description": self._vars["description"].get(),
            "expires": self._vars["expires"].get(),
        })
        self.destroy()


class KeyCard(ctk.CTkFrame):
    """A card widget representing one API key entry."""

    def __init__(self, parent, entry: APIKeyEntry, on_copy, on_delete):
        super().__init__(parent, corner_radius=8)
        self.entry = entry
        color = STATUS_COLORS.get(entry.status_label, "#ffffff")

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        ctk.CTkLabel(info_frame, text=entry.name, font=("Helvetica", 14, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(
            info_frame,
            text=f"{entry.service}  •  {entry.status_label}",
            text_color=color, anchor="w"
        ).pack(fill="x")
        if entry.tags:
            ctk.CTkLabel(info_frame, text=" ".join(f"#{t}" for t in entry.tags),
                         text_color="gray", anchor="w").pack(fill="x")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="Copy", width=60, command=lambda: on_copy(entry)).pack(pady=2)
        ctk.CTkButton(btn_frame, text="Del", width=60, fg_color="#c0392b",
                       command=lambda: on_delete(entry)).pack(pady=2)


class MainWindow(ctk.CTk):
    """Main wallet window after successful unlock."""

    def __init__(self, payload: WalletPayload, master_key: bytes):
        super().__init__()
        self.title("VaultKey")
        self.geometry("700x560")
        self.payload = payload
        self.master_key = master_key
        self._params = storage.read_kdf_params()
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(top, text="🔐 VaultKey", font=("Helvetica", 20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="+ Add Key", width=100, command=self._open_add_dialog).pack(side="right")
        ctk.CTkButton(top, text="Lock", width=70, fg_color="#555", command=self._lock).pack(side="right", padx=5)

        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=16, pady=8)
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_list())
        ctk.CTkEntry(search_frame, textvariable=self._search_var,
                      placeholder_text="🔍 Search keys...").pack(fill="x")

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=16, pady=8)

        self._status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self._status_label.pack(pady=4)

    def _refresh_list(self, *_) -> None:
        for widget in self._scroll.winfo_children():
            widget.destroy()

        query = self._search_var.get().lower()
        entries = [
            e for e in self.payload.keys.values()
            if not query or query in e.name.lower() or query in e.service.lower()
        ]

        for entry in sorted(entries, key=lambda e: e.name.lower()):
            card = KeyCard(self._scroll, entry, self._copy_key, self._delete_key)
            card.pack(fill="x", pady=3)

        self._status_label.configure(text=f"{len(entries)} key(s)")

    def _copy_key(self, entry: APIKeyEntry) -> None:
        value = decrypt_entry_value(
            self.master_key, entry.id,
            bytes.fromhex(entry.nonce_hex),
            bytes.fromhex(entry.cipher_hex)
        )
        copy_to_clipboard(value, key_name=entry.name, timeout=cfg.clipboard_clear_seconds)
        self._status_label.configure(text=f"✓ Copied: {entry.name}  (clears in {cfg.clipboard_clear_seconds}s)")
        threading.Timer(
            cfg.clipboard_clear_seconds,
            lambda: self._status_label.configure(text="Clipboard cleared.")
        ).start()

    def _delete_key(self, entry: APIKeyEntry) -> None:
        dialog = ctk.CTkInputDialog(
            text=f"Type '{entry.name}' to confirm deletion:",
            title="Confirm Delete"
        )
        confirmed = dialog.get_input()
        if confirmed == entry.name:
            self.payload.delete_entry(entry.id)
            storage.save(self.master_key, self._params, self.payload.to_dict())
            self._refresh_list()

    def _open_add_dialog(self) -> None:
        AddKeyDialog(self, self._on_add_key)

    def _on_add_key(self, data: dict) -> None:
        from wallet.utils.validators import parse_expiry_date
        svc = data["service"] or (detect_service(data["value"]).service_id if detect_service(data["value"]) else "unknown")
        nonce, cipher = encrypt_entry_value(self.master_key, "_tmp_", data["value"])
        entry = APIKeyEntry(
            name=data["name"], service=svc,
            nonce_hex=nonce.hex(), cipher_hex=cipher.hex(),
            tags=data["tags"], description=data["description"],
            expires_at=parse_expiry_date(data["expires"]),
        )
        nonce2, cipher2 = encrypt_entry_value(self.master_key, entry.id, data["value"])
        entry.nonce_hex = nonce2.hex()
        entry.cipher_hex = cipher2.hex()
        self.payload.add_entry(entry)
        storage.save(self.master_key, self._params, self.payload.to_dict())
        self._refresh_list()

    def _lock(self) -> None:
        session.lock()
        self.destroy()


def run_gui() -> None:
    if not storage.exists():
        print("No wallet found. Run: wallet init")
        return

    login = LoginWindow()
    login.mainloop()

    if not login._authenticated:
        return

    main = MainWindow(login._payload, login._master_key)
    main.mainloop()
