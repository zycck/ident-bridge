# -*- coding: utf-8 -*-
# PyInstaller spec for iDentBridge — single-file windowed .exe
# Usage: pyinstaller build.spec

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("resources/theme.qss",  "resources"),
        ("resources/icon.ico",   "resources"),
        ("resources/check.svg",  "resources"),
        ("resources/icons",      "resources/icons"),
        ("resources/fonts",      "resources/fonts"),
    ],
    hiddenimports=[
        "pyodbc",
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "PySide6.QtSvg",
        "encodings.utf_8",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "QtWebEngine",
        "QtQml",
        "QtQuick",
        "Qt3D",
        "QtMultimedia",
        "QtCharts",
        "QtBluetooth",
        "QtNfc",
        "QtLocation",
        "QtPositioning",
        "QtSensors",
        "QtSerialPort",
        "test",
        "unittest",
        "distutils",
        "setuptools",
        "doctest",
        "pydoc",
        "tkinter",
        "xmlrpc",
        "ftplib",
        "http.server",
        "turtle",
    ],
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
    name="iDentSync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,          # strip not supported on Windows
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # windowed — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/icon.ico",
    onefile=True,
)
