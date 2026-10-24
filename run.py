#!/usr/bin/env python3
"""Launcher script for ArcVault."""

import sys
from pathlib import Path

# Ensure root directory is on python path
root = Path(__file__).parent.resolve()
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from arc_vault.app import main

if __name__ == "__main__":
    sys.exit(main())
