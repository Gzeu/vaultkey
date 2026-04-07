# VaultKey — Build System

This folder contains everything needed to produce distributable binaries for all three platforms.

## Quick Start

### Windows
```powershell
# CLI + GUI (recommended)
.\build\scripts\build-windows.ps1 -Target all -Version 2.0.0

# CLI only (faster, smaller)
.\build\scripts\build-windows.ps1 -Target cli
```
Output: `dist/windows/vaultkey.exe`, `dist/windows/vaultkey-gui.exe`

### Linux
```bash
bash build/scripts/build-linux.sh all 2.0.0
```
Output:
- `dist/linux/vaultkey` — CLI binary (raw ELF, ~15-25MB)
- `dist/linux/vaultkey-tui` — TUI binary
- `dist/linux/VaultKey-2.0.0-x86_64.AppImage` — portable GUI

### macOS
```bash
bash build/scripts/build-macos.sh all 2.0.0
```
Output:
- `dist/macos/vaultkey` — CLI binary
- `dist/macos/VaultKey.app` — GUI .app bundle (unsigned by default)
- `dist/macos/VaultKey-2.0.0.dmg` — DMG (requires `brew install create-dmg`)

For signed builds, set env vars before running:
```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export APPLE_TEAM_ID="YOURTEAMID"
bash build/scripts/build-macos.sh gui 2.0.0
```

## GitHub Actions (Automated)

The build pipeline is fully automated via:
- **`.github/workflows/release.yml`** — triggered by pushing a version tag (`git tag v2.0.0 && git push --tags`)
- **`.github/workflows/ci.yml`** — runs on every push/PR (lint + typecheck + tests + security scan)

### Releasing v2.0.0
```bash
git tag -a v2.0.0 -m "VaultKey v2.0.0"
git push origin v2.0.0
```
This triggers the matrix build (6 jobs in parallel) and creates a GitHub Release with all binaries attached.

### Required GitHub Secrets

| Secret | Required | Description |
|---|---|---|
| `MACOS_CODESIGN_IDENTITY` | Optional | e.g. `Developer ID Application: Name (TEAMID)` |
| `MACOS_CERTIFICATE` | Optional | Base64-encoded `.p12` certificate |
| `MACOS_CERTIFICATE_PWD` | Optional | Password for the `.p12` cert |
| `APPLE_TEAM_ID` | Optional | For notarization |
| `GITHUB_TOKEN` | Auto | Provided by GitHub Actions automatically |

Without the macOS secrets, builds are **unsigned** — still functional, users need to right-click → Open on first launch.

## Structure

```
build/
├── pyinstaller/
│   ├── vaultkey-cli.spec       # CLI spec (console=True, minimal deps)
│   ├── vaultkey-tui.spec       # TUI spec (Textual + all CSS assets bundled)
│   ├── vaultkey-gui.spec       # GUI spec (CustomTkinter + .app bundle on macOS)
│   └── hooks/
│       ├── hook-argon2.py      # Ensures argon2-cffi CFFI binary is collected
│       ├── hook-cryptography.py # Ensures Rust extension is collected
│       └── hook-wallet.py      # Collects all wallet submodules
├── nuitka/
│   └── build-all.sh            # Alternative: compile to C (better perf, harder to RE)
├── macos/
│   └── entitlements.plist      # Hardened runtime entitlements for codesign
├── scripts/
│   ├── build-windows.ps1       # Windows PowerShell build
│   ├── build-linux.sh          # Linux build + AppImage packaging
│   └── build-macos.sh          # macOS build + codesign + DMG
└── README.md                   # This file
```

## Troubleshooting

### `ModuleNotFoundError: cryptography` at runtime
The `cryptography` package uses a Rust extension (`_rust.pyd`/`.so`). If it's not bundled:
```bash
pip show cryptography  # check version
# Make sure hook-cryptography.py is in build/pyinstaller/hooks/
```

### `argon2` binary missing
argon2-cffi uses CFFI. Ensure the hook is active and your venv path is correct in the spec file.

### CustomTkinter theme not found at runtime (GUI)
CTk loads theme JSON files dynamically. The `collect_data_files('customtkinter')` call in the spec handles this, but verify the `datas` tuple path matches your venv.

### macOS: `app is damaged and can't be opened`
This happens with unsigned builds. Fix:
```bash
xattr -cr VaultKey.app
```
Or quarantine remove:
```bash
xattr -d com.apple.quarantine VaultKey.app
```

### AppImage: `FUSE` error on Linux
```bash
sudo apt install libfuse2   # Ubuntu 22.04+
```

### Binary too large (>100MB)
- UPX compression is enabled by default (`upx=True` in spec)
- `optimize=2` strips docstrings
- Check `excludes` list in spec — add more unused packages
- Consider Nuitka build for GUI (better DCE)
