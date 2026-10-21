# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import get_package_paths

root = Path(SPECPATH)
# Все импорты autoservice.* статические: PyInstaller обнаруживает их из main.py.
# QtWidgets подключает штатные hooks QtGui/QtCore и платформенный плагин Windows.
qt = Path(get_package_paths('PySide6')[1])
# Python и Qt могут поставлять разные версии runtime. В корне загрузчика
# используем полный согласованный комплект из установленного колеса PySide6.
runtimes = [path for pattern in ('vcruntime140*.dll', 'msvcp140*.dll') for path in qt.glob(pattern)]
a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    binaries=[(str(path), '.') for path in runtimes],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoService',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AutoService',
)
