# 🛡️ ArcVault

**ArcVault** is a fast, lightweight, and cross-platform encrypted archive explorer, editor, and vault utility.

Unlike traditional vault systems (such as Cryptomator) that rely on complex virtual drive drivers (MacFUSE, WinFsp, or WebDAV loops), **ArcVault** takes a clean, file-centric approach:
- Your vault is simply a standard folder on your disk or cloud sync folder (Google Drive, MEGA, Dropbox, OneDrive).
- The vault uses a **decoupled, chunked storage architecture (V2)** where virtual folder entry points house encrypted metadata, while file contents are stored in uncompressed, store-mode AES-256 encrypted chunks under `arc-data/`.
- **Zero Re-Archiving Overhead**: Adding or deleting a file never rewrites existing archive contents.
- **Complete Vendor Freedom**: All encrypted chunks are standard 7-Zip archives with AES-256 header encryption (`-mhe=on`). You can inspect or extract any chunk directly using **7-Zip, NanaZip, Keka, or PeaZip** on Windows, macOS, or Linux!

---

## ✨ Features

- **Blazing Fast Store-Mode Encryption**: Bypasses CPU-heavy compression (`-mx=0`) while enforcing maximum AES-256 header and data encryption (`-mhe=on`), achieving native SSD throughput (500+ MB/s).
- **Decoupled Virtual Entry Points & `arc-data/`**:
  - Top-level archives (`photos.7z`, `documents.7z`) act as **virtual folders** holding lightweight AES-256 encrypted metadata.
  - Actual contents are organized under `arc-data/{random_ep_id}/{random_item_id}/`.
  - Adding or deleting an item updates only that item's directory and a ~1 KB metadata archive, taking milliseconds instead of minutes.
  - Moving and renaming files or folders are instant metadata operations with zero disk re-writing.
- **Large File 1 GB Chunk Shredding**:
  - Files $> 1\text{ GB}$ are automatically sliced into $1\text{ GB}$ encrypted chunks (`chunk_000.7z`, `chunk_001.7z`, etc.).
  - Files $\le 1\text{ GB}$ skip shredding and are stored directly in a single `chunk_000.7z`.
  - Multi-chunk export uses streaming $1\text{ MB}$ buffers, keeping RAM consumption under $50\text{ MB}$ regardless of file size.
  - Safeguard: Files $> 1\text{ GB}$ have preview and external editing disabled to protect system memory and disk, with export remaining fully functional.
- **Cloud Storage Friendly & Atomic Swaps**:
  - Metadata saves are staged in isolated temp storage and atomically committed with `os.replace`, completely preventing file-lock sharing violations with Google Drive, MEGA, OneDrive, or Dropbox sync daemons.
  - Version fallback backups (`.{entry_point}.bak`) are automatically retained and used if an archive is ever corrupted.
- **Deep Recursive Multi-Archive Search**:
  - Search across all virtual entry points and nested subfolders simultaneously in milliseconds.
  - Flexible scope selection: **Entire Vault (Recursive)**, **Current Archive (Recursive)**, or **Current Folder**.
  - Supports wildcard patterns (`*.png`, `*report*`, `invoice_??.pdf`) and substring text matching.
  - Dynamic **Location** column indicates archive origin and folder path for every result (`photos.7z / family/summer`).
  - Right-click **Reveal in Vault Folder** or double-click to immediately jump and select the item inside its native directory tree.
  - Keyboard shortcut: `Cmd+F` (macOS) or `Ctrl+F` (Windows/Linux) to instantly focus search.
- **Retina & High-DPI Display Support**:
  - Vector SVG icon engine populates standard and Retina (2x/3x) pixmaps with full antialiasing and smooth transformations, ensuring crisp rendering on MacBooks, Retina screens, and 4K monitors.
- **Fast & Reliable In-App & External Editing**:
  - **In-App Direct Editing**: Edit text, notes, JSON, and code files directly in the preview panel with `Save` (Ctrl+S / Cmd+S).
  - **External Editor Auto-Sync**: Right-click any file and select *Edit with Default App*. ArcVault extracts the file to a secure staging area watched with `QFileSystemWatcher`. Saving in your external editor (VS Code, TextEdit, Notepad) immediately updates the encrypted vault.
- **Cross-Platform Drag-and-Drop**:
  - **Drop onto Folders**: Dragging external files from Finder / Explorer and dropping them directly onto a subfolder row in the table encrypts and adds them into that specific directory.
  - **Drop Folders**: Dragging entire folders adds the directory hierarchy into the vault.
  - **Drag to Export**: Drag any file or selection from ArcVault out to your Desktop or Finder to automatically decrypt and export it.
