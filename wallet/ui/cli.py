"""
cli.py — Typer-based CLI for VaultKey.

All commands require an unlocked session except: init, unlock, status.
Sensitive input (master password, API key value) is always prompted with
echo=False to prevent terminal display and shell history leakage.

FIXES v1.1:
  FIX #2 (CRITIC): add() now generates the entry UUID BEFORE first encrypt.
    Previously: encrypted with '_tmp_' subkey first, then re-encrypted with
    the real UUID — wasted a HKDF derivation + left a short-lived wrong
    ciphertext in memory. Now: UUID generated upfront, single encrypt call.

  FIX #4 (MODERATE): 'from datetime import datetime, timezone' consolidated
    at module level. Previously imported 3× (module-level + inside get + rotate).
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from wallet.core.crypto import decrypt_entry_value, encrypt_entry_value
from wallet.core.kdf import (
    KDFParams,
    derive_key,
    hash_master_password,
    verify_master_password,
)
from wallet.core.session import (
    SessionManager,
    TooManyAttemptsException,
    WalletLockedException,
)
from wallet.core.storage import WalletCorruptError, WalletStorage
from wallet.models.config import WalletConfig
from wallet.models.wallet import APIKeyEntry, WalletPayload
from wallet.utils.audit import audit_log
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.prefix_detect import detect_service, mask_key
from wallet.utils.validators import (
    parse_expiry_date,
    validate_api_key_value,
    validate_key_name,
)

app = typer.Typer(
    name="wallet",
    help="VaultKey — Secure API Key Wallet",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
console = Console()
cfg = WalletConfig()
session = SessionManager()
storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _require_unlocked() -> bytes:
    try:
        return session.get_key()
    except WalletLockedException as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    except TooManyAttemptsException as e:
        console.print(f"[red]🔒 {e}[/red]")
        raise typer.Exit(1)


def _load_payload(key: bytes) -> WalletPayload:
    try:
        data = storage.load(key)
        return WalletPayload.from_dict(data)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    except WalletCorruptError as e:
        console.print(f"[red]❌ Wallet corrupted: {e}[/red]")
        raise typer.Exit(1)


def _save_payload(payload: WalletPayload, key: bytes, params: KDFParams) -> None:
    storage.save(key, params, payload.to_dict())


def _status_color(label: str) -> str:
    colors = {"active": "green", "expiring": "yellow", "expired": "red", "revoked": "dim"}
    return colors.get(label, "white")


# ------------------------------------------------------------------ #
# Commands
# ------------------------------------------------------------------ #

@app.command()
def init() -> None:
    """Initialize a new wallet. Sets master password and creates wallet.enc."""
    if storage.exists():
        if not Confirm.ask("[yellow]Wallet already exists. Overwrite?[/yellow]"):
            raise typer.Exit(0)

    console.print(Panel("[bold cyan]VaultKey — New Wallet Setup[/bold cyan]", expand=False))
    password = typer.prompt("Master password", hide_input=True)
    confirm = typer.prompt("Confirm master password", hide_input=True)
    if password != confirm:
        console.print("[red]❌ Passwords do not match.[/red]")
        raise typer.Exit(1)
    if len(password) < 8:
        console.print("[red]❌ Password too short (min 8 characters).[/red]")
        raise typer.Exit(1)

    params = KDFParams.generate()
    key = derive_key(password, params)
    master_hash = hash_master_password(password)
    payload = WalletPayload(master_hash=master_hash)
    storage.save(key, params, payload.to_dict())
    audit_log("INIT", status="OK")
    console.print("[green]✓ Wallet created successfully.[/green]")
    console.print(f"[dim]Path: {cfg.wallet_path}[/dim]")


@app.command()
def unlock() -> None:
    """Unlock the wallet. Loads master password and derives session key."""
    if not storage.exists():
        console.print("[red]❌ No wallet found. Run: wallet init[/red]")
        raise typer.Exit(1)

    password = typer.prompt("Master password", hide_input=True)
    try:
        params = storage.read_kdf_params()
        key = derive_key(password, params)
        data = storage.load(key)
        payload = WalletPayload.from_dict(data)
    except ValueError:
        session.record_failed_attempt()
        console.print("[red]❌ Wrong password.[/red]")
        raise typer.Exit(1)

    if not verify_master_password(password, payload.master_hash):
        session.record_failed_attempt()
        console.print("[red]❌ Wrong password.[/red]")
        raise typer.Exit(1)

    session.unlock(key)
    console.print(
        f"[green]✓ Wallet unlocked.[/green] "
        f"[dim]Auto-locks in {cfg.session_timeout_minutes} minutes.[/dim]"
    )


@app.command()
def lock() -> None:
    """Lock the wallet and clear the session key from memory."""
    session.lock()
    console.print("[green]🔒 Wallet locked.[/green]")


@app.command()
def status() -> None:
    """Show wallet status, session info, and key count."""
    info = session.info
    if info["unlocked"]:
        key = _require_unlocked()
        payload = _load_payload(key)
        active = sum(1 for e in payload.keys.values() if e.is_active and not e.is_expired)
        expired = sum(1 for e in payload.keys.values() if e.is_expired)
        console.print(Panel(
            f"[green]✓ Unlocked[/green]\n"
            f"Keys: {len(payload.keys)} total, {active} active, {expired} expired\n"
            f"Unlocked at: {info['unlocked_at']}\n"
            f"Last activity: {info['last_activity']}\n"
            f"Timeout: {info['timeout_minutes']} min",
            title="VaultKey Status", expand=False,
        ))
    else:
        console.print(Panel("[red]🔒 Locked[/red]", title="VaultKey Status", expand=False))


@app.command()
def add(
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    service: Optional[str] = typer.Option(None, "--service", "-s"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    expires: Optional[str] = typer.Option(None, "--expires", "-e", help="YYYY-MM-DD"),
) -> None:
    """Add a new API key to the wallet."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    name = name or Prompt.ask("Key name (e.g. OpenAI Production)")
    name = validate_key_name(name)

    raw_value = typer.prompt("API key value", hide_input=True)
    raw_value = validate_api_key_value(raw_value)

    svc_info = detect_service(raw_value)
    service = service or (
        svc_info.service_id if svc_info else Prompt.ask("Service name")
    )
    prefix = (
        raw_value[: raw_value.index("-") + 1]
        if "-" in raw_value[:12]
        else raw_value[:4]
    )

    # FIX #2: Generate UUID first — encrypt once with the correct subkey.
    # Previously: encrypted with '_tmp_' (wrong subkey), then re-encrypted.
    entry_id = str(uuid.uuid4())
    nonce, cipher = encrypt_entry_value(key, entry_id, raw_value)

    entry = APIKeyEntry(
        id=entry_id,
        name=name,
        service=service,
        nonce_hex=nonce.hex(),
        cipher_hex=cipher.hex(),
        prefix=prefix,
        description=description,
        tags=tags or "",
        expires_at=parse_expiry_date(expires or ""),
    )

    payload.add_entry(entry)
    _save_payload(payload, key, params)
    audit_log("ADD", key_name=name, status="OK")
    console.print(f"[green]✓ Added:[/green] {name} ({service})")
    if svc_info:
        console.print(f"[dim]Detected service: {svc_info.display_name}[/dim]")


