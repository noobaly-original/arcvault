"""About ArcVault dialog displaying version, contributors, and open source credits."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from arc_vault.gui.icons import IconProvider


class AboutDialog(QDialog):
    """Modern modal dialog presenting ArcVault information, contributors, and special thanks."""

    def __init__(self, parent: Optional[QWidget] = None, dark_mode: bool = True) -> None:
        super().__init__(parent)
        self.dark_mode = dark_mode

        self.setWindowTitle("About ArcVault")
        self.setFixedSize(520, 560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        # Header with Logo & Version
        header = QHBoxLayout()
        header.setSpacing(16)

        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(IconProvider.get_pixmap("vault", dark_mode=self.dark_mode, size=48))
        header.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_lbl = QLabel("ArcVault", self)
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; letter-spacing: -0.5px;")

        ver_lbl = QLabel("Version 2.0 • Chunked Decoupled Architecture", self)
        ver_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 600;" if self.dark_mode else "color: #0284c7; font-size: 12px; font-weight: 600;")

        sub_lbl = QLabel("Fast, Lightweight Encrypted Archive Explorer & Vault Utility", self)
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;" if self.dark_mode else "color: #64748b; font-size: 11px;")

        title_layout.addWidget(title_lbl)
        title_layout.addWidget(ver_lbl)
        title_layout.addWidget(sub_lbl)
        header.addLayout(title_layout)
        header.addStretch()
        layout.addLayout(header)

        # Divider
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #334155;" if self.dark_mode else "color: #e2e8f0;")
        layout.addWidget(divider)

        # Scrollable content area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 4, 8, 4)
        scroll_layout.setSpacing(14)

        # Contributors Section
        contrib_lbl = QLabel("👥 Contributors", scroll_content)
        contrib_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        scroll_layout.addWidget(contrib_lbl)

        contrib_text = QLabel(
            "• <b>Kenan (@noobaly-original)</b> — Project Creator & Core Developer<br>"
            "• <b>Antigravity (Google DeepMind)</b> — AI Pair Programmer & System Architect",
            scroll_content,
        )
        contrib_text.setTextFormat(Qt.TextFormat.RichText)
        contrib_text.setStyleSheet("font-size: 12px; line-height: 1.5; color: #cbd5e1;" if self.dark_mode else "font-size: 12px; line-height: 1.5; color: #334155;")
        contrib_text.setWordWrap(True)
        scroll_layout.addWidget(contrib_text)

        # Special Thanks Section
        thanks_lbl = QLabel("🙏 Special Thanks & Open Source Credits", scroll_content)
        thanks_lbl.setStyleSheet("font-size: 13px; font-weight: 700; margin-top: 6px;")
        scroll_layout.addWidget(thanks_lbl)

        thanks_desc = QLabel(
            "ArcVault stands on the shoulders of giants. Sincere gratitude to the creators and maintainers of these foundational open source projects:",
            scroll_content,
        )
        thanks_desc.setStyleSheet("font-size: 11px; color: #94a3b8;" if self.dark_mode else "font-size: 11px; color: #64748b;")
        thanks_desc.setWordWrap(True)
        scroll_layout.addWidget(thanks_desc)

        credits_html = """
        <div style="line-height: 1.45; font-size: 11px;">
        <p>• <b>7-Zip by Igor Pavlov</b><br>
        <span style="color: {muted};">The core archival and cryptographic engine behind ArcVault, providing rock-solid AES-256 header and data encryption (-mx=0, -mhe=on), instant SSD throughput, and universal vendor independence.</span></p>

        <p>• <b>PyQt6 (Riverbank Computing & The Qt Company)</b><br>
        <span style="color: {muted};">The world-class desktop application framework providing the sleek user interface, high-DPI Retina vector rendering, and responsive multi-threading worker pipeline.</span></p>

        <p>• <b>Pygments (Georg Brandl & team)</b><br>
        <span style="color: {muted};">The extensive syntax-highlighting engine driving code, script, and markdown previews in the viewer panel.</span></p>

        <p>• <b>Pillow / PIL (Jeffrey A. Clark & contributors)</b><br>
        <span style="color: {muted};">The premier imaging library powering high-performance image decoding, aspect ratio preservation, and dimension analysis.</span></p>

        <p>• <b>PyInstaller (David Cortesi & team)</b><br>
        <span style="color: {muted};">The cross-platform packaging utility enabling self-contained, standalone desktop binary compilation.</span></p>
        </div>
        """.format(muted="#94a3b8" if self.dark_mode else "#64748b")

        credits_lbl = QLabel(credits_html, scroll_content)
        credits_lbl.setTextFormat(Qt.TextFormat.RichText)
        credits_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1;" if self.dark_mode else "font-size: 11px; color: #334155;")
        credits_lbl.setWordWrap(True)
        scroll_layout.addWidget(credits_lbl)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Footer with Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_close = QPushButton("Close", self)
        self.btn_close.setProperty("class", "primary")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)
