# -*- mode: python ; coding: utf-8 -*-
# VaultKey GUI — PyInstaller spec
# Produces: vaultkey-gui (single-file, CustomTkinter windowed app)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'gui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        *ctk_datas,
        # CustomTkinter needs its themes folder at runtime
        (str(ROOT / '.venv' / 'Lib' / 'site-packages' / 'customtkinter') if sys.platform == 'win32'
         else str(ROOT / '.venv' / 'lib'), 'customtkinter'),
    ],
    hiddenimports=[
        'customtkinter',
        'tkinter',
        'tkinter.ttk',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL._tkinter_finder',
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
        'textual',
        'matplotlib',
        'numpy',
        'scipy',
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
    name='vaultkey-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # windowed — no console popup on Windows/macOS
    disable_windowed_traceback=False,
    argv_emulation=False,  # macOS argv emulation off (avoid LSOpenApplication issues)
    target_arch=None,
    codesign_identity=None,
    entitlements_file='build/macos/entitlements.plist' if sys.platform == 'darwin' else None,
    icon=str(ROOT / 'docs' / 'assets' / 'icon.ico') if sys.platform == 'win32' and (ROOT / 'docs' / 'assets' / 'icon.ico').exists()
         else (str(ROOT / 'docs' / 'assets' / 'icon.icns') if sys.platform == 'darwin' and (ROOT / 'docs' / 'assets' / 'icon.icns').exists()
               else None),
)

# macOS .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='VaultKey.app',
        icon=str(ROOT / 'docs' / 'assets' / 'icon.icns') if (ROOT / 'docs' / 'assets' / 'icon.icns').exists() else None,
        bundle_identifier='io.vaultkey.app',
        info_plist={
            'CFBundleName': 'VaultKey',
            'CFBundleDisplayName': 'VaultKey',
            'CFBundleVersion': '2.0.0',
            'CFBundleShortVersionString': '2.0.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,  # allows dark mode
            'LSMinimumSystemVersion': '12.0',
            'LSUIElement': False,
            'NSAppleEventsUsageDescription': 'VaultKey needs automation access to fill credentials.',
        },
    )
