# VaultKey — Windows Build Script (PowerShell 7+)
# Produces: dist/vaultkey.exe (CLI), dist/VaultKey.exe (GUI)
# Requirements: Python 3.11+, pip install pyinstaller
#
# Usage:
#   .\build\scripts\build-windows.ps1
#   .\build\scripts\build-windows.ps1 -Target cli
#   .\build\scripts\build-windows.ps1 -Target gui
#   .\build\scripts\build-windows.ps1 -Target all

param(
    [ValidateSet('cli', 'tui', 'gui', 'all')]
    [string]$Target = 'all',
    [switch]$Clean,
    [switch]$NoUPX
)

$ErrorActionPreference = 'Stop'
$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Write-Host "" 
Write-Host "  VaultKey Windows Build Pipeline" -ForegroundColor Cyan
Write-Host "  Target: $Target" -ForegroundColor Gray
Write-Host ""

# Validate environment
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found in PATH. Install Python 3.11+ first."
    exit 1
}

$PythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$PythonVersion -lt [version]"3.11") {
    Write-Error "Python 3.11+ required. Found: $PythonVersion"
    exit 1
}

if (-not (python -c "import PyInstaller" 2>$null; $?)) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    pip install "pyinstaller>=6.0" --quiet
}

if (-not (python -c "import upx" 2>$null; $?) -and -not $NoUPX) {
    Write-Host "UPX not found — binaries will not be compressed. Install UPX for smaller files." -ForegroundColor Yellow
}

# Clean previous builds
if ($Clean -or (Test-Path "$ROOT\dist")) {
    Write-Host "Cleaning previous dist/..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$ROOT\dist" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$ROOT\build\__pycache__" -ErrorAction SilentlyContinue
}

Set-Location $ROOT

function Build-Target {
    param([string]$Name, [string]$SpecFile)
    
    Write-Host "Building $Name..." -ForegroundColor Green
    $startTime = Get-Date
    
    $args = @(
        "--clean",
        "--noconfirm",
        $SpecFile
    )
    if ($NoUPX) { $args += "--noupx" }
    
    python -m PyInstaller @args
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed for $Name (exit code: $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    
    $elapsed = (Get-Date) - $startTime
    Write-Host "  $Name built in $($elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
}

# Generate Windows version info file
$VersionContent = @"
VSVERS1 {
  FILEVERSION 2,0,0,0
  PRODUCTVERSION 2,0,0,0
  FILEFLAGSMASK 0x3fL
  FILEFLAGS 0x0L
  FILEOS 0x40004L
  FILETYPE 0x1L
  FILESUBTYPE 0x0L
  BEGIN
    BLOCK "StringFileInfo"
    BEGIN
      BLOCK "040904B0"
      BEGIN
        VALUE "CompanyName", "VaultKey Contributors"
        VALUE "FileDescription", "VaultKey — Secure API Key Manager"
        VALUE "FileVersion", "2.0.0.0"
        VALUE "InternalName", "vaultkey"
        VALUE "LegalCopyright", "MIT License"
        VALUE "OriginalFilename", "vaultkey.exe"
        VALUE "ProductName", "VaultKey"
        VALUE "ProductVersion", "2.0.0.0"
      END
    END
    BLOCK "VarFileInfo"
    BEGIN
      VALUE "Translation", 0x409, 1200
    END
  END
}
"@
$VersionContent | Out-File -FilePath "$ROOT\build\assets\version.txt" -Encoding UTF8

switch ($Target) {
    'cli' { Build-Target 'CLI' "$ROOT\build\pyinstaller\vaultkey-cli.spec" }
    'tui' { Build-Target 'TUI' "$ROOT\build\pyinstaller\vaultkey-tui.spec" }
    'gui' { Build-Target 'GUI' "$ROOT\build\pyinstaller\vaultkey-gui.spec" }
    'all' {
        Build-Target 'CLI' "$ROOT\build\pyinstaller\vaultkey-cli.spec"
        Build-Target 'TUI' "$ROOT\build\pyinstaller\vaultkey-tui.spec"
        Build-Target 'GUI' "$ROOT\build\pyinstaller\vaultkey-gui.spec"
    }
}

# Rename for clarity + compute hashes
Write-Host ""
Write-Host "Artifacts:" -ForegroundColor Cyan
Get-ChildItem "$ROOT\dist" -Filter "*.exe" | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $sizeKB = [math]::Round($_.Length / 1KB, 0)
    Write-Host "  $($_.Name)  (${sizeKB}KB)" -ForegroundColor White
    Write-Host "  SHA256: $hash" -ForegroundColor Gray
    # Write sidecar
    "$hash  $($_.Name)" | Out-File -FilePath "$ROOT\dist\$($_.BaseName).sha256" -Encoding ASCII
}

Write-Host ""
Write-Host "  Windows build complete." -ForegroundColor Green
