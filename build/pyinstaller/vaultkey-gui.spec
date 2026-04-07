# -*- mode: python ; coding: utf-8 -*-
# VaultKey GUI — PyInstaller spec
# Produces: vaultkey-gui(.exe / .app)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Gather CustomTkinter themes and images
ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'gui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        *ctk_datas,
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
        'customtkinter',
        'tkinter',
        '_tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'pyperclip',
    ] + collect_submodules('customtkinter'),
    hookspath=['build/pyinstaller/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'textual',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    # macOS: produce a .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='VaultKey',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=str(ROOT / 'build' / 'macos' / 'entitlements.plist'),
        icon=str(ROOT / 'assets' / 'icon.icns') if (ROOT / 'assets' / 'icon.icns').exists() else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='VaultKey',
    )
    app = BUNDLE(
        coll,
        name='VaultKey.app',
        icon=str(ROOT / 'assets' / 'icon.icns') if (ROOT / 'assets' / 'icon.icns').exists() else None,
        bundle_identifier='io.vaultkey.app',
        version='2.0.0',
        info_plist={
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
            'CFBundleShortVersionString': '2.0.0',
            'CFBundleVersion': '2.0.0',
            'LSMinimumSystemVersion': '12.0',
            'NSHumanReadableCopyright': 'Copyright © 2024-2026 VaultKey Contributors',
        },
    )
else:
    # Windows / Linux: single-file windowed exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='vaultkey-gui',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=['vcruntime140.dll'],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / 'assets' / 'icon.ico') if (ROOT / 'assets' / 'icon.ico').exists() else None,
    )
