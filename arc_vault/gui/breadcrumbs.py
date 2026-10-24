"""Interactive breadcrumb navigation bar for ArcVault."""

from __future__ import annotations

from typing import List, Optional
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)

from arc_vault.gui.icons import IconProvider


class BreadcrumbBar(QWidget):
    """Horizontal bar displaying interactive clickable path segments."""

    path_changed = pyqtSignal(str, str)  # (entry_point_name, subfolder_path)
    refresh_requested = pyqtSignal()
    up_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.entry_point_name: str = ""
        self.current_subfolder: str = ""
        self.dark_mode: bool = True

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(6, 4, 6, 4)
        self.layout.setSpacing(4)

        # Up navigation button
        self.btn_up = QToolButton(self)
        self.btn_up.setToolTip("Go to Parent Folder (Up)")
        self.btn_up.setIconSize(QSize(16, 16))
        self.btn_up.clicked.connect(self._on_up_clicked)
        self.layout.addWidget(self.btn_up)

        # Refresh button
        self.btn_refresh = QToolButton(self)
        self.btn_refresh.setToolTip("Refresh Current View")
        self.btn_refresh.setIconSize(QSize(16, 16))
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.layout.addWidget(self.btn_refresh)

        # Separator line
        sep = QLabel("|", self)
        sep.setStyleSheet("color: #64748b; padding: 0 4px;")
        self.layout.addWidget(sep)

        # Container for breadcrumb segments
        self.segments_container = QWidget(self)
        self.segments_layout = QHBoxLayout(self.segments_container)
        self.segments_layout.setContentsMargins(0, 0, 0, 0)
        self.segments_layout.setSpacing(2)
        self.layout.addWidget(self.segments_container)

        self.layout.addStretch()
        self.update_icons()

    def update_icons(self) -> None:
        self.btn_up.setIcon(IconProvider.get_icon("arrow_up", dark_mode=self.dark_mode, size=16))
        self.btn_refresh.setIcon(IconProvider.get_icon("refresh", dark_mode=self.dark_mode, size=16))

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self.update_icons()
        self.set_path(self.entry_point_name, self.current_subfolder)

    def set_path(self, entry_point_name: str, subfolder: str = "") -> None:
        """Update breadcrumbs display."""
        self.entry_point_name = entry_point_name
        self.current_subfolder = subfolder.strip("/").replace("\\", "/")

        # Clear existing segment buttons
        while self.segments_layout.count():
            item = self.segments_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Vault Root button
        btn_root = QPushButton("Vault Root", self)
        btn_root.setFlat(True)
        btn_root.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_root.setStyleSheet(self._button_style(active=not entry_point_name))
        btn_root.clicked.connect(lambda: self.path_changed.emit("", ""))
        self.segments_layout.addWidget(btn_root)

        if not entry_point_name:
            self.btn_up.setEnabled(False)
            return

        # Arrow separator
        self._add_arrow()

        # Entry Point button (e.g. photos)
        is_ep_active = not self.current_subfolder
        btn_ep = QPushButton(entry_point_name, self)
        btn_ep.setIcon(IconProvider.get_icon("entry_point", dark_mode=self.dark_mode, size=16))
        btn_ep.setFlat(True)
        btn_ep.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ep.setStyleSheet(self._button_style(active=is_ep_active))
        btn_ep.clicked.connect(lambda: self.path_changed.emit(entry_point_name, ""))
        self.segments_layout.addWidget(btn_ep)

        # Subfolders if present (e.g. family > 2026)
        if self.current_subfolder:
            parts = self.current_subfolder.split("/")
            accum = ""
            for i, part in enumerate(parts):
                self._add_arrow()
                accum = f"{accum}/{part}" if accum else part
                is_last = (i == len(parts) - 1)

                btn_sub = QPushButton(part, self)
                btn_sub.setIcon(IconProvider.get_icon("folder", dark_mode=self.dark_mode, size=16))
                btn_sub.setFlat(True)
                btn_sub.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_sub.setStyleSheet(self._button_style(active=is_last))
                target_sub = accum
                btn_sub.clicked.connect(lambda checked=False, s=target_sub: self.path_changed.emit(self.entry_point_name, s))
                self.segments_layout.addWidget(btn_sub)

        self.btn_up.setEnabled(bool(entry_point_name))

    def _add_arrow(self) -> None:
        arrow = QLabel("›", self)
        arrow.setStyleSheet("color: #64748b; font-size: 16px; font-weight: bold; margin: 0 2px;")
        self.segments_layout.addWidget(arrow)

    def _on_up_clicked(self) -> None:
        if not self.entry_point_name:
            return

        if self.current_subfolder:
            parts = self.current_subfolder.split("/")
            if len(parts) > 1:
                parent_sub = "/".join(parts[:-1])
                self.path_changed.emit(self.entry_point_name, parent_sub)
            else:
                self.path_changed.emit(self.entry_point_name, "")
        else:
            # Go back to Vault Root
            self.path_changed.emit("", "")

    def _button_style(self, active: bool = False) -> str:
        color = ("#38bdf8" if self.dark_mode else "#0284c7") if active else ("#f8fafc" if self.dark_mode else "#1e293b")
        font_weight = "600" if active else "400"
        hover_bg = "#334155" if self.dark_mode else "#e2e8f0"
        return f"""
            QPushButton {{
                color: {color};
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 12px;
                font-weight: {font_weight};
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
            }}
        """
