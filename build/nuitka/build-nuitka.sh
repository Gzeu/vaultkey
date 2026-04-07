#!/usr/bin/env bash
# VaultKey — Nuitka build script
# Nuitka compiles Python to C, producing smaller and faster binaries than PyInstaller.
# Best used on Linux/macOS. Windows support is good but requires MSVC or MinGW.
#
# Requirements:
#   pip install nuitka ordered-set zstandard
#   Linux:  gcc, patchelf
#   macOS:  clang (Xcode CLI tools)
#   Windows: MSVC (Visual Studio Build Tools)
#
# Usage:
#   ./build/nuitka/build-nuitka.sh [cli|tui|gui|all]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="${ROOT}/dist-nuitka"
TARGET="${1:-all}"

echo "====================================================="
echo " VaultKey Nuitka Build — Target: ${TARGET}"
echo "====================================================="

if [[ ! -d "${ROOT}/.venv-build" ]]; then
  python3 -m venv "${ROOT}/.venv-build"
fi
source "${ROOT}/.venv-build/bin/activate"

pip install --quiet nuitka ordered-set zstandard
mkdir -p "$DIST"

# ── Common Nuitka flags ───────────────────────────────────────────────────────
COMMON_FLAGS=(
  --standalone
  --onefile
  --assume-yes-for-downloads
  --python-flag=no_site
  --python-flag=no_warnings
  --python-flag=isolated
  # Include wallet package
  --include-package=wallet
  --include-package=wallet.core
  --include-package=wallet.models
  --include-package=wallet.utils
  --include-package=wallet.ui
  # Cryptography
  --include-package=cryptography
  --include-distribution-metadata=cryptography
  # argon2-cffi
  --include-package=argon2
  --include-distribution-metadata=argon2_cffi
  # pydantic
  --include-package=pydantic
  --include-package=pydantic_core
  --include-distribution-metadata=pydantic
  # misc
  --include-package=httpx
  --include-package=pyperclip
  --include-package=rich
  --include-package=typer
  # Output
  --output-dir="${DIST}"
  --remove-output
)

# ── CLI ───────────────────────────────────────────────────────────────────────
build_cli() {
  echo "[*] Building CLI with Nuitka..."
  python -m nuitka \
    "${COMMON_FLAGS[@]}" \
    --output-filename=vaultkey-cli \
    --console-mode=force \
    "${ROOT}/wallet/ui/cli.py"
  echo "[*] Done: ${DIST}/vaultkey-cli"
}

# ── TUI ───────────────────────────────────────────────────────────────────────
build_tui() {
  echo "[*] Building TUI with Nuitka..."
  python -m nuitka \
    "${COMMON_FLAGS[@]}" \
    --include-package=textual \
    --include-data-dir="$(python -c 'import textual; import os; print(os.path.dirname(textual.__file__))')"=textual \
    --output-filename=vaultkey-tui \
    --console-mode=force \
    "${ROOT}/wallet/ui/tui.py"
  echo "[*] Done: ${DIST}/vaultkey-tui"
}

# ── GUI ───────────────────────────────────────────────────────────────────────
build_gui() {
  echo "[*] Building GUI with Nuitka..."
  python -m nuitka \
    "${COMMON_FLAGS[@]}" \
    --include-package=customtkinter \
    --include-package=tkinter \
    --include-data-dir="$(python -c 'import customtkinter; import os; print(os.path.dirname(customtkinter.__file__))')"=customtkinter \
    --output-filename=vaultkey-gui \
    --console-mode=disable \
    "${ROOT}/wallet/ui/gui.py"
  echo "[*] Done: ${DIST}/vaultkey-gui"
}

case "$TARGET" in
  cli) build_cli ;;
  tui) build_tui ;;
  gui) build_gui ;;
  all) build_cli; build_tui; build_gui ;;
  *) echo "Usage: $0 [cli|tui|gui|all]"; exit 1 ;;
esac

echo ""
echo "====================================================="
echo " Nuitka build complete!"
echo "====================================================="
ls -lh "$DIST"
