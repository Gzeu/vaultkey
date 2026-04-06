# TUI Reference

The Terminal UI is built with [Textual](https://textual.textualize.io/) and provides a full-keyboard interface for VaultKey without leaving the terminal.

## Launch

```bash
wallet tui
```

You will be prompted for your master password before the TUI opens.

## Layout

```
┌─────────────────────────────────────────────────────┐
│  🔐 VaultKey  [UNLOCKED]  auto-locks in 14:32        │  ← Header
├───────────┬─────────────────────────────────────────┤
│  Keys  7  │  ┌─────────────────────────────────────┐│
│  ──────   │  │  OpenAI Production          A  95  ││  ← Key card
│  > OpenAI │  │  openai  •  sk-abc1...  •  active   ││
│  Anthropic│  │  Tags: #ai #prod         2027-01-01 ││
│  GitHub   │  └─────────────────────────────────────┘│
│  Stripe   │  ┌─────────────────────────────────────┐│
│  AWS      │  │  Anthropic Claude          B  84  ││
│  ...      │  └─────────────────────────────────────┘│
├───────────┴─────────────────────────────────────────┤
│  [c]opy  [i]nfo  [r]ename  [d]elete  [/]search  [?]│  ← Footer
└─────────────────────────────────────────────────────┘
```

## Keyboard Shortcuts

### Navigation

| Key | Action |
|---|---|
| `↑` / `↓` | Move selection up / down |
| `j` / `k` | Move selection down / up (Vim-style) |
| `Home` / `End` | Jump to first / last key |
| `PgUp` / `PgDn` | Scroll list page up / down |
| `Tab` | Switch focus between sidebar and main panel |

### Key Actions

| Key | Action |
|---|---|
| `c` | Copy selected key to clipboard |
| `i` | Show full info panel for selected key |
| `a` | Add new key (opens input form) |
| `r` | Rename selected key |
| `d` | Delete selected key (confirmation required) |
| `R` | Rotate selected key (re-encrypt with new nonce) |
| `v` | Revoke selected key |

### Search & Filter

| Key | Action |
|---|---|
| `/` | Open search bar |
| `Escape` | Clear search / close panel |
| `f` | Open filter panel (by service, tag, status) |

### Views

| Key | Action |
|---|---|
| `1` | Keys view |
| `2` | Expiry view |
| `3` | Health view |
| `4` | Audit log view |

### Session

| Key | Action |
|---|---|
| `l` | Lock session immediately |
| `q` | Quit TUI (session remains active) |
| `Q` | Quit and lock session |
| `?` | Show help overlay |

## Expiry View

Press `2` to switch to expiry view. Keys are sorted by urgency:

```
🔴 EXPIRED     GitHub Actions Token       expired 5 days ago
🟠 CRITICAL    Stripe Live Key            3 days remaining
🟡 WARNING     AWS Root Key               18 days remaining
⚪ INFO         OpenAI Production          182 days remaining
```

Press `Enter` on any entry to view details. Press `r` to set or update expiry date.

## Health View

Press `3` to switch to health view. Keys are sorted by score (lowest first).

```
 Overall: B  (82/100)   ✅ 5 Healthy   ⚠️ 1 Warning   🔴 1 Critical

 F  32   AWS Root Key         No expiry, never rotated, no description
 C  61   GitHub Actions       Expiring in 24 days
 B  84   Anthropic Claude     No expiry set
 A  95   OpenAI Production    All checks passed
```

## Add Key Form

Press `a` to open the inline add-key form:

```
 Add New API Key
 ───────────────────────────────
 Name *          │                     |
 Service         │                     |
 API Key Value * │ (hidden input)       |
 Tags            │ comma-separated      |
 Description     │                     |
 Expires         │ YYYY-MM-DD           |
 ───────────────────────────────
 [Enter] Save    [Esc] Cancel
```

## Mouse Support

Textual supports mouse clicks for list navigation and button activation. All keyboard shortcuts remain active when using mouse.
