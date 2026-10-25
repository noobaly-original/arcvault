"""Vaultables - Fast, lightweight, encrypted archive vault explorer."""

import os

# Prevent macOS from generating ._ AppleDouble sidecar files during copy operations on network/cloud drives
os.environ["COPYFILE_DISABLE"] = "1"

__version__ = "2.1.5"
__app_name__ = "Vaultables"
