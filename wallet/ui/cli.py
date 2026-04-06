"""
cli.py — Typer-based CLI for VaultKey.

All commands require an unlocked session except: init, unlock, status, verify.
Sensitive input (master password, API key value) always prompted with echo=False.

Wave 3 additions:
  - `wallet health`         — per-entry health scores + overall grade
  - `wallet audit`          — human-readable audit log viewer with filtering
  - `wallet verify`         — structural + HMAC integrity check
  - `wallet wipe`           — panic wipe with multi-step confirmation
  - `wallet search`         — fuzzy search alias (delegates to list)
  - `wallet tag`            — add/remove tags without touching crypto
  - All commands emit audit_log() events consistently.

Wave 6 additions:
  - `wallet duplicate <name>` — clone an entry under a new UUID + new nonce.

Wave 7 additions:
  - `wallet rename <name> --to <new-name>` — metadata-only rename (no re-encryption).
  - `wallet expiry-check [--days N]`       — show keys expiring within N days.
    Auto-runs at unlock (silent unless warnings exist).
  - `wallet bulk-import <file>`            — import keys from .env / .json / .csv.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

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
from wallet.utils.audit import audit_log, read_audit_log
from wallet.utils.clipboard import copy_to_clipboard
from wallet.utils.prefix_detect import detect_service, mask_key
from wallet.utils.validators import (
    parse_expiry_date,
    validate_api_key_value,
    validate_key_name,
)

app = typer.Typer(
    name="wallet",
    help="🔐 VaultKey — Ultra-Secure API Key Wallet",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)
console = Console()
cfg = WalletConfig()
session = SessionManager()
storage = WalletStorage(cfg.wallet_path, cfg.backup_dir)


# ------------------------------------------------------------------ #
# Internal helpers
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
    return {"active": "green", "expiring": "yellow",
            "expired": "red", "revoked": "dim"}.get(label, "white")


def _grade_color(grade: str) -> str:
    return {"A": "bright_green", "B": "green", "C": "yellow",
            "D": "orange1", "F": "red"}.get(grade, "white")


def _urgency_color(urgency: str) -> str:
    return {"expired": "red", "critical": "orange1",
            "warning": "yellow", "info": "cyan"}.get(urgency, "white")


def _run_expiry_check_silent(payload: WalletPayload) -> None:
    """Auto-check run at unlock — prints warnings only if entries are near expiry."""
    from wallet.utils.expiry_checker import check_expiry
    warnings = check_expiry(payload, days=7)
    if not warnings:
        return
    console.print(
        f"[yellow]⚠ {len(warnings)} key(s) expiring within 7 days. "
        "Run [bold]wallet expiry-check[/bold] for details.[/yellow]"
    )


# ------------------------------------------------------------------ #
# Commands — Wallet Lifecycle
# ------------------------------------------------------------------ #

@app.command()
def init() -> None:
    """Initialize a new wallet. Sets master password and creates wallet.enc."""
    if storage.exists():
        if not Confirm.ask("[yellow]Wallet already exists. Overwrite?[/yellow]"):
            raise typer.Exit(0)

    console.print(Panel(
        "[bold cyan]VaultKey — New Wallet Setup[/bold cyan]\n"
        "[dim]Your keys never leave this machine.[/dim]",
        expand=False,
    ))
    password = typer.prompt("Master password", hide_input=True)
    confirm = typer.prompt("Confirm master password", hide_input=True)
    if password != confirm:
        console.print("[red]❌ Passwords do not match.[/red]")
        raise typer.Exit(1)
    if len(password) < 8:
        console.print("[red]❌ Password too short (min 8 characters).[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Deriving key (Argon2id 64MB)…[/cyan]"):
        params = KDFParams.generate()
        key = derive_key(password, params)
        master_hash = hash_master_password(password)

    payload = WalletPayload(master_hash=master_hash)
    cfg.wallet_path.parent.mkdir(parents=True, exist_ok=True)
    storage.save(key, params, payload.to_dict())
    audit_log("INIT", status="OK")
    console.print("[green]✓ Wallet created.[/green]")
    console.print(f"[dim]Path: {cfg.wallet_path}[/dim]")


@app.command()
def unlock() -> None:
    """Unlock the wallet. Derives session key from master password."""
    if not storage.exists():
        console.print("[red]❌ No wallet found. Run: wallet init[/red]")
        raise typer.Exit(1)

    password = typer.prompt("Master password", hide_input=True)
    try:
        with console.status("[cyan]Unlocking…[/cyan]"):
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
    info = session.info
    secs = info.get("seconds_until_lock")
    console.print(
        f"[green]✓ Unlocked.[/green] "
        f"[dim]Auto-locks in {cfg.session_timeout_minutes} min"
        + (f" ({secs}s remaining)[/dim]" if secs is not None else ".[/dim]")
    )

    # Wave 7: silent expiry check at unlock
    _run_expiry_check_silent(payload)


@app.command()
def lock() -> None:
    """Lock the wallet and zero the session key from memory."""
    session.lock()
    console.print("[green]🔒 Wallet locked.[/green]")


@app.command()
def status() -> None:
    """Show session state, key count, and pending warnings."""
    info = session.info
    if info["unlocked"]:
        key = _require_unlocked()
        payload = _load_payload(key)
        active = sum(1 for e in payload.keys.values() if e.is_active and not e.is_expired)
        expiring = sum(1 for e in payload.keys.values() if e.expires_soon)
        expired = sum(1 for e in payload.keys.values() if e.is_expired)
        revoked = sum(1 for e in payload.keys.values() if not e.is_active)
        secs = info.get("seconds_until_lock")
        timeout_str = (
            f"{info['timeout_minutes']} min ({secs}s remaining)"
            if secs is not None
            else f"{info['timeout_minutes']} min"
        )
        lines = [
            f"[green]✓ Unlocked[/green]",
            f"Total keys:  {len(payload.keys)}",
            f"Active:      [green]{active}[/green]",
            f"Expiring:    [yellow]{expiring}[/yellow]",
            f"Expired:     [red]{expired}[/red]",
            f"Revoked:     [dim]{revoked}[/dim]",
            f"Unlocked at: {info['unlocked_at']}",
            f"Last action: {info['last_activity']}",
            f"Timeout:     {timeout_str}",
        ]
        console.print(Panel("\n".join(lines), title="🔐 VaultKey Status", expand=False))
    else:
        console.print(Panel("[red]🔒 Locked[/red]", title="VaultKey Status", expand=False))


# ------------------------------------------------------------------ #
# Commands — Key CRUD
# ------------------------------------------------------------------ #

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

    name = validate_key_name(name or Prompt.ask("Key name"))
    raw_value = validate_api_key_value(typer.prompt("API key value", hide_input=True))

    svc_info = detect_service(raw_value)
    if svc_info and not service:
        console.print(f"[dim]Detected: {svc_info.display_name}[/dim]")
        service = svc_info.service_id
    service = service or Prompt.ask("Service name")

    prefix = raw_value[:8]

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


@app.command(name="list")
def list_keys(
    query: Optional[str] = typer.Argument(None),
    tag: Optional[str] = typer.Option(None, "--tag"),
    service: Optional[str] = typer.Option(None, "--service"),
    expired: bool = typer.Option(False, "--expired"),
    sort: str = typer.Option("name", "--sort", help="name|service|added|expires"),
) -> None:
    """List API keys (values never shown)."""
    key = _require_unlocked()
    payload = _load_payload(key)

    results = payload.search(query=query or "", tag=tag or "", service=service or "")
    if expired:
        results = [e for e in results if e.is_expired]

    sort_map = {
        "name": lambda e: e.name.lower(),
        "service": lambda e: e.service.lower(),
        "added": lambda e: e.created_at,
        "expires": lambda e: (e.expires_at or datetime.max.replace(tzinfo=timezone.utc)),
    }
    results.sort(key=sort_map.get(sort, sort_map["name"]))

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Service")
    table.add_column("Tags")
    table.add_column("Added")
    table.add_column("Expires")
    table.add_column("Status")
    table.add_column("Used", justify="right")

    for e in results:
        c = _status_color(e.status_label)
        table.add_row(
            e.name,
            e.service,
            ", ".join(e.tags),
            e.created_at.strftime("%Y-%m-%d"),
            e.expires_at.strftime("%Y-%m-%d") if e.expires_at else "—",
            f"[{c}]{e.status_label}[/{c}]",
            str(e.access_count),
        )

    console.print(table)
    console.print(f"[dim]{len(results)} key(s)[/dim]")


@app.command()
def get(
    name: str = typer.Argument(..., help="Key name or ID"),
    show: bool = typer.Option(False, "--show", help="Show masked value in terminal"),
    raw: bool = typer.Option(False, "--raw", help="Print raw value (for piping)"),
    env: bool = typer.Option(False, "--env", help="Print as export ENV_VAR=value"),
) -> None:
    """Copy API key to clipboard or print in various formats."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    value = decrypt_entry_value(
        key, entry.id,
        bytes.fromhex(entry.nonce_hex),
        bytes.fromhex(entry.cipher_hex),
    )

    entry.access_count += 1
    entry.last_accessed_at = datetime.now(timezone.utc)
    _save_payload(payload, key, params)
    audit_log("GET", key_name=entry.name, status="OK")

    if raw:
        print(value, end="")
    elif env:
        env_var = entry.service.upper().replace("-", "_").replace(" ", "_") + "_API_KEY"
        print(f"export {env_var}={value}")
    elif show:
        console.print(f"[dim]{entry.name}:[/dim] [yellow]{mask_key(value)}[/yellow]")
    else:
        ok = copy_to_clipboard(value, key_name=entry.name, timeout=cfg.clipboard_clear_seconds)
        if ok:
            console.print(
                f"[green]✓ Copied {entry.name} to clipboard.[/green] "
                f"[dim]Clears in {cfg.clipboard_clear_seconds}s[/dim]"
            )


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

    console.print(f"[yellow]About to delete: [bold]{entry.name}[/bold] ({entry.service})[/yellow]")
    if not Confirm.ask("Are you sure?"):
        raise typer.Exit(0)
    confirm_name = Prompt.ask("Type the key name to confirm")
    if confirm_name != entry.name:
        console.print("[red]❌ Name mismatch. Cancelled.[/red]")
        raise typer.Exit(1)

    payload.delete_entry(entry.id)
    _save_payload(payload, key, params)
    audit_log("DELETE", key_name=entry.name, status="OK")
    console.print(f"[green]✓ Deleted: {entry.name}[/green]")


