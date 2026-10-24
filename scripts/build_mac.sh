#!/usr/bin/env bash
# ==============================================================================
# ArcVault - macOS Build Script
# Builds a portable "onefile" standalone executable and macOS .app bundle.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "          ArcVault - macOS Build & Packaging              "
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

# 2. Check / Install PyInstaller
if ! $PYTHON_BIN -c "import PyInstaller" &>/dev/null; then
    echo "[*] PyInstaller not detected in current environment. Installing..."
    $PYTHON_BIN -m pip install --quiet pyinstaller
fi

# 3. Ensure icon assets are up to date
ICON_PNG="arc_vault/resources/icon.png"
ICON_ICNS="arc_vault/resources/ArcVault.icns"

if [ -f "$ICON_PNG" ] && command -v iconutil &>/dev/null && command -v sips &>/dev/null; then
    if [ ! -f "$ICON_ICNS" ] || [ "$ICON_PNG" -nt "$ICON_ICNS" ]; then
        echo "[*] Regenerating Apple Iconset (ArcVault.icns) from icon.png..."
        TMP_ICONSET="/tmp/ArcVault_build.iconset"
        rm -rf "$TMP_ICONSET"
        mkdir -p "$TMP_ICONSET"
        sips -z 16 16     "$ICON_PNG" --out "$TMP_ICONSET/icon_16x16.png" >/dev/null 2>&1
        sips -z 32 32     "$ICON_PNG" --out "$TMP_ICONSET/icon_16x16@2x.png" >/dev/null 2>&1
        sips -z 32 32     "$ICON_PNG" --out "$TMP_ICONSET/icon_32x32.png" >/dev/null 2>&1
        sips -z 64 64     "$ICON_PNG" --out "$TMP_ICONSET/icon_32x32@2x.png" >/dev/null 2>&1
        sips -z 128 128   "$ICON_PNG" --out "$TMP_ICONSET/icon_128x128.png" >/dev/null 2>&1
        sips -z 256 256   "$ICON_PNG" --out "$TMP_ICONSET/icon_128x128@2x.png" >/dev/null 2>&1
        sips -z 256 256   "$ICON_PNG" --out "$TMP_ICONSET/icon_256x256.png" >/dev/null 2>&1
        sips -z 512 512   "$ICON_PNG" --out "$TMP_ICONSET/icon_256x256@2x.png" >/dev/null 2>&1
        sips -z 512 512   "$ICON_PNG" --out "$TMP_ICONSET/icon_512x512.png" >/dev/null 2>&1
        sips -z 1024 1024 "$ICON_PNG" --out "$TMP_ICONSET/icon_512x512@2x.png" >/dev/null 2>&1
        iconutil -c icns "$TMP_ICONSET" -o "$ICON_ICNS"
        rm -rf "$TMP_ICONSET"
        echo "[+] Updated $ICON_ICNS"
    fi
fi

# 4. Clean prior build files
echo "[*] Cleaning build/ directory..."
rm -rf build/arcvault build/arcvault_onefile

# 5. Build macOS Application Bundle first
echo "[*] Compiling native macOS Application Bundle (ArcVault.app)..."
$PYTHON_BIN -m PyInstaller arcvault.spec --noconfirm --clean

# 6. Build Portable Onefile Executable
echo "[*] Compiling portable standalone executable (onefile)..."
$PYTHON_BIN -m PyInstaller arcvault_onefile.spec --noconfirm

# 7. Ad-hoc code sign for macOS Gatekeeper
if command -v codesign &>/dev/null; then
    echo "[*] Applying ad-hoc signature to executables..."
    if [ -f "dist/ArcVault" ]; then
        codesign --force --sign - "dist/ArcVault" >/dev/null 2>&1 || true
    fi
    if [ -d "dist/ArcVault.app" ]; then
        codesign --force --deep --sign - "dist/ArcVault.app" >/dev/null 2>&1 || true
    fi
fi

# 8. Report outputs
echo ""
echo "=========================================================="
echo "                   Build Successful!                      "
echo "=========================================================="
if [ -f "dist/ArcVault" ]; then
    SIZE=$(ls -lh "dist/ArcVault" | awk '{print $5}')
    echo "[✓] Standalone Portable Executable: dist/ArcVault ($SIZE)"
fi
if [ -d "dist/ArcVault.app" ]; then
    echo "[✓] macOS Application Bundle:      dist/ArcVault.app"
fi
echo ""
echo "To run the standalone portable binary:"
echo "  ./dist/ArcVault"
echo ""
echo "To open the macOS app bundle:"
echo "  open dist/ArcVault.app"
echo "=========================================================="
