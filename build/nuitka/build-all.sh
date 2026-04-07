#!/usr/bin/env bash
# VaultKey Nuitka build — performance-optimized alternative to PyInstaller
# Use when PyInstaller binary is too large or startup is too slow.
# Nuitka compiles Python to C, resulting in faster startup + smaller footprint.
#
# Usage: bash build/nuitka/build-all.sh [cli|gui|tui|all]
# Requires: pip install nuitka ordered-set zstandard

set -euo pipefail

TARGET=${1:-all}
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist/nuitka"
mkdir -p "${DIST_DIR}"

VERSION=$(python -c "import wallet; print(wallet.__version__)" 2>/dev/null || echo "2.0.0")
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

echo "==> Nuitka build: target=${TARGET} version=${VERSION} os=${OS} arch=${ARCH}"

build_cli() {
    echo "==> Compiling CLI..."
    python -m nuitka \
        --onefile \
        --standalone \
        --assume-yes-for-downloads \
        --output-dir="${DIST_DIR}" \
        --output-filename="vaultkey-${VERSION}-${OS}-${ARCH}" \
        --include-package=wallet \
        --include-package=argon2 \
        --include-package=cryptography \
        --include-package=pydantic \
        --include-package=typer \
        --include-package=rich \
        --nofollow-import-to=textual \
        --nofollow-import-to=customtkinter \
        --nofollow-import-to=tkinter \
        --python-flag=no_site \
        --python-flag=no_warnings \
        wallet/ui/cli.py
    echo "==> CLI done."
}

build_gui() {
    echo "==> Compiling GUI..."
    python -m nuitka \
        --onefile \
        --standalone \
        --assume-yes-for-downloads \
        --output-dir="${DIST_DIR}" \
        --output-filename="vaultkey-gui-${VERSION}-${OS}-${ARCH}" \
        --include-package=wallet \
        --include-package=argon2 \
        --include-package=cryptography \
        --include-package=pydantic \
        --include-package=customtkinter \
        --include-data-dir="$(python -c 'import customtkinter; import os; print(os.path.dirname(customtkinter.__file__))')=customtkinter" \
        --enable-plugin=tk-inter \
        --nofollow-import-to=textual \
        --python-flag=no_site \
        wallet/ui/gui.py
    echo "==> GUI done."
}

build_tui() {
    echo "==> Compiling TUI..."
    python -m nuitka \
        --onefile \
        --standalone \
        --assume-yes-for-downloads \
        --output-dir="${DIST_DIR}" \
        --output-filename="vaultkey-tui-${VERSION}-${OS}-${ARCH}" \
        --include-package=wallet \
        --include-package=argon2 \
        --include-package=cryptography \
        --include-package=pydantic \
        --include-package=textual \
        --include-data-dir="$(python -c 'import textual; import os; print(os.path.dirname(textual.__file__))')=textual" \
        --nofollow-import-to=customtkinter \
        --nofollow-import-to=tkinter \
        --python-flag=no_site \
        wallet/ui/tui.py
    echo "==> TUI done."
}

case "${TARGET}" in
    cli) build_cli ;;
    gui) build_gui ;;
    tui) build_tui ;;
    all) build_cli; build_gui; build_tui ;;
    *) echo "Usage: $0 [cli|gui|tui|all]" >&2; exit 1 ;;
esac

echo ""
echo "==> All done. Output in dist/nuitka/"
