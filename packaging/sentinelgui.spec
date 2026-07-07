# -*- mode: python ; coding: utf-8 -*-
# ruff: noqa: F821
# PyInstaller injects Analysis/PYZ/EXE/COLLECT/BUNDLE as globals at runtime, so
# F821 (undefined name) is expected and silenced for this spec file only.
#
# onedir spec for SentinelGUI. Invoke from the repo root:
#     pyinstaller packaging/sentinelgui.spec --noconfirm
# so the relative paths below (../src, hooks, build-icons) resolve against the
# packaging/ dir that contains this spec.
import os
import sys

from PyInstaller.utils.hooks import collect_data_files

# SPECPATH is injected by PyInstaller and points at this file's directory
# (packaging/). Anchor every path on it so the spec works no matter what the
# current working directory is (PyInstaller resolves runtime_hooks/hookspath
# relative to the CWD, but the Analysis scripts relative to SPECPATH).
HERE = SPECPATH
SRC = os.path.join(HERE, "..", "src")
HOOKS = os.path.join(HERE, "hooks")

# Bundle the whole resources/ tree (SVG icons + icon.png master) so the app's
# importlib.resources lookups resolve inside the frozen bundle.
datas = collect_data_files("sentinelgui", includes=["resources/**"])

# Windows needs an .ico; PyInstaller ignores icon= on Linux. Only pass it if the
# generated file exists so the Linux build (where make_icons may or may not have
# run) never hard-fails on a missing icon.
_ico = os.path.join(HERE, "build-icons", "app.ico")
icon_arg = _ico if os.path.exists(_ico) else None

a = Analysis(
    [os.path.join(SRC, "sentinelgui", "__main__.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=[],  # rasterio submodules come from hooks/hook-rasterio.py
    hookspath=[HOOKS],
    runtime_hooks=[os.path.join(HOOKS, "rthook_gdal.py")],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SentinelGUI",
    console=False,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="SentinelGUI",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SentinelGUI.app",
        icon=os.path.join(HERE, "build-icons", "app.icns"),  # built by CI via iconutil
        bundle_identifier="com.sentinelgui.app",
        info_plist={
            "CFBundleName": "SentinelGUI",
            "CFBundleDisplayName": "SentinelGUI",
            "CFBundleIdentifier": "com.sentinelgui.app",
            "CFBundleVersion": "0.1.4",
            "CFBundleShortVersionString": "0.1.4",
            "CFBundleIconFile": "app.icns",
            "NSHighResolutionCapable": True,
        },
    )
