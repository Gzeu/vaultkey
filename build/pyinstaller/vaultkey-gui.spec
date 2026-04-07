# -*- mode: python ; coding: utf-8 -*-
# VaultKey GUI — PyInstaller spec
# Produces a windowed single-file executable using CustomTkinter.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent

# Locate customtkinter data directory (ships themes + fonts)
try:
    import customtkinter
    CTK_PATH = Path(customtkinter.__file__).parent
except ImportError:
    CTK_PATH = None

datas = [(str(ROOT / 'wallet'), 'wallet')]
if CTK_PATH:
    datas.append((str(CTK_PATH), 'customtkinter'))

a = Analysis(
    [str(ROOT / 'wallet' / 'ui' / 'gui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'argon2._utils',
        'argon2.low_level',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.bindings._rust',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'pydantic.deprecated.class_validators',
        'pydantic.deprecated.config',
        # CustomTkinter internals
        'customtkinter',
        'customtkinter.windows',
        'customtkinter.windows.widgets',
        'customtkinter.windows.widgets.theme',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL._imaging',
        # tkinter
        'tkinter',
        'tkinter.ttk',
        'tkinter.font',
        'tkinter.messagebox',
        'tkinter.filedialog',
        '_tkinter',
        # pystray (system tray — optional, graceful fallback)
        'pystray',
        # rest
        'pyperclip',
        'httpx',
        'anyio',
        'sniffio',
        'rich.console',
    ],
    hookspath=[str(ROOT / 'build' / 'pyinstaller' / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'textual',
    ],
    noarchive=False,
    optimize=2,
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
        strip=True,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,  # needed for macOS .app drag-and-drop
        target_arch=None,
        codesign_identity=None,
        entitlements_file=str(ROOT / 'build' / 'assets' / 'entitlements.plist'),
        icon=str(ROOT / 'build' / 'assets' / 'icon.icns'),
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=True,
        upx=False,
        upx_exclude=[],
        name='VaultKey',
    )
    app = BUNDLE(
        coll,
        name='VaultKey.app',
        icon=str(ROOT / 'build' / 'assets' / 'icon.icns'),
        bundle_identifier='io.vaultkey.app',
        info_plist={
            'CFBundleShortVersionString': '2.0.0',
            'CFBundleVersion': '2.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '12.0',
            'NSHumanReadableCopyright': 'MIT License',
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
        },
    )
else:
    # Windows / Linux: single-file exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='VaultKey',
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=True,
        upx_exclude=['vcruntime140.dll', 'python*.dll', '_tkinter*.dll'],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / 'build' / 'assets' / 'icon.ico') if sys.platform == 'win32' else None,
        version=str(ROOT / 'build' / 'assets' / 'version.txt') if sys.platform == 'win32' else None,
    )