@app.command()
def rename(
    name: str = typer.Argument(..., help="Current key name or ID"),
    new_name: str = typer.Option(..., "--to", "-n", help="New name for the entry"),
) -> None:
    """Rename an entry without re-encrypting the key value.

    This is a metadata-only operation: the UUID and encrypted ciphertext
    remain identical, so no re-encryption cost is incurred.

    Example:
        wallet rename "Stripe Test" --to "Stripe Production"
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    try:
        new_name_validated = validate_key_name(new_name)
        entry = payload.rename_entry(name, new_name_validated)
    except KeyError:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)

    _save_payload(payload, key, params)
    audit_log("RENAME", key_name=new_name_validated, status="OK",
              extra=f"from={name}")
    console.print(
        f"[green]✓ Renamed:[/green] "
        f"[bold]{name}[/bold] → [bold]{new_name_validated}[/bold]"
    )


@app.command()
def info(name: str = typer.Argument(...)) -> None:
    """Show full metadata for a key (value never shown)."""
    key = _require_unlocked()
    payload = _load_payload(key)
    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    from wallet.core.health import analyze_entry
    eh = analyze_entry(entry)
    c = _status_color(entry.status_label)
    gc = _grade_color(eh.grade)
    lines = [
        f"[bold]{entry.name}[/bold]",
        f"  Service:      {entry.service}",
        f"  Prefix:       {entry.prefix or '—'}",
        f"  Description:  {entry.description or '—'}",
        f"  Tags:         {', '.join(entry.tags) or '—'}",
        f"  Created:      {entry.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Updated:      {entry.updated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"  Expires:      {entry.expires_at.strftime('%Y-%m-%d') if entry.expires_at else '—'}",
        f"  Last access:  {entry.last_accessed_at.strftime('%Y-%m-%d %H:%M UTC') if entry.last_accessed_at else 'Never'}",
        f"  Access count: {entry.access_count}",
        f"  Status:       [{c}]{entry.status_label}[/{c}]",
        f"  Health:       [{gc}]{eh.grade} ({eh.score}/100)[/{gc}]",
    ]
    if eh.issues:
        lines.append("  Issues:")
        for issue in eh.issues:
            lines.append(f"    [yellow]⚠ {issue}[/yellow]")
    if eh.recommendations:
        lines.append("  Recommendations:")
        for rec in eh.recommendations:
            lines.append(f"    [dim]→ {rec}[/dim]")
    console.print(Panel("\n".join(lines), title="Key Info", expand=False))


@app.command()
def rotate(name: str = typer.Argument(...)) -> None:
    """Rotate an API key — replace the stored value with a new one."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    new_value = validate_api_key_value(typer.prompt("New API key value", hide_input=True))
    nonce, cipher = encrypt_entry_value(key, entry.id, new_value)
    entry.nonce_hex = nonce.hex()
    entry.cipher_hex = cipher.hex()
    entry.updated_at = datetime.now(timezone.utc)

    _save_payload(payload, key, params)
    audit_log("ROTATE", key_name=entry.name, status="OK")
    console.print(f"[green]✓ Rotated: {entry.name}[/green]")


