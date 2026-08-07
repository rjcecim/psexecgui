# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: gera exe sem console (só janela da aplicação)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('config', 'config'),  # embutido no exe (+ cópia em dist/ ao final)
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'ui.tabs.psinfo',
        'ui.tabs.appsearch',
        'utils.psinfo',
        'utils.app_catalog',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PSExecGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # sem console — só a janela da aplicação
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

# Copia config/ para dist/ ao lado do .exe (editável em runtime)
import shutil
from pathlib import Path

_src_config = Path(SPECPATH) / 'config'
_dst_config = Path(DISTPATH) / 'config'
if _src_config.is_dir():
    if _dst_config.exists():
        shutil.rmtree(_dst_config)
    shutil.copytree(_src_config, _dst_config)
