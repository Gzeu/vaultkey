#!/usr/bin/env bash
# VaultKey — macOS build script
# Produces:
#   dist/vaultkey-cli         (CLI binary)
#   dist/vaultkey-tui         (TUI binary)
#   dist/VaultKey.app         (GUI app bundle)
#   dist/VaultKey-macos.dmg   (DMG installer, if create-dmg is available)
#
# Code signing:
#   Set MACOS_SIGN_IDENTITY env var to your Developer ID Application cert name
#   e.g.: export MACOS_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
#
# Usage:
#   ./build/scripts/build-macos.sh
#   MACOS_SIGN_IDENTITY="Developer ID Application: ..." ./build/scripts/build-macos.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="${ROOT}/dist"
BUILD_TMP="${ROOT}/build_tmp"
SIGN_IDENTITY="${MACOS_SIGN_IDENTITY:-}"

echo "====================================================="
echo " VaultKey macOS Build Script"
echo "====================================================="
echo " Root   : ${ROOT}"
echo " Dist   : ${DIST}"
echo " Signing: ${SIGN_IDENTITY:-UNSIGNED}"
echo ""

# ── Virtualenv ────────────────────────────────────────────────────────────────
if [[ ! -d "${ROOT}/.venv-build" ]]; then
  echo "[*] Creating isolated build virtualenv..."
  python3 -m venv "${ROOT}/.venv-build"
fi

source "${ROOT}/.venv-build/bin/activate"

echo "[*] Installing build dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e "${ROOT}[dev]"
pip install --quiet pyinstaller

mkdir -p "${DIST}" "${BUILD_TMP}"

# ── Build CLI ─────────────────────────────────────────────────────────────────
echo ""
echo "[1/3] Building CLI binary..."
pyinstaller \
  --distpath "${DIST}" \
  --workpath "${BUILD_TMP}/cli" \
  --noconfirm \
  "${ROOT}/build/pyinstaller/vaultkey-cli.spec"
echo "[*] Built: ${DIST}/vaultkey-cli"

# ── Build TUI ─────────────────────────────────────────────────────────────────
echo ""
echo "[2/3] Building TUI binary..."
pyinstaller \
  --distpath "${DIST}" \
  --workpath "${BUILD_TMP}/tui" \
  --noconfirm \
  "${ROOT}/build/pyinstaller/vaultkey-tui.spec"
echo "[*] Built: ${DIST}/vaultkey-tui"

# ── Build GUI (.app) ─────────────────────────────────────────────────────────
echo ""
echo "[3/3] Building GUI app bundle..."
pyinstaller \
  --distpath "${DIST}" \
  --workpath "${BUILD_TMP}/gui" \
  --noconfirm \
  "${ROOT}/build/pyinstaller/vaultkey-gui.spec"
echo "[*] Built: ${DIST}/VaultKey.app"

# ── Code signing ─────────────────────────────────────────────────────────────
if [[ -n "$SIGN_IDENTITY" ]]; then
  echo ""
  echo "[*] Code signing with: ${SIGN_IDENTITY}"

  # Sign frameworks and dylibs first (inside-out order)
  find "${DIST}/VaultKey.app" -name "*.dylib" -o -name "*.so" | while read -r lib; do
    codesign --force --options runtime \
      --entitlements "${ROOT}/build/assets/entitlements.plist" \
      --sign "${SIGN_IDENTITY}" "$lib" 2>/dev/null || true
  done

  # Sign CLI and TUI binaries
  for bin in vaultkey-cli vaultkey-tui; do
    if [[ -f "${DIST}/${bin}" ]]; then
      codesign --force --options runtime \
        --entitlements "${ROOT}/build/assets/entitlements.plist" \
        --sign "${SIGN_IDENTITY}" "${DIST}/${bin}"
    fi
  done

  # Sign the .app bundle (must be last)
  codesign --force --deep --options runtime \
    --entitlements "${ROOT}/build/assets/entitlements.plist" \
    --sign "${SIGN_IDENTITY}" \
    "${DIST}/VaultKey.app"

  echo "[*] Verifying signature..."
  codesign --verify --deep --strict --verbose=2 "${DIST}/VaultKey.app"
  spctl --assess --verbose=4 --type exec "${DIST}/VaultKey.app" 2>&1 || \
    echo "[!] spctl: app not notarized yet (expected before notarization)"
else
  echo ""
  echo "[!] No MACOS_SIGN_IDENTITY set — skipping code signing"
  echo "    Unsigned builds will trigger Gatekeeper on other Macs."
  echo "    Set MACOS_SIGN_IDENTITY to your Developer ID cert to sign."
fi

# ── DMG packaging ─────────────────────────────────────────────────────────────
if command -v create-dmg &>/dev/null; then
  echo ""
  echo "[*] Creating DMG installer..."
  create-dmg \
    --volname "VaultKey" \
    --volicon "${ROOT}/build/assets/vaultkey.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "VaultKey.app" 175 190 \
    --hide-extension "VaultKey.app" \
    --app-drop-link 425 190 \
    "${DIST}/VaultKey-macos.dmg" \
    "${DIST}/VaultKey.app"
  echo "[*] Built: ${DIST}/VaultKey-macos.dmg"
else
  echo ""
  echo "[!] create-dmg not found — skipping DMG creation"
  echo "    Install with: brew install create-dmg"
  # Fallback: plain zip
  cd "${DIST}" && zip -r VaultKey-macos.zip VaultKey.app
  echo "[*] Fallback: ${DIST}/VaultKey-macos.zip"
fi

# ── SHA256 ────────────────────────────────────────────────────────────────────
echo ""
echo "[*] Generating SHA256 checksums..."
cd "${DIST}"
shasum -a 256 vaultkey-cli vaultkey-tui VaultKey-macos.dmg \
  2>/dev/null | tee SHA256SUMS-macos.txt || \
shasum -a 256 vaultkey-cli vaultkey-tui VaultKey-macos.zip \
  2>/dev/null | tee SHA256SUMS-macos.txt || true

echo ""
echo "====================================================="
echo " macOS build complete!"
echo "====================================================="
ls -lh "${DIST}"
