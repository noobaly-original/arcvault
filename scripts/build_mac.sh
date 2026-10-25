#!/usr/bin/env bash
# ==============================================================================
# Vaultables - macOS Build Script
# Builds a portable "onefile" standalone executable and macOS .app bundle.
# Automatically sets up .venv and installs requirements.txt.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "          Vaultables - macOS Build & Packaging              "
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

# 4. Ensure icon assets (icns & ico) are up to date from icon.png
ICON_PNG="vaultables/resources/icon.png"
ICON_ICNS="vaultables/resources/Vaultables.icns"
ICON_ICO="vaultables/resources/Vaultables.ico"

if [ -f "$ICON_PNG" ]; then
    # Generate macOS .icns if needed
    if command -v iconutil &>/dev/null && command -v sips &>/dev/null; then
        if [ ! -f "$ICON_ICNS" ] || [ "$ICON_PNG" -nt "$ICON_ICNS" ]; then
            echo "[*] Regenerating Apple Iconset (Vaultables.icns) from icon.png..."
            TMP_ICONSET="/tmp/Vaultables_build.iconset"
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

    # Generate Windows .ico if needed
    if [ ! -f "$ICON_ICO" ] || [ "$ICON_PNG" -nt "$ICON_ICO" ]; then
        $PYTHON_BIN -c "from PIL import Image; Image.open('$ICON_PNG').save('$ICON_ICO', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>/dev/null || true
    fi
fi

# 5. Clean prior build files
echo "[*] Cleaning build/ directory..."
rm -rf build/vaultables build/vaultables_onefile

# 6. Build macOS Application Bundle first
echo "[*] Compiling native macOS Application Bundle (Vaultables.app)..."
$PYTHON_BIN -m PyInstaller vaultables.spec --noconfirm --clean

# 7. Build Portable Onefile Executable
echo "[*] Compiling portable standalone executable (onefile)..."
$PYTHON_BIN -m PyInstaller vaultables_onefile.spec --noconfirm

# 8. Ad-hoc code sign for macOS Gatekeeper
if command -v codesign &>/dev/null; then
    echo "[*] Applying ad-hoc signature to executables..."
    if [ -f "dist/Vaultables" ]; then
        codesign --force --sign - "dist/Vaultables" >/dev/null 2>&1 || true
    fi
    if [ -d "dist/Vaultables.app" ]; then
        codesign --force --deep --sign - "dist/Vaultables.app" >/dev/null 2>&1 || true
    fi
fi

# 9. Report outputs
echo ""
echo "=========================================================="
echo "                   Build Successful!                      "
echo "=========================================================="
if [ -f "dist/Vaultables" ]; then
    SIZE=$(ls -lh "dist/Vaultables" | awk '{print $5}')
    echo "[OK] Standalone Portable Executable: dist/Vaultables ($SIZE)"
fi
if [ -d "dist/Vaultables.app" ]; then
    echo "[OK] macOS Application Bundle:      dist/Vaultables.app"
fi
echo ""
echo "To run the standalone portable binary:"
echo "  ./dist/Vaultables"
echo ""
echo "To open the macOS app bundle:"
echo "  open dist/Vaultables.app"
echo "=========================================================="