- **Rich Previews**:
  - **Text & Code**: Syntax-highlighted viewer (powered by Pygments) for Python, JavaScript, JSON, Markdown, HTML, CSS, C/C++, Rust, Shell scripts, etc.
  - **Images**: High-resolution image viewer with zoom controls, smooth scaling, and dimension badges (PNG, JPG, WebP, GIF, SVG, BMP, ICO).
  - **Executables & Binaries**: Clear metadata cards with distinct badges and vector icons for **Windows executables** (`.exe`, `.bat`, `.cmd`), **macOS bundles** (`.app`, `.dmg`, `.pkg`), and **Unix/Linux binaries** (`.sh`, `.bin`).
- **Real-Time Logs Panel**:
  - Built-in logging drawer capturing application events and 7-Zip CLI execution with automatic password masking (`-p***`).
- **Minimalistic & Modern Dual-Mode UI**:
  - Dual-mode theme engine with instant **Light Mode** and **Dark Mode** toggle.
  - Window placement, size, splitters, and theme preference persist across restarts.
  - Interactive breadcrumb navigation bar (`Vault Root › photos › family`).
  - Real-time search and filter bar.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.9+
- 7-Zip CLI (`7zz`, `7z`, or `nanazip`):
  - **macOS**: `brew install sevenzip`
  - **Linux**: `sudo apt install p7zip-full` or `sudo dnf install p7zip`
  - **Windows**: Install 7-Zip or NanaZip.

### 2. Installation
```bash
git clone https://github.com/noobaly-original/archive-explorer.git
cd archive-explorer

# Using uv (recommended):
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Or using standard python:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Launching ArcVault
```bash
python3 run.py
```

---

## 📁 Vault Structure Explained

When ArcVault creates a vault named `MyVault`, the filesystem structure looks like this:

```text
MyVault/
├── .arcvault                       # Vault metadata descriptor (ID, name, version)
├── .vault_check.7z                 # Fast password verification canary
├── photos.7z                       # Virtual Entry Point: Encrypted metadata.json
├── documents.7z                    # Virtual Entry Point: Encrypted metadata.json
└── arc-data/                       # Store-mode AES-256 encrypted payload
    ├── K9mB3vXp8Q1L/              # Entry point data directory (random alphanumeric ID)
    │   ├── a1b2c3d4e5f6/          # Item folder for "vacation.jpg" (<= 1 GB)
    │   │   └── chunk_000.7z       # AES-256 store-mode chunk (-mx=0, -mhe=on)
    │   └── 9z8y7x6w5v4u/          # Item folder for "drone_4k.mp4" (> 1 GB)
    │       ├── chunk_000.7z       # 1 GB encrypted chunk
    │       ├── chunk_001.7z       # 1 GB encrypted chunk
    │       └── chunk_002.7z       # Remainder encrypted chunk
    └── Z7y4W1v2U9t0/              # Entry point data directory for 'documents'
```

- When viewing `photos` inside ArcVault, the application projects the virtual items seamlessly as single unified files and directories.
- `metadata.json` is automatically hidden from the user view.
- Legacy V1 monolithic archives are automatically migrated to V2 chunked format upon opening.

---

## 🧪 Running Tests

The test suite covers backend encryption, V2 chunking/shredding, atomic swapping, backup recovery, password validation, and GUI components:

```bash
.venv/bin/python3 -m unittest discover tests -v
```

---

## 📦 Compiling Standalone Binaries (PyInstaller)

ArcVault can be compiled into a standalone desktop application or macOS app bundle using PyInstaller:

```bash
# Build using the included specification file
pyinstaller arcvault.spec --noconfirm --clean
```

The resulting binaries will be located in `dist/`:
- **macOS**: `dist/ArcVault.app` and `dist/ArcVault/ArcVault`
- **Linux**: `dist/ArcVault/ArcVault`
- **Windows**: `dist\ArcVault\ArcVault.exe`

For detailed build instructions, cross-platform options, and icon assets, see [**`BUILD.md`**](BUILD.md).

---

## 🔒 Security Model

- **Encryption**: Standard AES-256 with 7-Zip header encryption (`-mhe=on`). File names, chunk sizes, and internal folder hierarchies cannot be inspected without the master key.
- **Atomic Operations**: All metadata changes are written to temporary scratch archives and atomically swapped into place (`os.replace`), preventing partial writes and synchronization corruption.
- **Memory Safety**: Master passwords and encryption keys exist only in process RAM while unlocked, and are completely purged when the vault is locked or the application closes.
- **Isolated Staging**: Previews and temporary extraction operations run inside permission-restricted directories cleaned up automatically on lock or termination.
