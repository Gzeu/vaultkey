# VaultKey — Windows build script
# Usage: .\build\scripts\build-windows.ps1 [-Target cli|tui|gui|all] [-Version 2.0.0]
# Requires: Python 3.11+, pip install pyinstaller upx (upx optional but recommended)

param(
    [ValidateSet('cli','tui','gui','all')]
    [string]$Target = 'all',
    [string]$Version = '2.0.0'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path (Split-Path $PSScriptRoot)
$Dist = Join-Path $Root 'dist'

Write-Host "==> VaultKey Windows Build v$Version" -ForegroundColor Cyan
Write-Host "    Target  : $Target"
Write-Host "    Root    : $Root"
Write-Host ""

# Ensure PyInstaller is installed
pip show pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}

function Build-Target($name) {
    Write-Host "==> Building $name..." -ForegroundColor Green
    $spec = Join-Path $Root "build\pyinstaller\vaultkey-$name.spec"
    pyinstaller `
        --distpath "$Dist\windows" `
        --workpath "$Root\build\tmp\$name" `
        --noconfirm `
        --clean `
        $spec
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed for $name"
        exit 1
    }
    Write-Host "    OK -> dist\windows\$name" -ForegroundColor Green
}

if ($Target -eq 'all' -or $Target -eq 'cli') { Build-Target 'cli' }
if ($Target -eq 'all' -or $Target -eq 'tui') { Build-Target 'tui' }
if ($Target -eq 'all' -or $Target -eq 'gui') { Build-Target 'gui' }

Write-Host ""
Write-Host "==> Build complete. Binaries in: dist\windows\" -ForegroundColor Cyan
Get-ChildItem "$Dist\windows" -Recurse -Filter '*.exe' | ForEach-Object {
    $size = [math]::Round($_.Length / 1MB, 1)
    Write-Host "    $($_.Name)  ($size MB)"
}
