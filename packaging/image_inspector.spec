# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
project_root = os.path.abspath(os.path.join(SPECPATH, ".."))
entrypoint = os.path.join(project_root, "image_inspector", "app.py")

datas = []
binaries = []
hiddenimports = []

# Minimal runtime assets. Avoid collect_all(torch/ultralytics), which is huge and pulls training/tracking extras.
try:
    datas += collect_data_files("ultralytics", include_py_files=False)
except Exception:
    pass

for package in ("torch", "torchvision", "pypylon"):
    try:
        binaries += collect_dynamic_libs(package)
    except Exception:
        pass

hiddenimports += [
    "ultralytics",
    "ultralytics.models",
    "ultralytics.models.yolo",
    "ultralytics.models.yolo.model",
    "ultralytics.nn",
    "ultralytics.nn.tasks",
    "ultralytics.utils",
    "ultralytics.utils.ops",
    "torch",
    "torchvision",
    "pypylon",
    "pypylon.pylon",
    "cv2",
]
hiddenimports += collect_submodules("image_inspector")

excludes = [
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "matplotlib.tests",
    "pandas.tests",
    "numpy.tests",
    "ultralytics.trackers",
    "ultralytics.solutions",
    "ultralytics.hub",
    "ultralytics.data.explorer",
    "ultralytics.engine.exporter",
]


a = Analysis(
    [entrypoint],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="Image Inspector",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Image Inspector",
)

