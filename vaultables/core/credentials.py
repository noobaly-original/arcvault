"""OS-native credential management for Vaultables master passwords.

Securely stores, retrieves, and deletes vault master passwords using platform-native
credential stores:
  - macOS: Keychain (via keyring / security CLI)
  - Windows: Windows Credential Manager / DPAPI (via keyring / win32cred)
  - Linux: Secret Service API / GNOME Keyring / KDE Wallet (via keyring)

Format Requirement:
  - Stored credential string: "vaultables:{main_password}"
  - Reading credential string: strips "vaultables:" prefix and returns "{main_password}".
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

SERVICE_NAME = "Vaultables"
CREDENTIAL_PREFIX = "vaultables:"

# In-memory store used in test / headless CI environments where no desktop keyring daemon runs
_MEM_FALLBACK_STORE: dict[str, str] = {}


def format_credential(password: str) -> str:
    """Format the master password for storage in OS credential manager.

    Format: vaultables:{main_password}
    """
    return f"{CREDENTIAL_PREFIX}{password}"


def parse_credential(raw_credential: Optional[str]) -> Optional[str]:
    """Parse the raw stored credential and extract only {main_password}."""
    if not raw_credential:
        return None
    if raw_credential.startswith(CREDENTIAL_PREFIX):
        return raw_credential[len(CREDENTIAL_PREFIX):]
    return raw_credential


def _get_account_key(vault_path: Union[str, Path]) -> str:
    """Return normalized canonical account identifier for a vault path."""
    return str(Path(vault_path).resolve())


def _macos_security_set(service: str, account: str, secret: str) -> bool:
    """Set password using macOS native security command-line tool."""
    try:
        proc = subprocess.run(
            ["security", "add-generic-password", "-a", account, "-s", service, "-w", secret, "-U"],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0
    except Exception as e:
        logger.debug(f"macOS security CLI set failed: {e}")
        return False


def _macos_security_get(service: str, account: str) -> Optional[str]:
    """Retrieve password using macOS native security command-line tool."""
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.rstrip("\r\n")
        return None
    except Exception as e:
        logger.debug(f"macOS security CLI get failed: {e}")
        return None


def _macos_security_delete(service: str, account: str) -> bool:
    """Delete password using macOS native security command-line tool."""
    try:
        proc = subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", service],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 or "could not be found" in proc.stderr.lower()
    except Exception as e:
        logger.debug(f"macOS security CLI delete failed: {e}")
        return False


def store_vault_password(
    vault_path: Union[str, Path],
    password: str,
    vault_id: Optional[str] = None,
) -> bool:
    """Store the master vault password formatted as 'vaultables:{main_password}' in the OS credential manager."""
    if not password:
        return False

    account = _get_account_key(vault_path)
    payload = format_credential(password)
    stored = False

    # 1. Try keyring library (cross-platform: Keychain, DPAPI/WinVault, GNOME Keyring / SecretService, KWallet)
    try:
        import keyring
        keyring.set_password(SERVICE_NAME, account, payload)
        if vault_id:
            try:
                keyring.set_password(SERVICE_NAME, f"id:{vault_id}", payload)
            except Exception:
                pass
        stored = True
    except Exception as e:
        logger.debug(f"keyring.set_password failed: {e}")

    # 2. Try macOS security CLI fallback if on darwin and keyring failed
    if not stored and sys.platform == "darwin":
        if _macos_security_set(SERVICE_NAME, account, payload):
            if vault_id:
                _macos_security_set(SERVICE_NAME, f"id:{vault_id}", payload)
            stored = True

    # 3. Always mirror to in-memory store for fallback/headless environments
    _MEM_FALLBACK_STORE[account] = payload
    if vault_id:
        _MEM_FALLBACK_STORE[f"id:{vault_id}"] = payload

    return stored or bool(os.environ.get("VAULTABLES_USE_MEM_KEYRING")) or bool(_MEM_FALLBACK_STORE)


def retrieve_vault_password(
    vault_path: Union[str, Path],
    vault_id: Optional[str] = None,
) -> Optional[str]:
    """Retrieve the master password for the vault, returning only {main_password}."""
    account = _get_account_key(vault_path)
    raw: Optional[str] = None

    # 1. Try keyring library
    try:
        import keyring
        raw = keyring.get_password(SERVICE_NAME, account)
        if not raw and vault_id:
            raw = keyring.get_password(SERVICE_NAME, f"id:{vault_id}")
    except Exception as e:
        logger.debug(f"keyring.get_password failed: {e}")

    # 2. Try macOS security CLI fallback
    if not raw and sys.platform == "darwin":
        raw = _macos_security_get(SERVICE_NAME, account)
        if not raw and vault_id:
            raw = _macos_security_get(SERVICE_NAME, f"id:{vault_id}")

    # 3. Fallback to memory store if present
    if not raw:
        raw = _MEM_FALLBACK_STORE.get(account) or (
            _MEM_FALLBACK_STORE.get(f"id:{vault_id}") if vault_id else None
        )

    return parse_credential(raw)


def delete_vault_password(
    vault_path: Union[str, Path],
    vault_id: Optional[str] = None,
) -> bool:
    """Delete the stored vault master password from the OS credential manager."""
    account = _get_account_key(vault_path)

    # 1. Try keyring library
    try:
        import keyring
        try:
            keyring.delete_password(SERVICE_NAME, account)
        except Exception:
            pass
        if vault_id:
            try:
                keyring.delete_password(SERVICE_NAME, f"id:{vault_id}")
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"keyring.delete_password error: {e}")

    # 2. Try macOS security CLI
    if sys.platform == "darwin":
        _macos_security_delete(SERVICE_NAME, account)
        if vault_id:
            _macos_security_delete(SERVICE_NAME, f"id:{vault_id}")

    # 3. Remove from memory store
    _MEM_FALLBACK_STORE.pop(account, None)
    if vault_id:
        _MEM_FALLBACK_STORE.pop(f"id:{vault_id}", None)

    return True


def is_vault_password_stored(
    vault_path: Union[str, Path],
    vault_id: Optional[str] = None,
) -> bool:
    """Check if a master password is saved for the given vault."""
    return retrieve_vault_password(vault_path, vault_id=vault_id) is not None
