"""Unit tests for ArcVault core logic, 7z encryption, and vault management."""

import shutil
import tempfile
import unittest
from pathlib import Path

from arc_vault.core.models import FileCategory, classify_file
from arc_vault.core.sevenzip import SevenZip, SevenZipExecutableNotFoundError, SevenZipOperationError
from arc_vault.core.vault import Vault, VaultUnlockError


class TestArcVaultBackend(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="arcvault_test_")
        self.root_path = Path(self.tmp_dir)
        self.sz = SevenZip()
        self.password = "MySecureTestPass123!"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_classify_file(self) -> None:
        self.assertEqual(classify_file("folder", is_dir=True), FileCategory.FOLDER)
        self.assertEqual(classify_file("setup.exe"), FileCategory.EXECUTABLE_WINDOWS)
        self.assertEqual(classify_file("script.bat"), FileCategory.EXECUTABLE_WINDOWS)
        self.assertEqual(classify_file("MyApp.app"), FileCategory.EXECUTABLE_MACOS)
        self.assertEqual(classify_file("installer.dmg"), FileCategory.EXECUTABLE_MACOS)
        self.assertEqual(classify_file("run.sh"), FileCategory.EXECUTABLE_UNIX)
        self.assertEqual(classify_file("photo.PNG"), FileCategory.IMAGE)
        self.assertEqual(classify_file("main.py"), FileCategory.CODE)
        self.assertEqual(classify_file("notes.txt"), FileCategory.TEXT)
        self.assertEqual(classify_file("doc.pdf"), FileCategory.DOCUMENT)
        self.assertEqual(classify_file("music.mp3"), FileCategory.AUDIO)
        self.assertEqual(classify_file("clip.mp4"), FileCategory.VIDEO)
        self.assertEqual(classify_file("key.pem"), FileCategory.KEY_CERT)

    def test_sevenzip_binary_found(self) -> None:
        binary = self.sz.binary
        self.assertTrue(Path(binary).is_file())

    def test_vault_create_unlock_lock(self) -> None:
        vault = Vault.create_vault(
            self.root_path,
            name="Test Vault",
            password=self.password,
            initial_entry_points=["photos", "documents"],
            sevenzip=self.sz,
        )

        self.assertTrue(vault.is_unlocked)
        self.assertEqual(vault.metadata.name, "Test Vault")
        self.assertIn("photos", vault.entry_points)
        self.assertIn("documents", vault.entry_points)

        vault.lock()
        self.assertFalse(vault.is_unlocked)
        with self.assertRaises(VaultUnlockError):
            _ = vault.password

        vault2 = Vault(self.root_path, self.sz)
        self.assertFalse(vault2.is_unlocked)

        self.assertFalse(vault2.unlock("WrongPassword"))
        self.assertFalse(vault2.is_unlocked)

        self.assertTrue(vault2.unlock(self.password))
        self.assertTrue(vault2.is_unlocked)
        self.assertIn("photos", vault2.entry_points)

    def test_vault_entry_point_file_operations(self) -> None:
        vault = Vault.create_vault(
            self.root_path,
            name="Test Vault",
            password=self.password,
            initial_entry_points=["photos"],
            sevenzip=self.sz,
        )

        sample1 = self.root_path / "sample1.txt"
        sample1.write_text("Hello ArcVault Text!", encoding="utf-8")

        sample_img = self.root_path / "picture.png"
        sample_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")

        ok = vault.add_files("photos", [sample1, sample_img])
        self.assertTrue(ok)

        items = vault.get_items_in_directory("photos", "")
        names = [item.name for item in items]
        self.assertIn("sample1.txt", names)
        self.assertIn("picture.png", names)

        ok = vault.create_subfolder("photos", "", "family")
        self.assertTrue(ok)

        sample_fam = self.root_path / "family1.png"
        sample_fam.write_bytes(b"\x89PNG family image data")
        ok = vault.add_files("photos", [sample_fam], subfolder="family")
        self.assertTrue(ok)

        fam_items = vault.get_items_in_directory("photos", "family")
        fam_names = [f.name for f in fam_items]
        self.assertIn("family1.png", fam_names)

        preview_path = vault.extract_file_for_preview("photos", "sample1.txt")
        self.assertIsNotNone(preview_path)
        self.assertTrue(preview_path.exists())
        self.assertEqual(preview_path.read_text(encoding="utf-8"), "Hello ArcVault Text!")

        export_dest = self.root_path / "exported"
        ok_exp = vault.export_items("photos", ["sample1.txt"], export_dest)
        self.assertTrue(ok_exp)
        self.assertTrue((export_dest / "sample1.txt").exists())

        ok_rn = vault.rename_item("photos", "sample1.txt", "renamed_sample.txt")
        self.assertTrue(ok_rn)
        items_renamed = vault.get_items_in_directory("photos", "")
        renamed_names = [i.name for i in items_renamed]
        self.assertIn("renamed_sample.txt", renamed_names)
        self.assertNotIn("sample1.txt", renamed_names)

        ok = vault.delete_item("photos", "renamed_sample.txt")
        self.assertTrue(ok)
        items_after_del = vault.get_items_in_directory("photos", "")
        self.assertNotIn("renamed_sample.txt", [i.name for i in items_after_del])

    def test_fast_archive_editing_in_app_and_disk(self) -> None:
        vault = Vault.create_vault(
            self.root_path,
            name="Edit Vault",
            password=self.password,
            initial_entry_points=["docs"],
            sevenzip=self.sz,
        )

        note_file = self.root_path / "note.txt"
        note_file.write_text("Original Note v1", encoding="utf-8")
        self.assertTrue(vault.add_files("docs", [note_file]))

        # Test updating file content directly via string
        ok_update = vault.update_file_content("docs", "note.txt", "Updated Note v2 (Fast Edit)")
        self.assertTrue(ok_update)

        # Verify extracted content matches updated text
        preview = vault.extract_file_for_preview("docs", "note.txt")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.read_text(encoding="utf-8"), "Updated Note v2 (Fast Edit)")

        # Test updating a file nested in a subfolder from disk
        self.assertTrue(vault.create_subfolder("docs", "", "sub"))
        nested_file = self.root_path / "config.json"
        nested_file.write_text('{"key": "initial"}', encoding="utf-8")
        self.assertTrue(vault.add_files("docs", [nested_file], subfolder="sub"))

        # Update from disk
        updated_disk_file = self.root_path / "config_new.json"
        updated_disk_file.write_text('{"key": "updated_from_disk"}', encoding="utf-8")
        ok_disk_up = vault.update_file_from_disk("docs", "sub/config.json", updated_disk_file)
        self.assertTrue(ok_disk_up)

        # Verify
        preview_nested = vault.extract_file_for_preview("docs", "sub/config.json")
        self.assertIsNotNone(preview_nested)
        self.assertEqual(preview_nested.read_text(encoding="utf-8"), '{"key": "updated_from_disk"}')

        # Test staging extraction for external editing
        staged = vault.extract_file_for_editing("docs", "sub/config.json")
        self.assertIsNotNone(staged)
        self.assertTrue(staged.exists())
        self.assertEqual(staged.read_text(encoding="utf-8"), '{"key": "updated_from_disk"}')

    def test_entry_point_crud(self) -> None:
        vault = Vault.create_vault(
            self.root_path,
            name="CRUD Vault",
            password=self.password,
        )
        self.assertEqual(len(vault.entry_points), 0)

        ep = vault.create_entry_point("work")
        self.assertEqual(ep.name, "work")
        self.assertIn("work", vault.entry_points)
        self.assertTrue(ep.archive_file.exists())

        ok = vault.rename_entry_point("work", "work_archive")
        self.assertTrue(ok)
        self.assertIn("work_archive", vault.entry_points)
        self.assertNotIn("work", vault.entry_points)

        ok = vault.delete_entry_point("work_archive")
        self.assertTrue(ok)
        self.assertNotIn("work_archive", vault.entry_points)

    def test_subfolders_and_move_operations(self) -> None:
        vault = Vault.create_vault(
            self.root_path,
            name="Folder Vault",
            password=self.password,
            initial_entry_points=["data"],
            sevenzip=self.sz,
        )

        # 1. Create subfolder inside archive
        self.assertTrue(vault.create_subfolder("data", "", "documents"))
        root_items = vault.get_items_in_directory("data", "")
        doc_item = next(i for i in root_items if i.name == "documents")
        self.assertTrue(doc_item.is_dir)
        self.assertEqual(doc_item.category, FileCategory.FOLDER)

        # 2. Add local directory with files into vault root
        local_dir = self.root_path / "imported_folder"
        local_dir.mkdir()
        (local_dir / "sample.txt").write_text("sample content", encoding="utf-8")
        nested_sub = local_dir / "nested"
        nested_sub.mkdir()
        (nested_sub / "inner.txt").write_text("inner content", encoding="utf-8")

        self.assertTrue(vault.add_files("data", [local_dir]))
        root_items2 = vault.get_items_in_directory("data", "")
        imported_item = next(i for i in root_items2 if i.name == "imported_folder")
        self.assertTrue(imported_item.is_dir)
        self.assertEqual(imported_item.category, FileCategory.FOLDER)

        # Verify contents of imported folder
        folder_items = vault.get_items_in_directory("data", "imported_folder")
        folder_names = [i.name for i in folder_items]
        self.assertIn("sample.txt", folder_names)
        self.assertIn("nested", folder_names)
        nested_item = next(i for i in folder_items if i.name == "nested")
        self.assertTrue(nested_item.is_dir)
        self.assertEqual(nested_item.category, FileCategory.FOLDER)

        # 3. Add standalone file to root and move it into documents folder
        root_file = self.root_path / "movable.txt"
        root_file.write_text("to be moved", encoding="utf-8")
        self.assertTrue(vault.add_files("data", [root_file]))

        self.assertTrue(vault.move_items("data", ["movable.txt"], "documents"))
        root_after_move = [i.name for i in vault.get_items_in_directory("data", "")]
        self.assertNotIn("movable.txt", root_after_move)

        docs_after_move = [i.name for i in vault.get_items_in_directory("data", "documents")]
        self.assertIn("movable.txt", docs_after_move)

        # 4. Move imported_folder into documents
        self.assertTrue(vault.move_items("data", ["imported_folder"], "documents"))
        docs_items = [i.name for i in vault.get_items_in_directory("data", "documents")]
        self.assertIn("imported_folder", docs_items)

        # Verify nested file inside moved folder is intact
        preview = vault.extract_file_for_preview("data", "documents/imported_folder/nested/inner.txt")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.read_text(encoding="utf-8"), "inner content")


if __name__ == "__main__":
    unittest.main()
