# PyInstaller hook for argon2-cffi
# Ensures the native _cffi extension and low-level bindings are collected.
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

datas, binaries, hiddenimports = collect_all('argon2')
binaries += collect_dynamic_libs('argon2')
hiddenimports += [
    'argon2._utils',
    'argon2.low_level',
    'argon2.profiles',
    '_cffi_backend',
]
