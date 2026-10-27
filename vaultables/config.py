"""Configuration management for Vaultables."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class AppConfig:
    """Manages persistent application settings, window state, and known vault locations."""

    CONFIG_DIR = Path.home() / ".vaultables"
    LEGACY_CONFIG_DIR = Path.home() / ".vaultables"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    def __init__(self, config_file: Optional[Path] = None) -> None:
        self.config_file: Path = Path(config_file) if config_file else self.CONFIG_FILE
        self.known_vaults: List[Dict[str, Any]] = []
        self.theme: str = "dark"  # "dark" | "light" | "system"
        self.sevenzip_override_path: Optional[str] = None
        self.preview_max_text_size_kb: int = 4096
        self.last_selected_vault_path: Optional[str] = None
        self.check_updates_on_startup: bool = True

        # Window state persistence
        self.window_geometry: Optional[str] = None
        self.window_maximized: bool = False
        self.window_width: int = 1180
        self.window_height: int = 740
        self.window_x: Optional[int] = None
        self.window_y: Optional[int] = None
        self.splitter_state: Optional[str] = None
        self.file_list_size_index: int = 4
        self.file_column_widths: Optional[Dict[str, int]] = None

        self.load()

    def load(self) -> None:
        """Load configuration from disk."""
        if not self.config_file.exists():
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.known_vaults = data.get("known_vaults", [])
            self.theme = data.get("theme", "dark")
            self.sevenzip_override_path = data.get("sevenzip_override_path")
            self.preview_max_text_size_kb = data.get("preview_max_text_size_kb", 4096)
            self.last_selected_vault_path = data.get("last_selected_vault_path")
            self.check_updates_on_startup = bool(data.get("check_updates_on_startup", True))

            # Window state
            self.window_geometry = data.get("window_geometry")
            self.window_maximized = bool(data.get("window_maximized", False))
            self.window_width = int(data.get("window_width", 1180))
            self.window_height = int(data.get("window_height", 740))
            self.window_x = data.get("window_x")
            self.window_y = data.get("window_y")
            self.splitter_state = data.get("splitter_state")
            self.file_list_size_index = max(0, min(9, int(data.get("file_list_size_index", 4))))
            self.file_column_widths = data.get("file_column_widths")
        except Exception:
            # Fall back to defaults if corrupted
            pass

    def save(self) -> None:
        """Save configuration to disk."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "known_vaults": self.known_vaults,
                "theme": self.theme,
                "sevenzip_override_path": self.sevenzip_override_path,
                "preview_max_text_size_kb": self.preview_max_text_size_kb,
                "last_selected_vault_path": self.last_selected_vault_path,
                "check_updates_on_startup": self.check_updates_on_startup,
                "window_geometry": self.window_geometry,
                "window_maximized": self.window_maximized,
                "window_width": self.window_width,
                "window_height": self.window_height,
                "window_x": self.window_x,
                "window_y": self.window_y,
                "splitter_state": self.splitter_state,
                "file_list_size_index": self.file_list_size_index,
                "file_column_widths": self.file_column_widths,
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Vaultables] Failed to save config: {e}")

    def is_check_updates_enabled(self) -> bool:
        """Return whether automatic update checking on startup is enabled."""
        return getattr(self, "check_updates_on_startup", True)

    def set_check_updates_enabled(self, enabled: bool) -> None:
        """Persist automatic update checking preference."""
        self.check_updates_on_startup = bool(enabled)
        self.save()

    def add_or_update_vault(self, vault_path: str, name: str) -> None:
        """Add or update a vault in known vaults list."""
        norm_path = str(Path(vault_path).resolve())
        # Check if already exists
        for item in self.known_vaults:
            if str(Path(item.get("path", "")).resolve()) == norm_path:
                item["name"] = name
                item["path"] = norm_path
                self.last_selected_vault_path = norm_path
                self.save()
                return

        # Insert new
        self.known_vaults.insert(
            0,
            {
                "path": norm_path,
                "name": name,
            },
        )
        self.last_selected_vault_path = norm_path
        self.save()

    def remove_vault(self, vault_path: str) -> None:
        """Remove a vault from known vaults list."""
        norm_path = str(Path(vault_path).resolve())
        self.known_vaults = [
            v for v in self.known_vaults
            if str(Path(v.get("path", "")).resolve()) != norm_path
        ]
        if self.last_selected_vault_path == norm_path:
            self.last_selected_vault_path = (
                self.known_vaults[0]["path"] if self.known_vaults else None
            )
        self.save()

    def is_password_saved(self, vault_path: str) -> bool:
        """Check if password storage is enabled for this vault in configuration."""
        norm_path = str(Path(vault_path).resolve())
        for item in self.known_vaults:
            if str(Path(item.get("path", "")).resolve()) == norm_path:
                return bool(item.get("store_password", False))
        return False

    def set_password_saved(self, vault_path: str, saved: bool) -> None:
        """Set password storage preference for this vault."""
        norm_path = str(Path(vault_path).resolve())
        for item in self.known_vaults:
            if str(Path(item.get("path", "")).resolve()) == norm_path:
                item["store_password"] = bool(saved)
                self.save()
                return

        self.known_vaults.insert(
            0,
            {
                "path": norm_path,
                "name": Path(vault_path).name,
                "store_password": bool(saved),
            },
        )
        self.save()
