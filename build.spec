# -*- mode: python ; coding: utf-8 -*-

import os

import certifi
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

logo_dir = "logo images"
datas = [
    ("version.json", "."),
    (certifi.where(), "certifi"),
]
if os.path.isdir(logo_dir):
    datas.append((logo_dir, logo_dir))

icon_path = os.path.join(logo_dir, "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    ["zefsnap.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("webview") + ["certifi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="Zefsnap",
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
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Zefsnap",
)
