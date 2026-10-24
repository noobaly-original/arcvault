# 🛠️ ArcVault Build & Compilation Guide

This document describes how to compile **ArcVault** into a standalone, distribution-ready executable and macOS application bundle using **PyInstaller**.

---

## 📋 Prerequisites

1. **Python 3.9+** (recommended: Python 3.11 or 3.12)
2. **7-Zip CLI**:
   - **macOS**: `brew install sevenzip` (`7zz` binary)
   - **Linux**: `sudo apt install p7zip-full` (`7z` binary)
   - **Windows**: Install [7-Zip](https://www.7-zip.org/) or [NanaZip](https://github.com/M2Team/NanaZip)
3. **Virtual Environment Tools**: `uv` (recommended) or standard `pip` / `venv`.

---

## 🚀 Step 1: Environment Setup

Clone the repository and create an isolated virtual environment:

```bash
git clone https://github.com/noobaly-original/arcvault.git
cd arcvault

# Recommended: using uv
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install pyinstaller

# Or using standard python:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

---

## 📦 Step 2: Compiling with PyInstaller

### Option A: Using the Included Specification File (Recommended)

ArcVault includes a preconfigured `arcvault.spec` file that handles data bundling, vector icons, Pygments syntax highlighters, and macOS app bundle settings:

```bash
# Activate your virtual environment first
source .venv/bin/activate

# Clean and build the distribution
pyinstaller arcvault.spec --noconfirm --clean
```

Upon completion, your binaries will be in the `dist/` directory:
- **macOS**:
  - `dist/ArcVault.app` (macOS Application Bundle with Retina vector icon)
  - `dist/ArcVault/ArcVault` (Standalone UNIX binary)
- **Linux**:
  - `dist/ArcVault/ArcVault` (Standalone executable)
- **Windows**:
  - `dist\ArcVault\ArcVault.exe` (Standalone Windows executable)

---

### Option B: Compiling from CLI Directly

If you prefer building directly from the command line without the `.spec` file:

#### macOS:
```bash
pyinstaller run.py \
  --name "ArcVault" \
  --windowed \
  --icon "arc_vault/resources/ArcVault.icns" \
  --add-data "arc_vault/resources:arc_vault/resources" \
  --hidden-import "PyQt6.QtCore" \
  --hidden-import "PyQt6.QtGui" \
  --hidden-import "PyQt6.QtWidgets" \
  --hidden-import "pygments" \
  --hidden-import "PIL" \
  --noconfirm --clean
```

#### Windows:
```cmd
pyinstaller run.py ^
  --name "ArcVault" ^
  --windowed ^
  --icon "arc_vault/resources/icon.png" ^
  --add-data "arc_vault/resources;arc_vault/resources" ^
  --hidden-import "PyQt6.QtCore" ^
  --hidden-import "PyQt6.QtGui" ^
  --hidden-import "PyQt6.QtWidgets" ^
  --hidden-import "pygments" ^
  --hidden-import "PIL" ^
  --noconfirm --clean
```

#### Linux:
```bash
pyinstaller run.py \
  --name "ArcVault" \
  --windowed \
  --icon "arc_vault/resources/icon.png" \
  --add-data "arc_vault/resources:arc_vault/resources" \
  --hidden-import "PyQt6.QtCore" \
  --hidden-import "PyQt6.QtGui" \
  --hidden-import "PyQt6.QtWidgets" \
  --hidden-import "pygments" \
  --hidden-import "PIL" \
  --noconfirm --clean
```

---

## 🎨 macOS Icon Generation (Reference)

If you modify `arc_vault/resources/icon.png` and wish to regenerate `ArcVault.icns`:

```bash
mkdir -p /tmp/ArcVault.iconset
sips -z 16 16     arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_16x16.png
sips -z 32 32     arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_16x16@2x.png
sips -z 32 32     arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_32x32.png
sips -z 64 64     arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_32x32@2x.png
sips -z 128 128   arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_128x128.png
sips -z 256 256   arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_128x128@2x.png
sips -z 256 256   arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_256x256.png
sips -z 512 512   arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_256x256@2x.png
sips -z 512 512   arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_512x512.png
sips -z 1024 1024 arc_vault/resources/icon.png --out /tmp/ArcVault.iconset/icon_512x512@2x.png
iconutil -c icns /tmp/ArcVault.iconset -o arc_vault/resources/ArcVault.icns
rm -rf /tmp/ArcVault.iconset
```

---

## 🏃 Running the Compiled Binary

### macOS:
```bash
open dist/ArcVault.app
# Or run binary directly from terminal:
./dist/ArcVault/ArcVault
```

### Linux:
```bash
./dist/ArcVault/ArcVault
```

### Windows:
```cmd
dist\ArcVault\ArcVault.exe
```

---

## 🧪 Testing

To ensure all unit tests pass before compiling:

```bash
.venv/bin/python3 -m unittest discover tests -v
```