@app.command(name="list")
def list_keys(
    query: Optional[str] = typer.Argument(None),
    tag: Optional[str] = typer.Option(None, "--tag"),
    service: Optional[str] = typer.Option(None, "--service"),
    expired: bool = typer.Option(False, "--expired"),
    sort: str = typer.Option("name", "--sort", help="name|service|added|expires"),
) -> None:
    """List API keys (no values shown)."""
    key = _require_unlocked()
    payload = _load_payload(key)

    results = payload.search(query=query or "", tag=tag or "", service=service or "")
    if expired:
        results = [e for e in results if e.is_expired]

    sort_map = {
        "name": lambda e: e.name.lower(),
        "service": lambda e: e.service.lower(),
        "added": lambda e: e.created_at,
        "expires": lambda e: (e.expires_at or e.created_at),
    }
    results.sort(key=sort_map.get(sort, sort_map["name"]))

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Service")
    table.add_column("Tags")
    table.add_column("Added")
    table.add_column("Expires")
    table.add_column("Status")

    for e in results:
        color = _status_color(e.status_label)
        table.add_row(
            e.name,
            e.service,
            ", ".join(e.tags),
            e.created_at.strftime("%Y-%m-%d"),
            e.expires_at.strftime("%Y-%m-%d") if e.expires_at else "—",
            f"[{color}]{e.status_label}[/{color}]",
        )

    console.print(table)
    console.print(f"[dim]{len(results)} key(s) found[/dim]")


