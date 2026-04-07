# build/assets/

Place platform icon files here **before running a build**.

| File | Platform | Format | Size |
|------|----------|--------|------|
| `vaultkey.ico` | Windows | ICO (multi-size: 16/32/48/256) | ≤ 200KB |
| `vaultkey.icns` | macOS | ICNS | ≤ 500KB |
| `vaultkey.png` | Linux | PNG | 512×512px |

## Generating icons from a single PNG

```bash
# Install tools
brew install imagemagick          # macOS
sudo apt install imagemagick      # Linux

# Windows ICO (requires ImageMagick)
convert vaultkey-512.png -define icon:auto-resize=256,128,96,64,48,32,16 vaultkey.ico

# macOS ICNS
mkdir vaultkey.iconset
for s in 16 32 64 128 256 512; do
  sips -z $s $s vaultkey-512.png --out vaultkey.iconset/icon_${s}x${s}.png
done
iconutil -c icns vaultkey.iconset

# Linux PNG — just copy
cp vaultkey-512.png vaultkey.png
```

See `build/README.md` for full build instructions.
