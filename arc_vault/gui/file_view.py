"""Table view component displaying archives, folders, and encrypted files with cross-platform drag-and-drop."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QEvent, QMimeData, QModelIndex, QPoint, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arc_vault.core.models import ArchiveItem, FileCategory
from arc_vault.gui.icons import IconProvider
from arc_vault.gui.preview_panel import format_size


class FileTableWidget(QTableWidget):
    """QTableWidget supporting cross-platform drop targeting and drag export."""

    files_dropped_on_item = pyqtSignal(list, object)  # (List[Path], Optional[ArchiveItem])
    drag_export_requested = pyqtSignal(list)          # List[ArchiveItem]
    delete_pressed = pyqtSignal()
    enter_pressed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragEnabled(True)
        self._drag_start_pos: Optional[QPoint] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self._drag_start_pos:
            super().mouseMoveEvent(event)
            return

        dist = (event.pos() - self._drag_start_pos).manhattanLength()
        if dist < 10:
            super().mouseMoveEvent(event)
            return

        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            super().mouseMoveEvent(event)
            return

        rows = sorted(set(idx.row() for idx in selected_indexes))
        items: List[ArchiveItem] = []
        for r in rows:
            it = self.item(r, 0)
            if it:
                item_data = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(item_data, ArchiveItem):
                    items.append(item_data)

        if items:
            self.drag_export_requested.emit(items)

        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            row = self.rowAt(int(event.position().y()))
            if 0 <= row < self.rowCount():
                col0 = self.item(row, 0)
                if col0:
                    self.setCurrentItem(col0)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        file_paths: List[Path] = []
        for u in urls:
            local = u.toLocalFile()
            if local:
                p = Path(local)
                if p.exists():
                    file_paths.append(p)

        if not file_paths:
            event.ignore()
            return

        # Target item row resolution across any column
        row = self.rowAt(int(event.position().y()))
        target_archive_item: Optional[ArchiveItem] = None
        if 0 <= row < self.rowCount():
            col0 = self.item(row, 0)
            if col0:
                data = col0.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, ArchiveItem):
                    target_archive_item = data

        self.files_dropped_on_item.emit(file_paths, target_archive_item)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)


class FileExplorerView(QWidget):
    """File table view with search filter, sorting, and drag-and-drop actions."""

    item_selected = pyqtSignal(object)  # Optional[ArchiveItem]
    item_double_clicked = pyqtSignal(object)  # ArchiveItem
    files_dropped_on_folder = pyqtSignal(list, str)  # (List[Path], target_subfolder_str)
    files_dropped_on_entry_point = pyqtSignal(list, str)  # (List[Path], entry_point_name)
    files_dropped_root = pyqtSignal(list)  # List[Path]
    drag_export_requested = pyqtSignal(list)  # List[ArchiveItem]
    create_folder_requested = pyqtSignal()
    add_files_requested = pyqtSignal()
    export_requested = pyqtSignal(list)  # List[ArchiveItem]
    delete_requested = pyqtSignal(list)  # List[ArchiveItem]
    rename_requested = pyqtSignal(ArchiveItem)
    edit_external_requested = pyqtSignal(ArchiveItem)

    COLUMNS = ["Name", "Size", "Type", "Modified", "Packed"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dark_mode: bool = True
        self.all_items: List[ArchiveItem] = []
        self.displayed_items: List[ArchiveItem] = []
        self.current_entry_point: str = ""
        self.current_subfolder: str = ""

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        # Search bar
        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Filter files in current folder...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self._filter_items)
        self.layout.addWidget(self.search_bar)

        # Table
        self.table = FileTableWidget(self)
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Size
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Type
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Modified
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Packed

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.files_dropped_on_item.connect(self._on_files_dropped)
        self.table.drag_export_requested.connect(self.drag_export_requested.emit)
        self.table.delete_pressed.connect(self._on_delete_key)
        self.table.enter_pressed.connect(self._on_enter_key)

        self.layout.addWidget(self.table)

    def set_location_context(self, entry_point_name: str, subfolder: str = "") -> None:
        self.current_entry_point = entry_point_name
        self.current_subfolder = subfolder.strip("/").replace("\\", "/")

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self.set_items(self.all_items)

    def set_items(self, items: List[ArchiveItem]) -> None:
        self.all_items = items
        self._filter_items(self.search_bar.text())

    def _filter_items(self, text: str) -> None:
        query = text.strip().lower()
        if query:
            self.displayed_items = [i for i in self.all_items if query in i.name.lower()]
        else:
            self.displayed_items = list(self.all_items)

        self._render_table()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self.displayed_items))

        for row, item in enumerate(self.displayed_items):
            # Column 0: Name with Category Icon
            name_item = QTableWidgetItem(item.name)
            icon = IconProvider.get_category_icon(item.category, dark_mode=self.dark_mode, size=18)
            name_item.setIcon(icon)
            name_item.setData(Qt.ItemDataRole.UserRole, item)

            # Column 1: Size
            size_str = "" if item.is_dir else format_size(item.size)
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Column 2: Type
            type_str = self._format_category_name(item.category)
            type_item = QTableWidgetItem(type_str)

            # Column 3: Modified
            mod_str = item.modified or ""
            mod_item = QTableWidgetItem(mod_str)

            # Column 4: Packed Size
            packed_str = "" if item.is_dir else format_size(item.packed_size)
            packed_item = QTableWidgetItem(packed_str)
            packed_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, type_item)
            self.table.setItem(row, 3, mod_item)
            self.table.setItem(row, 4, packed_item)

    def _format_category_name(self, cat: FileCategory) -> str:
        names = {
            FileCategory.ENTRY_POINT: "Entry Point",
            FileCategory.FOLDER: "Folder",
            FileCategory.IMAGE: "Image",
            FileCategory.TEXT: "Plain Text",
            FileCategory.CODE: "Source Code",
            FileCategory.DOCUMENT: "Document",
            FileCategory.EXECUTABLE_WINDOWS: "Windows Executable",
            FileCategory.EXECUTABLE_MACOS: "macOS Bundle",
            FileCategory.EXECUTABLE_UNIX: "Unix Executable",
            FileCategory.ARCHIVE: "Archive",
            FileCategory.AUDIO: "Audio",
            FileCategory.VIDEO: "Video",
            FileCategory.KEY_CERT: "Key / Certificate",
            FileCategory.GENERIC: "File",
        }
        return names.get(cat, "File")

    def get_selected_items(self) -> List[ArchiveItem]:
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        items: List[ArchiveItem] = []
        for r in selected_rows:
            if 0 <= r < len(self.displayed_items):
                items.append(self.displayed_items[r])
        return items

    def _on_selection_changed(self) -> None:
        items = self.get_selected_items()
        if len(items) == 1:
            self.item_selected.emit(items[0])
        else:
            self.item_selected.emit(None)

    def _on_double_clicked(self, table_item: QTableWidgetItem) -> None:
        row = table_item.row()
        if 0 <= row < len(self.displayed_items):
            self.item_double_clicked.emit(self.displayed_items[row])

    def _on_delete_key(self) -> None:
        items = self.get_selected_items()
        if items:
            self.delete_requested.emit(items)

    def _on_enter_key(self) -> None:
        items = self.get_selected_items()
        if len(items) == 1:
            self.item_double_clicked.emit(items[0])

    def _on_files_dropped(self, files: List[Path], target_item: Optional[ArchiveItem]) -> None:
        """Route dropped files to target folder or entry point."""
        if not self.current_entry_point:
            # We are in Vault Root
            if target_item and (target_item.category == FileCategory.ENTRY_POINT or target_item.is_dir):
                ep_name = target_item.entry_point_name or target_item.name
                self.files_dropped_on_entry_point.emit(files, ep_name)
            else:
                self.files_dropped_root.emit(files)
            return

        # Inside an entry point archive
        if target_item and target_item.is_dir:
            target_sub = target_item.path.strip("/")
            self.files_dropped_on_folder.emit(files, target_sub)
        else:
            self.files_dropped_on_folder.emit(files, self.current_subfolder)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        items = self.get_selected_items()

        if items:
            first = items[0]
            if first.is_dir:
                open_act = menu.addAction("Open Folder")
                open_act.triggered.connect(lambda: self.item_double_clicked.emit(first))
            else:
                preview_act = menu.addAction("Preview")
                preview_act.triggered.connect(lambda: self.item_double_clicked.emit(first))

                edit_act = menu.addAction("Edit in External App...")
                edit_act.setIcon(IconProvider.get_icon("edit", dark_mode=self.dark_mode, size=16))
                edit_act.triggered.connect(lambda: self.edit_external_requested.emit(first))

            export_act = menu.addAction("Export / Save As...")
            export_act.setIcon(IconProvider.get_icon("export", dark_mode=self.dark_mode, size=16))
            export_act.triggered.connect(lambda: self.export_requested.emit(items))

            if len(items) == 1:
                rename_act = menu.addAction("Rename...")
                rename_act.triggered.connect(lambda: self.rename_requested.emit(first))

            delete_act = menu.addAction("Delete")
            delete_act.setIcon(IconProvider.get_icon("trash", dark_mode=self.dark_mode, size=16))
            delete_act.triggered.connect(lambda: self.delete_requested.emit(items))
            menu.addSeparator()

        add_files_act = menu.addAction("Add Files Here...")
        add_files_act.setIcon(IconProvider.get_icon("add_file", dark_mode=self.dark_mode, size=16))
        add_files_act.triggered.connect(self.add_files_requested.emit)

        new_folder_act = menu.addAction("New Folder...")
        new_folder_act.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16))
        new_folder_act.triggered.connect(self.create_folder_requested.emit)

        menu.exec(self.table.viewport().mapToGlobal(pos))
