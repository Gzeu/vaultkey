# Build VaultKey Windows .exe
# Usage: .\build\windows\build-windows.ps1
# Requires: PyInstaller, UPX (optional, auto-detected)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path "$PSScriptRoot\..\.."
$DistDir = Join-Path $ProjectRoot "dist"

try {
    $Version = python -c "import wallet; print(wallet.__version__)" 2>$null
} catch {
    $Version = "2.0.0"
}

Write-Host "==> Building VaultKey v$Version for Windows..." -ForegroundColor Cyan

Set-Location $ProjectRoot

# 1. Check UPX
$UpxPath = Get-Command upx -ErrorAction SilentlyContinue
if ($UpxPath) {
    Write-Host "==> UPX found: $($UpxPath.Source)" -ForegroundColor Green
} else {
    Write-Host "INFO: UPX not found. Binaries won't be compressed. Install from https://upx.github.io/" -ForegroundColor Yellow
}

# 2. Build CLI
Write-Host "==> Building CLI binary..." -ForegroundColor Cyan
pyinstaller --clean --noconfirm `
    "build\pyinstaller\vaultkey-cli.spec"

# 3. Build GUI
Write-Host "==> Building GUI binary..." -ForegroundColor Cyan
pyinstaller --clean --noconfirm `
    "build\pyinstaller\vaultkey-gui.spec"

# 4. Rename with version + platform suffix
$CliExe = Join-Path $DistDir "vaultkey.exe"
$GuiExe = Join-Path $DistDir "vaultkey-gui.exe"
$CliFinal = Join-Path $DistDir "VaultKey-$Version-windows-x64-cli.exe"
$GuiFinal = Join-Path $DistDir "VaultKey-$Version-windows-x64-gui.exe"

if (Test-Path $CliExe) { Rename-Item $CliExe $CliFinal }
if (Test-Path $GuiExe) { Rename-Item $GuiExe $GuiFinal }

# 5. SHA256 checksums
Write-Host ""
Write-Host "==> Checksums:" -ForegroundColor Cyan
if (Test-Path $CliFinal) {
    $hash = (Get-FileHash $CliFinal -Algorithm SHA256).Hash
    Write-Host "  CLI: $hash"
    "$hash  $(Split-Path $CliFinal -Leaf)" | Out-File -Append "$DistDir\SHA256SUMS.txt"
}
if (Test-Path $GuiFinal) {
    $hash = (Get-FileHash $GuiFinal -Algorithm SHA256).Hash
    Write-Host "  GUI: $hash"
    "$hash  $(Split-Path $GuiFinal -Leaf)" | Out-File -Append "$DistDir\SHA256SUMS.txt"
}

Write-Host ""
Write-Host "==> Done! Output in dist/" -ForegroundColor Green
