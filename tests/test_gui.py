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

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QHeaderView, QLabel

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


    def test_recursive_search_in_gui_and_reveal_flow(self) -> None:
        """Verify search UI renders Location column, handles results, and reveal navigation."""
        view = FileExplorerView()
        self.assertEqual(view.table.columnCount(), 5)  # Normal 5 columns

        # 1. Provide search results from multiple entry points
        items = [
            ArchiveItem(name="vacation.png", path="family/vacation.png", entry_point_name="photos", category=FileCategory.IMAGE),
            ArchiveItem(name="budget.xlsx", path="work/2026/budget.xlsx", entry_point_name="documents", category=FileCategory.DOCUMENT),
        ]
        view.set_search_results(items, query="va", scope="vault")

        # In search mode, table should have 6 columns (with Location column at index 1)
        self.assertTrue(view.is_search_mode)
        self.assertEqual(view.table.columnCount(), 6)
        self.assertEqual(view.table.horizontalHeaderItem(1).text(), "Location")
        self.assertEqual(view.table.rowCount(), 2)

        # Check location display
        loc_row0 = view.table.item(0, 1).text()
        self.assertEqual(loc_row0, "photos.7z / family")

        loc_row1 = view.table.item(1, 1).text()
        self.assertEqual(loc_row1, "documents.7z / work/2026")

        # 2. Test reveal signal
        revealed_items = []
        view.reveal_requested.connect(lambda it: revealed_items.append(it))
        view.reveal_requested.emit(items[0])
        self.assertEqual(len(revealed_items), 1)
        self.assertEqual(revealed_items[0].name, "vacation.png")

        # 3. Clear search restores normal mode and 5 columns
        view.search_bar.clear()
        self.assertFalse(view.is_search_mode)
        self.assertEqual(view.table.columnCount(), 5)
        self.assertEqual(view.table.horizontalHeaderItem(1).text(), "Size")

    def test_horizontal_column_resizing(self) -> None:
        """Verify columns are in Interactive mode allowing horizontal drag resizing and custom widths."""
        view = FileExplorerView()
        header = view.table.horizontalHeader()

        # All columns in normal mode must be Interactive
        for col_idx in range(view.table.columnCount()):
            self.assertEqual(
                header.sectionResizeMode(col_idx),
                QHeaderView.ResizeMode.Interactive,
                f"Column {col_idx} should be Interactive for horizontal resizing",
            )

        # Test custom column width application
        view.set_custom_column_widths({"Name": 320, "Size": 110, "Type": 140})
        self.assertEqual(view.table.columnWidth(0), 320)
        self.assertEqual(view.table.columnWidth(1), 110)
        self.assertEqual(view.table.columnWidth(2), 140)

        # Check sectionResized event updates saved column widths and emits signal
        emitted_widths = []
        view.column_widths_changed.connect(lambda w: emitted_widths.append(w))
        view._on_header_section_resized(0, 320, 400)
        self.assertEqual(view._column_widths["Name"], 400)
        self.assertTrue(len(emitted_widths) > 0)
        self.assertEqual(emitted_widths[-1]["Name"], 400)

    def test_ten_predefined_file_list_sizes(self) -> None:
        """Verify 10 predefined sizes (5th/index 4 is default, <4 smaller, >4 bigger)."""
        view = FileExplorerView()
        self.assertEqual(len(view.LIST_SIZES), 10)
        self.assertEqual(view.DEFAULT_SIZE_INDEX, 4)
        self.assertEqual(view.current_size_index, 4)

        default_height = view.LIST_SIZES[4]["row_height"]
        self.assertEqual(default_height, 36)

        # Sizes backward (< 4) must be strictly smaller
        for i in range(4):
            self.assertLess(view.LIST_SIZES[i]["row_height"], default_height)

        # Sizes onward (> 4) must be strictly bigger
        for i in range(5, 10):
            self.assertGreater(view.LIST_SIZES[i]["row_height"], default_height)

        # Test applying size 0 (smallest)
        view.apply_list_size(0)
        self.assertEqual(view.current_size_index, 0)
        self.assertEqual(view.table.verticalHeader().defaultSectionSize(), 22)

        # Test applying size 9 (largest)
        view.apply_list_size(9)
        self.assertEqual(view.current_size_index, 9)
        self.assertEqual(view.table.verticalHeader().defaultSectionSize(), 74)

        # Test clamping out of bounds
        view.apply_list_size(-5)
        self.assertEqual(view.current_size_index, 0)
        view.apply_list_size(99)
        self.assertEqual(view.current_size_index, 9)

    def test_control_scroll_and_trackpad_zoom_gestures(self) -> None:
        """Verify Ctrl + mouse wheel and trackpad vertical motion adjust file list size."""
        view = FileExplorerView()
        view.apply_list_size(4)  # Start at default 5th size (index 4)

        # 1. Ctrl + Wheel scroll up -> zoom in (+1 size)
        wheel_up = QWheelEvent(
            QPointF(20, 20),
            QPointF(20, 20),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        view.table.wheelEvent(wheel_up)
        self.assertEqual(view.current_size_index, 5)

        # 2. Ctrl + Wheel scroll down -> zoom out (-1 size)
        wheel_down = QWheelEvent(
            QPointF(20, 20),
            QPointF(20, 20),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        view.table.wheelEvent(wheel_down)
        self.assertEqual(view.current_size_index, 4)

        # 3. Trackpad two-hand/finger vertical motion (accumulated delta > 60)
        for _ in range(3):
            tp_event = QWheelEvent(
                QPointF(20, 20),
                QPointF(20, 20),
                QPoint(0, 5),
                QPoint(0, 25),  # 3 * 25 = 75 > 60
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            view.table.wheelEvent(tp_event)
        self.assertEqual(view.current_size_index, 5)

    def test_sidebar_entry_points_label_and_persistence(self) -> None:
        """Verify sidebar section title is ENTRY POINTS (without (.7z)) and config persists zoom & widths."""
        cfg_file = self.root_path / "test_config.json"
        config = AppConfig(cfg_file)
        sidebar = VaultSidebar(config)

        # Check section labels
        labels = [lbl.text() for lbl in sidebar.findChildren(QLabel)]
        self.assertIn("ENTRY POINTS", labels)
        for text in labels:
            self.assertNotIn("(.7Z)", text)
            self.assertNotIn("(.7z)", text)

        # Check config persistence of file list size index and column widths
        config.file_list_size_index = 7
        config.file_column_widths = {"Name": 350, "Size": 120}
        config.save()

        # Reload from disk
        config_reloaded = AppConfig(cfg_file)
        self.assertEqual(config_reloaded.file_list_size_index, 7)
        self.assertEqual(config_reloaded.file_column_widths["Name"], 350)
        self.assertEqual(config_reloaded.file_column_widths["Size"], 120)

    def test_vault_root_context_menu_options(self) -> None:
        """Verify Vault Root context menu has no 'Move to Folder...', and shows 'New Entry Point...'."""
        from PyQt6.QtWidgets import QMenu
        view = FileExplorerView()
        # 1. At Vault Root with an Entry Point selected
        view.set_location_context("", "")
        ep_item = ArchiveItem(
            name="photos",
            path="photos",
            is_dir=True,
            category=FileCategory.ENTRY_POINT,
            entry_point_name="photos",
        )
        view.set_items([ep_item])
        view.table.selectRow(0)

        captured_actions = []
        def fake_exec(self_menu, *args, **kwargs):
            captured_actions.extend([a.text() for a in self_menu.actions() if a.text()])

        with patch.object(QMenu, "exec", fake_exec):
            view._show_context_menu(QPoint(5, 5))

        self.assertNotIn("Move to Folder...", captured_actions)
        self.assertNotIn("Add Files Here...", captured_actions)
        self.assertIn("Export / Save As...", captured_actions)
        self.assertIn("Open Entry Point", captured_actions)
        self.assertIn("New Entry Point...", captured_actions)

        # 2. Inside a subfolder
        view.set_location_context("photos", "family")
        sub_item = ArchiveItem(
            name="beach.png",
            path="family/beach.png",
            is_dir=False,
            category=FileCategory.IMAGE,
            entry_point_name="photos",
        )
        view.set_items([sub_item])
        view.table.selectRow(0)

        sub_actions = []
        def fake_exec_sub(self_menu, *args, **kwargs):
            sub_actions.extend([a.text() for a in self_menu.actions() if a.text()])

        with patch.object(QMenu, "exec", fake_exec_sub):
            view._show_context_menu(QPoint(5, 5))

        self.assertIn("Move to Folder...", sub_actions)
        self.assertIn("Add Files Here...", sub_actions)
        self.assertIn("New Folder...", sub_actions)

    def test_export_files_worker_with_entry_points(self) -> None:
        """Verify ExportFilesWorker correctly exports entire entry point to destination folder."""
        from arc_vault.gui.workers import ExportFilesWorker

        vault_dir = self.root_path / "WorkerExportVault"
        vault = Vault.create_vault(
            vault_dir,
            name="Worker Vault",
            password="TestPassword123!",
            initial_entry_points=["docs"],
        )
        sample = self.root_path / "hello.txt"
        sample.write_text("hello export worker", encoding="utf-8")
        vault.add_files("docs", [sample])

        dest_dir = self.root_path / "exported_worker_output"
        ep_item = ArchiveItem(
            name="docs",
            path="docs",
            is_dir=True,
            category=FileCategory.ENTRY_POINT,
            entry_point_name="docs",
        )

        worker = ExportFilesWorker(vault, [ep_item], dest_dir)
        worker.run()

        exported_file = dest_dir / "docs" / "hello.txt"
        self.assertTrue(exported_file.is_file())
        self.assertEqual(exported_file.read_text(encoding="utf-8"), "hello export worker")


    def test_create_vault_dialog_obfuscation_option(self) -> None:
        """Verify CreateVaultDialog has obfuscation checkbox defaulting to checked."""
        from arc_vault.gui.vault_dialog import CreateVaultDialog

        dlg = CreateVaultDialog(dark_mode=True)
        self.assertTrue(hasattr(dlg, "chk_obfuscate"))
        self.assertTrue(dlg.chk_obfuscate.isChecked())
        self.assertEqual(dlg.chk_obfuscate.text(), "Obfuscate folder & file names in arc-data")
        dlg.close()


    def test_about_dialog_and_special_thanks(self) -> None:
        """Verify AboutDialog contains contributors and special thanks credits for 7-Zip and libraries."""
        from arc_vault.gui.about_dialog import AboutDialog

        dlg = AboutDialog(dark_mode=True)
        # Verify credits in dialog
        all_labels = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        combined_text = " ".join(all_labels)

        self.assertIn("Kenan (@noobaly-original)", combined_text)
        self.assertIn("Antigravity (Google DeepMind)", combined_text)
        self.assertIn("7-Zip by Igor Pavlov", combined_text)
        self.assertIn("PyQt6", combined_text)
        self.assertIn("Pygments", combined_text)
        self.assertIn("Pillow", combined_text)
        self.assertIn("PyInstaller", combined_text)
        dlg.close()


    def test_create_vault_dialog_blocks_existing_vault_folder(self) -> None:
        """Verify CreateVaultDialog rejects creating a vault in an existing vault or its subfolders."""
        from PyQt6.QtWidgets import QMessageBox
        from arc_vault.gui.vault_dialog import CreateVaultDialog

        vault_dir = self.root_path / "gui_existing_vault"
        Vault.create_vault(
            vault_dir,
            name="Existing Vault",
            password="SecurePass123!",
            initial_entry_points=["docs"],
        )

        dlg = CreateVaultDialog(dark_mode=True)
        dlg.edit_name.setText("New Vault")
        dlg.edit_password.setText("ValidPassword123")
        dlg.edit_confirm.setText("ValidPassword123")

        # 1. Target is the existing vault
        dlg.edit_location.setText(str(vault_dir))
        with patch.object(QMessageBox, "warning") as mock_warn:
            dlg._on_create_clicked()
            mock_warn.assert_called_once()
            self.assertIn("already an existing vault", mock_warn.call_args[0][2])

        self.assertIsNone(dlg.created_vault_path)
        self.assertFalse(dlg.lbl_error.isHidden())
        self.assertIn("already an existing vault", dlg.lbl_error.text())

        # 2. Target is inside the existing vault
        dlg.edit_location.setText(str(vault_dir / "subfolder" / "inner"))
        with patch.object(QMessageBox, "warning") as mock_warn2:
            dlg._on_create_clicked()
            mock_warn2.assert_called_once()
            self.assertIn("inside an existing vault folder", mock_warn2.call_args[0][2])

        self.assertIsNone(dlg.created_vault_path)
        dlg.close()

    def test_rename_vault_display_name_in_gui(self) -> None:
        """Verify changing vault display name via GUI updates vault, config, and sidebar."""
        from PyQt6.QtWidgets import QInputDialog
        from arc_vault.gui.main_window import MainWindow

        vault_dir = self.root_path / "rename_gui_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Initial Vault Name",
            password="SecurePass123!",
            initial_entry_points=["docs"],
        )

        win = MainWindow(self.config)
        win.open_vault_by_path(vault_dir, prompt_unlock=False)
        self.assertEqual(win.vault.name, "Initial Vault Name")

        with patch.object(QInputDialog, "getText", return_value=("Renamed GUI Vault", True)):
            win._on_rename_vault_display_name(vault_dir)

        self.assertEqual(win.vault.name, "Renamed GUI Vault")

        # Check config known vaults
        matching = [v for v in win.config.known_vaults if str(Path(v["path"]).resolve()) == str(vault_dir.resolve())]
        self.assertTrue(len(matching) > 0)
        self.assertEqual(matching[0]["name"], "Renamed GUI Vault")

        # Check sidebar list display
        found_in_sidebar = False
        for i in range(win.sidebar.vault_list.count()):
            if "Renamed GUI Vault" in win.sidebar.vault_list.item(i).text():
                found_in_sidebar = True
                break
        self.assertTrue(found_in_sidebar)
        win.close()

    def test_check_imports_in_gui(self) -> None:
        """Verify 'Check Imports' toolbar action processes off-site files and prompts user."""
        from PyQt6.QtWidgets import QMessageBox
        from arc_vault.core.sevenzip import SevenZip
        from arc_vault.gui.main_window import MainWindow

        vault_dir = self.root_path / "gui_import_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="GUI Import Vault",
            password="ImportPass123!",
            initial_entry_points=["docs"],
        )

        win = MainWindow(self.config, auto_unlock_last=False)
        win.vault = vault
        win.sidebar.set_current_vault(vault)
        win._update_toolbar_state()
        self.assertTrue(win.act_check_imports.isEnabled())

        # 1. No pending archives -> shows information prompt
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Cancel) as mock_info:
            win._on_check_imports_action()
            mock_info.assert_called_once()
            self.assertIn("No pending encrypted .7z", mock_info.call_args[0][2])

        # 2. Stage a 7z archive in import_dir
        sz = SevenZip()
        sample = self.root_path / "offsite_doc.txt"
        sample.write_text("content from offsite device", encoding="utf-8")
        archive_7z = vault.import_dir / "offsite.7z"
        sz.add_files(archive_7z, [sample], "ImportPass123!")
        self.assertTrue(archive_7z.exists())

        # 3. Trigger check imports -> successfully imports and informs user
        with patch.object(QMessageBox, "information") as mock_info_success:
            win._on_check_imports_action()
            mock_info_success.assert_called_once()
            self.assertIn("Successfully imported 1 archive(s)", mock_info_success.call_args[0][2])

        self.assertFalse(archive_7z.exists())
        self.assertIn("imports", win.vault.entry_points)
        self.assertIn("Imported 1 off-site archive(s)", win.status_bar.currentMessage())
        win.close()

if __name__ == "__main__":
    unittest.main()
