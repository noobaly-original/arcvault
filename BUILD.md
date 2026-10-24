# 🛠️ ArcVault Build & Compilation Guide

This document describes how to compile **ArcVault** into portable **"onefile" standalone executables** and native application bundles across **macOS**, **Windows**, and **Linux** using **PyInstaller**.

---

## ⚡ Quick Start: 1-Click Platform Build Scripts

ArcVault includes automated build scripts located in the root directory (and mirrored in `scripts/`) that set up dependencies, compile portable standalone binaries, configure Retina icons, and sign binaries:

### 🍎 macOS (Apple Silicon & Intel)
```bash
chmod +x build_mac.sh
./build_mac.sh
```
- Produces:
  - `dist/ArcVault` — Standalone portable onefile binary (can be run directly or copied anywhere).
  - `dist/ArcVault.app` — Native macOS Application Bundle.

### 🪟 Windows (x64)
In Command Prompt (`cmd.exe`):
```cmd
build_windows.bat
```
Or in PowerShell:
```powershell
.\build_windows.ps1
```
- Produces:
  - `dist\ArcVault.exe` — Standalone portable onefile Windows executable.
- **USB / Portable Tip**: You can carry `ArcVault.exe` on a USB drive. If 7-Zip is not installed on the host machine, simply drop `7z.exe` and `7z.dll` next to `ArcVault.exe`.

### 🐧 Linux (x86_64 & aarch64)
```bash
chmod +x build_linux.sh
./build_linux.sh
```
- Produces:
  - `dist/ArcVault` — Standalone portable onefile ELF binary.

---

## 📋 Prerequisites

1. **Python 3.9+** (recommended: Python 3.11 or 3.12)
2. **7-Zip CLI**:
   - **macOS**: `brew install sevenzip` (`7zz` binary)
   - **Linux**: `sudo apt install p7zip-full` (`7z` binary)
   - **Windows**: Install [7-Zip](https://www.7-zip.org/) or [NanaZip](https://github.com/M2Team/NanaZip)
3. **Virtual Environment Tools**: `uv` (recommended) or standard `pip` / `venv`.

---

## 🚀 Manual Build Guide

### Step 1: Virtual Environment Setup

```bash
git clone https://github.com/noobaly-original/arcvault.git
cd arcvault

# Using uv (fast):
uv venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
uv pip install pyinstaller

# Or using standard python:
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
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
