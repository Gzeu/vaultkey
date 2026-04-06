# Installation

## Requirements

- Python 3.11 or newer
- pip 23+
- Platform: Linux, macOS, Windows

## Install from PyPI

```bash
pip install vaultkey
```

## Install from Source

```bash
git clone https://github.com/Gzeu/vaultkey.git
cd vaultkey
pip install -e ".[dev]"
```

## Clipboard Backends

VaultKey uses `pyperclip` for clipboard access. The required backend depends on your platform:

| Platform | Backend | Notes |
|---|---|---|
| macOS | `pbcopy` / `pbpaste` | Built-in, no setup needed |
| Linux (X11) | `xclip` or `xsel` | `sudo apt install xclip` |
| Linux (Wayland) | `wl-clipboard` | `sudo apt install wl-clipboard` |
| Windows | `clip` / `powershell` | Built-in, no setup needed |

## Data Directory

VaultKey stores all data under the XDG Base Directory (or platform equivalent):

| Platform | Default path |
|---|---|
| Linux / macOS | `~/.local/share/vaultkey/` |
| Windows | `%APPDATA%\vaultkey\` |

Override with `VAULTKEY_WALLET_PATH` environment variable.

## Verify Installation

```bash
wallet --version
wallet status
```
