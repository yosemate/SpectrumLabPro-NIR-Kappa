# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['supervisor_entry.py'],
    pathex=[],
    binaries=[],
    datas=[('banco_materiais.json', '.'), ('assets', 'assets'), ('experiments/chemometrics', 'experiments/chemometrics')],
    hiddenimports=['acquisition_quality', 'experimental_chemometrics'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['sklearn'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpectrumLabPro_4_17_6',
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
    name='SpectrumLabPro_4_17_6',
)
