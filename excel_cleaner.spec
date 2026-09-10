# -*- mode: python ; coding: utf-8 -*-
# excel_cleaner.spec — fuente de verdad del build (skill: pyinstaller-packaging-workflow)
# Build repetible:  python -m PyInstaller excel_cleaner.spec --clean --noconfirm
# Modo: onefile + noconsole (GUI comercial, sin terminal detrás, sin Python en el cliente)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Icono comercial: recurso estático cargado en runtime por main.py
        # vía sys._MEIPASS (regla 3 de la skill pyinstaller-packaging-workflow).
        ('assets/icono.ico', 'assets'),
    ],
    hiddenimports=[
        # Regla 1 de la skill: dependencias ocultas verificadas ANTES de compilar.
        # pandas importa openpyxl dinámicamente (motor XLSX) → PyInstaller no lo ve solo.
        'pandas',
        'numpy',
        'openpyxl',
        'openpyxl.cell._writer',
        # Canal de red único hacia Ollama local.
        'requests',
        # Soporte de zonas horarias de pandas en Windows (usado por generate_audit_report).
        'tzdata',
    ],
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
    a.binaries,
    a.datas,
    [],
    name='ExcelCleaner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Regla comercial de la skill: UPX desactivado (falsos positivos de antivirus).
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Regla 2 de la skill: GUI sin consola en producción.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icono comercial del ejecutable (visible en Explorer y barra de tareas).
    icon='assets\\icono.ico',
)
