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
        # Create vault with initial entry points "photos" and "documents"
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

        # Lock the vault
        vault.lock()
        self.assertFalse(vault.is_unlocked)
        with self.assertRaises(VaultUnlockError):
            _ = vault.password

        # Re-open vault from disk
        vault2 = Vault(self.root_path, self.sz)
        self.assertFalse(vault2.is_unlocked)

        # Attempt unlock with wrong password
        self.assertFalse(vault2.unlock("WrongPassword"))
        self.assertFalse(vault2.is_unlocked)

        # Unlock with correct password
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

        # Create sample local files
        sample1 = self.root_path / "sample1.txt"
        sample1.write_text("Hello ArcVault Text!", encoding="utf-8")

        sample_img = self.root_path / "picture.png"
        sample_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")

        # Add files to "photos" entry point at root
        ok = vault.add_files("photos", [sample1, sample_img])
        self.assertTrue(ok)

        # List items in "photos"
        items = vault.get_items_in_directory("photos", "")
        names = [item.name for item in items]
        self.assertIn("sample1.txt", names)
        self.assertIn("picture.png", names)

        # Create subfolder "family" inside "photos"
        ok = vault.create_subfolder("photos", "", "family")
        self.assertTrue(ok)

        # Add file inside subfolder "family"
        sample_fam = self.root_path / "family1.png"
        sample_fam.write_bytes(b"\x89PNG family image data")
        ok = vault.add_files("photos", [sample_fam], subfolder="family")
        self.assertTrue(ok)

        # Check items in "family"
        fam_items = vault.get_items_in_directory("photos", "family")
        fam_names = [f.name for f in fam_items]
        self.assertIn("family1.png", fam_names)

        # Test preview extraction
        preview_path = vault.extract_file_for_preview("photos", "sample1.txt")
        self.assertIsNotNone(preview_path)
        self.assertTrue(preview_path.exists())
        self.assertEqual(preview_path.read_text(encoding="utf-8"), "Hello ArcVault Text!")

        # Test export items
        export_dest = self.root_path / "exported"
        ok_exp = vault.export_items("photos", ["sample1.txt"], export_dest)
        self.assertTrue(ok_exp)
        self.assertTrue((export_dest / "sample1.txt").exists())

        # Test rename item inside archive
        ok_rn = vault.rename_item("photos", "sample1.txt", "renamed_sample.txt")
        self.assertTrue(ok_rn)
        items_renamed = vault.get_items_in_directory("photos", "")
        renamed_names = [i.name for i in items_renamed]
        self.assertIn("renamed_sample.txt", renamed_names)
        self.assertNotIn("sample1.txt", renamed_names)

        # Delete item
        ok = vault.delete_item("photos", "renamed_sample.txt")
        self.assertTrue(ok)
        items_after_del = vault.get_items_in_directory("photos", "")
        self.assertNotIn("renamed_sample.txt", [i.name for i in items_after_del])

    def test_entry_point_crud(self) -> None:
        vault = Vault.create_vault(
            self.root_path,
            name="CRUD Vault",
            password=self.password,
        )
        self.assertEqual(len(vault.entry_points), 0)

        # Create entry point
        ep = vault.create_entry_point("work")
        self.assertEqual(ep.name, "work")
        self.assertIn("work", vault.entry_points)
        self.assertTrue(ep.archive_file.exists())

        # Rename entry point
        ok = vault.rename_entry_point("work", "work_archive")
        self.assertTrue(ok)
        self.assertIn("work_archive", vault.entry_points)
        self.assertNotIn("work", vault.entry_points)

        # Delete entry point
        ok = vault.delete_entry_point("work_archive")
        self.assertTrue(ok)
        self.assertNotIn("work_archive", vault.entry_points)


if __name__ == "__main__":
    unittest.main()
