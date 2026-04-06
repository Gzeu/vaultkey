"""
cli_wave9.py — Wave 9 CLI command groups for VaultKey.

Registers three Typer sub-apps onto the main `app`:

  wallet profile list|add|use|remove|current
      Multi-vault profile manager. Switch between named wallet files.

  wallet share export <name>
  wallet share import <file>
      Per-entry encrypted share tokens (AES-256-GCM, Argon2id passphrase).

  wallet webhook set <url>
  wallet webhook test
  wallet webhook clear
  wallet webhook status
      Webhook notifier for expiry alerts (Slack / Discord / generic).

This module is imported by cli.py via:
    from wallet.ui.cli_wave9 import register_wave9
    register_wave9(app)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


# ------------------------------------------------------------------ #
# Helper: resolve current session/storage from cli.py globals
# ------------------------------------------------------------------ #

def _get_cli_globals():
    """Import live session/storage/cfg from cli.py at call-time."""
    from wallet.ui import cli as _cli
    return _cli.session, _cli.storage, _cli.cfg


def _require_unlocked():
    session, storage, cfg = _get_cli_globals()
    from wallet.core.session import TooManyAttemptsException, WalletLockedException
    try:
        return session.get_key()
    except WalletLockedException as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    except TooManyAttemptsException as e:
        console.print(f"[red]🔒 {e}[/red]")
        raise typer.Exit(1)


def _load_payload(key: bytes):
    _, storage, _ = _get_cli_globals()
    from wallet.core.storage import WalletCorruptError
    from wallet.models.wallet import WalletPayload
    try:
        data = storage.load(key)
        return WalletPayload.from_dict(data)
    except (ValueError, WalletCorruptError) as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)


# ================================================================== #
# Profile commands
# ================================================================== #

profile_app = typer.Typer(
    name="profile",
    help="Manage multiple named vault profiles.",
    no_args_is_help=True,
)


@profile_app.command(name="list")
def profile_list() -> None:
    """List all registered vault profiles."""
    from wallet.utils.vault_profiles import ProfileRegistry
    reg = ProfileRegistry()
    profiles = reg.list_all()

    if not profiles:
        console.print("[dim]No profiles registered. Use: wallet profile add <name> <path>[/dim]")
        return

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Path")
    table.add_column("File", justify="center")
    table.add_column("Active", justify="center")

    for p in profiles:
        active_mark = "[green]●[/green]" if p["active"] else ""
        exists_mark = "[green]✓[/green]" if p["exists"] else "[red]✗[/red]"
        table.add_row(p["name"], p["path"], exists_mark, active_mark)

    console.print(table)
    console.print(f"[dim]Active: {reg.active}[/dim]")


@profile_app.command(name="add")
def profile_add(
    name: str = typer.Argument(..., help="Profile name (e.g. work, personal)"),
    path: str = typer.Argument(..., help="Path to wallet .enc file"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing profile"),
) -> None:
    """Register a new named vault profile."""
    from wallet.utils.vault_profiles import ProfileRegistry
    reg = ProfileRegistry()
    try:
        reg.add(name, Path(path), overwrite=overwrite)
    except ValueError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Profile added:[/green] {name} → {path}")


@profile_app.command(name="use")
def profile_use(
    name: str = typer.Argument(..., help="Profile name to activate"),
) -> None:
    """Switch the active vault profile."""
    from wallet.utils.vault_profiles import ProfileRegistry
    reg = ProfileRegistry()
    try:
        wallet_path = reg.use(name)
    except KeyError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]✓ Switched to profile:[/green] [bold]{name}[/bold]\n"
        f"[dim]Wallet: {wallet_path}[/dim]\n"
        "[yellow]Run [bold]wallet unlock[/bold] to start a new session.[/yellow]"
    )


@profile_app.command(name="remove")
def profile_remove(
    name: str = typer.Argument(..., help="Profile name to remove"),
) -> None:
    """Unregister a vault profile (does not delete the wallet file)."""
    from wallet.utils.vault_profiles import ProfileRegistry
    reg = ProfileRegistry()
    try:
        reg.remove(name)
    except (KeyError, ValueError) as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Profile removed:[/green] {name}")


@profile_app.command(name="current")
def profile_current() -> None:
    """Show the currently active vault profile."""
    from wallet.utils.vault_profiles import ProfileRegistry
    reg = ProfileRegistry()
    active_path = reg.active_path()
    console.print(
        f"[bold]{reg.active}[/bold] "
        + (f"→ {active_path}" if active_path else "[dim](no path set)[/dim]")
    )


# ================================================================== #
# Share commands
# ================================================================== #

share_app = typer.Typer(
    name="share",
    help="Export/import single API keys as encrypted share tokens.",
    no_args_is_help=True,
)


@share_app.command(name="export")
def share_export(
    name: str = typer.Argument(..., help="Key name or ID to export"),
    output: Optional[str] = typer.Option(None, "--output", "-o",
                                         help="Output .vkshare file path"),
) -> None:
    """Export one API key as an encrypted share token (.vkshare file).

    The token is encrypted with a one-time passphrase you choose.
    Send the .vkshare file + passphrase to the recipient separately.
    """
    key = _require_unlocked()
    payload = _load_payload(key)

    entry = payload.get_entry(name)
    if not entry:
        console.print(f"[red]❌ Key '{name}' not found.[/red]")
        raise typer.Exit(1)

    from wallet.core.crypto import decrypt_entry_value
    raw_value = decrypt_entry_value(
        key, entry.id,
        bytes.fromhex(entry.nonce_hex),
        bytes.fromhex(entry.cipher_hex),
    )

    passphrase = typer.prompt("Share passphrase", hide_input=True)
    confirm = typer.prompt("Confirm passphrase", hide_input=True)
    if passphrase != confirm:
        console.print("[red]❌ Passphrases do not match.[/red]")
        raise typer.Exit(1)

    from wallet.utils.share_token import export_share_token, write_token_file
    with console.status("[cyan]Encrypting share token…[/cyan]"):
        token = export_share_token(
            entry_name=entry.name,
            entry_service=entry.service,
            entry_tags=entry.tags,
            entry_description=entry.description,
            entry_expires_at=entry.expires_at,
            raw_value=raw_value,
            passphrase=passphrase,
        )

    out_path = Path(output) if output else Path(f"{entry.name.replace(' ', '_')}.vkshare")
    write_token_file(token, out_path)

    from wallet.utils.audit import audit_log
    audit_log("SHARE_EXPORT", key_name=entry.name, status="OK", extra=str(out_path))

    console.print(
        f"[green]✓ Exported:[/green] {entry.name} → [bold]{out_path}[/bold]\n"
        f"[dim]Send the file and passphrase separately to the recipient.[/dim]"
    )


@share_app.command(name="import")
def share_import(
    file: str = typer.Argument(..., help="Path to .vkshare token file"),
    name_override: Optional[str] = typer.Option(None, "--name",
                                                  help="Override entry name"),
) -> None:
    """Import a share token into the active wallet."""
    key = _require_unlocked()
    payload = _load_payload(key)
    _, storage, _ = _get_cli_globals()
    from wallet.core.storage import WalletStorage
    _, _, cfg = _get_cli_globals()
    params = storage.read_kdf_params()

    src = Path(file)
    if not src.exists():
        console.print(f"[red]❌ File not found: {file}[/red]")
        raise typer.Exit(1)

    from wallet.utils.share_token import import_share_token, read_token_file
    token_str = read_token_file(src)

    passphrase = typer.prompt("Share passphrase", hide_input=True)

    with console.status("[cyan]Decrypting share token…[/cyan]"):
        try:
            data = import_share_token(token_str, passphrase)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)

    import uuid
    from datetime import timezone
    from wallet.core.crypto import encrypt_entry_value
    from wallet.models.wallet import APIKeyEntry
    from wallet.utils.validators import parse_expiry_date

    final_name = name_override or data["name"]
    if payload.get_entry(final_name):
        final_name = f"{final_name}_shared_1"
        n = 1
        while payload.get_entry(final_name):
            n += 1
            final_name = f"{data['name']}_shared_{n}"

    entry_id = str(uuid.uuid4())
    nonce, cipher = encrypt_entry_value(key, entry_id, data["value"])

    from datetime import datetime
    expires_at = None
    if data.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(data["expires_at"])
        except ValueError:
            pass

    new_entry = APIKeyEntry(
        id=entry_id,
        name=final_name,
        service=data.get("service", ""),
        nonce_hex=nonce.hex(),
        cipher_hex=cipher.hex(),
        prefix=data["value"][:8],
        description=data.get("description"),
        tags=data.get("tags", []),
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )

    payload.add_entry(new_entry)
    storage.save(key, params, payload.to_dict())

    from wallet.utils.audit import audit_log
    audit_log("SHARE_IMPORT", key_name=final_name, status="OK", extra=str(src))
    console.print(f"[green]✓ Imported:[/green] [bold]{final_name}[/bold] ({new_entry.service})")


# ================================================================== #
# Webhook commands
# ================================================================== #

webhook_app = typer.Typer(
    name="webhook",
    help="Configure webhook notifications for expiry alerts.",
    no_args_is_help=True,
)


@webhook_app.command(name="set")
def webhook_set(
    url: str = typer.Argument(..., help="Webhook URL (Slack / Discord / custom)"),
    fmt: str = typer.Option("generic", "--format", "-f",
                            help="Payload format: slack | discord | generic"),
    min_days: int = typer.Option(7, "--min-days",
                                 help="Only notify if days_left ≤ this value"),
) -> None:
    """Set (or update) the webhook URL and format."""
    from wallet.utils.webhook import WebhookConfig, save_webhook_config

    valid_formats = ("slack", "discord", "generic")
    if fmt not in valid_formats:
        console.print(f"[red]❌ Invalid format '{fmt}'. Use: {', '.join(valid_formats)}[/red]")
        raise typer.Exit(1)

    cfg = WebhookConfig(url=url, format=fmt, enabled=True, min_days=min_days)
    save_webhook_config(cfg)
    console.print(
        f"[green]✓ Webhook configured.[/green]\n"
        f"  URL:     {url}\n"
        f"  Format:  {fmt}\n"
        f"  Min days: {min_days}"
    )


@webhook_app.command(name="test")
def webhook_test() -> None:
    """Send a test payload to the configured webhook URL."""
    from wallet.utils.webhook import WebhookConfig, load_webhook_config, send_test_notification

    cfg = load_webhook_config()
    if not cfg:
        console.print("[red]❌ No webhook configured. Run: wallet webhook set <url>[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Sending test notification…[/cyan]"):
        ok, msg = send_test_notification(cfg)

    if ok:
        console.print(f"[green]✓ Test sent successfully ({msg})[/green]")
    else:
        console.print(f"[red]❌ Test failed: {msg}[/red]")
        raise typer.Exit(1)


@webhook_app.command(name="clear")
def webhook_clear() -> None:
    """Remove the webhook configuration."""
    from wallet.utils.webhook import clear_webhook_config

    removed = clear_webhook_config()
    if removed:
        console.print("[green]✓ Webhook configuration removed.[/green]")
    else:
        console.print("[dim]No webhook configuration found.[/dim]")


@webhook_app.command(name="status")
def webhook_status() -> None:
    """Show current webhook configuration."""
    from wallet.utils.webhook import load_webhook_config

    cfg = load_webhook_config()
    if not cfg:
        console.print("[dim]No webhook configured.[/dim]")
        return

    enabled_str = "[green]enabled[/green]" if cfg.enabled else "[red]disabled[/red]"
    console.print(Panel(
        f"URL:      {cfg.url}\n"
        f"Format:   {cfg.format}\n"
        f"Min days: {cfg.min_days}\n"
        f"Status:   {enabled_str}",
        title="🔔 Webhook Config",
        expand=False,
    ))


# ================================================================== #
# Registration
# ================================================================== #


def register_wave9(app: typer.Typer) -> None:
    """Attach all Wave 9 sub-apps to the main Typer application."""
    app.add_typer(profile_app, name="profile")
    app.add_typer(share_app, name="share")
    app.add_typer(webhook_app, name="webhook")
