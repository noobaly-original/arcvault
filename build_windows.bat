@echo off
rem ==============================================================================
rem ArcVault - Windows Build Script (Batch)
rem Builds a portable "onefile" standalone executable (ArcVault.exe).
rem Automatically sets up .venv and installs requirements.txt.
rem ==============================================================================

setlocal enabledelayedexpansion
title ArcVault Windows Builder

echo ==========================================================
echo          ArcVault - Windows Build ^& Packaging
echo ==========================================================

rem 1. Locate host Python or uv
set "HOST_PYTHON="
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "HAS_UV=1"
) else (
    set "HAS_UV=0"
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "HOST_PYTHON=py -3"
    goto :FoundHost
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "HOST_PYTHON=python"
    goto :FoundHost
)

if exist ".venv\Scripts\python.exe" (
    set "HOST_PYTHON=.venv\Scripts\python.exe"
    goto :FoundHost
)

echo [-] Error: Python was not found in PATH or system.
echo     Please install Python 3.9+ from https://www.python.org/
exit /b 1

:FoundHost
rem 2. Setup / Use Virtual Environment
if not exist ".venv" (
    echo [*] Virtual environment not found. Creating .venv...
    if "%HAS_UV%"=="1" (
        uv venv .venv
    ) else (
        %HOST_PYTHON% -m venv .venv
    )
)

set "PYTHON_CMD=.venv\Scripts\python.exe"
if not exist "%PYTHON_CMD%" (
    set "PYTHON_CMD=%HOST_PYTHON%"
)

echo [+] Using Python: %PYTHON_CMD%
%PYTHON_CMD% --version

rem 3. Always install / sync dependencies from requirements.txt
echo [*] Installing dependencies from requirements.txt...
if "%HAS_UV%"=="1" (
    uv pip install -r requirements.txt --python "%PYTHON_CMD%" --quiet
) else (
    %PYTHON_CMD% -m pip --version >nul 2>nul || %PYTHON_CMD% -m ensurepip --upgrade >nul 2>nul
    %PYTHON_CMD% -m pip install --quiet -r requirements.txt
)

rem 4. Ensure Windows .ico icon is up to date
if exist "arc_vault\resources\icon.png" (
    %PYTHON_CMD% -c "from PIL import Image; from pathlib import Path; p = Path('arc_vault/resources/icon.png'); i = Path('arc_vault/resources/ArcVault.ico'); (not i.exists() or p.stat().st_mtime > i.stat().st_mtime) and Image.open(p).save(i, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])" >nul 2>nul
)

rem 5. Clean prior build files
echo [*] Cleaning build directory...
if exist "build\arcvault" rmdir /s /q "build\arcvault"
if exist "build\arcvault_onefile" rmdir /s /q "build\arcvault_onefile"

rem 6. Build Portable Standalone Onefile Executable with .ico embedding
echo [*] Compiling portable standalone Windows executable with ArcVault.ico...
%PYTHON_CMD% -m PyInstaller arcvault_onefile.spec --noconfirm --clean

if %ERRORLEVEL% neq 0 (
    echo [-] Build failed. Check the error output above.
    exit /b %ERRORLEVEL%
)

rem 7. Report result
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
