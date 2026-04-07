# -*- mode: python ; coding: utf-8 -*-
# VaultKey CLI — PyInstaller spec
# Produces: vaultkey-cli (or vaultkey-cli.exe on Windows)
# Usage: pyinstaller build/pyinstaller/vaultkey-cli.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent
BLOCK_CIPHER = None

# ── Hidden imports required for cryptography + argon2-cffi ─────────────────────
HIDDEN_IMPORTS = [
    # cryptography / OpenSSL backend
    "cryptography",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.kdf.hkdf",
    "cryptography.hazmat.primitives.kdf.scrypt",
    "cryptography.hazmat.primitives.hashes",
    "cryptography.hazmat.primitives.hmac",
    "cryptography.hazmat.backends",
    "cryptography.hazmat.backends.openssl",
    "cryptography.hazmat.backends.openssl.backend",
    "cryptography.hazmat.bindings._rust",
    "cryptography.hazmat.bindings._rust.openssl",
    # argon2-cffi
    "argon2",
    "argon2._utils",
    "argon2.low_level",
    "argon2._typing",
    # pydantic v2
    "pydantic",
    "pydantic.v1",
    "pydantic_core",
    "pydantic_settings",
    # typer / rich / click
    "typer",
    "rich",
    "rich.console",
    "rich.table",
    "rich.panel",
    "rich.prompt",
    "rich.progress",
    "rich.syntax",
    "rich.traceback",
    "click",
    "click_completion",
    # pyperclip
    "pyperclip",
    # httpx (webhooks)
    "httpx",
    "httpx._transports.default",
    # stdlib used by wallet
    "json",
    "os",
    "sys",
    "pathlib",
    "logging",
    "datetime",
    "uuid",
    "base64",
    "hmac",
    "hashlib",
    "secrets",
    "struct",
    "ctypes",
    "threading",
    "tempfile",
    "shutil",
    "platform",
    # wallet internal
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
]

# ── Collect data files (Textual CSS, etc. — not needed for CLI but safe to add) ──
DATAS = [
    (str(ROOT / "wallet"), "wallet"),
]

a = Analysis(
    [str(ROOT / "wallet" / "ui" / "cli.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[str(ROOT / "build" / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "build" / "hooks" / "rthook_cryptography.py")],
    excludes=[
        "textual",
        "customtkinter",
        "tkinter",
        "_tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "test",
        "unittest",
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="vaultkey-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python3.dll"],
    runtime_tmpdir=None,
    console=True,          # CLI must be console app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "build" / "assets" / "vaultkey.ico") if sys.platform == "win32"
         else str(ROOT / "build" / "assets" / "vaultkey.icns") if sys.platform == "darwin"
         else None,
)
