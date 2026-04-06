"""
vault_profiles.py — Multi-vault profile manager for VaultKey.

Wave 9 addition.

Allows users to maintain multiple named wallet files (e.g., "work", "personal",
"staging") and switch between them with `wallet profile use <name>`.

Profile registry stored at ~/.vaultkey/profiles.json (plaintext — only paths,
no secrets). Each profile maps a name to a wallet file path.

Usage:
    wallet profile list
    wallet profile add work ~/.vaultkey/work.enc
    wallet profile use work
    wallet profile remove work
    wallet profile current
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_DEFAULT_REGISTRY = Path.home() / ".vaultkey" / "profiles.json"
_DEFAULT_PROFILE = "default"


class ProfileRegistry:
    """Manages named vault profiles persisted to a JSON registry file."""

    def __init__(self, registry_path: Path = _DEFAULT_REGISTRY) -> None:
        self.registry_path = registry_path
        self._data: dict = self._load()

    # ------------------------------------------------------------------ #
    # Internal I/O
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        if not self.registry_path.exists():
            return {"active": _DEFAULT_PROFILE, "profiles": {}}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"active": _DEFAULT_PROFILE, "profiles": {}}

    def _save(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def active(self) -> str:
        """Name of the currently active profile."""
        return self._data.get("active", _DEFAULT_PROFILE)

    @property
    def profiles(self) -> dict[str, str]:
        """Mapping of profile_name → wallet_path."""
        return self._data.get("profiles", {})

    def active_path(self) -> Optional[Path]:
        """Return the wallet Path for the active profile, or None if unset."""
        raw = self.profiles.get(self.active)
        return Path(raw) if raw else None

    def add(self, name: str, path: Path, overwrite: bool = False) -> None:
        """Register a new profile.

        Args:
            name:      Profile identifier (alphanumeric + hyphens/underscores).
            path:      Absolute path to the wallet .enc file.
            overwrite: If True, replace an existing profile of the same name.

        Raises:
            ValueError: If name already exists and overwrite is False.
            ValueError: If name contains invalid characters.
        """
        _validate_name(name)
        if name in self.profiles and not overwrite:
            raise ValueError(
                f"Profile '{name}' already exists. Use overwrite=True to replace."
            )
        self._data.setdefault("profiles", {})[name] = str(path.expanduser().resolve())
        self._save()

    def use(self, name: str) -> Path:
        """Switch the active profile.

        Returns:
            The wallet path for the newly active profile.

        Raises:
            KeyError: Profile not found.
        """
        if name not in self.profiles:
            raise KeyError(f"Profile '{name}' not found.")
        self._data["active"] = name
        self._save()
        return Path(self.profiles[name])

    def remove(self, name: str) -> None:
        """Unregister a profile.

        Raises:
            KeyError:  Profile not found.
            ValueError: Cannot remove the active profile.
        """
        if name not in self.profiles:
            raise KeyError(f"Profile '{name}' not found.")
        if name == self.active:
            raise ValueError(
                "Cannot remove the active profile. Switch to another profile first."
            )
        del self._data["profiles"][name]
        self._save()

    def list_all(self) -> list[dict]:
        """Return a sorted list of profile dicts with 'name', 'path', 'active'."""
        result = []
        for name, path in sorted(self.profiles.items()):
            result.append(
                {
                    "name": name,
                    "path": path,
                    "active": name == self.active,
                    "exists": Path(path).exists(),
                }
            )
        return result


def _validate_name(name: str) -> None:
    import re
    if not re.match(r"^[a-zA-Z0-9_-]{1,32}$", name):
        raise ValueError(
            "Profile name must be 1-32 characters: letters, digits, hyphens, underscores."
        )
