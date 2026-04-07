# PyInstaller hook for argon2-cffi
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

hiddenimports = collect_submodules("argon2") + ["argon2._utils", "argon2.low_level"]
binaries = collect_dynamic_libs("argon2")
