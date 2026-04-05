# Installation

## Requirements

- Python **3.11** or newer
- pip 23+

## From PyPI (recommended)

```bash
pip install vaultkey
```

## From source

```bash
git clone https://github.com/Gzeu/vaultkey
cd vaultkey
pip install -e .
```

## Development install (includes test tools)

```bash
pip install -e ".[dev]"
```

## Verify installation

```bash
wallet --help
```

## Platform notes

| Platform | Clipboard backend |
|----------|------------------|
| Linux | `xclip` or `xsel` required (`apt install xclip`) |
| macOS | `pbcopy` / `pbpaste` (built-in) |
| Windows | `win32clipboard` (included with `pyperclip`) |

## Wallet location

| Platform | Default path |
|----------|--------------|
| Linux / macOS | `~/.local/share/vaultkey/wallet.enc` |
| Windows | `%APPDATA%\vaultkey\wallet.enc` |

Override with `VAULTKEY_WALLET_PATH` environment variable.
