@echo off
rem ==============================================================================
rem ArcVault - Windows Build Script (Batch)
rem Builds a portable "onefile" standalone executable (ArcVault.exe).
rem ==============================================================================

setlocal enabledelayedexpansion
title ArcVault Windows Builder

echo ==========================================================
echo          ArcVault - Windows Build ^& Packaging
echo ==========================================================

rem 1. Locate Python executable
set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
    goto :FoundPython
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=py -3"
    goto :FoundPython
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
    goto :FoundPython
)

echo [-] Error: Python was not found in PATH or .venv.
echo     Please install Python 3.9+ from https://www.python.org/
exit /b 1

:FoundPython
echo [+] Using Python command: %PYTHON_CMD%
%PYTHON_CMD% --version

rem 2. Ensure PyInstaller is installed
%PYTHON_CMD% -c "import PyInstaller" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [*] Installing PyInstaller...
    %PYTHON_CMD% -m pip install --quiet pyinstaller
)

rem 3. Clean prior build files
echo [*] Cleaning build directory...
if exist "build\arcvault" rmdir /s /q "build\arcvault"
if exist "build\arcvault_onefile" rmdir /s /q "build\arcvault_onefile"

rem 4. Build Portable Standalone Onefile Executable
echo [*] Compiling portable standalone Windows executable (onefile)...
%PYTHON_CMD% -m PyInstaller arcvault_onefile.spec --noconfirm --clean

if %ERRORLEVEL% neq 0 (
    echo [-] Build failed. Check the error output above.
    exit /b %ERRORLEVEL%
)

rem 5. Report result
echo.
echo ==========================================================
echo                   Build Successful!
echo ==========================================================
if exist "dist\ArcVault.exe" (
    for %%F in ("dist\ArcVault.exe") do set "SIZE=%%~zF bytes"
    echo [✓] Standalone Portable Executable: dist\ArcVault.exe (!SIZE!)
    echo.
    echo Portable Deployment Tip:
    echo   You can copy 'dist\ArcVault.exe' to any folder or USB drive.
    echo   If 7-Zip is not installed globally on the target machine,
    echo   simply copy '7z.exe' and '7z.dll' next to 'ArcVault.exe'.
) else (
    echo [!] Warning: dist\ArcVault.exe not found.
)
echo ==========================================================
echo.
pause
