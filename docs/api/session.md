# `wallet.core.session`

In-memory session management with automatic lock and brute-force protection.

## Overview

The `SessionManager` holds the derived master key in memory between commands. It auto-locks after a configurable idle timeout, wiping the key from memory via `ctypes.memset`.

## Classes

### `SessionManager`

```python
class SessionManager:
    def unlock(self, key: bytes) -> None: ...
    def lock(self, reason: str = "manual") -> None: ...
    def require_unlocked(self) -> bytes: ...
    def record_failed_attempt(self) -> None: ...
    def reset_failed_attempts(self) -> None: ...
    @property
    def info(self) -> dict: ...
    @property
    def is_locked(self) -> bool: ...
```

---

### `SessionManager.unlock`

```python
def unlock(self, key: bytes) -> None:
    ...
```

Store the derived master key and start the idle timer.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `key` | `bytes` | 32-byte master key from `derive_key()` |

Cancels any existing timer before starting a new one.

---

### `SessionManager.lock`

```python
def lock(self, reason: str = "manual") -> None:
    ...
```

Zero the session key from memory and cancel the idle timer.

| Parameter | Type | Description |
|---|---|---|
| `reason` | `str` | Logged to audit log (`manual`, `timeout`, `gui_close`, etc.) |

---

### `SessionManager.require_unlocked`

```python
def require_unlocked(self) -> bytes:
    ...
```

Return the session key, or raise `WalletLockedException` if locked.

**Raises:** `WalletLockedException`

---

### `SessionManager.record_failed_attempt`

```python
def record_failed_attempt(self) -> None:
    ...
```

Increment the failed attempt counter. After `VAULTKEY_MAX_FAILED_ATTEMPTS` (default: 5) failures, sets a lockout until `now + VAULTKEY_LOCKOUT_SECONDS`.

---

### `SessionManager.info`

```python
@property
def info(self) -> dict:
    ...
```

Returns a snapshot of session state:

```python
{
    "locked": False,
    "timeout_minutes": 15,
    "failed_attempts": 0,
    "locked_until": None,   # or datetime if in lockout
}
```

---

## Exceptions

### `WalletLockedException`

```python
class WalletLockedException(Exception):
    """Raised when an operation requires an unlocked session."""
```

Raised by `require_unlocked()` when the session is locked.

---

## Example

```python
from wallet.core.session import SessionManager, WalletLockedException
from wallet.core.kdf import derive_key, KDFParams

session = SessionManager()
params = KDFParams.generate()
key = derive_key("password", params)

session.unlock(key)
print(session.is_locked)  # False

active_key = session.require_unlocked()  # returns key

session.lock(reason="done")
print(session.is_locked)  # True

try:
    session.require_unlocked()
except WalletLockedException:
    print("Please unlock first: wallet unlock")
```
