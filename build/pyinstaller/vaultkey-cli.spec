# -*- mode: python ; coding: utf-8 -*-
# VaultKey CLI — PyInstaller spec
# Produces: vaultkey-cli (single-file, no console window on Windows)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'cli.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # argon2-cffi needs its _ffi_bindings
        (str(ROOT / '.venv' / 'Lib' / 'site-packages' / 'argon2') if sys.platform == 'win32'
         else str(ROOT / '.venv' / 'lib'), 'argon2'),
    ],
    hiddenimports=[
        'argon2._utils',
        'argon2._ffi',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'cryptography.hazmat.primitives.hmac',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.bindings._rust',
        'rich.logging',
        'rich.traceback',
        'typer',
        'click',
        'pyperclip',
        'pydantic',
        'pydantic_settings',
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
        'textual',
        'customtkinter',
        'tkinter',
        '_tkinter',
        'PIL',
        'matplotlib',
        'numpy',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
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
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # CLI needs console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'docs' / 'assets' / 'icon.ico') if (ROOT / 'docs' / 'assets' / 'icon.ico').exists() else None,
)
