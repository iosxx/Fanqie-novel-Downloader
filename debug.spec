# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files
from build_config import get_hidden_imports
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

# 收集 fake_useragent 数据文件
fake_useragent_datas = collect_data_files('fake_useragent')

# 分析需要包含的模块
a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[
        # 确保Pillow的二进制文件被包含
    ],
    datas=[
        ('external_updater.py', '.'),
        # ('version.py', '.'),  # Removed version.py file
    ] + fake_useragent_datas,
    hiddenimports=(get_hidden_imports() + ['updater', 'external_updater', 'version']),  # 自动从 requirements.txt 读取依赖，并强制包含本地更新模块
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'pandas',
        'numpy',
        'scipy',
        'bokeh',
        'h5py',
        'lz4',
        'jinja2',
        'cloudpickle',
        'dask',
        'distributed',
        'fsspec',
        'pyarrow',
        'pytz'
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
    name='TomatoNovelDownloader-debug',
    debug=True,  # 启用debug模式
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX压缩以避免Windows构建问题
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 启用控制台输出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
) 