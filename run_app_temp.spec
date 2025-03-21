# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files


block_cipher = None

hiddenimports = collect_submodules('streamlit') + collect_submodules('PIL') + collect_submodules('captcha') + ["pyexpat"]
datas = collect_data_files('streamlit') + collect_data_files('captcha')
datas += [("settings.json", ".")]

datas += [
    ("./myenv/Lib/site-packages/altair/vegalite/v5/schema/vega-lite-schema.json", "./altair/vegalite/v5/schema/"),
    ("./myenv/Lib/site-packages/streamlit/static", "./streamlit/static"),
    ("./myenv/Lib/site-packages/streamlit/runtime", "./streamlit/runtime"),
    ("./myenv/Lib/site-packages/pyopenms", "./pyopenms/"),
    ("./myenv/Lib/site-packages/captcha", "./captcha/"),
    ("./myenv/Lib/site-packages/pyarrow", "./pyarrow/"),
]

a = Analysis(
    ['run_app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['./hooks'],
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
    name='run_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
