"""V2 Chunked and Metadata-Decoupled Storage Engine for ArcVault.

Under V2:
- Vault root contains lightweight encrypted {entry_point}.7z metadata archives.
- Vault root contains 'arc-data/' holding encrypted file and folder chunks.
- Files > 1GB are shredded into 1GB encrypted chunks with 7-Zip store mode (-mx=0) and AES-256 (-mhe=on).
- Files <= 1GB skip shredding and are stored as a single encrypted chunk_000.7z.
- Metadata is projected onto the UI as virtual files and folders.
- Add and delete operations never re-archive existing files.
"""

from __future__ import annotations

import json
import secrets
import shutil
import string
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from arc_vault.core.models import ArchiveItem, FileCategory, classify_file
from arc_vault.core.sevenzip import SevenZip, SevenZipOperationError
from arc_vault.logger import log_info, log_warning

# Default chunk size: 1 GB (1024 * 1024 * 1024 bytes)
DEFAULT_CHUNK_SIZE: int = 1024 * 1024 * 1024
METADATA_FILENAME: str = "metadata.json"


def generate_random_id(length: int = 12) -> str:
    """Generate a random alphanumeric ID (letters and digits only)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@dataclass
class V2ItemMetadata:
    """Metadata for a single virtual file or directory inside an entry point."""

    path: str              # Internal path, e.g. "family/photo.png" or "family"
    name: str              # e.g. "photo.png"
    is_dir: bool = False
    item_id: str = ""      # Random alphanumeric directory name in arc-data/{ep_dir_id}/{item_id}
    size: int = 0          # Total uncompressed size
    packed_size: int = 0   # Total encrypted size on disk
    modified: str = ""
    category: str = "UNKNOWN"
    chunks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> V2ItemMetadata:
        return cls(
            path=data.get("path", ""),
            name=data.get("name", ""),
            is_dir=bool(data.get("is_dir", False)),
            item_id=data.get("item_id", ""),
            size=int(data.get("size", 0)),
            packed_size=int(data.get("packed_size", 0)),
            modified=data.get("modified", ""),
            category=data.get("category", "UNKNOWN"),
            chunks=data.get("chunks", []),
        )

    def to_archive_item(self, entry_point_name: str) -> ArchiveItem:
        """Project this metadata item into an ArchiveItem for GUI views."""
        cat_enum = FileCategory[self.category] if self.category in FileCategory.__members__ else classify_file(self.name, is_dir=self.is_dir)
        return ArchiveItem(
            name=self.name,
            path=self.path,
            is_dir=self.is_dir,
            size=self.size,
            packed_size=self.packed_size,
            modified=self.modified,
            encrypted=True,
            entry_point_name=entry_point_name,
            category=cat_enum,
        )


@dataclass
class V2EntryPointMetadata:
    """Top-level metadata stored inside {entry_point}.7z."""

    version: str = "2.0"
    entry_point_name: str = ""
    ep_dir_id: str = ""    # Folder name under vault_root / "arc-data" / ep_dir_id
    items: Dict[str, V2ItemMetadata] = field(default_factory=dict)

    def to_json(self) -> str:
        data = {
            "version": self.version,
            "entry_point_name": self.entry_point_name,
            "ep_dir_id": self.ep_dir_id,
            "items": {p: item.to_dict() for p, item in self.items.items()},
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> V2EntryPointMetadata:
        data = json.loads(json_str)
        items_raw = data.get("items", {})
        parsed_items: Dict[str, V2ItemMetadata] = {}
        for p, item_dict in items_raw.items():
            parsed_items[p] = V2ItemMetadata.from_dict(item_dict)

        return cls(
            version=data.get("version", "2.0"),
            entry_point_name=data.get("entry_point_name", ""),
            ep_dir_id=data.get("ep_dir_id", ""),
            items=parsed_items,
        )


class V2StorageEngine:
    """Handles file chunking, store-mode AES-256 encryption, and metadata sync."""

    def __init__(self, sevenzip: SevenZip, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self.sevenzip = sevenzip
        self.chunk_size = chunk_size

    def create_entry_point_archive(
        self,
        archive_path: Path,
        entry_point_name: str,
        password: str,
        arc_data_root: Path,
    ) -> V2EntryPointMetadata:
        """Create a new V2 metadata archive and its arc-data directory."""
        ep_dir_id = generate_random_id(12)
        ep_data_dir = arc_data_root / ep_dir_id
        ep_data_dir.mkdir(parents=True, exist_ok=True)

        meta = V2EntryPointMetadata(
            version="2.0",
            entry_point_name=entry_point_name,
            ep_dir_id=ep_dir_id,
            items={},
        )
        self.save_metadata(archive_path, meta, password)
        return meta

    def load_metadata(self, archive_path: Path, password: str) -> Optional[V2EntryPointMetadata]:
        """Read and parse metadata.json from {entry_point}.7z."""
        if not archive_path.exists():
            return None

        with tempfile.TemporaryDirectory(prefix="arc_meta_load_") as tmp_dir:
            extracted_path = self.sevenzip.extract_file_for_preview(
                archive_path, METADATA_FILENAME, password, Path(tmp_dir)
            )
            if not extracted_path or not extracted_path.exists():
                return None

            try:
                json_str = extracted_path.read_text(encoding="utf-8")
                return V2EntryPointMetadata.from_json(json_str)
            except Exception as e:
                log_warning(f"Failed to parse metadata from {archive_path.name}: {e}")
                return None

    def save_metadata(self, archive_path: Path, meta: V2EntryPointMetadata, password: str) -> bool:
        """Pack metadata.json into {entry_point}.7z with AES-256 header encryption."""
        with tempfile.TemporaryDirectory(prefix="arc_meta_save_") as tmp_dir:
            meta_file = Path(tmp_dir) / METADATA_FILENAME
            meta_file.write_text(meta.to_json(), encoding="utf-8")

            # Update/replace metadata.json in archive
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                "a",
                f"-p{password}",
                "-mhe=on",
                "-mx=5",
                "-y",
                str(archive_path.resolve()),
                METADATA_FILENAME,
            ]
            res = self.sevenzip._run(cmd, cwd=Path(tmp_dir))
            return res.returncode in (0, 1)

    def chunk_and_encrypt_file(
        self,
        source_file: Path,
        item_dir: Path,
        password: str,
        chunk_size_override: Optional[int] = None,
    ) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Shred a file into 1GB encrypted chunks with store mode (-mx=0) and AES-256 (-mhe=on).
        If file <= 1GB, shredding is skipped and a single chunk_000.7z is created.
        Returns (total_size, total_packed_size, chunk_list).
        """
        item_dir.mkdir(parents=True, exist_ok=True)
        effective_chunk_size = chunk_size_override or self.chunk_size
        file_size = source_file.stat().st_size
        chunks: List[Dict[str, Any]] = []
        total_packed = 0

        # Optimization: file <= chunk_size skips multi-part shredding
        if file_size <= effective_chunk_size:
            chunk_file = item_dir / "chunk_000.7z"
            self._encrypt_chunk(chunk_file, source_file, password)
            packed_size = chunk_file.stat().st_size if chunk_file.exists() else file_size
            chunks.append({
                "index": 0,
                "filename": "chunk_000.7z",
                "size": file_size,
                "packed_size": packed_size,
            })
            return file_size, packed_size, chunks

        # File > chunk_size: Shred into chunks
        chunk_index = 0
        with open(source_file, "rb") as f_in:
            while True:
                data = f_in.read(effective_chunk_size)
                if not data and chunk_index > 0:
                    break

                chunk_file = item_dir / f"chunk_{chunk_index:03d}.7z"
                with tempfile.TemporaryDirectory(prefix="arc_chunk_stage_") as stage_dir:
                    part_file = Path(stage_dir) / f"part_{chunk_index:03d}"
                    part_file.write_bytes(data)
                    self._encrypt_chunk(chunk_file, part_file, password)

                packed_size = chunk_file.stat().st_size if chunk_file.exists() else len(data)
                total_packed += packed_size
                chunks.append({
                    "index": chunk_index,
                    "filename": f"chunk_{chunk_index:03d}.7z",
                    "size": len(data),
                    "packed_size": packed_size,
                })
                chunk_index += 1
                if len(data) < effective_chunk_size:
                    break

        return file_size, total_packed, chunks

    def _encrypt_chunk(self, chunk_archive_file: Path, source_data_file: Path, password: str) -> bool:
        """Create a single AES-256 encrypted chunk using store mode (-mx=0, no compression)."""
        cmd = [
            "a",
            "-mx=0",
            "-mhe=on",
            f"-p{password}",
            "-y",
            str(chunk_archive_file.resolve()),
            source_data_file.name,
        ]
        res = self.sevenzip._run(cmd, cwd=source_data_file.parent)
        if res.returncode not in (0, 1):
            raise SevenZipOperationError(f"Failed to encrypt chunk: {res.stderr or res.stdout}")
        return True

    def extract_file_to_destination(
        self,
        item: V2ItemMetadata,
        item_dir: Path,
        password: str,
        dest_file: Path,
    ) -> bool:
        """
        Extract chunk(s) and reassemble into dest_file.
        Streams chunks in sequence to minimize memory and temporary disk usage.
        """
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if dest_file.exists():
            dest_file.unlink()

        if not item.chunks:
            # Empty file
            dest_file.touch()
            return True

        # Single chunk fast path
        if len(item.chunks) == 1:
            chunk_file = item_dir / item.chunks[0]["filename"]
            with tempfile.TemporaryDirectory(prefix="arc_ext_single_") as tmp_dir:
                res = self.sevenzip._run(
                    ["e", f"-p{password}", f"-o{tmp_dir}", "-y", str(chunk_file.resolve())]
                )
                if res.returncode not in (0, 1):
                    return False
                extracted_files = list(Path(tmp_dir).iterdir())
                if extracted_files:
                    shutil.move(str(extracted_files[0]), str(dest_file))
                    return True
                dest_file.touch()
                return True

        # Multi-chunk streaming reassembly
        sorted_chunks = sorted(item.chunks, key=lambda c: c.get("index", 0))
        with open(dest_file, "wb") as f_out:
            for c in sorted_chunks:
                chunk_file = item_dir / c["filename"]
                if not chunk_file.exists():
                    log_warning(f"Missing chunk file: {chunk_file}")
                    return False

                with tempfile.TemporaryDirectory(prefix="arc_ext_part_") as tmp_dir:
                    res = self.sevenzip._run(
                        ["e", f"-p{password}", f"-o{tmp_dir}", "-y", str(chunk_file.resolve())]
                    )
                    if res.returncode not in (0, 1):
                        return False

                    extracted = list(Path(tmp_dir).iterdir())
                    if extracted:
                        with open(extracted[0], "rb") as f_in:
                            while True:
                                buf = f_in.read(1024 * 1024)  # 1MB buffer
                                if not buf:
                                    break
                                f_out.write(buf)

        return dest_file.exists()
