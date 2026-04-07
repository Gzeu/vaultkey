# -*- mode: python ; coding: utf-8 -*-
# VaultKey TUI — PyInstaller spec
# Produces: vaultkey-tui(.exe)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

# Collect all Textual CSS/assets
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

textual_datas = collect_data_files('textual')

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'tui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        *textual_datas,
    ],
    hiddenimports=[
        'argon2',
        'argon2._utils',
        'argon2.low_level',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'cryptography.hazmat.primitives.hmac',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.backends.openssl.backend',
        'pydantic',
        'pydantic_settings',
        'typer',
        'rich',
        'textual',
        'textual.app',
        'textual.widgets',
        'textual.containers',
        'textual.screen',
        'textual.css',
        'textual.css.query',
        'pyperclip',
    ] + collect_submodules('textual'),
    hookspath=['build/pyinstaller/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'customtkinter',
        'tkinter',
        '_tkinter',
        'PIL',
        'matplotlib',
        'numpy',
        'pandas',
    ],
    noarchive=False,
    optimize=1,
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
