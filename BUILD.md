# 🛠️ ArcVault Build & Compilation Guide

This document describes how to compile **ArcVault** into portable **"onefile" standalone executables** and native application bundles across **macOS**, **Windows**, and **Linux** using **PyInstaller**.

---

## ⚡ Quick Start: 1-Click Platform Build Scripts

ArcVault includes self-sufficient build scripts in the root directory (and mirrored in `scripts/`). Each script automatically creates a `.venv` virtual environment if missing, upgrades pip, installs all dependencies from `requirements.txt`, synchronizes icons, and builds the distribution:

### 🍎 macOS (Apple Silicon & Intel)
```bash
chmod +x build_mac.sh
./build_mac.sh
```
- **Automatically**:
  - Initializes `.venv` and installs `requirements.txt`.
  - Regenerates `ArcVault.icns` and `ArcVault.ico` if `icon.png` is updated.
  - Builds `dist/ArcVault` (portable standalone binary) and `dist/ArcVault.app` (macOS Application Bundle).
  - Signs with ad-hoc certificates for macOS Gatekeeper.

### 🪟 Windows (x64)
In Command Prompt (`cmd.exe`):
```cmd
build_windows.bat
```
Or in PowerShell:
```powershell
.\build_windows.ps1
```
- **Automatically**:
  - Initializes `.venv` and installs `requirements.txt`.
  - Synchronizes multi-resolution `ArcVault.ico` (16x16 to 256x256).
  - Builds `dist\ArcVault.exe` with embedded icon resources.
- **USB / Portable Tip**: You can carry `ArcVault.exe` on a USB drive. If 7-Zip is not installed on the host machine, simply drop `7z.exe` and `7z.dll` next to `ArcVault.exe`.

### 🐧 Linux (x86_64 & aarch64)
```bash
chmod +x build_linux.sh
./build_linux.sh
```
- **Automatically**:
  - Initializes `.venv` and installs `requirements.txt`.
  - Builds `dist/ArcVault` (portable standalone ELF binary).

---

## 📋 Prerequisites

1. **Python 3.9+** (recommended: Python 3.11 or 3.12)
2. **7-Zip CLI**:
   - **macOS**: `brew install sevenzip` (`7zz` binary)
   - **Linux**: `sudo apt install p7zip-full` (`7z` binary)
   - **Windows**: Install [7-Zip](https://www.7-zip.org/) or [NanaZip](https://github.com/M2Team/NanaZip)

---

## 🚀 Manual Build Guide

### Step 1: Virtual Environment Setup

```bash
git clone https://github.com/noobaly-original/arcvault.git
cd arcvault

# Setup virtual environment and dependencies:
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

### Step 2: Compiling with Spec Files

ArcVault provides two specification files:

#### 1. Portable Single-File Executable (`arcvault_onefile.spec`)
Packs Python, PyQt6, Pillow, Pygments, and all graphics assets into a single self-extracting executable:
```bash
pyinstaller arcvault_onefile.spec --noconfirm --clean
```
Output:
- **macOS / Linux**: `dist/ArcVault`
- **Windows**: `dist\ArcVault.exe`

#### 2. Native macOS Directory / App Bundle (`arcvault.spec`)
Builds a standard native macOS bundle (`dist/ArcVault.app`):
```bash
pyinstaller arcvault.spec --noconfirm --clean
```

---

## 🎨 Icon Generation (Reference)

### macOS (.icns):
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

### Windows (.ico):
```bash
python -c "from PIL import Image; Image.open('arc_vault/resources/icon.png').save('arc_vault/resources/ArcVault.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```

---

## 🏃 Running the Compiled Binary

### macOS:
```bash
# Run the portable standalone binary:
./dist/ArcVault

# Or launch the macOS app bundle:
open dist/ArcVault.app
```

### Linux:
```bash
./dist/ArcVault
```

### Windows:
Double-click `dist\ArcVault.exe` or execute from Command Prompt / PowerShell:
```cmd
.\dist\ArcVault.exe
```

---

## 🔍 CLI Inspection
The portable binary also supports command-line flags:
```bash
./dist/ArcVault --version
./dist/ArcVault --help
```
