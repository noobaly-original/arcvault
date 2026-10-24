# ==============================================================================
# ArcVault - Windows PowerShell Build Script
# Builds a portable "onefile" standalone executable (ArcVault.exe).
# Automatically sets up .venv and installs requirements.txt.
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "          ArcVault - Windows Build & Packaging            " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check for uv or host Python
$HasUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)
$HostPython = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    $HostPython = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $HostPython = "python"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $HostPython = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    Write-Error "Python 3.9+ was not found. Please install Python from https://www.python.org/"
    exit 1
}

# 2. Setup / Use Virtual Environment
if (-not (Test-Path ".venv")) {
    Write-Host "[*] Virtual environment not found. Creating .venv..." -ForegroundColor Yellow
    if ($HasUv) {
        uv venv .venv
    } else {
        & $HostPython -m venv .venv
    }
}

$PythonExe = ""
if (Test-Path ".venv\Scripts\python.exe") {
    $PythonExe = (Resolve-Path ".venv\Scripts\python.exe").Path
} else {
    $PythonExe = $HostPython
}

Write-Host "[+] Using Python: " -NoNewline -ForegroundColor Green
& $PythonExe --version

# 3. Always install / sync dependencies from requirements.txt
Write-Host "[*] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
if ($HasUv) {
    uv pip install -r requirements.txt --python $PythonExe --quiet
} else {
    try { & $PythonExe -m pip --version | Out-Null } catch { & $PythonExe -m ensurepip --upgrade | Out-Null }
    & $PythonExe -m pip install --quiet -r requirements.txt
}

# 4. Ensure Windows .ico icon is up to date
if (Test-Path "arc_vault\resources\icon.png") {
    & $PythonExe -c "from PIL import Image; from pathlib import Path; p = Path('arc_vault/resources/icon.png'); i = Path('arc_vault/resources/ArcVault.ico'); (not i.exists() or p.stat().st_mtime > i.stat().st_mtime) and Image.open(p).save(i, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>$null
}

# 5. Clean previous builds
if ($Clean -or (Test-Path "build")) {
    Write-Host "[*] Cleaning build directory..." -ForegroundColor Yellow
    if (Test-Path "build\arcvault") { Remove-Item -Recurse -Force "build\arcvault" }
    if (Test-Path "build\arcvault_onefile") { Remove-Item -Recurse -Force "build\arcvault_onefile" }
}

# 6. Build Portable Standalone Onefile Executable with .ico embedding
Write-Host "[*] Compiling portable standalone Windows executable with ArcVault.ico..." -ForegroundColor Yellow
& $PythonExe -m PyInstaller arcvault_onefile.spec --noconfirm --clean

# 7. Verify and display output
$OutputExe = "dist\ArcVault.exe"
if (Test-Path $OutputExe) {
    $Item = Get-Item $OutputExe
    $SizeMB = [math]::Round($Item.Length / 1MB, 2)
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "                   Build Successful!                      " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "[✓] Standalone Portable Executable: $OutputExe ($SizeMB MB)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Portable Deployment Tip:" -ForegroundColor Gray
    Write-Host "  You can copy '$OutputExe' to any folder or USB drive." -ForegroundColor Gray
    Write-Host "  If 7-Zip is not installed globally on the target machine," -ForegroundColor Gray
    Write-Host "  simply copy '7z.exe' and '7z.dll' next to 'ArcVault.exe'." -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Error "Build finished but $OutputExe was not found."
}
