# PyInstaller hook for cryptography
# The cryptography package ships a Rust extension (_rust) that PyInstaller
# misses without explicit collection.
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

datas, binaries, hiddenimports = collect_all('cryptography')
binaries += collect_dynamic_libs('cryptography')
hiddenimports += [
    'cryptography.hazmat.backends.openssl',
    'cryptography.hazmat.backends.openssl.aead',
    'cryptography.hazmat.bindings._rust',
    'cryptography.hazmat.bindings._rust.openssl',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.ciphers.aead',
    'cryptography.hazmat.primitives.kdf.hkdf',
    'cryptography.hazmat.primitives.kdf.scrypt',
    'cryptography.hazmat.primitives.hmac',
    'cryptography.hazmat.primitives.hashes',
    'cryptography.hazmat.primitives.padding',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.hazmat.primitives.asymmetric',
    'cryptography.x509',
]
