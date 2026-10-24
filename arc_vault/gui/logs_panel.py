"""Logs and 7-Zip activity panel for monitoring operations, compression commands, and errors."""

from __future__ import annotations

import html
from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arc_vault.gui.icons import IconProvider
from arc_vault.logger import LogEntry, clear_log_history, get_log_history, log_emitter


class LogsPanel(QWidget):
    """Toggleable bottom pane displaying real-time application logs and 7-Zip commands."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dark_mode: bool = True
        self._entries: List[LogEntry] = []

        self._build_ui()
        self._connect_signals()

        # Load existing history
        for entry in get_log_history():
            self._entries.append(entry)
        self._refresh_display()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header toolbar
        self.header = QWidget(self)
        self.header.setObjectName("logsHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(10)

        self.lbl_title = QLabel("Activity & 7-Zip Logs", self.header)
        self.lbl_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        header_layout.addWidget(self.lbl_title)

        # Filter dropdown
        self.filter_combo = QComboBox(self.header)
        self.filter_combo.addItems(["All Logs", "7-Zip Only", "App & Security", "Errors & Warnings"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.filter_combo)

        # Search box
        self.search_edit = QLineEdit(self.header)
        self.search_edit.setPlaceholderText("Filter text...")
        self.search_edit.setMaximumWidth(180)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.search_edit)

        header_layout.addStretch()

        # Action buttons
        self.btn_copy = QToolButton(self.header)
        self.btn_copy.setText("Copy")
        self.btn_copy.setToolTip("Copy displayed logs to clipboard")
        self.btn_copy.clicked.connect(self._copy_logs)
        header_layout.addWidget(self.btn_copy)

        self.btn_clear = QToolButton(self.header)
        self.btn_clear.setText("Clear")
        self.btn_clear.setToolTip("Clear log view")
        self.btn_clear.clicked.connect(self._clear_logs)
        header_layout.addWidget(self.btn_clear)

        self.btn_close = QToolButton(self.header)
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Close logs pane")
        self.btn_close.clicked.connect(self.hide)
        header_layout.addWidget(self.btn_close)

        layout.addWidget(self.header)

        # Log content text edit
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # Monospace font
        font = QFont("JetBrains Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["JetBrains Mono", "SF Mono", "Menlo", "Consolas", "Courier New", "monospace"])
        self.text_edit.setFont(font)

        layout.addWidget(self.text_edit)

    def _connect_signals(self) -> None:
        log_emitter.entry_logged.connect(self._on_new_entry)

    def _on_new_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if self._matches_filter(entry):
            self._append_entry_to_view(entry)

    def _matches_filter(self, entry: LogEntry) -> bool:
        filter_mode = self.filter_combo.currentText()
        search_query = self.search_edit.text().strip().lower()

        if filter_mode == "7-Zip Only" and entry.category != "7ZIP":
            return False
        elif filter_mode == "App & Security" and entry.category not in ("APP", "SECURITY"):
            return False
        elif filter_mode == "Errors & Warnings" and entry.level not in ("WARNING", "ERROR"):
            return False

        if search_query:
            combined = f"{entry.timestamp} {entry.level} {entry.category} {entry.message}".lower()
            if search_query not in combined:
                return False

        return True

    def _format_entry_line(self, entry: LogEntry) -> str:
        # Theme-aware colors
        if self.dark_mode:
            ts_color = "#64748b"  # muted slate
            app_color = "#38bdf8"  # light cyan
            sz_color = "#c084fc"   # light purple
            sec_color = "#34d399"  # emerald
            info_color = "#94a3b8" # slate
            warn_color = "#fbbf24" # amber
            err_color = "#f87171"  # red
            body_color = "#f1f5f9"
        else:
            ts_color = "#94a3b8"
            app_color = "#0284c7"
            sz_color = "#7c3aed"
            sec_color = "#059669"
            info_color = "#475569"
            warn_color = "#d97706"
            err_color = "#dc2626"
            body_color = "#0f172a"

        cat_color = sz_color if entry.category == "7ZIP" else (sec_color if entry.category == "SECURITY" else app_color)
        lvl_color = err_color if entry.level == "ERROR" else (warn_color if entry.level == "WARNING" else info_color)

        safe_msg = html.escape(entry.message).replace("\n", "<br>&nbsp;&nbsp;&nbsp;&nbsp;")

        return (
            f"<div style='margin-bottom: 2px;'>"
            f"<span style='color:{ts_color};'>[{entry.timestamp}]</span> "
            f"<span style='color:{lvl_color}; font-weight:bold;'>[{entry.level}]</span> "
            f"<span style='color:{cat_color}; font-weight:bold;'>[{entry.category}]</span> "
            f"<span style='color:{body_color};'>{safe_msg}</span>"
            f"</div>"
        )

    def _append_entry_to_view(self, entry: LogEntry) -> None:
        html_line = self._format_entry_line(entry)

        scrollbar = self.text_edit.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= (scrollbar.maximum() - 15)

        self.text_edit.append(html_line)

        if was_at_bottom:
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _refresh_display(self) -> None:
        self.text_edit.clear()
        matching = [e for e in self._entries if self._matches_filter(e)]
        if matching:
            html_content = "".join(self._format_entry_line(e) for e in matching)
            self.text_edit.setHtml(html_content)
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _on_filter_changed(self) -> None:
        self._refresh_display()

    def _copy_logs(self) -> None:
        plain_text = self.text_edit.toPlainText()
        if plain_text:
            QApplication.clipboard().setText(plain_text)
            self.btn_copy.setText("Copied!")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_copy.setText("Copy"))

    def _clear_logs(self) -> None:
        self._entries.clear()
        clear_log_history()
        self.text_edit.clear()

    def set_theme(self, dark_mode: bool) -> None:
        self.dark_mode = dark_mode
        if dark_mode:
            self.header.setStyleSheet(
                "QWidget#logsHeader { background: #0f172a; border-top: 1px solid #334155; border-bottom: 1px solid #1e293b; }"
                "QLabel { color: #f1f5f9; }"
            )
            self.text_edit.setStyleSheet(
                "QTextEdit { background-color: #0b1120; color: #f1f5f9; border: none; padding: 6px; selection-background-color: #3b82f6; }"
            )
        else:
            self.header.setStyleSheet(
                "QWidget#logsHeader { background: #f1f5f9; border-top: 1px solid #cbd5e1; border-bottom: 1px solid #e2e8f0; }"
                "QLabel { color: #0f172a; }"
            )
            self.text_edit.setStyleSheet(
                "QTextEdit { background-color: #f8fafc; color: #0f172a; border: none; padding: 6px; selection-background-color: #93c5fd; }"
            )
        self._refresh_display()
