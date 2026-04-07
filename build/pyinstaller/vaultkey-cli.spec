# -*- mode: python ; coding: utf-8 -*-
# VaultKey CLI — PyInstaller spec
# Produces a single-file executable for the CLI interface.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'cli.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'wallet'), 'wallet'),
    ],
    hiddenimports=[
        # argon2-cffi native bindings
        'argon2._utils',
        'argon2.low_level',
        # cryptography hazmat backends
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.bindings._rust',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'cryptography.hazmat.primitives.kdf.scrypt',
        # pydantic
        'pydantic.deprecated.class_validators',
        'pydantic.deprecated.config',
        'pydantic.deprecated.tools',
        # typer / click internals
        'typer',
        'click',
        'rich.console',
        'rich.traceback',
        'rich.table',
        'rich.panel',
        'rich.progress',
        'rich.prompt',
        # pyperclip backends
        'pyperclip',
        # httpx
        'httpx',
        'anyio',
        'sniffio',
    ],
    hookspath=[str(ROOT / 'build' / 'pyinstaller' / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude GUI/TUI deps from CLI binary
        'customtkinter',
        'textual',
        'tkinter',
        '_tkinter',
        'PIL',
        'Pillow',
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='vaultkey',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python*.dll'],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'build' / 'assets' / 'icon.ico') if sys.platform == 'win32' else None,
    version=str(ROOT / 'build' / 'assets' / 'version.txt') if sys.platform == 'win32' else None,
)