@app.command()
def duplicate(
    name: str = typer.Argument(..., help="Name of the entry to clone"),
    new_name: Optional[str] = typer.Option(None, "--as", "-n", help="Name for the new entry"),
) -> None:
    """Clone an entry under a new UUID and fresh nonce.

    Decrypts the source entry once, re-encrypts under a brand-new entry ID
    (which changes the HKDF subkey domain) with a fresh random nonce.
    The cloned entry inherits all metadata (service, tags, description,
    expiry) but starts with access_count=0 and a new created_at timestamp.

    Example:
        wallet duplicate "OpenAI Production" --as "OpenAI Staging"
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    source = payload.get_entry(name)
    if not source:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    if not new_name:
        suggested = f"{source.name} (copy)"
        new_name = validate_key_name(
            Prompt.ask("New entry name", default=suggested)
        )
    else:
        new_name = validate_key_name(new_name)

    if payload.get_entry(new_name):
        console.print(f"[red]❌ An entry named '{new_name}' already exists.[/red]")
        raise typer.Exit(1)

    raw_value = decrypt_entry_value(
        key,
        source.id,
        bytes.fromhex(source.nonce_hex),
        bytes.fromhex(source.cipher_hex),
    )

    new_id = str(uuid.uuid4())
    new_nonce, new_cipher = encrypt_entry_value(key, new_id, raw_value)

    clone = APIKeyEntry(
        id=new_id,
        name=new_name,
        service=source.service,
        nonce_hex=new_nonce.hex(),
        cipher_hex=new_cipher.hex(),
        prefix=source.prefix,
        description=source.description,
        tags=",".join(source.tags) if source.tags else "",
        expires_at=source.expires_at,
        created_at=datetime.now(timezone.utc),
        is_active=source.is_active,
        rotation_reminder_days=source.rotation_reminder_days,
    )

    payload.add_entry(clone)
    _save_payload(payload, key, params)
    audit_log("DUPLICATE", key_name=new_name, status="OK",
              extra=f"source={source.name}")
    console.print(
        f"[green]✓ Duplicated:[/green] "
        f"[bold]{source.name}[/bold] → [bold]{new_name}[/bold] "
        f"[dim](new ID: {new_id[:8]}…)[/dim]"
    )


@app.command()
def tag(
    name: str = typer.Argument(..., help="Key name or ID"),
    add_tags: Optional[str] = typer.Option(None, "--add", help="Comma-separated tags to add"),
    remove_tags: Optional[str] = typer.Option(None, "--remove", help="Comma-separated tags to remove"),
) -> None:
    """Add or remove tags from an entry (no re-encryption needed)."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    if add_tags:
        new = [t.strip().lower() for t in add_tags.split(",") if t.strip()]
        entry.tags = list(dict.fromkeys(entry.tags + new))
    if remove_tags:
        rm = {t.strip().lower() for t in remove_tags.split(",")}
        entry.tags = [t for t in entry.tags if t not in rm]

    entry.updated_at = datetime.now(timezone.utc)
    _save_payload(payload, key, params)
    console.print(f"[green]✓ Tags updated: {', '.join(entry.tags) or '(none)'}[/green]")


