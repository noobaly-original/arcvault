"""Application entry point and Qt initialization."""

from __future__ import annotations

import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from arc_vault import __app_name__, __version__
from arc_vault.config import AppConfig
from arc_vault.gui.main_window import MainWindow


def main() -> int:
    """Initialize and run ArcVault application."""
    # High DPI attributes
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ArcVault")

    config = AppConfig()
    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
