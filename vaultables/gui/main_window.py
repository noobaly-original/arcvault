"""Main application window for Vaultables with fast archive editing and cross-platform drag-and-drop."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PyQt6.QtCore import QByteArray, QFileSystemWatcher, QMimeData, QPoint, QSize, Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QDrag, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QCheckBox,
    QDialog,
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

from vaultables.config import AppConfig
from vaultables.core.credentials import (
    delete_vault_password,
    retrieve_vault_password,
    store_vault_password,
)
from vaultables.core.models import ArchiveItem, FileCategory, is_ignorable_system_file
from vaultables.core.sevenzip import SevenZip, SevenZipExecutableNotFoundError
from vaultables.core.vault import Vault
from vaultables.gui.breadcrumbs import BreadcrumbBar
from vaultables.gui.file_view import FileExplorerView
from vaultables.gui.icons import IconProvider
from vaultables.gui.logs_panel import LogsPanel
from vaultables.gui.preview_panel import PreviewPanel, format_size
from vaultables.gui.sidebar import VaultSidebar
from vaultables.gui.theme import get_stylesheet
from vaultables.gui.vault_dialog import CreateVaultDialog, UnlockVaultDialog, CreateEntryPointDialog
from vaultables.gui.workers import (
    AddFilesWorker,
    ExportFilesWorker,
    ExtractPreviewWorker,
    LoadItemsWorker,
    SearchWorker,
    UpdateFileWorker,
)


class MainWindow(QMainWindow):
    """Main window integrating sidebar, breadcrumbs, file explorer, editing, and preview panel."""

    def __init__(self, config: AppConfig, auto_unlock_last: bool = False) -> None:
        super().__init__()
        self.config = config
        self.dark_mode: bool = (config.theme != "light")
        self.sevenzip = SevenZip(override_path=config.sevenzip_override_path)
        self.vault: Optional[Vault] = None
        self.active_entry_point: str = ""
        self.current_subfolder: str = ""

        # Workers & Watchers
        self._load_worker: Optional[LoadItemsWorker] = None
        self._preview_worker: Optional[ExtractPreviewWorker] = None
        self._add_worker: Optional[AddFilesWorker] = None
        self._export_worker: Optional[ExportFilesWorker] = None
        self._update_worker: Optional[UpdateFileWorker] = None

        # External Editor Watcher: {str(file_path): (ep_name, internal_path, mtime, hash)}
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self._on_watched_file_changed)
        self._watched_files: Dict[str, Tuple[str, str, float, str]] = {}

        self.setWindowTitle("Vaultables - Encrypted Archive Explorer")
        self.resize(1180, 740)
        self.setMinimumSize(850, 500)

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            icon_path = Path(meipass) / "vaultables" / "resources" / "icon.png"
        else:
            icon_path = Path(__file__).parent.parent / "resources" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._apply_theme()
        self._restore_window_state()

        if self.config.last_selected_vault_path:
            last_p = Path(self.config.last_selected_vault_path)
            if last_p.exists():
                self.open_vault_by_path(last_p, prompt_unlock=auto_unlock_last)

    def _build_ui(self) -> None:
        """Construct toolbar, panels, and status bar."""
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 1. Left Sidebar
        self.sidebar = VaultSidebar(self.config, self.main_splitter)
        self.sidebar.vault_selected.connect(lambda p: self.open_vault_by_path(p, prompt_unlock=True))
        self.sidebar.entry_point_selected.connect(self._on_entry_point_selected)
        self.sidebar.create_vault_requested.connect(self._on_create_vault)
        self.sidebar.open_vault_requested.connect(self._on_open_existing_vault)
        self.sidebar.remove_vault_requested.connect(self._on_remove_vault)
        self.sidebar.rename_vault_display_name_requested.connect(self._on_rename_vault_display_name)
        self.sidebar.lock_vault_requested.connect(self.lock_vault)
        self.sidebar.create_entry_point_requested.connect(self._on_create_entry_point)
        self.sidebar.rename_entry_point_requested.connect(self._on_rename_entry_point)
        self.sidebar.delete_entry_point_requested.connect(self._on_delete_entry_point)
        self.sidebar.files_dropped_on_entry_point.connect(self._on_files_dropped_on_entry_point)
        self.main_splitter.addWidget(self.sidebar)

        # 2. Center Explorer (Breadcrumbs + File View + Logs Pane)
        self.center_widget = QWidget(self.main_splitter)
        center_layout = QVBoxLayout(self.center_widget)
        center_layout.setContentsMargins(8, 8, 8, 8)
        center_layout.setSpacing(6)

        self.breadcrumbs = BreadcrumbBar(self.center_widget)
        self.breadcrumbs.path_changed.connect(self._on_breadcrumb_nav)
        self.breadcrumbs.refresh_requested.connect(lambda: self.refresh_current_view(force_reload=True))
        center_layout.addWidget(self.breadcrumbs)

        self.center_splitter = QSplitter(Qt.Orientation.Vertical, self.center_widget)
        self.center_splitter.setHandleWidth(4)

        self.file_view = FileExplorerView(self.center_splitter)
        self.file_view.item_selected.connect(self._on_file_selected)
        self.file_view.item_double_clicked.connect(self._on_file_double_clicked)
        self.file_view.files_dropped_on_folder.connect(self._on_files_dropped_on_folder)
        self.file_view.files_dropped_on_entry_point.connect(self._on_files_dropped_on_entry_point)
        self.file_view.files_dropped_root.connect(self._on_files_dropped_root)
        self.file_view.drag_export_requested.connect(self._on_drag_export_requested)
        self.file_view.add_files_requested.connect(self._on_add_files_action)
        self.file_view.create_folder_requested.connect(self._on_create_folder_action)
        self.file_view.export_requested.connect(self._on_export_action)
        self.file_view.delete_requested.connect(self._on_delete_action)
        self.file_view.rename_requested.connect(self._on_rename_action)
        self.file_view.edit_external_requested.connect(self._start_external_editing)
        self.file_view.move_requested.connect(self._on_move_action)
        self.file_view.internal_move_requested.connect(self._on_internal_move_requested)
        self.file_view.search_requested.connect(self._on_search_requested)
        self.file_view.reveal_requested.connect(self._on_reveal_in_vault)
        self.file_view.list_size_changed.connect(self._on_list_size_changed)
        self.file_view.column_widths_changed.connect(self._on_column_widths_changed)
        self.file_view.refresh_requested.connect(lambda: self.refresh_current_view(force_reload=True))

        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(self._focus_search_bar)

        self.refresh_shortcut_f5 = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        self.refresh_shortcut_f5.activated.connect(lambda: self.refresh_current_view(force_reload=True))

        self.refresh_shortcut_cmd_r = QShortcut(QKeySequence(QKeySequence.StandardKey.Refresh), self)
        self.refresh_shortcut_cmd_r.activated.connect(lambda: self.refresh_current_view(force_reload=True))

        self.center_splitter.addWidget(self.file_view)

        self.logs_panel = LogsPanel(self.center_splitter)
        self.logs_panel.hide()
        self.center_splitter.addWidget(self.logs_panel)
        self.center_splitter.setSizes([500, 160])

        center_layout.addWidget(self.center_splitter)

        self.main_splitter.addWidget(self.center_widget)

        # 3. Right Preview & Edit Panel
        self.preview_panel = PreviewPanel(self.main_splitter)
        self.preview_panel.export_requested.connect(lambda item: self._on_export_action([item]))
        self.preview_panel.save_text_requested.connect(self._on_save_in_app_text)
        self.preview_panel.edit_external_requested.connect(self._start_external_editing)
        self.main_splitter.addWidget(self.preview_panel)

        self.main_splitter.setChildrenCollapsible(False)
        self.sidebar.setMinimumWidth(180)
        self.center_widget.setMinimumWidth(320)
        self.preview_panel.setMinimumWidth(260)
        self.main_splitter.setSizes([220, 560, 340])
        self.setCentralWidget(self.main_splitter)

        self._build_toolbar()

        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select or create an encrypted vault to begin.")

        # Progress bar container embedded into status bar
        self.progress_container = QWidget(self)
        prog_layout = QHBoxLayout(self.progress_container)
        prog_layout.setContentsMargins(4, 0, 4, 0)
        prog_layout.setSpacing(8)

        self.progress_label = QLabel(self.progress_container)
        self.progress_label.setStyleSheet("font-size: 11px; font-weight: 500;")
        prog_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar(self.progress_container)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setTextVisible(True)
        prog_layout.addWidget(self.progress_bar)

        self.status_bar.addPermanentWidget(self.progress_container)
        self.progress_container.hide()
        self._task_start_time = None
        self._task_total_bytes = 0

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Main Toolbar", self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.toolbar)

        self.act_add_files = QAction("Add Files", self)
        self.act_add_files.setToolTip("Add and encrypt files into active folder")
        self.act_add_files.triggered.connect(self._on_add_files_action)
        self.toolbar.addAction(self.act_add_files)

        self.act_new_folder = QAction("New Folder", self)
        self.act_new_folder.setToolTip("Create new directory (or entry point at root)")
        self.act_new_folder.triggered.connect(self._on_create_folder_action)
        self.toolbar.addAction(self.act_new_folder)

        self.act_export = QAction("Export Selected", self)
        self.act_export.setToolTip("Export selected files/folders to local folder")
        self.act_export.triggered.connect(lambda: self._on_export_action(self.file_view.get_selected_items()))
        self.toolbar.addAction(self.act_export)

        self.act_delete = QAction("Delete", self)
        self.act_delete.setToolTip("Delete selected items from archive")
        self.act_delete.triggered.connect(lambda: self._on_delete_action(self.file_view.get_selected_items()))
        self.toolbar.addAction(self.act_delete)

        self.toolbar.addSeparator()

        self.act_check_imports = QAction("Check Imports", self)
        self.act_check_imports.setToolTip("Process off-site encrypted .7z files from the vault's 'import/' folder")
        self.act_check_imports.triggered.connect(self._on_check_imports_action)
        self.toolbar.addAction(self.act_check_imports)

        self.act_rename_vault = QAction("Rename Vault", self)
        self.act_rename_vault.setToolTip("Rename vault display name")
        self.act_rename_vault.triggered.connect(lambda: self._on_rename_vault_display_name(self.vault.root_dir if self.vault else None))
        self.toolbar.addAction(self.act_rename_vault)

        self.act_lock = QAction("Lock Vault", self)
        self.act_lock.setToolTip("Lock vault and purge memory keys")
        self.act_lock.triggered.connect(self.lock_vault)
        self.toolbar.addAction(self.act_lock)

        self.toolbar.addSeparator()

        self.chk_store_password = QCheckBox("Store Password", self)
        self.chk_store_password.setToolTip(
            "Store master vault password in secure OS credential manager (Keychain / DPAPI / Secret Service)"
        )
        self.chk_store_password.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_store_password.toggled.connect(self._on_store_password_toggled)
        self.toolbar.addWidget(self.chk_store_password)

        self.toolbar.addSeparator()

        self.act_logs = QAction("Vault Logs", self)
        self.act_logs.setToolTip("Toggle Vault Activity & 7-Zip Logs (Ctrl+L / Cmd+L)")
        self.act_logs.setShortcut(QKeySequence("Ctrl+L"))
        self.act_logs.triggered.connect(self._toggle_logs_panel)
        self.toolbar.addAction(self.act_logs)

        spacer = QWidget(self)
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy().Preferred)
        self.toolbar.addWidget(spacer)

        self.act_theme = QAction("Theme", self)
        self.act_theme.setToolTip("Toggle Light / Dark mode")
        self.act_theme.triggered.connect(self._toggle_theme)
        self.toolbar.addAction(self.act_theme)

        self.act_preview_toggle = QAction("Preview Panel", self)
        self.act_preview_toggle.setToolTip("Toggle preview panel visibility")
        self.act_preview_toggle.triggered.connect(self._toggle_preview_panel)
        self.toolbar.addAction(self.act_preview_toggle)

        self.act_about = QAction("About", self)
        self.act_about.setToolTip("About Vaultables, contributors & special thanks")
        self.act_about.triggered.connect(self._show_about_dialog)
        self.toolbar.addAction(self.act_about)

        self._update_toolbar_state()

    def _update_toolbar_state(self) -> None:
        has_unlocked_vault = bool(self.vault and self.vault.is_unlocked)
        self.act_add_files.setEnabled(has_unlocked_vault and bool(self.active_entry_point))
        self.act_new_folder.setEnabled(has_unlocked_vault)
        self.act_export.setEnabled(has_unlocked_vault)
        self.act_delete.setEnabled(has_unlocked_vault)
        self.act_lock.setEnabled(has_unlocked_vault)
        self.act_rename_vault.setEnabled(has_unlocked_vault)
        self.act_check_imports.setEnabled(has_unlocked_vault)

        self.chk_store_password.setEnabled(has_unlocked_vault)
        self.chk_store_password.blockSignals(True)
        if has_unlocked_vault:
            self.chk_store_password.setChecked(
                self.config.is_password_saved(str(self.vault.root_dir))
            )
        else:
            self.chk_store_password.setChecked(False)
        self.chk_store_password.blockSignals(False)

    def _on_store_password_toggled(self, checked: bool) -> None:
        if not self.vault or not self.vault.is_unlocked:
            return

        vault_path = str(self.vault.root_dir)
        vault_id = self.vault.metadata.vault_id if self.vault.metadata else None

        if checked:
            if self.vault.password:
                success = store_vault_password(vault_path, self.vault.password, vault_id=vault_id)
                if success:
                    self.config.set_password_saved(vault_path, True)
                    self.status_bar.showMessage("Master password securely saved in OS credential manager.", 4000)
                else:
                    self.chk_store_password.blockSignals(True)
                    self.chk_store_password.setChecked(False)
                    self.chk_store_password.blockSignals(False)
                    self.config.set_password_saved(vault_path, False)
                    QMessageBox.warning(
                        self,
                        "Credential Storage Failed",
                        "Could not save master password to the OS credential manager. Please check system permissions.",
                    )
        else:
            delete_vault_password(vault_path, vault_id=vault_id)
            self.config.set_password_saved(vault_path, False)
            self.status_bar.showMessage("Master password removed from OS credential manager.", 4000)

    def _apply_theme(self) -> None:
        qss = get_stylesheet(self.dark_mode)
        self.setStyleSheet(qss)
        IconProvider.clear_cache()

        self.act_add_files.setIcon(IconProvider.get_icon("add_file", dark_mode=self.dark_mode, size=20))
        self.act_new_folder.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=20))
        self.act_export.setIcon(IconProvider.get_icon("export", dark_mode=self.dark_mode, size=20))
        self.act_delete.setIcon(IconProvider.get_icon("trash", dark_mode=self.dark_mode, size=20))
        self.act_check_imports.setIcon(IconProvider.get_icon("archive", dark_mode=self.dark_mode, size=20))
        self.act_rename_vault.setIcon(IconProvider.get_icon("edit", dark_mode=self.dark_mode, size=20))
        self.act_lock.setIcon(IconProvider.get_icon("vault", dark_mode=self.dark_mode, size=20))
        self.act_logs.setIcon(IconProvider.get_icon("logs", dark_mode=self.dark_mode, size=20))
        self.act_theme.setIcon(
            IconProvider.get_icon("sun" if self.dark_mode else "moon", dark_mode=self.dark_mode, size=20)
        )
        self.act_preview_toggle.setIcon(IconProvider.get_icon("preview", dark_mode=self.dark_mode, size=20))
        self.act_about.setIcon(IconProvider.get_icon("info", dark_mode=self.dark_mode, size=20))

        self.sidebar.set_theme(self.dark_mode)
        self.breadcrumbs.set_theme(self.dark_mode)
        self.file_view.set_theme(self.dark_mode)
        self.preview_panel.set_theme(self.dark_mode)
        self.logs_panel.set_theme(self.dark_mode)

    def _toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self.config.theme = "dark" if self.dark_mode else "light"
        self.config.save()
        self._apply_theme()

    def _show_about_dialog(self) -> None:
        from vaultables.gui.about_dialog import AboutDialog
        dlg = AboutDialog(self, dark_mode=self.dark_mode)
        dlg.exec()

    def _toggle_preview_panel(self) -> None:
        sizes = self.main_splitter.sizes()
        is_collapsed = len(sizes) > 2 and sizes[2] < 50
        if self.preview_panel.isHidden() or is_collapsed:
            self.preview_panel.show()
            if is_collapsed:
                sb_w = sizes[0] if sizes[0] > 100 else 220
                preview_w = 340
                total = sum(sizes) if sum(sizes) > 600 else self.main_splitter.width()
                center_w = max(260, total - sb_w - preview_w)
                self.main_splitter.setSizes([sb_w, center_w, preview_w])
        else:
            self.preview_panel.hide()

    def _toggle_logs_panel(self) -> None:
        if self.logs_panel.isHidden():
            self.logs_panel.show()
            self.center_splitter.setSizes([380, 180])
        else:
            self.logs_panel.hide()

    # --- Vault Operations ---

    def open_vault_by_path(self, path: Path, prompt_unlock: bool = True) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Vault Not Found", f"Directory '{path}' does not exist.")
            self.config.remove_vault(str(path))
            self.sidebar.refresh_vaults_list()
            return

        if self.vault and self.vault.root_dir.resolve() == path.resolve() and self.vault.is_unlocked:
            return

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
                msg = f"Vault '{self.vault.metadata.name if self.vault.metadata else 'Vault'}' unlocked."
                if getattr(self.vault, "last_imported_count", 0) > 0:
                    msg += f" Imported {self.vault.last_imported_count} off-site archive(s) into 'imports'."
                self.status_bar.showMessage(msg)
            else:
                self.lock_vault()

    def lock_vault(self) -> None:
        if self._watched_files:
            files_to_remove = list(self._watched_files.keys())
            self.file_watcher.removePaths(files_to_remove)
            self._watched_files.clear()

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
            self.vault = Vault(dlg.created_vault_path, self.sevenzip)
            dlg_unlock = UnlockVaultDialog(self.vault, self, dark_mode=self.dark_mode)
            if dlg_unlock.exec() == UnlockVaultDialog.DialogCode.Accepted:
                self.sidebar.set_current_vault(self.vault)
                self._update_toolbar_state()
                self.refresh_current_view()

    def _on_check_imports_action(self) -> None:
        """Scan and import off-site .7z files from the vault's import/ folder."""
        if not self.vault or not self.vault.is_unlocked:
            return

        count = self.vault.process_pending_imports()
        if count > 0:
            self.refresh_current_view()
            self.status_bar.showMessage(f"Imported {count} off-site archive(s) into 'imports'.")
            QMessageBox.information(
                self,
                "Off-site Import",
                f"Successfully imported {count} archive(s) from the 'import/' folder into 'imports'.",
            )
        else:
            msg = (
                "No pending encrypted .7z archives were found in the 'import/' folder.\n\n"
                "To import files from other devices, compress them with 7z using your vault password, "
                "drop the .7z files into the 'import/' folder, and click 'Check Imports'.\n\n"
                "Open 'import/' folder in file manager now?"
            )
            res = QMessageBox.information(
                self,
                "Off-site Import",
                msg,
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            )
            if res == QMessageBox.StandardButton.Open:
                from PyQt6.QtCore import QUrl
                from PyQt6.QtGui import QDesktopServices
                self.vault.import_dir.mkdir(parents=True, exist_ok=True)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.vault.import_dir.resolve())))

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
            if self.vault and self.vault.root_dir.resolve() == vault_path.resolve():
                self.lock_vault()
                self.vault = None
                self.sidebar.set_current_vault(None)
            self.config.remove_vault(str(vault_path))
            self.sidebar.refresh_vaults_list()

    def _on_rename_vault_display_name(self, vault_path: Optional[Path]) -> None:
        """Prompt user and change the display name of a vault (persists to .vaultables and config)."""
        if not vault_path:
            if self.vault:
                vault_path = self.vault.root_dir
            else:
                return

        # Determine current display name
        current_name = ""
        if self.vault and self.vault.root_dir.resolve() == vault_path.resolve():
            current_name = self.vault.name
        else:
            for it in self.config.known_vaults:
                if str(Path(it.get("path", "")).resolve()) == str(vault_path.resolve()):
                    current_name = it.get("name", vault_path.name)
                    break
            if not current_name:
                current_name = vault_path.name

        msg = f"Enter new display name for vault '{current_name}': (Physical directory: {vault_path.name})"
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Vault Display Name",
            msg,
            text=current_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == current_name:
            return

        clean_name = new_name.strip()

        # Update vault metadata
        if self.vault and self.vault.root_dir.resolve() == vault_path.resolve():
            self.vault.set_display_name(clean_name)
        else:
            marker = vault_path / Vault.MARKER_FILENAME
            if marker.is_file():
                try:
                    data = json.loads(marker.read_text(encoding="utf-8"))
                    data["name"] = clean_name
                    marker.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass

        # Update config known vaults and UI
        self.config.add_or_update_vault(str(vault_path), clean_name)
        self.sidebar.refresh_vaults_list()

        if self.vault and self.vault.root_dir.resolve() == vault_path.resolve():
            self.sidebar.set_current_vault(self.vault)
            self.setWindowTitle(f"Vaultables - {clean_name}")
            self.refresh_current_view()

        self.status_bar.showMessage(f"Vault display name changed to '{clean_name}'.")

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

    def refresh_current_view(self, force_reload: bool = False) -> None:
        if not self.vault or not self.vault.is_unlocked:
            self.file_view.set_items([])
            self.file_view.set_location_context("", "")
            self.breadcrumbs.set_path("", "")
            self.preview_panel.set_empty()
            return

        if force_reload:
            self.status_bar.showMessage("Refreshing vault contents...")
            self.vault.clear_cache()
            self.vault.refresh_entry_points()
            self.sidebar.refresh_entry_points()
            self.sidebar.refresh_vaults_list()
            self.preview_panel.set_empty()

            if self.active_entry_point and self.active_entry_point not in self.vault.entry_points:
                self.active_entry_point = ""
                self.current_subfolder = ""
                self.sidebar.set_active_entry_point("")

        self.breadcrumbs.set_path(self.active_entry_point, self.current_subfolder)
        self.file_view.set_location_context(self.active_entry_point, self.current_subfolder)
        self._update_toolbar_state()

        if not self.active_entry_point:
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
            msg = f"Vault Root: {len(items)} entry point archives."
            if getattr(self.vault, "last_imported_count", 0) > 0:
                msg += f" (Imported {self.vault.last_imported_count} off-site archive(s))"
            self.status_bar.showMessage(msg)
            return

        self.status_bar.showMessage(f"Reading '{self.active_entry_point}.7z'...")
        self._load_worker = LoadItemsWorker(
            self.vault, self.active_entry_point, self.current_subfolder, force_reload=force_reload
        )
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
        msg = f"{self.active_entry_point}{folder_str} • {len(items)} items ({format_size(total_size)})"
        if getattr(self.vault, "last_imported_count", 0) > 0:
            msg += f" • Imported {self.vault.last_imported_count} off-site archive(s)"
        self.status_bar.showMessage(msg)

    # --- File Explorer Interactions ---

    def _on_file_selected(self, item: Optional[ArchiveItem]) -> None:
        if not item or item.is_dir:
            self.preview_panel.set_empty()
            return

        # Ensure preview panel is visible and expanded
        if self.preview_panel.isHidden():
            self.preview_panel.show()
        sizes = self.main_splitter.sizes()
        if len(sizes) > 2 and sizes[2] < 50:
            sb_w = sizes[0] if sizes[0] > 100 else 220
            preview_w = 340
            total = sum(sizes) if sum(sizes) > 600 else self.main_splitter.width()
            center_w = max(260, total - sb_w - preview_w)
            self.main_splitter.setSizes([sb_w, center_w, preview_w])

        self.preview_panel.show_card_only(item, status_note="Extracting preview...")

        self._preview_worker = ExtractPreviewWorker(self.vault, item.entry_point_name, item.path)
        self._preview_worker.finished.connect(
            lambda path, err, it=item: self._on_preview_extracted(it, path, err)
        )
        self._preview_worker.start()

    def _on_preview_extracted(self, item: ArchiveItem, local_path: Optional[Path], err: str) -> None:
        if local_path and local_path.exists():
            self.preview_panel.show_preview(item, local_path)
        else:
            note = err if err else ("File exceeds 1GB preview threshold." if item.size > 1024 * 1024 * 1024 else "Preview unavailable.")
            self.preview_panel.show_card_only(item, status_note=note)

    def _on_file_double_clicked(self, item: ArchiveItem) -> None:
        if item.category == FileCategory.ENTRY_POINT or (not self.active_entry_point and item.is_dir):
            self.file_view.search_bar.clear()
            self.active_entry_point = item.entry_point_name or item.name
            self.current_subfolder = ""
            self.sidebar.set_active_entry_point(self.active_entry_point)
            self.refresh_current_view()
        elif item.is_dir:
            self.file_view.search_bar.clear()
            self.active_entry_point = item.entry_point_name or self.active_entry_point
            self.current_subfolder = item.path.strip("/")
            self.sidebar.set_active_entry_point(self.active_entry_point)
            self.refresh_current_view()
        else:
            if item.size > 1024 * 1024 * 1024:
                QMessageBox.information(
                    self,
                    "File Over 1 GB",
                    f"'{item.name}' is {format_size(item.size)} (over 1 GB limit for in-app preview/editing).\n\n"
                    "Please use 'Export / Save As' to extract this file to disk.",
                )
                return
            self._on_file_selected(item)

    def _focus_search_bar(self) -> None:
        self.file_view.search_bar.setFocus()
        self.file_view.search_bar.selectAll()

    def _on_search_requested(self, query: str, scope: str) -> None:
        clean_q = query.strip()
        if not clean_q or not self.vault or not self.vault.is_unlocked:
            self.refresh_current_view()
            return

        target_ep = None
        target_sub = ""
        recursive = True

        if scope == "folder":
            target_ep = self.active_entry_point or None
            target_sub = self.current_subfolder
            recursive = False
        elif scope == "entry_point":
            target_ep = self.active_entry_point or None
            target_sub = ""
            recursive = True
        else:  # "vault"
            target_ep = None
            target_sub = ""
            recursive = True

        scope_label = "entire vault" if not target_ep else f"{target_ep}.7z (recursive)"
        if scope == "folder":
            scope_label = f"/{self.current_subfolder}" if self.current_subfolder else "current folder"

        self.status_bar.showMessage(f"Searching {scope_label} for '{clean_q}'...")

        if hasattr(self, "_search_worker") and self._search_worker and self._search_worker.isRunning():
            self._search_worker.terminate()
            self._search_worker.wait()

        self._search_worker = SearchWorker(
            self.vault, clean_q, entry_point_name=target_ep, subfolder=target_sub, recursive=recursive
        )
        self._search_worker.results_found.connect(
            lambda items, q: self._on_search_results_ready(items, q, scope_label)
        )
        self._search_worker.start()

    def _on_search_results_ready(self, items: list, query: str, scope_label: str) -> None:
        self.file_view.set_search_results(items, query, scope_label)
        count = len(items)
        if count == 0:
            self.status_bar.showMessage(f"No files matching '{query}' found in {scope_label}.")
        else:
            self.status_bar.showMessage(f"Found {count} item{'s' if count != 1 else ''} matching '{query}' in {scope_label}.")

    def _on_reveal_in_vault(self, item: ArchiveItem) -> None:
        self.file_view.search_bar.clear()
        if item.category == FileCategory.ENTRY_POINT:
            self.active_entry_point = ""
            self.current_subfolder = ""
        else:
            self.active_entry_point = item.entry_point_name
            parts = item.path.strip("/").replace("\\", "/").split("/")
            self.current_subfolder = "/".join(parts[:-1]) if len(parts) > 1 else ""

        self.sidebar.set_active_entry_point(self.active_entry_point)
        self.refresh_current_view()
        self.file_view.select_item_by_name(item.name)

    # --- Drag & Drop Implementations ---

    def _on_files_dropped_on_folder(self, files: List[Path], target_subfolder: str) -> None:
        """User dropped files into a specific folder inside current entry point."""
        if not self.vault or not self.vault.is_unlocked or not self.active_entry_point:
            return
        self._start_add_files(files, target_subfolder=target_subfolder)

    def _on_files_dropped_on_entry_point(self, files: List[Path], ep_name: str) -> None:
        """User dropped files onto an entry point in the sidebar or root list."""
        if not self.vault or not self.vault.is_unlocked:
            return
        self.active_entry_point = ep_name
        self.current_subfolder = ""
        self.sidebar.set_active_entry_point(ep_name)
        self._start_add_files(files, target_subfolder="")

    def _on_files_dropped_root(self, files: List[Path]) -> None:
        """User dropped files while in Vault Root."""
        if not self.vault or not self.vault.is_unlocked:
            return

        ep_names = list(self.vault.entry_points.keys())
        if not ep_names:
            # Prompt to create initial entry point
            self._on_create_entry_point()
            return

        items = ["+ Create New Entry Point (.7z)"] + ep_names
        chosen, ok = QInputDialog.getItem(
            self,
            "Add Dropped Files",
            f"Select target Entry Point archive for {len(files)} dropped file(s):",
            items,
            0,
            False,
        )
        if ok and chosen:
            if chosen.startswith("+"):
                dlg = CreateEntryPointDialog(
                    vault_is_obfuscated=self.vault.obfuscate_names,
                    parent=self,
                    dark_mode=self.dark_mode,
                )
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    clean_name = dlg.get_entry_point_name()
                    obf_setting = dlg.get_obfuscate_setting()
                    try:
                        self.vault.create_entry_point(clean_name, obfuscate=obf_setting)
                        self.sidebar.refresh_entry_points()
                        self._on_files_dropped_on_entry_point(files, clean_name)
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to create entry point: {e}")
            else:
                self._on_files_dropped_on_entry_point(files, chosen)

    def _on_drag_export_requested(self, items: List[ArchiveItem]) -> None:
        """Native cross-platform drag-out: user drags files OUT of Vaultables to desktop/Finder."""
        if not items or not self.vault or not self.vault.is_unlocked:
            return

        # Extract to temporary drag cache
        temp_drag_dir = Path(tempfile.mkdtemp(prefix="vaultables_drag_out_"))
        extracted_urls: List[QUrl] = []

        ep_name = items[0].entry_point_name or self.active_entry_point
        internal_paths = [it.path for it in items]

        ok = self.vault.export_items(ep_name, internal_paths, temp_drag_dir)
        if not ok:
            return

        for it in items:
            local_target = temp_drag_dir / it.name
            if local_target.exists():
                extracted_urls.append(QUrl.fromLocalFile(str(local_target.resolve())))

        if not extracted_urls:
            return

        # Prepare QDrag
        drag = QDrag(self)
        from PyQt6.QtCore import QMimeData
        mime = QMimeData()
        mime.setUrls(extracted_urls)
        internal_payload = {
            "entry_point": ep_name,
            "paths": internal_paths,
        }
        mime.setData("application/x-vaultables-internal", json.dumps(internal_payload).encode("utf-8"))
        drag.setMimeData(mime)

        first_icon = IconProvider.get_category_icon(items[0].category, dark_mode=self.dark_mode, size=32)
        drag.setPixmap(first_icon.pixmap(32, 32))
        drag.setHotSpot(QPoint(16, 16))

        drag.exec(Qt.DropAction.CopyAction)

    # --- Editing Vault Archives (In-App & External) ---

    def _on_save_in_app_text(self, item: ArchiveItem, new_text: str) -> None:
        """Handle saving directly edited text inside the app."""
        if not self.vault or not self.vault.is_unlocked:
            return

        self.status_bar.showMessage(f"Saving and re-encrypting '{item.name}' into {item.entry_point_name}.7z...")
        self._update_worker = UpdateFileWorker(
            self.vault, item.entry_point_name, item.path, new_text
        )
        self._update_worker.finished.connect(
            lambda ok, err, txt=new_text, it=item: self._on_in_app_save_finished(it, txt, ok, err)
        )
        self._update_worker.start()

    def _on_in_app_save_finished(self, item: ArchiveItem, new_text: str, success: bool, error_msg: str) -> None:
        if success:
            self.status_bar.showMessage(f"Successfully updated '{item.name}' in {item.entry_point_name}.7z.")
            self.preview_panel.on_save_successful(new_text)
            self.refresh_current_view()
        else:
            QMessageBox.critical(self, "Save Failed", f"Could not update file in archive: {error_msg}")
            self.status_bar.showMessage("Save failed.")

    def _start_external_editing(self, item: ArchiveItem) -> None:
        """Extract file to watched directory and launch external editor."""
        if not self.vault or not self.vault.is_unlocked:
            return

        if item.size > 1024 * 1024 * 1024:
            QMessageBox.information(
                self,
                "File Over 1 GB",
                f"'{item.name}' is {format_size(item.size)} (over 1 GB limit for external editing).\n\n"
                "Please use 'Export / Save As' to extract this file to disk.",
            )
            return

        staged_path = self.vault.extract_file_for_editing(item.entry_point_name, item.path)
        if not staged_path or not staged_path.exists():
            QMessageBox.warning(self, "Edit Error", "Could not extract file for editing.")
            return

        path_str = str(staged_path.resolve())
        mtime = staged_path.stat().st_mtime
        file_hash = self._compute_file_hash(staged_path)

        self._watched_files[path_str] = (item.entry_point_name, item.path, mtime, file_hash)
        self.file_watcher.addPath(path_str)

        self.status_bar.showMessage(
            f"Opened '{item.name}' in external editor. Changes will auto-save to vault."
        )

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path_str])
            elif sys.platform == "win32":
                os.startfile(path_str)
            else:
                subprocess.Popen(["xdg-open", path_str])
        except Exception as e:
            QMessageBox.warning(self, "Launch Error", f"Failed to launch external editor: {e}")

    def _on_watched_file_changed(self, file_path_str: str) -> None:
        """Called by QFileSystemWatcher whenever an external application modifies the staged file."""
        if file_path_str not in self._watched_files:
            return

        p = Path(file_path_str)
        if not p.exists():
            return

        ep_name, internal_path, last_mtime, last_hash = self._watched_files[file_path_str]
        new_mtime = p.stat().st_mtime
        new_hash = self._compute_file_hash(p)

        if new_hash == last_hash:
            return  # No actual change in content

        self._watched_files[file_path_str] = (ep_name, internal_path, new_mtime, new_hash)
        self.status_bar.showMessage(
            f"Detected modification in '{p.name}'. Re-encrypting into {ep_name}.7z..."
        )

        ok = self.vault.update_file_from_disk(ep_name, internal_path, p)
        if ok:
            self.status_bar.showMessage(
                f"Auto-saved external edits of '{p.name}' into {ep_name}.7z."
            )
            # Re-read preview if it's currently selected
            if self.preview_panel.current_item and self.preview_panel.current_item.path == internal_path:
                self.preview_panel.show_preview(self.preview_panel.current_item, p)
            self.refresh_current_view()
        else:
            self.status_bar.showMessage(f"Failed to auto-save edits of '{p.name}'.")

    @staticmethod
    def _compute_file_hash(path: Path) -> str:
        try:
            return hashlib.md5(path.read_bytes()).hexdigest()
        except Exception:
            return ""

    # --- Actions ---

    def _on_add_files_action(self) -> None:
        if not self.vault or not self.vault.is_unlocked or not self.active_entry_point:
            return

        files, _ = QFileDialog.getOpenFileNames(self, f"Add Files to '{self.active_entry_point}'", str(Path.home()))
        if files:
            path_objs = [Path(f) for f in files if not is_ignorable_system_file(Path(f))]
            if path_objs:
                self._start_add_files(path_objs, target_subfolder=self.current_subfolder)

    def _reset_progress(self) -> None:
        self.progress_container.hide()
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self._task_start_time = None
        self._task_total_bytes = 0

    def _start_progress(self, total_bytes: int = 0) -> None:
        self._task_start_time = time.time()
        self._task_total_bytes = total_bytes
        self.progress_bar.setValue(0)
        if total_bytes > 0:
            self.progress_label.setText(f"0 B / {format_size(total_bytes)} ({format_size(total_bytes)} remaining)")
        else:
            self.progress_label.setText("Preparing...")
        self.progress_container.show()

    def _on_task_progress(self, bytes_done: int, total_bytes: int) -> None:
        if total_bytes <= 0:
            return

        self._task_total_bytes = total_bytes
        pct = int(min(100, max(0, (bytes_done / total_bytes) * 100)))
        self.progress_bar.setValue(pct)

        elapsed = time.time() - (self._task_start_time or time.time())
        speed_str = ""
        eta_str = ""

        if elapsed > 0.5 and bytes_done > 0:
            bps = bytes_done / elapsed
            speed_str = f" • {format_size(int(bps))}/s"
            remaining_bytes = max(0, total_bytes - bytes_done)
            if bps > 0 and remaining_bytes > 0:
                seconds_left = int(remaining_bytes / bps)
                mins, secs = divmod(seconds_left, 60)
                hours, mins = divmod(mins, 60)
                if hours > 0:
                    eta_str = f" • ETA {hours:02d}:{mins:02d}:{secs:02d}"
                else:
                    eta_str = f" • ETA {mins:02d}:{secs:02d}"

        rem_bytes = max(0, total_bytes - bytes_done)
        label_text = f"{format_size(bytes_done)} / {format_size(total_bytes)} ({format_size(rem_bytes)} remaining){speed_str}{eta_str}"
        self.progress_label.setText(label_text)

    def _start_add_files(self, files: List[Path], target_subfolder: str = "") -> None:
        files = [f for f in files if not is_ignorable_system_file(f)]
        if not files:
            return
        sub_info = f"/{target_subfolder}" if target_subfolder else ""
        self.status_bar.showMessage(
            f"Encrypting and adding {len(files)} items into {self.active_entry_point}.7z{sub_info}..."
        )
        total_size = 0
        for f in files:
            if f.is_file():
                total_size += f.stat().st_size
            elif f.is_dir():
                total_size += sum(child.stat().st_size for child in f.rglob('*') if child.is_file() and not is_ignorable_system_file(child))
        self._start_progress(total_size)
        self._add_worker = AddFilesWorker(
            self.vault, self.active_entry_point, files, subfolder=target_subfolder
        )
        self._add_worker.progress.connect(self._on_task_progress)
        self._add_worker.finished.connect(self._on_add_finished)
        self._add_worker.start()

    def _on_add_finished(self, success: bool, error_msg: str) -> None:
        self._reset_progress()
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
            self._on_create_entry_point()
            return

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

        dlg = CreateEntryPointDialog(
            vault_is_obfuscated=self.vault.obfuscate_names,
            parent=self,
            dark_mode=self.dark_mode,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            clean_name = dlg.get_entry_point_name()
            obf_setting = dlg.get_obfuscate_setting()
            try:
                self.vault.create_entry_point(clean_name, obfuscate=obf_setting)
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
        self.status_bar.showMessage(f"Decrypting and exporting {len(items)} item(s)...")
        total_size = sum(it.size for it in items if not it.is_dir)
        self._start_progress(total_size)
        self._export_worker = ExportFilesWorker(
            self.vault, items, dest_path, active_entry_point=self.active_entry_point
        )
        self._export_worker.progress.connect(self._on_task_progress)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.start()

    def _on_export_finished(self, success: bool, error_msg: str) -> None:
        self._reset_progress()
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

        paths_to_delete = [it.path for it in items]
        self.vault.delete_items(self.active_entry_point, paths_to_delete)

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
            parent = "/".join(item.path.split("/")[:-1])
            new_path = f"{parent}/{clean_name}".strip("/") if parent else clean_name
            ok_rn = self.vault.rename_item(self.active_entry_point, item.path, new_path)
            if ok_rn:
                self.refresh_current_view()
            else:
                QMessageBox.warning(self, "Rename Error", "Failed to rename item in archive.")

    def _on_move_action(self, items: List[ArchiveItem]) -> None:
        """Prompt user with a list of destination subfolders to move selected items into."""
        if not items or not self.vault or not self.vault.is_unlocked or not self.active_entry_point:
            return

        all_subs = self.vault.get_all_subfolders(self.active_entry_point)
        item_paths = {i.path.strip("/") for i in items}
        valid_destinations = ["/ [Root Folder]"]
        for s in all_subs:
            if any(s == p or s.startswith(p + "/") for p in item_paths):
                continue
            valid_destinations.append(s)

        valid_destinations.append("+ Create New Folder...")

        chosen, ok = QInputDialog.getItem(
            self,
            "Move Items",
            f"Select destination folder for {len(items)} item(s):",
            valid_destinations,
            current=0,
            editable=False,
        )
        if not ok or not chosen:
            return

        if chosen == "+ Create New Folder...":
            new_name, ok_new = QInputDialog.getText(
                self, "New Folder", f"Create new folder inside '{self.active_entry_point}':"
            )
            if not ok_new or not new_name.strip():
                return
            clean_name = new_name.strip()
            self.vault.create_subfolder(self.active_entry_point, self.current_subfolder, clean_name)
            target_sub = f"{self.current_subfolder}/{clean_name}".strip("/") if self.current_subfolder else clean_name
        elif chosen == "/ [Root Folder]":
            target_sub = ""
        else:
            target_sub = chosen

        ok_move = self.vault.move_items(self.active_entry_point, [i.path for i in items], target_sub)
        if ok_move:
            self.refresh_current_view()
            dest_name = target_sub if target_sub else "root"
            self.status_bar.showMessage(f"Moved {len(items)} item(s) to '{dest_name}'.")
        else:
            QMessageBox.warning(self, "Move Error", "Failed to move one or more items.")
            self.refresh_current_view()

    def _on_internal_move_requested(
        self,
        source_ep: str,
        item_paths: List[str],
        target_item: Optional[ArchiveItem],
    ) -> None:
        """Handle moving files/folders inside the archive when dragged onto a folder."""
        if not self.vault or not self.vault.is_unlocked:
            return

        if not self.active_entry_point or source_ep != self.active_entry_point:
            return

        # Determine destination subfolder
        if target_item and target_item.is_dir:
            target_subfolder = target_item.path.strip("/")
        elif not target_item:
            # Dropped on empty area in current view
            target_subfolder = self.current_subfolder
        else:
            return

        # Prevent moving a folder into itself or its own subdirectories
        for p in item_paths:
            clean_p = p.strip("/")
            if clean_p == target_subfolder or target_subfolder.startswith(clean_p + "/"):
                QMessageBox.warning(self, "Invalid Move", f"Cannot move '{clean_p}' into itself or its subfolder.")
                return

        # Filter out items already in target folder
        items_to_move = []
        for p in item_paths:
            clean_p = p.strip("/")
            parent = "/".join(clean_p.split("/")[:-1])
            if parent != target_subfolder:
                items_to_move.append(p)

        if not items_to_move:
            return

        self.status_bar.showMessage(f"Moving {len(items_to_move)} item(s) to '{target_subfolder or root}'...")
        ok = self.vault.move_items(self.active_entry_point, items_to_move, target_subfolder)
        if ok:
            self.refresh_current_view()
            dest_name = target_item.name if target_item else (target_subfolder or "root")
            self.status_bar.showMessage(f"Successfully moved {len(items_to_move)} item(s) to '{dest_name}'.")
        else:
            QMessageBox.warning(self, "Move Error", "Failed to move one or more items.")
            self.refresh_current_view()

    def _restore_window_state(self) -> None:
        """Restore window size, position, maximized state, and splitter layout from config."""
        try:
            restored = False
            if self.config.window_geometry:
                geo_bytes = QByteArray.fromBase64(self.config.window_geometry.encode('ascii'))
                restored = self.restoreGeometry(geo_bytes)

            if not restored:
                w = max(self.config.window_width, 850)
                h = max(self.config.window_height, 500)
                self.resize(w, h)
                if self.config.window_x is not None and self.config.window_y is not None:
                    self.move(self.config.window_x, self.config.window_y)

            if self.config.window_maximized:
                self.showMaximized()

            if self.config.splitter_state and hasattr(self, 'main_splitter'):
                split_bytes = QByteArray.fromBase64(self.config.splitter_state.encode('ascii'))
                self.main_splitter.restoreState(split_bytes)
                sizes = self.main_splitter.sizes()
                if len(sizes) >= 3 and sizes[2] < 100:
                    sb_w = max(180, sizes[0])
                    preview_w = 340
                    total = sum(sizes) if sum(sizes) > 600 else 1120
                    center_w = max(260, total - sb_w - preview_w)
                    self.main_splitter.setSizes([sb_w, center_w, preview_w])

            if hasattr(self.config, "file_list_size_index") and self.config.file_list_size_index is not None:
                self.file_view.apply_list_size(self.config.file_list_size_index)
            if hasattr(self.config, "file_column_widths") and self.config.file_column_widths:
                self.file_view.set_custom_column_widths(self.config.file_column_widths)
        except Exception as e:
            print(f'[Vaultables] Failed to restore window state: {e}')

    def _save_window_state(self) -> None:
        """Save window size, placement, maximized status, and splitter state to config."""
        try:
            self.config.window_geometry = bytes(self.saveGeometry().toBase64()).decode('ascii')
            self.config.window_maximized = self.isMaximized()
            if not self.isMaximized():
                self.config.window_width = self.width()
                self.config.window_height = self.height()
                self.config.window_x = self.x()
                self.config.window_y = self.y()
            if hasattr(self, 'main_splitter'):
                self.config.splitter_state = bytes(self.main_splitter.saveState().toBase64()).decode('ascii')
            self.config.theme = 'dark' if self.dark_mode else 'light'
            self.config.save()
        except Exception as e:
            print(f'[Vaultables] Failed to save window state: {e}')

    def _on_list_size_changed(self, size_index: int) -> None:
        self.config.file_list_size_index = size_index
        self.config.save()
        label = f"Size {size_index + 1}/10"
        if size_index == 4:
            label += " (Default)"
        self.statusBar().showMessage(f"File list zoom: {label}", 1500)

    def _on_column_widths_changed(self, widths: dict) -> None:
        self.config.file_column_widths = widths
        self.config.save()

    def closeEvent(self, event) -> None:
        self._save_window_state()
        if self._watched_files:
            self.file_watcher.removePaths(list(self._watched_files.keys()))
            self._watched_files.clear()
        if self.vault:
            self.vault.lock()
        event.accept()
