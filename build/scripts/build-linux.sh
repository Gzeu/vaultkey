#!/usr/bin/env bash
# VaultKey — Linux build script
# Usage: bash build/scripts/build-linux.sh [cli|tui|gui|all] [version]
# Produces:
#   dist/linux/vaultkey         (CLI, raw ELF)
#   dist/linux/vaultkey-tui     (TUI, raw ELF)
#   dist/linux/VaultKey-*.AppImage  (GUI, portable AppImage)
# Requires: python3.11+, pyinstaller, appimagetool (auto-downloaded if missing)

set -euo pipefail

TARGET="${1:-all}"
VERSION="${2:-2.0.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist/linux"

echo "==> VaultKey Linux Build v$VERSION"
echo "    Target : $TARGET"
echo "    Root   : $ROOT"
mkdir -p "$DIST"

# Check PyInstaller
python3 -m PyInstaller --version &>/dev/null || pip3 install pyinstaller

build_target() {
    local name="$1"
    echo "==> Building $name..."
    python3 -m PyInstaller \
        --distpath "$DIST" \
        --workpath "$ROOT/build/tmp/$name" \
        --noconfirm \
        --clean \
        "$ROOT/build/pyinstaller/vaultkey-$name.spec"
    echo "    OK -> dist/linux/$name"
}

build_appimage() {
    echo "==> Packaging GUI as AppImage..."
    local APPDIR="$ROOT/build/tmp/AppDir"
    local BINARY="$DIST/vaultkey-gui"

    [ -f "$BINARY" ] || { echo "ERROR: $BINARY not found. Build gui first."; exit 1; }

    # Download appimagetool if not on PATH
    if ! command -v appimagetool &>/dev/null; then
        echo "    Downloading appimagetool..."
        curl -fsSL -o /tmp/appimagetool \
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
        chmod +x /tmp/appimagetool
        APPIMAGETOOL=/tmp/appimagetool
    else
        APPIMAGETOOL=appimagetool
    fi

    # Build AppDir structure
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    cp "$BINARY" "$APPDIR/usr/bin/vaultkey-gui"
    chmod +x "$APPDIR/usr/bin/vaultkey-gui"

    # AppRun entrypoint
    cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
exec "$APPDIR/usr/bin/vaultkey-gui" "$@"
EOF
    chmod +x "$APPDIR/AppRun"

    # .desktop file
    cat > "$APPDIR/vaultkey.desktop" << EOF
[Desktop Entry]
Name=VaultKey
Exec=vaultkey-gui
Icon=vaultkey
Type=Application
Categories=Utility;Security;
Comment=Ultra-secure API key wallet
EOF

    # Use placeholder icon if none exists
    if [ -f "$ROOT/docs/assets/icon.png" ]; then
        cp "$ROOT/docs/assets/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/vaultkey.png"
        cp "$ROOT/docs/assets/icon.png" "$APPDIR/vaultkey.png"
    else
        # Create minimal SVG icon as fallback
        cat > "$APPDIR/vaultkey.svg" << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#01696f"/>
  <path d="M32 14a12 12 0 0 0-12 12v4h-4v20h32V30h-4v-4a12 12 0 0 0-12-12zm0 4a8 8 0 0 1 8 8v4H24v-4a8 8 0 0 1 8-8zm0 14a4 4 0 1 1 0 8 4 4 0 0 1 0-8z" fill="white"/>
</svg>
EOF
    fi

    ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$DIST/VaultKey-$VERSION-x86_64.AppImage"
    echo "    OK -> dist/linux/VaultKey-$VERSION-x86_64.AppImage"
}

if [[ "$TARGET" == 'all' || "$TARGET" == 'cli' ]]; then build_target 'cli'; fi
if [[ "$TARGET" == 'all' || "$TARGET" == 'tui' ]]; then build_target 'tui'; fi
if [[ "$TARGET" == 'all' || "$TARGET" == 'gui' ]]; then
    build_target 'gui'
    build_appimage
fi

echo ""
echo "==> Done. Binaries in: dist/linux/"
ls -lh "$DIST" 2>/dev/null || true