@app.command()
def search(query: str = typer.Argument(...)) -> None:
    """Fuzzy search across name, service, tags, and description."""
    key = _require_unlocked()
    payload = _load_payload(key)
    results = payload.search(query=query)

    if not results:
        console.print(f"[yellow]No keys matching '{query}'[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Service")
    table.add_column("Tags")
    table.add_column("Status")
    for e in results:
        c = _status_color(e.status_label)
        table.add_row(e.name, e.service, ", ".join(e.tags), f"[{c}]{e.status_label}[/{c}]")
    console.print(table)


# ------------------------------------------------------------------ #
# Commands — Security & Maintenance
# ------------------------------------------------------------------ #

@app.command(name="expiry-check")
def expiry_check(
    days: int = typer.Option(7, "--days", "-d", help="Warning horizon in days"),
    all_entries: bool = typer.Option(False, "--all", "-a", help="Include already-expired keys"),
) -> None:
    """Show API keys expiring within the next N days.

    By default shows keys expiring within 7 days. Use --days 30 for
    a broader sweep. Urgency levels: critical (≤3d), warning (≤7d), info (>7d).

    Also runs automatically (silent) each time the wallet is unlocked.

    Example:
        wallet expiry-check --days 30
    """
    key = _require_unlocked()
    payload = _load_payload(key)

    from wallet.utils.expiry_checker import check_expiry
    warnings = check_expiry(payload, days=days)

    if not all_entries:
        warnings = [w for w in warnings if not w.is_expired]

    if not warnings:
        console.print(f"[green]✓ No keys expiring within {days} day(s).[/green]")
        raise typer.Exit(0)

    table = Table(box=box.ROUNDED, header_style="bold", show_header=True)
    table.add_column("Name", style="bold")
    table.add_column("Service")
    table.add_column("Expires", justify="center")
    table.add_column("Days left", justify="right")
    table.add_column("Urgency", justify="center")

    for w in warnings:
        uc = _urgency_color(w.urgency)
        days_str = "EXPIRED" if w.is_expired else str(w.days_left)
        table.add_row(
            w.name,
            w.service,
            w.expires_at.strftime("%Y-%m-%d"),
            f"[{uc}]{days_str}[/{uc}]",
            f"[{uc}]{w.urgency}[/{uc}]",
        )

    console.print(table)
    console.print(f"[dim]{len(warnings)} key(s) found[/dim]")


