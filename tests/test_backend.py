"""Unit tests for Vaultables core logic, 7z encryption, and vault management."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from vaultables.core.models import FileCategory, classify_file
from vaultables.core.sevenzip import SevenZip, SevenZipExecutableNotFoundError, SevenZipOperationError
from vaultables.core.vault import Vault, VaultUnlockError


class TestVaultablesBackend(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="vaultables_test_")
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
        sample1.write_text("Hello Vaultables Text!", encoding="utf-8")

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
        self.assertEqual(preview_path.read_text(encoding="utf-8"), "Hello Vaultables Text!")

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

        # 3. Check vaultables-data directory structure
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
        self.assertNotIn(".vaultables_init", item_names)

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


    def test_unique_random_folder_generation_collision_avoidance(self) -> None:
        """Verify generate_unique_folder_id skips existing folders and regenerates unique names."""
        from vaultables.core.storage_v2 import generate_unique_folder_id

        test_dir = self.root_path / "collision_test"
        test_dir.mkdir()

        # Pre-create several subdirectories
        (test_dir / "colliding1").mkdir()
        (test_dir / "colliding2").mkdir()

        # Test with existing_ids set
        uid = generate_unique_folder_id(test_dir, length=8, existing_ids={"colliding1", "colliding2"})
        self.assertNotIn(uid, {"colliding1", "colliding2"})
        self.assertFalse((test_dir / uid).exists())

        # Create that folder and generate another
        (test_dir / uid).mkdir()
        uid2 = generate_unique_folder_id(test_dir, length=8)
        self.assertNotEqual(uid, uid2)
        self.assertFalse((test_dir / uid2).exists())



    def test_recursive_search_across_multiple_entry_points(self) -> None:
        """Verify recursive search across all entry points, subfolders, and wildcard matching."""
        vault_dir = self.root_path / "search_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Search Vault",
            password=self.password,
            initial_entry_points=["photos", "documents"],
            sevenzip=self.sz,
        )

        # 1. Add nested files to photos
        f1 = self.root_path / "beach_vacation.png"
        f1.write_bytes(b"beach image")
        vault.add_files("photos", [f1], subfolder="family/summer")

        # 2. Add files to documents
        f2 = self.root_path / "annual_finance.xlsx"
        f2.write_bytes(b"spreadsheets")
        vault.add_files("documents", [f2], subfolder="work/2026")

        f3 = self.root_path / "quick_notes.txt"
        f3.write_bytes(b"notes text")
        vault.add_files("documents", [f3], subfolder="")

        # Query A: Search entire vault for "vacation"
        results_vacation = vault.search_items("vacation")
        self.assertEqual(len(results_vacation), 1)
        self.assertEqual(results_vacation[0].name, "beach_vacation.png")
        self.assertEqual(results_vacation[0].entry_point_name, "photos")
        self.assertEqual(results_vacation[0].path, "family/summer/beach_vacation.png")

        # Query B: Wildcard search across all entry points for "*.png"
        results_png = vault.search_items("*.png")
        self.assertEqual(len(results_png), 1)
        self.assertEqual(results_png[0].name, "beach_vacation.png")

        # Query C: Wildcard search for "*.xlsx"
        results_xlsx = vault.search_items("*.xlsx")
        self.assertEqual(len(results_xlsx), 1)
        self.assertEqual(results_xlsx[0].name, "annual_finance.xlsx")
        self.assertEqual(results_xlsx[0].entry_point_name, "documents")

        # Query D: Scoped recursive search inside "documents"
        results_docs = vault.search_items("finance", entry_point_name="documents")
        self.assertEqual(len(results_docs), 1)
        self.assertEqual(results_docs[0].name, "annual_finance.xlsx")

        # Query E: Scoped search inside "photos" should NOT find "finance"
        results_photos = vault.search_items("finance", entry_point_name="photos")
        self.assertEqual(len(results_photos), 0)

        # Query F: Subfolder recursive vs non-recursive
        # Inside "work", recursive should find work/2026/annual_finance.xlsx
        res_rec = vault.search_items("finance", entry_point_name="documents", subfolder_prefix="work", recursive=True)
        self.assertEqual(len(res_rec), 1)

        # Non-recursive inside "work" should NOT find annual_finance.xlsx because it is in work/2026/
        res_non_rec = vault.search_items("finance", entry_point_name="documents", subfolder_prefix="work", recursive=False)
        self.assertEqual(len(res_non_rec), 0)

    def test_export_entire_entry_point(self) -> None:
        """Verify exporting an entire entry point extracts all nested files and subfolders accurately."""
        vault_dir = self.root_path / "export_test_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Export Vault",
            password=self.password,
            initial_entry_points=["my_archive"],
            sevenzip=self.sz,
        )

        # Add root file and nested file in subfolder
        f1 = self.root_path / "doc.txt"
        f1.write_text("root file content", encoding="utf-8")
        vault.add_files("my_archive", [f1], subfolder="")

        f2 = self.root_path / "nested.png"
        f2.write_bytes(b"nested image data")
        vault.add_files("my_archive", [f2], subfolder="graphics/2026")

        # 1. Test vault.export_entry_point directly
        dest_dir1 = self.root_path / "exported_ep1"
        ok1 = vault.export_entry_point("my_archive", dest_dir1)
        self.assertTrue(ok1)
        self.assertTrue((dest_dir1 / "doc.txt").is_file())
        self.assertEqual((dest_dir1 / "doc.txt").read_text(encoding="utf-8"), "root file content")
        self.assertTrue((dest_dir1 / "graphics" / "2026" / "nested.png").is_file())
        self.assertEqual((dest_dir1 / "graphics" / "2026" / "nested.png").read_bytes(), b"nested image data")

        # 2. Test vault.export_items with ["my_archive"] as path (as sent when in Vault Root)
        dest_dir2 = self.root_path / "exported_ep2"
        ok2 = vault.export_items("my_archive", ["my_archive"], dest_dir2)
        self.assertTrue(ok2)
        # Should create dest_dir2 / my_archive / ...
        target_sub = dest_dir2 / "my_archive"
        self.assertTrue(target_sub.is_dir())
        self.assertTrue((target_sub / "doc.txt").is_file())
        self.assertEqual((target_sub / "doc.txt").read_text(encoding="utf-8"), "root file content")
        self.assertTrue((target_sub / "graphics" / "2026" / "nested.png").is_file())


    def test_vault_obfuscation_option_disabled(self) -> None:
        """Verify vault created with obfuscate_names=False preserves human-readable entry points, folders, and files in vaultables-data."""
        vault_dir = self.root_path / "plain_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Plain Vault",
            password=self.password,
            initial_entry_points=["documents"],
            sevenzip=self.sz,
            obfuscate_names=False,
        )

        self.assertFalse(vault.obfuscate_names)
        self.assertFalse(vault.metadata.obfuscate_names)

        # 1. Entry point folder under vaultables-data should be "documents" (not random 12-char ID)
        meta = vault._v2_metadata["documents"]
        self.assertEqual(meta.ep_dir_id, "documents")
        ep_data_dir = vault.arc_data_dir / "documents"
        self.assertTrue(ep_data_dir.is_dir())

        # 2. Add root file
        f1 = self.root_path / "notes.txt"
        f1.write_text("plain notes", encoding="utf-8")
        vault.add_files("documents", [f1])

        # File chunk should be under vaultables-data/documents/notes-txt/chunk_000.7z (dots replaced with dashes)
        self.assertEqual(meta.items["notes.txt"].item_id, "notes-txt")
        self.assertTrue((ep_data_dir / "notes-txt" / "chunk_000.7z").is_file())

        # 3. Create subfolder "work" and add file
        vault.create_subfolder("documents", "", "work")
        self.assertTrue((ep_data_dir / "work").is_dir())

        f2 = self.root_path / "report.pdf"
        f2.write_bytes(b"report bytes")
        vault.add_files("documents", [f2], subfolder="work")

        meta = vault._v2_metadata["documents"]
        self.assertEqual(meta.items["work/report.pdf"].item_id, "work/report-pdf")
        self.assertTrue((ep_data_dir / "work" / "report-pdf" / "chunk_000.7z").is_file())

        # 4. Preview and extraction work correctly
        preview = vault.extract_file_for_preview("documents", "work/report.pdf")
        self.assertIsNotNone(preview)
        self.assertEqual(preview.read_bytes(), b"report bytes")

        # 5. Rename item renames folder on disk
        self.assertTrue(vault.rename_item("documents", "work/report.pdf", "work/final.pdf"))
        self.assertEqual(meta.items["work/final.pdf"].item_id, "work/final-pdf")
        self.assertTrue((ep_data_dir / "work" / "final-pdf" / "chunk_000.7z").is_file())
        self.assertFalse((ep_data_dir / "work" / "report-pdf").exists())

        # 6. Export works
        dest_dir = self.root_path / "exported_plain"
        self.assertTrue(vault.export_entry_point("documents", dest_dir))
        self.assertTrue((dest_dir / "notes.txt").is_file())
        self.assertEqual((dest_dir / "notes.txt").read_text(encoding="utf-8"), "plain notes")
        self.assertTrue((dest_dir / "work" / "final.pdf").is_file())
        self.assertEqual((dest_dir / "work" / "final.pdf").read_bytes(), b"report bytes")

        # 7. Delete item cleans up on disk
        self.assertTrue(vault.delete_item("documents", "work/final.pdf"))
        self.assertFalse((ep_data_dir / "work" / "final.pdf").exists())

    def test_vault_obfuscation_option_enabled(self) -> None:
        """Verify vault created with obfuscate_names=True (default) generates random folder names."""
        vault_dir = self.root_path / "obf_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Obf Vault",
            password=self.password,
            initial_entry_points=["photos"],
            sevenzip=self.sz,
            obfuscate_names=True,
        )

        self.assertTrue(vault.obfuscate_names)
        self.assertTrue(vault.metadata.obfuscate_names)

        meta = vault._v2_metadata["photos"]
        self.assertNotEqual(meta.ep_dir_id, "photos")
        self.assertEqual(len(meta.ep_dir_id), 12)
        self.assertTrue((vault.arc_data_dir / meta.ep_dir_id).is_dir())


    def test_cannot_create_vault_inside_existing_vault(self) -> None:
        """Verify creating a vault inside or at an existing vault directory raises VaultExistsError."""
        from vaultables.core.vault import VaultExistsError

        vault_dir = self.root_path / "first_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="First Vault",
            password=self.password,
            initial_entry_points=["docs"],
            sevenzip=self.sz,
        )
        self.assertTrue(vault.is_unlocked)

        # 1. Attempting to create at exact same path raises VaultExistsError
        with self.assertRaises(VaultExistsError) as ctx1:
            Vault.create_vault(
                vault_dir,
                name="Duplicate Vault",
                password=self.password,
                sevenzip=self.sz,
            )
        self.assertIn("already an existing vault", str(ctx1.exception))

        # 2. Attempting to create in a nested subfolder inside the vault raises VaultExistsError
        nested_dir = vault_dir / "subfolder" / "nested_vault"
        with self.assertRaises(VaultExistsError) as ctx2:
            Vault.create_vault(
                nested_dir,
                name="Nested Vault",
                password=self.password,
                sevenzip=self.sz,
            )
        self.assertIn("located inside an existing vault folder", str(ctx2.exception))

        # 3. Attempting to create inside vaultables-data raises VaultExistsError
        arc_data_sub = vault_dir / "vaultables-data" / "rogue_vault"
        with self.assertRaises(VaultExistsError) as ctx3:
            Vault.create_vault(
                arc_data_sub,
                name="Rogue Vault",
                password=self.password,
                sevenzip=self.sz,
            )
        self.assertIn("located inside an existing vault folder", str(ctx3.exception))

    def test_home_config_directory_not_mistaken_for_vault(self) -> None:
        """Verify a directory with a .vaultables subdirectory (like ~/.vaultables) is not mistaken for a vault."""
        mock_home = self.root_path / "mock_user_home"
        mock_home.mkdir(parents=True, exist_ok=True)
        # Simulate ~/.vaultables configuration folder
        cfg_dir = mock_home / ".vaultables"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text('{"theme": "dark"}', encoding="utf-8")

        # mock_home must NOT be detected as a vault
        self.assertFalse(Vault.is_vault_dir(mock_home))
        self.assertIsNone(Vault.find_enclosing_vault(mock_home / "Documents" / "FirstVault"))

        # Creating a vault inside mock_home (e.g. ~/Documents/FirstVault) must succeed
        new_vault_path = mock_home / "Documents" / "FirstVault"
        vault = Vault.create_vault(
            new_vault_path,
            name="FirstVault",
            password=self.password,
            sevenzip=self.sz,
        )
        self.assertTrue(vault.is_unlocked)
        self.assertTrue(Vault.is_vault_dir(new_vault_path))
        self.assertFalse(Vault.is_vault_dir(mock_home))

    def test_change_vault_display_name(self) -> None:
        """Verify changing vault display name updates metadata and persists across instances."""
        vault_dir = self.root_path / "named_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Original Vault Name",
            password=self.password,
            sevenzip=self.sz,
        )
        self.assertEqual(vault.name, "Original Vault Name")

        # Change display name
        vault.set_display_name("Custom Secret Vault")
        self.assertEqual(vault.name, "Custom Secret Vault")

        # Verify persisted to .vaultables on disk
        marker_data = json.loads((vault_dir / Vault.MARKER_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(marker_data.get("name"), "Custom Secret Vault")

        # Reopen with new instance and verify display name loaded
        reopened = Vault(vault_dir, self.sz)
        self.assertEqual(reopened.name, "Custom Secret Vault")

    def test_offsite_file_importer(self) -> None:
        """Verify off-site file importer processes encrypted 7z files in import/ and populates 'imports' entry point."""
        vault_dir = self.root_path / "offsite_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Offsite Vault",
            password=self.password,
            sevenzip=self.sz,
        )

        # 1. Verify import folder was created
        self.assertTrue(vault.import_dir.is_dir())
        self.assertTrue((vault.import_dir / "README.txt").is_file())

        # 2. Stage offsite files created outside the vault
        offsite_stage = self.root_path / "offsite_creator"
        offsite_stage.mkdir()

        # Archive 1: Single file notes.7z (encrypted with vault password)
        note_file = offsite_stage / "quick_note.txt"
        note_file.write_text("Secret offsite note content", encoding="utf-8")
        note_7z = vault.import_dir / "notes.7z"
        self.assertTrue(self.sz.add_files(note_7z, [note_file], self.password))

        # Archive 2: Nested folder photos.7z (encrypted with vault password)
        photo_dir = offsite_stage / "travel"
        photo_dir.mkdir()
        (photo_dir / "sunset.jpg").write_bytes(b"sunset_image_bytes")
        photos_7z = vault.import_dir / "photos.7z"
        self.assertTrue(self.sz.add_files(photos_7z, [photo_dir], self.password))

        # Archive 3: Encrypted with WRONG password
        wrong_file = offsite_stage / "wrong.txt"
        wrong_file.write_text("wrong pass", encoding="utf-8")
        wrong_7z = vault.import_dir / "wrong.7z"
        self.assertTrue(self.sz.add_files(wrong_7z, [wrong_file], "WrongPassword123!"))

        # Incomplete / half-downloaded cloud file (.7z with incomplete header/bytes)
        partial_7z = vault.import_dir / "incomplete_download.7z"
        partial_7z.write_bytes(b"7z_partial_half_downloaded_bytes")

        # Non-7z file in import folder
        random_file = vault.import_dir / "notes.txt"
        random_file.write_text("plain text", encoding="utf-8")

        # 3. Process pending imports
        imported_count = vault.process_pending_imports()
        self.assertEqual(imported_count, 2)

        # 4. Valid archives should be removed from import/, while wrong password, half-downloaded cloud file, and non-7z should stay untouched
        self.assertFalse(note_7z.exists())
        self.assertFalse(photos_7z.exists())
        self.assertTrue(wrong_7z.exists())
        self.assertTrue(partial_7z.exists())
        self.assertTrue(random_file.exists())

        # 5. 'imports' entry point was created and populated
        self.assertIn("imports", vault.entry_points)
        items = vault.get_items_in_directory("imports", "")
        item_names = [i.name for i in items]
        self.assertIn("quick_note.txt", item_names)
        self.assertIn("travel", item_names)

        # Verify nested item inside travel
        travel_items = vault.get_items_in_directory("imports", "travel")
        self.assertEqual(len(travel_items), 1)
        self.assertEqual(travel_items[0].name, "sunset.jpg")

        # Verify preview extraction of imported files
        preview_note = vault.extract_file_for_preview("imports", "quick_note.txt")
        self.assertIsNotNone(preview_note)
        self.assertEqual(preview_note.read_text(encoding="utf-8"), "Secret offsite note content")

        preview_img = vault.extract_file_for_preview("imports", "travel/sunset.jpg")
        self.assertIsNotNone(preview_img)
        self.assertEqual(preview_img.read_bytes(), b"sunset_image_bytes")

        # 6. Test automatic import on unlock()
        vault.lock()
        self.assertFalse(vault.is_unlocked)

        # Drop another valid archive into import/
        doc_file = offsite_stage / "extra.pdf"
        doc_file.write_bytes(b"pdf_document_bytes")
        extra_7z = vault.import_dir / "extra.7z"
        self.assertTrue(self.sz.add_files(extra_7z, [doc_file], self.password))

        # Reopen and unlock vault
        reopened = Vault(vault_dir, self.sz)
        unlocked = reopened.unlock(self.password)
        self.assertTrue(unlocked)
        self.assertEqual(reopened.last_imported_count, 1)
        self.assertFalse(extra_7z.exists())

        # Check that 'imports' contains both previous items and new item
        reopened_items = [i.name for i in reopened.get_items_in_directory("imports", "")]
        self.assertIn("quick_note.txt", reopened_items)
        self.assertIn("travel", reopened_items)
        self.assertIn("extra.pdf", reopened_items)

        # 7. Verify obfuscation was strictly respected in obfuscated vault
        self.assertTrue(reopened.obfuscate_names)
        meta_obf = reopened._v2_metadata["imports"]
        self.assertNotEqual(meta_obf.ep_dir_id, "imports")
        self.assertFalse((reopened.arc_data_dir / "imports").exists())
        self.assertTrue((reopened.arc_data_dir / meta_obf.ep_dir_id).is_dir())

        # 8. Verify nested subfolder cleanup inside import/
        nested_subfolder = reopened.import_dir / "incoming_folder"
        nested_subfolder.mkdir()
        nested_file = offsite_stage / "subfile.txt"
        nested_file.write_text("nested folder import test", encoding="utf-8")
        nested_7z = nested_subfolder / "nested.7z"
        self.sz.add_files(nested_7z, [nested_file], self.password)
        self.assertTrue(nested_7z.exists())

        imported_nested = reopened.process_pending_imports()
        self.assertEqual(imported_nested, 1)
        # Archive inside import/ is deleted, but containing folders and unimported files remain untouched
        self.assertFalse(nested_7z.exists())
        self.assertTrue(nested_subfolder.exists())
        self.assertTrue((reopened.import_dir / "README.txt").is_file())

        # 9. Verify obfuscation respected when vault has obfuscate_names=False
        plain_vault_dir = self.root_path / "plain_offsite_vault"
        plain_vault = Vault.create_vault(
            plain_vault_dir,
            name="Plain Offsite Vault",
            password=self.password,
            sevenzip=self.sz,
            obfuscate_names=False,
        )
        self.assertFalse(plain_vault.obfuscate_names)
        plain_file = offsite_stage / "plain_doc.txt"
        plain_file.write_text("plain doc content", encoding="utf-8")
        plain_7z = plain_vault.import_dir / "plain.7z"
        self.sz.add_files(plain_7z, [plain_file], self.password)

        plain_count = plain_vault.process_pending_imports()
        self.assertEqual(plain_count, 1)
        self.assertFalse(plain_7z.exists())
        # In unobfuscated vault, vaultables-data/imports/plain_doc-txt/chunk_000.7z must exist (no dots in folder names)
        plain_meta = plain_vault._v2_metadata["imports"]
        self.assertEqual(plain_meta.ep_dir_id, "imports")
        self.assertTrue((plain_vault.arc_data_dir / "imports" / "plain_doc-txt" / "chunk_000.7z").is_file())


    def test_on_demand_obfuscation(self) -> None:
        """
        Verify on-demand obfuscation override when creating entry points:
        - Obfuscated vault: override to make entry point easily readable (plain names).
        - Unobfuscated vault: override to make entry point names randomized (obfuscated).
        """
        test_file = self.root_path / "ondemand_sample.txt"
        test_file.write_text("on demand obfuscation test content", encoding="utf-8")

        # 1. Obfuscated Vault
        obf_vault_dir = self.root_path / "ondemand_obf_vault"
        obf_vault = Vault.create_vault(
            obf_vault_dir,
            name="OnDemand Obf Vault",
            password=self.password,
            sevenzip=self.sz,
            obfuscate_names=True,
        )
        self.assertTrue(obf_vault.obfuscate_names)

        # Default entry point (inherits True)
        obf_vault.create_entry_point("default_ep")
        self.assertTrue(obf_vault.is_entry_point_obfuscated("default_ep"))
        meta_default = obf_vault._v2_metadata["default_ep"]
        self.assertNotEqual(meta_default.ep_dir_id, "default_ep")
        self.assertTrue(meta_default.is_obfuscated(obf_vault.obfuscate_names))

        # On-demand readable entry point in obfuscated vault (obfuscate=False)
        obf_vault.create_entry_point("readable_ep", obfuscate=False)
        self.assertFalse(obf_vault.is_entry_point_obfuscated("readable_ep"))
        meta_readable = obf_vault._v2_metadata["readable_ep"]
        self.assertEqual(meta_readable.ep_dir_id, "readable_ep")
        self.assertFalse(meta_readable.is_obfuscated(obf_vault.obfuscate_names))
        self.assertFalse(meta_readable.obfuscate_names)

        # Add file to readable_ep and verify human-readable path under vaultables-data/ (no dots in folder names)
        obf_vault.add_files("readable_ep", [test_file])
        expected_chunk = obf_vault.arc_data_dir / "readable_ep" / "ondemand_sample-txt" / "chunk_000.7z"
        self.assertTrue(expected_chunk.is_file())

        # Test subfolder in readable_ep
        obf_vault.create_subfolder("readable_ep", "", "subdocs")
        self.assertTrue((obf_vault.arc_data_dir / "readable_ep" / "subdocs").is_dir())

        # Rename file in readable_ep
        obf_vault.rename_item("readable_ep", "ondemand_sample.txt", "renamed_sample.txt")
        renamed_chunk = obf_vault.arc_data_dir / "readable_ep" / "renamed_sample-txt" / "chunk_000.7z"
        self.assertTrue(renamed_chunk.is_file())
        self.assertFalse(expected_chunk.exists())

        # 2. Unobfuscated Vault
        plain_vault_dir = self.root_path / "ondemand_plain_vault"
        plain_vault = Vault.create_vault(
            plain_vault_dir,
            name="OnDemand Plain Vault",
            password=self.password,
            sevenzip=self.sz,
            obfuscate_names=False,
        )
        self.assertFalse(plain_vault.obfuscate_names)

        # Default entry point (inherits False)
        plain_vault.create_entry_point("default_plain_ep")
        self.assertFalse(plain_vault.is_entry_point_obfuscated("default_plain_ep"))
        meta_plain = plain_vault._v2_metadata["default_plain_ep"]
        self.assertEqual(meta_plain.ep_dir_id, "default_plain_ep")

        # On-demand obfuscated entry point in unobfuscated vault (obfuscate=True)
        plain_vault.create_entry_point("secret_ep", obfuscate=True)
        self.assertTrue(plain_vault.is_entry_point_obfuscated("secret_ep"))
        meta_secret = plain_vault._v2_metadata["secret_ep"]
        self.assertNotEqual(meta_secret.ep_dir_id, "secret_ep")
        self.assertTrue(meta_secret.is_obfuscated(plain_vault.obfuscate_names))
        self.assertTrue(meta_secret.obfuscate_names)

        # Add file to secret_ep and verify randomized path under vaultables-data/
        plain_vault.add_files("secret_ep", [test_file])
        item_meta = meta_secret.items["ondemand_sample.txt"]
        self.assertNotEqual(item_meta.item_id, "ondemand_sample.txt")
        self.assertTrue((plain_vault.arc_data_dir / meta_secret.ep_dir_id / item_meta.item_id / "chunk_000.7z").is_file())
        self.assertFalse((plain_vault.arc_data_dir / "secret_ep").exists())


    def test_refresh_view_and_cache_invalidation(self) -> None:
        """Verify Vault.clear_cache(), refresh_entry_points(), and force_reload invalidate cache accurately."""
        vault_dir = self.root_path / "refresh_test_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="Refresh Test Vault",
            password=self.password,
            initial_entry_points=["docs"],
            sevenzip=self.sz,
        )

        f1 = self.root_path / "item1.txt"
        f1.write_text("item 1 content", encoding="utf-8")
        vault.add_files("docs", [f1])

        # 1. First read populates in-memory cache
        items = vault.get_items_in_directory("docs")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "item1.txt")
        self.assertIn("docs", vault._cache)

        # 2. Simulate external addition by a second vault instance
        f2 = self.root_path / "item2.txt"
        f2.write_text("item 2 content", encoding="utf-8")
        external_vault = Vault(vault_dir, self.sz)
        self.assertTrue(external_vault.unlock(self.password))
        external_vault.add_files("docs", [f2])

        # 3. Default get_items_in_directory without force_reload uses in-memory cache
        stale_items = vault.get_items_in_directory("docs")
        self.assertEqual(len(stale_items), 1)

        # 4. force_reload=True reloads metadata from disk
        fresh_items = vault.get_items_in_directory("docs", force_reload=True)
        self.assertEqual(len(fresh_items), 2)
        names = {i.name for i in fresh_items}
        self.assertEqual(names, {"item1.txt", "item2.txt"})

        # 5. Drop file into import/ and call refresh_entry_points()
        offsite_f = self.root_path / "imported_note.txt"
        offsite_f.write_text("imported note content", encoding="utf-8")
        import_7z = vault.import_dir / "notes.7z"
        self.sz.add_files(import_7z, [offsite_f], self.password)
        self.assertTrue(import_7z.is_file())

        vault.refresh_entry_points()
        self.assertIn("imports", vault.entry_points)
        self.assertFalse(import_7z.exists())

        # 6. Delete entry point .7z file directly from disk and test refresh_entry_points()
        (vault_dir / "docs.7z").unlink()
        vault.refresh_entry_points()
        self.assertNotIn("docs", vault.entry_points)
        self.assertNotIn("docs", vault._v2_metadata)
        self.assertNotIn("docs", vault._cache)


    def test_ignore_appledouble_and_system_metadata_files(self) -> None:
        """Verify macOS AppleDouble (._*) files and system junk (.DS_Store) are ignored and auto-purged."""
        from vaultables.core.models import is_ignorable_system_file
        from vaultables.core.storage_v2 import V2ItemMetadata

        # 1. Direct classifier tests
        self.assertTrue(is_ignorable_system_file("._example.pdf"))
        self.assertTrue(is_ignorable_system_file(Path("/Volumes/GoogleDrive/._example.pdf")))
        self.assertTrue(is_ignorable_system_file(".DS_Store"))
        self.assertTrue(is_ignorable_system_file("Thumbs.db"))
        self.assertTrue(is_ignorable_system_file("desktop.ini"))
        self.assertFalse(is_ignorable_system_file("example.pdf"))
        self.assertFalse(is_ignorable_system_file("notes.txt"))
        self.assertFalse(is_ignorable_system_file(".gitignore"))

        # 2. Vaulting files with ._* sidecar companions (e.g. from Google Drive or FAT/exFAT drives)
        vault_dir = self.root_path / "appledouble_vault"
        vault = Vault.create_vault(
            vault_dir,
            name="AppleDouble Vault",
            password=self.password,
            initial_entry_points=["docs"],
            sevenzip=self.sz,
        )

        stage_dir = self.root_path / "stage_gdrive"
        stage_dir.mkdir()

        # Actual file (10 KB)
        main_pdf = stage_dir / "example.pdf"
        main_pdf.write_bytes(b"%PDF-1.4 real pdf document data" * 300)

        # AppleDouble companion file (4 KB) produced by macOS on Google Drive
        sidecar_pdf = stage_dir / "._example.pdf"
        sidecar_pdf.write_bytes(b"\x00\x05\x16\x07AppleDouble metadata" * 150)

        # macOS .DS_Store
        ds_store = stage_dir / ".DS_Store"
        ds_store.write_bytes(b"\x00\x00\x00\x01Bud1" * 50)

        # User vaults all items (as happens during multi-selection or folder drop)
        vault.add_files("docs", [main_pdf, sidecar_pdf, ds_store])

        # Verify only the genuine file was added
        items = vault.get_items_in_directory("docs")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "example.pdf")
        self.assertNotIn("._example.pdf", vault._v2_metadata["docs"].items)
        self.assertNotIn(".DS_Store", vault._v2_metadata["docs"].items)

        # 3. Adding a folder containing nested ._* files
        travel_dir = stage_dir / "travel"
        travel_dir.mkdir()
        photo = travel_dir / "beach.jpg"
        photo.write_bytes(b"jpg image data")
        photo_sidecar = travel_dir / "._beach.jpg"
        photo_sidecar.write_bytes(b"AppleDouble photo metadata")
        travel_ds_store = travel_dir / ".DS_Store"
        travel_ds_store.write_bytes(b"nested ds store")

        vault.add_files("docs", [travel_dir])

        travel_items = vault.get_items_in_directory("docs", "travel")
        self.assertEqual(len(travel_items), 1)
        self.assertEqual(travel_items[0].name, "beach.jpg")

        # 4. Auto-purge existing ._* entries in legacy / corrupted metadata
        meta = vault._v2_metadata["docs"]
        ep_data_dir = vault.arc_data_dir / meta.ep_dir_id
        dummy_stale_dir = ep_data_dir / "stale_item"
        dummy_stale_dir.mkdir(parents=True, exist_ok=True)
        (dummy_stale_dir / "chunk_000.7z").write_bytes(b"fake chunk")

        meta.items["._legacy.pdf"] = V2ItemMetadata(
            path="._legacy.pdf",
            name="._legacy.pdf",
            is_dir=False,
            item_id="stale_item",
            size=4096,
        )
        vault.v2_engine.save_metadata(vault.entry_points["docs"].archive_file, meta, vault.password)

        # Refresh / re-load entry points triggers auto-purge
        vault.refresh_entry_points()
        reloaded_items = vault.get_items_in_directory("docs")
        self.assertNotIn("._legacy.pdf", [i.name for i in reloaded_items])
        self.assertNotIn("._legacy.pdf", vault._v2_metadata["docs"].items)
        self.assertFalse(dummy_stale_dir.exists())

    def test_parallel_batch_ingestion(self) -> None:
        """Test parallel multi-threaded ingestion of multiple files and folders in Vault.add_files."""
        vault_dir = Path(self.tmp_dir) / "parallel_vault"
        vault = Vault.create_vault(vault_dir, name="ParallelVault", password=self.password, initial_entry_points=["data"], sevenzip=self.sz)

        # Create 10 files and 1 directory with nested files
        staging_dir = Path(self.tmp_dir) / "batch_sources"
        staging_dir.mkdir(parents=True, exist_ok=True)

        batch_files = []
        for i in range(10):
            p = staging_dir / f"file_{i:02d}.txt"
            p.write_bytes(f"Content for file {i} ".encode("utf-8") * 50)
            batch_files.append(p)

        sub_dir = staging_dir / "nested_folder"
        sub_dir.mkdir(parents=True, exist_ok=True)
        for j in range(3):
            sub_file = sub_dir / f"nested_{j:02d}.bin"
            sub_file.write_bytes(os.urandom(1024))

        batch_files.append(sub_dir)

        # Ingest entire batch in parallel
        self.assertTrue(vault.add_files("data", batch_files))

        # Verify all items in root of 'data'
        root_items = vault.get_items_in_directory("data")
        root_names = {it.name for it in root_items}
        for i in range(10):
            self.assertIn(f"file_{i:02d}.txt", root_names)
        self.assertIn("nested_folder", root_names)

        # Verify nested items
        nested_items = vault.get_items_in_directory("data", "nested_folder")
        nested_names = {it.name for it in nested_items}
        for j in range(3):
            self.assertIn(f"nested_{j:02d}.bin", nested_names)

        # Verify extraction and data integrity of parallel-ingested files
        export_dir = Path(self.tmp_dir) / "parallel_export"
        meta = vault._v2_metadata["data"]
        ep_data_dir = vault.arc_data_dir / meta.ep_dir_id
        for i in range(10):
            it = meta.items[f"file_{i:02d}.txt"]
            out_file = export_dir / f"file_{i:02d}.txt"
            ok = vault.v2_engine.extract_file_to_destination(
                it, ep_data_dir / it.item_id, vault.password, out_file
            )
            self.assertTrue(ok)
            expected = f"Content for file {i} ".encode("utf-8") * 50
            self.assertEqual(out_file.read_bytes(), expected)

    def test_stdin_chunking_multipart_and_reassembly(self) -> None:
        """Test direct stdin streaming chunking and reassembly for files exceeding chunk size."""
        vault_dir = Path(self.tmp_dir) / "chunk_stream_vault"
        vault = Vault.create_vault(vault_dir, name="ChunkStreamVault", password=self.password, initial_entry_points=["media"], sevenzip=self.sz)

        # Create a 25 KB file with non-repeating data
        large_source = Path(self.tmp_dir) / "large_source.bin"
        original_data = os.urandom(25 * 1024)
        large_source.write_bytes(original_data)

        # Chunk with small override (8 KB) to create 4 chunks via stdin streaming
        chunk_target_dir = Path(self.tmp_dir) / "item_chunks"
        chunk_target_dir.mkdir(parents=True, exist_ok=True)

        size, packed, chunks = vault.v2_engine.chunk_and_encrypt_file(
            large_source,
            chunk_target_dir,
            vault.password,
            chunk_size_override=8 * 1024,
        )

        self.assertEqual(size, 25 * 1024)
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0]["filename"], "chunk_000.7z")
        self.assertEqual(chunks[1]["filename"], "chunk_001.7z")
        self.assertEqual(chunks[2]["filename"], "chunk_002.7z")
        self.assertEqual(chunks[3]["filename"], "chunk_003.7z")

        # Reassemble using extract_file_to_destination
        from vaultables.core.storage_v2 import V2ItemMetadata
        item_meta = V2ItemMetadata(
            path="large_source.bin",
            name="large_source.bin",
            chunks=chunks,
        )
        reassembled_dest = Path(self.tmp_dir) / "reassembled.bin"
        success = vault.v2_engine.extract_file_to_destination(
            item_meta,
            chunk_target_dir,
            vault.password,
            reassembled_dest,
        )
        self.assertTrue(success)
        self.assertEqual(reassembled_dest.read_bytes(), original_data)

if __name__ == "__main__":

    unittest.main()
