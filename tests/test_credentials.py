"""Unit tests for OS-native credential management in Vaultables."""

import os
import unittest
from pathlib import Path

from vaultables.config import AppConfig
from vaultables.core.credentials import (
    CREDENTIAL_PREFIX,
    SERVICE_NAME,
    _MEM_FALLBACK_STORE,
    delete_vault_password,
    format_credential,
    is_vault_password_stored,
    parse_credential,
    retrieve_vault_password,
    store_vault_password,
)


class TestCredentials(unittest.TestCase):
    """Test formatting, storing, parsing, and deleting vault credentials."""

    def setUp(self) -> None:
        self.test_vault_path = Path("/tmp/vaultables_test_credentials_vault")
        self.test_vault_id = "test-vault-id-abc123xyz"
        # Ensure clean state
        delete_vault_password(self.test_vault_path, vault_id=self.test_vault_id)

    def tearDown(self) -> None:
        delete_vault_password(self.test_vault_path, vault_id=self.test_vault_id)

    def test_format_and_parse_credential(self) -> None:
        """Verify strict credential formatting ('vaultables:{main_password}') and parsing."""
        raw_pwd = "MySuperSecretPassword!#123"
        formatted = format_credential(raw_pwd)
        self.assertEqual(formatted, f"{CREDENTIAL_PREFIX}{raw_pwd}")
        self.assertEqual(formatted, f"vaultables:{raw_pwd}")

        # Extracting password extracts ONLY {main_password}
        extracted = parse_credential(formatted)
        self.assertEqual(extracted, raw_pwd)

        # Passwords containing colons should be correctly preserved
        complex_pwd = "pass:with:multiple:colons:!@#$%^&*()"
        formatted_complex = format_credential(complex_pwd)
        self.assertEqual(formatted_complex, f"vaultables:{complex_pwd}")
        self.assertEqual(parse_credential(formatted_complex), complex_pwd)

        # None and empty handling
        self.assertIsNone(parse_credential(None))
        self.assertIsNone(parse_credential(""))

        # If stored without prefix (edge case fallback), return as-is
        self.assertEqual(parse_credential("raw_without_prefix"), "raw_without_prefix")

    def test_store_retrieve_delete_flow(self) -> None:
        """Verify storing, querying, and deleting a vault password."""
        test_password = "CorrectVaultPassword99!"

        # Initially not stored
        self.assertFalse(is_vault_password_stored(self.test_vault_path, vault_id=self.test_vault_id))
        self.assertIsNone(retrieve_vault_password(self.test_vault_path, vault_id=self.test_vault_id))

        # Store password
        success = store_vault_password(self.test_vault_path, test_password, vault_id=self.test_vault_id)
        self.assertTrue(success)

        # Verify stored and retrieved (only main password, without prefix)
        self.assertTrue(is_vault_password_stored(self.test_vault_path, vault_id=self.test_vault_id))
        retrieved = retrieve_vault_password(self.test_vault_path, vault_id=self.test_vault_id)
        self.assertEqual(retrieved, test_password)

        # Also retrievable by path alone
        retrieved_by_path = retrieve_vault_password(self.test_vault_path)
        self.assertEqual(retrieved_by_path, test_password)

        # Delete password
        del_success = delete_vault_password(self.test_vault_path, vault_id=self.test_vault_id)
        self.assertTrue(del_success)

        # Verify no longer stored
        self.assertFalse(is_vault_password_stored(self.test_vault_path, vault_id=self.test_vault_id))
        self.assertIsNone(retrieve_vault_password(self.test_vault_path, vault_id=self.test_vault_id))

    def test_delete_non_existent_key_does_not_raise(self) -> None:
        """Deleting a non-existent credential should gracefully succeed without throwing."""
        res = delete_vault_password(Path("/non/existent/vault/path/random123"), vault_id="non-existent-id")
        self.assertTrue(res)

    def test_store_empty_password_returns_false(self) -> None:
        """Attempting to store an empty password should fail gracefully."""
        self.assertFalse(store_vault_password(self.test_vault_path, ""))

    def test_app_config_password_saved_persistence(self) -> None:
        """Verify AppConfig persists store_password boolean for known vaults."""
        cfg_path = Path("/tmp/vaultables_test_cfg.json")
        if cfg_path.exists():
            cfg_path.unlink()

        try:
            config = AppConfig(config_file=cfg_path)
            vpath = "/path/to/my/vault"

            self.assertFalse(config.is_password_saved(vpath))

            config.set_password_saved(vpath, True)
            self.assertTrue(config.is_password_saved(vpath))

            # Reload config to ensure disk persistence
            config_reloaded = AppConfig(config_file=cfg_path)
            self.assertTrue(config_reloaded.is_password_saved(vpath))

            # Turn off
            config_reloaded.set_password_saved(vpath, False)
            self.assertFalse(config_reloaded.is_password_saved(vpath))
        finally:
            if cfg_path.exists():
                cfg_path.unlink()


if __name__ == "__main__":
    unittest.main()
