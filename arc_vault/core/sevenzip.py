"""Cross-platform 7-Zip CLI wrapper for AES-256 encrypted archive operations."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from arc_vault.core.models import ArchiveItem, classify_file


class SevenZipExecutableNotFoundError(Exception):
    """Raised when no compatible 7-Zip binary can be found on the host system."""
    pass


class SevenZipOperationError(Exception):
    """Raised when a 7-Zip operation fails."""
    pass


class SevenZip:
    """Wrapper around 7-Zip command line interface (7zz, 7z, nanazip)."""

    def __init__(self, override_path: Optional[str] = None) -> None:
        self._binary_path: Optional[str] = None
        if override_path and Path(override_path).is_file():
            self._binary_path = override_path
        else:
            self._binary_path = self.find_binary()

    @classmethod
    def find_binary(cls) -> Optional[str]:
        """Detect the 7-Zip executable path across macOS, Linux, and Windows."""
        # 1. Environment variable
        env_override = os.environ.get("ARCVUULT_7Z_PATH") or os.environ.get("SEVENZIP_PATH")
        if env_override and Path(env_override).is_file():
            return env_override

        # 2. Check PATH for standard binary names
        candidates = ["7zz", "7z", "7za", "nanazip"]
        if sys.platform == "win32":
            candidates = ["7z.exe", "7za.exe", "nanazip.exe"]

        for cand in candidates:
            found = shutil.which(cand)
            if found:
                return found

        # 3. Platform-specific known standard locations
        known_locations = []
        if sys.platform == "darwin":
            known_locations = [
                "/opt/homebrew/bin/7zz",
                "/usr/local/bin/7zz",
                "/opt/homebrew/bin/7z",
                "/usr/local/bin/7z",
                "/opt/homebrew/Cellar/sevenzip/26.05/bin/7zz",
            ]
        elif sys.platform == "win32":
            known_locations = [
                r"C:\Program Files\7-Zip\7z.exe",
                r"C:\Program Files (x86)\7-Zip\7z.exe",
                r"C:\Program Files\NanaZip\nanazip.exe",
            ]
        else:  # Linux / Unix
            known_locations = [
                "/usr/bin/7zz",
                "/usr/bin/7z",
                "/usr/local/bin/7z",
                "/usr/bin/7za",
            ]

        for loc in known_locations:
            if Path(loc).is_file() and os.access(loc, os.X_OK if sys.platform != "win32" else os.F_OK):
                return loc

        return None

    @property
    def binary(self) -> str:
        if not self._binary_path:
            self._binary_path = self.find_binary()
        if not self._binary_path:
            raise SevenZipExecutableNotFoundError(
                "Could not find a 7-Zip binary (7zz, 7z, or nanazip). "
                "Please install 7-Zip (or sevenzip via brew/apt/winget)."
            )
        return self._binary_path

    def _run(
        self,
        args: List[str],
        cwd: Optional[Path] = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run 7-Zip command with arguments list (avoids shell execution)."""
        cmd = [self.binary] + args
        # Hide console window on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else None,
            startupinfo=startupinfo,
        )
        if check and res.returncode not in (0, 1):
            err = (res.stderr or res.stdout).strip()
            raise SevenZipOperationError(f"7-Zip error ({res.returncode}): {err}")
        return res

    def test_archive(self, archive_path: Path, password: str) -> bool:
        """Test archive integrity and verify if password opens the archive."""
        if not archive_path.exists():
            return False

        res = self._run(["t", f"-p{password}", "-y", str(archive_path.resolve())])
        if res.returncode in (0, 1) and "Everything is Ok" in res.stdout:
            return True

        stdout_err = (res.stdout + "\n" + res.stderr).lower()
        if "wrong password" in stdout_err or "cannot open encrypted" in stdout_err or "headers error" in stdout_err:
            return False

        return res.returncode in (0, 1)

    def list_archive(self, archive_path: Path, password: str, entry_point_name: str = "") -> List[ArchiveItem]:
        """List contents of archive using '-slt' switch."""
        if not archive_path.exists():
            return []

        res = self._run(["l", "-slt", f"-p{password}", "-y", str(archive_path.resolve())])
        if res.returncode not in (0, 1):
            stdout_err = (res.stdout + "\n" + res.stderr).lower()
            if "wrong password" in stdout_err or "headers error" in stdout_err:
                raise SevenZipOperationError("Wrong password for archive.")
            raise SevenZipOperationError(f"Failed to list archive: {res.stderr or res.stdout}")

        items: List[ArchiveItem] = []
        raw_blocks = res.stdout.split("\n\n")

        for block in raw_blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            entry_dict: Dict[str, str] = {}
            for line in lines:
                if "=" in line:
                    key, val = line.split("=", 1)
                    entry_dict[key.strip()] = val.strip()

            path_val = entry_dict.get("Path")
            # Skip the root archive description block (where Path == archive file name)
            if not path_val or path_val == archive_path.name or path_val == str(archive_path.resolve()):
                continue

            # Skip hidden marker file if present
            if path_val.endswith(".arcvault_init"):
                continue

            is_folder = entry_dict.get("Folder") == "+"
            size = int(entry_dict.get("Size", 0)) if entry_dict.get("Size", "").isdigit() else 0
            packed_size = int(entry_dict.get("Packed Size", 0)) if entry_dict.get("Packed Size", "").isdigit() else 0
            modified = entry_dict.get("Modified")
            attributes = entry_dict.get("Attributes", "")
            crc = entry_dict.get("CRC")
            encrypted = entry_dict.get("Encrypted") == "+"

            item_name = Path(path_val).name
            category = classify_file(item_name, is_dir=is_folder)

            items.append(
                ArchiveItem(
                    name=item_name,
                    path=path_val.replace("\\", "/"),
                    is_dir=is_folder,
                    size=size,
                    packed_size=packed_size,
                    modified=modified,
                    attributes=attributes,
                    crc=crc,
                    encrypted=encrypted,
                    entry_point_name=entry_point_name or archive_path.stem,
                    category=category,
                )
            )

        return items

    def create_empty_archive(self, archive_path: Path, password: str) -> bool:
        """Create a new 7z archive encrypted with AES-256 and header encryption."""
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            marker = Path(tmp_dir) / ".arcvault_init"
            marker.write_text("ArcVault entry point archive initialized.\n", encoding="utf-8")

            res = self._run(
                ["a", f"-p{password}", "-mhe=on", "-mx=5", "-y", str(archive_path.resolve()), ".arcvault_init"],
                cwd=Path(tmp_dir),
            )
            return res.returncode in (0, 1) and archive_path.exists()

    def add_files(
        self,
        archive_path: Path,
        source_paths: List[Path],
        password: str,
        archive_subfolder: str = "",
    ) -> bool:
        """
        Add local files or directories into the archive with robust staging.
        Supports both root and nested subfolders reliably without absolute path issues.
        """
        if not source_paths:
            return True

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        norm_sub = archive_subfolder.strip("/").replace("\\", "/")

        with tempfile.TemporaryDirectory(prefix="arcvault_add_") as staging_dir:
            staging_root = Path(staging_dir)
            target_stage = staging_root / norm_sub if norm_sub else staging_root
            target_stage.mkdir(parents=True, exist_ok=True)

            items_to_add: List[str] = []
            for src in source_paths:
                if not src.exists():
                    continue
                dest = target_stage / src.name
                if src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest)

                if not norm_sub:
                    items_to_add.append(src.name)

            if norm_sub:
                items_to_add = [norm_sub]

            if not items_to_add:
                return True

            cmd = [
                "a",
                f"-p{password}",
                "-mhe=on",
                "-mx=5",
                "-r",
                "-y",
                str(archive_path.resolve()),
            ] + items_to_add

            res = self._run(cmd, cwd=staging_root)

            # In 7-Zip, exit code 0 is OK, 1 is Warning (e.g. attribute warnings on macOS, file added successfully)
            if res.returncode not in (0, 1):
                err = (res.stderr or res.stdout).strip()
                raise SevenZipOperationError(err or f"7-Zip exited with code {res.returncode}")

            return True

    def update_single_file(
        self,
        archive_path: Path,
        local_source_file: Path,
        internal_path: str,
        password: str,
    ) -> bool:
        """Quickly update an existing file inside the 7z archive via staging."""
        if not local_source_file.exists() or not archive_path.exists():
            return False

        norm_internal = internal_path.strip("/").replace("\\", "/")
        with tempfile.TemporaryDirectory(prefix="arcvault_edit_") as stage_dir:
            stage_path = Path(stage_dir) / norm_internal
            stage_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_source_file, stage_path)

            res = self._run(
                ["u", f"-p{password}", "-mhe=on", "-mx=5", "-y", str(archive_path.resolve()), norm_internal],
                cwd=Path(stage_dir),
            )
            if res.returncode not in (0, 1):
                err = (res.stderr or res.stdout).strip()
                raise SevenZipOperationError(err or f"7-Zip update error ({res.returncode})")

            return True

    def create_subfolder_in_archive(
        self,
        archive_path: Path,
        folder_path_inside_archive: str,
        password: str,
    ) -> bool:
        """Create a directory entry inside the archive."""
        norm_path = folder_path_inside_archive.strip("/").replace("\\", "/")
        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_dir = Path(tmp_dir) / norm_path
            dummy_dir.mkdir(parents=True, exist_ok=True)
            keep_file = dummy_dir / ".keep"
            keep_file.write_text("", encoding="utf-8")

            res = self._run(
                ["a", f"-p{password}", "-mhe=on", "-mx=5", "-r", "-y", str(archive_path.resolve()), norm_path],
                cwd=Path(tmp_dir),
            )
            self._run(["d", f"-p{password}", "-mhe=on", "-y", str(archive_path.resolve()), f"{norm_path}/.keep"])
            return res.returncode in (0, 1)

    def extract_file_for_preview(
        self,
        archive_path: Path,
        internal_path: str,
        password: str,
        dest_dir: Path,
    ) -> Optional[Path]:
        """Extract a single file into dest_dir for preview."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        res = self._run(
            ["e", f"-p{password}", f"-o{str(dest_dir.resolve())}", "-y", str(archive_path.resolve()), internal_path]
        )
        if res.returncode not in (0, 1):
            return None

        filename = Path(internal_path).name
        target = dest_dir / filename
        return target if target.exists() else None

    def extract_to_destination(
        self,
        archive_path: Path,
        internal_paths: List[str],
        password: str,
        destination_dir: Path,
    ) -> bool:
        """Extract selected items or entire archive preserving directory hierarchy."""
        destination_dir.mkdir(parents=True, exist_ok=True)
        cmd = ["x", f"-p{password}", f"-o{str(destination_dir.resolve())}", "-y", str(archive_path.resolve())]
        if internal_paths:
            cmd.extend(internal_paths)
        res = self._run(cmd)
        return res.returncode in (0, 1)

    def delete_items(
        self,
        archive_path: Path,
        internal_paths: List[str],
        password: str,
    ) -> bool:
        """Delete files or folders from archive."""
        if not internal_paths:
            return True
        cmd = ["d", f"-p{password}", "-mhe=on", "-y", str(archive_path.resolve())] + internal_paths
        res = self._run(cmd)
        return res.returncode in (0, 1)

    def rename_item(
        self,
        archive_path: Path,
        old_path: str,
        new_path: str,
        password: str,
    ) -> bool:
        """Rename a file or folder inside the archive."""
        cmd = ["rn", f"-p{password}", "-mhe=on", "-y", str(archive_path.resolve()), old_path, new_path]
        res = self._run(cmd)
        return res.returncode in (0, 1)
