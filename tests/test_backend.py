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

    def test_v2_chunking_shredding_and_reassembly(self) -> None:
        """Verify V2 chunk shredding (>1GB logic tested with 5KB test chunks) and projection."""
        vault = Vault.create_vault(
            self.root_path,
            name="Chunk Vault",
            password=self.password,
            initial_entry_points=["storage"],
            sevenzip=self.sz,
            chunk_size=5000,  # 5KB chunk size for testing shredding without consuming gigabytes
        )

        # 1. Create a 12 KB file that will be shredded into 3 chunks
        payload = b"PART_1_CONTENT_" * 350 + b"PART_2_CONTENT_" * 350 + b"PART_3_FINAL"
        total_len = len(payload)
        test_file = self.root_path / "big_video.mp4"
        test_file.write_bytes(payload)

        # 2. Add to entry point
        self.assertTrue(vault.add_files("storage", [test_file]))

        # 3. Check arc-data directory structure
        meta = vault._v2_metadata["storage"]
        ep_dir = vault.arc_data_dir / meta.ep_dir_id
        self.assertTrue(ep_dir.exists())

        item_meta = meta.items["big_video.mp4"]
        self.assertEqual(item_meta.size, total_len)
        self.assertGreaterEqual(len(item_meta.chunks), 3)

        item_dir = ep_dir / item_meta.item_id
        self.assertTrue(item_dir.exists())
        self.assertTrue((item_dir / "chunk_000.7z").exists())
        self.assertTrue((item_dir / "chunk_001.7z").exists())

        # 4. Check projection in directory: single file with total size, metadata.json excluded
        items = vault.get_items_in_directory("storage", "")
        item_names = [i.name for i in items]
        self.assertIn("big_video.mp4", item_names)
        self.assertNotIn("metadata.json", item_names)  # Metadata must never be rendered!
        self.assertNotIn(".arcvault_init", item_names)

        proj_item = next(i for i in items if i.name == "big_video.mp4")
        self.assertEqual(proj_item.size, total_len)
        self.assertFalse(proj_item.is_dir)

        # 5. Export and verify complete byte-for-byte reassembly
        export_dir = self.root_path / "reconstructed"
        self.assertTrue(vault.export_items("storage", ["big_video.mp4"], export_dir))
        reconstructed_file = export_dir / "big_video.mp4"
        self.assertTrue(reconstructed_file.exists())
        self.assertEqual(reconstructed_file.read_bytes(), payload)

        # 6. Test safeguard for files over 1GB
        proj_item.size = 1024 * 1024 * 1024 + 100  # Fake > 1GB
        meta.items["big_video.mp4"].size = 1024 * 1024 * 1024 + 100
        preview_large = vault.extract_file_for_preview("storage", "big_video.mp4")
        self.assertIsNone(preview_large)  # Must be blocked!


    def test_atomic_metadata_save_and_backup_recovery(self) -> None:
        """Verify save_metadata uses atomic swap, generates .bak, and recovers from corruption."""
        vault = Vault.create_vault(
            self.root_path,
            name="Atomic Vault",
            password=self.password,
            initial_entry_points=["secure"],
            sevenzip=self.sz,
        )

        # Add first file
        test_file = self.root_path / "hello.txt"
        test_file.write_text("hello atomic world", encoding="utf-8")
        vault.add_files("secure", [test_file])

        # Add second file so .bak contains version with hello.txt
        test_file2 = self.root_path / "world.txt"
        test_file2.write_text("world", encoding="utf-8")
        vault.add_files("secure", [test_file2])

        ep_archive = self.root_path / "secure.7z"
        bak_file = self.root_path / ".secure.bak"

        # Check that .secure.bak exists after saving updates
        self.assertTrue(ep_archive.exists())
        self.assertTrue(bak_file.exists())

        # Test recovery: corrupt the live archive by zeroing it
        ep_archive.write_bytes(b"")

        # Load metadata should transparently fallback to .secure.bak
        recovered_meta = vault.v2_engine.load_metadata(ep_archive, self.password)
        self.assertIsNotNone(recovered_meta)
        self.assertIn("hello.txt", recovered_meta.items)


if __name__ == "__main__":
    unittest.main()
