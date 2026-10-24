"""Main application window for ArcVault."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arc_vault.config import AppConfig
from arc_vault.core.models import ArchiveItem, FileCategory
from arc_vault.core.sevenzip import SevenZip, SevenZipExecutableNotFoundError
from arc_vault.core.vault import Vault
from arc_vault.gui.breadcrumbs import BreadcrumbBar
from arc_vault.gui.file_view import FileExplorerView
from arc_vault.gui.icons import IconProvider
from arc_vault.gui.preview_panel import PreviewPanel, format_size
from arc_vault.gui.sidebar import VaultSidebar
from arc_vault.gui.theme import get_stylesheet
from arc_vault.gui.vault_dialog import CreateVaultDialog, UnlockVaultDialog
from arc_vault.gui.workers import AddFilesWorker, ExportFilesWorker, ExtractPreviewWorker, LoadItemsWorker


class MainWindow(QMainWindow):
    """Main window integrating sidebar, breadcrumbs, file explorer, and preview panel."""

    def __init__(self, config: AppConfig, auto_unlock_last: bool = False) -> None:
        super().__init__()
        self.config = config
        self.dark_mode: bool = (config.theme != "light")
        self.sevenzip = SevenZip(override_path=config.sevenzip_override_path)
        self.vault: Optional[Vault] = None
        self.active_entry_point: str = ""
        self.current_subfolder: str = ""

        # Workers
        self._load_worker: Optional[LoadItemsWorker] = None
        self._preview_worker: Optional[ExtractPreviewWorker] = None
        self._add_worker: Optional[AddFilesWorker] = None
        self._export_worker: Optional[ExportFilesWorker] = None

        self.setWindowTitle("ArcVault - Encrypted Archive Explorer")
        self.resize(1150, 720)
        self.setMinimumSize(850, 500)

        # Set App Window Icon
        icon_path = Path(__file__).parent.parent / "resources" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._apply_theme()

        # Load last opened vault if exists
        if self.config.last_selected_vault_path:
            last_p = Path(self.config.last_selected_vault_path)
            if last_p.exists():
                self.open_vault_by_path(last_p, prompt_unlock=auto_unlock_last)

    def _build_ui(self) -> None:
        """Construct toolbar, panels, and status bar."""
        # Central Splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 1. Left Sidebar
        self.sidebar = VaultSidebar(self.config, self.main_splitter)
        self.sidebar.vault_selected.connect(lambda p: self.open_vault_by_path(p, prompt_unlock=True))
        self.sidebar.entry_point_selected.connect(self._on_entry_point_selected)
        self.sidebar.create_vault_requested.connect(self._on_create_vault)
        self.sidebar.open_vault_requested.connect(self._on_open_existing_vault)
        self.sidebar.remove_vault_requested.connect(self._on_remove_vault)
        self.sidebar.lock_vault_requested.connect(self.lock_vault)
        self.sidebar.create_entry_point_requested.connect(self._on_create_entry_point)
        self.sidebar.rename_entry_point_requested.connect(self._on_rename_entry_point)
        self.sidebar.delete_entry_point_requested.connect(self._on_delete_entry_point)
        self.main_splitter.addWidget(self.sidebar)

        # 2. Center Explorer (Breadcrumbs + File View)
        self.center_widget = QWidget(self.main_splitter)
        center_layout = QVBoxLayout(self.center_widget)
        center_layout.setContentsMargins(8, 8, 8, 8)
        center_layout.setSpacing(6)

        self.breadcrumbs = BreadcrumbBar(self.center_widget)
        self.breadcrumbs.path_changed.connect(self._on_breadcrumb_nav)
        self.breadcrumbs.refresh_requested.connect(self.refresh_current_view)
        center_layout.addWidget(self.breadcrumbs)

        self.file_view = FileExplorerView(self.center_widget)
        self.file_view.item_selected.connect(self._on_file_selected)
        self.file_view.item_double_clicked.connect(self._on_file_double_clicked)
        self.file_view.files_dropped.connect(self._on_files_dropped)
        self.file_view.add_files_requested.connect(self._on_add_files_action)
        self.file_view.create_folder_requested.connect(self._on_create_folder_action)
        self.file_view.export_requested.connect(self._on_export_action)
        self.file_view.delete_requested.connect(self._on_delete_action)
        self.file_view.rename_requested.connect(self._on_rename_action)
        center_layout.addWidget(self.file_view)

        self.main_splitter.addWidget(self.center_widget)

        # 3. Right Preview Panel
        self.preview_panel = PreviewPanel(self.main_splitter)
        self.preview_panel.export_requested.connect(lambda item: self._on_export_action([item]))
        self.main_splitter.addWidget(self.preview_panel)

        # Splitter sizing ratio: 220px sidebar, rest center, 320px preview
        self.main_splitter.setSizes([220, 580, 350])
        self.setCentralWidget(self.main_splitter)

        # Toolbar
        self._build_toolbar()

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select or create an encrypted vault to begin.")

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Main Toolbar", self)
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        # Add Files button
        self.act_add_files = QAction("Add Files", self)
        self.act_add_files.setToolTip("Add and encrypt files into active folder")
        self.act_add_files.triggered.connect(self._on_add_files_action)
        self.toolbar.addAction(self.act_add_files)

        # New Folder / Entry Point button
        self.act_new_folder = QAction("New Folder", self)
        self.act_new_folder.setToolTip("Create new directory (or entry point at root)")
        self.act_new_folder.triggered.connect(self._on_create_folder_action)
        self.toolbar.addAction(self.act_new_folder)

        # Export button
        self.act_export = QAction("Export Selected", self)
        self.act_export.setToolTip("Export selected files/folders to local folder")
        self.act_export.triggered.connect(lambda: self._on_export_action(self.file_view.get_selected_items()))
        self.toolbar.addAction(self.act_export)

        # Delete button
        self.act_delete = QAction("Delete", self)
        self.act_delete.setToolTip("Delete selected items from archive")
        self.act_delete.triggered.connect(lambda: self._on_delete_action(self.file_view.get_selected_items()))
        self.toolbar.addAction(self.act_delete)

        self.toolbar.addSeparator()

        # Lock Vault
        self.act_lock = QAction("Lock Vault", self)
        self.act_lock.setToolTip("Lock vault and purge memory keys")
        self.act_lock.triggered.connect(self.lock_vault)
        self.toolbar.addAction(self.act_lock)

        # Spacer to push theme and preview toggle to right
        spacer = QWidget(self)
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy().Preferred)
        self.toolbar.addWidget(spacer)

        # Theme Toggle
        self.act_theme = QAction("Theme", self)
        self.act_theme.setToolTip("Toggle Light / Dark mode")
        self.act_theme.triggered.connect(self._toggle_theme)
        self.toolbar.addAction(self.act_theme)

        # Toggle Preview Panel
        self.act_preview_toggle = QAction("Preview Panel", self)
        self.act_preview_toggle.setToolTip("Toggle preview panel visibility")
        self.act_preview_toggle.triggered.connect(self._toggle_preview_panel)
        self.toolbar.addAction(self.act_preview_toggle)

        self._update_toolbar_state()

    def _update_toolbar_state(self) -> None:
        has_unlocked_vault = bool(self.vault and self.vault.is_unlocked)
        self.act_add_files.setEnabled(has_unlocked_vault and bool(self.active_entry_point))
        self.act_new_folder.setEnabled(has_unlocked_vault)
        self.act_export.setEnabled(has_unlocked_vault)
        self.act_delete.setEnabled(has_unlocked_vault)
        self.act_lock.setEnabled(has_unlocked_vault)

    def _apply_theme(self) -> None:
        qss = get_stylesheet(self.dark_mode)
        self.setStyleSheet(qss)
        IconProvider.clear_cache()

        # Update icons
        self.act_add_files.setIcon(IconProvider.get_icon("upload", dark_mode=self.dark_mode, size=18))
        self.act_new_folder.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=18))
        self.act_export.setIcon(IconProvider.get_icon("download", dark_mode=self.dark_mode, size=18))
        self.act_delete.setIcon(IconProvider.get_icon("trash", dark_mode=self.dark_mode, size=18))
        self.act_lock.setIcon(IconProvider.get_icon("vault", dark_mode=self.dark_mode, size=18))
        self.act_theme.setIcon(
            IconProvider.get_icon("sun" if self.dark_mode else "moon", dark_mode=self.dark_mode, size=18)
        )
        self.act_preview_toggle.setIcon(IconProvider.get_icon("preview", dark_mode=self.dark_mode, size=18))

        self.sidebar.set_theme(self.dark_mode)
        self.breadcrumbs.set_theme(self.dark_mode)
        self.file_view.set_theme(self.dark_mode)
        self.preview_panel.set_theme(self.dark_mode)

    def _toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self.config.theme = "dark" if self.dark_mode else "light"
        self.config.save()
        self._apply_theme()

    def _toggle_preview_panel(self) -> None:
        self.preview_panel.setVisible(not self.preview_panel.isVisible())

    # --- Vault Operations ---

    def open_vault_by_path(self, path: Path, prompt_unlock: bool = True) -> None:
        """Select a vault by its filesystem path."""
        if not path.exists():
            QMessageBox.warning(self, "Vault Not Found", f"Directory '{path}' does not exist.")
            self.config.remove_vault(str(path))
            self.sidebar.refresh_vaults_list()
            return

        if self.vault and self.vault.root_dir == path and self.vault.is_unlocked:
            return  # Already open and unlocked

        try:
            self.vault = Vault(path, self.sevenzip)
        except SevenZipExecutableNotFoundError as e:
            QMessageBox.critical(self, "7-Zip Not Found", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Vault Error", f"Failed to initialize vault: {e}")
            return

        self.config.add_or_update_vault(str(path), self.vault.metadata.name if self.vault.metadata else path.name)
        self.sidebar.set_current_vault(self.vault)
        self._update_toolbar_state()

        if prompt_unlock:
            dlg = UnlockVaultDialog(self.vault, self, dark_mode=self.dark_mode)
            if dlg.exec() == UnlockVaultDialog.DialogCode.Accepted:
                self.sidebar.set_current_vault(self.vault)
                self._update_toolbar_state()
                self.active_entry_point = ""
                self.current_subfolder = ""
                self.refresh_current_view()
                self.status_bar.showMessage(
                    f"Vault '{self.vault.metadata.name if self.vault.metadata else 'Vault'}' unlocked."
                )
            else:
                self.lock_vault()

    def lock_vault(self) -> None:
        """Lock current vault and clear sensitive state."""
        if self.vault:
            self.vault.lock()
        self.active_entry_point = ""
        self.current_subfolder = ""
        self.sidebar.set_current_vault(self.vault)
        self.breadcrumbs.set_path("", "")
        self.file_view.set_items([])
        self.preview_panel.set_empty()
        self._update_toolbar_state()
        self.status_bar.showMessage("Vault locked.")

    def _on_create_vault(self) -> None:
        dlg = CreateVaultDialog(self, dark_mode=self.dark_mode)
        if dlg.exec() == CreateVaultDialog.DialogCode.Accepted and dlg.created_vault_path:
            self.config.add_or_update_vault(str(dlg.created_vault_path), dlg.created_vault_name)
            self.open_vault_by_path(dlg.created_vault_path, prompt_unlock=False)
            # Re-read vault as unlocked
            self.vault = Vault(dlg.created_vault_path, self.sevenzip)
            # Since create_vault in dialog already created it with password, prompt unlock
            dlg_unlock = UnlockVaultDialog(self.vault, self, dark_mode=self.dark_mode)
            if dlg_unlock.exec() == UnlockVaultDialog.DialogCode.Accepted:
                self.sidebar.set_current_vault(self.vault)
                self._update_toolbar_state()
                self.refresh_current_view()

    def _on_open_existing_vault(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Existing Vault Folder", str(Path.home()))
        if folder:
            p = Path(folder)
            self.open_vault_by_path(p, prompt_unlock=True)

    def _on_remove_vault(self, vault_path: Path) -> None:
        res = QMessageBox.question(
            self,
            "Remove Vault",
            f"Remove '{vault_path.name}' from known vaults list?\n\n(Files on disk will NOT be deleted.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            if self.vault and self.vault.root_dir == vault_path:
                self.lock_vault()
                self.vault = None
                self.sidebar.set_current_vault(None)
            self.config.remove_vault(str(vault_path))
            self.sidebar.refresh_vaults_list()

    # --- Navigation & Entry Points ---

    def _on_entry_point_selected(self, ep_name: str) -> None:
        self.active_entry_point = ep_name
        self.current_subfolder = ""
        self.sidebar.set_active_entry_point(ep_name)
        self.refresh_current_view()

    def _on_breadcrumb_nav(self, ep_name: str, subfolder: str) -> None:
        self.active_entry_point = ep_name
        self.current_subfolder = subfolder
        self.sidebar.set_active_entry_point(ep_name)
        self.refresh_current_view()

    def refresh_current_view(self) -> None:
        """Reload file list for active entry point and subfolder."""
        if not self.vault or not self.vault.is_unlocked:
            self.file_view.set_items([])
            self.breadcrumbs.set_path("", "")
            self.preview_panel.set_empty()
            return

        self.breadcrumbs.set_path(self.active_entry_point, self.current_subfolder)
        self._update_toolbar_state()

        if not self.active_entry_point:
            # Viewing Vault Root -> Display all Entry Point archives as top-level folders!
            items: List[ArchiveItem] = []
            for ep_name, ep in self.vault.entry_points.items():
                items.append(
                    ArchiveItem(
                        name=f"{ep_name}",
                        path=ep_name,
                        is_dir=True,
                        size=ep.size_on_disk,
                        packed_size=ep.size_on_disk,
                        entry_point_name=ep_name,
                        category=FileCategory.ENTRY_POINT,
                    )
                )
            self.file_view.set_items(items)
            self.status_bar.showMessage(f"Vault Root: {len(items)} entry point archives.")
            return

        # Viewing inside an Entry Point archive
        self.status_bar.showMessage(f"Reading '{self.active_entry_point}.7z'...")
        self._load_worker = LoadItemsWorker(self.vault, self.active_entry_point, self.current_subfolder)
        self._load_worker.items_loaded.connect(self._on_items_loaded)
        self._load_worker.start()

    def _on_items_loaded(self, items: list, error_msg: str) -> None:
        if error_msg:
            self.status_bar.showMessage(f"Error loading archive: {error_msg}")
            QMessageBox.warning(self, "Archive Error", error_msg)
            return

        self.file_view.set_items(items)
        total_size = sum(i.size for i in items if not i.is_dir)
        folder_str = f"/{self.current_subfolder}" if self.current_subfolder else ""
        self.status_bar.showMessage(
            f"{self.active_entry_point}{folder_str} • {len(items)} items ({format_size(total_size)})"
        )

    # --- File Explorer Interactions ---

    def _on_file_selected(self, item: Optional[ArchiveItem]) -> None:
        if not item or item.is_dir:
            self.preview_panel.set_empty()
            return

        # Trigger background preview extraction
        self._preview_worker = ExtractPreviewWorker(self.vault, item.entry_point_name, item.path)
        self._preview_worker.finished.connect(
            lambda path, err, it=item: self._on_preview_extracted(it, path, err)
        )
        self._preview_worker.start()

    def _on_preview_extracted(self, item: ArchiveItem, local_path: Optional[Path], err: str) -> None:
        if local_path and local_path.exists():
            self.preview_panel.show_preview(item, local_path)
        else:
            self.preview_panel.set_empty()

    def _on_file_double_clicked(self, item: ArchiveItem) -> None:
        if item.category == FileCategory.ENTRY_POINT or (not self.active_entry_point and item.is_dir):
            # Double clicked an entry point in Vault Root -> enter it!
            self.active_entry_point = item.entry_point_name or item.name
            self.current_subfolder = ""
            self.sidebar.set_active_entry_point(self.active_entry_point)
            self.refresh_current_view()
        elif item.is_dir:
            # Double clicked subfolder inside active entry point
            self.current_subfolder = item.path.strip("/")
            self.refresh_current_view()
        else:
            # Double clicked file -> preview already selected, or open external
            self._on_file_selected(item)

    def _on_files_dropped(self, files: List[Path]) -> None:
        """Handle drag and drop of files from OS into active folder."""
        if not self.vault or not self.vault.is_unlocked:
            return

        if not self.active_entry_point:
            QMessageBox.information(
                self,
                "Select Entry Point",
                "Please select an entry point category archive (e.g. photos or documents) to import files into.",
            )
            return

        self._start_add_files(files)

    def _on_add_files_action(self) -> None:
        if not self.vault or not self.vault.is_unlocked or not self.active_entry_point:
            return

        files, _ = QFileDialog.getOpenFileNames(self, f"Add Files to '{self.active_entry_point}'", str(Path.home()))
        if files:
            path_objs = [Path(f) for f in files]
            self._start_add_files(path_objs)

    def _start_add_files(self, files: List[Path]) -> None:
        self.status_bar.showMessage(f"Encrypting and adding {len(files)} items into {self.active_entry_point}.7z...")
        self._add_worker = AddFilesWorker(
            self.vault, self.active_entry_point, files, subfolder=self.current_subfolder
        )
        self._add_worker.finished.connect(self._on_add_finished)
        self._add_worker.start()

    def _on_add_finished(self, success: bool, error_msg: str) -> None:
        if success:
            self.status_bar.showMessage("Files encrypted and added successfully.")
            self.refresh_current_view()
        else:
            QMessageBox.critical(self, "Encryption Failed", f"Failed to add files: {error_msg}")
            self.status_bar.showMessage("Failed to add files.")

    def _on_create_folder_action(self) -> None:
        if not self.vault or not self.vault.is_unlocked:
            return

        if not self.active_entry_point:
            # In Vault Root -> Prompt to create new Entry Point .7z archive!
            self._on_create_entry_point()
            return

        # Inside an entry point -> Create subfolder
        name, ok = QInputDialog.getText(
            self, "New Folder", f"Create new folder inside '{self.active_entry_point}':"
        )
        if ok and name.strip():
            clean_name = name.strip()
            ok_res = self.vault.create_subfolder(self.active_entry_point, self.current_subfolder, clean_name)
            if ok_res:
                self.refresh_current_view()
            else:
                QMessageBox.warning(self, "Error", "Failed to create folder.")

    def _on_create_entry_point(self) -> None:
        if not self.vault or not self.vault.is_unlocked:
            return

        name, ok = QInputDialog.getText(
            self, "New Entry Point", "Enter entry point category name (e.g. photos, work):"
        )
        if ok and name.strip():
            clean_name = name.strip().replace(".7z", "")
            try:
                self.vault.create_entry_point(clean_name)
                self.sidebar.refresh_entry_points()
                self.active_entry_point = clean_name
                self.current_subfolder = ""
                self.refresh_current_view()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create entry point: {e}")

    def _on_rename_entry_point(self, old_name: str) -> None:
        if not self.vault or not self.vault.is_unlocked:
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Entry Point", f"Enter new name for '{old_name}':", text=old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            clean_new = new_name.strip().replace(".7z", "")
            try:
                self.vault.rename_entry_point(old_name, clean_new)
                self.sidebar.refresh_entry_points()
                if self.active_entry_point == old_name:
                    self.active_entry_point = clean_new
                self.refresh_current_view()
            except Exception as e:
                QMessageBox.warning(self, "Rename Error", f"Failed to rename: {e}")

    def _on_delete_entry_point(self, ep_name: str) -> None:
        if not self.vault or not self.vault.is_unlocked:
            return

        res = QMessageBox.question(
            self,
            "Delete Entry Point",
            f"Are you sure you want to permanently delete '{ep_name}.7z' and all its contents?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.vault.delete_entry_point(ep_name)
            self.sidebar.refresh_entry_points()
            if self.active_entry_point == ep_name:
                self.active_entry_point = ""
                self.current_subfolder = ""
            self.refresh_current_view()

    def _on_export_action(self, items: List[ArchiveItem]) -> None:
        if not items or not self.vault or not self.vault.is_unlocked:
            return

        dest = QFileDialog.getExistingDirectory(self, "Select Export Destination Directory", str(Path.home()))
        if not dest:
            return

        dest_path = Path(dest)
        internal_paths = [i.path for i in items]
        ep_name = items[0].entry_point_name or self.active_entry_point

        self.status_bar.showMessage(f"Decrypting and exporting {len(items)} items...")
        self._export_worker = ExportFilesWorker(self.vault, ep_name, internal_paths, dest_path)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.start()

    def _on_export_finished(self, success: bool, error_msg: str) -> None:
        if success:
            self.status_bar.showMessage("Export completed successfully.")
            QMessageBox.information(self, "Export Complete", "Selected files were exported successfully.")
        else:
            QMessageBox.critical(self, "Export Failed", f"Failed to export files: {error_msg}")
            self.status_bar.showMessage("Export failed.")

    def _on_delete_action(self, items: List[ArchiveItem]) -> None:
        if not items or not self.vault or not self.vault.is_unlocked:
            return

        if not self.active_entry_point:
            # Deleting entry points from Vault Root
            for item in items:
                self._on_delete_entry_point(item.entry_point_name or item.name)
            return

        res = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {len(items)} item(s) from '{self.active_entry_point}.7z'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        for it in items:
            self.vault.delete_item(self.active_entry_point, it.path)

        self.preview_panel.set_empty()
        self.refresh_current_view()

    def _on_rename_action(self, item: ArchiveItem) -> None:
        if not self.vault or not self.vault.is_unlocked:
            return

        if not self.active_entry_point:
            self._on_rename_entry_point(item.entry_point_name or item.name)
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Item", f"Enter new name for '{item.name}':", text=item.name
        )
        if ok and new_name.strip() and new_name.strip() != item.name:
            clean_name = new_name.strip()
            # Construct target path inside archive
            parent = "/".join(item.path.split("/")[:-1])
            new_path = f"{parent}/{clean_name}".strip("/") if parent else clean_name
            ok_rn = self.vault.rename_item(self.active_entry_point, item.path, new_path)
            if ok_rn:
                self.refresh_current_view()
            else:
                QMessageBox.warning(self, "Rename Error", "Failed to rename item in archive.")

    def closeEvent(self, event) -> None:
        """Lock and clean up on close."""
        if self.vault:
            self.vault.lock()
        event.accept()
