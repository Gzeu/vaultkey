#!/usr/bin/env bash
# VaultKey — Linux build script
# Produces: dist/vaultkey-cli, dist/vaultkey-tui, dist/vaultkey-linux.AppImage
# Requirements: Python 3.11+, appimagetool in PATH (or auto-downloaded)
#
# Usage:
#   ./build/scripts/build-linux.sh             # builds all targets
#   ./build/scripts/build-linux.sh --cli-only  # CLI only
#   ./build/scripts/build-linux.sh --gui-only  # GUI only

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="${ROOT}/dist"
BUILD_TMP="${ROOT}/build_tmp"

CLI_ONLY=false
GUI_ONLY=false
for arg in "$@"; do
  [[ "$arg" == "--cli-only" ]] && CLI_ONLY=true
  [[ "$arg" == "--gui-only" ]] && GUI_ONLY=true
done

echo "====================================================="
echo " VaultKey Linux Build Script"
echo "====================================================="
echo " Root : ${ROOT}"
echo " Dist : ${DIST}"
echo ""

# ── Setup virtualenv ──────────────────────────────────────────────────────────
if [[ ! -d "${ROOT}/.venv-build" ]]; then
  echo "[*] Creating isolated build virtualenv..."
  python3 -m venv "${ROOT}/.venv-build"
fi

source "${ROOT}/.venv-build/bin/activate"

echo "[*] Installing build dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e "${ROOT}[dev]"
pip install --quiet pyinstaller upx-ucl || pip install --quiet pyinstaller

mkdir -p "${DIST}" "${BUILD_TMP}"

# ── Build CLI ─────────────────────────────────────────────────────────────────
if [[ "$GUI_ONLY" == false ]]; then
  echo ""
  echo "[1/3] Building CLI binary..."
  pyinstaller \
    --distpath "${DIST}" \
    --workpath "${BUILD_TMP}/cli" \
    --noconfirm \
    "${ROOT}/build/pyinstaller/vaultkey-cli.spec"

  echo "[*] Built: ${DIST}/vaultkey-cli"

  echo ""
  echo "[2/3] Building TUI binary..."
  pyinstaller \
    --distpath "${DIST}" \
    --workpath "${BUILD_TMP}/tui" \
    --noconfirm \
    "${ROOT}/build/pyinstaller/vaultkey-tui.spec"

  echo "[*] Built: ${DIST}/vaultkey-tui"
fi

# ── Build GUI ─────────────────────────────────────────────────────────────────
if [[ "$CLI_ONLY" == false ]]; then
  echo ""
  echo "[3/3] Building GUI binary..."
  pyinstaller \
    --distpath "${DIST}" \
    --workpath "${BUILD_TMP}/gui" \
    --noconfirm \
    "${ROOT}/build/pyinstaller/vaultkey-gui.spec"

  echo "[*] Built: ${DIST}/vaultkey-gui"
fi

# ── AppImage packaging (GUI) ─────────────────────────────────────────────────
if [[ "$CLI_ONLY" == false ]]; then
  echo ""
  echo "[AppImage] Packaging GUI as AppImage..."

  # Download appimagetool if not in PATH
  APPIMAGETOOL="$(command -v appimagetool 2>/dev/null || true)"
  if [[ -z "$APPIMAGETOOL" ]]; then
    echo "[*] appimagetool not found — downloading..."
    APPIMAGETOOL="/tmp/appimagetool"
    curl -fsSL -o "$APPIMAGETOOL" \
      "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
  fi

  APPDIR="${BUILD_TMP}/VaultKey.AppDir"
  rm -rf "$APPDIR"
  mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/share/icons/hicolor/512x512/apps"

  # Copy binary
  cp "${DIST}/vaultkey-gui" "${APPDIR}/usr/bin/vaultkey"
  chmod +x "${APPDIR}/usr/bin/vaultkey"

  # Desktop entry
  cat > "${APPDIR}/vaultkey.desktop" << 'DESKTOP'
[Desktop Entry]
Name=VaultKey
Exec=vaultkey
Icon=vaultkey
Type=Application
Categories=Utility;Security;
Comment=Ultra-secure API key manager
DESKTOP

  # Icon
  if [[ -f "${ROOT}/build/assets/vaultkey.png" ]]; then
    cp "${ROOT}/build/assets/vaultkey.png" \
       "${APPDIR}/usr/share/icons/hicolor/512x512/apps/vaultkey.png"
    cp "${ROOT}/build/assets/vaultkey.png" "${APPDIR}/vaultkey.png"
  fi

  # AppRun symlink
  cat > "${APPDIR}/AppRun" << 'APPRUN'
#!/bin/bash
exec "$(dirname "$0")/usr/bin/vaultkey" "$@"
APPRUN
  chmod +x "${APPDIR}/AppRun"

  # Build
  ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "${DIST}/vaultkey-linux.AppImage" 2>&1
  chmod +x "${DIST}/vaultkey-linux.AppImage"
  echo "[*] Built: ${DIST}/vaultkey-linux.AppImage"
fi

# ── SHA256 checksums ─────────────────────────────────────────────────────────
echo ""
echo "[*] Generating SHA256 checksums..."
cd "${DIST}"
sha256sum vaultkey-cli vaultkey-tui vaultkey-gui vaultkey-linux.AppImage \
  2>/dev/null | tee SHA256SUMS-linux.txt || true

echo ""
echo "====================================================="
echo " Linux build complete!"
echo "====================================================="
ls -lh "${DIST}"