@app.command(name="bulk-import")
def bulk_import(
    file: str = typer.Argument(..., help="Path to .env, .json, or .csv file"),
    strategy: str = typer.Option(
        "rename", "--on-conflict",
        help="skip | overwrite | rename (default: rename)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse only — do not save"),
) -> None:
    """Import API keys from a .env, JSON, or CSV file.

    Supported formats:
      .env   — KEY_NAME=value lines (# comments skipped)
      .json  — [{"name", "value", "service", "tags", "description", "expires"}]
      .csv   — header row with at least 'name' and 'value' columns

    Conflict strategies:
      skip       — leave existing entries unchanged
      overwrite  — replace value in-place (same UUID, new nonce)
      rename     — append _imported_N suffix (default)

    Examples:
        wallet bulk-import .env
        wallet bulk-import keys.json --on-conflict overwrite
        wallet bulk-import keys.csv --dry-run
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    src = Path(file)
    if not src.exists():
        console.print(f"[red]❌ File not found: {file}[/red]")
        raise typer.Exit(1)

    valid_strategies = ("skip", "overwrite", "rename")
    if strategy not in valid_strategies:
        console.print(f"[red]❌ Invalid strategy '{strategy}'. Use: {', '.join(valid_strategies)}[/red]")
        raise typer.Exit(1)

    from wallet.utils.bulk_import import apply_bulk_import, parse_file

    try:
        raw_entries = parse_file(src)
    except ValueError as e:
        console.print(f"[red]❌ Parse error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Parsed {len(raw_entries)} entries from {src.name}[/dim]")

    if dry_run:
        table = Table(box=box.SIMPLE, header_style="bold cyan")
        table.add_column("Name")
        table.add_column("Service")
        table.add_column("Tags")
        table.add_column("Expires")
        for r in raw_entries:
            table.add_row(r.name, r.service or "—", r.tags or "—", r.expires or "—")
        console.print(table)
        console.print("[yellow]Dry run — nothing saved.[/yellow]")
        raise typer.Exit(0)

    result = apply_bulk_import(
        raw_entries, payload, key, strategy=strategy  # type: ignore[arg-type]
    )

    if result.errors:
        for err in result.errors:
            console.print(f"[yellow]⚠ {err}[/yellow]")

    _save_payload(payload, key, params)
    audit_log(
        "BULK_IMPORT",
        status="OK",
        extra=(
            f"file={src.name},added={result.added},"
            f"overwritten={result.overwritten},renamed={result.renamed},"
            f"skipped={result.skipped}"
        ),
    )

    lines = [
        f"Added:       [green]{result.added}[/green]",
        f"Overwritten: [cyan]{result.overwritten}[/cyan]",
        f"Renamed:     [blue]{result.renamed}[/blue]",
        f"Skipped:     [dim]{result.skipped}[/dim]",
    ]
    if result.errors:
        lines.append(f"Errors:      [red]{len(result.errors)}[/red]")
    console.print(Panel("\n".join(lines), title=f"✓ Bulk Import — {src.name}", expand=False))


@app.command()
def health(
    all_entries: bool = typer.Option(False, "--all", "-a", help="Show all entries, not just problem ones"),
) -> None:
    """Wallet-wide API key health report with scores and recommendations."""
    key = _require_unlocked()
    payload = _load_payload(key)

    from wallet.core.health import analyze_wallet
    wh = analyze_wallet(payload)

    gc = _grade_color(wh.overall_grade)
    console.print(Panel(
        f"Overall grade: [{gc}][bold]{wh.overall_grade}[/bold][/{gc}]  "
        f"Score: [{gc}]{wh.overall_score}/100[/{gc}]\n"
        f"Healthy: [green]{wh.healthy}[/green]  "
        f"Warning: [yellow]{wh.warning}[/yellow]  "
        f"Critical: [red]{wh.critical}[/red]  "
        f"Total: {wh.total}",
        title="📊 Health Report",
        expand=False,
    ))

    table = Table(box=box.ROUNDED, header_style="bold")
    table.add_column("Name")
    table.add_column("Score", justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Issues")
    table.add_column("Recommendation")

    for eh in wh.entries:
        if not all_entries and eh.score >= 70:
            continue
        gc2 = _grade_color(eh.grade)
        table.add_row(
            eh.name,
            str(eh.score),
            f"[{gc2}]{eh.grade}[/{gc2}]",
            "\n".join(eh.issues) or "—",
            "\n".join(eh.recommendations[:1]) or "—",
        )

    if table.row_count:
        console.print(table)
    elif not all_entries:
        console.print("[green]✓ All keys are healthy (score ≥ 70).[/green]")


@app.command()
def audit(
    last: int = typer.Option(50, "--last", "-n", help="Show last N events"),
    event: Optional[str] = typer.Option(None, "--event", "-e", help="Filter by event type"),
    failed: bool = typer.Option(False, "--failed", help="Show only FAIL events"),
) -> None:
    """View structured audit log with optional filtering."""
    events = read_audit_log(
        last_n=last,
        event_filter=event.upper() if event else None,
        status_filter="FAIL" if failed else None,
    )

    if not events:
        console.print("[dim]No audit events found.[/dim]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE, header_style="bold", show_lines=False)
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Event", style="bold")
    table.add_column("Status")
    table.add_column("Key")
    table.add_column("User", style="dim")
    table.add_column("Extra", style="dim")

    for ev in events:
        status = ev.get("status", "")
        sc = "green" if status == "OK" else "red"
        ts = ev.get("ts", "")[:19].replace("T", " ")
        table.add_row(
            ts,
            ev.get("event", ""),
            f"[{sc}]{status}[/{sc}]",
            ev.get("key_name", "") or "—",
            ev.get("user", ""),
            ev.get("extra", "") or "—",
        )

    console.print(table)
    console.print(f"[dim]{len(events)} event(s)[/dim]")


@app.command()
def verify() -> None:
    """Run structural and HMAC integrity check on the wallet file."""
    if not storage.exists():
        console.print("[red]❌ No wallet found. Run: wallet init[/red]")
        raise typer.Exit(1)

    key = _require_unlocked()
    payload = _load_payload(key)

    from wallet.core.integrity import verify_integrity
    with console.status("[cyan]Verifying integrity…[/cyan]"):
        report = verify_integrity(key, payload, strict=False)

    if report.ok:
        manifest_note = (
            "[green]HMAC manifest valid ✓[/green]"
            if report.hmac_valid
            else "[yellow]No HMAC manifest (pre-v1.1 wallet — will be added on next save)[/yellow]"
        )
        console.print(Panel(
            f"[green]✓ Integrity OK[/green]\n"
            f"Entries checked: {report.entries_checked}\n"
            f"{manifest_note}",
            title="🔍 Integrity Check", expand=False,
        ))
        audit_log("VERIFY", status="OK", extra=f"entries={report.entries_checked}")
    else:
        console.print(Panel(
            f"[red]❌ INTEGRITY FAILURE[/red]\n"
            + "\n".join(f"  ⚠ {e}" for e in report.structural_errors),
            title="🔍 Integrity Check", expand=False,
        ))
        audit_log("VERIFY", status="FAIL",
                  extra=f"errors={len(report.structural_errors)}")
        raise typer.Exit(2)


@app.command()
def change_password() -> None:
    """Change master password and re-encrypt the entire wallet."""
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
    if len(new_pass) < 8:
        console.print("[red]❌ New password too short.[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Re-encrypting all entries…[/cyan]"):
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
    console.print("[green]✓ Password changed. Wallet fully re-encrypted.[/green]")


@app.command()
def wipe(
    delete_audit: bool = typer.Option(False, "--delete-audit", help="Also destroy the audit log"),
) -> None:
    """[red bold]EMERGENCY: Securely destroy the wallet and all backups.[/red bold]"""
    console.print(Panel(
        "[red bold]⚠⚠⚠  PANIC WIPE  ⚠⚠⚠[/red bold]\n"
        "This will PERMANENTLY and IRREVERSIBLY destroy:\n"
        "  • wallet.enc\n"
        "  • All backup files\n"
        + ("  • audit.log\n" if delete_audit else "") +
        "[dim]On SSDs, overwrite is best-effort. Use full-disk encryption for strongest protection.[/dim]",
        title="☠️  Secure Wipe", border_style="red", expand=False,
    ))

    confirm1 = Prompt.ask("Type [bold]WIPE[/bold] to confirm")
    if confirm1 != "WIPE":
        console.print("[green]Cancelled.[/green]")
        raise typer.Exit(0)

    confirm2 = Prompt.ask("Type [bold]CONFIRM[/bold] to execute")
    if confirm2 != "CONFIRM":
        console.print("[green]Cancelled.[/green]")
        raise typer.Exit(0)

    from wallet.core.wipe import panic_wipe
    audit_log("PANIC_WIPE", status="OK")

    summary = panic_wipe(
        cfg.wallet_path,
        cfg.backup_dir,
        session=session,
        delete_audit_log=delete_audit,
        audit_log_path=cfg.audit_log_path,
    )

    lines = []
    lines.append(f"Session wiped: [green]{'yes' if summary['session_wiped'] else 'no'}[/green]")
    lines.append(f"wallet.enc:    [green]{'deleted' if summary['wallet_deleted'] else 'not found'}[/green]")
    lines.append(f"Backups:       [green]{summary['backups_deleted']} file(s) deleted[/green]")
    if delete_audit:
        lines.append(f"audit.log:     [green]{'deleted' if summary['audit_deleted'] else 'not found'}[/green]")
    console.print(Panel("\n".join(lines), title="Wipe Complete", expand=False))


# ------------------------------------------------------------------ #
# Commands — Import / Export
# ------------------------------------------------------------------ #

@app.command(name="export")
def export_wallet(
    output: str = typer.Option("backup.enc", "--output", "-o"),
) -> None:
    """Export wallet to an encrypted backup file (separate password)."""
    key = _require_unlocked()
    payload = _load_payload(key)
    out_path = Path(output)

    export_pass = typer.prompt("Export password", hide_input=True)
    confirm = typer.prompt("Confirm export password", hide_input=True)
    if export_pass != confirm:
        console.print("[red]❌ Passwords do not match.[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Encrypting export…[/cyan]"):
        export_params = KDFParams.generate()
        export_key = derive_key(export_pass, export_params)
        WalletStorage(out_path).save(export_key, export_params, payload.to_dict())

    audit_log("EXPORT", status="OK", extra=str(out_path))
    console.print(f"[green]✓ Exported to {out_path}[/green]")


@app.command(name="import")
def import_wallet(
    file: str = typer.Argument(...),
    strategy: str = typer.Option("rename", "--on-conflict",
                                 help="skip | overwrite | rename"),
) -> None:
    """Import keys from an encrypted backup file."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    src = Path(file)
    if not src.exists():
        console.print(f"[red]❌ File not found: {file}[/red]")
        raise typer.Exit(1)

    import_pass = typer.prompt("Import file password", hide_input=True)
    with console.status("[cyan]Decrypting import…[/cyan]"):
        import_storage = WalletStorage(src)
        import_params = import_storage.read_kdf_params()
        import_key = derive_key(import_pass, import_params)
        import_data = import_storage.load(import_key)

    import_payload = WalletPayload.from_dict(import_data)
    added = 0
    for _entry_id, entry in import_payload.keys.items():
        existing = payload.get_entry(entry.name)
        if existing:
            if strategy == "skip":
                continue
            elif strategy == "overwrite":
                payload.keys[existing.id] = entry
            else:
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


# ------------------------------------------------------------------ #
# Commands — UI Launchers
# ------------------------------------------------------------------ #

@app.command()
def tui() -> None:
    """Launch the interactive full-screen TUI."""
    from wallet.ui.tui import run_tui
    run_tui()


@app.command()
def gui() -> None:
    """Launch the graphical GUI (customtkinter)."""
    from wallet.ui.gui import run_gui
    run_gui()


if __name__ == "__main__":
    app()
