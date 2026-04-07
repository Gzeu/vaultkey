#!/usr/bin/env bash
# VaultKey — macOS build script
# Usage: bash build/scripts/build-macos.sh [cli|tui|gui|all] [version]
# Produces:
#   dist/macos/vaultkey              (CLI)
#   dist/macos/vaultkey-tui          (TUI)
#   dist/macos/VaultKey.app          (GUI .app bundle)
#   dist/macos/VaultKey-*.dmg        (DMG via create-dmg, optional)
# Signing: set CODESIGN_IDENTITY and APPLE_TEAM_ID env vars
#   If not set, builds are unsigned (fine for local use / dev)

set -euo pipefail

TARGET="${1:-all}"
VERSION="${2:-2.0.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist/macos"
SIGN_ID="${CODESIGN_IDENTITY:-}"
TEAM_ID="${APPLE_TEAM_ID:-}"

echo "==> VaultKey macOS Build v$VERSION"
echo "    Target    : $TARGET"
echo "    Root      : $ROOT"
echo "    Sign ID   : ${SIGN_ID:-'(unsigned)'}"
mkdir -p "$DIST"

python3 -m PyInstaller --version &>/dev/null || pip3 install pyinstaller

build_target() {
    local name="$1"
    echo "==> Building $name..."
    python3 -m PyInstaller \
        --distpath "$DIST" \
        --workpath "$ROOT/build/tmp/$name" \
        --noconfirm \
        --clean \
        --target-arch universal2 \
        "$ROOT/build/pyinstaller/vaultkey-$name.spec"
    echo "    OK -> dist/macos/$name"
}

codesign_app() {
    local app="$DIST/VaultKey.app"
    [ -d "$app" ] || return 0
    [ -n "$SIGN_ID" ] || { echo "    Skipping codesign (CODESIGN_IDENTITY not set)"; return 0; }

    echo "==> Signing VaultKey.app with: $SIGN_ID"
    codesign \
        --force \
        --deep \
        --sign "$SIGN_ID" \
        --options runtime \
        --entitlements "$ROOT/build/macos/entitlements.plist" \
        --timestamp \
        "$app"
    echo "    codesign OK"

    # Verify
    codesign --verify --deep --strict --verbose=2 "$app"
    spctl --assess --type execute --verbose "$app" || echo "    (spctl: Gatekeeper check — may fail without notarization)"
}

build_dmg() {
    local app="$DIST/VaultKey.app"
    local dmg="$DIST/VaultKey-$VERSION.dmg"
    [ -d "$app" ] || return 0
    command -v create-dmg &>/dev/null || { echo "    Skipping DMG (create-dmg not found; brew install create-dmg)"; return 0; }

    echo "==> Creating DMG..."
    create-dmg \
        --volname "VaultKey $VERSION" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "VaultKey.app" 175 190 \
        --hide-extension "VaultKey.app" \
        --app-drop-link 425 190 \
        "$dmg" \
        "$app"
    echo "    OK -> $dmg"

    # Notarize (requires APPLE_TEAM_ID and notarytool credentials in keychain)
    if [ -n "$TEAM_ID" ] && command -v xcrun &>/dev/null; then
        echo "==> Notarizing DMG (team: $TEAM_ID)..."
        xcrun notarytool submit "$dmg" \
            --keychain-profile "vaultkey-notary" \
            --wait \
            --timeout 10m || echo "    Notarization failed or skipped."
        xcrun stapler staple "$dmg" || true
        echo "    Notarization done."
    fi
}

if [[ "$TARGET" == 'all' || "$TARGET" == 'cli' ]]; then build_target 'cli'; fi
if [[ "$TARGET" == 'all' || "$TARGET" == 'tui' ]]; then build_target 'tui'; fi
if [[ "$TARGET" == 'all' || "$TARGET" == 'gui' ]]; then
    build_target 'gui'
    codesign_app
    build_dmg
fi

echo ""
echo "==> Done. Binaries in: dist/macos/"
ls -lh "$DIST"
