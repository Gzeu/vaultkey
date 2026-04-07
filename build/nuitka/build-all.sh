#!/usr/bin/env bash
# VaultKey — Nuitka build script (alternative to PyInstaller)
# Use Nuitka for:
#   - Better startup performance (compiled to C)
#   - Harder reverse engineering
#   - More reliable with complex C extension trees
# Usage: bash build/nuitka/build-all.sh [cli|gui] [version]
# Requires: pip install nuitka ordered-set zstandard

set -euo pipefail

TARGET="${1:-cli}"
VERSION="${2:-2.0.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist/nuitka"

echo "==> VaultKey Nuitka Build v$VERSION — $TARGET"
mkdir -p "$DIST"

python3 -m nuitka --version &>/dev/null || pip3 install nuitka ordered-set zstandard

COMMON_FLAGS=(
    --standalone
    --onefile
    --assume-yes-for-downloads
    --python-flag=no_site
    --python-flag=no_warnings
    --python-flag=isolated
    --include-package=wallet
    --include-package=cryptography
    --include-package=argon2
    --include-package=pydantic
    --include-package=pydantic_settings
    --include-package=httpx
    --include-package=rich
    --output-dir="$DIST"
    --remove-output
)

if [ "$TARGET" = 'cli' ] || [ "$TARGET" = 'all' ]; then
    echo "==> Compiling CLI..."
    python3 -m nuitka \
        "${COMMON_FLAGS[@]}" \
        --include-package=typer \
        --include-package=click \
        --include-package=pyperclip \
        --output-filename="vaultkey" \
        "$ROOT/wallet/ui/cli.py"
    echo "    OK -> dist/nuitka/vaultkey"
fi

if [ "$TARGET" = 'gui' ] || [ "$TARGET" = 'all' ]; then
    echo "==> Compiling GUI..."
    python3 -m nuitka \
        "${COMMON_FLAGS[@]}" \
        --include-package=customtkinter \
        --include-package=tkinter \
        --include-data-dir="$(python3 -c 'import customtkinter; import os; print(os.path.dirname(customtkinter.__file__))')"=customtkinter \
        --windows-disable-console \
        --output-filename="vaultkey-gui" \
        "$ROOT/wallet/ui/gui.py"
    echo "    OK -> dist/nuitka/vaultkey-gui"
fi

echo ""
echo "==> Nuitka build done."
ls -lh "$DIST"
