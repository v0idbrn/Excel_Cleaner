---
name: pyinstaller-packaging-workflow
description: Flujo de trabajo estricto para empaquetar aplicaciones Python (con Pandas y Tkinter) en ejecutables standalone usando PyInstaller. Aplicar antes de generar cualquier .exe de Excel Cleaner.
license: MIT
metadata:
  category: packaging
  project: excel-cleaner
  stack: pandas-tkinter
---

# PyInstaller Packaging Workflow — Excel Cleaner

Objetivo: producir un ejecutable **standalone y comercializable** que funcione en la
máquina del cliente **sin entorno Python instalado**, de forma **repetible** y
verificada. Un build que no se probó es un build que no existe.

## Stack real de este proyecto (verificar contra `requirements.txt` antes de build)

- `pandas` (3.0.x) + `numpy` (2.x) — los dos mayores productores de fallos de empaquetado.
- `openpyxl` — motor XLSX; PyInstaller NO lo detecta solo (pandas lo importa dinámicamente).
- `requests` — único canal de red (Ollama local). Sin SDKs de IA locales → sin binarios ML.
- `tkinter` — GUI (viene con Python; requiere el hook estándar de PyInstaller).
- Objetivo de entorno: Windows 10, Python 3.14.

## Reglas críticas de empaquetado (no negociables)

### 1. Dependencias ocultas — verificar hooks ANTES de compilar

PyInstaller no sigue imports dinámicos. Para este stack son obligatorios:

```text
--hidden-import pandas
--hidden-import numpy
--hidden-import openpyxl
--collect-submodules openpyxl
```

- Si aparece `ModuleNotFoundError` al ejecutar el .exe, es un hidden-import faltante:
  agregarlo al `.spec` y recompilar (no intentar "arreglos" en la máquina cliente).
- Prohibido compensar con `--collect-all pandas` por defecto: infla el bundle;
  usar solo como último recurso documentado.
- Cualquier dependencia nueva en `requirements.txt` exige revisar esta lista.

### 2. Modo ventana — GUI sin terminal detrás

```text
--noconsole        (equivalente: --windowed, o console=False en el .spec)
```

- Producción SIEMPRE con `console=False`. Una GUI comercial no abre una consola negra.
- El debugging del .exe se hace en un build temporal `--console` NUNCA distribuido;
  los errores de GUI deben capturarse con el manejador global ya existente.

### 3. Gestión de assets — `--add-data` + `sys._MEIPASS`

```text
--add-data "assets;assets"        (Windows usa ';' ; Linux/macOS ':')
```

- Todo recurso estático (icono, templates, reportes base) debe resolverse en runtime:

```python
import sys
from pathlib import Path

def resource_path(relative: str) -> Path:
    """Ruta absoluta al recurso, compatible con PyInstaller (sys._MEIPASS) y con dev."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / relative if base else Path(__file__).resolve().parent / relative
```

- Prohibido abrir assets con rutas relativas al CWD: en modo `--onefile` el CWD no es
  el directorio del ejecutable.
- El icono va con `--icon assets/icono.ico` y también con `--add-data` si se usa en runtime.

### 4. Entorno limpio — el build se hace desde un `.spec`, nunca con comandos kilométricos

- La fuente de verdad del build es **`excel_cleaner.spec`** versionado en el repo.
  Se genera UNA vez (`pyi-makespec`) y luego se edita a mano:

```python
# excel_cleaner.spec (esqueleto mínimo esperado)
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['pandas', 'numpy', 'openpyxl'],
    hookspath=[],
    runtime_hooks=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name='ExcelCleaner',
    console=False,
    icon='assets\\icono.ico',
    upx=False,
)
```

- Build único y repetible: `pyinstaller excel_cleaner.spec --clean --noconfirm`
- Prohibido: flags dispersos en la terminal, builds "a mano" no reproducibles, o editar
  el spec generado dentro de `build/` (es basura temporal).
- `upx=False` por defecto: la compresión UPX dispara falsos positivos de antivirus,
  inaceptable para un producto comercial.

## Procedimiento estándar (orden estricto)

1. **Congelar entorno**: `pip freeze > build-frozen.txt` y verificar contra `requirements.txt`.
2. **Suite verde ANTES de empaquetar**: unittest discovery + tests por patrón función
   (un .exe no arregla bugs; solo los congela).
3. **Espec limpio**: crear/actualizar `excel_cleaner.spec` según las reglas 1–4.
4. **Build**: `pyinstaller excel_cleaner.spec --clean --noconfirm` desde la raíz del proyecto.
5. **Inspección del log**: buscar `WARNING: Hidden import ... not found` y módulos faltantes.
   Cada warning debe resolverse en el spec, no ignorarse.
6. **Prueba del ejecutable en máquina LIMPIA** (o VM sin Python): abrir, cargar CSV/XLSX,
   analizar, limpiar, validar, exportar y verificar que se genera `*_audit_report.txt`.
   Sin Python en PATH: así se valida la promesa "standalone".
7. **Smoke test de producción**: confirmar que NO se abre consola y que el icono aparece.
8. **Registrar el resultado** (versión, warnings pendientes, tamaño del bundle) en el
   informe de la fase. Máximo 3 ciclos de corrección por problema de build; si no
   resuelve, documentar el error exacto y el entorno.

## Modo de distribución recomendado

- `--onedir` para desarrollo/QA (arranque rápido, fácil de diagnosticar).
- `--onefile` para distribución final (un solo `ExcelCleaner.exe`), aceptando el arranque
  más lento por auto-extracción. Decidir por fase y documentarlo en el spec.

## Riesgos conocidos (comerciales)

- **Falsos positivos de antivirus**: minimizar con `upx=False`; si persisten, firmar el
  ejecutable (code signing) antes de venderlo.
- **Tamaño del bundle**: pandas+numpy ronda 150–300 MB; es normal, no "optimizar" quitando
  dependencias usadas.
- **Ollama no incluido**: el .exe empaqueta el cliente HTTP; Ollama corre aparte en la
  máquina del usuario (documentarlo en el README de instalación).
- **Rutas de usuario**: nunca escribir dentro del directorio de instalación; usar las
  rutas que el usuario elige en los diálogos.

## Prohibiciones

- No modificar código de producción solo para "hacer que el build funcione" salvo que sea
  un fix demostrable con test (regla de oro: un archivo, un cambio, un test).
- No distribuir builds con `console=True`, con UPX activado por defecto, o sin pruebas
  en máquina limpia.
- No versionar `build/` ni `dist/`; solo el `.spec` y el log de build.
