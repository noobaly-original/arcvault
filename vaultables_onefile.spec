# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None
project_root = Path(os.path.abspath(".")).resolve()

if sys.platform == "darwin":
    icon_file = "vaultables/resources/Vaultables.icns"
elif sys.platform == "win32":
    icon_file = "vaultables/resources/Vaultables.ico"
else:
    icon_file = "vaultables/resources/icon.png"

a = Analysis(
    ["run.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ("vaultables/resources", "vaultables/resources"),
    ],
    hiddenimports=[
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "pygments",
        "pygments.lexers",
        "pygments.formatters",
        "pygments.styles",
        "PIL",
        "PIL.Image",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Vaultables",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

if sys.platform == "darwin" and os.environ.get("BUILD_MACOS_BUNDLE", "0") == "1":
    app = BUNDLE(
        exe,
        name="Vaultables.app",
        icon=icon_file,
        bundle_identifier="com.vaultables.desktop",
        info_plist={
            "CFBundleShortVersionString": "1.5.1",
            "CFBundleVersion": "1.5.1",
            "NSHighResolutionCapable": "True",
            "CFBundleDisplayName": "Vaultables",
            "CFBundleName": "Vaultables",
        },
    )
