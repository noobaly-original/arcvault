"""Minimalist, modern styling and themes (Dark & Light) for ArcVault."""

from __future__ import annotations


DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #0f172a;
    color: #f8fafc;
    font-family: system-ui, "SF Pro Text", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #f8fafc;
    outline: none;
}

/* Toolbars & Headers */
QToolBar {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
    padding: 6px;
    spacing: 8px;
}

QToolButton {
    background: transparent;
    color: #f1f5f9;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #334155;
}
QToolButton:pressed {
    background-color: #475569;
}
QToolButton:disabled {
    color: #64748b;
}

/* Splitters */
QSplitter::handle {
    background-color: #334155;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}
QPushButton:pressed {
    background-color: #475569;
}
QPushButton:disabled {
    background-color: #1e293b;
    color: #64748b;
    border-color: #1e293b;
}

QPushButton.primary {
    background-color: #0284c7;
    border: 1px solid #38bdf8;
    color: #ffffff;
    font-weight: 600;
}
QPushButton.primary:hover {
    background-color: #0369a1;
}
QPushButton.primary:pressed {
    background-color: #075985;
}

QPushButton.danger {
    background-color: #991b1b;
    border: 1px solid #ef4444;
    color: #ffffff;
}
QPushButton.danger:hover {
    background-color: #b91c1c;
}

/* Text Inputs & Combos */
QLineEdit {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #0284c7;
}
QLineEdit:focus {
    border: 1px solid #38bdf8;
}

QComboBox {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
}
QComboBox:hover {
    border-color: #475569;
}
QComboBox:focus {
    border-color: #38bdf8;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    color: #f8fafc;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px;
}

/* Tree & Table Views */
QTreeView, QTableView, QListWidget {
    background-color: #0f172a;
    alternate-background-color: #141e33;
    color: #f8fafc;
    border: none;
    gridline-color: #1e293b;
    selection-background-color: #1e3a5f;
    selection-color: #38bdf8;
}

QTreeView::item, QTableView::item, QListWidget::item {
    padding: 6px;
    border-radius: 4px;
}
QTreeView::item:hover, QTableView::item:hover, QListWidget::item:hover {
    background-color: #1e293b;
}
QTreeView::item:selected, QTableView::item:selected, QListWidget::item:selected {
    background-color: #1e3a5f;
    color: #38bdf8;
}

QHeaderView::section {
    background-color: #1e293b;
    color: #94a3b8;
    border: none;
    border-bottom: 1px solid #334155;
    border-right: 1px solid #334155;
    padding: 6px 10px;
    font-weight: 600;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #0f172a;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #0f172a;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #334155;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #475569;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Context Menus */
QMenu {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 10px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #38bdf8;
    color: #0f172a;
}
QMenu::separator {
    height: 1px;
    background-color: #334155;
    margin: 4px 0px;
}

/* Status Bar */
QStatusBar {
    background-color: #1e293b;
    border-top: 1px solid #334155;
    color: #94a3b8;
    padding: 2px 8px;
}

/* GroupBox & Labels */
QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #38bdf8;
}

QLabel {
    color: #f8fafc;
}
"""

LIGHT_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: system-ui, "SF Pro Text", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #0f172a;
    outline: none;
}

/* Toolbars & Headers */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 6px;
    spacing: 8px;
}

QToolButton {
    background: transparent;
    color: #1e293b;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #f1f5f9;
}
QToolButton:pressed {
    background-color: #e2e8f0;
}
QToolButton:disabled {
    color: #94a3b8;
}

/* Splitters */
QSplitter::handle {
    background-color: #e2e8f0;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* Buttons */
QPushButton {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background-color: #e2e8f0;
}
QPushButton:disabled {
    background-color: #f8fafc;
    color: #94a3b8;
    border-color: #e2e8f0;
}

QPushButton.primary {
    background-color: #0284c7;
    border: 1px solid #0369a1;
    color: #ffffff;
    font-weight: 600;
}
QPushButton.primary:hover {
    background-color: #0369a1;
}
QPushButton.primary:pressed {
    background-color: #075985;
}

QPushButton.danger {
    background-color: #dc2626;
    border: 1px solid #b91c1c;
    color: #ffffff;
}
QPushButton.danger:hover {
    background-color: #b91c1c;
}

/* Text Inputs & Combos */
QLineEdit {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #0284c7;
}
QLineEdit:focus {
    border: 1px solid #0284c7;
}

QComboBox {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
}
QComboBox:hover {
    border-color: #94a3b8;
}
QComboBox:focus {
    border-color: #0284c7;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #0f172a;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 4px;
}

/* Tree & Table Views */
QTreeView, QTableView, QListWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    color: #0f172a;
    border: none;
    gridline-color: #f1f5f9;
    selection-background-color: #e0f2fe;
    selection-color: #0369a1;
}

QTreeView::item, QTableView::item, QListWidget::item {
    padding: 6px;
    border-radius: 4px;
}
QTreeView::item:hover, QTableView::item:hover, QListWidget::item:hover {
    background-color: #f1f5f9;
}
QTreeView::item:selected, QTableView::item:selected, QListWidget::item:selected {
    background-color: #e0f2fe;
    color: #0369a1;
}

QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    padding: 6px 10px;
    font-weight: 600;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #f8fafc;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #f8fafc;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Context Menus */
QMenu {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 10px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background-color: #e2e8f0;
    margin: 4px 0px;
}

/* Status Bar */
QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    padding: 2px 8px;
}

/* GroupBox & Labels */
QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #0284c7;
}

QLabel {
    color: #0f172a;
}
"""


def get_stylesheet(dark_mode: bool = True) -> str:
    """Return the active QSS stylesheet based on dark/light mode."""
    return DARK_STYLESHEET if dark_mode else LIGHT_STYLESHEET
