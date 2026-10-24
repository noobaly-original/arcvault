"""Left sidebar managing vault locations and entry-point archive list."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arc_vault.config import AppConfig
from arc_vault.core.vault import Vault
from arc_vault.gui.icons import IconProvider


class VaultSidebar(QWidget):
    """Sidebar providing vault switching and entry point archive navigation."""

    vault_selected = pyqtSignal(Path)
    entry_point_selected = pyqtSignal(str)
    create_vault_requested = pyqtSignal()
    open_vault_requested = pyqtSignal()
    remove_vault_requested = pyqtSignal(Path)
    lock_vault_requested = pyqtSignal()
    create_entry_point_requested = pyqtSignal()
    rename_entry_point_requested = pyqtSignal(str)
    delete_entry_point_requested = pyqtSignal(str)

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.dark_mode: bool = True
        self.current_vault: Optional[Vault] = None
        self.active_entry_point: str = ""

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Top App Brand Header
        brand_layout = QHBoxLayout()
        self.brand_icon = QLabel(self)
        self.brand_icon.setPixmap(IconProvider.get_icon("vault", dark_mode=self.dark_mode, size=24).pixmap(24, 24))
        brand_layout.addWidget(self.brand_icon)

        self.brand_title = QLabel("ArcVault", self)
        self.brand_title.setStyleSheet("font-size: 15px; font-weight: bold; letter-spacing: 0.5px;")
        brand_layout.addWidget(self.brand_title)
        brand_layout.addStretch()

        self.layout.addLayout(brand_layout)

        # Section: Vaults Header
        vaults_header = QHBoxLayout()
        lbl_vaults = QLabel("VAULTS", self)
        lbl_vaults.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        vaults_header.addWidget(lbl_vaults)
        vaults_header.addStretch()

        self.btn_add_vault = QToolButton(self)
        self.btn_add_vault.setToolTip("Add or Create Vault")
        self.btn_add_vault.clicked.connect(self._show_add_vault_menu)
        vaults_header.addWidget(self.btn_add_vault)

        self.layout.addLayout(vaults_header)

        # List of Known Vaults
        self.vault_list = QListWidget(self)
        self.vault_list.setMinimumHeight(120)
        self.vault_list.setMaximumHeight(180)
        self.vault_list.itemClicked.connect(self._on_vault_clicked)
        self.vault_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.vault_list.customContextMenuRequested.connect(self._show_vault_context_menu)
        self.layout.addWidget(self.vault_list)

        # Separator line
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #334155;" if self.dark_mode else "color: #e2e8f0;")
        self.layout.addWidget(sep)

        # Section: Entry Points (Root .7z Archives)
        ep_header = QHBoxLayout()
        lbl_ep = QLabel("ENTRY POINTS (.7Z)", self)
        lbl_ep.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        ep_header.addWidget(lbl_ep)
        ep_header.addStretch()

        self.btn_add_ep = QToolButton(self)
        self.btn_add_ep.setToolTip("Create New Entry Point (.7z Archive)")
        self.btn_add_ep.clicked.connect(self.create_entry_point_requested.emit)
        ep_header.addWidget(self.btn_add_ep)

        self.layout.addLayout(ep_header)

        # Entry points list
        self.ep_list = QListWidget(self)
        self.ep_list.itemClicked.connect(self._on_ep_clicked)
        self.ep_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ep_list.customContextMenuRequested.connect(self._show_ep_context_menu)
        self.layout.addWidget(self.ep_list)

        # Bottom Vault Status Bar
        self.status_box = QFrame(self)
        self.status_box.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(self.status_box)
        status_layout.setContentsMargins(6, 6, 6, 6)
        status_layout.setSpacing(6)

        self.lbl_lock_status = QLabel("No Vault Open", self)
        self.lbl_lock_status.setStyleSheet("font-size: 11px; color: #64748b;")
        status_layout.addWidget(self.lbl_lock_status)
        status_layout.addStretch()

        self.btn_lock = QPushButton("Lock", self)
        self.btn_lock.setVisible(False)
        self.btn_lock.clicked.connect(self.lock_vault_requested.emit)
        status_layout.addWidget(self.btn_lock)

        self.layout.addWidget(self.status_box)

        self.update_icons()
        self.refresh_vaults_list()

    def update_icons(self) -> None:
        self.brand_icon.setPixmap(
            IconProvider.get_icon("vault", dark_mode=self.dark_mode, size=24).pixmap(24, 24)
        )
        self.btn_add_vault.setIcon(
            IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16)
        )
        self.btn_add_ep.setIcon(
            IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16)
        )

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self.update_icons()
        self.refresh_vaults_list()
        self.refresh_entry_points()

    def refresh_vaults_list(self) -> None:
        """Populate the known vaults list."""
        self.vault_list.clear()
        selected_row = -1

        for idx, item in enumerate(self.config.known_vaults):
            v_path_str = item.get("path", "")
            v_name = item.get("name", Path(v_path_str).name)
            v_path = Path(v_path_str)

            is_active = self.current_vault and self.current_vault.root_dir == v_path
            is_unlocked = is_active and self.current_vault.is_unlocked

            icon_name = "vault_unlocked" if is_unlocked else "vault"
            icon_color = ("#10b981" if is_unlocked else "#94a3b8") if self.dark_mode else ("#059669" if is_unlocked else "#64748b")
            icon = IconProvider.get_icon(icon_name, color=icon_color, dark_mode=self.dark_mode, size=20)

            list_item = QListWidgetItem(f"{v_name}")
            list_item.setIcon(icon)
            list_item.setData(Qt.ItemDataRole.UserRole, v_path)
            list_item.setToolTip(v_path_str)
            self.vault_list.addItem(list_item)

            if is_active:
                selected_row = idx

        if selected_row >= 0:
            self.vault_list.setCurrentRow(selected_row)

    def set_current_vault(self, vault: Optional[Vault]) -> None:
        """Update display when active vault changes."""
        self.current_vault = vault
        self.refresh_vaults_list()
        self.refresh_entry_points()

        if vault and vault.is_unlocked:
            self.lbl_lock_status.setText(f"Unlocked: {vault.metadata.name if vault.metadata else 'Vault'}")
            self.lbl_lock_status.setStyleSheet("color: #10b981; font-weight: 600; font-size: 11px;")
            self.btn_lock.setVisible(True)
            self.btn_add_ep.setEnabled(True)
        elif vault:
            self.lbl_lock_status.setText(f"Locked: {vault.metadata.name if vault.metadata else 'Vault'}")
            self.lbl_lock_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
            self.btn_lock.setVisible(False)
            self.btn_add_ep.setEnabled(False)
        else:
            self.lbl_lock_status.setText("No Vault Open")
            self.lbl_lock_status.setStyleSheet("color: #64748b; font-size: 11px;")
            self.btn_lock.setVisible(False)
            self.btn_add_ep.setEnabled(False)

    def refresh_entry_points(self) -> None:
        """Populate list of entry points in active unlocked vault."""
        self.ep_list.clear()
        if not self.current_vault or not self.current_vault.is_unlocked:
            return

        selected_row = -1
        # Item 0: Vault Root
        root_item = QListWidgetItem("Vault Root (All Entries)")
        root_item.setIcon(IconProvider.get_icon("vault_unlocked", dark_mode=self.dark_mode, size=18))
        root_item.setData(Qt.ItemDataRole.UserRole, "")
        self.ep_list.addItem(root_item)
        if not self.active_entry_point:
            selected_row = 0

        # Entry points
        for idx, (ep_name, ep) in enumerate(self.current_vault.entry_points.items(), start=1):
            item = QListWidgetItem(f"{ep_name}.7z")
            item.setIcon(IconProvider.get_icon("entry_point", dark_mode=self.dark_mode, size=18))
            item.setData(Qt.ItemDataRole.UserRole, ep_name)
            item.setToolTip(f"Archive: {ep.archive_file.name}")
            self.ep_list.addItem(item)
            if self.active_entry_point == ep_name:
                selected_row = idx

        if selected_row >= 0:
            self.ep_list.setCurrentRow(selected_row)

    def set_active_entry_point(self, ep_name: str) -> None:
        self.active_entry_point = ep_name
        for i in range(self.ep_list.count()):
            item = self.ep_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == ep_name:
                self.ep_list.setCurrentRow(i)
                break

    def _show_add_vault_menu(self) -> None:
        menu = QMenu(self)
        act_new = menu.addAction("Create New Vault...")
        act_new.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16))
        act_new.triggered.connect(self.create_vault_requested.emit)

        act_open = menu.addAction("Open Existing Vault...")
        act_open.setIcon(IconProvider.get_icon("folder", dark_mode=self.dark_mode, size=16))
        act_open.triggered.connect(self.open_vault_requested.emit)

        menu.exec(self.btn_add_vault.mapToGlobal(self.btn_add_vault.rect().bottomLeft()))

    def _on_vault_clicked(self, item: QListWidgetItem) -> None:
        v_path = item.data(Qt.ItemDataRole.UserRole)
        if v_path:
            self.vault_selected.emit(Path(v_path))

    def _on_ep_clicked(self, item: QListWidgetItem) -> None:
        ep_name = item.data(Qt.ItemDataRole.UserRole)
        self.active_entry_point = ep_name
        self.entry_point_selected.emit(ep_name)

    def _show_vault_context_menu(self, pos) -> None:
        item = self.vault_list.itemAt(pos)
        if not item:
            return

        v_path: Path = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)

        act_open = menu.addAction("Select Vault")
        act_open.triggered.connect(lambda: self.vault_selected.emit(v_path))

        act_reveal = menu.addAction("Reveal in System File Manager")
        act_reveal.setIcon(IconProvider.get_icon("external", dark_mode=self.dark_mode, size=16))
        act_reveal.triggered.connect(lambda: self._reveal_path(v_path))

        menu.addSeparator()

        act_remove = menu.addAction("Remove from Vault List")
        act_remove.setIcon(IconProvider.get_icon("trash", dark_mode=self.dark_mode, size=16))
        act_remove.triggered.connect(lambda: self.remove_vault_requested.emit(v_path))

        menu.exec(self.vault_list.viewport().mapToGlobal(pos))

    def _show_ep_context_menu(self, pos) -> None:
        item = self.ep_list.itemAt(pos)
        if not item:
            return

        ep_name = item.data(Qt.ItemDataRole.UserRole)
        if not ep_name:
            return  # Root item

        menu = QMenu(self)

        act_open = menu.addAction(f"Open '{ep_name}'")
        act_open.triggered.connect(lambda: self.entry_point_selected.emit(ep_name))

        if self.current_vault and ep_name in self.current_vault.entry_points:
            ep_file = self.current_vault.entry_points[ep_name].archive_file
            act_reveal = menu.addAction("Reveal .7z Archive File")
            act_reveal.setIcon(IconProvider.get_icon("external", dark_mode=self.dark_mode, size=16))
            act_reveal.triggered.connect(lambda: self._reveal_path(ep_file))

        act_rename = menu.addAction("Rename Entry Point...")
        act_rename.triggered.connect(lambda: self.rename_entry_point_requested.emit(ep_name))

        menu.addSeparator()

        act_delete = menu.addAction("Delete Entry Point Archive")
        act_delete.setIcon(IconProvider.get_icon("trash", dark_mode=self.dark_mode, size=16))
        act_delete.triggered.connect(lambda: self.delete_entry_point_requested.emit(ep_name))

        menu.exec(self.ep_list.viewport().mapToGlobal(pos))

    def _reveal_path(self, path: Path) -> None:
        target = str(path.resolve())
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", target])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception as e:
            print(f"[ArcVault] Failed to reveal path: {e}")
