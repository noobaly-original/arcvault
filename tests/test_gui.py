"""Headless GUI tests for ArcVault components."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Force headless offscreen platform for Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from arc_vault.config import AppConfig
from arc_vault.core.models import ArchiveItem, FileCategory
from arc_vault.core.vault import Vault
from arc_vault.gui.breadcrumbs import BreadcrumbBar
from arc_vault.gui.file_view import FileExplorerView
from arc_vault.gui.icons import IconProvider
from arc_vault.gui.main_window import MainWindow
from arc_vault.gui.preview_panel import PreviewPanel
from arc_vault.gui.theme import DARK_STYLESHEET, LIGHT_STYLESHEET, get_stylesheet


class TestArcVaultGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="arcvault_gui_test_")
        self.root_path = Path(self.tmp_dir)
        self.config = AppConfig()
        self.config.known_vaults = []
        self.config.last_selected_vault_path = None

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_theme_stylesheets(self) -> None:
        dark_qss = get_stylesheet(dark_mode=True)
        light_qss = get_stylesheet(dark_mode=False)
        self.assertIn("#0f172a", dark_qss)
        self.assertIn("#f8fafc", light_qss)

    def test_icons_generation(self) -> None:
        for cat in FileCategory:
            icon = IconProvider.get_category_icon(cat, dark_mode=True, size=24)
            self.assertFalse(icon.isNull())
            self.assertEqual(icon.availableSizes()[0].width(), 24)

    def test_preview_panel_views(self) -> None:
        panel = PreviewPanel()

        # Empty state
        self.assertEqual(panel.stack.currentIndex(), 0)

        # Image preview
        img_path = self.root_path / "test.png"
        from PIL import Image
        im = Image.new("RGB", (64, 64), color="red")
        im.save(img_path)

        img_item = ArchiveItem(name="test.png", path="test.png", category=FileCategory.IMAGE)
        panel.show_preview(img_item, img_path)
        self.assertEqual(panel.stack.currentIndex(), 2)  # Page 2 = Image

        # Text preview
        txt_path = self.root_path / "code.py"
        txt_path.write_text("def hello():\n    return 42\n", encoding="utf-8")
        code_item = ArchiveItem(name="code.py", path="code.py", category=FileCategory.CODE)
        panel.show_preview(code_item, txt_path)
        self.assertEqual(panel.stack.currentIndex(), 1)  # Page 1 = Text

        # Executable card preview
        exe_item = ArchiveItem(name="setup.exe", path="setup.exe", category=FileCategory.EXECUTABLE_WINDOWS)
        panel.show_preview(exe_item, txt_path)
        self.assertEqual(panel.stack.currentIndex(), 3)  # Page 3 = Card
        self.assertIn("WINDOWS EXECUTABLE", panel.card_badge.text())

    def test_breadcrumb_bar(self) -> None:
        bar = BreadcrumbBar()
        bar.set_path("photos", "family/vacation")
        self.assertEqual(bar.entry_point_name, "photos")
        self.assertEqual(bar.current_subfolder, "family/vacation")
        self.assertTrue(bar.btn_up.isEnabled())

    def test_file_view_filtering(self) -> None:
        view = FileExplorerView()
        items = [
            ArchiveItem(name="photo1.jpg", path="photo1.jpg", category=FileCategory.IMAGE),
            ArchiveItem(name="notes.txt", path="notes.txt", category=FileCategory.TEXT),
            ArchiveItem(name="vacation.png", path="vacation.png", category=FileCategory.IMAGE),
        ]
        view.set_items(items)
        self.assertEqual(view.table.rowCount(), 3)

        # Filter by "photo"
        view._filter_items("photo")
        self.assertEqual(view.table.rowCount(), 1)
        self.assertEqual(view.displayed_items[0].name, "photo1.jpg")

    def test_main_window_init_and_vault_flow(self) -> None:
        # Create a real test vault
        vault_path = self.root_path / "MyVault"
        vault = Vault.create_vault(
            vault_path,
            name="My Secret Vault",
            password="StrongPassword123!",
            initial_entry_points=["photos", "documents"],
        )

        self.config.known_vaults = [{"path": str(vault_path), "name": "My Secret Vault"}]
        self.config.last_selected_vault_path = None
        win = MainWindow(self.config, auto_unlock_last=False)

        # Open vault in unlocked state for test
        win.vault = vault
        win.sidebar.set_current_vault(vault)
        win._update_toolbar_state()
        win.refresh_current_view()

        self.assertTrue(win.vault.is_unlocked)
        # In Vault Root, table should have 2 entry points (photos and documents)
        self.assertEqual(win.file_view.table.rowCount(), 2)

        # Switch theme
        win._toggle_theme()
        self.assertFalse(win.dark_mode)
        win._toggle_theme()
        self.assertTrue(win.dark_mode)

        # Lock vault
        win.lock_vault()
        self.assertFalse(win.vault.is_unlocked)
        self.assertEqual(win.file_view.table.rowCount(), 0)

        win.close()


if __name__ == "__main__":
    unittest.main()
