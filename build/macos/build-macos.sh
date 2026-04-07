#!/usr/bin/env bash
# Build VaultKey macOS .app bundle + optional codesign + DMG
# Usage: bash build/macos/build-macos.sh [--sign] [--dmg]
# Requires: PyInstaller, create-dmg (optional)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
VERSION=$(python -c "import wallet; print(wallet.__version__)" 2>/dev/null || echo "2.0.0")
SIGN=false
DMG=false

for arg in "$@"; do
    case $arg in
        --sign) SIGN=true ;;
        --dmg)  DMG=true ;;
    esac
done

echo "==> Building VaultKey v${VERSION} for macOS..."

cd "${PROJECT_ROOT}"

# 1. Build .app bundle
pyinstaller --clean --noconfirm \
    "build/pyinstaller/vaultkey-gui.spec"

APP_BUNDLE="${DIST_DIR}/VaultKey.app"

if [ ! -d "${APP_BUNDLE}" ]; then
    echo "ERROR: .app bundle not found at ${APP_BUNDLE}" >&2
    exit 1
fi

# 2. Optional codesign
if [ "${SIGN}" = "true" ]; then
    if [ -z "${CODESIGN_IDENTITY:-}" ]; then
        echo "ERROR: CODESIGN_IDENTITY env var required for --sign" >&2
        echo "       Export: export CODESIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'" >&2
        exit 1
    fi
    echo "==> Signing with identity: ${CODESIGN_IDENTITY}"
    codesign --deep --force --verify --verbose \
        --sign "${CODESIGN_IDENTITY}" \
        --entitlements "build/macos/entitlements.plist" \
        --options runtime \
        "${APP_BUNDLE}"
    echo "==> Verifying signature..."
    codesign --verify --deep --strict --verbose=4 "${APP_BUNDLE}"
    spctl --assess --verbose=4 --type exec "${APP_BUNDLE}" || echo "WARN: spctl check failed (expected without notarization)"
else
    echo "INFO: Skipping codesign (no --sign flag). Binary will show Gatekeeper warning on first launch."
    echo "      Run: xattr -cr dist/VaultKey.app  (to allow unsigned on your machine)"
fi

# 3. Optional DMG creation
if [ "${DMG}" = "true" ]; then
    OUTPUT_DMG="${DIST_DIR}/VaultKey-${VERSION}-macos.dmg"
    if command -v create-dmg &>/dev/null; then
        create-dmg \
            --volname "VaultKey ${VERSION}" \
            --volicon "assets/icon.icns" \
            --window-pos 200 120 \
            --window-size 600 300 \
            --icon-size 100 \
            --icon "VaultKey.app" 175 120 \
            --hide-extension "VaultKey.app" \
            --app-drop-link 425 120 \
            "${OUTPUT_DMG}" \
            "${APP_BUNDLE}"
        echo "==> DMG created: ${OUTPUT_DMG}"
    else
        echo "WARN: create-dmg not found. Install: brew install create-dmg"
        echo "      Falling back to hdiutil..."
        hdiutil create -volname "VaultKey" -srcfolder "${APP_BUNDLE}" \
            -ov -format UDZO "${OUTPUT_DMG}"
        echo "==> DMG created: ${OUTPUT_DMG}"
    fi
fi

echo ""
echo "==> Done! Output: dist/VaultKey.app"
