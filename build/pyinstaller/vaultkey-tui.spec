# -*- mode: python ; coding: utf-8 -*-
# VaultKey TUI — PyInstaller spec
# Produces: vaultkey-tui (single-file, terminal UI via Textual)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

# Collect all Textual CSS/assets — required for Textual to render
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

textual_datas = collect_data_files('textual')
textual_hidden = collect_submodules('textual')

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'tui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        *textual_datas,
        # tui_import companion module
        (str(ROOT / 'wallet' / 'ui' / 'tui_import.py'), 'wallet/ui'),
    ],
    hiddenimports=[
        *textual_hidden,
        'textual.app',
        'textual.widgets',
        'textual.widgets._data_table',
        'textual.widgets._input',
        'textual.widgets._button',
        'textual.widgets._static',
        'textual.widgets._label',
        'textual.widgets._tabs',
        'textual.widgets._tab_pane',
        'textual.css.query',
        'textual.reactive',
        'textual.binding',
        'argon2._utils',
        'argon2._ffi',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'cryptography.hazmat.bindings._rust',
        'rich.logging',
        'pydantic',
        'pydantic_settings',
        'pyperclip',
        'httpx',
        'wallet.core.crypto',
        'wallet.core.kdf',
        'wallet.core.session',
        'wallet.core.storage',
        'wallet.core.integrity',
        'wallet.core.health',
        'wallet.core.rotate',
        'wallet.core.wipe',
        'wallet.models',
        'wallet.utils',
    ],
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
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'docs' / 'assets' / 'icon.ico') if (ROOT / 'docs' / 'assets' / 'icon.ico').exists() else None,
)
