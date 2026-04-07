# VaultKey Build System

This directory contains all build configuration for producing distributable binaries of VaultKey.

## Structure

```
build/
├── pyinstaller/          # PyInstaller specs (primary build method)
│   ├── vaultkey-cli.spec     # CLI-only binary (~15-25 MB)
│   ├── vaultkey-tui.spec     # TUI binary with Textual bundled (~40-60 MB)
│   ├── vaultkey-gui.spec     # GUI binary with CustomTkinter (~60-90 MB)
│   └── hooks/                # Custom PyInstaller hooks for argon2 + cryptography
│       ├── hook-argon2.py
│       └── hook-cryptography.py
├── nuitka/               # Nuitka fallback (faster startup, smaller size)
│   └── build-all.sh
├── linux/                # Linux-specific
│   ├── build-appimage.sh     # AppImage packaging script
│   └── vaultkey.desktop      # .desktop entry for AppImage
├── macos/                # macOS-specific
│   ├── build-macos.sh        # .app + codesign + DMG
│   └── entitlements.plist    # Hardened Runtime entitlements
└── windows/              # Windows-specific
    └── build-windows.ps1     # PowerShell build script
```

## Quick Start

### Prerequisites

```bash
pip install pyinstaller>=6.5
# Optional but recommended:
pip install Pillow  # for CTk icon support
# UPX for compression (reduces .exe size ~40%):
#   Windows: winget install upx
#   Linux:   sudo apt install upx-ucl
#   macOS:   brew install upx
```

### Build Locally

**Windows (PowerShell):**
```powershell
.\build\windows\build-windows.ps1
```

**Linux:**
```bash
# CLI only (fast, ~20MB)
pyinstaller --clean --noconfirm build/pyinstaller/vaultkey-cli.spec

# GUI + AppImage
bash build/linux/build-appimage.sh
```

**macOS:**
```bash
# Unsigned (for local use)
bash build/macos/build-macos.sh

# Signed (requires Apple Developer ID)
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
bash build/macos/build-macos.sh --sign --dmg
```

**Nuitka (all platforms, faster startup):**
```bash
bash build/nuitka/build-all.sh cli    # CLI only
bash build/nuitka/build-all.sh all    # All targets
```

## GitHub Actions

The `build-binaries.yml` workflow:
- **On tag push** `v2.x.x`: builds Windows + Linux + macOS, attaches binaries to GitHub Release
- **Manual dispatch**: select specific OS and CLI/GUI target
- **On branch push** `feat/v2-build-pipeline`: validates the build without uploading

### Setting Up Secrets

For macOS code signing (optional, for App Store / Gatekeeper trust):
```
GitHub repo → Settings → Secrets and variables → Actions

Secret name: MACOS_CODESIGN_IDENTITY
Value:        Developer ID Application: Your Name (ABCDE12345)
```

For the full notarization pipeline (post v2.0):
```
APPLE_ID              → your@email.com
APPLE_ID_PASSWORD     → app-specific-password from appleid.apple.com
APPLE_TEAM_ID         → ABCDE12345
```

## Binary Sizes (Estimated)

| Binary | Windows | Linux | macOS |
|--------|---------|-------|-------|
| `vaultkey` (CLI) | ~25 MB | ~22 MB | ~24 MB |
| `vaultkey-gui` (GUI) | ~80 MB | ~75 MB | ~85 MB |
| `VaultKey.AppImage` | — | ~80 MB | — |
| `VaultKey.app.zip` | — | — | ~90 MB |

> Sizes with UPX enabled. Without UPX: +40% approximately.

## Troubleshooting

### `argon2` not found at runtime
Ensure the `hook-argon2.py` hook is found. PyInstaller must be run from the **project root**:
```bash
cd /path/to/vaultkey
pyinstaller --clean --noconfirm build/pyinstaller/vaultkey-cli.spec
```

### `customtkinter` missing themes
The `collect_data_files('customtkinter')` call in the spec handles this. If themes are missing, run:
```bash
python -c "import customtkinter; print(customtkinter.__file__)"
# Verify the themes folder exists next to __init__.py
```

### macOS: "App is damaged and can't be opened"
```bash
xattr -cr dist/VaultKey.app
```

### Linux: AppImage won't run — FUSE error
```bash
# Either install FUSE:
sudo apt install fuse libfuse2
# Or extract and run directly:
./VaultKey-2.0.0-linux-x86_64.AppImage --appimage-extract
./squashfs-root/AppRun
```
