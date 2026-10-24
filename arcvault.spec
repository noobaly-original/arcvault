# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None
project_root = Path(os.path.abspath(".")).resolve()

if sys.platform == "darwin":
    icon_file = "arc_vault/resources/ArcVault.icns"
elif sys.platform == "win32":
    icon_file = "arc_vault/resources/ArcVault.ico"
else:
    icon_file = "arc_vault/resources/icon.png"

a = Analysis(
    ["run.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ("arc_vault/resources", "arc_vault/resources"),
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
    [],
    exclude_binaries=True,
    name="ArcVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ArcVault",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ArcVault.app",
        icon=icon_file,
        bundle_identifier="com.arcvault.desktop",
        info_plist={
            "CFBundleShortVersionString": "2.0.0",
            "CFBundleVersion": "2.0.0",
            "NSHighResolutionCapable": "True",
            "CFBundleDisplayName": "ArcVault",
            "CFBundleName": "ArcVault",
        },
    )
