"""Modern modal dialog presenting application update status and GitHub releases."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vaultables.config import AppConfig
from vaultables.core.updater import GITHUB_RELEASES_URL, UpdateInfo
from vaultables.gui.icons import IconProvider


class UpdateDialog(QDialog):
    """Modern modal dialog displaying update availability, release notes, and download links."""

    def __init__(
        self,
        update_info: UpdateInfo,
        parent: Optional[QWidget] = None,
        dark_mode: bool = True,
    ) -> None:
        super().__init__(parent)
        self.update_info = update_info
        self.dark_mode = dark_mode
        self.config = AppConfig()

        title = "Update Available" if update_info.available else ("Update Check" if not update_info.error else "Update Error")
        self.setWindowTitle(title)
        self.setFixedSize(500, 460 if (update_info.available and update_info.release_notes) else 320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header with Icon & Title
        header = QHBoxLayout()
        header.setSpacing(14)

        icon_lbl = QLabel(self)
        icon_name = "update" if update_info.available else ("info" if not update_info.error else "info")
        icon_lbl.setPixmap(IconProvider.get_pixmap(icon_name, dark_mode=self.dark_mode, size=40))
        header.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        if update_info.available:
            main_title = QLabel("New Version Available!", self)
            main_title.setStyleSheet("font-size: 16px; font-weight: 700;")
            sub_title = QLabel(
                f"Vaultables <b>v{update_info.latest_version}</b> is now available (you have v{update_info.current_version}).",
                self,
            )
            sub_title.setTextFormat(Qt.TextFormat.RichText)
            sub_title.setStyleSheet("color: #38bdf8; font-size: 12px;" if self.dark_mode else "color: #0284c7; font-size: 12px;")
        elif update_info.error:
            main_title = QLabel("Update Check Failed", self)
            main_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f87171;")
            sub_title = QLabel("Unable to contact GitHub release server.", self)
            sub_title.setStyleSheet("color: #94a3b8; font-size: 12px;" if self.dark_mode else "color: #64748b; font-size: 12px;")
        else:
            main_title = QLabel("You're Up to Date!", self)
            main_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #34d399;" if self.dark_mode else "font-size: 16px; font-weight: 700; color: #059669;")
            sub_title = QLabel(
                f"Vaultables <b>v{update_info.current_version}</b> is currently the latest version.",
                self,
            )
            sub_title.setTextFormat(Qt.TextFormat.RichText)
            sub_title.setStyleSheet("color: #94a3b8; font-size: 12px;" if self.dark_mode else "color: #64748b; font-size: 12px;")

        title_layout.addWidget(main_title)
        title_layout.addWidget(sub_title)
        header.addLayout(title_layout)
        header.addStretch()
        layout.addLayout(header)

        # Divider
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #334155;" if self.dark_mode else "color: #e2e8f0;")
        layout.addWidget(divider)

        # Body: Release Notes or Error Details
        if update_info.available:
            if update_info.release_notes:
                notes_lbl = QLabel("Release Notes & Highlights:", self)
                notes_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
                layout.addWidget(notes_lbl)

                notes_edit = QTextEdit(self)
                notes_edit.setReadOnly(True)
                notes_edit.setPlainText(update_info.release_notes)
                notes_edit.setStyleSheet(
                    "QTextEdit { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 8px; font-size: 12px; line-height: 1.4; color: #cbd5e1; }"
                    if self.dark_mode else
                    "QTextEdit { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px; font-size: 12px; line-height: 1.4; color: #334155; }"
                )
                layout.addWidget(notes_edit)
            else:
                info_lbl = QLabel("A new build has been published on GitHub with bug fixes and enhancements.", self)
                info_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;" if self.dark_mode else "color: #64748b; font-size: 12px;")
                layout.addWidget(info_lbl)
        elif update_info.error:
            err_box = QTextEdit(self)
            err_box.setReadOnly(True)
            err_box.setMaximumHeight(80)
            err_box.setPlainText(f"Error details:\n{update_info.error}\n\nPlease check your network connection or firewall.")
            err_box.setStyleSheet(
                "QTextEdit { background-color: #1e1b4b; border: 1px solid #ef4444; border-radius: 6px; padding: 8px; font-size: 11px; color: #fca5a5; }"
                if self.dark_mode else
                "QTextEdit { background-color: #fef2f2; border: 1px solid #f87171; border-radius: 6px; padding: 8px; font-size: 11px; color: #991b1b; }"
            )
            layout.addWidget(err_box)
        else:
            up_to_date_lbl = QLabel(
                "No updates found. You have the most recent release with all security patches and performance improvements.",
                self,
            )
            up_to_date_lbl.setWordWrap(True)
            up_to_date_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;" if self.dark_mode else "color: #64748b; font-size: 12px;")
            layout.addWidget(up_to_date_lbl)

        layout.addStretch()

        # Startup auto-check preference checkbox
        self.chk_auto = QCheckBox("Check for updates automatically on startup", self)
        self.chk_auto.setChecked(self.config.is_check_updates_enabled())
        self.chk_auto.setStyleSheet("font-size: 12px; color: #94a3b8;" if self.dark_mode else "font-size: 12px; color: #475569;")
        self.chk_auto.toggled.connect(self._on_auto_check_toggled)
        layout.addWidget(self.chk_auto)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        if update_info.available:
            self.btn_close = QPushButton("Later", self)
            self.btn_close.clicked.connect(self.reject)
            btn_layout.addWidget(self.btn_close)

            self.btn_download = QPushButton("Download Update", self)
            self.btn_download.setProperty("class", "primary")
            self.btn_download.clicked.connect(self._open_release_url)
            btn_layout.addWidget(self.btn_download)
        elif update_info.error:
            self.btn_releases = QPushButton("View Releases on GitHub", self)
            self.btn_releases.clicked.connect(self._open_release_url)
            btn_layout.addWidget(self.btn_releases)

            self.btn_close = QPushButton("Close", self)
            self.btn_close.clicked.connect(self.accept)
            btn_layout.addWidget(self.btn_close)
        else:
            self.btn_close = QPushButton("OK", self)
            self.btn_close.setProperty("class", "primary")
            self.btn_close.clicked.connect(self.accept)
            btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _on_auto_check_toggled(self, checked: bool) -> None:
        self.config.set_check_updates_enabled(checked)

    def _open_release_url(self) -> None:
        target_url = self.update_info.release_url or GITHUB_RELEASES_URL
        QDesktopServices.openUrl(QUrl(target_url))
        self.accept()
