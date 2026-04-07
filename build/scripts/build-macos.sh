#!/usr/bin/env bash
# VaultKey — macOS Build Script
# Produces:
#   dist/vaultkey          (CLI, Mach-O binary)
#   dist/vaultkey-tui      (TUI, Mach-O binary)
#   dist/VaultKey.app      (GUI, .app bundle)
#   dist/VaultKey.dmg      (optional — requires create-dmg)
#
# Code Signing (optional — requires Apple Developer account):
#   export VAULTKEY_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
#   export VAULTKEY_NOTARIZE=1
#   export APPLE_ID="your@email.com"
#   export APPLE_TEAM_ID="YOURTEAMID"
#   export APPLE_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"  # app-specific password
#
# Usage:
#   ./build/scripts/build-macos.sh
#   ./build/scripts/build-macos.sh cli
#   ./build/scripts/build-macos.sh gui
#   VAULTKEY_CODESIGN_IDENTITY="..." ./build/scripts/build-macos.sh all

set -euo pipefail

TARGET="${1:-all}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; GRAY='\033[0;37m'; NC='\033[0m'

CODESIGN_IDENTITY="${VAULTKEY_CODESIGN_IDENTITY:-}"
NOTARIZE="${VAULTKEY_NOTARIZE:-0}"

echo -e "\n  ${CYAN}VaultKey macOS Build Pipeline${NC}"
echo -e "  Target: ${GRAY}$TARGET${NC}"
[ -n "$CODESIGN_IDENTITY" ] && echo -e "  Signing: ${GREEN}$CODESIGN_IDENTITY${NC}" || \
    echo -e "  Signing: ${YELLOW}unsigned (set VAULTKEY_CODESIGN_IDENTITY to enable)${NC}"
echo ""

# Validate environment
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 not found.${NC}"; exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
if [ "$PY_VER" -lt 311 ]; then
    echo -e "${RED}Error: Python 3.11+ required.${NC}"; exit 1
fi

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

codesign_binary() {
    local BINARY="$1"
    [ -z "$CODESIGN_IDENTITY" ] && return
    echo -e "  ${GRAY}Signing: $BINARY${NC}"
    codesign \
        --force \
        --deep \
        --options runtime \
        --entitlements "$ROOT/build/assets/entitlements.plist" \
        --sign "$CODESIGN_IDENTITY" \
        --timestamp \
        "$BINARY"
}

codesign_app() {
    local APP="$1"
    [ -z "$CODESIGN_IDENTITY" ] && return
    echo -e "  ${GRAY}Deep-signing .app bundle...${NC}"
    # Sign all frameworks and dylibs first
    find "$APP" -name "*.dylib" -o -name "*.so" -o -name "*.framework" | while read f; do
        codesign --force --sign "$CODESIGN_IDENTITY" --timestamp "$f" 2>/dev/null || true
    done
    # Sign the bundle itself
    codesign \
        --force \
        --deep \
        --options runtime \
        --entitlements "$ROOT/build/assets/entitlements.plist" \
        --sign "$CODESIGN_IDENTITY" \
        --timestamp \
        "$APP"
    echo -e "  ${GREEN}Signed: $APP${NC}"
}

notarize_app() {
    local APP="$1"
    [ "$NOTARIZE" != "1" ] || [ -z "$CODESIGN_IDENTITY" ] && return
    [ -z "${APPLE_ID:-}" ] && echo -e "${YELLOW}APPLE_ID not set — skipping notarization${NC}" && return
    
    echo -e "  ${GRAY}Creating zip for notarization...${NC}"
    local ZIP="$DIST/VaultKey-notarize.zip"
    ditto -c -k --keepParent "$APP" "$ZIP"
    
    echo -e "  ${GRAY}Submitting to Apple notarization service...${NC}"
    xcrun notarytool submit "$ZIP" \
        --apple-id "${APPLE_ID}" \
        --team-id "${APPLE_TEAM_ID}" \
        --password "${APPLE_APP_PASSWORD}" \
        --wait
    
    xcrun stapler staple "$APP"
    rm -f "$ZIP"
    echo -e "  ${GREEN}Notarized and stapled.${NC}"
}

build_dmg() {
    local APP="$DIST/VaultKey.app"
    [ ! -d "$APP" ] && return
    
    if ! command -v create-dmg &>/dev/null; then
        echo -e "  ${YELLOW}create-dmg not found — skipping DMG. Install with: brew install create-dmg${NC}"
        return
    fi
    
    echo -e "${GREEN}Building DMG...${NC}"
    create-dmg \
        --volname "VaultKey" \
        --volicon "$ROOT/build/assets/icon.icns" \
        --window-pos 200 120 \
        --window-size 660 400 \
        --icon-size 160 \
        --icon "VaultKey.app" 180 170 \
        --hide-extension "VaultKey.app" \
        --app-drop-link 480 170 \
        --background "$ROOT/build/assets/dmg-background.png" \
        "$DIST/VaultKey.dmg" \
        "$APP" 2>/dev/null || true
    
    [ -f "$DIST/VaultKey.dmg" ] && \
        echo -e "  ${GREEN}DMG created: $DIST/VaultKey.dmg${NC}" || \
        echo -e "  ${YELLOW}DMG creation failed — continuing${NC}"
}

cd "$ROOT"

case "$TARGET" in
    cli)
        build_target 'CLI' "$ROOT/build/pyinstaller/vaultkey-cli.spec"
        codesign_binary "$DIST/vaultkey"
        ;;
    tui)
        build_target 'TUI' "$ROOT/build/pyinstaller/vaultkey-tui.spec"
        codesign_binary "$DIST/vaultkey-tui"
        ;;
    gui)
        build_target 'GUI' "$ROOT/build/pyinstaller/vaultkey-gui.spec"
        codesign_app "$DIST/VaultKey.app"
        notarize_app "$DIST/VaultKey.app"
        build_dmg
        ;;
    all)
        build_target 'CLI' "$ROOT/build/pyinstaller/vaultkey-cli.spec"
        build_target 'TUI' "$ROOT/build/pyinstaller/vaultkey-tui.spec"
        build_target 'GUI' "$ROOT/build/pyinstaller/vaultkey-gui.spec"
        codesign_binary "$DIST/vaultkey"
        codesign_binary "$DIST/vaultkey-tui"
        codesign_app "$DIST/VaultKey.app"
        notarize_app "$DIST/VaultKey.app"
        build_dmg
        ;;
    *)
        echo -e "${RED}Unknown target: $TARGET. Use: cli | tui | gui | all${NC}"
        exit 1
        ;;
esac

# Print artifacts + hashes
echo -e "\n${CYAN}Artifacts:${NC}"
for f in "$DIST"/vaultkey "$DIST"/vaultkey-tui "$DIST"/VaultKey.app "$DIST"/*.dmg; do
    [ -e "$f" ] || continue
    if [ -d "$f" ]; then
        SIZE=$(du -sh "$f" | awk '{print $1}')
        echo -e "  ${f##*/}  (${SIZE})"
    else
        HASH=$(shasum -a 256 "$f" | awk '{print $1}')
        SIZE=$(du -sh "$f" | awk '{print $1}')
        echo -e "  ${f##*/}  (${SIZE})"
        echo -e "  SHA256: ${GRAY}$HASH${NC}"
        echo "$HASH  ${f##*/}" > "${f}.sha256"
    fi
done

echo -e "\n  ${GREEN}macOS build complete.${NC}\n"
