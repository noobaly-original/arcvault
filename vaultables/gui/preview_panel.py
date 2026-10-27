"""Rich preview panel supporting images, PDFs, syntax-highlighted code/text, direct in-app editing, and executable file cards."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QPointF, QTimer, Qt, pyqtSignal
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

try:
    from PyQt6.QtPdf import QPdfDocument
    from PyQt6.QtPdfWidgets import QPdfView
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

from vaultables.core.models import ArchiveItem, FileCategory
from vaultables.gui.icons import IconProvider


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
    status_message = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dark_mode: bool = True
        self.current_item: Optional[ArchiveItem] = None
        self.current_file_path: Optional[Path] = None
        self._zoom_factor: float = 1.0
        self._auto_fit_image: bool = True
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
        self.btn_edit_text.setToolTip("Edit text directly inside Vaultables")
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

        # Stacked pages: 0=Empty, 1=Text, 2=Image, 3=Card, 4=PDF
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

        btn_zoom_in = QToolButton()
        btn_zoom_in.setText("+")
        btn_zoom_in.setToolTip("Zoom In")
        btn_zoom_in.clicked.connect(self._zoom_in)
        img_bar_layout.addWidget(btn_zoom_in)

        btn_zoom_out = QToolButton()
        btn_zoom_out.setText("-")
        btn_zoom_out.setToolTip("Zoom Out")
        btn_zoom_out.clicked.connect(self._zoom_out)
        img_bar_layout.addWidget(btn_zoom_out)

        btn_zoom_fit = QToolButton()
        btn_zoom_fit.setText("Fit")
        btn_zoom_fit.setToolTip("Fit to Window")
        btn_zoom_fit.clicked.connect(self._zoom_fit)
        img_bar_layout.addWidget(btn_zoom_fit)

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
        self.card_name.setStyleSheet("font-weight: bold; font-size: 15px;")
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

        # Page 4: PDF Viewer
        self.page_pdf = QWidget()
        pdf_layout = QVBoxLayout(self.page_pdf)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        pdf_layout.setSpacing(4)

        pdf_bar = QWidget()
        pdf_bar_layout = QHBoxLayout(pdf_bar)
        pdf_bar_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_pdf_info = QLabel("")
        self.lbl_pdf_info.setStyleSheet("color: #64748b; font-size: 11px;")
        pdf_bar_layout.addWidget(self.lbl_pdf_info)
        pdf_bar_layout.addStretch()

        self.btn_pdf_prev = QToolButton()
        self.btn_pdf_prev.setText("<")
        self.btn_pdf_prev.setToolTip("Previous Page")
        self.btn_pdf_prev.clicked.connect(self._pdf_prev_page)
        pdf_bar_layout.addWidget(self.btn_pdf_prev)

        self.btn_pdf_next = QToolButton()
        self.btn_pdf_next.setText(">")
        self.btn_pdf_next.setToolTip("Next Page")
        self.btn_pdf_next.clicked.connect(self._pdf_next_page)
        pdf_bar_layout.addWidget(self.btn_pdf_next)

        btn_pdf_zoom_in = QToolButton()
        btn_pdf_zoom_in.setText("+")
        btn_pdf_zoom_in.setToolTip("Zoom In")
        btn_pdf_zoom_in.clicked.connect(self._pdf_zoom_in)
        pdf_bar_layout.addWidget(btn_pdf_zoom_in)

        btn_pdf_zoom_out = QToolButton()
        btn_pdf_zoom_out.setText("-")
        btn_pdf_zoom_out.setToolTip("Zoom Out")
        btn_pdf_zoom_out.clicked.connect(self._pdf_zoom_out)
        pdf_bar_layout.addWidget(btn_pdf_zoom_out)

        btn_pdf_fit_w = QToolButton()
        btn_pdf_fit_w.setText("Fit Width")
        btn_pdf_fit_w.setToolTip("Fit to Width")
        btn_pdf_fit_w.clicked.connect(self._pdf_fit_width)
        pdf_bar_layout.addWidget(btn_pdf_fit_w)

        btn_pdf_fit_p = QToolButton()
        btn_pdf_fit_p.setText("Fit Page")
        btn_pdf_fit_p.setToolTip("Fit Page to Window")
        btn_pdf_fit_p.clicked.connect(self._pdf_fit_page)
        pdf_bar_layout.addWidget(btn_pdf_fit_p)

        pdf_layout.addWidget(pdf_bar)

        if HAS_PDF:
            self.pdf_document = QPdfDocument(self)
            self.pdf_view = QPdfView(self)
            self.pdf_view.setDocument(self.pdf_document)
            self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_pdf_page_changed)
            pdf_layout.addWidget(self.pdf_view)
        else:
            self.pdf_document = None
            self.pdf_view = None

        self.stack.addWidget(self.page_pdf)

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
        elif self.current_item:
            self._show_card(self.current_item)

    def set_empty(self) -> None:
        """Reset to empty preview state."""
        if HAS_PDF and hasattr(self, "pdf_document") and self.pdf_document:
            self.pdf_document.close()
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

    def show_card_only(self, item: ArchiveItem, status_note: str = "") -> None:
        """Display metadata card immediately without requiring an extracted local file."""
        if HAS_PDF and hasattr(self, "pdf_document") and self.pdf_document:
            self.pdf_document.close()
        self.current_item = item
        self.current_file_path = None
        self._is_editing_text = False
        self.lbl_title.setText(item.name)
        self.btn_open_external.setEnabled(False)
        self.btn_edit_external.setEnabled(False)
        self.btn_export.setEnabled(True)
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        self._show_card(item, status_note=status_note)

    @staticmethod
    def _is_text_file(path: Path) -> bool:
        """Quickly check if a file contains valid readable text without binary null bytes."""
        try:
            with open(path, "rb") as f:
                sample = f.read(1024)
            if b"\x00" in sample:
                return False
            sample.decode("utf-8", errors="strict")
            return True
        except Exception:
            return False

    def show_preview(self, item: ArchiveItem, local_path: Path) -> None:
        """Display preview based on file category and content."""
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
        elif (item.name.lower().endswith(".pdf") or local_path.suffix.lower() == ".pdf") and HAS_PDF:
            self._show_pdf(item, local_path)
        elif category in {FileCategory.TEXT, FileCategory.CODE}:
            self._show_text(item, local_path)
        elif category in {FileCategory.DOCUMENT, FileCategory.GENERIC}:
            if self._is_text_file(local_path):
                self._show_text(item, local_path)
            else:
                self._show_card(item)
        else:
            self._show_card(item)

    def _show_image(self, local_path: Path) -> None:
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        if HAS_PDF and hasattr(self, "pdf_document") and self.pdf_document:
            self.pdf_document.close()

        pixmap = QPixmap(str(local_path))
        if pixmap.isNull():
            self._show_card(self.current_item)
            return

        self._original_pixmap = pixmap
        self.lbl_img_dim.setText(f"{pixmap.width()} × {pixmap.height()} px • {format_size(local_path.stat().st_size)}")
        self.stack.setCurrentIndex(2)
        # Automatically fit image to canvas viewport
        self._zoom_fit()
        QTimer.singleShot(0, self._zoom_fit)

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
        self._auto_fit_image = False
        self._zoom_factor = min(self._zoom_factor * 1.25, 5.0)
        self._update_image_display()

    def _zoom_out(self) -> None:
        self._auto_fit_image = False
        self._zoom_factor = max(self._zoom_factor / 1.25, 0.1)
        self._update_image_display()

    def _zoom_fit(self, preserve_auto_fit: bool = False) -> None:
        if not preserve_auto_fit:
            self._auto_fit_image = True
        if not self._original_pixmap or self._original_pixmap.width() == 0 or self._original_pixmap.height() == 0:
            return
        area_size = self.image_scroll.viewport().size()
        w = area_size.width() - 20
        h = area_size.height() - 20
        if w > 10 and h > 10:
            factor_w = w / self._original_pixmap.width()
            factor_h = h / self._original_pixmap.height()
            self._zoom_factor = max(min(factor_w, factor_h, 1.0), 0.05)
        else:
            self._zoom_factor = 1.0
        self._update_image_display()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.stack.currentIndex() == 2 and getattr(self, "_auto_fit_image", False):
            self._zoom_fit(preserve_auto_fit=True)

    def _show_pdf(self, item: ArchiveItem, local_path: Path) -> None:
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)

        if not HAS_PDF or self.pdf_document is None or self.pdf_view is None:
            self._show_card(item)
            return

        err = self.pdf_document.load(str(local_path.resolve()))
        if err != QPdfDocument.Error.None_:
            self._show_card(item, status_note=f"PDF Error: {err.name}")
            return

        page_count = self.pdf_document.pageCount()
        if page_count == 0:
            self._show_card(item, status_note="Empty PDF document")
            return

        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._update_pdf_info()
        self.stack.setCurrentIndex(4)

    def _pdf_prev_page(self) -> None:
        if not HAS_PDF or not self.pdf_view or not self.pdf_document:
            return
        nav = self.pdf_view.pageNavigator()
        cur = nav.currentPage()
        if cur > 0:
            nav.jump(cur - 1, QPointF(), nav.currentZoom())

    def _pdf_next_page(self) -> None:
        if not HAS_PDF or not self.pdf_view or not self.pdf_document:
            return
        nav = self.pdf_view.pageNavigator()
        cur = nav.currentPage()
        total = self.pdf_document.pageCount()
        if cur + 1 < total:
            nav.jump(cur + 1, QPointF(), nav.currentZoom())

    def _pdf_zoom_in(self) -> None:
        if not HAS_PDF or not self.pdf_view:
            return
        cur = self.pdf_view.zoomFactor()
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(min(cur * 1.25, 5.0))

    def _pdf_zoom_out(self) -> None:
        if not HAS_PDF or not self.pdf_view:
            return
        cur = self.pdf_view.zoomFactor()
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(max(cur / 1.25, 0.1))

    def _pdf_fit_width(self) -> None:
        if not HAS_PDF or not self.pdf_view:
            return
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def _pdf_fit_page(self) -> None:
        if not HAS_PDF or not self.pdf_view:
            return
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)

    def _on_pdf_page_changed(self, page_index: int) -> None:
        self._update_pdf_info()

    def _update_pdf_info(self) -> None:
        if not HAS_PDF or not self.pdf_document or not self.pdf_view:
            return
        total = self.pdf_document.pageCount()
        cur = self.pdf_view.pageNavigator().currentPage() + 1 if total > 0 else 0
        size_str = ""
        if self.current_file_path and self.current_file_path.exists():
            size_str = f" • {format_size(self.current_file_path.stat().st_size)}"
        elif self.current_item and self.current_item.size:
            size_str = f" • {format_size(self.current_item.size)}"
        self.lbl_pdf_info.setText(f"Page {cur} of {total}{size_str}")
        self.btn_pdf_prev.setEnabled(cur > 1)
        self.btn_pdf_next.setEnabled(cur < total)

    def _show_text(self, item: ArchiveItem, local_path: Path) -> None:
        self._is_editing_text = False
        self.btn_copy_text.setVisible(True)
        self.btn_edit_text.setVisible(True)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        if HAS_PDF and hasattr(self, "pdf_document") and self.pdf_document:
            self.pdf_document.close()
        self.text_edit.setReadOnly(True)

        try:
            with open(local_path, "rb") as f:
                initial = f.read(1024)
            if b"\x00" in initial:
                self._show_card(item)
                return
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
            self.btn_edit_text.setToolTip("Edit text directly inside Vaultables")

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
        name = self.current_item.name if self.current_item else "file"
        self.status_message.emit(f"Editing '{name}' in-app. Click Save or press Ctrl+S when done.")

    def _cancel_text_edit(self) -> None:
        """Cancel editing mode and restore original view."""
        was_editing = self._is_editing_text
        self._is_editing_text = False
        if self.current_item and self.current_file_path:
            self._show_text(self.current_item, self.current_file_path)
        if was_editing:
            name = self.current_item.name if self.current_item else "file"
            self.status_message.emit(f"Discarded in-app edits for '{name}'.")

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

    def _show_card(self, item: ArchiveItem, status_note: str = "") -> None:
        self.btn_copy_text.setVisible(False)
        self.btn_edit_text.setVisible(False)
        self.btn_save_text.setVisible(False)
        self.btn_cancel_edit.setVisible(False)
        if HAS_PDF and hasattr(self, "pdf_document") and self.pdf_document:
            self.pdf_document.close()
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

        note_html = f"<br><span style='color: #38bdf8;'><i>{status_note}</i></span>" if status_note else ""

        details_html = f"""
            <b>Size:</b> {format_size(item.size)}<br>
            <b>Compressed:</b> {format_size(item.packed_size)}{ratio}<br>
            <b>Modified:</b> {item.modified or 'Unknown'}<br>
            <b>Encrypted:</b> AES-256 (7-Zip)<br>
            <b>CRC32:</b> {item.crc or 'N/A'}{note_html}
        """
        self.card_details.setText(details_html)
        self.stack.setCurrentIndex(3)

    def _copy_text(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        self.status_message.emit("Copied preview text to clipboard.")

    def _open_external(self) -> None:
        if not self.current_file_path or not self.current_file_path.exists():
            return

        name = self.current_item.name if self.current_item else self.current_file_path.name
        self.status_message.emit(f"Opening '{name}' in system application...")
        path_str = str(self.current_file_path.resolve())
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path_str])
            elif sys.platform == "win32":
                os.startfile(path_str)
            else:
                subprocess.Popen(["xdg-open", path_str])
        except Exception as e:
            print(f"[Vaultables] Failed to open external app: {e}")

    def _on_edit_external_clicked(self) -> None:
        if self.current_item:
            self.edit_external_requested.emit(self.current_item)

    def _on_export_clicked(self) -> None:
        if self.current_item:
            self.export_requested.emit(self.current_item)
