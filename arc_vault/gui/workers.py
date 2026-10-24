"""Asynchronous background worker threads for non-blocking 7z vault operations."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from arc_vault.core.models import ArchiveItem
from arc_vault.core.vault import Vault


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
    """Worker thread to export files from archive to local directory."""

    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        vault: Vault,
        entry_point_name: str,
        internal_paths: List[str],
        dest_dir: Path,
    ) -> None:
        super().__init__()
        self.vault = vault
        self.entry_point_name = entry_point_name
        self.internal_paths = internal_paths
        self.dest_dir = dest_dir

    def run(self) -> None:
        try:
            ok = self.vault.export_items(self.entry_point_name, self.internal_paths, self.dest_dir)
            self.finished.emit(ok, "" if ok else "Extraction failed.")
        except Exception as e:
            self.finished.emit(False, str(e))
