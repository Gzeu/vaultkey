# -*- mode: python ; coding: utf-8 -*-
# VaultKey TUI — PyInstaller spec
# Produces a single-file executable for the Textual TUI interface.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'tui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'wallet'), 'wallet'),
        # Textual ships CSS files that must be bundled
        ('$(python -c "import textual; print(textual.__path__[0])")', 'textual'),
    ],
    hiddenimports=[
        'argon2._utils',
        'argon2.low_level',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.bindings._rust',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'pydantic.deprecated.class_validators',
        'pydantic.deprecated.config',
        # Textual internals
        'textual',
        'textual.app',
        'textual.widgets',
        'textual.widgets._button',
        'textual.widgets._input',
        'textual.widgets._label',
        'textual.widgets._list_view',
        'textual.widgets._data_table',
        'textual.widgets._tabs',
        'textual.widgets._static',
        'textual.widgets._footer',
        'textual.widgets._header',
        'textual.screen',
        'textual.containers',
        'textual.binding',
        'textual.reactive',
        'textual.css.query',
        'rich.console',
        'rich.segment',
        'pyperclip',
        'httpx',
        'anyio',
        'anyio._backends._asyncio',
        'sniffio',
    ],
    hookspath=[str(ROOT / 'build' / 'pyinstaller' / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'customtkinter',
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
    name='vaultkey-tui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=['vcruntime140.dll'],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
