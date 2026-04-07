#!/usr/bin/env bash
# Build VaultKey Linux AppImage
# Usage: bash build/linux/build-appimage.sh
# Requires: appimagetool (auto-downloaded), PyInstaller

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
APPDIR="${DIST_DIR}/VaultKey.AppDir"
VERSION=$(python -c "import wallet; print(wallet.__version__)" 2>/dev/null || echo "2.0.0")

echo "==> Building VaultKey v${VERSION} AppImage for Linux..."

# 1. Build GUI binary with PyInstaller
cd "${PROJECT_ROOT}"
pyinstaller --clean --noconfirm \
    "build/pyinstaller/vaultkey-gui.spec"

# 2. Scaffold AppDir structure
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# 3. Copy binary
cp "${DIST_DIR}/vaultkey-gui" "${APPDIR}/usr/bin/vaultkey-gui"
chmod +x "${APPDIR}/usr/bin/vaultkey-gui"

# 4. Desktop entry + icon
cp "build/linux/vaultkey.desktop" "${APPDIR}/usr/share/applications/vaultkey.desktop"
cp "build/linux/vaultkey.desktop" "${APPDIR}/vaultkey.desktop"  # AppImage root symlink

if [ -f "assets/icon.png" ]; then
    cp "assets/icon.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/vaultkey.png"
    cp "assets/icon.png" "${APPDIR}/vaultkey.png"  # AppImage root icon
else
    echo "WARN: assets/icon.png not found — AppImage will have no icon"
    touch "${APPDIR}/vaultkey.png"
fi

# 5. AppRun entrypoint
cat > "${APPDIR}/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/vaultkey-gui" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

# 6. Download appimagetool if not present
APITOOL="${DIST_DIR}/appimagetool"
if [ ! -f "${APITOOL}" ]; then
    echo "==> Downloading appimagetool..."
    ARCH=$(uname -m)  # x86_64 or aarch64
    curl -L -o "${APITOOL}" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "${APITOOL}"
fi

# 7. Build AppImage
OUTPUT_NAME="VaultKey-${VERSION}-linux-$(uname -m).AppImage"
ARCH=$(uname -m) "${APITOOL}" "${APPDIR}" "${DIST_DIR}/${OUTPUT_NAME}"

echo ""
echo "==> Done! Output: dist/${OUTPUT_NAME}"
echo "    SHA256: $(sha256sum "${DIST_DIR}/${OUTPUT_NAME}" | cut -d' ' -f1)"
