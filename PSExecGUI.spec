# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: gera exe sem console (so janela da aplicacao)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('config', 'config'),
        ('hosts.example.json', '.'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'ui.tabs.psinfo',
        'ui.tabs.appsearch',
        'utils.psinfo',
        'utils.remote_registry_query',
        'utils.app_catalog',
        'utils.redaction',
        'utils.app_logging',
        'utils.hosts',
        'services.ops',
        'core.models',
        'core.win_cmd',
        'multiprocessing',
        'multiprocessing.spawn',
        'multiprocessing.resource_tracker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pytest'],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

import shutil
from pathlib import Path

_src_config = Path(SPECPATH) / 'config'
_dst_config = Path(DISTPATH) / 'config'
if _src_config.is_dir():
    if _dst_config.exists():
        shutil.rmtree(_dst_config)
    shutil.copytree(_src_config, _dst_config)

_src_hosts_ex = Path(SPECPATH) / 'hosts.example.json'
_dst_hosts_ex = Path(DISTPATH) / 'hosts.example.json'
if _src_hosts_ex.is_file():
    shutil.copy2(_src_hosts_ex, _dst_hosts_ex)
