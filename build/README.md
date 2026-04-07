# VaultKey — Build System

This directory contains everything needed to produce distributable binaries for
Windows, Linux, and macOS.

## Directory Structure

```
build/
├── pyinstaller/          # PyInstaller .spec files (primary build method)
│   ├── vaultkey-cli.spec     # CLI-only binary (~15–25 MB)
│   ├── vaultkey-tui.spec     # TUI binary (Textual included, ~30–45 MB)
│   └── vaultkey-gui.spec     # GUI binary (CustomTkinter, ~40–60 MB)
├── hooks/                # Custom PyInstaller collection hooks
│   ├── hook-cryptography.py  # OpenSSL bindings collector
│   ├── hook-argon2.py        # argon2-cffi Rust extension collector
│   ├── hook-pydantic.py      # pydantic-core Rust extension collector
│   └── rthook_cryptography.py  # Runtime hook: sets DYLD/LD paths
├── nuitka/
│   └── build-nuitka.sh       # Nuitka alternative (smaller, faster output)
├── scripts/
│   ├── build-linux.sh        # Linux → ELF binary + AppImage
│   ├── build-macos.sh        # macOS → .app bundle + DMG
│   └── build-windows.ps1     # Windows → .exe files
├── assets/
│   ├── vaultkey.ico          # Windows icon (place here manually)
│   ├── vaultkey.icns         # macOS icon (place here manually)
│   ├── vaultkey.png          # Linux icon (place here manually)
│   ├── entitlements.plist    # macOS hardened runtime entitlements
│   └── README.md             # Icon generation instructions
└── README.md             # This file
```

## Quick Start

### Prerequisites

```bash
pip install pyinstaller
```

Optionally install UPX for binary compression (~30% smaller):
- **Linux**: `sudo apt install upx` or `sudo dnf install upx`
- **macOS**: `brew install upx`
- **Windows**: Download from https://github.com/upx/upx/releases

### Build Locally

**Linux:**
```bash
chmod +x build/scripts/build-linux.sh
./build/scripts/build-linux.sh
```

**macOS:**
```bash
chmod +x build/scripts/build-macos.sh
./build/scripts/build-macos.sh
# With code signing:
export MACOS_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
./build/scripts/build-macos.sh
```

**Windows (PowerShell):**
```powershell
.\build\scripts\build-windows.ps1
# CLI only:
.\build\scripts\build-windows.ps1 -CliOnly
```

### Using Nuitka (Optional)

Nuitka compiles Python to C for smaller, faster binaries:

```bash
pip install nuitka ordered-set zstandard
# Linux: also install patchelf
sudo apt install patchelf

./build/nuitka/build-nuitka.sh all
```

## Binary Sizes (Expected)

| Binary | Platform | Approx. Size |
|--------|----------|--------------|
| `vaultkey-cli` | All | 15–25 MB |
| `vaultkey-tui` | All | 30–45 MB |
| `vaultkey-gui.exe` / `VaultKey.app` | Windows/macOS | 40–65 MB |
| `vaultkey-linux.AppImage` | Linux | 45–70 MB |

> Sizes with UPX compression are ~30% smaller.

## GitHub Actions

Binaries are built automatically by the **Binaries** workflow:

- **Trigger**: On push to `v*` tags (e.g. `v2.0.0`) OR manually via workflow_dispatch
- **Matrix**: `windows-latest × linux-latest × macos-latest` × `cli + gui`
- **Artifacts**: Attached to the GitHub Release automatically

See [`.github/workflows/binaries.yml`](../.github/workflows/binaries.yml)

## macOS Code Signing

To sign for distribution outside the App Store:

1. Obtain a **Developer ID Application** certificate from Apple Developer Portal
2. Export as `.p12` and base64-encode it:
   ```bash
   base64 -i certificate.p12 | pbcopy
   ```
3. Add these **GitHub repository secrets**:
   - `MACOS_CERTIFICATE` — base64-encoded .p12
   - `MACOS_CERTIFICATE_PWD` — .p12 password
   - `MACOS_SIGN_IDENTITY` — e.g. `Developer ID Application: Your Name (TEAMID)`
   - `MACOS_KEYCHAIN_PWD` — temporary keychain password (any random string)

The `binaries.yml` workflow automatically imports the certificate and signs the build if these secrets are present.

## Known Issues

### cryptography / OpenSSL
`cryptography` uses a Rust extension that bundles OpenSSL. PyInstaller
sometimes misses the `_rust` submodule — the `hook-cryptography.py` and
`rthook_cryptography.py` files fix this.

### Textual CSS Files
Textual loads `.tcss` CSS files at runtime. The `collect_data_files("textual")`
call in `vaultkey-tui.spec` ensures they are bundled. If TUI fails with
`FileNotFoundError` on `.tcss`, verify this.

### CustomTkinter Themes
CustomTkinter loads JSON theme files from its package directory. The
`collect_data_files("customtkinter")` call handles this. If the GUI starts
with wrong theming or crashes, check that `customtkinter/` data was collected.

### Windows Antivirus
PyInstaller `.exe` files frequently trigger false positives on Windows Defender.
This is a known issue with all PyInstaller builds. Adding the binary to the
Windows Defender exclusions list resolves it. Signing with an EV code-signing
certificate eliminates this entirely.
