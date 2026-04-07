#!/usr/bin/env bash
# VaultKey — Linux Build Script
# Produces:
#   dist/vaultkey          (CLI, ELF binary)
#   dist/vaultkey-tui      (TUI, ELF binary)
#   dist/VaultKey.AppImage (GUI, AppImage)
#
# Requirements:
#   - Python 3.11+
#   - pip install pyinstaller
#   - appimagetool (auto-downloaded if missing)
#
# Usage:
#   ./build/scripts/build-linux.sh
#   ./build/scripts/build-linux.sh cli
#   ./build/scripts/build-linux.sh gui
#   ./build/scripts/build-linux.sh all

set -euo pipefail

TARGET="${1:-all}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; GRAY='\033[0;37m'; NC='\033[0m'

echo -e "\n  ${CYAN}VaultKey Linux Build Pipeline${NC}"
echo -e "  Target: ${GRAY}$TARGET${NC}\n"

# Validate Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 not found. Install Python 3.11+ first.${NC}"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
if [ "$PY_VER" -lt 311 ]; then
    echo -e "${RED}Error: Python 3.11+ required.${NC}"
    exit 1
fi

# Install PyInstaller if needed
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo -e "${GRAY}Installing PyInstaller...${NC}"
    pip3 install "pyinstaller>=6.0" --quiet
fi

mkdir -p "$DIST"

build_target() {
    local NAME="$1"
    local SPEC="$2"
    echo -e "${GREEN}Building $NAME...${NC}"
    local START=$(date +%s)
    python3 -m PyInstaller --clean --noconfirm "$SPEC"
    local END=$(date +%s)
    echo -e "  ${GRAY}$NAME built in $((END - START))s${NC}"
}

build_appimage() {
    echo -e "${GREEN}Packaging GUI as AppImage...${NC}"
    
    # Check/download appimagetool
    APPIMAGETOOL="$ROOT/build/tools/appimagetool"
    if [ ! -f "$APPIMAGETOOL" ]; then
        echo -e "  ${GRAY}Downloading appimagetool...${NC}"
        mkdir -p "$ROOT/build/tools"
        ARCH=$(uname -m)
        curl -sL "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" \
            -o "$APPIMAGETOOL"
        chmod +x "$APPIMAGETOOL"
    fi
    
    # Create AppDir structure
    APPDIR="$ROOT/dist/VaultKey.AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    mkdir -p "$APPDIR/usr/share/applications"
    mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
    
    # Copy binary
    cp "$DIST/VaultKey" "$APPDIR/usr/bin/VaultKey"
    chmod +x "$APPDIR/usr/bin/VaultKey"
    
    # Desktop entry
    cat > "$APPDIR/vaultkey.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=VaultKey
GenericName=API Key Manager
Comment=Ultra-secure local API key wallet
Exec=VaultKey
Icon=vaultkey
Categories=Utility;Security;
Terminal=false
StartupWMClass=VaultKey
EOF
    cp "$APPDIR/vaultkey.desktop" "$APPDIR/usr/share/applications/"
    
    # Icon (copy if exists, otherwise create placeholder)
    if [ -f "$ROOT/build/assets/icon.png" ]; then
        cp "$ROOT/build/assets/icon.png" "$APPDIR/vaultkey.png"
        cp "$ROOT/build/assets/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/vaultkey.png"
    fi
    
    # AppRun symlink
    ln -sf usr/bin/VaultKey "$APPDIR/AppRun"
    
    # Build AppImage
    ARCH="$(uname -m)" "$APPIMAGETOOL" "$APPDIR" "$DIST/VaultKey-$(uname -m).AppImage"
    chmod +x "$DIST/VaultKey-$(uname -m).AppImage"
    rm -rf "$APPDIR"
    echo -e "  ${GRAY}AppImage created: $DIST/VaultKey-$(uname -m).AppImage${NC}"
}

cd "$ROOT"

case "$TARGET" in
    cli)
        build_target 'CLI' "$ROOT/build/pyinstaller/vaultkey-cli.spec"
        ;;
    tui)
        build_target 'TUI' "$ROOT/build/pyinstaller/vaultkey-tui.spec"
        ;;
    gui)
        build_target 'GUI' "$ROOT/build/pyinstaller/vaultkey-gui.spec"
        build_appimage
        ;;
    all)
        build_target 'CLI' "$ROOT/build/pyinstaller/vaultkey-cli.spec"
        build_target 'TUI' "$ROOT/build/pyinstaller/vaultkey-tui.spec"
        build_target 'GUI' "$ROOT/build/pyinstaller/vaultkey-gui.spec"
        build_appimage
        ;;
    *)
        echo -e "${RED}Unknown target: $TARGET. Use: cli | tui | gui | all${NC}"
        exit 1
        ;;
esac

# Print artifacts + hashes
echo -e "\n${CYAN}Artifacts:${NC}"
for f in "$DIST"/vaultkey "$DIST"/vaultkey-tui "$DIST"/VaultKey "$DIST"/*.AppImage; do
    [ -f "$f" ] || continue
    HASH=$(sha256sum "$f" | awk '{print $1}')
    SIZE=$(du -sh "$f" | awk '{print $1}')
    echo -e "  ${f##*/}  (${SIZE})"
    echo -e "  SHA256: ${GRAY}$HASH${NC}"
    echo "$HASH  ${f##*/}" > "${f}.sha256"
done

echo -e "\n  ${GREEN}Linux build complete.${NC}\n"
