# ==============================================================================
# ArcVault - Windows PowerShell Build Script
# Builds a portable "onefile" standalone executable (ArcVault.exe).
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "          ArcVault - Windows Build & Packaging            " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Locate Python
$PythonExe = ""
if (Test-Path ".venv\Scripts\python.exe") {
    $PythonExe = (Resolve-Path ".venv\Scripts\python.exe").Path
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
} else {
    Write-Error "Python 3.9+ was not found. Please install Python or set up a virtual environment."
    exit 1
}

Write-Host "[+] Using Python: " -NoNewline -ForegroundColor Green
& $PythonExe --version

# 2. Check / Install PyInstaller
try {
    & $PythonExe -c "import PyInstaller" | Out-Null
} catch {
    Write-Host "[*] Installing PyInstaller..." -ForegroundColor Yellow
    & $PythonExe -m pip install --quiet pyinstaller
}

# 3. Clean previous builds
if ($Clean -or (Test-Path "build")) {
    Write-Host "[*] Cleaning build directory..." -ForegroundColor Yellow
    if (Test-Path "build\arcvault") { Remove-Item -Recurse -Force "build\arcvault" }
    if (Test-Path "build\arcvault_onefile") { Remove-Item -Recurse -Force "build\arcvault_onefile" }
}

# 4. Build Portable Standalone Onefile Executable
Write-Host "[*] Compiling portable standalone Windows executable (onefile)..." -ForegroundColor Yellow
& $PythonExe -m PyInstaller arcvault_onefile.spec --noconfirm --clean

# 5. Verify and display output
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
