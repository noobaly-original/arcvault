"""Update checker querying GitHub releases for Vaultables."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from vaultables import __version__
from vaultables.logger import log_error, log_info


GITHUB_REPO: str = "noobaly-original/vaultables"
GITHUB_RELEASES_URL: str = f"https://github.com/{GITHUB_REPO}/releases"
GITHUB_API_LATEST: str = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(version_str: str) -> Tuple[int, ...]:
    """
    Parse a version string (e.g. 'v2.1.7', '2.1.7', 'v2.2.0-beta1') into a comparable tuple of ints.
    Leading 'v'/'V' is stripped, prerelease / build metadata after '-' or '+' is stripped,
    and numeric segments are parsed sequentially.
    """
    clean = version_str.strip().lstrip("vV")
    for delimiter in ("-", "+", "_"):
        if delimiter in clean:
            clean = clean.split(delimiter, 1)[0]
    parts = []
    for piece in clean.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits:
            parts.append(int(digits))
        else:
            break
    return tuple(parts) if parts else (0,)


def is_newer_version(candidate_version: str, current_version: str) -> bool:
    """Return True if candidate_version is strictly newer than current_version."""
    return parse_version(candidate_version) > parse_version(current_version)


@dataclass
class UpdateInfo:
    """Detailed metadata about available application updates."""

    available: bool
    current_version: str
    latest_version: str
    release_name: str
    release_url: str
    release_notes: str
    published_at: str
    error: Optional[str] = None


def check_for_updates_sync(
    current_version: str = __version__,
    timeout: float = 6.0,
    api_url: str = GITHUB_API_LATEST,
) -> UpdateInfo:
    """
    Query GitHub API synchronously for the latest release and compare with current app version.
    Returns an UpdateInfo dataclass containing check results.
    """
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": f"Vaultables-App/{current_version}",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_data = resp.read().decode("utf-8")
            data = json.loads(raw_data)

        tag_name = data.get("tag_name", "").strip()
        release_name = data.get("name", "").strip() or tag_name
        release_url = data.get("html_url", "").strip() or GITHUB_RELEASES_URL
        release_notes = data.get("body", "").strip()
        published_at = data.get("published_at", "").strip()

        latest_clean = tag_name.lstrip("vV")
        has_update = is_newer_version(tag_name, current_version)

        if has_update:
            log_info(f"Update available: {tag_name} (current: {current_version})", category="APP")
        else:
            log_info(f"Vaultables is up to date (current: {current_version}, latest: {tag_name})", category="APP")

        return UpdateInfo(
            available=has_update,
            current_version=current_version,
            latest_version=latest_clean,
            release_name=release_name,
            release_url=release_url,
            release_notes=release_notes,
            published_at=published_at,
            error=None,
        )
    except urllib.error.HTTPError as e:
        err_msg = f"HTTP {e.code}: {e.reason}"
        log_error(f"Update check failed: {err_msg}")
        return UpdateInfo(
            available=False,
            current_version=current_version,
            latest_version="",
            release_name="",
            release_url=GITHUB_RELEASES_URL,
            release_notes="",
            published_at="",
            error=err_msg,
        )
    except Exception as e:
        err_msg = str(e)
        log_error(f"Update check network error: {err_msg}")
        return UpdateInfo(
            available=False,
            current_version=current_version,
            latest_version="",
            release_name="",
            release_url=GITHUB_RELEASES_URL,
            release_notes="",
            published_at="",
            error=err_msg,
        )
