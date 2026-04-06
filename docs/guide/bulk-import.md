# Bulk Import

Import keys from existing secrets files without manual entry one-by-one.

## Supported Formats

### `.env` files

```bash
# Lines starting with # are ignored
OPENAI_API_KEY=sk-abc123...
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
```

- Service is auto-detected from the key name prefix (`OPENAI_` → `openai`)
- Lines without `=` are skipped
- Empty values are skipped

### `.json` files

```json
[
  {
    "name": "OpenAI Production",
    "value": "sk-abc123...",
    "service": "openai",
    "tags": "ai,production",
    "description": "Main production key",
    "expires": "2027-01-01"
  }
]
```

Only `name` and `value` are required. All other fields are optional.

### `.csv` files

```csv
name,value,service,tags,description,expires
OpenAI Production,sk-abc123...,openai,ai prod,,2027-01-01
```

Header row is required. Only `name` and `value` columns are mandatory.

## Conflict Strategies

| Strategy | Behavior |
|---|---|
| `skip` (default) | Leave existing key unchanged, count as skipped |
| `overwrite` | Replace existing key's value and metadata |
| `rename` | Import as `<name>_1`, `<name>_2`, etc. |

## CLI Usage

```bash
# Preview without writing
wallet bulk-import .env --dry-run

# Import with rename on conflict
wallet bulk-import keys.json --on-conflict rename

# Import CSV, overwrite duplicates
wallet bulk-import secrets.csv --on-conflict overwrite
```

## GUI Usage

In the GUI, go to **⚙️ Settings → Bulk Import** section:

1. Select conflict strategy (radio buttons)
2. Toggle **Dry run** to preview without saving
3. Click **Choose file…** and pick your `.env`, `.json`, or `.csv`
4. Result summary shows: Added / Skipped / Overwritten / Renamed / Errors
