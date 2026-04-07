"""PyInstaller hook for cryptography — bundles OpenSSL bindings."""
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

binaries = collect_dynamic_libs('cryptography')
hiddenimports = (
    collect_submodules('cryptography.hazmat.primitives')
    + collect_submodules('cryptography.hazmat.backends')
    + ['cryptography.hazmat.backends.openssl.backend']
)
