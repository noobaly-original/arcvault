"""Vault manager orchestrating root directory archives, entry points, and V2 chunked storage."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from arc_vault.core.models import ArchiveItem, EntryPoint, FileCategory, VaultMetadata, classify_file
from arc_vault.core.sevenzip import SevenZip, SevenZipOperationError
from arc_vault.core.storage_v2 import (
    DEFAULT_CHUNK_SIZE,
    METADATA_FILENAME,
    V2EntryPointMetadata,
    V2ItemMetadata,
    V2StorageEngine,
    generate_random_id,
    generate_unique_folder_id,
)
from arc_vault.logger import log_info, log_warning


class VaultUnlockError(Exception):
    """Raised when vault unlocking fails due to invalid password or corrupted archive."""
    pass


class VaultExistsError(FileExistsError):
    """Raised when trying to create a vault inside an existing vault folder."""
    pass


class Vault:
    """
    Manages an ArcVault root directory, its encrypted metadata entry points,
    and the decoupled chunked storage in 'arc-data/'.
    """

    MARKER_FILENAME = ".arcvault"
    CHECK_FILENAME = ".vault_check.7z"
    ARC_DATA_DIRNAME = "arc-data"

    @classmethod
    def is_vault_dir(cls, directory: Path) -> bool:
        """Check if directory is an existing ArcVault root."""
        if not directory.exists() or not directory.is_dir():
            return False

        # 1. Fast verification check archive
        if (directory / cls.CHECK_FILENAME).is_file():
            return True

        # 2. Primary metadata marker file (.arcvault)
        # Note: Must be a regular file, NOT a directory (e.g. ~/.arcvault config dir)
        marker = directory / cls.MARKER_FILENAME
        if marker.is_file():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                if isinstance(data, dict) and ("vault_id" in data or "storage_mode" in data or "version" in data):
                    return True
            except Exception:
                pass

        # 3. Alternate metadata marker file (.arcvault_vault)
        alt = directory / ".arcvault_vault"
        if alt.is_file():
            try:
                data = json.loads(alt.read_text(encoding="utf-8"))
                if isinstance(data, dict) and ("vault_id" in data or "storage_mode" in data or "version" in data):
                    return True
            except Exception:
                pass

        return False

    @classmethod
    def find_enclosing_vault(cls, target_path: Path) -> Optional[Path]:
        """
        Check if target_path or any of its parent directories is an existing vault.
        Returns the existing vault's root directory if found, or None.
        """
        try:
            curr = target_path.resolve()
        except Exception:
            curr = target_path

        while True:
            if cls.is_vault_dir(curr):
                return curr
            parent = curr.parent
            if parent == curr:
                break
            curr = parent
        return None

    def __init__(
        self,
        root_dir: Path,
        sevenzip: Optional[SevenZip] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self.root_dir = root_dir.resolve()
        self.sevenzip = sevenzip or SevenZip()
        self.chunk_size = chunk_size
        self.v2_engine = V2StorageEngine(self.sevenzip, chunk_size=chunk_size)
        self.arc_data_dir = self.root_dir / self.ARC_DATA_DIRNAME

        self.metadata: Optional[VaultMetadata] = None
        self._password: Optional[str] = None
        self.is_unlocked: bool = False
        self.entry_points: Dict[str, EntryPoint] = {}
        self._v2_metadata: Dict[str, V2EntryPointMetadata] = {}
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
        if not marker.is_file():
            alt_marker = self.root_dir / ".arcvault_vault"
            if alt_marker.is_file():
                marker = alt_marker

        if marker.is_file():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                self.metadata = VaultMetadata(
                    name=data.get("name", self.root_dir.name),
                    vault_id=data.get("vault_id", str(uuid.uuid4())),
                    version=data.get("version", "2.0"),
                    created_at=data.get("created_at", ""),
                    encryption=data.get("encryption", "AES-256"),
                    obfuscate_names=bool(data.get("obfuscate_names", True)),
                )
                return
            except Exception:
                pass

        self.metadata = VaultMetadata(
            name=self.root_dir.name,
            vault_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            obfuscate_names=True,
        )

    @property
    def name(self) -> str:
        """Return the display name of the vault."""
        if self.metadata and self.metadata.name:
            return self.metadata.name
        return self.root_dir.name

    def set_display_name(self, new_name: str) -> None:
        """
        Update the display name of the vault in its metadata without changing its physical root directory.
        Persists the change in the .arcvault metadata file.
        """
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Vault display name cannot be empty.")

        if not self.metadata:
            self._read_metadata()
        if self.metadata:
            self.metadata.name = clean_name

        marker = self.root_dir / self.MARKER_FILENAME
        data = {}
        if marker.is_file():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        data["name"] = clean_name
        if "vault_id" not in data and self.metadata:
            data["vault_id"] = self.metadata.vault_id
        if "version" not in data:
            data["version"] = "2.0"

        marker.write_text(json.dumps(data, indent=2), encoding="utf-8")
        log_info(f"Updated vault display name to '{clean_name}' for '{self.root_dir}'", category="VAULT")

    @property
    def obfuscate_names(self) -> bool:
        if self.metadata:
            return self.metadata.obfuscate_names
        return True

    @classmethod
    def create_vault(
        cls,
        root_dir: Path,
        name: str,
        password: str,
        initial_entry_points: Optional[List[str]] = None,
        sevenzip: Optional[SevenZip] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        obfuscate_names: bool = True,
    ) -> Vault:
        """Create a new vault directory with marker, verification check, and arc-data folder."""
        # Safeguard: prevent creating a vault inside or at an existing vault folder
        enclosing = cls.find_enclosing_vault(root_dir)
        if enclosing:
            if enclosing == root_dir.resolve():
                raise VaultExistsError(
                    f"Cannot create vault: Directory '{root_dir}' is already an existing vault."
                )
            else:
                raise VaultExistsError(
                    f"Cannot create vault: Target directory '{root_dir}' is located inside an existing vault folder ('{enclosing}')."
                )

        sz = sevenzip or SevenZip()
        root_dir.mkdir(parents=True, exist_ok=True)
        arc_data = root_dir / cls.ARC_DATA_DIRNAME
        arc_data.mkdir(parents=True, exist_ok=True)

        vault_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        metadata_dict = {
            "name": name,
            "vault_id": vault_id,
            "version": "2.0",
            "created_at": created_at,
            "encryption": "AES-256",
            "check_archive": cls.CHECK_FILENAME,
            "storage_mode": "v2_chunked_arc_data",
            "obfuscate_names": obfuscate_names,
        }
        marker_file = root_dir / cls.MARKER_FILENAME
        marker_file.write_text(json.dumps(metadata_dict, indent=2), encoding="utf-8")

        # Fast password verification archive
        check_path = root_dir / cls.CHECK_FILENAME
        sz.create_empty_archive(check_path, password)

        vault = cls(root_dir, sz, chunk_size=chunk_size)
        vault._password = password
        vault.is_unlocked = True

        # Initialize requested initial entry points in V2 format
        if initial_entry_points:
            for ep_name in initial_entry_points:
                clean_name = ep_name.strip()
                if clean_name:
                    vault.create_entry_point(clean_name)

        log_info(f"Created new vault '{name}' at {root_dir} (obfuscate_names={obfuscate_names})", category="SECURITY")
        return vault

    def unlock(self, password: str) -> bool:
        """Verify password and unlock vault, loading V2 metadata."""
        if not self.root_dir.exists():
            raise VaultUnlockError(f"Vault folder '{self.root_dir}' does not exist.")

        self.arc_data_dir.mkdir(parents=True, exist_ok=True)

        # 1. Try checking against check archive
        check_file = self.root_dir / self.CHECK_FILENAME
        if check_file.is_file():
            if not self.sevenzip.test_archive(check_file, password):
                log_warning(f"Failed password check on '{self.root_dir.name}'", category="SECURITY")
                return False
        else:
            sevenz_files = [
                f for f in self.root_dir.glob("*.7z")
                if not f.name.startswith(".") and not f.name.endswith(".bak") and f.name != self.CHECK_FILENAME
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
        """Lock vault, clearing cached passwords, metadata, and staging dirs."""
        vault_title = self.metadata.name if self.metadata else self.root_dir.name
        self._password = None
        self.is_unlocked = False
        self.entry_points.clear()
        self._v2_metadata.clear()
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
        if not self._temp_preview_dir:
            self._temp_preview_dir = tempfile.TemporaryDirectory(prefix="arcvault_preview_")
        return Path(self._temp_preview_dir.name)

    def get_edit_staging_dir(self) -> Path:
        if not self._edit_staging_dir:
            self._edit_staging_dir = tempfile.TemporaryDirectory(prefix="arcvault_watched_edit_")
        return Path(self._edit_staging_dir.name)

    def refresh_entry_points(self) -> Dict[str, EntryPoint]:
        """Scan vault root for .7z files and load V2 metadata."""
        if not self.is_unlocked:
            return {}

        self.entry_points.clear()
        for file in sorted(self.root_dir.glob("*.7z")):
            if file.name.startswith(".") or file.name.endswith(".bak") or file.name == self.CHECK_FILENAME:
                continue

            ep_name = file.stem
            meta = self._load_or_migrate_entry_point(ep_name, file)
            self._v2_metadata[ep_name] = meta

            # Calculate total size on disk (archive file + chunk files in arc-data/{ep_dir_id})
            size_on_disk = file.stat().st_size
            ep_data_dir = self.arc_data_dir / meta.ep_dir_id
            if ep_data_dir.exists():
                for p in ep_data_dir.rglob("*.7z"):
                    try:
                        size_on_disk += p.stat().st_size
                    except Exception:
                        pass

            item_count = sum(1 for it in meta.items.values() if not it.is_dir)
            self.entry_points[ep_name] = EntryPoint(
                name=ep_name,
                archive_file=file,
                size_on_disk=size_on_disk,
                item_count=item_count,
            )

        return self.entry_points

    def _load_or_migrate_entry_point(self, ep_name: str, ep_file: Path) -> V2EntryPointMetadata:
        """Load V2 metadata. If legacy V1 monolithic archive, migrate seamlessly."""
        meta = self.v2_engine.load_metadata(ep_file, self.password)
        if meta is not None:
            return meta

        # Legacy V1 archive detected! Auto-migrate into V2
        log_info(f"Migrating legacy entry point '{ep_name}.7z' to V2 chunked architecture...")
        if self.obfuscate_names:
            ep_dir_id = generate_unique_folder_id(self.arc_data_dir, 12)
        else:
            ep_dir_id = ep_name
        ep_data_dir = self.arc_data_dir / ep_dir_id
        ep_data_dir.mkdir(parents=True, exist_ok=True)

        meta = V2EntryPointMetadata(
            version="2.0",
            entry_point_name=ep_name,
            ep_dir_id=ep_dir_id,
            items={},
        )

        try:
            legacy_items = self.sevenzip.list_archive(ep_file, self.password, entry_point_name=ep_name)
            with tempfile.TemporaryDirectory(prefix="arc_v1_migration_") as ext_dir:
                ext_path = Path(ext_dir)
                self.sevenzip.extract_to_destination(ep_file, [], self.password, ext_path)

                for item in legacy_items:
                    if item.name in (METADATA_FILENAME, ".arcvault_init"):
                        continue
                    clean_path = item.path.strip("/").replace("\\", "/")
                    if self.obfuscate_names:
                        used_ids = {it.item_id for it in meta.items.values() if it.item_id}
                        item_id = generate_unique_folder_id(ep_data_dir, 12, existing_ids=used_ids)
                    else:
                        item_id = clean_path

                    if item.is_dir:
                        meta.items[clean_path] = V2ItemMetadata(
                            path=clean_path,
                            name=item.name,
                            is_dir=True,
                            item_id=item_id,
                            modified=item.modified or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            category="FOLDER",
                        )
                        (ep_data_dir / item_id).mkdir(parents=True, exist_ok=True)
                    else:
                        local_extracted = ext_path / clean_path
                        if local_extracted.exists():
                            item_dir = ep_data_dir / item_id
                            size, packed, chunks = self.v2_engine.chunk_and_encrypt_file(
                                local_extracted, item_dir, self.password
                            )
                            cat = classify_file(item.name, is_dir=False).name
                            meta.items[clean_path] = V2ItemMetadata(
                                path=clean_path,
                                name=item.name,
                                is_dir=False,
                                item_id=item_id,
                                size=size,
                                packed_size=packed,
                                modified=item.modified or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                category=cat,
                                chunks=chunks,
                            )
        except Exception as e:
            log_warning(f"Error during legacy migration of '{ep_name}': {e}")

        # Save metadata and recreate lightweight archive containing only metadata.json (atomic swap)
        self.v2_engine.save_metadata(ep_file, meta, self.password)
        log_info(f"Successfully migrated '{ep_name}.7z' to V2 format ({len(meta.items)} items).")
        return meta

    def create_entry_point(self, name: str) -> EntryPoint:
        """Create a new V2 entry point archive."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Entry point name cannot be empty.")

        ep_file = self.root_dir / f"{clean_name}.7z"
        if ep_file.exists():
            raise FileExistsError(f"Entry point '{clean_name}' already exists.")

        meta = self.v2_engine.create_entry_point_archive(
            ep_file, clean_name, self.password, self.arc_data_dir, obfuscate_names=self.obfuscate_names
        )
        self._v2_metadata[clean_name] = meta
        self._cache[clean_name] = []

        ep = EntryPoint(
            name=clean_name,
            archive_file=ep_file,
            size_on_disk=ep_file.stat().st_size if ep_file.exists() else 0,
        )
        self.entry_points[clean_name] = ep
        log_info(f"Created new V2 entry point '{clean_name}.7z'")
        return ep

    def delete_entry_point(self, name: str) -> bool:
        """Delete an entire entry point and its data directory in arc-data."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if name not in self.entry_points:
            return False

        meta = self._v2_metadata.get(name)
        if meta and meta.ep_dir_id:
            ep_data_dir = self.arc_data_dir / meta.ep_dir_id
            if ep_data_dir.exists():
                shutil.rmtree(ep_data_dir, ignore_errors=True)

        ep = self.entry_points[name]
        if ep.archive_file.exists():
            ep.archive_file.unlink()

        del self.entry_points[name]
        self._v2_metadata.pop(name, None)
        self._cache.pop(name, None)
        log_info(f"Deleted entry point '{name}.7z' and its data store")
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
        meta = self._v2_metadata.pop(old_name, None)

        if meta:
            meta.entry_point_name = clean_new
            if not self.obfuscate_names:
                old_ep_dir = self.arc_data_dir / meta.ep_dir_id
                new_ep_dir = self.arc_data_dir / clean_new
                if old_ep_dir.exists():
                    old_ep_dir.rename(new_ep_dir)
                meta.ep_dir_id = clean_new
            self.v2_engine.save_metadata(new_file, meta, self.password)
            self._v2_metadata[clean_new] = meta

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
        """Project virtual files and folders from V2 metadata (metadata.json is never rendered)."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if entry_point_name not in self.entry_points:
            return []

        if not force_reload and entry_point_name in self._cache:
            return self._cache[entry_point_name]

        meta = self._v2_metadata.get(entry_point_name)
        if not meta:
            ep_file = self.entry_points[entry_point_name].archive_file
            meta = self._load_or_migrate_entry_point(entry_point_name, ep_file)
            self._v2_metadata[entry_point_name] = meta

        items: List[ArchiveItem] = []
        for item_meta in meta.items.values():
            if item_meta.name == METADATA_FILENAME or item_meta.name == ".arcvault_init":
                continue
            items.append(item_meta.to_archive_item(entry_point_name))

        self._cache[entry_point_name] = items
        self.entry_points[entry_point_name].item_count = sum(1 for i in items if not i.is_dir)
        self.entry_points[entry_point_name].children = items
        return items

    def get_items_in_directory(self, entry_point_name: str, subfolder_path: str = "") -> List[ArchiveItem]:
        """List immediate children (files and subfolders) inside a specific subfolder."""
        all_items = self.get_archive_items(entry_point_name)
        norm_sub = subfolder_path.strip("/").replace("\\", "/")

        results_dict: Dict[str, ArchiveItem] = {}

        for item in all_items:
            item_path = item.path.strip("/").replace("\\", "/")
            if norm_sub:
                if not item_path.startswith(norm_sub + "/"):
                    continue
                relative = item_path[len(norm_sub) + 1:]
            else:
                relative = item_path

            if not relative:
                continue

            parts = relative.split("/")
            first_segment = parts[0]
            if len(parts) == 1:
                # Immediate child
                if first_segment not in results_dict or item.is_dir:
                    results_dict[first_segment] = item
            else:
                # Intermediate directory
                if first_segment not in results_dict:
                    full_dir_path = f"{norm_sub}/{first_segment}" if norm_sub else first_segment
                    explicit_dir = next(
                        (i for i in all_items if i.path.strip("/").replace("\\", "/") == full_dir_path and i.is_dir),
                        None,
                    )
                    if explicit_dir:
                        results_dict[first_segment] = explicit_dir
                    else:
                        results_dict[first_segment] = ArchiveItem(
                            name=first_segment,
                            path=full_dir_path,
                            is_dir=True,
                            category=FileCategory.FOLDER,
                            entry_point_name=entry_point_name,
                        )

        results = list(results_dict.values())
        results.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        return results

    def get_all_subfolders(self, entry_point_name: str) -> List[str]:
        """Return a sorted list of all unique subfolder paths inside an entry point."""
        items = self.get_archive_items(entry_point_name)
        dirs = set()
        for i in items:
            if i.is_dir:
                dirs.add(i.path.strip("/").replace("\\", "/"))
            else:
                parts = i.path.strip("/").replace("\\", "/").split("/")
                if len(parts) > 1:
                    for k in range(1, len(parts)):
                        dirs.add("/".join(parts[:k]))
        return sorted(dirs)

    def search_items(
        self,
        query: str,
        entry_point_name: Optional[str] = None,
        subfolder_prefix: str = "",
        recursive: bool = True,
    ) -> List[ArchiveItem]:
        """
        Recursively search for files and folders matching query across multiple entry points and subfolders.
        - If entry_point_name is provided, search within that entry point.
          - If subfolder_prefix is provided:
            - If recursive=True, search within subfolder and all its descendants.
            - If recursive=False, search only immediate children of subfolder.
        - If entry_point_name is None or empty, search across ALL entry points in the vault.
        Matches against item name and internal path using substring and wildcard patterns.
        """
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        clean_q = query.strip()
        if not clean_q:
            return []

        lower_q = clean_q.lower()
        use_wildcard = "*" in clean_q or "?" in clean_q

        # Determine target entry points
        if entry_point_name:
            target_eps = [entry_point_name] if entry_point_name in self.entry_points else []
        else:
            target_eps = list(self.entry_points.keys())

        matched_items: List[ArchiveItem] = []
        norm_sub = subfolder_prefix.strip("/").replace("\\", "/") if subfolder_prefix else ""

        # If searching entire vault at root level, also match entry points themselves
        if not entry_point_name and not norm_sub:
            for ep_name, ep in self.entry_points.items():
                if lower_q in ep_name.lower():
                    matched_items.append(
                        ArchiveItem(
                            name=ep_name,
                            path=ep_name,
                            is_dir=True,
                            size=ep.size_on_disk,
                            packed_size=ep.size_on_disk,
                            entry_point_name=ep_name,
                            category=FileCategory.ENTRY_POINT,
                        )
                    )

        for ep_name in target_eps:
            all_ep_items = self.get_archive_items(ep_name)
            for it in all_ep_items:
                it_path = it.path.strip("/").replace("\\", "/")
                if norm_sub:
                    if not (it_path == norm_sub or it_path.startswith(norm_sub + "/")):
                        continue
                    if not recursive:
                        rel = it_path[len(norm_sub) + 1:] if it_path.startswith(norm_sub + "/") else ""
                        if "/" in rel:
                            continue

                name_lower = it.name.lower()
                path_lower = it_path.lower()

                matches = False
                if use_wildcard:
                    if fnmatch.fnmatch(name_lower, lower_q) or fnmatch.fnmatch(path_lower, lower_q):
                        matches = True
                else:
                    if lower_q in name_lower or lower_q in path_lower:
                        matches = True

                if matches:
                    matched_items.append(it)

        # Sort: folders first, then by name
        matched_items.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        return matched_items

    def add_files(
        self,
        entry_point_name: str,
        source_paths: List[Path],
        subfolder: str = "",
    ) -> bool:
        """
        Add local files or directories into the entry point without re-archiving existing files.
        Chunks files > 1GB into 1GB store-mode AES-256 encrypted parts under arc-data.
        """
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if entry_point_name not in self.entry_points:
            raise ValueError(f"Entry point '{entry_point_name}' not found.")

        meta = self._v2_metadata.get(entry_point_name)
        if not meta:
            ep_file = self.entry_points[entry_point_name].archive_file
            meta = self._load_or_migrate_entry_point(entry_point_name, ep_file)
            self._v2_metadata[entry_point_name] = meta

        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        ep_data_dir.mkdir(parents=True, exist_ok=True)
        norm_sub = subfolder.strip("/").replace("\\", "/")

        for src in source_paths:
            if not src.exists():
                continue

            if src.is_dir():
                self._add_directory_recursive(meta, ep_data_dir, src, parent_subfolder=norm_sub)
            else:
                self._add_single_file(meta, ep_data_dir, src, target_subfolder=norm_sub)

        # Save lightweight metadata
        ep_file = self.entry_points[entry_point_name].archive_file
        self.v2_engine.save_metadata(ep_file, meta, self.password)
        self._cache.pop(entry_point_name, None)
        self.refresh_entry_points()

        sub_desc = f"/{norm_sub}" if norm_sub else "root"
        log_info(f"Added {len(source_paths)} items to '{entry_point_name}' ({sub_desc})")
        return True

    def _add_single_file(
        self,
        meta: V2EntryPointMetadata,
        ep_data_dir: Path,
        source_file: Path,
        target_subfolder: str = "",
    ) -> V2ItemMetadata:
        """Encrypt and record a single file."""
        clean_name = source_file.name
        rel_path = f"{target_subfolder}/{clean_name}".strip("/") if target_subfolder else clean_name

        if self.obfuscate_names:
            used_ids = {it.item_id for it in meta.items.values() if it.item_id}
            item_id = generate_unique_folder_id(ep_data_dir, 12, existing_ids=used_ids)
        else:
            item_id = rel_path

        item_dir = ep_data_dir / item_id
        if not self.obfuscate_names and item_dir.exists():
            shutil.rmtree(item_dir, ignore_errors=True)

        size, packed, chunks = self.v2_engine.chunk_and_encrypt_file(
            source_file, item_dir, self.password
        )

        mod_time = datetime.fromtimestamp(source_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        cat = classify_file(clean_name, is_dir=False).name

        item_meta = V2ItemMetadata(
            path=rel_path,
            name=clean_name,
            is_dir=False,
            item_id=item_id,
            size=size,
            packed_size=packed,
            modified=mod_time,
            category=cat,
            chunks=chunks,
        )
        meta.items[rel_path] = item_meta
        return item_meta

    def _add_directory_recursive(
        self,
        meta: V2EntryPointMetadata,
        ep_data_dir: Path,
        source_dir: Path,
        parent_subfolder: str = "",
    ) -> None:
        """Recursively add a local folder and all its contents."""
        dir_name = source_dir.name
        rel_dir_path = f"{parent_subfolder}/{dir_name}".strip("/") if parent_subfolder else dir_name

        # Create folder item
        if self.obfuscate_names:
            used_ids = {it.item_id for it in meta.items.values() if it.item_id}
            folder_item_id = generate_unique_folder_id(ep_data_dir, 12, existing_ids=used_ids)
        else:
            folder_item_id = rel_dir_path

        (ep_data_dir / folder_item_id).mkdir(parents=True, exist_ok=True)
        mod_time = datetime.fromtimestamp(source_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        meta.items[rel_dir_path] = V2ItemMetadata(
            path=rel_dir_path,
            name=dir_name,
            is_dir=True,
            item_id=folder_item_id,
            modified=mod_time,
            category="FOLDER",
        )

        for child in source_dir.iterdir():
            if child.is_dir():
                self._add_directory_recursive(meta, ep_data_dir, child, parent_subfolder=rel_dir_path)
            else:
                self._add_single_file(meta, ep_data_dir, child, target_subfolder=rel_dir_path)

    def create_subfolder(self, entry_point_name: str, parent_subfolder: str, new_folder_name: str) -> bool:
        """Create a new folder inside an entry point (instant metadata operation)."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata[entry_point_name]
        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        clean_name = new_folder_name.strip()
        target_path = f"{parent_subfolder}/{clean_name}".strip("/") if parent_subfolder else clean_name

        if self.obfuscate_names:
            used_ids = {it.item_id for it in meta.items.values() if it.item_id}
            folder_item_id = generate_unique_folder_id(ep_data_dir, 12, existing_ids=used_ids)
        else:
            folder_item_id = target_path

        (ep_data_dir / folder_item_id).mkdir(parents=True, exist_ok=True)

        meta.items[target_path] = V2ItemMetadata(
            path=target_path,
            name=clean_name,
            is_dir=True,
            item_id=folder_item_id,
            modified=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            category="FOLDER",
        )

        ep_file = self.entry_points[entry_point_name].archive_file
        self.v2_engine.save_metadata(ep_file, meta, self.password)
        self._cache.pop(entry_point_name, None)
        self.refresh_entry_points()
        log_info(f"Created subfolder '{target_path}' inside '{entry_point_name}.7z'")
        return True

    def delete_item(self, entry_point_name: str, internal_path: str) -> bool:
        """Delete an item or directory and remove its chunks from arc-data without re-archiving other files."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata[entry_point_name]
        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        clean_path = internal_path.strip("/").replace("\\", "/")

        prefix = clean_path + "/"
        to_delete_paths = [
            p for p in meta.items.keys()
            if p == clean_path or p.startswith(prefix)
        ]

        if not to_delete_paths:
            return False

        for p in to_delete_paths:
            item = meta.items.pop(p, None)
            if item and item.item_id:
                item_dir = ep_data_dir / item.item_id
                if item_dir.exists():
                    shutil.rmtree(item_dir, ignore_errors=True)

        if not self.obfuscate_names:
            parent = (ep_data_dir / clean_path).parent
            while parent != ep_data_dir and parent.exists():
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break

        ep_file = self.entry_points[entry_point_name].archive_file
        self.v2_engine.save_metadata(ep_file, meta, self.password)
        self._cache.pop(entry_point_name, None)
        self.refresh_entry_points()
        log_info(f"Deleted '{clean_path}' ({len(to_delete_paths)} items) from '{entry_point_name}.7z'")
        return True

    def rename_item(self, entry_point_name: str, old_path: str, new_path: str) -> bool:
        """Rename an item inside metadata (instant, no chunk data re-encryption needed)."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata[entry_point_name]
        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        clean_old = old_path.strip("/").replace("\\", "/")
        clean_new = new_path.strip("/").replace("\\", "/")

        prefix = clean_old + "/"
        affected_items = [
            (p, it) for p, it in meta.items.items()
            if p == clean_old or p.startswith(prefix)
        ]

        if not affected_items:
            return False

        if not self.obfuscate_names:
            old_disk_dir = ep_data_dir / clean_old
            new_disk_dir = ep_data_dir / clean_new
            if old_disk_dir.exists():
                new_disk_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_disk_dir), str(new_disk_dir))

        for p, item in affected_items:
            del meta.items[p]
            if p == clean_old:
                item.path = clean_new
                item.name = clean_new.split("/")[-1]
                if not self.obfuscate_names:
                    item.item_id = clean_new
            else:
                rel = p[len(clean_old) + 1:]
                item.path = f"{clean_new}/{rel}"
                if not self.obfuscate_names:
                    item.item_id = item.path
            meta.items[item.path] = item

        ep_file = self.entry_points[entry_point_name].archive_file
        self.v2_engine.save_metadata(ep_file, meta, self.password)
        self._cache.pop(entry_point_name, None)
        self.refresh_entry_points()
        log_info(f"Renamed inside '{entry_point_name}.7z': '{clean_old}' -> '{clean_new}'")
        return True

    def move_items(self, entry_point_name: str, item_paths: List[str], target_subfolder: str) -> bool:
        """Move items into a target subfolder (instant metadata update)."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        clean_target = target_subfolder.strip("/").replace("\\", "/")
        for p in item_paths:
            clean_p = p.strip("/").replace("\\", "/")
            item_name = clean_p.split("/")[-1]
            new_path = f"{clean_target}/{item_name}".strip("/") if clean_target else item_name
            self.rename_item(entry_point_name, clean_p, new_path)

        dest_desc = f"/{clean_target}" if clean_target else "root"
        log_info(f"Moved {len(item_paths)} items in '{entry_point_name}.7z' to {dest_desc}")
        return True

    def extract_file_for_preview(self, entry_point_name: str, internal_path: str) -> Optional[Path]:
        """Extract a single file for preview. Files > 1GB cannot be previewed."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata.get(entry_point_name)
        if not meta and entry_point_name in self.entry_points:
            ep_file = self.entry_points[entry_point_name].archive_file
            meta = self._load_or_migrate_entry_point(entry_point_name, ep_file)
            self._v2_metadata[entry_point_name] = meta
        if not meta:
            return None

        clean_path = internal_path.strip("/").replace("\\", "/")
        item = meta.items.get(clean_path)
        if not item or item.is_dir:
            return None

        # Safeguard: files over 1GB cannot be previewed
        if item.size > DEFAULT_CHUNK_SIZE:
            log_warning(f"Preview skipped: '{item.name}' is over 1GB ({item.size} bytes).")
            return None

        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        item_dir = ep_data_dir / item.item_id
        preview_dir = self.get_preview_temp_dir() / item.item_id
        preview_dir.mkdir(parents=True, exist_ok=True)
        dest_file = preview_dir / item.name

        ok = self.v2_engine.extract_file_to_destination(item, item_dir, self.password, dest_file)
        return dest_file if (ok and dest_file.exists()) else None

    def extract_file_for_editing(self, entry_point_name: str, internal_path: str) -> Optional[Path]:
        """Extract a single file into watched staging for external editor. Files > 1GB disabled."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata.get(entry_point_name)
        if not meta and entry_point_name in self.entry_points:
            ep_file = self.entry_points[entry_point_name].archive_file
            meta = self._load_or_migrate_entry_point(entry_point_name, ep_file)
            self._v2_metadata[entry_point_name] = meta
        if not meta:
            return None
        clean_path = internal_path.strip("/").replace("\\", "/")
        item = meta.items.get(clean_path)
        if not item or item.is_dir:
            return None

        # Safeguard: files over 1GB disabled for external editing
        if item.size > DEFAULT_CHUNK_SIZE:
            log_warning(f"External edit skipped: '{item.name}' is over 1GB.")
            return None

        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        item_dir = ep_data_dir / item.item_id
        staging_dir = self.get_edit_staging_dir() / entry_point_name
        staging_dir.mkdir(parents=True, exist_ok=True)
        dest_file = staging_dir / item.name

        ok = self.v2_engine.extract_file_to_destination(item, item_dir, self.password, dest_file)
        return dest_file if (ok and dest_file.exists()) else None

    def update_file_from_disk(
        self,
        entry_point_name: str,
        internal_path: str,
        source_disk_file: Path,
    ) -> bool:
        """Update an existing file directly from disk without re-archiving other files."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata[entry_point_name]
        clean_path = internal_path.strip("/").replace("\\", "/")
        item = meta.items.get(clean_path)
        if not item or item.is_dir or not source_disk_file.exists():
            return False

        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        item_dir = ep_data_dir / item.item_id

        # Clean existing chunks
        if item_dir.exists():
            shutil.rmtree(item_dir, ignore_errors=True)

        size, packed, chunks = self.v2_engine.chunk_and_encrypt_file(
            source_disk_file, item_dir, self.password
        )

        item.size = size
        item.packed_size = packed
        item.chunks = chunks
        item.modified = datetime.fromtimestamp(source_disk_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        ep_file = self.entry_points[entry_point_name].archive_file
        self.v2_engine.save_metadata(ep_file, meta, self.password)
        self._cache.pop(entry_point_name, None)
        self.refresh_entry_points()
        log_info(f"Updated '{internal_path}' in '{entry_point_name}.7z'")
        return True

    def update_file_content(
        self,
        entry_point_name: str,
        internal_path: str,
        content: Union[str, bytes],
    ) -> bool:
        """Update an existing file with new string or byte content."""
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

    def export_entry_point(self, entry_point_name: str, dest_dir: Path) -> bool:
        """Export an entire entry point and all its subfolders/files into dest_dir."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        if entry_point_name not in self.entry_points:
            raise ValueError(f"Entry point '{entry_point_name}' not found.")

        meta = self._v2_metadata.get(entry_point_name)
        if not meta:
            ep_file = self.entry_points[entry_point_name].archive_file
            meta = self._load_or_migrate_entry_point(entry_point_name, ep_file)
            self._v2_metadata[entry_point_name] = meta

        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        all_ok = True
        for p, item in meta.items.items():
            clean_p = p.strip("/").replace("\\", "/")
            target_path = dest_dir / clean_p
            if item.is_dir:
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                item_dir = ep_data_dir / item.item_id
                if not self.v2_engine.extract_file_to_destination(item, item_dir, self.password, target_path):
                    all_ok = False

        log_info(f"Exported entire entry point '{entry_point_name}' ({len(meta.items)} items) to {dest_dir}")
        return all_ok

    def export_items(self, entry_point_name: str, internal_paths: List[str], dest_dir: Path) -> bool:
        """Export selected items from V2 entry point, reassembling any shredded chunks."""
        if not self.is_unlocked:
            raise VaultUnlockError("Vault is locked.")

        meta = self._v2_metadata.get(entry_point_name)
        if not meta:
            ep_file = self.entry_points[entry_point_name].archive_file
            meta = self._load_or_migrate_entry_point(entry_point_name, ep_file)
            self._v2_metadata[entry_point_name] = meta

        clean_paths = [p.strip("/").replace("\\", "/") for p in internal_paths]
        # If internal_paths is empty or specifies the entry point root/itself:
        if not internal_paths or "" in clean_paths or entry_point_name in clean_paths:
            target_dir = dest_dir if dest_dir.name == entry_point_name else (dest_dir / entry_point_name)
            return self.export_entry_point(entry_point_name, target_dir)

        ep_data_dir = self.arc_data_dir / meta.ep_dir_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        targets = clean_paths
        all_ok = True

        for clean_p in targets:
            item = meta.items.get(clean_p)
            if not item:
                continue

            if item.is_dir:
                # Export folder and all its contents
                folder_dest = dest_dir / item.name
                folder_dest.mkdir(parents=True, exist_ok=True)
                prefix = clean_p + "/"
                child_paths = [cp for cp in meta.items.keys() if cp.startswith(prefix)]
                for cp in child_paths:
                    c_item = meta.items[cp]
                    if c_item.is_dir:
                        rel = cp[len(clean_p) + 1:]
                        (folder_dest / rel).mkdir(parents=True, exist_ok=True)
                    else:
                        rel = cp[len(clean_p) + 1:]
                        c_file = folder_dest / rel
                        c_item_dir = ep_data_dir / c_item.item_id
                        if not self.v2_engine.extract_file_to_destination(c_item, c_item_dir, self.password, c_file):
                            all_ok = False
            else:
                target_file = dest_dir / item.name
                item_dir = ep_data_dir / item.item_id
                if not self.v2_engine.extract_file_to_destination(item, item_dir, self.password, target_file):
                    all_ok = False

        log_info(f"Exported {len(targets)} items from '{entry_point_name}' to {dest_dir}")
        return all_ok
