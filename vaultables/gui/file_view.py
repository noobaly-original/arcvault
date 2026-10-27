"""Table view component displaying archives, folders, and encrypted files with cross-platform drag-and-drop and recursive multi-entry search."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from PyQt6.QtCore import QEvent, QMimeData, QModelIndex, QPoint, QSize, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultables.core.models import ArchiveItem, FileCategory, is_ignorable_system_file
from vaultables.gui.icons import IconProvider
from vaultables.gui.preview_panel import format_size


class FileTableWidget(QTableWidget):
    """QTableWidget supporting cross-platform drop targeting and drag export."""

    files_dropped_on_item = pyqtSignal(list, object)  # (List[Path], Optional[ArchiveItem])
    drag_export_requested = pyqtSignal(list)          # List[ArchiveItem]
    internal_move_requested = pyqtSignal(str, list, object)  # (source_ep, item_paths, target_item)
    delete_pressed = pyqtSignal()
    enter_pressed = pyqtSignal()
    zoom_requested = pyqtSignal(int)  # +1 (larger/onward) or -1 (smaller/backward)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragEnabled(True)
        self._drag_start_pos: Optional[QPoint] = None
        self._zoom_delta_accum: float = 0.0
        self._is_search_mode: bool = False
        self._current_entry_point: str = ""
        self._current_subfolder: str = ""

    @property
    def is_search_mode(self) -> bool:
        parent = self.parent()
        if parent and hasattr(parent, "is_search_mode"):
            return bool(parent.is_search_mode)
        return self._is_search_mode

    @is_search_mode.setter
    def is_search_mode(self, val: bool) -> None:
        self._is_search_mode = bool(val)

    @property
    def current_entry_point(self) -> str:
        parent = self.parent()
        if parent and hasattr(parent, "current_entry_point"):
            return str(parent.current_entry_point)
        return self._current_entry_point

    @current_entry_point.setter
    def current_entry_point(self, val: str) -> None:
        self._current_entry_point = str(val)

    @property
    def current_subfolder(self) -> str:
        parent = self.parent()
        if parent and hasattr(parent, "current_subfolder"):
            return str(parent.current_subfolder)
        return self._current_subfolder

    @current_subfolder.setter
    def current_subfolder(self, val: str) -> None:
        self._current_subfolder = str(val)

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
            return

        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return

        selected_rows = sorted(set(idx.row() for idx in selected_indexes))
        items: List[ArchiveItem] = []
        for r in selected_rows:
            it = self.item(r, 0)
            if it:
                archive_item = it.data(Qt.ItemDataRole.UserRole)
                if archive_item:
                    items.append(archive_item)

        if not items:
            return

        if self.receivers(self.drag_export_requested) > 0:
            self.drag_export_requested.emit(items)
            return

        drag = QDrag(self)
        mime = QMimeData()

        # Custom internal mime type for internal folder reordering
        import json
        internal_data = {
            "source_entry_point": items[0].entry_point_name,
            "items": [it.path for it in items],
            "entry_point": items[0].entry_point_name,
            "paths": [it.path for it in items],
        }
        mime.setData("application/x-vaultables-internal", json.dumps(internal_data).encode("utf-8"))

        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def _is_valid_drop_target(self, event, target_item: Optional[ArchiveItem]) -> bool:
        """
        Validate whether dropping on target_item (or empty canvas) is allowed:
        - Regular files can NEVER be drop targets (cannot drop files onto other files or onto itself).
        - A folder cannot be dropped onto itself or into any of its subfolders.
        - Items cannot be dropped into the folder they already reside in.
        """
        # Rule 1: A regular file cannot be a drop target under any circumstance.
        if target_item is not None and not (target_item.is_dir or target_item.category == FileCategory.ENTRY_POINT):
            return False

        mime = event.mimeData()

        # Rule 2: Internal drag inside Vaultables
        if mime.hasFormat("application/x-vaultables-internal"):
            try:
                import json
                raw = bytes(mime.data("application/x-vaultables-internal"))
                d = json.loads(raw.decode("utf-8"))
                source_ep = d.get("source_entry_point") or d.get("entry_point") or ""
                item_paths = [p.strip("/") for p in (d.get("items") or d.get("paths") or [])]
            except Exception:
                return False

            if not item_paths:
                return False

            if target_item is not None:
                target_path = target_item.path.strip("/")

                # Cannot drop a folder onto itself
                if target_path in item_paths:
                    return False

                # Cannot drop a folder into one of its descendants
                for p in item_paths:
                    if target_path.startswith(p + "/"):
                        return False

                # Cannot drop items into the exact folder they are already inside
                if all("/".join(p.split("/")[:-1]) == target_path for p in item_paths):
                    return False

                return True
            else:
                # Hovering over empty canvas space
                # If all dragged items are already in current subfolder in the same entry point, it's a no-op
                if not self.is_search_mode and source_ep == self.current_entry_point:
                    cur = self.current_subfolder.strip("/")
                    if all("/".join(p.split("/")[:-1]) == cur for p in item_paths):
                        return False
                return True

        # Rule 3: External files from OS (files can be dropped into folders or empty area)
        if mime.hasUrls():
            return True

        return False

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat("application/x-vaultables-internal") or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        row = self.rowAt(pos.y())

        target_item: Optional[ArchiveItem] = None
        if row >= 0:
            item_widget = self.item(row, 0)
            if item_widget:
                target_item = item_widget.data(Qt.ItemDataRole.UserRole)

        if self._is_valid_drop_target(event, target_item):
            if row >= 0 and target_item:
                self.selectRow(row)
            else:
                self.clearSelection()
            event.acceptProposedAction()
        else:
            self.clearSelection()
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        row = self.rowAt(pos.y())

        target_item: Optional[ArchiveItem] = None
        if row >= 0:
            item_widget = self.item(row, 0)
            if item_widget:
                target_item = item_widget.data(Qt.ItemDataRole.UserRole)

        if not self._is_valid_drop_target(event, target_item):
            self.clearSelection()
            event.ignore()
            return

        # 1. Handle Internal Drag & Move
        if event.mimeData().hasFormat("application/x-vaultables-internal"):
            try:
                import json
                raw_bytes = bytes(event.mimeData().data("application/x-vaultables-internal"))
                data = json.loads(raw_bytes.decode("utf-8"))
                source_ep = data.get("source_entry_point") or data.get("entry_point") or ""
                item_paths = data.get("items") or data.get("paths") or []
                if item_paths:
                    self.internal_move_requested.emit(source_ep, item_paths, target_item)
                    self.clearSelection()
                    event.acceptProposedAction()
                    return
            except Exception as e:
                print(f"[Vaultables] Failed to process internal drop: {e}")
            self.clearSelection()
            event.ignore()
            return

        # 2. Handle External Files Drop from OS
        urls = event.mimeData().urls()
        if urls:
            file_paths = [
                Path(u.toLocalFile()) for u in urls
                if u.isLocalFile() and not is_ignorable_system_file(Path(u.toLocalFile()))
            ]
            if file_paths:
                self.files_dropped_on_item.emit(file_paths, target_item)
                self.clearSelection()
                event.acceptProposedAction()
                return

        self.clearSelection()
        event.ignore()

    def wheelEvent(self, event: QWheelEvent) -> None:
        modifiers = event.modifiers()
        is_ctrl_held = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        if is_ctrl_held:
            delta_y = event.angleDelta().y()
            if delta_y == 0 and not event.pixelDelta().isNull():
                delta_y = event.pixelDelta().y()

            if delta_y != 0:
                self._zoom_delta_accum += delta_y
                threshold = 60.0
                if self._zoom_delta_accum >= threshold:
                    self._zoom_delta_accum = 0.0
                    self.zoom_requested.emit(1)
                    event.accept()
                    return
                elif self._zoom_delta_accum <= -threshold:
                    self._zoom_delta_accum = 0.0
                    self.zoom_requested.emit(-1)
                    event.accept()
                    return
                else:
                    event.accept()
                    return
            event.accept()
            return

        self._zoom_delta_accum = 0.0
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
        else:
            super().keyPressEvent(event)


class FileExplorerView(QWidget):
    """File table view with recursive search, multi-scope filtering, and drag-and-drop actions."""

    selection_changed = pyqtSignal(list)  # List[ArchiveItem]
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
    move_requested = pyqtSignal(list)  # List[ArchiveItem]
    internal_move_requested = pyqtSignal(str, list, object)  # (source_ep, item_paths, target_item)
    search_requested = pyqtSignal(str, str)  # (query_string, scope) -> scope in ("vault", "entry_point", "folder")
    reveal_requested = pyqtSignal(ArchiveItem)  # Reveal in enclosing vault folder
    refresh_requested = pyqtSignal()

    COLUMNS_NORMAL = ["Name", "Size", "Type", "Modified", "Packed"]
    COLUMNS_SEARCH = ["Name", "Location", "Size", "Type", "Modified", "Packed"]
    COLUMNS = COLUMNS_NORMAL

    # 10 Predefined File List Sizes (5th size, index 4, is default)
    # Sizes onward (> 4) are bigger; backward (< 4) are smaller
    LIST_SIZES: List[Dict[str, int]] = [
        {"row_height": 22, "icon_size": 14, "font_size": 10, "padding": 2},  # 1. Ultra Compact
        {"row_height": 25, "icon_size": 15, "font_size": 11, "padding": 3},  # 2. Compact
        {"row_height": 28, "icon_size": 16, "font_size": 11, "padding": 4},  # 3. Dense
        {"row_height": 32, "icon_size": 17, "font_size": 12, "padding": 5},  # 4. Moderate
        {"row_height": 36, "icon_size": 18, "font_size": 13, "padding": 6},  # 5. Default
        {"row_height": 42, "icon_size": 22, "font_size": 13, "padding": 7},  # 6. Comfortable
        {"row_height": 48, "icon_size": 26, "font_size": 14, "padding": 8},  # 7. Large
        {"row_height": 56, "icon_size": 32, "font_size": 15, "padding": 9},  # 8. Extra Large
        {"row_height": 64, "icon_size": 38, "font_size": 16, "padding": 10}, # 9. Huge
        {"row_height": 74, "icon_size": 46, "font_size": 17, "padding": 12}, # 10. Giant / Maximum
    ]
    DEFAULT_SIZE_INDEX: int = 4  # 5th size is default

    DEFAULT_COLUMN_WIDTHS: Dict[str, int] = {
        "Name": 280,
        "Location": 220,
        "Size": 95,
        "Type": 125,
        "Modified": 145,
        "Packed": 95,
    }

    list_size_changed = pyqtSignal(int)          # Emits new size_index (0..9)
    column_widths_changed = pyqtSignal(dict)     # Emits updated {col_name: width_px}

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dark_mode: bool = True
        self.all_items: List[ArchiveItem] = []
        self.displayed_items: List[ArchiveItem] = []
        self.current_entry_point: str = ""
        self.current_subfolder: str = ""
        self.is_search_mode: bool = False
        self.current_size_index: int = self.DEFAULT_SIZE_INDEX
        self._column_widths: Dict[str, int] = dict(self.DEFAULT_COLUMN_WIDTHS)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        # Search bar header layout with search input and scope selector
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)

        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Search files recursively across entire vault or subfolders... (Cmd+F)")
        self.search_bar.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_bar, stretch=1)

        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem("🌐 Entire Vault (Recursive)", "vault")
        self.scope_combo.addItem("📦 Current Archive (Recursive)", "entry_point")
        self.scope_combo.addItem("📂 Current Folder", "folder")
        self.scope_combo.setToolTip("Select search scope: entire vault, current archive, or current folder")
        search_layout.addWidget(self.scope_combo)

        self.layout.addLayout(search_layout)

        # Debounce timer for asynchronous search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._emit_search_requested)

        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)

        # Table
        self.table = FileTableWidget(self)
        self.table.setColumnCount(len(self.COLUMNS_NORMAL))
        self.table.setHorizontalHeaderLabels(self.COLUMNS_NORMAL)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        self._configure_table_headers()

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.files_dropped_on_item.connect(self._on_files_dropped)
        self.table.internal_move_requested.connect(self.internal_move_requested.emit)
        self.table.drag_export_requested.connect(self.drag_export_requested.emit)
        self.table.delete_pressed.connect(self._on_delete_key)
        self.table.enter_pressed.connect(self._on_enter_key)
        self.table.zoom_requested.connect(self._on_zoom_requested)
        self.table.horizontalHeader().sectionResized.connect(self._on_header_section_resized)

        self.layout.addWidget(self.table)

    def _configure_table_headers(self) -> None:
        header = self.table.horizontalHeader()
        cols = self.COLUMNS_SEARCH if self.is_search_mode else self.COLUMNS_NORMAL

        header.blockSignals(True)
        for idx, col_name in enumerate(cols):
            # QHeaderView.ResizeMode.Interactive enables user to horizontally resize Name, Size, Type, etc.
            header.setSectionResizeMode(idx, QHeaderView.ResizeMode.Interactive)
            width = self._column_widths.get(col_name, self.DEFAULT_COLUMN_WIDTHS.get(col_name, 100))
            self.table.setColumnWidth(idx, width)

        header.setStretchLastSection(True)
        header.blockSignals(False)

    def _on_header_section_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        cols = self.COLUMNS_SEARCH if self.is_search_mode else self.COLUMNS_NORMAL
        if 0 <= logical_index < len(cols) and new_size > 20:
            col_name = cols[logical_index]
            self._column_widths[col_name] = new_size
            self.column_widths_changed.emit(dict(self._column_widths))

    def set_custom_column_widths(self, widths: Dict[str, int]) -> None:
        if isinstance(widths, dict):
            self._column_widths.update(widths)
            self._configure_table_headers()

    def _on_zoom_requested(self, direction: int) -> None:
        new_index = self.current_size_index + direction
        new_index = max(0, min(len(self.LIST_SIZES) - 1, new_index))
        if new_index != self.current_size_index:
            self.apply_list_size(new_index)

    def apply_list_size(self, size_index: int) -> None:
        self.current_size_index = max(0, min(len(self.LIST_SIZES) - 1, size_index))
        cfg = self.LIST_SIZES[self.current_size_index]

        self.table.setIconSize(QSize(cfg["icon_size"], cfg["icon_size"]))
        self.table.verticalHeader().setDefaultSectionSize(cfg["row_height"])

        font = self.table.font()
        font.setPointSize(cfg["font_size"])
        self.table.setFont(font)

        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, cfg["row_height"])
            name_item = self.table.item(r, 0)
            if name_item:
                archive_item = name_item.data(Qt.ItemDataRole.UserRole)
                if archive_item:
                    icon = IconProvider.get_category_icon(
                        archive_item.category,
                        dark_mode=self.dark_mode,
                        size=cfg["icon_size"],
                    )
                    name_item.setIcon(icon)

        self.list_size_changed.emit(self.current_size_index)

    def wheelEvent(self, event: QWheelEvent) -> None:
        modifiers = event.modifiers()
        is_ctrl_held = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        if is_ctrl_held:
            delta_y = event.angleDelta().y()
            if delta_y == 0 and not event.pixelDelta().isNull():
                delta_y = event.pixelDelta().y()
            if delta_y > 0:
                self._on_zoom_requested(1)
                event.accept()
                return
            elif delta_y < 0:
                self._on_zoom_requested(-1)
                event.accept()
                return
        super().wheelEvent(event)

    def set_location_context(self, entry_point_name: str, subfolder: str = "") -> None:
        self.current_entry_point = entry_point_name
        self.current_subfolder = subfolder.strip("/").replace("\\", "/")
        self._update_scope_combo_labels()

    def _update_scope_combo_labels(self) -> None:
        if not hasattr(self, "scope_combo"):
            return

        self.scope_combo.blockSignals(True)
        current_data = self.scope_combo.currentData() or "vault"
        self.scope_combo.clear()

        self.scope_combo.addItem("🌐 Entire Vault (Recursive)", "vault")
        if self.current_entry_point:
            self.scope_combo.addItem(f"📦 {self.current_entry_point}.7z (Recursive)", "entry_point")
            sub_label = f"/{self.current_subfolder}" if self.current_subfolder else "Root"
            self.scope_combo.addItem(f"📂 Current Folder ({sub_label})", "folder")
        else:
            self.scope_combo.addItem("📂 Vault Root Only", "folder")

        idx = self.scope_combo.findData(current_data)
        if idx >= 0:
            self.scope_combo.setCurrentIndex(idx)
        else:
            self.scope_combo.setCurrentIndex(0)
        self.scope_combo.blockSignals(False)

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self._render_table()

    def set_items(self, items: List[ArchiveItem]) -> None:
        self.all_items = items
        query = self.search_bar.text().strip()
        if query:
            self._on_search_text_changed(query)
        else:
            self.is_search_mode = False
            self.displayed_items = list(items)
            self._render_table()

    def set_search_results(self, items: List[ArchiveItem], query: str, scope: str) -> None:
        """Display recursive search results with location column."""
        self.is_search_mode = bool(query.strip())
        if self.search_bar.text() != query:
            self.search_bar.blockSignals(True)
            self.search_bar.setText(query)
            self.search_bar.blockSignals(False)
        self.displayed_items = list(items)
        self._render_table()

    def _on_search_text_changed(self, text: str) -> None:
        query = text.strip()
        if not query:
            self.is_search_mode = False
            self.displayed_items = list(self.all_items)
            self._render_table()
            self.search_requested.emit("", self.scope_combo.currentData() or "vault")
            return

        scope = self.scope_combo.currentData() or "vault"
        # Standalone / non-connected fallback (e.g. unit tests)
        if scope == "folder" and self.search_requested.receivers(self.search_requested) == 0:
            self.is_search_mode = False
            self.displayed_items = [i for i in self.all_items if query.lower() in i.name.lower()]
            self._render_table()
        else:
            self._search_timer.start()

    def _on_scope_changed(self, _index: int) -> None:
        query = self.search_bar.text().strip()
        if query:
            self._emit_search_requested()

    def _emit_search_requested(self) -> None:
        query = self.search_bar.text().strip()
        scope = self.scope_combo.currentData() if hasattr(self, "scope_combo") else "vault"
        self.search_requested.emit(query, scope or "vault")

    def _filter_items(self, text: str) -> None:
        """Compatibility wrapper for direct filtering calls."""
        self.search_bar.setText(text)
        query = text.strip().lower()
        if query:
            self.displayed_items = [i for i in self.all_items if query in i.name.lower()]
        else:
            self.displayed_items = list(self.all_items)
        self._render_table()

    def _format_item_location(self, item: ArchiveItem) -> str:
        if item.category == FileCategory.ENTRY_POINT:
            return "Vault Root"
        ep = f"{item.entry_point_name}.7z" if item.entry_point_name else "Vault Root"
        parts = item.path.strip("/").replace("\\", "/").split("/")
        if len(parts) > 1:
            folder_part = "/".join(parts[:-1])
            return f"{ep} / {folder_part}"
        return ep

    def _render_table(self) -> None:
        cols = self.COLUMNS_SEARCH if self.is_search_mode else self.COLUMNS_NORMAL
        if self.table.columnCount() != len(cols):
            self.table.setColumnCount(len(cols))
            self.table.setHorizontalHeaderLabels(cols)
            self._configure_table_headers()

        cfg = self.LIST_SIZES[self.current_size_index]
        self.table.setIconSize(QSize(cfg["icon_size"], cfg["icon_size"]))
        self.table.verticalHeader().setDefaultSectionSize(cfg["row_height"])
        font = self.table.font()
        font.setPointSize(cfg["font_size"])
        self.table.setFont(font)

        self.table.setRowCount(len(self.displayed_items))

        for row, item in enumerate(self.displayed_items):
            self.table.setRowHeight(row, cfg["row_height"])

            # Column 0: Name with Category Icon
            name_item = QTableWidgetItem(item.name)
            icon = IconProvider.get_category_icon(item.category, dark_mode=self.dark_mode, size=cfg["icon_size"])
            name_item.setIcon(icon)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_item.setData(Qt.ItemDataRole.UserRole, item)

            col_offset = 0
            if self.is_search_mode:
                col_offset = 1
                loc_str = self._format_item_location(item)
                loc_item = QTableWidgetItem(loc_str)
                loc_item.setForeground(QColor("#38bdf8" if self.dark_mode else "#0284c7"))
                loc_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, 1, loc_item)

            # Size
            size_str = "" if item.is_dir else format_size(item.size)
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Type
            type_str = self._format_category_name(item.category)
            type_item = QTableWidgetItem(type_str)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            # Modified
            mod_str = item.modified or ""
            mod_item = QTableWidgetItem(mod_str)
            mod_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            # Packed Size
            packed_str = "" if item.is_dir else format_size(item.packed_size)
            packed_item = QTableWidgetItem(packed_str)
            packed_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1 + col_offset, size_item)
            self.table.setItem(row, 2 + col_offset, type_item)
            self.table.setItem(row, 3 + col_offset, mod_item)
            self.table.setItem(row, 4 + col_offset, packed_item)

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

    def select_item_by_name(self, name: str) -> None:
        """Find and select an item row by its name."""
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text() == name:
                self.table.selectRow(r)
                self.table.scrollToItem(item)
                break

    def get_selected_items(self) -> List[ArchiveItem]:
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        items: List[ArchiveItem] = []
        for r in selected_rows:
            if 0 <= r < len(self.displayed_items):
                items.append(self.displayed_items[r])
        return items

    def _on_selection_changed(self) -> None:
        items = self.get_selected_items()
        self.selection_changed.emit(items)
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
        if target_item and (target_item.is_dir or target_item.category == FileCategory.ENTRY_POINT):
            target_sub = target_item.path.strip("/")
            self.files_dropped_on_folder.emit(files, target_sub)
        elif target_item is None:
            self.files_dropped_on_folder.emit(files, self.current_subfolder)
        else:
            # Dropping onto a regular file is disallowed
            return

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        items = self.get_selected_items()
        is_vault_root = (not self.current_entry_point and not self.is_search_mode)

        if items:
            first = items[0]
            is_entry_point = (first.category == FileCategory.ENTRY_POINT or is_vault_root)
            is_over_1gb = (first.size > 1024 * 1024 * 1024)

            if self.is_search_mode:
                reveal_act = menu.addAction("Reveal in Vault Folder")
                reveal_act.setIcon(IconProvider.get_icon("folder", dark_mode=self.dark_mode, size=16))
                reveal_act.triggered.connect(lambda: self.reveal_requested.emit(first))
                menu.addSeparator()

            if is_entry_point:
                open_act = menu.addAction("Open Entry Point")
                open_act.setIcon(IconProvider.get_icon("folder", dark_mode=self.dark_mode, size=16))
                open_act.triggered.connect(lambda: self.item_double_clicked.emit(first))
            elif first.is_dir:
                open_act = menu.addAction("Open Folder")
                open_act.setIcon(IconProvider.get_icon("folder", dark_mode=self.dark_mode, size=16))
                open_act.triggered.connect(lambda: self.item_double_clicked.emit(first))
            else:
                if is_over_1gb:
                    preview_act = menu.addAction("Preview (Disabled: >1GB)")
                    preview_act.setEnabled(False)
                else:
                    preview_act = menu.addAction("Preview")
                    preview_act.triggered.connect(lambda: self.item_double_clicked.emit(first))

                if is_over_1gb:
                    edit_act = menu.addAction("Edit in External App (Disabled: >1GB)")
                    edit_act.setIcon(IconProvider.get_icon("edit", dark_mode=self.dark_mode, size=16))
                    edit_act.setEnabled(False)
                else:
                    edit_act = menu.addAction("Edit in External App...")
                    edit_act.setIcon(IconProvider.get_icon("edit", dark_mode=self.dark_mode, size=16))
                    edit_act.triggered.connect(lambda: self.edit_external_requested.emit(first))

            menu.addSeparator()

            # "Move to Folder..." is only available inside archives, not for top-level Entry Points
            if not is_entry_point:
                move_act = menu.addAction("Move to Folder...")
                move_act.setIcon(IconProvider.get_icon("folder", dark_mode=self.dark_mode, size=16))
                move_act.triggered.connect(lambda: self.move_requested.emit(items))

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

        if is_vault_root:
            new_ep_act = menu.addAction("New Entry Point...")
            new_ep_act.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16))
            new_ep_act.triggered.connect(self.create_folder_requested.emit)
        else:
            add_files_act = menu.addAction("Add Files Here...")
            add_files_act.setIcon(IconProvider.get_icon("add_file", dark_mode=self.dark_mode, size=16))
            add_files_act.triggered.connect(self.add_files_requested.emit)

            new_folder_act = menu.addAction("New Folder...")
            new_folder_act.setIcon(IconProvider.get_icon("plus", dark_mode=self.dark_mode, size=16))
            new_folder_act.triggered.connect(self.create_folder_requested.emit)

        menu.addSeparator()
        refresh_act = menu.addAction("Refresh View")
        refresh_act.setIcon(IconProvider.get_icon("refresh", dark_mode=self.dark_mode, size=16))
        refresh_act.triggered.connect(self.refresh_requested.emit)

        menu.exec(self.table.viewport().mapToGlobal(pos))
