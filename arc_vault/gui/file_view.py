"""Table view component displaying archives, folders, and encrypted files."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QEvent, QMimeData, QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent
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
    """QTableWidget with custom drag-and-drop and key handling."""

    files_dropped = pyqtSignal(list)  # List[Path]
    delete_pressed = pyqtSignal()
    enter_pressed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
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

        if file_paths:
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)


class FileExplorerView(QWidget):
    """File table view with search filter, sorting, and context menus."""

    item_selected = pyqtSignal(object)  # Optional[ArchiveItem]
    item_double_clicked = pyqtSignal(object)  # ArchiveItem
    files_dropped = pyqtSignal(list)  # List[Path]
    create_folder_requested = pyqtSignal()
    add_files_requested = pyqtSignal()
    export_requested = pyqtSignal(list)  # List[ArchiveItem]
    delete_requested = pyqtSignal(list)  # List[ArchiveItem]
    rename_requested = pyqtSignal(ArchiveItem)

    COLUMNS = ["Name", "Size", "Type", "Modified", "Packed"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dark_mode: bool = True
        self.all_items: List[ArchiveItem] = []
        self.displayed_items: List[ArchiveItem] = []

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
        self.table.files_dropped.connect(self.files_dropped.emit)
        self.table.delete_pressed.connect(self._on_delete_key)
        self.table.enter_pressed.connect(self._on_enter_key)

        self.layout.addWidget(self.table)

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self.set_items(self.all_items)

    def set_items(self, items: List[ArchiveItem]) -> None:
        """Populate table with archive items."""
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

            export_act = menu.addAction("Export / Save As...")
            export_act.setIcon(IconProvider.get_icon("download", dark_mode=self.dark_mode, size=16))
            export_act.triggered.connect(lambda: self.export_requested.emit(items))

            if len(items) == 1:
                rename_act = menu.addAction("Rename...")
                rename_act.triggered.connect(lambda: self.rename_requested.emit(first))

            delete_act = menu.addAction("Delete")
            delete_act.setIcon(IconProvider.get_icon("trash", dark_mode=self.dark_mode, size=16))
            delete_act.triggered.connect(lambda: self.delete_requested.emit(items))
            menu.addSeparator()

        add_files_act = menu.addAction("Add Files Here...")
        add_files_act.setIcon(IconProvider.get_icon("upload", dark_mode=self.dark_mode, size=16))
        add_files_act.triggered.connect(self.add_files_requested.emit)

        new_folder_act = menu.addAction("New Folder...")
        new_folder_act.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16))
        new_folder_act.triggered.connect(self.create_folder_requested.emit)

        menu.exec(self.table.viewport().mapToGlobal(pos))
