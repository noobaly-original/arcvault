# 🛠️ Vaultables Build & Compilation Guide

This document describes how to compile **Vaultables** into portable **"onefile" standalone executables** and native application bundles across **macOS**, **Windows**, and **Linux** using **PyInstaller**.

---

## ⚡ Quick Start: 1-Click Platform Build Scripts

Vaultables includes self-sufficient build scripts in the root directory (and mirrored in `scripts/`). Each script automatically creates a `.venv` virtual environment if missing, upgrades pip, installs all dependencies from `requirements.txt`, synchronizes icons, and builds the distribution:

### 🍎 macOS (Apple Silicon & Intel)
```bash
chmod +x build_mac.sh
./build_mac.sh
```
- **Automatically**:
  - Initializes `.venv` and installs `requirements.txt`.
  - Regenerates `Vaultables.icns` and `Vaultables.ico` if `icon.png` is updated.
  - Builds `dist/Vaultables` (portable standalone binary) and `dist/Vaultables.app` (macOS Application Bundle).
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
  - Synchronizes multi-resolution `Vaultables.ico` (16x16 to 256x256).
  - Builds `dist\Vaultables.exe` with embedded icon resources.
- **USB / Portable Tip**: You can carry `Vaultables.exe` on a USB drive. If 7-Zip is not installed on the host machine, simply drop `7z.exe` and `7z.dll` next to `Vaultables.exe`.

### 🐧 Linux (x86_64 & aarch64)
```bash
chmod +x build_linux.sh
./build_linux.sh
```
- **Automatically**:
  - Initializes `.venv` and installs `requirements.txt`.
  - Builds `dist/Vaultables` (portable standalone ELF binary).

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
git clone https://github.com/noobaly-original/vaultables.git
cd vaultables

# Setup virtual environment and dependencies:
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

### Step 2: Compiling with Spec Files

Vaultables provides two specification files:

#### 1. Portable Single-File Executable (`vaultables_onefile.spec`)
Packs Python, PyQt6, Pillow, Pygments, and all graphics assets into a single self-extracting executable:
```bash
pyinstaller vaultables_onefile.spec --noconfirm --clean
```
Output:
- **macOS / Linux**: `dist/Vaultables`
- **Windows**: `dist\Vaultables.exe`

#### 2. Native macOS Directory / App Bundle (`vaultables.spec`)
Builds a standard native macOS bundle (`dist/Vaultables.app`):
```bash
pyinstaller vaultables.spec --noconfirm --clean
```

---

## 🎨 Icon Generation (Reference)

### macOS (.icns):
```bash
mkdir -p /tmp/Vaultables.iconset
sips -z 16 16     vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_16x16.png
sips -z 32 32     vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_16x16@2x.png
sips -z 32 32     vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_32x32.png
sips -z 64 64     vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_32x32@2x.png
sips -z 128 128   vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_128x128.png
sips -z 256 256   vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_128x128@2x.png
sips -z 256 256   vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_256x256.png
sips -z 512 512   vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_256x256@2x.png
sips -z 512 512   vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_512x512.png
sips -z 1024 1024 vaultables/resources/icon.png --out /tmp/Vaultables.iconset/icon_512x512@2x.png
iconutil -c icns /tmp/Vaultables.iconset -o vaultables/resources/Vaultables.icns
rm -rf /tmp/Vaultables.iconset
```

### Windows (.ico):
```bash
python -c "from PIL import Image; Image.open('vaultables/resources/icon.png').save('vaultables/resources/Vaultables.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```

---

## 🏃 Running the Compiled Binary

### macOS:
```bash
# Run the portable standalone binary:
./dist/Vaultables

# Or launch the macOS app bundle:
open dist/Vaultables.app
```

### Linux:
```bash
./dist/Vaultables
```

### Windows:
Double-click `dist\Vaultables.exe` or execute from Command Prompt / PowerShell:
```cmd
.\dist\Vaultables.exe
```

---

## 🔍 CLI Inspection
The portable binary also supports command-line flags:
```bash
./dist/Vaultables --version
./dist/Vaultables --help
```

---

## 🚀 Automated Multi-Platform GitHub Releases (CI/CD)

Vaultables includes a turnkey GitHub Actions workflow (`.github/workflows/release.yml`) that compiles native binaries across all major platforms and architectures on cloud runners:

- **Windows x64 (AMD64)**: `Vaultables-Windows-x64.exe`
- **Linux x64 (AMD64)**: `Vaultables-Linux-x64` & `Vaultables-Linux-x64.tar.gz`
- **macOS Apple Silicon (ARM64)**: `Vaultables-macOS-arm64` & `Vaultables-macOS-arm64.app.zip`
- **macOS Intel (x86_64 / AMD64)**: `Vaultables-macOS-x86_64` & `Vaultables-macOS-x86_64.app.zip`
- **SHA256 Checksums**: `SHA256SUMS.txt`

### To Trigger an Automated Release:
Push any version tag starting with `v`:
```bash
git tag v2.0.0
git push origin v2.0.0
```
Or manually trigger the workflow from your browser in the **Actions** tab on GitHub via **Run workflow**.
