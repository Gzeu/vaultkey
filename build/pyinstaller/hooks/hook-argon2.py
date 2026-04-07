"""PyInstaller hook for argon2-cffi — ensures native .so/.pyd is bundled."""
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

binaries = collect_dynamic_libs('argon2')
datas = collect_data_files('argon2')
hiddenimports = ['argon2', 'argon2._utils', 'argon2.low_level', 'argon2.exceptions']
