# -*- mode: python ; coding: utf-8 -*-
# VaultKey GUI — PyInstaller spec
# Produces: vaultkey-gui.exe (Windows), VaultKey.app (macOS), vaultkey-gui (Linux)
# Usage: pyinstaller build/pyinstaller/vaultkey-gui.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent
BLOCK_CIPHER = None

HIDDEN_IMPORTS = [
    # crypto stack
    "cryptography",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.kdf.hkdf",
    "cryptography.hazmat.primitives.hashes",
    "cryptography.hazmat.primitives.hmac",
    "cryptography.hazmat.backends",
    "cryptography.hazmat.backends.openssl",
    "cryptography.hazmat.backends.openssl.backend",
    "cryptography.hazmat.bindings._rust",
    "cryptography.hazmat.bindings._rust.openssl",
    "argon2",
    "argon2._utils",
    "argon2.low_level",
    "argon2._typing",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "typer",
    "rich",
    "pyperclip",
    "httpx",
    "httpx._transports.default",
    # tkinter / customtkinter
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "tkinter.font",
    "_tkinter",
    "customtkinter",
    "customtkinter.windows",
    "customtkinter.windows.widgets",
    "customtkinter.windows.widgets.core_widget_classes",
    "customtkinter.windows.widgets.font",
    "customtkinter.windows.widgets.image",
    "customtkinter.windows.widgets.scaling",
    "customtkinter.windows.widgets.theme",
    "customtkinter.windows.ctk_tk",
    "customtkinter.windows.ctk_toplevel",
    "customtkinter.windows.ctk_input_dialog",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    # wallet
    "wallet",
    "wallet.core",
    "wallet.core.crypto",
    "wallet.core.kdf",
    "wallet.core.session",
    "wallet.core.storage",
    "wallet.core.integrity",
    "wallet.core.health",
    "wallet.core.rotate",
    "wallet.core.wipe",
    "wallet.models",
    "wallet.utils",
    "wallet.ui.cli",
    "wallet.ui.gui",
]

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

DATAS = [
    (str(ROOT / "wallet"), "wallet"),
    *collect_data_files("customtkinter"),   # Themes JSON + image assets
]

HIDDEN_IMPORTS += collect_submodules("customtkinter")

a = Analysis(
    [str(ROOT / "wallet" / "ui" / "gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[str(ROOT / "build" / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "build" / "hooks" / "rthook_cryptography.py")],
    excludes=[
        "textual",
        "matplotlib",
        "numpy",
        "pandas",
        "test",
        "unittest",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="vaultkey-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,   # Don't strip GUI — breaks macOS code signature
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3.dll", "tcl*.dll", "tk*.dll"],
    runtime_tmpdir=None,
    console=False,         # Windowed — no terminal popup on Windows/macOS
    disable_windowed_traceback=False,
    argv_emulation=False,  # macOS: let CTk handle argv
    target_arch=None,
    codesign_identity=None,
    entitlements_file=str(ROOT / "build" / "assets" / "entitlements.plist")
        if sys.platform == "darwin" else None,
    icon=str(ROOT / "build" / "assets" / "vaultkey.ico") if sys.platform == "win32"
         else str(ROOT / "build" / "assets" / "vaultkey.icns") if sys.platform == "darwin"
         else None,
)

# ── macOS .app bundle ────────────────────────────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="VaultKey.app",
        icon=str(ROOT / "build" / "assets" / "vaultkey.icns"),
        bundle_identifier="io.vaultkey.app",
        info_plist={
            "CFBundleName": "VaultKey",
            "CFBundleDisplayName": "VaultKey",
            "CFBundleVersion": "2.0.0",
            "CFBundleShortVersionString": "2.0.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "MIT License",
            "LSUIElement": False,
            "NSAppleEventsUsageDescription": "VaultKey needs AppleEvents for clipboard access.",
            "NSCameraUsageDescription": "",
            "NSMicrophoneUsageDescription": "",
        },
    )
