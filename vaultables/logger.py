"""Centralized logging system for Vaultables capturing Python runtime events and 7-Zip outputs."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import List, Optional
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class LogEntry:
    timestamp: str
    level: str  # "INFO" | "WARNING" | "ERROR" | "DEBUG"
    category: str  # "APP" | "7ZIP" | "SECURITY"
    message: str


class _LogEmitter(QObject):
    entry_logged = pyqtSignal(object)  # emits LogEntry


# Global emitter and memory buffer
log_emitter = _LogEmitter()
_log_history: List[LogEntry] = []
MAX_HISTORY = 1500


def get_log_history() -> List[LogEntry]:
    """Retrieve in-memory log history for newly initialized panels."""
    return list(_log_history)


def clear_log_history() -> None:
    """Clear memory log history."""
    _log_history.clear()


class _VaultablesLogHandler(logging.Handler):
    """Custom logging handler bridging standard Python logging to PyQt signals."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            ts = datetime.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            category = getattr(record, "category", "APP")
            msg = self.format(record)
            entry = LogEntry(
                timestamp=ts,
                level=record.levelname,
                category=category,
                message=msg,
            )
            _log_history.append(entry)
            if len(_log_history) > MAX_HISTORY:
                _log_history.pop(0)

            log_emitter.entry_logged.emit(entry)
        except Exception:
            self.handleError(record)


# Configure global logger
_logger = logging.getLogger("Vaultables")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False

_formatter = logging.Formatter("%(message)s")
_handler = _VaultablesLogHandler()
_handler.setFormatter(_formatter)
_logger.addHandler(_handler)

# Also output to stdout/stderr in dev
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
_console_handler.setLevel(logging.INFO)
_logger.addHandler(_console_handler)


def log_info(message: str, category: str = "APP") -> None:
    """Log informational application event."""
    _logger.info(message, extra={"category": category})


def log_warning(message: str, category: str = "APP") -> None:
    """Log application warning."""
    _logger.warning(message, extra={"category": category})


def log_error(message: str, category: str = "APP") -> None:
    """Log application error."""
    _logger.error(message, extra={"category": category})


def log_7zip(cmd_list: List[str], returncode: int, stdout: str = "", stderr: str = "") -> None:
    """
    Log 7-Zip process execution with password masking.
    Captures command arguments, return codes, and relevant output.
    """
    safe_cmd: List[str] = []
    for arg in cmd_list:
        if arg.startswith("-p"):
            safe_cmd.append("-p***")
        else:
            safe_cmd.append(arg)

    cmd_str = " ".join(safe_cmd)
    status = "OK" if returncode in (0, 1) else f"FAILED ({returncode})"
    msg = f"7z [{status}] {cmd_str}"

    clean_stdout = stdout.strip() if stdout else ""
    clean_stderr = stderr.strip() if stderr else ""

    if returncode in (0, 1):
        # Extract meaningful summary lines (e.g. "Files read from disk", "Everything is Ok", "Warnings")
        notable = []
        for line in clean_stdout.splitlines():
            l = line.strip()
            if any(k in l for k in ("Everything is Ok", "Warnings:", "Files read", "Archive size:", "Scanning the drive:")):
                notable.append(l)
        if notable:
            msg += "\n    " + " | ".join(notable)
        _logger.info(msg, extra={"category": "7ZIP"})
    else:
        err = clean_stderr or clean_stdout
        if err:
            first_lines = "\n    ".join(err.splitlines()[:4])
            msg += f"\n    {first_lines}"
        _logger.error(msg, extra={"category": "7ZIP"})
