#!/usr/bin/env bash
# ==============================================================================
# Vaultables - Linux Build Script
# Builds a portable "onefile" standalone ELF executable for Linux.
# Automatically sets up .venv and installs requirements.txt.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "          Vaultables - Linux Build & Packaging              "
echo "=========================================================="

# 1. Locate Host Python 3
SYSTEM_PYTHON=""
if command -v python3 &>/dev/null; then
    SYSTEM_PYTHON="python3"
elif command -v python &>/dev/null; then
    SYSTEM_PYTHON="python"
else
    echo "[-] Error: Python 3 was not found. Please install Python 3.9+."
    exit 1
fi

# 2. Setup / Use Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[*] Virtual environment not found. Creating .venv..."
    if command -v uv &>/dev/null; then
        uv venv .venv
    else
        $SYSTEM_PYTHON -m venv .venv
    fi
fi

PYTHON_BIN=".venv/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

echo "[+] Using Python: $($PYTHON_BIN --version 2>&1)"

# 3. Always install / sync dependencies from requirements.txt
echo "[*] Installing dependencies from requirements.txt..."
if command -v uv &>/dev/null; then
    uv pip install -r requirements.txt --python "$PYTHON_BIN" --quiet
elif $PYTHON_BIN -m pip --version &>/dev/null; then
    $PYTHON_BIN -m pip install --quiet -r requirements.txt
else
    $PYTHON_BIN -m ensurepip --upgrade 2>/dev/null || true
    $PYTHON_BIN -m pip install --quiet -r requirements.txt
fi

# 4. Clean prior build files
echo "[*] Cleaning build/ directory..."
rm -rf build/vaultables build/vaultables_onefile

# 5. Build Portable Onefile Executable
echo "[*] Compiling portable standalone Linux executable (onefile)..."
$PYTHON_BIN -m PyInstaller vaultables_onefile.spec --noconfirm --clean

# 6. Ensure executable permissions
if [ -f "dist/Vaultables" ]; then
    chmod +x "dist/Vaultables"
fi

# 7. Verify 7-Zip CLI availability
echo ""
echo "[*] Checking system 7-Zip installation..."
if command -v 7zz &>/dev/null || command -v 7z &>/dev/null || command -v 7za &>/dev/null; then
    echo "[+] 7-Zip engine detected on host system."
else
    echo "[!] Notice: 7-Zip binary was not found in PATH."
    echo "    To run Vaultables on this machine, install 7-Zip:"
    echo "      Ubuntu/Debian: sudo apt install p7zip-full"
    echo "      Fedora/RHEL:   sudo dnf install p7zip p7zip-plugins"
    echo "      Arch Linux:    sudo pacman -S p7zip"
    echo "    Alternatively, place a standalone '7zz' or '7z' binary next to Vaultables."
fi

# 8. Report outputs
echo ""
echo "=========================================================="
echo "                   Build Successful!                      "
echo "=========================================================="
if [ -f "dist/Vaultables" ]; then
    SIZE=$(ls -lh "dist/Vaultables" | awk '{print $5}')
    echo "[OK] Standalone Portable Executable: dist/Vaultables ($SIZE)"
fi
echo ""
echo "To run the standalone executable:"
echo "  ./dist/Vaultables"
echo "=========================================================="
