"""
cli_extensions.py — Wave 10 CLI commands for VaultKey.

This module registers additional Typer sub-apps and commands on the main
`app` object from wallet/ui/cli.py. Import this module in cli.py to activate.

New commands added:
    wallet gen-password        — Generate a secure random password
    wallet gen-passphrase      — Generate a memorable passphrase
    wallet import-external     — Import from Bitwarden/1Password/KeePass export
    wallet stats               — Show vault statistics and analytics
    wallet export-report       — Export Markdown or redacted JSON report
    wallet search-advanced     — Advanced boolean/regex search
    wallet note add            — Add a secure note
    wallet note get            — Retrieve and display a note
    wallet note list           — List all notes
    wallet note delete         — Delete a note
    wallet mvx add             — Store a MultiversX wallet key
    wallet mvx get             — Retrieve MVX seed/privkey to clipboard
    wallet mvx list            — List MultiversX entries
    wallet mvx delete          — Delete an MVX entry

Integration: add this import at the bottom of wallet/ui/cli.py:
    from wallet.utils import cli_extensions  # noqa: F401  (activates commands)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import the main app and helpers from cli.py
from wallet.ui.cli import (
    _load_payload,
    _require_unlocked,
    _save_payload,
    _status_color,
    app,
    cfg,
    console,
    session,
    storage,
)
from wallet.utils.audit import audit_log


# ------------------------------------------------------------------ #
# Sub-apps
# ------------------------------------------------------------------ #

note_app = typer.Typer(help="Manage encrypted secure notes.")
app.add_typer(note_app, name="note")

mvx_app = typer.Typer(help="Manage MultiversX (EGLD) wallet keys.")
app.add_typer(mvx_app, name="mvx")


# ================================================================== #
# Password / Passphrase generators
# ================================================================== #

@app.command(name="gen-password")
def gen_password(
    length: int = typer.Option(20, "--length", "-l", help="Password length (8-128)"),
    no_symbols: bool = typer.Option(False, "--no-symbols", help="Exclude symbols"),
    no_ambiguous: bool = typer.Option(False, "--no-ambiguous", help="Exclude 0/O/1/l/I"),
    count: int = typer.Option(1, "--count", "-n", help="Number of passwords to generate"),
    show_score: bool = typer.Option(True, "--score/--no-score", help="Show strength score"),
) -> None:
    """Generate one or more cryptographically secure random passwords.

    Examples:
        wallet gen-password
        wallet gen-password --length 32 --no-symbols
        wallet gen-password --count 5 --length 16
    """
    from wallet.utils.password_generator import CharsetFlags, generate_with_score

    flags = CharsetFlags.ALL
    if no_symbols:
        flags = CharsetFlags.ALPHANUM

    length = max(8, min(128, length))

    table = Table(box=box.SIMPLE, header_style="bold cyan", show_header=count > 1 or show_score)
    table.add_column("Password", style="bold yellow")
    if show_score:
        table.add_column("Score", justify="center")
        table.add_column("Entropy", justify="right")
        table.add_column("Label")

    for _ in range(max(1, min(count, 20))):
        result = generate_with_score(length, flags, exclude_ambiguous=no_ambiguous)
        score_colors = ["red", "orange1", "yellow", "green", "bright_green"]
        sc = result.score.score
        color = score_colors[sc]
        if show_score:
            table.add_row(
                result.password,
                f"[{color}]{sc}/4[/{color}]",
                f"{result.score.entropy_bits} bits",
                f"[{color}]{result.score.label}[/{color}]",
            )
        else:
            table.add_row(result.password)

    console.print(table)


@app.command(name="gen-passphrase")
def gen_passphrase(
    words: int = typer.Option(6, "--words", "-w", help="Number of words (4-12)"),
    separator: str = typer.Option("-", "--sep", "-s", help="Word separator"),
    capitalize: bool = typer.Option(False, "--capitalize", "-c"),
    no_number: bool = typer.Option(False, "--no-number", help="Omit trailing number"),
    count: int = typer.Option(1, "--count", "-n"),
) -> None:
    """Generate memorable passphrases from a word list.

    Examples:
        wallet gen-passphrase
        wallet gen-passphrase --words 8 --sep ' '
        wallet gen-passphrase --count 3 --capitalize
    """
    from wallet.utils.password_generator import generate_passphrase, score_password

    words = max(4, min(12, words))
    count = max(1, min(20, count))

    for _ in range(count):
        phrase = generate_passphrase(
            word_count=words,
            separator=separator,
            capitalize=capitalize,
            append_number=not no_number,
        )
        sc = score_password(phrase)
        score_colors = ["red", "orange1", "yellow", "green", "bright_green"]
        color = score_colors[sc.score]
        console.print(
            f"[bold yellow]{phrase}[/bold yellow]  "
            f"[{color}]{sc.label} ({sc.entropy_bits} bits)[/{color}]"
        )


# ================================================================== #
# External import (Bitwarden / 1Password / KeePass)
# ================================================================== #

@app.command(name="import-external")
def import_external(
    file: str = typer.Argument(..., help="Path to Bitwarden JSON, 1Password CSV, or KeePass CSV"),
    fmt: str = typer.Option("auto", "--format", "-f",
                            help="auto | bitwarden | 1password | keepass"),
    strategy: str = typer.Option("rename", "--on-conflict",
                                 help="skip | overwrite | rename"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Import secrets from Bitwarden, 1Password, or KeePass export files.

    Examples:
        wallet import-external vault_export.json
        wallet import-external export.csv --format 1password
        wallet import-external keepass.csv --format keepass --on-conflict skip
        wallet import-external vault.json --dry-run
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    src = Path(file)
    if not src.exists():
        console.print(f"[red]\u274c File not found: {file}[/red]")
        raise typer.Exit(1)

    from wallet.utils.bitwarden_import import SourceFormat, parse_external_export
    from wallet.utils.bulk_import import apply_bulk_import

    fmt_typed: SourceFormat = fmt  # type: ignore[assignment]

    try:
        result = parse_external_export(src, fmt=fmt_typed)
    except ValueError as e:
        console.print(f"[red]\u274c Parse error: {e}[/red]")
        raise typer.Exit(1)

    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]\u26a0 {w.item_title}: {w.reason}[/yellow]")

    console.print(f"[dim]Parsed {result.count} entries from {src.name}[/dim]")

    if dry_run:
        table = Table(box=box.SIMPLE, header_style="bold cyan")
        table.add_column("Name")
        table.add_column("Service")
        table.add_column("Tags")
        for r in result.entries:
            table.add_row(r.name, r.service or "—", r.tags or "—")
        console.print(table)
        console.print("[yellow]Dry run — nothing saved.[/yellow]")
        raise typer.Exit(0)

    if strategy not in ("skip", "overwrite", "rename"):
        console.print("[red]\u274c Invalid strategy. Use: skip | overwrite | rename[/red]")
        raise typer.Exit(1)

    import_result = apply_bulk_import(
        result.entries, payload, key, strategy=strategy  # type: ignore[arg-type]
    )
    if import_result.errors:
        for err in import_result.errors:
            console.print(f"[yellow]\u26a0 {err}[/yellow]")

    _save_payload(payload, key, params)
    audit_log(
        "IMPORT_EXTERNAL", status="OK",
        extra=(
            f"source={src.name},fmt={fmt},"
            f"added={import_result.added},skipped={import_result.skipped},"
            f"warnings={len(result.warnings)}"
        ),
    )
    lines = [
        f"Added:       [green]{import_result.added}[/green]",
        f"Overwritten: [cyan]{import_result.overwritten}[/cyan]",
        f"Renamed:     [blue]{import_result.renamed}[/blue]",
        f"Skipped:     [dim]{import_result.skipped}[/dim]",
        f"Warnings:    [yellow]{len(result.warnings)}[/yellow]",
    ]
    console.print(Panel("\n".join(lines), title=f"\u2713 Import — {src.name}", expand=False))


# ================================================================== #
# Stats
# ================================================================== #

@app.command(name="stats")
def stats(
    top: int = typer.Option(5, "--top", "-n", help="Number of top items per category"),
    export_md: Optional[str] = typer.Option(
        None, "--export-md", help="Save Markdown report to this path"
    ),
) -> None:
    """Show vault statistics: usage, rotation, tag distribution, score.

    Examples:
        wallet stats
        wallet stats --top 10
        wallet stats --export-md vault_report.md
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    from wallet.utils.stats import VaultStats, compute_stats, format_stats_report

    st = compute_stats(payload)

    score_color = (
        "bright_green" if st.vault_score >= 80
        else "green" if st.vault_score >= 60
        else "yellow" if st.vault_score >= 40
        else "red"
    )

    console.print(Panel(
        f"Vault Score: [{score_color}][bold]{st.vault_score}/100[/bold][/{score_color}]\n"
        f"Total: {st.total}  Active: [green]{st.active}[/green]  "
        f"Expired: [red]{st.expired}[/red]  "
        f"Expiring: [yellow]{st.expiring_soon}[/yellow]  "
        f"Revoked: [dim]{st.revoked}[/dim]\n"
        f"Unused (30d+): [yellow]{st.unused}[/yellow]  "
        f"Never rotated: [orange1]{st.never_rotated}[/orange1]\n"
        f"Avg age: {st.average_age_days}d  "
        f"Avg rotation lag: {st.average_rotation_lag_days}d",
        title="\U0001f4ca Vault Statistics",
        expand=False,
    ))

    if st.tag_distribution:
        tag_table = Table(box=box.SIMPLE, title="Top Tags", header_style="bold cyan")
        tag_table.add_column("Tag")
        tag_table.add_column("Count", justify="right")
        for tag, count in list(st.tag_distribution.items())[:top]:
            tag_table.add_row(tag, str(count))
        console.print(tag_table)

    if st.most_accessed:
        acc_table = Table(box=box.SIMPLE, title="Most Accessed", header_style="bold cyan")
        acc_table.add_column("Name")
        acc_table.add_column("Service")
        acc_table.add_column("Accesses", justify="right")
        for a in st.most_accessed[:top]:
            acc_table.add_row(a.name, a.service, str(a.access_count))
        console.print(acc_table)

    if export_md:
        from wallet.utils.batch_export import export_markdown
        n = export_markdown(payload, Path(export_md))
        console.print(f"[green]\u2713 Markdown report saved: {export_md} ({n} entries)[/green]")


