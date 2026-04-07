# PyInstaller hook for cryptography
# Ensures OpenSSL bindings and all hazmat backends are collected
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

hiddenimports = collect_submodules("cryptography")
binaries = collect_dynamic_libs("cryptography")
