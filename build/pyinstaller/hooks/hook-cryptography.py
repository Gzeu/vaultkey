# PyInstaller hook for cryptography (pyca/cryptography)
# The Rust-backed _rust extension must be explicitly collected.

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files, collect_submodules

datas = collect_data_files('cryptography')
binaries = collect_dynamic_libs('cryptography')
hiddenimports = collect_submodules('cryptography.hazmat') + [
    'cryptography.hazmat.bindings._rust',
    'cryptography.hazmat.primitives.ciphers.aead',
    'cryptography.hazmat.primitives.kdf.hkdf',
    'cryptography.hazmat.primitives.kdf.pbkdf2',
    'cryptography.hazmat.primitives.hmac',
    'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.backends.openssl',
    'cryptography.hazmat.backends.openssl.backend',
]
