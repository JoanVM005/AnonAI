# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


SPEC_DIR = Path(SPECPATH).resolve()
APPLICATION_ROOT = SPEC_DIR.parent
PROJECT_ROOT = APPLICATION_ROOT.parent
MODEL_WEIGHTS_DIR = PROJECT_ROOT / "Model" / "runs" / "radiograph_phi_detection" / "augmented" / "weights"
BEST_MODEL = MODEL_WEIGHTS_DIR / "best.pt"

datas = [
    (str(APPLICATION_ROOT / "resources"), "resources"),
    (str(APPLICATION_ROOT / "config"), "config"),
]

if BEST_MODEL.exists():
    datas.append((str(BEST_MODEL), "Model/runs/radiograph_phi_detection/augmented/weights"))

for package_name in ("easyocr", "ultralytics"):
    datas += collect_data_files(package_name)

hiddenimports = []
for package_name in ("easyocr", "ultralytics", "pydicom", "pylibjpeg", "cv2"):
    hiddenimports += collect_submodules(package_name)


a = Analysis(
    [str(APPLICATION_ROOT / "src" / "app.py")],
    pathex=[str(APPLICATION_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnonRad AI",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AnonRad AI",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AnonRad AI.app",
        icon=None,
        bundle_identifier="ai.anonrad.desktop",
        info_plist={
            "CFBundleName": "AnonRad AI",
            "CFBundleDisplayName": "AnonRad AI",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": "True",
        },
    )
