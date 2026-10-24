"""Configuration management for ArcVault."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class AppConfig:
    """Manages persistent application settings and known vault locations."""

    CONFIG_DIR = Path.home() / ".arcvault"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    def __init__(self) -> None:
        self.known_vaults: List[Dict[str, Any]] = []
        self.theme: str = "dark"  # "dark" | "light" | "system"
        self.sevenzip_override_path: Optional[str] = None
        self.preview_max_text_size_kb: int = 4096
        self.last_selected_vault_path: Optional[str] = None
        self.load()

    def load(self) -> None:
        """Load configuration from disk."""
        if not self.CONFIG_FILE.exists():
            return

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.known_vaults = data.get("known_vaults", [])
            self.theme = data.get("theme", "dark")
            self.sevenzip_override_path = data.get("sevenzip_override_path")
            self.preview_max_text_size_kb = data.get("preview_max_text_size_kb", 4096)
            self.last_selected_vault_path = data.get("last_selected_vault_path")
            # Filter out non-existent folders from known_vaults gracefully
            # (or keep them but flag them)
        except Exception:
            # Fall back to defaults if corrupted
            pass

    def save(self) -> None:
        """Save configuration to disk."""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "known_vaults": self.known_vaults,
                "theme": self.theme,
                "sevenzip_override_path": self.sevenzip_override_path,
                "preview_max_text_size_kb": self.preview_max_text_size_kb,
                "last_selected_vault_path": self.last_selected_vault_path,
            }
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ArcVault] Failed to save config: {e}")

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
