# 📝 Vaultables - Developer Note-to-Self & Architecture Guide

> **Quick Context**: Vaultables is an open-source, lightweight, cross-platform encrypted vault manager and editor built in Python (PyQt6 + 7-Zip).
> **GitHub Repository**: [https://github.com/noobaly-original/vaultables](https://github.com/noobaly-original/vaultables)

---

## 💡 1. Core Philosophy & Design Rationale

Traditional vault tools (Cryptomator, VeraCrypt) rely on mounting virtual disk drives using third-party kernel/filesystem drivers (FUSE, Dokany, WinFsp, WebDAV). This introduces:
- Driver dependency rot and permission crashes across OS updates.
- Monolithic container files that cause massive cloud-sync conflicts and bandwidth waste (modifying 1 byte re-uploads gigabytes).
- Total file imprisonment: without the specific vault software installed and running, files cannot be accessed.

**Vaultables's Core Rule**: *"A vault should not be a prison for your files."*
1. **Zero Kernel Drivers / No Mounted Disks**: Vaultables presents an application-level virtual folder hierarchy backed by lightweight, encrypted metadata files.
2. **True Data Independence**: All stored files are individually encrypted with standard 7-Zip AES-256 (`-mhe=on`). If Vaultables is not installed, the user can open any file with standard file archivers (7-Zip, NanaZip, PeaZip, Keka) and their master password.
3. **Cloud-Sync Friendly**: Modifying, adding, or deleting a file only changes that specific file's encrypted container, syncing efficiently on Google Drive, Nextcloud, Dropbox, and Syncthing.
4. **No Mass Re-Archiving**: Unlike keeping one giant `.7z` file, editing or deleting an item never triggers a full re-pack.

---

## 🏛️ 2. Vault On-Disk Layout Specification

```
[Vault Root Directory]/
├── .vaultables                 # JSON: display name, vault_id, version, obfuscation mode
├── .vault_check.7z           # Micro-archive token for 5ms master password validation
├── import/                   # Off-site incoming inbox for encrypted .7z archives
│   └── README.txt            # Helpful guide for dropping archives from mobile/external devices
├── vaultables-data/                 # V2 decoupled chunk storage
│   ├── <ep_dir_id>/          # Obfuscated hash or human-readable entry point folder
│   │   └── <item_id>/        # Obfuscated hash or relative file path folder
│   │       ├── chunk_000.7z  # Store-mode AES-256 encrypted 1GB chunk (with -mhe=on)
│   │       └── chunk_001.7z  # (Subsequent chunks if file > 1GB)
│   └── ...
├── documents.7z              # Entry Point archive (contains only encrypted metadata.json)
├── photos.7z                 # Entry Point archive
└── imports.7z                # Auto-created entry point for off-site imported files
```

### Decoupled Display Name
- The physical directory name on disk (e.g., `MyVault/`) is decoupled from the vault's display name (e.g., `"Financial Records"`).
- Persisted in `.vaultables` and cached in user config (`~/.vaultables/config.json`).
- Renameable on the fly via toolbar or sidebar.

### Obfuscation Modes & On-Demand Obfuscation
- **Obfuscated (`obfuscate_names=True`, default)**: Folder and file items under `vaultables-data/` use randomly generated 12-character alphanumeric IDs (`generate_unique_folder_id`). Protects against filesystem metadata snooping.
- **Unobfuscated (`obfuscate_names=False`)**: Folder hierarchy under `vaultables-data/` mirrors the internal layout with clear text folder names. Ideal for users who want to browse their encrypted files directly in Finder / File Explorer without the GUI.
- **On-Demand Obfuscation (Per-Entry-Point Override)**:
  - When creating a new entry point, Vaultables detects the vault mode and adapts the modal dialog:
    * In an **obfuscated vault**: Checkbox offers `"Obfuscated vault, but this entry point is easily readable"` (stores this specific entry point under human-readable paths in `vaultables-data/`).
    * In an **unobfuscated vault**: Checkbox offers `"Unobfuscated vault, but this entry point has names randomized"` (disguises this specific entry point with randomized 12-char privacy IDs in `vaultables-data/`).
  - Stored inside each `{entry_point}.7z` metadata as `"obfuscate_names": true/false/null` and exposed via `vault.is_entry_point_obfuscated(name)` and `meta.is_obfuscated()`.
  - All file addition, subfolder creation, deletion, and renaming automatically respect each entry point's individual obfuscation setting.

---

## 📬 3. Off-site File Importer (`import/` -> `imports.7z`)

### Why It Exists
Publishing an iOS/iPadOS app to the Apple App Store requires a \$99/year developer license. To keep Vaultables free, portable, and liberating:
- Users on mobile devices or other machines can simply use any standard archiving app (Keka, iZip, standard 7-Zip) to compress/encrypt files with their vault password into a `.7z` file.
- Drop the `.7z` into the vault's `import/` folder (via cloud sync, AirDrop, or local file transfer).

### How It Works
1. Upon unlock (or clicking **Check Imports** on the toolbar, or clicking **Refresh**):
   `vault.process_pending_imports()` scans `vault/import/*.7z`.
2. Tests each `.7z` file against the vault master password (`sevenzip.test_archive`). Unencrypted archives or wrong-password files are safely ignored and left intact.
3. Valid archives are extracted into an isolated secure OS temporary staging folder (`tempfile.TemporaryDirectory` with random UUID subfolder).
4. Extracted files/directories are chunked, AES-256 encrypted, and incorporated into the `imports` entry point (`imports.7z` and `vaultables-data/`).
5. Upon successful incorporation, the source `.7z` in `import/` is removed to prevent duplicate reprocessing.
6. Temporary plaintext staging files are purged from memory and disk.

---

## 🗺️ 4. Codebase Architecture & Key Files

### Backend (`vaultables/core/`)
- `vault.py`: Main `Vault` class orchestrating entry points, search, file additions, migrations, display name persistence, and off-site imports.
- `storage_v2.py`: `V2StorageEngine`, `V2EntryPointMetadata`, `V2ItemMetadata`. Implements chunking (default 1GB, store-mode AES-256 with encrypted headers), atomic swaps via `.bak` files, and metadata serialization.
- `sevenzip.py`: Cross-platform CLI runner for `7zz`, `7z`, or `nanazip`. Provides `-mhe=on`, `-mx=5` (for metadata) / `-mx=0` (for chunks), listing, testing, and extraction.
- `models.py`: Data classes (`ArchiveItem`, `EntryPoint`, `VaultMetadata`, `FileCategory`). Contains file classification logic.

### Frontend (`vaultables/gui/`)
- `main_window.py`: PyQt6 main application, toolbar actions, splitter management, search bar routing, external file watcher integration, and import triggers.
- `sidebar.py`: Vault list, entry point navigation, display name updates, drag-and-drop targets.
- `file_view.py`: Modern file table with 10 zoom sizes, horizontal column resizing, search result location badges, context menus.
- `preview_panel.py`: Quick preview for images, syntax-highlighted code/text (Pygments), in-app text editor, external app launcher.
- `vault_dialog.py`: `UnlockVaultDialog`, `CreateVaultDialog` (with obfuscation toggle and duplicate vault folder prevention).
- `workers.py`: Background `QThread` workers for unlock, item listing, adding files, and unencrypted exporting.
- `icons.py`: SVG vector icon provider with crisp Retina 1x/2x/3x DPR rasterization and caching.
- `theme.py`: Slate modern dark and light stylesheets.
- `logger.py`: Centralized logging with UI notification signals and persistent history.

---

## 🛠️ 5. Build System & GitHub Actions CI/CD

### Target Artifacts
- **Windows**: Portable standalone `Vaultables-Windows-x64.exe` (with embedded multi-res `Vaultables.ico`).
- **Linux**: Standalone ELF binary `Vaultables-Linux-x64` + `.tar.gz`.
- **macOS Apple Silicon**: `Vaultables-macOS-arm64` + `.app.zip` (ad-hoc signed).
- **macOS Intel**: `Vaultables-macOS-x86_64` + `.app.zip` (ad-hoc signed).

### Build Scripts
- `build_mac.sh`: Creates both `.app` bundle and standalone onefile binary using PyInstaller.
- `build_linux.sh`: Sets up `.venv`, installs requirements, builds onefile binary.
- `build_windows.ps1` & `build_windows.bat`: Automatically prepares `.venv`, installs `requirements.txt`, generates `.ico` from `icon.png`, and compiles `dist\Vaultables.exe`.

### Crucial Lessons & Gotchas
1. **PowerShell Non-ASCII Encoding**: PowerShell 5.1 parses scripts using the system code page (Windows-1252). Non-ASCII characters (like UTF-8 checkmarks `✓`) can map to smart quotes `“` and corrupt string parsing. **Always keep all build scripts in pure ASCII** (e.g. use `[OK]`, `[+]`).
2. **GitHub Actions Runners**:
   - `macos-13` was deprecated and retired by GitHub in late 2025. Always use `macos-15-intel` for macOS x86_64 runners.
   - `macos-14` is used for macOS ARM64 Apple Silicon.

---

## 🧪 6. Testing & Quality Assurance

Run the complete test suite:
```bash
.venv/bin/python -m unittest discover tests
```
- Total tests: **45 automated tests** covering backend encryption, V2 chunk shredding, atomic recovery, folder name obfuscation, search, display name renaming, off-site file importer, Retina icon scaling, and GUI workflows.
- All tests run in headless offscreen mode (`QT_QPA_PLATFORM=offscreen`).
