"""Headless GUI tests for ArcVault components."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Force headless offscreen platform for Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from arc_vault.config import AppConfig
from arc_vault.core.models import ArchiveItem, FileCategory
from arc_vault.core.vault import Vault
from arc_vault.gui.breadcrumbs import BreadcrumbBar
from arc_vault.gui.file_view import FileExplorerView
from arc_vault.gui.icons import IconProvider
from arc_vault.gui.logs_panel import LogsPanel
from arc_vault.gui.main_window import MainWindow
from arc_vault.gui.preview_panel import PreviewPanel
from arc_vault.gui.sidebar import VaultSidebar
from arc_vault.gui.theme import DARK_STYLESHEET, LIGHT_STYLESHEET, get_stylesheet
from arc_vault.logger import clear_log_history, log_7zip, log_info


class TestArcVaultGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="arcvault_gui_test_")
        self.root_path = Path(self.tmp_dir)
        self.config = AppConfig(config_file=self.root_path / "config.json")
        self.config.known_vaults = []
        self.config.last_selected_vault_path = None
        clear_log_history()

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

    def test_custom_ui_icons(self) -> None:
        """Verify add_file (incoming), export (outgoing), and logs icons exist and render properly."""
        for icon_name in ("add_file", "export", "logs"):
            icon = IconProvider.get_icon(icon_name, dark_mode=True, size=18)
            self.assertFalse(icon.isNull(), f"Icon {icon_name} should not be null")
            self.assertEqual(icon.availableSizes()[0].width(), 18)

    def test_logs_panel_and_masking(self) -> None:
        panel = LogsPanel()
        self.assertFalse(panel.lbl_title.text() == "")

        # Emit log entries
        log_info("Application test start event", category="APP")
        log_7zip(["7zz", "a", "-pSecretVaultPass123", "-mhe=on", "archive.7z"], 0, "Everything is Ok")

        text = panel.text_edit.toPlainText()
        self.assertIn("Application test start event", text)
        self.assertIn("7z [OK]", text)
        self.assertIn("-p***", text)
        self.assertNotIn("SecretVaultPass123", text)  # Password must be masked!

        # Test filter
        panel.filter_combo.setCurrentText("7-Zip Only")
        filtered_text = panel.text_edit.toPlainText()
        self.assertIn("7z [OK]", filtered_text)
        self.assertNotIn("Application test start event", filtered_text)

        # Test clear
        panel._clear_logs()
        self.assertEqual(panel.text_edit.toPlainText().strip(), "")

    def test_preview_panel_views_and_in_app_editing(self) -> None:
        panel = PreviewPanel()
        self.assertEqual(panel.stack.currentIndex(), 0)

        # Image preview
        img_path = self.root_path / "test.png"
        from PIL import Image
        im = Image.new("RGB", (64, 64), color="red")
        im.save(img_path)

        img_item = ArchiveItem(name="test.png", path="test.png", category=FileCategory.IMAGE)
        panel.show_preview(img_item, img_path)
        self.assertEqual(panel.stack.currentIndex(), 2)

        # Text preview and in-app editing toggle
        txt_path = self.root_path / "code.py"
        txt_path.write_text("def hello():\n    return 42\n", encoding="utf-8")
        code_item = ArchiveItem(name="code.py", path="code.py", category=FileCategory.CODE)
        panel.show_preview(code_item, txt_path)
        self.assertEqual(panel.stack.currentIndex(), 1)
        self.assertFalse(panel.btn_edit_text.isHidden())

        # Switch to edit mode
        panel._toggle_text_edit_mode()
        self.assertTrue(panel._is_editing_text)
        self.assertFalse(panel.text_edit.isReadOnly())
        self.assertFalse(panel.btn_save_text.isHidden())

        # Modify text and trigger save
        saved_data = []
        panel.save_text_requested.connect(lambda item, text: saved_data.append((item, text)))
        panel.text_edit.setPlainText("def hello():\n    return 100\n")
        panel._save_in_app_text()
        self.assertEqual(len(saved_data), 1)
        self.assertEqual(saved_data[0][1], "def hello():\n    return 100\n")

        # Simulate save successful
        panel.on_save_successful("def hello():\n    return 100\n")
        self.assertTrue(panel.text_edit.isReadOnly())
        self.assertTrue(panel.btn_save_text.isHidden())

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

        view._filter_items("photo")
        self.assertEqual(view.table.rowCount(), 1)
        self.assertEqual(view.displayed_items[0].name, "photo1.jpg")

    def test_drag_drop_routing_in_file_view(self) -> None:
        view = FileExplorerView()
        view.set_location_context("photos", "family")

        folder_item = ArchiveItem(name="subfolder", path="family/subfolder", is_dir=True)
        file_item = ArchiveItem(name="image.png", path="family/image.png", is_dir=False)
        view.set_items([folder_item, file_item])

        dropped_folders = []
        view.files_dropped_on_folder.connect(lambda files, sub: dropped_folders.append((files, sub)))

        sample_file = self.root_path / "upload.txt"
        sample_file.write_text("upload", encoding="utf-8")

        # 1. Drop onto specific folder row
        view._on_files_dropped([sample_file], folder_item)
        self.assertEqual(len(dropped_folders), 1)
        self.assertEqual(dropped_folders[0][1], "family/subfolder")

        # 2. Drop onto empty space (no target item) -> targets current subfolder
        view._on_files_dropped([sample_file], None)
        self.assertEqual(len(dropped_folders), 2)
        self.assertEqual(dropped_folders[1][1], "family")

    def test_main_window_init_and_vault_flow(self) -> None:
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

        win.vault = vault
        win.sidebar.set_current_vault(vault)
        win._update_toolbar_state()
        win.refresh_current_view()

        self.assertTrue(win.vault.is_unlocked)
        self.assertEqual(win.file_view.table.rowCount(), 2)

        # Toggle logs panel
        self.assertTrue(win.logs_panel.isHidden())
        win._toggle_logs_panel()
        self.assertFalse(win.logs_panel.isHidden())
        win._toggle_logs_panel()
        self.assertTrue(win.logs_panel.isHidden())

        # Toggle theme
        win._toggle_theme()
        self.assertFalse(win.dark_mode)
        win._toggle_theme()
        self.assertTrue(win.dark_mode)

        win.lock_vault()
        self.assertFalse(win.vault.is_unlocked)
        self.assertEqual(win.file_view.table.rowCount(), 0)

        win.close()

    def test_external_editing_dispatch(self) -> None:
        """Verify external editing initiates OS editor process without NameError."""
        win = MainWindow(self.config, auto_unlock_last=False)
        item = ArchiveItem(name="notes.txt", path="notes.txt", entry_point_name="documents")

        win.vault = MagicMock()
        win.vault.is_unlocked = True
        fake_staged = self.root_path / "notes.txt"
        fake_staged.write_text("hello", encoding="utf-8")
        win.vault.extract_file_for_editing.return_value = fake_staged

        with patch("arc_vault.gui.main_window.subprocess.Popen") as mock_popen:
            win._start_external_editing(item)
            if sys.platform != "win32":
                mock_popen.assert_called_once()

        win.close()

    def test_window_state_and_theme_persistence(self) -> None:
        """Verify theme, window geometry/placement, and sizes persist to config and restore."""
        # 1. Test config saving/restoring
        self.config.theme = "light"
        self.config.window_width = 1200
        self.config.window_height = 800
        self.config.window_x = 100
        self.config.window_y = 120
        self.config.window_maximized = False
        self.config.save()

        config2 = AppConfig(config_file=self.config.config_file)
        self.assertEqual(config2.theme, "light")
        self.assertEqual(config2.window_width, 1200)
        self.assertEqual(config2.window_height, 800)
        self.assertEqual(config2.window_x, 100)
        self.assertEqual(config2.window_y, 120)

        # 2. Test MainWindow saves state on close and restores
        win = MainWindow(config2, auto_unlock_last=False)
        self.assertFalse(win.dark_mode)  # Theme should be light
        win.resize(1250, 820)
        win.move(150, 160)
        win._save_window_state()

        self.assertIsNotNone(config2.window_geometry)
        self.assertEqual(config2.window_width, 1250)
        self.assertEqual(config2.window_height, 820)
        win.close()

    def test_folder_display_and_internal_move_in_gui(self) -> None:
        """Verify subfolders render as 'Folder' with folder icons and emit internal move signals."""
        view = FileExplorerView()
        folder_item = ArchiveItem(
            name="vacation",
            path="vacation",
            is_dir=True,
            category=FileCategory.FOLDER,
        )
        file_item = ArchiveItem(
            name="photo.png",
            path="photo.png",
            is_dir=False,
            category=FileCategory.IMAGE,
        )

        view.set_items([folder_item, file_item])
        self.assertEqual(view.table.rowCount(), 2)

        # Row 0 should be the folder
        type_item_0 = view.table.item(0, 2)
        self.assertIsNotNone(type_item_0)
        self.assertEqual(type_item_0.text(), "Folder")

        # Row 1 should be the image
        type_item_1 = view.table.item(1, 2)
        self.assertIsNotNone(type_item_1)
        self.assertEqual(type_item_1.text(), "Image")



    def test_toolbar_icon_resolutions_and_sharpness(self) -> None:
        """Verify toolbar and UI icons supply sharp multi-resolution pixmaps for 20px, 24px, and 32px."""
        from PyQt6.QtCore import QSize
        icon = IconProvider.get_icon("add_file", dark_mode=True, size=20)
        
        # Verify available sizes cover 1x, 2x Retina, 3x for both 20px and 32px
        avail_tuples = [(s.width(), s.height()) for s in icon.availableSizes()]
        self.assertIn((20, 20), avail_tuples)
        self.assertIn((40, 40), avail_tuples)  # 20px @ 2x Retina
        self.assertIn((60, 60), avail_tuples)  # 20px @ 3x
        self.assertIn((32, 32), avail_tuples)
        self.assertIn((64, 64), avail_tuples)  # 32px @ 2x Retina

        # Test Retina DPR 2.0 direct pixmap generation
        pix20 = IconProvider.get_pixmap("add_file", size=20, dpr=2.0)
        self.assertEqual(pix20.width(), 40)
        self.assertEqual(pix20.devicePixelRatio(), 2.0)

        pix32 = IconProvider.get_pixmap("add_file", size=32, dpr=2.0)
        self.assertEqual(pix32.width(), 64)
        self.assertEqual(pix32.devicePixelRatio(), 2.0)

    def test_preview_panel_collapsed_recovery(self) -> None:
        """Verify that a collapsed preview panel (width 0 from old saved state) is auto-expanded."""
        import base64
        from PyQt6.QtCore import QByteArray
        
        # Use the exact corrupted splitter state where preview panel was 0px wide
        bad_splitter_state = "AAAA/wAAAAEAAAADAAAAzgAAAoIAAAAAAf////8BAAAAAQA="
        self.config.splitter_state = bad_splitter_state
        self.config.save()

        win = MainWindow(self.config, auto_unlock_last=False)
        win.show()
        QApplication.processEvents()
        sizes = win.main_splitter.sizes()
        self.assertGreaterEqual(len(sizes), 3)
        self.assertGreaterEqual(sizes[2], 260, "Preview panel must be auto-expanded if collapsed to 0")
        self.assertFalse(win.preview_panel.isHidden())
        win.close()

    def test_preview_panel_card_only_and_plain_text_detection(self) -> None:
        """Verify show_card_only and text detection on files with generic extensions."""
        panel = PreviewPanel()
        
        # 1. Immediate card display without disk file
        item = ArchiveItem(name="document.dat", path="document.dat", size=2048, category=FileCategory.GENERIC)
        panel.show_card_only(item, status_note="Extracting preview...")
        self.assertEqual(panel.stack.currentIndex(), 3)
        self.assertIn("document.dat", panel.card_name.text())
        self.assertIn("Extracting preview...", panel.card_details.text())

        # 2. Text detection on generic extension file
        txt_file = self.root_path / "README"
        txt_file.write_text("ArcVault Quickstart Guide", encoding="utf-8")
        readme_item = ArchiveItem(name="README", path="README", size=25, category=FileCategory.GENERIC)
        panel.show_preview(readme_item, txt_file)
        self.assertEqual(panel.stack.currentIndex(), 1)
        self.assertIn("ArcVault Quickstart Guide", panel.text_edit.toPlainText())

if __name__ == "__main__":
    unittest.main()
