# `wallet.core.health`

Per-entry and wallet-wide health scoring engine.

## Overview

The health engine scores each API key entry from 0–100 and assigns a letter grade (A–F) based on security hygiene factors. It operates entirely on metadata — no decryption is performed.

## Data Classes

### `EntryHealth`

```python
@dataclass
class EntryHealth:
    entry_id: str
    name: str
    score: int           # 0–100
    grade: str           # "A" | "B" | "C" | "D" | "F"
    issues: list[str]    # Human-readable problem descriptions
    recommendations: list[str]  # Actionable fix suggestions
```

---

### `WalletHealth`

```python
@dataclass
class WalletHealth:
    overall_score: int
    overall_grade: str
    healthy: int         # entries with grade A or B
    warning: int         # entries with grade C
    critical: int        # entries with grade D or F
    entries: list[EntryHealth]
```

---

## Functions

### `analyze_entry`

```python
def analyze_entry(entry: APIKeyEntry) -> EntryHealth:
    ...
```

Score a single `APIKeyEntry`.

**Scoring deductions:**

| Condition | Points deducted |
|---|---|
| No expiry date set | −20 |
| Key is expired | −40 |
| Expiring within 30 days | −15 |
| No description | −10 |
| Never accessed | −5 |
| Not rotated in 90 days | −15 |
| Service is `"unknown"` | −5 |

**Grade thresholds:**

| Grade | Score range |
|---|---|
| A | 90–100 |
| B | 75–89 |
| C | 60–74 |
| D | 40–59 |
| F | 0–39 |

**Example:**
```python
from wallet.core.health import analyze_entry

health = analyze_entry(entry)
print(f"{health.grade} ({health.score}/100)")
for issue in health.issues:
    print(f"  ⚠ {issue}")
```

---

### `analyze_wallet`

```python
def analyze_wallet(payload: WalletPayload) -> WalletHealth:
    ...
```

Run `analyze_entry` on every entry in the wallet and aggregate results.

**Returns:** A `WalletHealth` with overall grade, counts, and per-entry breakdown.

**Example:**
```python
from wallet.core.health import analyze_wallet

wh = analyze_wallet(payload)
print(f"Overall: {wh.overall_grade} ({wh.overall_score}/100)")
print(f"Healthy: {wh.healthy}  Warning: {wh.warning}  Critical: {wh.critical}")
```
