"""Data models for ArcVault archives and vault structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class FileCategory(str, Enum):
    ENTRY_POINT = "entry_point"
    FOLDER = "folder"
    IMAGE = "image"
    TEXT = "text"
    CODE = "code"
    DOCUMENT = "document"
    EXECUTABLE_WINDOWS = "executable_windows"
    EXECUTABLE_MACOS = "executable_macos"
    EXECUTABLE_UNIX = "executable_unix"
    ARCHIVE = "archive"
    AUDIO = "audio"
    VIDEO = "video"
    KEY_CERT = "key_cert"
    GENERIC = "generic"


@dataclass
class ArchiveItem:
    """Represents a file or directory inside an entry-point archive."""

    name: str
    path: str  # Path inside archive, e.g. "family/photo.jpg", or "" for root
    is_dir: bool = False
    size: int = 0
    packed_size: int = 0
    modified: Optional[str] = None
    attributes: str = ""
    crc: Optional[str] = None
    encrypted: bool = True
    entry_point_name: str = ""  # The .7z base name (e.g. "photos")
    category: FileCategory = FileCategory.GENERIC

    def __post_init__(self) -> None:
        if not self.category or self.category == FileCategory.GENERIC:
            self.category = classify_file(self.name, self.is_dir)


@dataclass
class EntryPoint:
    """Represents a top-level .7z file in the vault root."""

    name: str  # e.g. "photos"
    archive_file: Path  # path to /vault/root/photos.7z
    size_on_disk: int = 0
    item_count: int = 0
    is_loaded: bool = False
    children: List[ArchiveItem] = field(default_factory=list)


@dataclass
class VaultMetadata:
    """Metadata read from the vault marker file (.arcvault)."""

    name: str
    vault_id: str
    version: str = "1.0"
    created_at: str = ""
    encryption: str = "AES-256"


def classify_file(name: str, is_dir: bool = False) -> FileCategory:
    """Classify a file name into a category for icons and preview handling."""
    if is_dir:
        return FileCategory.FOLDER

    lower = name.lower()
    suffix = Path(lower).suffix

    # Executables - special Windows
    if suffix in {".exe", ".bat", ".cmd", ".msi", ".com", ".scr", ".ps1", ".vbs"}:
        return FileCategory.EXECUTABLE_WINDOWS

    # Executables - special macOS
    if suffix in {".app", ".dmg", ".pkg", ".dylib", ".command"}:
        return FileCategory.EXECUTABLE_MACOS

    # Executables - Unix / Linux / General
    if suffix in {".sh", ".bin", ".run", ".elf", ".so", ".out"}:
        return FileCategory.EXECUTABLE_UNIX

    # Images
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".ico", ".tiff", ".tif", ".avif"}:
        return FileCategory.IMAGE

    # Code / Scripts
    if suffix in {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss", ".json",
        ".xml", ".yaml", ".yml", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java",
        ".kt", ".swift", ".php", ".rb", ".lua", ".sql", ".toml", ".ini", ".conf", ".env",
        ".dockerfile", ".makefile"
    } or lower in {"dockerfile", "makefile", "gemfile"}:
        return FileCategory.CODE

    # Documents & Text
    if suffix in {".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".rtf", ".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods"}:
        return FileCategory.DOCUMENT if suffix in {".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods"} else FileCategory.TEXT

    # Archives
    if suffix in {".7z", ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".zst", ".tgz"}:
        return FileCategory.ARCHIVE

    # Audio
    if suffix in {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma", ".opus"}:
        return FileCategory.AUDIO

    # Video
    if suffix in {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv", ".m4v"}:
        return FileCategory.VIDEO

    # Keys / Certs
    if suffix in {".pem", ".key", ".crt", ".cer", ".p12", ".pfx", ".pub", ".gpg", ".asc"}:
        return FileCategory.KEY_CERT

    return FileCategory.GENERIC