# ================================================================== #
# Export report
# ================================================================== #

@app.command(name="export-report")
def export_report(
    output: str = typer.Option("vault_report.md", "--output", "-o"),
    fmt: str = typer.Option("markdown", "--format", "-f",
                            help="markdown | json_redacted | encrypted_json"),
) -> None:
    """Export vault inventory report (no key values included unless encrypted).

    Examples:
        wallet export-report
        wallet export-report --output audit.json --format json_redacted
        wallet export-report --output backup.enc --format encrypted_json
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    from wallet.utils.batch_export import ExportFormat, export_vault

    out_path = Path(output)
    fmt_typed: ExportFormat = fmt  # type: ignore[assignment]
    export_password: Optional[str] = None

    if fmt == "encrypted_json":
        export_password = typer.prompt("Export password", hide_input=True)
        if typer.prompt("Confirm export password", hide_input=True) != export_password:
            console.print("[red]\u274c Passwords do not match.[/red]")
            raise typer.Exit(1)

    try:
        n = export_vault(
            payload, out_path, fmt_typed,
            master_key=key if fmt == "encrypted_json" else None,
            export_password=export_password,
        )
    except ValueError as e:
        console.print(f"[red]\u274c {e}[/red]")
        raise typer.Exit(1)

    audit_log("EXPORT", status="OK", extra=f"fmt={fmt},file={output},entries={n}")
    console.print(f"[green]\u2713 Exported {n} entries to {output} ({fmt})[/green]")


# ================================================================== #
# Advanced search
# ================================================================== #

@app.command(name="search-advanced")
def search_advanced_cmd(
    query: str = typer.Argument(..., help="Search query (see docs for syntax)"),
    include_revoked: bool = typer.Option(False, "--revoked"),
    no_expired: bool = typer.Option(False, "--no-expired"),
) -> None:
    """Advanced boolean/regex search across all vault entries.

    Query syntax:
        name:openai          — field-scoped
        tag:prod OR tag:dev  — boolean OR
        NOT tag:deprecated   — negation
        /^sk-[a-z]/          — regex

    Examples:
        wallet search-advanced "name:openai"
        wallet search-advanced "tag:production NOT expired"
        wallet search-advanced "/^sk-/ NOT tag:test"
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    from wallet.utils.search_advanced import advanced_search

    results = advanced_search(
        payload, query,
        include_revoked=include_revoked,
        include_expired=not no_expired,
    )

    if not results:
        console.print(f"[yellow]No entries matching: {query!r}[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Service")
    table.add_column("Tags")
    table.add_column("Status")
    table.add_column("Score", justify="right")
    table.add_column("Matched fields")
    for r in results:
        c = _status_color(r.entry.status_label)
        table.add_row(
            r.entry.name, r.entry.service,
            ", ".join(r.entry.tags),
            f"[{c}]{r.entry.status_label}[/{c}]",
            str(r.score),
            ", ".join(r.matched_fields[:3]),
        )
    console.print(table)
    console.print(f"[dim]{len(results)} result(s) for: {query!r}[/dim]")


