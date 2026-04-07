# PyInstaller hook for argon2-cffi
# Ensures the CFFI binary extension and its data files are collected.

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

datas = collect_data_files('argon2')
binaries = collect_dynamic_libs('argon2')
hiddenimports = ['argon2._utils', 'argon2._ffi', 'cffi', '_cffi_backend']
