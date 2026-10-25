"""Asynchronous background worker threads for non-blocking 7z vault operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from vaultables.core.models import ArchiveItem, FileCategory
from vaultables.core.vault import Vault


class UnlockWorker(QThread):
    """Worker thread to test password and unlock vault."""

    finished = pyqtSignal(bool, str)  # (success, error_message)

    def __init__(self, vault: Vault, password: str) -> None:
        super().__init__()
        self.vault = vault
        self.password = password

    def run(self) -> None:
        try:
            success = self.vault.unlock(self.password)
            if success:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "Incorrect password. Please verify and try again.")
        except Exception as e:
            self.finished.emit(False, str(e))


class LoadItemsWorker(QThread):
    """Worker thread to retrieve directory listing."""

    items_loaded = pyqtSignal(list, str)  # (List[ArchiveItem], error_message)

    def __init__(self, vault: Vault, entry_point_name: str, subfolder: str = "") -> None:
        super().__init__()
        self.vault = vault
        self.entry_point_name = entry_point_name
        self.subfolder = subfolder

    def run(self) -> None:
        try:
            items = self.vault.get_items_in_directory(self.entry_point_name, self.subfolder)
            self.items_loaded.emit(items, "")
        except Exception as e:
            self.items_loaded.emit([], str(e))


class AddFilesWorker(QThread):
    """Worker thread to encrypt and add files to an entry point archive."""

    finished = pyqtSignal(bool, str)  # (success, error_message)

    def __init__(
        self,
        vault: Vault,
        entry_point_name: str,
        files: List[Path],
        subfolder: str = "",
    ) -> None:
        super().__init__()
        self.vault = vault
        self.entry_point_name = entry_point_name
        self.files = files
        self.subfolder = subfolder

    def run(self) -> None:
        try:
            ok = self.vault.add_files(self.entry_point_name, self.files, self.subfolder)
            if ok:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "Could not add files to archive.")
        except Exception as e:
            self.finished.emit(False, str(e))


class UpdateFileWorker(QThread):
    """Worker thread to update an existing file inside the 7z archive quickly."""

    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        vault: Vault,
        entry_point_name: str,
        internal_path: str,
        content_or_file: Union[str, bytes, Path],
    ) -> None:
        super().__init__()
        self.vault = vault
        self.entry_point_name = entry_point_name
        self.internal_path = internal_path
        self.content_or_file = content_or_file

    def run(self) -> None:
        try:
            if isinstance(self.content_or_file, Path):
                ok = self.vault.update_file_from_disk(
                    self.entry_point_name, self.internal_path, self.content_or_file
                )
            else:
                ok = self.vault.update_file_content(
                    self.entry_point_name, self.internal_path, self.content_or_file
                )
            self.finished.emit(ok, "" if ok else "Failed to update archive.")
        except Exception as e:
            self.finished.emit(False, str(e))


class SearchWorker(QThread):
    """Worker thread to perform fast recursive search across vault archives."""

    results_found = pyqtSignal(list, str)  # (List[ArchiveItem], query)

    def __init__(
        self,
        vault: Vault,
        query: str,
        entry_point_name: Optional[str] = None,
        subfolder: str = "",
        recursive: bool = True,
    ) -> None:
        super().__init__()
        self.vault = vault
        self.query = query
        self.entry_point_name = entry_point_name
        self.subfolder = subfolder
        self.recursive = recursive

    def run(self) -> None:
        try:
            if not self.vault or not self.vault.is_unlocked or not self.query.strip():
                self.results_found.emit([], self.query)
                return
            results = self.vault.search_items(
                query=self.query,
                entry_point_name=self.entry_point_name,
                subfolder_prefix=self.subfolder,
                recursive=self.recursive,
            )
            self.results_found.emit(results, self.query)
        except Exception:
            self.results_found.emit([], self.query)


class ExtractPreviewWorker(QThread):
    """Worker thread to extract a file for internal preview."""

    finished = pyqtSignal(object, str)  # (Optional[Path], error_message)

    def __init__(self, vault: Vault, entry_point_name: str, internal_path: str) -> None:
        super().__init__()
        self.vault = vault
        self.entry_point_name = entry_point_name
        self.internal_path = internal_path

    def run(self) -> None:
        try:
            path = self.vault.extract_file_for_preview(self.entry_point_name, self.internal_path)
            self.finished.emit(path, "")
        except Exception as e:
            self.finished.emit(None, str(e))


class ExportFilesWorker(QThread):
    """Worker thread to export files or entire entry points to local directory."""

    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        vault: Vault,
        entry_point_name_or_items: Any,
        internal_paths_or_dest: Any = None,
        dest_dir: Optional[Path] = None,
        active_entry_point: str = "",
    ) -> None:
        super().__init__()
        self.vault = vault
        self.active_entry_point = active_entry_point

        if isinstance(entry_point_name_or_items, list) and isinstance(internal_paths_or_dest, Path):
            # Signature: (vault, items: List[ArchiveItem], dest_dir: Path)
            self.items: Optional[List[ArchiveItem]] = entry_point_name_or_items
            self.dest_dir: Path = internal_paths_or_dest
            self.entry_point_name: str = ""
            self.internal_paths: List[str] = []
        else:
            # Signature: (vault, entry_point_name: str, internal_paths: List[str], dest_dir: Path)
            self.items = None
            self.entry_point_name = str(entry_point_name_or_items)
            self.internal_paths = internal_paths_or_dest or []
            self.dest_dir = dest_dir if dest_dir else Path.home()

    def run(self) -> None:
        try:
            if self.items is not None:
                all_ok = True
                # 1. Process whole entry points
                ep_items = [it for it in self.items if it.category == FileCategory.ENTRY_POINT]
                for ep_it in ep_items:
                    ep_name = ep_it.entry_point_name or ep_it.name
                    target = self.dest_dir if self.dest_dir.name == ep_name else (self.dest_dir / ep_name)
                    if not self.vault.export_entry_point(ep_name, target):
                        all_ok = False

                # 2. Process regular items (grouped by entry_point_name)
                regular_items = [it for it in self.items if it.category != FileCategory.ENTRY_POINT]
                if regular_items:
                    ep_groups: Dict[str, List[str]] = {}
                    for it in regular_items:
                        ep = it.entry_point_name or self.active_entry_point
                        if ep:
                            ep_groups.setdefault(ep, []).append(it.path)

                    for ep, paths in ep_groups.items():
                        if not self.vault.export_items(ep, paths, self.dest_dir):
                            all_ok = False

                self.finished.emit(all_ok, "" if all_ok else "One or more items could not be exported.")
            else:
                ok = self.vault.export_items(self.entry_point_name, self.internal_paths, self.dest_dir)
                self.finished.emit(ok, "" if ok else "Extraction failed.")
        except Exception as e:
            self.finished.emit(False, str(e))
