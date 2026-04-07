# VaultKey — Windows build script (PowerShell)
# Produces:
#   dist\vaultkey-cli.exe
#   dist\vaultkey-tui.exe
#   dist\vaultkey-gui.exe
#
# Requirements: Python 3.11+, pip
# Usage (from repo root):
#   .\build\scripts\build-windows.ps1
#   .\build\scripts\build-windows.ps1 -CliOnly
#   .\build\scripts\build-windows.ps1 -GuiOnly

param(
    [switch]$CliOnly,
    [switch]$GuiOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root   = Resolve-Path (Join-Path $PSScriptRoot "..\..") | Select-Object -ExpandProperty Path
$Dist   = Join-Path $Root "dist"
$BuildTmp = Join-Path $Root "build_tmp"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " VaultKey Windows Build Script" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " Root : $Root"
Write-Host " Dist : $Dist"
Write-Host ""

# ── Virtualenv ────────────────────────────────────────────────────────────────
$VenvPath = Join-Path $Root ".venv-build"
if (-not (Test-Path $VenvPath)) {
    Write-Host "[*] Creating isolated build virtualenv..."
    python -m venv $VenvPath
}

$PipPath = Join-Path $VenvPath "Scripts\pip.exe"
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"

Write-Host "[*] Installing build dependencies..."
& $PipPath install --quiet --upgrade pip
& $PipPath install --quiet -e "$Root[dev]"
& $PipPath install --quiet pyinstaller

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
New-Item -ItemType Directory -Force -Path $BuildTmp | Out-Null

$PyInstaller = Join-Path $VenvPath "Scripts\pyinstaller.exe"

# ── Build CLI ─────────────────────────────────────────────────────────────────
if (-not $GuiOnly) {
    Write-Host ""
    Write-Host "[1/3] Building CLI binary..." -ForegroundColor Yellow
    & $PyInstaller `
        --distpath $Dist `
        --workpath (Join-Path $BuildTmp "cli") `
        --noconfirm `
        (Join-Path $Root "build\pyinstaller\vaultkey-cli.spec")
    Write-Host "[*] Built: $Dist\vaultkey-cli.exe" -ForegroundColor Green

    Write-Host ""
    Write-Host "[2/3] Building TUI binary..." -ForegroundColor Yellow
    & $PyInstaller `
        --distpath $Dist `
        --workpath (Join-Path $BuildTmp "tui") `
        --noconfirm `
        (Join-Path $Root "build\pyinstaller\vaultkey-tui.spec")
    Write-Host "[*] Built: $Dist\vaultkey-tui.exe" -ForegroundColor Green
}

# ── Build GUI ─────────────────────────────────────────────────────────────────
if (-not $CliOnly) {
    Write-Host ""
    Write-Host "[3/3] Building GUI binary..." -ForegroundColor Yellow
    & $PyInstaller `
        --distpath $Dist `
        --workpath (Join-Path $BuildTmp "gui") `
        --noconfirm `
        (Join-Path $Root "build\pyinstaller\vaultkey-gui.spec")
    Write-Host "[*] Built: $Dist\vaultkey-gui.exe" -ForegroundColor Green
}

# ── SHA256 checksums ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Generating SHA256 checksums..."
Push-Location $Dist
try {
    $HashFile = Join-Path $Dist "SHA256SUMS-windows.txt"
    $files = @("vaultkey-cli.exe", "vaultkey-tui.exe", "vaultkey-gui.exe") |
        Where-Object { Test-Path (Join-Path $Dist $_) }
    $files | ForEach-Object {
        $hash = Get-FileHash -Algorithm SHA256 (Join-Path $Dist $_)
        "$($hash.Hash.ToLower())  $_"
    } | Set-Content $HashFile
    Write-Host "[*] SHA256SUMS-windows.txt written"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " Windows build complete!" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Get-ChildItem $Dist | Select-Object Name, @{N='Size';E={'{0:N0} KB' -f ($_.Length / 1KB)}}
