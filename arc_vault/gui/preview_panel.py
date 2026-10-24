"""Rich preview panel supporting images, syntax-highlighted code/text, direct in-app editing, and executable file cards."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_for_filename, TextLexer
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

from arc_vault.core.models import ArchiveItem, FileCategory
from arc_vault.gui.icons import IconProvider


def format_size(bytes_size: int) -> str:
    """Format bytes into readable size string."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"


class PreviewPanel(QWidget):
    """Multi-view preview panel with direct editing and external editor integration."""

    export_requested = pyqtSignal(ArchiveItem)
    save_text_requested = pyqtSignal(object, str)  # (ArchiveItem, new_text)
    edit_external_requested = pyqtSignal(object)   # ArchiveItem

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dark_mode: bool = True
        self.current_item: Optional[ArchiveItem] = None
        self.current_file_path: Optional[Path] = None
        self._zoom_factor: float = 1.0
        self._original_pixmap: Optional[QPixmap] = None
        self._is_editing_text: bool = False
        self._original_text_content: str = ""

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)

        # Header bar
        self.header_widget = QWidget(self)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self.lbl_title = QLabel("Preview", self)
        self.lbl_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        header_layout.addWidget(self.lbl_title)

        header_layout.addStretch()

        # In-App Edit & Save buttons for text/code
        self.btn_edit_text = QToolButton(self)
        self.btn_edit_text.setText("Edit")
        self.btn_edit_text.setToolTip("Edit text directly inside ArcVault")
        self.btn_edit_text.clicked.connect(self._toggle_text_edit_mode)
        self.btn_edit_text.setVisible(False)
        header_layout.addWidget(self.btn_edit_text)

        self.btn_save_text = QToolButton(self)
        self.btn_save_text.setText("Save")
        self.btn_save_text.setToolTip("Save and re-encrypt into archive (Ctrl+S / Cmd+S)")
        self.btn_save_text.clicked.connect(self._save_in_app_text)
        self.btn_save_text.setVisible(False)
        self.btn_save_text.setStyleSheet("color: #10b981; font-weight: bold;")
        header_layout.addWidget(self.btn_save_text)

        self.btn_cancel_edit = QToolButton(self)
        self.btn_cancel_edit.setText("Cancel")
        self.btn_cancel_edit.setToolTip("Discard edits and reload")
        self.btn_cancel_edit.clicked.connect(self._cancel_text_edit)
        self.btn_cancel_edit.setVisible(False)
        header_layout.addWidget(self.btn_cancel_edit)

        # External Editor button
        self.btn_edit_external = QToolButton(self)
        self.btn_edit_external.setText("Edit Externally")
        self.btn_edit_external.setToolTip("Open in external editor and auto-update vault on save")
        self.btn_edit_external.clicked.connect(self._on_edit_external_clicked)
        header_layout.addWidget(self.btn_edit_external)

        self.btn_copy_text = QToolButton(self)
        self.btn_copy_text.setText("Copy")
        self.btn_copy_text.setToolTip("Copy text content to clipboard")
        self.btn_copy_text.clicked.connect(self._copy_text)
        self.btn_copy_text.setVisible(False)
        header_layout.addWidget(self.btn_copy_text)

        self.btn_open_external = QToolButton(self)
        self.btn_open_external.setText("Open")
        self.btn_open_external.setToolTip("Open in default system application")
        self.btn_open_external.clicked.connect(self._open_external)
        header_layout.addWidget(self.btn_open_external)

        self.btn_export = QToolButton(self)
        self.btn_export.setText("Export...")
        self.btn_export.setToolTip("Export this file to disk")
        self.btn_export.clicked.connect(self._on_export_clicked)
        header_layout.addWidget(self.btn_export)

        self.layout.addWidget(self.header_widget)

        # Stacked pages: 0=Empty, 1=Text, 2=Image, 3=Card
        self.stack = QStackedWidget(self)

        # Page 0: Empty
        self.page_empty = QWidget()
        empty_layout = QVBoxLayout(self.page_empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_icon = QLabel()
        self.lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_text = QLabel("Select a file to preview or edit")
        self.lbl_empty_text.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.lbl_empty_icon)
        empty_layout.addWidget(self.lbl_empty_text)
        self.stack.addWidget(self.page_empty)

        # Page 1: Text / Code Editor
        self.page_text = QWidget()
        text_layout = QVBoxLayout(self.page_text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Menlo, Consolas, Courier New, monospace", 11))
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        text_layout.addWidget(self.text_edit)
        self.stack.addWidget(self.page_text)

        # Shortcut for Save: Ctrl+S / Cmd+S
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self.text_edit)
        self.save_shortcut.activated.connect(self._on_save_shortcut)

        # Page 2: Image Viewer
        self.page_image = QWidget()
        img_layout = QVBoxLayout(self.page_image)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(4)

        img_bar = QWidget()
        img_bar_layout = QHBoxLayout(img_bar)
        img_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_img_dim = QLabel("")
        self.lbl_img_dim.setStyleSheet("color: #64748b; font-size: 11px;")
        img_bar_layout.addWidget(self.lbl_img_dim)
        img_bar_layout.addStretch()

        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setText("+")
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        img_bar_layout.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setText("-")
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        img_bar_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_fit = QToolButton()
        self.btn_zoom_fit.setText("Fit")
        self.btn_zoom_fit.clicked.connect(self._zoom_fit)
        img_bar_layout.addWidget(self.btn_zoom_fit)

        img_layout.addWidget(img_bar)

        self.image_scroll = QScrollArea(self)
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll.setWidget(self.lbl_image)
        img_layout.addWidget(self.image_scroll)
        self.stack.addWidget(self.page_image)

        # Page 3: Metadata Card
        self.page_card = QWidget()
        card_layout = QVBoxLayout(self.page_card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(12)

        self.card_icon = QLabel()
        self.card_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.card_icon)

        self.card_name = QLabel()
        self.card_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_name.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.card_name.setWordWrap(True)
        card_layout.addWidget(self.card_name)

        self.card_badge = QLabel()
        self.card_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.card_badge)

        self.card_details = QLabel()
        self.card_details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_details.setStyleSheet("color: #64748b; font-size: 12px; line-height: 1.5;")
        card_layout.addWidget(self.card_details)

        card_layout.addStretch()
        self.stack.addWidget(self.page_card)

        self.layout.addWidget(self.stack)

        self.set_empty()

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        self.lbl_empty_icon.setPixmap(
            IconProvider.get_pixmap("preview", dark_mode=self.dark_mode, size=36)
        )
        self.btn_edit_text.setIcon(IconProvider.get_icon("edit", dark_mode=self.dark_mode, size=16))
        self.btn_save_text.setIcon(IconProvider.get_icon("save", dark_mode=self.dark_mode, size=16))
        if self.current_item and self.current_file_path:
            self.show_preview(self.current_item, self.current_file_path)

    def set_empty(self) -> None:
        """Reset to empty preview state."""
        self.current_item = None
        self.current_file_path = None
        self._original_pixmap = None
        self._is_editing_text = False
        self.lbl_title.setText("Preview")
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        self.btn_edit_external.setEnabled(False)
        self.btn_open_external.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.lbl_empty_icon.setPixmap(
            IconProvider.get_pixmap("preview", dark_mode=self.dark_mode, size=36)
        )
        self.stack.setCurrentIndex(0)

    def show_preview(self, item: ArchiveItem, local_path: Path) -> None:
        """Display preview based on file category."""
        self.current_item = item
        self.current_file_path = local_path
        self._is_editing_text = False
        self.lbl_title.setText(item.name)
        self.btn_open_external.setEnabled(True)
        self.btn_edit_external.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)

        category = item.category

        if category == FileCategory.IMAGE:
            self._show_image(local_path)
        elif category in {FileCategory.TEXT, FileCategory.CODE}:
            self._show_text(item, local_path)
        else:
            self._show_card(item)

    def _show_image(self, local_path: Path) -> None:
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        pixmap = QPixmap(str(local_path))
        if pixmap.isNull():
            self._show_card(self.current_item)
            return

        self._original_pixmap = pixmap
        self._zoom_factor = 1.0
        self.lbl_img_dim.setText(f"{pixmap.width()} × {pixmap.height()} px • {format_size(local_path.stat().st_size)}")
        self._update_image_display()
        self.stack.setCurrentIndex(2)

    def _update_image_display(self) -> None:
        if not self._original_pixmap:
            return
        scaled = self._original_pixmap.scaled(
            int(self._original_pixmap.width() * self._zoom_factor),
            int(self._original_pixmap.height() * self._zoom_factor),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_image.setPixmap(scaled)

    def _zoom_in(self) -> None:
        self._zoom_factor = min(self._zoom_factor * 1.25, 5.0)
        self._update_image_display()

    def _zoom_out(self) -> None:
        self._zoom_factor = max(self._zoom_factor / 1.25, 0.1)
        self._update_image_display()

    def _zoom_fit(self) -> None:
        if not self._original_pixmap:
            return
        area_size = self.image_scroll.viewport().size()
        factor_w = (area_size.width() - 20) / self._original_pixmap.width()
        factor_h = (area_size.height() - 20) / self._original_pixmap.height()
        self._zoom_factor = min(factor_w, factor_h, 1.0)
        self._update_image_display()

    def _show_text(self, item: ArchiveItem, local_path: Path) -> None:
        self._is_editing_text = False
        self.btn_copy_text.setVisible(True)
        self.btn_edit_text.setVisible(True)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        self.text_edit.setReadOnly(True)

        try:
            content = local_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            self._show_card(item)
            return

        self._original_text_content = content

        if len(content) > 500000:
            content = content[:500000] + "\n\n... [File truncated for preview] ..."
            self.btn_edit_text.setEnabled(False)
            self.btn_edit_text.setToolTip("File too large for in-app editing. Use Edit Externally.")
        else:
            self.btn_edit_text.setEnabled(True)
            self.btn_edit_text.setToolTip("Edit text directly inside ArcVault")

        if HAS_PYGMENTS:
            try:
                lexer = get_lexer_for_filename(item.name, content)
            except Exception:
                lexer = TextLexer()

            pygments_style = "monokai" if self.dark_mode else "friendly"
            formatter = HtmlFormatter(style=pygments_style, full=True, noclasses=True)
            html = highlight(content, lexer, formatter)
            self.text_edit.setHtml(html)
        else:
            self.text_edit.setPlainText(content)

        self.stack.setCurrentIndex(1)

    def _toggle_text_edit_mode(self) -> None:
        """Switch to direct in-app text editing mode."""
        self._is_editing_text = True
        self.text_edit.setReadOnly(False)
        self.text_edit.setPlainText(self._original_text_content)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(True)
        self.btn_cancel_edit.setVisible(True)
        self.text_edit.setFocus()

    def _cancel_text_edit(self) -> None:
        """Cancel editing mode and restore original view."""
        self._is_editing_text = False
        if self.current_item and self.current_file_path:
            self._show_text(self.current_item, self.current_file_path)

    def _save_in_app_text(self) -> None:
        """Emit save signal with updated text content."""
        if not self.current_item:
            return
        new_text = self.text_edit.toPlainText()
        self.save_text_requested.emit(self.current_item, new_text)

    def _on_save_shortcut(self) -> None:
        if self._is_editing_text:
            self._save_in_app_text()

    def on_save_successful(self, new_text: str) -> None:
        """Called when vault finishes writing and re-encrypting the updated file."""
        self._original_text_content = new_text
        if self.current_file_path:
            try:
                self.current_file_path.write_text(new_text, encoding="utf-8")
            except Exception:
                pass
        self._cancel_text_edit()

    def _show_card(self, item: ArchiveItem) -> None:
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        self.card_icon.setPixmap(
            IconProvider.get_category_pixmap(item.category, dark_mode=self.dark_mode, size=64)
        )
        self.card_name.setText(item.name)

        if item.category == FileCategory.EXECUTABLE_WINDOWS:
            self.card_badge.setText("  WINDOWS EXECUTABLE  ")
            self.card_badge.setStyleSheet(
                "background-color: #1e3a8a; color: #93c5fd; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
            )
            self.card_badge.setVisible(True)
        elif item.category == FileCategory.EXECUTABLE_MACOS:
            self.card_badge.setText("  MACOS APPLICATION / BUNDLE  ")
            self.card_badge.setStyleSheet(
                "background-color: #831843; color: #fbcfe8; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
            )
            self.card_badge.setVisible(True)
        elif item.category == FileCategory.EXECUTABLE_UNIX:
            self.card_badge.setText("  UNIX / LINUX EXECUTABLE  ")
            self.card_badge.setStyleSheet(
                "background-color: #064e3b; color: #6ee7b7; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;"
            )
            self.card_badge.setVisible(True)
        else:
            self.card_badge.setVisible(False)

        ratio = ""
        if item.size > 0 and item.packed_size > 0:
            ratio_val = (1.0 - (item.packed_size / item.size)) * 100
            ratio = f"<br><b>Compression:</b> {ratio_val:.1f}% saved"

        details_html = f"""
            <b>Size:</b> {format_size(item.size)}<br>
            <b>Compressed:</b> {format_size(item.packed_size)}{ratio}<br>
            <b>Modified:</b> {item.modified or 'Unknown'}<br>
            <b>Encrypted:</b> AES-256 (7-Zip)<br>
            <b>CRC32:</b> {item.crc or 'N/A'}
        """
        self.card_details.setText(details_html)
        self.stack.setCurrentIndex(3)

    def _copy_text(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())

    def _open_external(self) -> None:
        if not self.current_file_path or not self.current_file_path.exists():
            return

        path_str = str(self.current_file_path.resolve())
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path_str])
            elif sys.platform == "win32":
                os.startfile(path_str)
            else:
                subprocess.Popen(["xdg-open", path_str])
        except Exception as e:
            print(f"[ArcVault] Failed to open external app: {e}")

    def _on_edit_external_clicked(self) -> None:
        if self.current_item:
            self.edit_external_requested.emit(self.current_item)

    def _on_export_clicked(self) -> None:
        if self.current_item:
            self.export_requested.emit(self.current_item)
