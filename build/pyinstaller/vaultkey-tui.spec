# -*- mode: python ; coding: utf-8 -*-
# VaultKey TUI — PyInstaller spec
# Produces: vaultkey-tui (or vaultkey-tui.exe on Windows)
# Usage: pyinstaller build/pyinstaller/vaultkey-tui.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent
BLOCK_CIPHER = None

HIDDEN_IMPORTS = [
    # All CLI imports
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
    "rich.console",
    "pyperclip",
    "httpx",
    "httpx._transports.default",
    # Textual — full collect needed
    "textual",
    "textual.app",
    "textual.screen",
    "textual.widget",
    "textual.widgets",
    "textual.widgets._button",
    "textual.widgets._input",
    "textual.widgets._label",
    "textual.widgets._list_view",
    "textual.widgets._list_item",
    "textual.widgets._data_table",
    "textual.widgets._tabs",
    "textual.widgets._tab_pane",
    "textual.widgets._static",
    "textual.widgets._header",
    "textual.widgets._footer",
    "textual.widgets._progress_bar",
    "textual.widgets._markdown",
    "textual.widgets._select",
    "textual.widgets._switch",
    "textual.widgets._tooltip",
    "textual.containers",
    "textual.css",
    "textual.css.query",
    "textual.binding",
    "textual.events",
    "textual.keys",
    "textual.reactive",
    "textual.message",
    "textual.worker",
    "textual.color",
    "textual.geometry",
    "textual.strip",
    "textual.driver",
    "textual._xterm_parser",
    "textual._compose",
    "textual._context",
    "textual.expand_tabs",
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
    "wallet.ui.tui",
    "wallet.ui.tui_import",
]

# Textual ships CSS files that MUST be collected
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

DATAS = [
    (str(ROOT / "wallet"), "wallet"),
    *collect_data_files("textual"),  # Textual CSS/TCSS files
]

HIDDEN_IMPORTS += collect_submodules("textual")

a = Analysis(
    [str(ROOT / "wallet" / "ui" / "tui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[str(ROOT / "build" / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "build" / "hooks" / "rthook_cryptography.py")],
    excludes=[
        "customtkinter",
        "tkinter",
        "_tkinter",
        "matplotlib",
        "numpy",
        "pandas",
    ],
    noarchive=False,
    optimize=1,  # Less aggressive — Textual uses dynamic imports
)

pyz = PYZ(a.pure, a.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="vaultkey-tui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=["vcruntime140.dll"],
    runtime_tmpdir=None,
    console=True,          # TUI must run in terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "build" / "assets" / "vaultkey.ico") if sys.platform == "win32"
         else str(ROOT / "build" / "assets" / "vaultkey.icns") if sys.platform == "darwin"
         else None,
)