@app.command()
def get(
    name: str = typer.Argument(..., help="Key name or ID"),
    show: bool = typer.Option(False, "--show", help="Show masked value"),
    raw: bool = typer.Option(False, "--raw", help="Print raw value to stdout (for piping)"),
    env: bool = typer.Option(False, "--env", help="Print as export ENV_VAR=value"),
) -> None:
    """Copy API key to clipboard (or print in various formats)."""
    key = _require_unlocked()
    payload = _load_payload(key)

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    value = decrypt_entry_value(
        key,
        entry.id,
        bytes.fromhex(entry.nonce_hex),
        bytes.fromhex(entry.cipher_hex),
    )

    # FIX #4: datetime imported at module level — no inline import needed
    entry.access_count += 1
    entry.last_accessed_at = datetime.now(timezone.utc)
    params = storage.read_kdf_params()
    _save_payload(payload, key, params)

    if raw:
        print(value, end="")
    elif env:
        env_var = entry.service.upper().replace("-", "_") + "_API_KEY"
        print(f"export {env_var}={value}")
    elif show:
        console.print(f"[dim]{entry.name}:[/dim] [yellow]{mask_key(value)}[/yellow]")
    else:
        copy_to_clipboard(value, key_name=entry.name, timeout=cfg.clipboard_clear_seconds)
        audit_log("GET", key_name=entry.name, status="OK")


@app.command()
def delete(name: str = typer.Argument(...)) -> None:
    """Delete an API key (requires double confirmation)."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[yellow]About to delete: {entry.name} ({entry.service})[/yellow]")
    if not Confirm.ask("Are you sure?"):
        raise typer.Exit(0)
    confirm_name = Prompt.ask("Type the key name to confirm")
    if confirm_name != entry.name:
        console.print("[red]❌ Name mismatch. Deletion cancelled.[/red]")
        raise typer.Exit(1)

    payload.delete_entry(entry.id)
    _save_payload(payload, key, params)
    audit_log("DELETE", key_name=entry.name, status="OK")
    console.print(f"[green]✓ Deleted: {entry.name}[/green]")


@app.command()
def info(name: str = typer.Argument(...)) -> None:
    """Show detailed metadata for a key (no value shown)."""
    key = _require_unlocked()
    payload = _load_payload(key)
    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    color = _status_color(entry.status_label)
    console.print(Panel(
        f"[bold]{entry.name}[/bold]\n"
        f"Service:     {entry.service}\n"
        f"Prefix:      {entry.prefix or '—'}\n"
        f"Description: {entry.description or '—'}\n"
        f"Tags:        {', '.join(entry.tags) or '—'}\n"
        f"Created:     {entry.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Updated:     {entry.updated_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Expires:     {entry.expires_at.strftime('%Y-%m-%d') if entry.expires_at else '—'}\n"
        f"Last access: "
        f"{entry.last_accessed_at.strftime('%Y-%m-%d %H:%M UTC') if entry.last_accessed_at else 'Never'}\n"
        f"Access count:{entry.access_count}\n"
        f"Status:      [{color}]{entry.status_label}[/{color}]",
        title="Key Info", expand=False,
    ))


@app.command()
def rotate(name: str = typer.Argument(...)) -> None:
    """Rotate an API key — replace with a new value."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    new_value = typer.prompt("New API key value", hide_input=True)
    new_value = validate_api_key_value(new_value)
    nonce, cipher = encrypt_entry_value(key, entry.id, new_value)

    # FIX #4: datetime already imported at module level
    entry.nonce_hex = nonce.hex()
    entry.cipher_hex = cipher.hex()
    entry.updated_at = datetime.now(timezone.utc)

    _save_payload(payload, key, params)
    audit_log("ROTATE", key_name=entry.name, status="OK")
    console.print(f"[green]✓ Rotated: {entry.name}[/green]")


