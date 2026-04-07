#!/usr/bin/env bash
# VaultKey — Nuitka Build (Alternative / Performance Builds)
# Nuitka compiles Python to C and then to native code.
# Use this for maximum performance or when PyInstaller fails.
#
# Nuitka advantages over PyInstaller:
#   - Smaller binaries (C compilation, no PYZ overhead)
#   - Better AV (antivirus) compatibility on Windows
#   - Harder to reverse-engineer (no embedded bytecode)
#
# Requirements:
#   pip install nuitka ordered-set zstandard
#   C compiler: gcc/clang on Linux/macOS, MSVC or MinGW on Windows
#
# Usage:
#   ./build/nuitka/build-nuitka.sh cli
#   ./build/nuitka/build-nuitka.sh gui

set -euo pipefail

TARGET="${1:-cli}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "\n  ${CYAN}VaultKey Nuitka Build — $TARGET${NC}\n"

if ! python3 -c "import nuitka" 2>/dev/null; then
    echo "Installing Nuitka..."
    pip3 install nuitka ordered-set zstandard --quiet
fi

NUITKA_COMMON=(
    --onefile
    --assume-yes-for-downloads
    --follow-imports
    --include-package=wallet
    --include-package=cryptography
    --include-package=argon2
    --include-package=pydantic
    --include-package=pydantic_settings
    --include-package=httpx
    --include-package=anyio
    --python-flag=no_site
    --python-flag=no_asserts
    --output-dir="$ROOT/dist-nuitka"
)

case "$TARGET" in
    cli)
        python3 -m nuitka \
            "${NUITKA_COMMON[@]}" \
            --include-package=typer \
            --include-package=rich \
            --include-package=click \
            --include-package=pyperclip \
            --output-filename=vaultkey \
            "$ROOT/wallet/ui/cli.py"
        ;;
    gui)
        python3 -m nuitka \
            "${NUITKA_COMMON[@]}" \
            --include-package=customtkinter \
            --include-data-dir="$(python3 -c 'import customtkinter,pathlib; print(pathlib.Path(customtkinter.__file__).parent)')"=customtkinter \
            --include-package=PIL \
            --include-package=tkinter \
            --enable-plugin=tk-inter \
            --windowed \
            --output-filename=VaultKey \
            "$ROOT/wallet/ui/gui.py"
        ;;
    *)
        echo -e "${RED}Unknown target: $TARGET. Use: cli | gui${NC}"
        exit 1
        ;;
esac

echo -e "\n  ${GREEN}Nuitka build complete. Artifacts in $ROOT/dist-nuitka/${NC}\n"
