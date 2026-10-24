"""Dialogs for unlocking and creating vaults."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arc_vault.core.vault import Vault
from arc_vault.gui.icons import IconProvider
from arc_vault.gui.workers import UnlockWorker


class UnlockVaultDialog(QDialog):
    """Modern modal dialog prompting for the master vault password."""

    def __init__(self, vault: Vault, parent: Optional[QWidget] = None, dark_mode: bool = True) -> None:
        super().__init__(parent)
        self.vault = vault
        self.dark_mode = dark_mode
        self.worker: Optional[UnlockWorker] = None

        self.setWindowTitle(f"Unlock Vault - {self.vault.metadata.name if self.vault.metadata else 'Vault'}")
        self.setFixedSize(440, 290)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header with Vault icon
        header = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(IconProvider.get_pixmap("vault", dark_mode=self.dark_mode, size=32))
        header.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_lbl = QLabel(self.vault.metadata.name if self.vault.metadata else "Encrypted Vault", self)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        path_lbl = QLabel(str(self.vault.root_dir), self)
        path_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        path_lbl.setWordWrap(True)
        title_layout.addWidget(title_lbl)
        title_layout.addWidget(path_lbl)
        header.addLayout(title_layout)
        header.addStretch()
        layout.addLayout(header)

        # Instruction
        msg_lbl = QLabel("Enter password to unlock AES-256 archives in this vault:", self)
        msg_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;" if self.dark_mode else "font-size: 12px; color: #475569;")
        layout.addWidget(msg_lbl)

        # Password input row
        pwd_container = QWidget(self)
        pwd_layout = QHBoxLayout(pwd_container)
        pwd_layout.setContentsMargins(0, 0, 0, 0)
        pwd_layout.setSpacing(6)

        self.edit_password = QLineEdit(self)
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_password.setPlaceholderText("Master Password")
        self.edit_password.returnPressed.connect(self._on_unlock_clicked)
        pwd_layout.addWidget(self.edit_password)

        self.btn_toggle_eye = QToolButton(self)
        self.btn_toggle_eye.setIcon(IconProvider.get_icon("eye", dark_mode=self.dark_mode, size=18))
        self.btn_toggle_eye.setToolTip("Show / Hide Password")
        self.btn_toggle_eye.clicked.connect(self._toggle_password_visibility)
        pwd_layout.addWidget(self.btn_toggle_eye)

        layout.addWidget(pwd_container)

        # Error / Status message banner
        self.lbl_status = QLabel("", self)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 500;")
        self.lbl_status.setVisible(False)
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_unlock = QPushButton("Unlock Vault", self)
        self.btn_unlock.setProperty("class", "primary")
        self.btn_unlock.clicked.connect(self._on_unlock_clicked)
        btn_layout.addWidget(self.btn_unlock)

        layout.addLayout(btn_layout)

        self.edit_password.setFocus()

    def _toggle_password_visibility(self) -> None:
        if self.edit_password.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_eye.setIcon(IconProvider.get_icon("eye_off", dark_mode=self.dark_mode, size=18))
        else:
            self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_eye.setIcon(IconProvider.get_icon("eye", dark_mode=self.dark_mode, size=18))

    def _on_unlock_clicked(self) -> None:
        pwd = self.edit_password.text()
        if not pwd:
            self.lbl_status.setText("Please enter the vault password.")
            self.lbl_status.setVisible(True)
            return

        self.btn_unlock.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.edit_password.setEnabled(False)
        self.lbl_status.setText("Verifying AES-256 archive keys...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 12px;" if self.dark_mode else "color: #0284c7; font-size: 12px;")
        self.lbl_status.setVisible(True)

        self.worker = UnlockWorker(self.vault, pwd)
        self.worker.finished.connect(self._on_unlock_finished)
        self.worker.start()

    def _on_unlock_finished(self, success: bool, error_msg: str) -> None:
        self.btn_unlock.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.edit_password.setEnabled(True)

        if success:
            self.accept()
        else:
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 500;")
            self.lbl_status.setText(error_msg or "Incorrect password. Please verify and try again.")
            self.lbl_status.setVisible(True)
            self.edit_password.setFocus()
            self.edit_password.selectAll()


class CreateVaultDialog(QDialog):
    """Dialog to configure and create a brand new encrypted vault."""

    def __init__(self, parent: Optional[QWidget] = None, dark_mode: bool = True) -> None:
        super().__init__(parent)
        self.dark_mode = dark_mode
        self.created_vault_path: Optional[Path] = None
        self.created_vault_name: str = ""

        self.setWindowTitle("Create New Vault")
        self.setFixedSize(500, 420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(IconProvider.get_pixmap("vault", dark_mode=self.dark_mode, size=32))
        header.addWidget(icon_lbl)

        title_layout = QVBoxLayout()
        title_lbl = QLabel("New Encrypted Vault", self)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        sub_lbl = QLabel("Vault contents are stored as separate AES-256 7z archives.", self)
        sub_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        title_layout.addWidget(title_lbl)
        title_layout.addWidget(sub_lbl)
        header.addLayout(title_layout)
        header.addStretch()
        layout.addLayout(header)

        # Form fields
        form = QFormLayout()
        form.setSpacing(10)

        self.edit_name = QLineEdit(self)
        self.edit_name.setPlaceholderText("e.g. My Vault")
        self.edit_name.setText("My Vault")
        form.addRow("Vault Name:", self.edit_name)

        # Location picker
        loc_container = QWidget(self)
        loc_layout = QHBoxLayout(loc_container)
        loc_layout.setContentsMargins(0, 0, 0, 0)
        loc_layout.setSpacing(6)
        self.edit_location = QLineEdit(self)
        self.edit_location.setPlaceholderText("Select directory for vault...")
        self.edit_location.setText(str(Path.home() / "Documents" / "MyVault"))
        loc_layout.addWidget(self.edit_location)
        self.btn_browse = QPushButton("Browse...", self)
        self.btn_browse.clicked.connect(self._on_browse)
        loc_layout.addWidget(self.btn_browse)
        form.addRow("Location:", loc_container)

        # Password
        self.edit_password = QLineEdit(self)
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_password.setPlaceholderText("Enter master password (AES-256)")
        form.addRow("Password:", self.edit_password)

        self.edit_confirm = QLineEdit(self)
        self.edit_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_confirm.setPlaceholderText("Confirm password")
        form.addRow("Confirm:", self.edit_confirm)

        layout.addLayout(form)

        # Initial entry points selection
        group_lbl = QLabel("Initial Category Archives (Entry Points):", self)
        group_lbl.setStyleSheet("font-size: 12px; font-weight: 600; margin-top: 6px;")
        layout.addWidget(group_lbl)

        categories_layout = QHBoxLayout()
        self.chk_photos = QCheckBox("photos", self)
        self.chk_photos.setChecked(True)
        self.chk_documents = QCheckBox("documents", self)
        self.chk_documents.setChecked(True)
        self.chk_finance = QCheckBox("finance", self)
        self.chk_personal = QCheckBox("personal", self)
        categories_layout.addWidget(self.chk_photos)
        categories_layout.addWidget(self.chk_documents)
        categories_layout.addWidget(self.chk_finance)
        categories_layout.addWidget(self.chk_personal)
        layout.addLayout(categories_layout)

        # Error banner
        self.lbl_error = QLabel("", self)
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
        self.lbl_error.setVisible(False)
        layout.addWidget(self.lbl_error)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_create = QPushButton("Create Vault", self)
        self.btn_create.setProperty("class", "primary")
        self.btn_create.clicked.connect(self._on_create_clicked)
        btn_layout.addWidget(self.btn_create)

        layout.addLayout(btn_layout)

    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Vault Directory", str(Path.home()))
        if chosen:
            self.edit_location.setText(chosen)

    def _on_create_clicked(self) -> None:
        name = self.edit_name.text().strip()
        loc_str = self.edit_location.text().strip()
        pwd = self.edit_password.text()
        confirm = self.edit_confirm.text()

        if not name:
            self._show_error("Please provide a vault name.")
            return
        if not loc_str:
            self._show_error("Please choose a location directory.")
            return
        if not pwd:
            self._show_error("Password cannot be empty.")
            return
        if pwd != confirm:
            self._show_error("Passwords do not match.")
            return
        if len(pwd) < 6:
            self._show_error("Password must be at least 6 characters.")
            return

        loc_path = Path(loc_str)
        initial_eps: List[str] = []
        if self.chk_photos.isChecked():
            initial_eps.append("photos")
        if self.chk_documents.isChecked():
            initial_eps.append("documents")
        if self.chk_finance.isChecked():
            initial_eps.append("finance")
        if self.chk_personal.isChecked():
            initial_eps.append("personal")

        try:
            vault = Vault.create_vault(
                root_dir=loc_path,
                name=name,
                password=pwd,
                initial_entry_points=initial_eps,
            )
            self.created_vault_path = loc_path
            self.created_vault_name = name
            self.accept()
        except Exception as e:
            self._show_error(f"Failed to create vault: {e}")

    def _show_error(self, msg: str) -> None:
        self.lbl_error.setText(msg)
        self.lbl_error.setVisible(True)
