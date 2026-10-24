#!/usr/bin/env bash
# ==============================================================================
# ArcVault - Linux Build Script
# Builds a portable "onefile" standalone ELF executable for Linux.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "          ArcVault - Linux Build & Packaging              "
echo "=========================================================="

# 1. Locate Python and Virtual Environment
PYTHON_BIN=""
if [ -f ".venv/bin/python3" ]; then
    PYTHON_BIN=".venv/bin/python3"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
else
    echo "[-] Error: Python 3 was not found. Please install Python 3.9+."
    exit 1
fi

echo "[+] Using Python: $($PYTHON_BIN --version 2>&1)"

# 2. Check / Install Dependencies & PyInstaller
if ! $PYTHON_BIN -c "import PyInstaller" &>/dev/null; then
    echo "[*] PyInstaller not detected. Installing..."
    $PYTHON_BIN -m pip install --quiet pyinstaller
fi

# 3. Clean prior build files
echo "[*] Cleaning build/ directory..."
rm -rf build/arcvault build/arcvault_onefile

# 4. Build Portable Onefile Executable
echo "[*] Compiling portable standalone Linux executable (onefile)..."
$PYTHON_BIN -m PyInstaller arcvault_onefile.spec --noconfirm --clean

# 5. Ensure executable permissions
if [ -f "dist/ArcVault" ]; then
    chmod +x "dist/ArcVault"
fi

# 6. Verify 7-Zip CLI availability
echo ""
echo "[*] Checking system 7-Zip installation..."
if command -v 7zz &>/dev/null || command -v 7z &>/dev/null || command -v 7za &>/dev/null; then
    echo "[+] 7-Zip engine detected on host system."
else
    echo "[!] Notice: 7-Zip binary was not found in PATH."
    echo "    To run ArcVault on this machine, install 7-Zip:"
    echo "      Ubuntu/Debian: sudo apt install p7zip-full"
    echo "      Fedora/RHEL:   sudo dnf install p7zip p7zip-plugins"
    echo "      Arch Linux:    sudo pacman -S p7zip"
    echo "    Alternatively, place a standalone '7zz' or '7z' binary next to ArcVault."
fi

# 7. Report outputs
echo ""
echo "=========================================================="
echo "                   Build Successful!                      "
echo "=========================================================="
if [ -f "dist/ArcVault" ]; then
    SIZE=$(ls -lh "dist/ArcVault" | awk '{print $5}')
    echo "[✓] Standalone Portable Executable: dist/ArcVault ($SIZE)"
fi
echo ""
echo "To run the standalone executable:"
echo "  ./dist/ArcVault"
echo "=========================================================="
