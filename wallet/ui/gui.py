"""
gui.py — CustomTkinter GUI for VaultKey (Wave 4 rewrite).

Tabs:
  Keys       — Scrollable card list, live search, Copy/Info/Delete per card.
  Health     — Per-entry health scores, overall grade, recommendations.
  Settings   — Change password, export/import, audit viewer.

Design decisions:
- Dark mode only — secrets should not be visible in bright environments.
- No API key values are EVER displayed in the GUI. Only masked prefixes.
  Copy sends to clipboard; clipboard auto-clears after cfg.clipboard_clear_seconds.
- AddKeyDialog no longer uses '_tmp_' sub-key (FIX from original gui.py).
  UUID is generated BEFORE first encrypt_entry_value call.
- All destructive actions (delete, wipe) require a typed-name confirmation dialog.
- GUI uses threading.Timer for clipboard countdown; never blocks the Tk event loop.
- Health analysis runs on payload without decrypting any ciphertext.
- All settings persistence goes through WalletConfig / WalletStorage; no extra files.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import customtkinter as ctk

from wallet.core.crypto import decrypt_entry_value, encrypt_entry_value
from wallet.core.health import analyze_wallet
from wallet.core.kdf import KDFParams, derive_key, hash_master_password, verify_master_password
from wallet.core.session import SessionManager, WalletLockedException
from wallet.core.storage import WalletStorage
from wallet.models.config import WalletConfig
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.audit import audit_log, read_audit_log
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.prefix_detect import detect_service
from wallet.utils.validators import parse_expiry_date, validate_api_key_value, validate_key_name

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
GRADE_COLORS = {"A": "#4CAF50", "B": "#8BC34A", "C": "#FFC107", "D": "#FF9800", "F": "#F44336"}


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _run_after(widget, ms: int, fn) -> None:
    """Schedule fn on the Tk main thread after ms milliseconds."""
    widget.after(ms, fn)


def _label_row(parent, text: str, value: str, text_color="gray") -> None:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=4, pady=1)
    ctk.CTkLabel(row, text=text, width=120, anchor="w").pack(side="left")
    ctk.CTkLabel(row, text=value, anchor="w", text_color=text_color).pack(side="left")


# ------------------------------------------------------------------ #
# Login Window
# ------------------------------------------------------------------ #

class LoginWindow(ctk.CTk):
    """Master password entry screen. Blocks until authenticated or closed."""

    def __init__(self) -> None:
        super().__init__()
        self.title("🔐 VaultKey — Unlock")
        self.geometry("420x300")
        self.resizable(False, False)
        self._authenticated = False
        self._master_key: Optional[bytes] = None
        self._payload: Optional[WalletPayload] = None
        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(self, text="🔐 VaultKey",
                     font=("Helvetica", 26, "bold")).pack(pady=(30, 4))
        ctk.CTkLabel(self, text="Enter master password to unlock",
                     text_color="gray").pack()

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

        ctk.CTkButton(frame, text="👁", width=40, height=40,
                      command=self._toggle_show).pack(side="left", padx=(5, 0))

        self._attempt_label = ctk.CTkLabel(self, text="", text_color="#F44336")
        self._attempt_label.pack()

        ctk.CTkButton(self, text="Unlock Wallet", height=40, width=200,
                      command=self._do_unlock).pack(pady=10)

    def _toggle_show(self) -> None:
        self._pass_entry.configure(
            show="" if self._pass_entry.cget("show") else "•"
        )

    def _do_unlock(self) -> None:
        password = self._pass_var.get()
        if not password:
            self._attempt_label.configure(text="❌ Password cannot be empty.")
            return
        if not storage.exists():
            self._attempt_label.configure(text="❌ No wallet found. Run: wallet init")
            return
        try:
            params = storage.read_kdf_params()
            key = derive_key(password, params)
            data = storage.load(key)
            payload = WalletPayload.from_dict(data)
        except Exception:  # noqa: BLE001
            session.record_failed_attempt()
            info = session.info
            self._attempt_label.configure(
                text=f"❌ Wrong password. (attempts: {info['failed_attempts']})"
            )
            self._pass_var.set("")
            return

        if not verify_master_password(password, payload.master_hash):
            session.record_failed_attempt()
            self._attempt_label.configure(text="❌ Wrong password.")
            self._pass_var.set("")
            return

        session.unlock(key)
        self._master_key = key
        self._payload = payload
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
        self.geometry("500x460")
        self.resizable(False, False)
        self.grab_set()
        self._on_save = on_save
        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(self, text="New API Key",
                     font=("Helvetica", 16, "bold")).pack(pady=(16, 8))

        fields = [
            ("Name *", "name", False, "e.g. OpenAI Production"),
            ("API Key Value *", "value", True, "sk-..."),
            ("Service", "service", False, "openai, anthropic, ..."),
            ("Tags", "tags", False, "prod, ml, billing"),
            ("Description", "description", False, "Optional note"),
            ("Expires (YYYY-MM-DD)", "expires", False, "2027-01-01"),
        ]
        self._vars: dict[str, ctk.StringVar] = {}
        for label, key, secret, placeholder in fields:
            ctk.CTkLabel(self, text=label, anchor="w").pack(fill="x", padx=20, pady=(6, 0))
            var = ctk.StringVar()
            self._vars[key] = var
            entry = ctk.CTkEntry(self, textvariable=var,
                                  placeholder_text=placeholder,
                                  show="•" if secret else "")
            entry.pack(fill="x", padx=20)

        self._error = ctk.CTkLabel(self, text="", text_color="#F44336",
                                    wraplength=440)
        self._error.pack(pady=6)
        ctk.CTkButton(self, text="✓ Save", height=38, width=180,
                       command=self._save).pack(pady=4)

    def _save(self) -> None:
        try:
            name = validate_key_name(self._vars["name"].get())
            value = validate_api_key_value(self._vars["value"].get())
        except Exception as e:  # noqa: BLE001
            self._error.configure(text=str(e))
            return
        self._on_save({
            "name": name,
            "value": value,
            "service": self._vars["service"].get().strip(),
            "tags": self._vars["tags"].get().strip(),
            "description": self._vars["description"].get().strip(),
            "expires": self._vars["expires"].get().strip(),
        })
        self.destroy()


# ------------------------------------------------------------------ #
# Key Card Widget
# ------------------------------------------------------------------ #

class KeyCard(ctk.CTkFrame):
    """One row per API key entry. Shows masked info + action buttons."""

    def __init__(self, parent, entry: APIKeyEntry, on_copy, on_info, on_delete) -> None:
        super().__init__(parent, corner_radius=8, border_width=1,
                          border_color="#333")
        color = STATUS_COLORS.get(entry.status_label, "#ffffff")

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(left, text=entry.name,
                      font=("Helvetica", 13, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(left,
                      text=f"{entry.service}  •  {entry.prefix or ''}  •  {entry.status_label}",
                      text_color=color, anchor="w").pack(fill="x")
        if entry.tags:
            ctk.CTkLabel(left,
                          text=" ".join(f"#{t}" for t in entry.tags),
                          text_color="gray", anchor="w").pack(fill="x")

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=8, pady=4)

        ctk.CTkButton(right, text="Copy", width=64, height=28,
                       command=lambda: on_copy(entry)).pack(pady=2)
        ctk.CTkButton(right, text="Info", width=64, height=28,
                       command=lambda: on_info(entry)).pack(pady=2)
        ctk.CTkButton(right, text="Delete", width=64, height=28,
                       fg_color="#7a2020", hover_color="#c0392b",
                       command=lambda: on_delete(entry)).pack(pady=2)


# ------------------------------------------------------------------ #
# Info Dialog
# ------------------------------------------------------------------ #

class InfoDialog(ctk.CTkToplevel):
    """Read-only metadata view for a key entry + health analysis."""

    def __init__(self, parent, entry: APIKeyEntry) -> None:
        super().__init__(parent)
        self.title(f"Key Info — {entry.name}")
        self.geometry("480x480")
        self.grab_set()
        self._build_ui(entry)

    def _build_ui(self, entry: APIKeyEntry) -> None:
        from wallet.core.health import analyze_entry
        eh = analyze_entry(entry)
        gc = GRADE_COLORS.get(eh.grade, "white")
        sc = STATUS_COLORS.get(entry.status_label, "white")

        ctk.CTkLabel(self, text=entry.name,
                      font=("Helvetica", 16, "bold")).pack(pady=(16, 4))

        frame = ctk.CTkScrollableFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=8)

        rows = [
            ("Service", entry.service),
            ("Prefix", entry.prefix or "—"),
            ("Description", entry.description or "—"),
            ("Tags", ", ".join(entry.tags) or "—"),
            ("Created", entry.created_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Updated", entry.updated_at.strftime("%Y-%m-%d %H:%M UTC")),
            ("Expires",
             entry.expires_at.strftime("%Y-%m-%d") if entry.expires_at else "—"),
            ("Last access",
             entry.last_accessed_at.strftime("%Y-%m-%d %H:%M UTC")
             if entry.last_accessed_at else "Never"),
            ("Access count", str(entry.access_count)),
        ]
        for label, value in rows:
            _label_row(frame, label, value)

        # Status row with color
        _label_row(frame, "Status", entry.status_label, text_color=sc)
        _label_row(frame, "Health", f"{eh.grade}  ({eh.score}/100)", text_color=gc)

        if eh.issues:
            ctk.CTkLabel(frame, text="Issues:", anchor="w").pack(fill="x", padx=4, pady=(8, 0))
            for issue in eh.issues:
                ctk.CTkLabel(frame, text=f"  ⚠ {issue}",
                              text_color="#FF9800", anchor="w").pack(fill="x", padx=4)
        if eh.recommendations:
            ctk.CTkLabel(frame, text="Recommendations:",
                          anchor="w").pack(fill="x", padx=4, pady=(8, 0))
            for rec in eh.recommendations:
                ctk.CTkLabel(frame, text=f"  → {rec}",
                              text_color="gray", anchor="w").pack(fill="x", padx=4)


# ------------------------------------------------------------------ #
# Keys Tab
# ------------------------------------------------------------------ #

class KeysTab(ctk.CTkFrame):
    """Scrollable list of key cards with live search and CRUD actions."""

    def __init__(self, parent, payload: WalletPayload, master_key: bytes,
                  on_data_changed) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload = payload
        self._master_key = master_key
        self._params = storage.read_kdf_params()
        self._on_data_changed = on_data_changed
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkEntry(top, textvariable=self._search_var,
                      placeholder_text="🔍 Search keys…").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(top, text="+ Add Key", width=100,
                       command=self._open_add).pack(side="right", padx=(8, 0))

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
            if not q or q in e.name.lower()
            or q in e.service.lower()
            or any(q in t for t in e.tags)
        ]
        entries.sort(key=lambda e: e.name.lower())
        for entry in entries:
            KeyCard(
                self._scroll, entry,
                on_copy=self._copy_key,
                on_info=self._show_info,
                on_delete=self._delete_key,
            ).pack(fill="x", pady=3)
        self._count_label.configure(text=f"{len(entries)} key(s)")

    def _copy_key(self, entry: APIKeyEntry) -> None:
        try:
            value = decrypt_entry_value(
                self._master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
        except Exception as e:  # noqa: BLE001
            ctk.CTkMessagebox(title="Error", message=str(e))
            return
        entry.access_count += 1
        entry.last_accessed_at = datetime.now(timezone.utc)
        storage.save(self._master_key, self._params, self._payload.to_dict())
        copy_to_clipboard(value, key_name=entry.name, timeout=cfg.clipboard_clear_seconds)
        audit_log("GET", key_name=entry.name, status="OK")

    def _show_info(self, entry: APIKeyEntry) -> None:
        InfoDialog(self, entry)

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
        self._refresh()
        self._on_data_changed()

    def _open_add(self) -> None:
        AddKeyDialog(self, self._on_add_key)

    def _on_add_key(self, data: dict) -> None:
        svc_info = detect_service(data["value"])
        service = data["service"] or (svc_info.service_id if svc_info else "unknown")
        prefix = data["value"][:8]

        # FIX: generate UUID BEFORE first encrypt (no _tmp_ sub-key waste)
        entry_id = str(uuid.uuid4())
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
        self._refresh()
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
            card = ctk.CTkFrame(scroll, corner_radius=6, border_width=1,
                                 border_color="#333")
            card.pack(fill="x", pady=3)
            gc2 = GRADE_COLORS.get(eh.grade, "white")

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=6)
            ctk.CTkLabel(row, text=eh.name,
                          font=("Helvetica", 12, "bold"),
                          width=200, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=f"{eh.grade}  {eh.score}/100",
                          text_color=gc2, width=80, anchor="w").pack(side="left")
            if eh.issues:
                ctk.CTkLabel(row, text=" | ".join(eh.issues),
                              text_color="#FF9800", anchor="w").pack(side="left")


# ------------------------------------------------------------------ #
# Settings Tab
# ------------------------------------------------------------------ #

class SettingsTab(ctk.CTkFrame):
    """Change password, export backup, view recent audit log."""

    def __init__(self, parent, payload: WalletPayload, master_key: bytes) -> None:
        super().__init__(parent, fg_color="transparent")
        self._payload = payload
        self._master_key = master_key
        self._params = storage.read_kdf_params()
        self._build_ui()

    def _build_ui(self) -> None:
        # — Change Password Section —
        sec1 = ctk.CTkFrame(self)
        sec1.pack(fill="x", padx=8, pady=(12, 4))
        ctk.CTkLabel(sec1, text="Change Master Password",
                      font=("Helvetica", 13, "bold")).pack(anchor="w", padx=10, pady=6)

        for label, attr, secret in [
            ("Current password", "_cur_pass", True),
            ("New password", "_new_pass", True),
            ("Confirm new", "_confirm_pass", True),
        ]:
            row = ctk.CTkFrame(sec1, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
            var = ctk.StringVar()
            setattr(self, attr + "_var", var)
            ctk.CTkEntry(row, textvariable=var, show="•").pack(side="left", fill="x", expand=True)

        self._pw_status = ctk.CTkLabel(sec1, text="", text_color="#F44336")
        self._pw_status.pack(anchor="w", padx=10)
        ctk.CTkButton(sec1, text="Change Password", width=180,
                       command=self._change_password).pack(padx=10, pady=6)

        # — Export Section —
        sec2 = ctk.CTkFrame(self)
        sec2.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(sec2, text="Export Encrypted Backup",
                      font=("Helvetica", 13, "bold")).pack(anchor="w", padx=10, pady=6)
        ctk.CTkButton(sec2, text="Export…", width=120,
                       command=self._export).pack(padx=10, pady=4)

        # — Audit Log Section —
        sec3 = ctk.CTkFrame(self)
        sec3.pack(fill="both", expand=True, padx=8, pady=4)
        ctk.CTkLabel(sec3, text="Recent Audit Events (last 20)",
                      font=("Helvetica", 13, "bold")).pack(anchor="w", padx=10, pady=6)

        audit_scroll = ctk.CTkScrollableFrame(sec3, height=160)
        audit_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        events = read_audit_log(last_n=20)
        for ev in reversed(events):
            ts = ev.get("ts", "")[:19].replace("T", " ")
            event = ev.get("event", "")
            status = ev.get("status", "")
            key_name = ev.get("key_name", "") or ""
            mark = "✓" if status == "OK" else "❌"
            line = f"{ts}  {mark} {event:<18}  {key_name}"
            ctk.CTkLabel(audit_scroll, text=line, anchor="w",
                          font=("Courier", 11)).pack(fill="x")

    def _change_password(self) -> None:
        cur = self._cur_pass_var.get()  # type: ignore[attr-defined]
        new = self._new_pass_var.get()  # type: ignore[attr-defined]
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
        new_key = derive_key(new, new_params)
        self._payload.master_hash = hash_master_password(new)
        for entry in self._payload.keys.values():
            old_val = decrypt_entry_value(
                self._master_key, entry.id,
                bytes.fromhex(entry.nonce_hex),
                bytes.fromhex(entry.cipher_hex),
            )
            nonce, cipher = encrypt_entry_value(new_key, entry.id, old_val)
            entry.nonce_hex = nonce.hex()
            entry.cipher_hex = cipher.hex()
        storage.save(new_key, new_params, self._payload.to_dict())
        session.unlock(new_key)
        self._master_key = new_key
        self._params = new_params
        audit_log("CHANGE_PASSWORD", status="OK")
        self._pw_status.configure(text="✓ Password changed.", text_color="#4CAF50")

    def _export(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".enc",
            filetypes=[("Encrypted backup", "*.enc")],
            title="Save encrypted backup",
        )
        if not path:
            return
        dialog = ctk.CTkInputDialog(
            text="Enter export password:", title="Export Password"
        )
        export_pass = dialog.get_input()
        if not export_pass or len(export_pass) < 8:
            return
        from pathlib import Path
        exp_params = KDFParams.generate()
        exp_key = derive_key(export_pass, exp_params)
        WalletStorage(Path(path)).save(exp_key, exp_params, self._payload.to_dict())
        audit_log("EXPORT", status="OK", extra=path)


# ------------------------------------------------------------------ #
# Main Window
# ------------------------------------------------------------------ #

class MainWindow(ctk.CTk):
    """Tabbed main window: Keys | Health | Settings."""

    def __init__(self, payload: WalletPayload, master_key: bytes) -> None:
        super().__init__()
        self.title("🔐 VaultKey")
        self.geometry("780x600")
        self.minsize(600, 480)
        self._payload = payload
        self._master_key = master_key
        self._build_ui()

    def _build_ui(self) -> None:
        # Top bar
        bar = ctk.CTkFrame(self, height=48, fg_color="#1a1a2e")
        bar.pack(fill="x")
        ctk.CTkLabel(bar, text="🔐 VaultKey",
                      font=("Helvetica", 18, "bold")).pack(side="left", padx=16, pady=8)

        info = session.info
        ctk.CTkLabel(
            bar,
            text=f"  Unlocked — auto-locks in {info['timeout_minutes']} min",
            text_color="#4CAF50",
        ).pack(side="left")
        ctk.CTkButton(bar, text="🔒 Lock", width=80, height=32,
                       fg_color="#555", hover_color="#c0392b",
                       command=self._lock).pack(side="right", padx=16, pady=8)

        # Tab view
        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=8)

        self._tabs.add("🗝️  Keys")
        self._tabs.add("📊  Health")
        self._tabs.add("⚙️  Settings")

        self._keys_tab = KeysTab(
            self._tabs.tab("🗝️  Keys"),
            self._payload, self._master_key,
            on_data_changed=self._on_data_changed,
        )
        self._keys_tab.pack(fill="both", expand=True)

        self._health_tab = HealthTab(
            self._tabs.tab("📊  Health"),
            self._payload,
        )
        self._health_tab.pack(fill="both", expand=True)

        self._settings_tab = SettingsTab(
            self._tabs.tab("⚙️  Settings"),
            self._payload, self._master_key,
        )
        self._settings_tab.pack(fill="both", expand=True)

    def _on_data_changed(self) -> None:
        """Rebuild Health tab after any data mutation."""
        for w in self._tabs.tab("📊  Health").winfo_children():
            w.destroy()
        self._health_tab = HealthTab(self._tabs.tab("📊  Health"), self._payload)
        self._health_tab.pack(fill="both", expand=True)

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