# ================================================================== #
# Secure Notes
# ================================================================== #

@note_app.command(name="add")
def note_add(
    title: str = typer.Argument(..., help="Note title"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t"),
    pinned: bool = typer.Option(False, "--pin"),
) -> None:
    """Add a new encrypted secure note. Body is entered interactively."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    console.print("[dim]Enter note body (paste text, then press Ctrl+D / Ctrl+Z+Enter to finish):[/dim]")
    import sys
    body_lines = []
    try:
        for line in sys.stdin:
            body_lines.append(line)
    except KeyboardInterrupt:
        pass
    body = "".join(body_lines).strip()

    if not body:
        console.print("[red]\u274c Note body cannot be empty.[/red]")
        raise typer.Exit(1)

    from wallet.utils.notes import create_note

    try:
        note = create_note(key, title, body, tags=tags or "", pinned=pinned)
    except ValueError as e:
        console.print(f"[red]\u274c {e}[/red]")
        raise typer.Exit(1)

    # Store in payload extra field
    if not hasattr(payload, "notes") or not isinstance(getattr(payload, "notes", None), dict):
        object.__setattr__(payload, "notes", {})
    notes_dict = getattr(payload, "notes")
    notes_dict[note.id] = note.model_dump(mode="json")
    payload.touch()

    _save_payload(payload, key, params)
    audit_log("NOTE_ADD", key_name=title, status="OK")
    console.print(f"[green]\u2713 Note added:[/green] {title} (id: {note.id[:8]}...)")
    if pinned:
        console.print("[cyan]\U0001f4cc Pinned[/cyan]")


@note_app.command(name="get")
def note_get(
    title_or_id: str = typer.Argument(..., help="Note title or ID"),
) -> None:
    """Decrypt and display a secure note."""
    key = _require_unlocked()
    payload = _load_payload(key)
    from wallet.utils.notes import SecureNote, retrieve_note_body

    notes_raw = getattr(payload, "notes", {})
    if not isinstance(notes_raw, dict):
        notes_raw = {}

    # Find by ID prefix or title
    target = None
    for nid, ndata in notes_raw.items():
        note = SecureNote.model_validate(ndata) if isinstance(ndata, dict) else ndata
        if nid == title_or_id or nid.startswith(title_or_id) or note.title.lower() == title_or_id.lower():
            target = note
            break

    if target is None:
        console.print(f"[red]\u274c Note '{title_or_id}' not found.[/red]")
        raise typer.Exit(1)

    try:
        body = retrieve_note_body(key, target)
    except Exception as e:
        console.print(f"[red]\u274c Decryption failed: {e}[/red]")
        raise typer.Exit(1)

    pin_icon = "\U0001f4cc " if target.pinned else ""
    tags_str = ", ".join(target.tags) if target.tags else "—"
    console.print(Panel(
        body,
        title=f"{pin_icon}[bold]{target.title}[/bold]  [dim]tags: {tags_str}[/dim]  "
              f"[dim]updated: {target.updated_at.strftime('%Y-%m-%d')}[/dim]",
        expand=True,
    ))


@note_app.command(name="list")
def note_list(
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
    query: Optional[str] = typer.Argument(None),
) -> None:
    """List all secure notes (titles only)."""
    key = _require_unlocked()
    payload = _load_payload(key)
    from wallet.utils.notes import SecureNote, list_notes

    notes_raw = getattr(payload, "notes", {})
    if not isinstance(notes_raw, dict) or not notes_raw:
        console.print("[dim]No notes found. Add one with: wallet note add \"My Note\"[/dim]")
        raise typer.Exit(0)

    notes_dict = {
        k: SecureNote.model_validate(v) if isinstance(v, dict) else v
        for k, v in notes_raw.items()
    }

    results = list_notes(notes_dict, tag=tag or "", query=query or "")

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Pin", justify="center", width=3)
    table.add_column("Title", style="bold")
    table.add_column("Tags")
    table.add_column("Updated")
    table.add_column("ID", style="dim")
    for note in results:
        pin = "\U0001f4cc" if note.pinned else ""
        table.add_row(
            pin, note.title, ", ".join(note.tags) or "—",
            note.updated_at.strftime("%Y-%m-%d"),
            note.id[:8] + "...",
        )
    console.print(table)
    console.print(f"[dim]{len(results)} note(s)[/dim]")


@note_app.command(name="delete")
def note_delete(title_or_id: str = typer.Argument(...)) -> None:
    """Delete a secure note permanently."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()
    from wallet.utils.notes import SecureNote
    from rich.prompt import Confirm

    notes_raw = getattr(payload, "notes", {})
    if not isinstance(notes_raw, dict):
        console.print("[red]\u274c No notes found.[/red]")
        raise typer.Exit(1)

    target_id = None
    for nid, ndata in notes_raw.items():
        note = SecureNote.model_validate(ndata) if isinstance(ndata, dict) else ndata
        if nid == title_or_id or nid.startswith(title_or_id) or note.title.lower() == title_or_id.lower():
            target_id = nid
            target_title = note.title
            break

    if target_id is None:
        console.print(f"[red]\u274c Note '{title_or_id}' not found.[/red]")
        raise typer.Exit(1)

    if not Confirm.ask(f"Delete note '[bold]{target_title}[/bold]'?"):
        raise typer.Exit(0)

    del notes_raw[target_id]
    payload.touch()
    _save_payload(payload, key, params)
    audit_log("NOTE_DELETE", key_name=target_title, status="OK")
    console.print(f"[green]\u2713 Note deleted: {target_title}[/green]")


# ================================================================== #
# MultiversX (EGLD) commands
# ================================================================== #

@mvx_app.command(name="add")
def mvx_add(
    label: str = typer.Argument(..., help="Human-readable wallet label"),
    address: Optional[str] = typer.Option(None, "--address", "-a", help="erd1... address"),
    network: str = typer.Option("mainnet", "--network", "-n",
                                help="mainnet | devnet | testnet"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t"),
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    has_seed: bool = typer.Option(True, "--seed/--no-seed",
                                   help="Prompt for BIP-39 seed phrase"),
    has_privkey: bool = typer.Option(False, "--privkey",
                                     help="Also prompt for private key hex"),
) -> None:
    """Store a MultiversX wallet seed phrase and/or private key securely.

    Examples:
        wallet mvx add \"My EGLD Wallet\"
        wallet mvx add \"Trading Wallet\" --network devnet --no-seed --privkey
        wallet mvx add \"Cold Storage\" --address erd1abc... --tags cold,egld
    """
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    from wallet.core.mvx import store_mvx_entry
    from wallet.core.mvx_wallet_payload import MvxPayloadMixin
    from wallet.utils.validators import validate_key_name

    seed_phrase: Optional[str] = None
    privkey_hex: Optional[str] = None

    if has_seed:
        seed_phrase = typer.prompt(
            "BIP-39 seed phrase (12/15/18/21/24 words)", hide_input=True
        )
    if has_privkey:
        privkey_hex = typer.prompt("Private key hex (64 chars)", hide_input=True)

    if not seed_phrase and not privkey_hex:
        console.print("[red]\u274c Provide at least a seed phrase or private key.[/red]")
        raise typer.Exit(1)

    try:
        entry = store_mvx_entry(
            key, label,
            seed_phrase=seed_phrase,
            privkey_hex=privkey_hex,
            address=address,
            network=network,
            description=description,
            tags=tags or "",
        )
    except ValueError as e:
        console.print(f"[red]\u274c {e}[/red]")
        raise typer.Exit(1)

    mvx = MvxPayloadMixin(payload)
    mvx.add_mvx_entry(entry)
    data = mvx.to_dict_with_mvx()
    storage.save(key, params, data)

    audit_log("MVX_ADD", key_name=label, status="OK",
              extra=f"network={network},has_seed={has_seed},has_privkey={has_privkey}")
    console.print(f"[green]\u2713 MultiversX wallet stored:[/green] {label}")
    if address:
        console.print(f"[dim]Address: {address}[/dim]")


@mvx_app.command(name="get")
def mvx_get(
    label_or_id: str = typer.Argument(..., help="Label or ID of the MVX entry"),
    show_seed: bool = typer.Option(False, "--seed", help="Reveal seed phrase"),
    show_privkey: bool = typer.Option(False, "--privkey", help="Reveal private key"),
) -> None:
    """Retrieve and display a MultiversX wallet entry.

    Secret values are only shown with explicit flags.

    Examples:
        wallet mvx get \"My EGLD Wallet\"
        wallet mvx get \"My EGLD Wallet\" --seed
        wallet mvx get \"My EGLD Wallet\" --privkey
    """
    key = _require_unlocked()
    payload = _load_payload(key)

    from wallet.core.mvx import retrieve_mvx_privkey, retrieve_mvx_seed
    from wallet.core.mvx_wallet_payload import MvxPayloadMixin

    mvx = MvxPayloadMixin(payload)
    entry = mvx.get_mvx_entry(label_or_id)

    if entry is None:
        console.print(f"[red]\u274c MultiversX entry '{label_or_id}' not found.[/red]")
        raise typer.Exit(1)

    lines = [
        f"[bold]{entry.label}[/bold]",
        f"  Network:     {entry.network}",
        f"  Address:     {entry.address or '\u2014'}",
        f"  Tags:        {', '.join(entry.tags) or '\u2014'}",
        f"  Description: {entry.description or '\u2014'}",
        f"  Has seed:    {'yes' if entry.has_seed else 'no'}",
        f"  Has privkey: {'yes' if entry.has_privkey else 'no'}",
        f"  Created:     {entry.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
    ]

    if show_seed:
        if not entry.has_seed:
            console.print("[yellow]\u26a0 No seed phrase stored for this entry.[/yellow]")
        else:
            seed = retrieve_mvx_seed(key, entry)
            lines.append(f"  [bold red]Seed phrase:[/bold red] [yellow]{seed}[/yellow]")
            audit_log("MVX_GET_SEED", key_name=entry.label, status="OK")

    if show_privkey:
        if not entry.has_privkey:
            console.print("[yellow]\u26a0 No private key stored for this entry.[/yellow]")
        else:
            pk = retrieve_mvx_privkey(key, entry)
            lines.append(f"  [bold red]Private key:[/bold red] [yellow]{pk}[/yellow]")
            audit_log("MVX_GET_PRIVKEY", key_name=entry.label, status="OK")

    console.print(Panel("\n".join(lines), title="MultiversX Wallet", expand=False))


@mvx_app.command(name="list")
def mvx_list(
    network: Optional[str] = typer.Option(None, "--network", "-n"),
    query: Optional[str] = typer.Argument(None),
) -> None:
    """List all stored MultiversX wallet entries."""
    key = _require_unlocked()
    payload = _load_payload(key)

    from wallet.core.mvx_wallet_payload import MvxPayloadMixin

    mvx = MvxPayloadMixin(payload)
    results = mvx.search_mvx(query=query or "", network=network or "")

    if not results:
        console.print("[dim]No MultiversX entries. Add one with: wallet mvx add \"My Wallet\"[/dim]")
        raise typer.Exit(0)

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Label", style="bold")
    table.add_column("Network")
    table.add_column("Address", style="dim")
    table.add_column("Tags")
    table.add_column("Has Seed", justify="center")
    table.add_column("Has Key", justify="center")
    for entry in results:
        addr = entry.address[:16] + "..." if entry.address and len(entry.address) > 20 else (entry.address or "—")
        table.add_row(
            entry.label,
            entry.network,
            addr,
            ", ".join(entry.tags) or "—",
            "[green]\u2713[/green]" if entry.has_seed else "[dim]\u2014[/dim]",
            "[green]\u2713[/green]" if entry.has_privkey else "[dim]\u2014[/dim]",
        )
    console.print(table)
    console.print(f"[dim]{len(results)} MultiversX wallet(s)[/dim]")


@mvx_app.command(name="delete")
def mvx_delete(label_or_id: str = typer.Argument(...)) -> None:
    """Delete a stored MultiversX wallet entry."""
    key = _require_unlocked()
    payload = _load_payload(key)
    params = storage.read_kdf_params()

    from wallet.core.mvx_wallet_payload import MvxPayloadMixin
    from rich.prompt import Confirm

    mvx = MvxPayloadMixin(payload)
    entry = mvx.get_mvx_entry(label_or_id)

    if entry is None:
        console.print(f"[red]\u274c MultiversX entry '{label_or_id}' not found.[/red]")
        raise typer.Exit(1)

    console.print(
        f"[yellow]About to delete MultiversX entry: [bold]{entry.label}[/bold][/yellow]"
    )
    if not Confirm.ask("Are you sure?"):
        raise typer.Exit(0)

    mvx.delete_mvx_entry(label_or_id)
    data = mvx.to_dict_with_mvx()
    storage.save(key, params, data)

    audit_log("MVX_DELETE", key_name=entry.label, status="OK")
    console.print(f"[green]\u2713 Deleted: {entry.label}[/green]")
