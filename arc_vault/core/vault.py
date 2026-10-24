"""Vault manager orchestrating root directory archives, entry points, and encryption."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from arc_vault.core.models import ArchiveItem, EntryPoint, VaultMetadata, classify_file
from arc_vault.core.sevenzip import SevenZip, SevenZipOperationError
from arc_vault.logger import log_info, log_warning


class VaultUnlockError(Exception):
    """Raised when vault unlocking fails due to invalid password or corrupted archive."""
    pass


class Vault:
    """Manages an ArcVault root directory and its encrypted 7z entry points."""

    MARKER_FILENAME = ".arcvault"
    CHECK_FILENAME = ".vault_check.7z"

    def __init__(self, root_dir: Path, sevenzip: Optional[SevenZip] = None) -> None:
        self.root_dir = root_dir.resolve()
        self.sevenzip = sevenzip or SevenZip()
        self.metadata: Optional[VaultMetadata] = None
        self._password: Optional[str] = None
        self.is_unlocked: bool = False
        self.entry_points: Dict[str, EntryPoint] = {}
        self._cache: Dict[str, List[ArchiveItem]] = {}
        self._temp_preview_dir: Optional[tempfile.TemporaryDirectory] = None
        self._edit_staging_dir: Optional[tempfile.TemporaryDirectory] = None

        self._read_metadata()

    def __del__(self) -> None:
        if hasattr(self, "_temp_preview_dir") and self._temp_preview_dir:
            try:
                self._temp_preview_dir.cleanup()
            except Exception:
                pass
            self._temp_preview_dir = None
        if hasattr(self, "_edit_staging_dir") and self._edit_staging_dir:
            try:
                self._edit_staging_dir.cleanup()
            except Exception:
                pass
            self._edit_staging_dir = None

    def _read_metadata(self) -> None:
        """Read .arcvault metadata if it exists."""
        marker = self.root_dir / self.MARKER_FILENAME
        # Also check fallback .{app}_vault
        if not marker.exists():
            alt_marker = self.root_dir / ".arcvault_vault"
            if alt_marker.exists():
                marker = alt_marker

        if marker.exists():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                self.metadata = VaultMetadata(
                    name=data.get("name", self.root_dir.name),
                    vault_id=data.get("vault_id", str(uuid.uuid4())),
                    version=data.get("version", "1.0"),
                    created_at=data.get("created_at", ""),
                    encryption=data.get("encryption", "AES-256"),
                )
                return
            except Exception:
                pass

        # Default metadata if marker doesn't exist yet
        self.metadata = VaultMetadata(
            name=self.root_dir.name,
            vault_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def create_vault(
        cls,
        root_dir: Path,
        name: str,
        password: str,
        initial_entry_points: Optional[List[str]] = None,
        sevenzip: Optional[SevenZip] = None,
    ) -> Vault:
        """Create a new vault directory with marker, verification check, and initial entry points."""
        sz = sevenzip or SevenZip()
        root_dir.mkdir(parents=True, exist_ok=True)

        vault_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        metadata_dict = {
            "name": name,
            "vault_id": vault_id,
            "version": "1.0",
            "created_at": created_at,
            "encryption": "AES-256",
            "check_archive": cls.CHECK_FILENAME,
        }
        marker_file = root_dir / cls.MARKER_FILENAME
        marker_file.write_text(json.dumps(metadata_dict, indent=2), encoding="utf-8")

        # Create the small vault check archive to allow fast password testing
        check_path = root_dir / cls.CHECK_FILENAME
        sz.create_empty_archive(check_path, password)

        # Create requested initial entry points (e.g. "photos", "documents")
        if initial_entry_points:
            for ep_name in initial_entry_points:
                clean_name = ep_name.strip()
                if clean_name:
                    ep_path = root_dir / f"{clean_name}.7z"
                    if not ep_path.exists():
                        sz.create_empty_archive(ep_path, password)

        log_info(f"Created new vault '{name}' at {root_dir}", category="SECURITY")
        vault = cls(root_dir, sz)
        vault.unlock(password)
        return vault

    def unlock(self, password: str) -> bool:
        """
        Verify password and unlock vault.
        Checks against .vault_check.7z if present, or against any .7z file in the vault root.
        """
        if not self.root_dir.exists():
            raise VaultUnlockError(f"Vault folder '{self.root_dir}' does not exist.")

        # 1. Try checking against check archive
        check_file = self.root_dir / self.CHECK_FILENAME
        if check_file.exists():
            if not self.sevenzip.test_archive(check_file, password):
                log_warning(f"Failed password check on '{self.root_dir.name}'", category="SECURITY")
                return False
        else:
            # 2. Check against any .7z file in root
            sevenz_files = [
                f for f in self.root_dir.glob("*.7z")
                if f.name != self.CHECK_FILENAME
            ]
            if sevenz_files:
                first_archive = sevenz_files[0]
                if not self.sevenzip.test_archive(first_archive, password):
                    log_warning(f"Failed password check on '{self.root_dir.name}'", category="SECURITY")
                    return False
            else:
                self.sevenzip.create_empty_archive(check_file, password)

        self._password = password
        self.is_unlocked = True
        self.refresh_entry_points()
        vault_title = self.metadata.name if self.metadata else self.root_dir.name
        log_info(f"Vault unlocked: '{vault_title}' ({len(self.entry_points)} entry points)", category="SECURITY")
        return True

    def lock(self) -> None:
        """Lock the vault, clearing cached passwords and temp previews/staging."""
        vault_title = self.metadata.name if self.metadata else self.root_dir.name
        self._password = None
        self.is_unlocked = False
        self.entry_points.clear()
        self._cache.clear()
        if self._temp_preview_dir:
            try:
                self._temp_preview_dir.cleanup()
            except Exception:
                pass
            self._temp_preview_dir = None
        if self._edit_staging_dir:
            try:
                self._edit_staging_dir.cleanup()
            except Exception:
                pass
            self._edit_staging_dir = None
        log_info(f"Vault locked: '{vault_title}' (memory keys purged)", category="SECURITY")

    @property
    def password(self) -> str:
        if not self._password or not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")
        return self._password

    def get_preview_temp_dir(self) -> Path:
        """Get or create isolated temp directory for previews."""
        if not self._temp_preview_dir:
            self._temp_preview_dir = tempfile.TemporaryDirectory(prefix="arcvault_preview_")
        return Path(self._temp_preview_dir.name)

    def get_edit_staging_dir(self) -> Path:
        """Get or create isolated temp directory for external editing staging."""
        if not self._edit_staging_dir:
            self._edit_staging_dir = tempfile.TemporaryDirectory(prefix="arcvault_watched_edit_")
        return Path(self._edit_staging_dir.name)

    def refresh_entry_points(self) -> Dict[str, EntryPoint]:
        """Scan vault root for .7z files (entry points)."""
        if not self.is_unlocked:
            return {}

        self.entry_points.clear()
        for file in sorted(self.root_dir.glob("*.7z")):
            if file.name == self.CHECK_FILENAME:
                continue

            ep_name = file.stem
            size_on_disk = file.stat().st_size
            self.entry_points[ep_name] = EntryPoint(
                name=ep_name,
                archive_file=file,
                size_on_disk=size_on_disk,
            )

        return self.entry_points

    def create_entry_point(self, name: str) -> EntryPoint:
        """Create a new top-level encrypted entry point (.7z file)."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Entry point name cannot be empty.")

        ep_file = self.root_dir / f"{clean_name}.7z"
        if ep_file.exists():
            raise FileExistsError(f"Entry point '{clean_name}' already exists.")

        self.sevenzip.create_empty_archive(ep_file, self.password)
        ep = EntryPoint(
            name=clean_name,
            archive_file=ep_file,
            size_on_disk=ep_file.stat().st_size if ep_file.exists() else 0,
        )
        self.entry_points[clean_name] = ep
        self._cache[clean_name] = []
        log_info(f"Created new entry point '{clean_name}.7z'")
        return ep

    def delete_entry_point(self, name: str) -> bool:
        """Delete an entire entry point (.7z file) from the vault."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if name not in self.entry_points:
            return False

        ep = self.entry_points[name]
        if ep.archive_file.exists():
            ep.archive_file.unlink()

        del self.entry_points[name]
        self._cache.pop(name, None)
        log_info(f"Deleted entry point '{name}.7z'")
        return True

    def rename_entry_point(self, old_name: str, new_name: str) -> bool:
        """Rename an entry point archive."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        clean_new = new_name.strip()
        if not clean_new or old_name not in self.entry_points:
            return False

        old_file = self.entry_points[old_name].archive_file
        new_file = self.root_dir / f"{clean_new}.7z"

        if new_file.exists():
            raise FileExistsError(f"Target '{clean_new}' already exists.")

        old_file.rename(new_file)
        self.entry_points.pop(old_name, None)
        cached = self._cache.pop(old_name, [])

        ep = EntryPoint(
            name=clean_new,
            archive_file=new_file,
            size_on_disk=new_file.stat().st_size,
        )
        self.entry_points[clean_new] = ep
        self._cache[clean_new] = cached
        log_info(f"Renamed entry point '{old_name}' -> '{clean_new}'")
        return True

    def get_archive_items(self, entry_point_name: str, force_reload: bool = False) -> List[ArchiveItem]:
        """Get all items inside an entry point archive (cached)."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if entry_point_name not in self.entry_points:
            return []

        if not force_reload and entry_point_name in self._cache:
            return self._cache[entry_point_name]

        archive_file = self.entry_points[entry_point_name].archive_file
        items = self.sevenzip.list_archive(archive_file, self.password, entry_point_name=entry_point_name)
        self._cache[entry_point_name] = items
        self.entry_points[entry_point_name].item_count = len(items)
        self.entry_points[entry_point_name].children = items
        return items

    def get_items_in_directory(self, entry_point_name: str, subfolder_path: str = "") -> List[ArchiveItem]:
        """
        List immediate children (files and subfolders) inside a specific subfolder.
        """
        all_items = self.get_archive_items(entry_point_name)
        norm_sub = subfolder_path.strip("/").replace("\\", "/")

        results: List[ArchiveItem] = []
        seen_dirs = set()

        for item in all_items:
            item_path = item.path.strip("/")
            if norm_sub:
                if not item_path.startswith(norm_sub + "/"):
                    continue
                relative = item_path[len(norm_sub) + 1:]
            else:
                relative = item_path

            if not relative:
                continue

            parts = relative.split("/")
            if len(parts) == 1:
                # Immediate child
                results.append(item)
            else:
                # Intermediate directory
                immediate_dir = parts[0]
                if immediate_dir not in seen_dirs:
                    seen_dirs.add(immediate_dir)
                    full_dir_path = f"{norm_sub}/{immediate_dir}" if norm_sub else immediate_dir
                    # Check if there's an explicit folder item for this
                    existing_folder = next((i for i in all_items if i.path.strip("/") == full_dir_path and i.is_dir), None)
                    if existing_folder:
                        results.append(existing_folder)
                    else:
                        results.append(
                            ArchiveItem(
                                name=immediate_dir,
                                path=full_dir_path,
                                is_dir=True,
                                entry_point_name=entry_point_name,
                            )
                        )

        results.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        return results

    def add_files(
        self,
        entry_point_name: str,
        source_paths: List[Path],
        subfolder: str = "",
    ) -> bool:
        """Add files into entry point archive under subfolder."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if entry_point_name not in self.entry_points:
            raise ValueError(f"Entry point '{entry_point_name}' not found.")

        ep = self.entry_points[entry_point_name]
        ok = self.sevenzip.add_files(ep.archive_file, source_paths, self.password, archive_subfolder=subfolder)
        if ok:
            self._cache.pop(entry_point_name, None)
            self.refresh_entry_points()
            sub_desc = f"/{subfolder}" if subfolder else "root"
            log_info(f"Added {len(source_paths)} items to '{entry_point_name}' ({sub_desc})")
        return ok

    def update_file_from_disk(
        self,
        entry_point_name: str,
        internal_path: str,
        source_disk_file: Path,
    ) -> bool:
        """Update an existing file inside the archive directly from a file on disk."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if entry_point_name not in self.entry_points:
            raise ValueError(f"Entry point '{entry_point_name}' not found.")

        ep = self.entry_points[entry_point_name]
        ok = self.sevenzip.update_single_file(
            ep.archive_file, source_disk_file, internal_path, self.password
        )
        if ok:
            self._cache.pop(entry_point_name, None)
            self.refresh_entry_points()
            log_info(f"Updated '{internal_path}' in '{entry_point_name}.7z'")
        return ok

    def update_file_content(
        self,
        entry_point_name: str,
        internal_path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Update an existing file inside the archive with new string or byte content."""
        with tempfile.NamedTemporaryFile("wb", delete=False) as tmp:
            if isinstance(content, str):
                tmp.write(content.encode("utf-8"))
            else:
                tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            return self.update_file_from_disk(entry_point_name, internal_path, tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def create_subfolder(self, entry_point_name: str, parent_subfolder: str, new_folder_name: str) -> bool:
        """Create a new folder inside an entry point."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        ep = self.entry_points[entry_point_name]
        clean_name = new_folder_name.strip()
        target_path = f"{parent_subfolder}/{clean_name}".strip("/") if parent_subfolder else clean_name
        ok = self.sevenzip.create_subfolder_in_archive(ep.archive_file, target_path, self.password)
        if ok:
            self._cache.pop(entry_point_name, None)
            self.refresh_entry_points()
            log_info(f"Created subfolder '{target_path}' inside '{entry_point_name}.7z'")
        return ok

    def delete_item(self, entry_point_name: str, internal_path: str) -> bool:
        """Delete an item (or directory) from an entry point archive."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        ep = self.entry_points[entry_point_name]
        ok = self.sevenzip.delete_items(ep.archive_file, [internal_path], self.password)
        if ok:
            self._cache.pop(entry_point_name, None)
            self.refresh_entry_points()
            log_info(f"Deleted '{internal_path}' from '{entry_point_name}.7z'")
        return ok

    def rename_item(self, entry_point_name: str, old_path: str, new_path: str) -> bool:
        """Rename an item inside an entry point archive."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        ep = self.entry_points[entry_point_name]
        ok = self.sevenzip.rename_item(ep.archive_file, old_path, new_path, self.password)
        if ok:
            self._cache.pop(entry_point_name, None)
            self.refresh_entry_points()
            log_info(f"Renamed inside '{entry_point_name}.7z': '{old_path}' -> '{new_path}'")
        return ok

    def extract_file_for_preview(self, entry_point_name: str, internal_path: str) -> Optional[Path]:
        """Extract a single file into the temporary preview directory."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        ep = self.entry_points[entry_point_name]
        preview_dir = self.get_preview_temp_dir()
        return self.sevenzip.extract_file_for_preview(
            ep.archive_file, internal_path, self.password, preview_dir
        )

    def extract_file_for_editing(self, entry_point_name: str, internal_path: str) -> Optional[Path]:
        """Extract a single file into the persistent watched editing staging directory."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        ep = self.entry_points[entry_point_name]
        staging_dir = self.get_edit_staging_dir() / entry_point_name
        staging_dir.mkdir(parents=True, exist_ok=True)
        return self.sevenzip.extract_file_for_preview(
            ep.archive_file, internal_path, self.password, staging_dir
        )

    def export_items(self, entry_point_name: str, internal_paths: List[str], dest_dir: Path) -> bool:
        """Export selected items from entry point archive to destination directory."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        ep = self.entry_points[entry_point_name]
        ok = self.sevenzip.extract_to_destination(
            ep.archive_file, internal_paths, self.password, dest_dir
        )
        if ok:
            log_info(f"Exported {len(internal_paths) if internal_paths else 'all'} items from '{entry_point_name}' to {dest_dir}")
        return ok