@app.command()
def change_password() -> None:
    """Change the master password and re-encrypt the entire wallet."""
    key = _require_unlocked()
    payload = _load_payload(key)

    current = typer.prompt("Current master password", hide_input=True)
    if not verify_master_password(current, payload.master_hash):
        console.print("[red]❌ Wrong current password.[/red]")
        raise typer.Exit(1)

    new_pass = typer.prompt("New master password", hide_input=True)
    confirm = typer.prompt("Confirm new password", hide_input=True)
    if new_pass != confirm:
        console.print("[red]❌ Passwords do not match.[/red]")
        raise typer.Exit(1)

    new_params = KDFParams.generate()
    new_key = derive_key(new_pass, new_params)
    payload.master_hash = hash_master_password(new_pass)

    for entry in payload.keys.values():
        old_value = decrypt_entry_value(
            key, entry.id,
            bytes.fromhex(entry.nonce_hex),
            bytes.fromhex(entry.cipher_hex),
        )
        nonce, cipher = encrypt_entry_value(new_key, entry.id, old_value)
        entry.nonce_hex = nonce.hex()
        entry.cipher_hex = cipher.hex()

    storage.save(new_key, new_params, payload.to_dict())
    session.unlock(new_key)
    audit_log("CHANGE_PASSWORD", status="OK")
    console.print("[green]✓ Password changed. Wallet re-encrypted.[/green]")


@app.command(name="export")
def export_wallet(
    output: str = typer.Option("backup.enc", "--output", "-o"),
    password: bool = typer.Option(True, "--password/--no-password"),
) -> None:
    """Export wallet to an encrypted backup file."""
    key = _require_unlocked()
    payload = _load_payload(key)

    out_path = Path(output)

    if password:
        export_pass = typer.prompt("Export password", hide_input=True)
        confirm = typer.prompt("Confirm export password", hide_input=True)
        if export_pass != confirm:
            console.print("[red]❌ Passwords do not match.[/red]")
            raise typer.Exit(1)
        export_params = KDFParams.generate()
        export_key = derive_key(export_pass, export_params)
        WalletStorage(out_path).save(export_key, export_params, payload.to_dict())
    else:
        console.print("[red bold]⚠  WARNING: Plaintext export contains unencrypted API keys![/red bold]")
        if not Confirm.ask("Are you absolutely sure?"):
            raise typer.Exit(0)
        out_path.write_text(json.dumps(payload.to_dict(), indent=2))

    audit_log("EXPORT", status="OK", extra=str(out_path))
    console.print(f"[green]✓ Exported to {out_path}[/green]")


@app.command(name="import")
def import_wallet(
    file: str = typer.Argument(...),
    strategy: str = typer.Option("rename", "--on-conflict", help="skip|overwrite|rename"),
) -> None:
    """Import keys from an encrypted or plaintext backup file."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    src = Path(file)
    if not src.exists():
        console.print(f"[red]❌ File not found: {file}[/red]")
        raise typer.Exit(1)

    if src.suffix == ".enc":
        import_pass = typer.prompt("Import file password", hide_input=True)
        import_storage = WalletStorage(src)
        import_params = import_storage.read_kdf_params()
        import_key = derive_key(import_pass, import_params)
        import_data = import_storage.load(import_key)
    else:
        import_data = json.loads(src.read_text())

    import_payload = WalletPayload.from_dict(import_data)
    added = 0
    for _entry_id, entry in import_payload.keys.items():
        existing = payload.get_entry(entry.name)
        if existing:
            if strategy == "skip":
                continue
            elif strategy == "overwrite":
                payload.keys[existing.id] = entry
            else:  # rename
                n, new_name = 1, f"{entry.name}_imported_1"
                while payload.get_entry(new_name):
                    n += 1
                    new_name = f"{entry.name}_imported_{n}"
                entry.name = new_name
                payload.add_entry(entry)
        else:
            payload.add_entry(entry)
        added += 1

    _save_payload(payload, key, params)
    audit_log("IMPORT", status="OK", extra=f"added={added}")
    console.print(f"[green]✓ Imported {added} key(s).[/green]")


@app.command()
def tui() -> None:
    """Launch the interactive TUI (full-screen terminal interface)."""
    from wallet.ui.tui import run_tui
    run_tui()


@app.command()
def gui() -> None:
    """Launch the graphical GUI (customtkinter)."""
    from wallet.ui.gui import run_gui
    run_gui()


if __name__ == "__main__":
    app()
