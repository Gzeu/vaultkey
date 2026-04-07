# -*- mode: python ; coding: utf-8 -*-
# VaultKey CLI — PyInstaller spec
# Produces a single-file executable: vaultkey-cli(.exe on Windows)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'cli.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Argon2-cffi native libs
        (str(ROOT / '.venv' / 'Lib' / 'site-packages' / 'argon2') if sys.platform == 'win32'
         else str(ROOT / '.venv' / 'lib'), 'argon2'),
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
        'rich.console',
        'rich.panel',
        'rich.table',
        'pyperclip',
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
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
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
    upx_exclude=['vcruntime140.dll', 'python3*.dll'],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets' / 'icon.ico') if (ROOT / 'assets' / 'icon.ico').exists() else None,
)
