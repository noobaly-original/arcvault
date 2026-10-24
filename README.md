# 🛡️ ArcVault

**ArcVault** is a fast, lightweight, and cross-platform encrypted archive explorer, editor, and vault utility.

Unlike traditional vault systems (such as Cryptomator) that rely on kernel virtual drive drivers (MacFUSE, WinFsp, or WebDAV loops), **ArcVault** takes a clean, file-centric approach:
- Your vault is simply a standard folder on your disk.
- Inside the vault root, top-level directories are stored directly as **AES-256 encrypted `.7z` archives** (termed *Entry Points*, such as `photos.7z`, `documents.7z`, `finances.7z`).
- **Complete Vendor Freedom**: If ArcVault is not installed, you can simply open any of the `.7z` files directly using **7-Zip, NanaZip, Keka, or PeaZip** on Windows, macOS, or Linux!

---

## ✨ Features

- **Blazing Fast & Lightweight**: Zero background mount daemons, zero kernel drivers.
- **AES-256 Header Encryption**: All archive headers (`-mhe=on`) are encrypted. File names and directory hierarchies cannot be seen without the master password.
- **Fast & Reliable Archive Editing**:
  - **In-App Direct Editing**: Edit text, notes, JSON, scripts, and code files directly in the preview panel with `Save` (Ctrl+S / Cmd+S). The app immediately stages and updates the `.7z` archive using 7-Zip's multithreaded fast update engine.
  - **External Editor Auto-Sync**: Right-click any file and select *Edit in External App...* (or click the button in Preview). ArcVault extracts the file to a secure watched staging area with `QFileSystemWatcher`. Whenever you hit save in your external editor (VS Code, TextEdit, Notepad, GIMP, etc.), ArcVault detects the change and automatically re-encrypts the updated file back into the `.7z` archive!
- **Cross-Platform Drag-and-Drop**:
  - **Drop onto Folders**: Dragging external files from Finder / Explorer and dropping them directly onto a subfolder row in the table automatically encrypts and adds them into that specific nested directory.
  - **Drop onto Sidebar Entry Points**: Drag files directly onto any `.7z` archive listed in the sidebar to add them to that entry point.
  - **Vault Root Drop Routing**: Dropping files at the vault root allows instant selection or creation of an entry point.
  - **Drag to Export**: Click and drag any file or group of files from ArcVault out to your Desktop or Finder to automatically decrypt and export them.
- **Entry-Point Vault Architecture**:
  - The vault root houses encrypted category entry points (`photos.7z`, `documents.7z`, etc.).
  - Navigating into an entry point seamlessly explores all nested directories and files inside.
- **Rich Previews**:
  - **Text & Code**: Syntax-highlighted viewer (powered by Pygments) for Python, JavaScript, JSON, Markdown, HTML, CSS, C/C++, Rust, Shell scripts, etc.
  - **Images**: High-resolution image viewer with zoom controls, smooth scaling, and dimension badges (PNG, JPG, WebP, GIF, SVG, BMP, ICO).
  - **Executables & Binaries**: Clear metadata cards with compression ratios, CRC32 checksums, and distinct badges.
- **Specialized Vector Icons**:
  - Crisp vector SVG icons rendered at native display resolution.
  - Distinctive badges and icons for **Windows executables** (`.exe`, `.bat`, `.cmd`, `.msi`), **macOS bundles** (`.app`, `.dmg`, `.pkg`), and **Unix/Linux scripts** (`.sh`, `.bin`, `.elf`).
- **Minimalistic & Modern UI**:
  - Dual-mode theme engine with instant **Light Mode** and **Dark Mode** toggle.
  - Interactive breadcrumb navigation bar (`Vault Root › photos › family`).
  - Real-time search and filter bar.
- **Cryptomator-Style Vault Switcher**:
  - Easily manage, add, create, or switch between multiple vaults in the left sidebar.
  - Secure in-memory password caching during session (purged immediately on Lock or App Close).

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.9+
- 7-Zip CLI (`7zz`, `7z`, or `nanazip`):
  - **macOS**: `brew install sevenzip`
  - **Linux**: `sudo apt install p7zip-full` or `sudo dnf install p7zip`
  - **Windows**: Install 7-Zip or NanaZip.

### 2. Installation
Clone this repository and install dependencies:
```bash
git clone https://github.com/your-username/archive-explorer.git
cd archive-explorer

# Using uv (fastest):
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Or using standard pip:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Launching ArcVault
```bash
./run.py
# or
python3 run.py
```

---

## 📁 Vault Structure Explained

When ArcVault creates a vault named "Personal Vault", the filesystem folder looks like this:

```text
Personal Vault/
├── .arcvault            # Small JSON vault descriptor (ID, name, metadata)
├── .vault_check.7z      # Micro-archive for instantaneous password validation
├── photos.7z            # Entry Point: Houses photos, nested albums, etc.
├── documents.7z         # Entry Point: Houses PDFs, spreadsheets, notes
└── work.7z              # Entry Point: Houses code projects, assets
```

Inside `photos.7z`, files are organized with full directory hierarchy:
```text
photos.7z
├── family/
│   ├── vacation_2026.jpg
│   └── birthday.png
└── landscape.png
```

You can double-click `photos.7z` in Finder or Explorer, type your password in 7-Zip/Keka/NanaZip, and extract or view files at any time, even without ArcVault!

---

## 🧪 Running Tests

The test suite covers backend encryption, fast archive editing, password validation, archive manipulations, and headless GUI components:

```bash
python3 -m unittest discover tests
```

---

## 🔒 Security Model

- **Encryption**: AES-256 with 7z header encryption (`-mhe=on`), preventing enumeration of file names, timestamps, or folder structures without the master key.
- **Memory Safety**: Passwords are held strictly in process memory while the vault is unlocked, and cleared as soon as the user clicks "Lock" or closes the app.
- **Preview Isolation**: Preview extractions take place in temporary, permission-restricted directories and are removed on lock or exit.
