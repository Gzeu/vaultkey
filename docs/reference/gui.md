# GUI Reference

The desktop GUI is built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) and provides a dark-mode graphical interface.

## Launch

```bash
wallet gui
```

A login window appears first. Enter your master password to unlock the wallet.

## Login Window

```
┌──────────────────────────────────┐
│         🔐 VaultKey              │
│   Enter master password to unlock│
│                                  │
│  [••••••••••••••••••••••] [👁]   │
│                                  │
│         [ Unlock Wallet ]        │
└──────────────────────────────────┘
```

- Click **👁** to toggle password visibility
- Press **Enter** to unlock
- Failed attempts are counted and shown; after 5 failures a 60-second lockout is enforced

## Main Window

After successful login, the main window opens with four tabs:

```
🔐 VaultKey  [UNLOCKED — auto-locks in 15 min]        [🔒 Lock]
┌──────────────────────────────────────────────────────────────┐
│  🗝️ Keys  │  ⏰ Expiry  │  📊 Health  │  ⚙️ Settings          │
└──────────────────────────────────────────────────────────────┘
```

---

## 🗝️ Keys Tab

Scrollable list of all key cards with live search.

### Search Bar

Type in the search box to instantly filter by name, service, or tag. The filter is case-insensitive.

### Key Card

Each entry shows:
- **Name** (bold)
- **Service** · **Prefix** (first 8 chars) · **Status** (color-coded)
- Tags as `#tag` labels (gray)
- Expiry date if set

### Card Buttons

| Button | Action |
|---|---|
| **Copy** | Decrypt and copy value to clipboard (auto-clears after 30 s) |
| **Info** | Open metadata + health analysis panel |
| **Rename** | Open rename dialog |
| **Delete** | Delete after typed-name confirmation |

### Add Key Button

Click **+ Add Key** (top-right) to open the add dialog:

- Fields: Name, API Key Value, Service, Tags, Description, Expires
- API key value is masked by default
- Service is auto-detected from the key prefix if left blank

---

## ⏰ Expiry Tab

Color-coded view of keys with approaching or past expiry dates.

### Controls

| Control | Description |
|---|---|
| **Look-ahead (days)** | Number field — how many days ahead to check (default: 30) |
| **Refresh** | Re-run the expiry check with current settings |
| **Show all** | Toggle to show/hide `info`-level entries |

### Urgency Colors

| Color | Urgency | Condition |
|---|---|---|
| 🔴 Red | `expired` | Expiry date has passed |
| 🟠 Orange | `critical` | ≤ 7 days remaining |
| 🟡 Yellow | `warning` | ≤ 30 days remaining |
| ⚪ Gray | `info` | > 30 days remaining |

### Summary Bar

Bottom of the tab shows: `🔴 N expired  🟠 N critical  🟡 N warning`

---

## 📊 Health Tab

Wallet-wide health analysis with per-entry breakdown.

### Summary Header

```
Overall Grade: B   Score: 82/100
✅ 5 Healthy   ⚠️ 1 Warning   🔴 1 Critical
```

### Entry List

Entries are sorted by score (worst first). Each row shows:
- Entry name
- Grade letter (color-coded A=green → F=red)
- Score out of 100
- Issues inline (e.g. `No expiry | Not rotated in 90d`)

Grades:

| Grade | Score range | Color |
|---|---|---|
| A | 90–100 | Green |
| B | 75–89 | Light green |
| C | 60–74 | Yellow |
| D | 40–59 | Orange |
| F | 0–39 | Red |

---

## ⚙️ Settings Tab

### Change Master Password

Enter current password, new password, and confirmation. Requirements:
- Minimum 8 characters
- New and confirm must match

On success, all entry subkeys are re-derived under the new master key and re-encrypted atomically.

### Export Encrypted Backup

Click **Export…** to save a portable `.enc` backup file. You will be prompted for a separate export password (the backup uses its own Argon2id parameters).

### Bulk Import

Import from `.env`, `.json`, or `.csv` files:

1. Choose conflict strategy: `skip` / `overwrite` / `rename`
2. Toggle **Dry run** to preview without saving
3. Click **Choose file…**
4. Result summary: Added / Skipped / Overwritten / Renamed / Errors

See [Bulk Import guide](../guide/bulk-import.md) for file format details.

### Audit Log

Shows the last 20 audit events in chronological order:

```
2026-04-06 12:34:01  ✓ GET                OpenAI Production
2026-04-06 12:30:11  ✓ ADD                Stripe Live Key
2026-04-06 11:00:00  ✓ CHANGE_PASSWORD
```

---

## Info Dialog

Opened via **Info** button on any key card. Shows read-only metadata:

| Field | Description |
|---|---|
| Service | Detected or manually set service |
| Prefix | First 8 characters of the key value |
| Description | Free-text note |
| Tags | Comma-separated list |
| Created | UTC timestamp |
| Updated | UTC timestamp of last change |
| Expires | Expiry date or `—` |
| Last access | UTC timestamp or `Never` |
| Access count | Number of times value was copied |
| Status | active / expiring / expired / revoked |
| Health | Grade + score |

Issues and recommendations from the health engine are shown below the metadata.
