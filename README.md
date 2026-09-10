# Excel Cleaner

> **EN** — Professional tool to **clean, normalize, validate and audit** Excel and CSV files: batch processing, multi-pass pipeline, audit reports with full traceability. 100% offline (desktop GUI + CLI).
>
> **ES** — Herramienta profesional para **limpiar, normalizar, validar y auditar** archivos Excel y CSV: procesamiento por lotes, pipeline multi-pass y reportes de auditoría con trazabilidad completa. Funciona 100% offline (GUI de escritorio + CLI).

*English version below · [Versión en español](#español)*

---

# English

## What it does and what problem it solves

Real-world data arrives dirty: invisible spaces, mixed date formats, amounts with currency symbols from different regions, empty rows, "disguised" duplicates. Excel Cleaner takes those files and produces clean versions **with a verifiable receipt of everything that was done** — without ever touching the originals.

```
INPUT (.csv/.xlsx/.xls)
   ↓
ANALYSIS    →  read-only problem detection
   ↓
CLEANING    →  deterministic multi-pass pipeline, approved actions only
   ↓
VALIDATION  →  Zero-Trust barrier: mathematical projection of the expected result
   ↓
OUTPUT      →  clean file + individual audit report
```

**Core principle:** the AI proposes, the user approves, the Cleaner executes, the Validator verifies, and the Exporter writes **only if validation passed** (zero-write). Original files are never modified.

## Current features

- **Formats:** `.csv` (encoding fallbacks: UTF-8, BOM, cp1252, latin-1; delimiter detection `,` `;` tab `|`), `.xlsx`, `.xls` (requires `xlrd`).
- **Multi-pass pipeline** (3 passes, logged per pass):
  - **Pass 1 — Structural cleanup:** whitespace trim, invisible characters (NBSP, zero-width, BOM), inconsistent casing.
  - **Pass 2 — Type normalization:** dates to ISO 8601 (configurable `dayfirst` for regional ambiguity), locale-aware monetary amounts (US/EU, `$ € £ US$ U$S USD`, accounting negatives `(150,00)`, percentages).
  - **Pass 3 — Consolidation:** empty strings to null, empty rows, exact duplicates **on already-clean data** (removes "dirty" duplicates that differ only by whitespace).
- **Batch processing:** a whole folder or a multi-file selection, with per-file progress, error isolation (one corrupt file never stops the batch), master report and optional ZIP of results. Every processed file is labeled **CLEANED** (effective changes) or **UNCHANGED** (verified cell-by-cell identical), and quarantined files get client-readable reasons — never raw stack traces.
- **Audit reports:** per-file (TXT/JSON) + batch master summary (JSON/TXT) with metrics: rows before/after, removed, per-cell changes, executed actions, warnings and the Zero-Trust validation verdict.
- **Optional local AI (Ollama):** receives **structural metadata only** (dtypes, counts, column names) — never cell values. Every proposal arrives `pending` and requires manual approval.
- **Configuration:** each batch pass can be enabled/disabled; each individual action is approved/rejected in the panel.

## Installation

```bash
pip install -r requirements.txt
```

Dependencies: `pandas`, `numpy`, `openpyxl` (XLSX engine), `requests` (only for the local Ollama call).

## Usage — GUI

```bash
python main.py
```

Single-file flow:

1. **Seleccionar** — loads the file (originals are never touched).
2. **Analizar Base** — detects issues and proposes actions (unchecked by default).
3. **✦ Consultar IA** *(optional)* — proposals from local Ollama, all `pending`.
4. Check the actions you approve in the panel and **Aplicar Limpieza** — the Validator audits the result immediately.
5. **Exportar** — choose path and format; the clean file is generated **plus** `<name>_audit_report.txt` in the same folder.

Batch flow (dozens/hundreds of files):

1. In the **"Batch: pases a aplicar"** panel, choose which passes to run (and whether you want a ZIP).
2. **📁 Batch (Carpeta)** → choose mode `carpeta` (process a whole folder) or `archivos` (multi-select with Ctrl+click).
3. Pick the output folder → the process runs in the background with per-file progress.
4. When done: a popup shows the summary (OK / rejected / errors / rows / changes) and the master report path.

Batch output structure:

```
output/
├── clientes_01.xlsx                 ← original file name preserved
├── clientes_01_audit_report.txt     ← per-file audit
├── batch_audit_summary.json/.txt    ← batch master summary
├── batch_results.zip                ← if you checked "Crear ZIP"
└── errors/                          ← corrupt files (moved) and Validator-rejected files (copied + reason)
```

## Usage — CLI (batch)

```bash
python batch_processor.py <input_folder> <output_folder> [--zip]
```

Example master report (`batch_audit_summary.txt`):

```
Files found: 25 | OK: 24 | Rejected by Validator: 0 | Errors: 1
  OK breakdown     : CLEANED (with changes): 22 | UNCHANGED (no mutations): 2
Rows before/after: 78,420 -> 76,903 (removed: 1,517)
Total changes     : 14,208 (modified cells + removed rows)

[CLEANED  ] clientes_01.xlsx -> clientes_01.xlsx (rows 1200->1180, changes: 340, actions: 6)
[UNCHANGED] clientes_02.xlsx -> clientes_02.xlsx (rows 980->980, changes: 0, actions: 0)
[ERROR]   clientes_09.xlsx -> Could not process this file. Cause: <plain-language reason>
```

`UNCHANGED` is honest by construction: the pipeline compares the original and the result with `DataFrame.equals` — not with heuristics. A file that did not need cleaning is reported as such, and its output is a faithful copy of the input.

## Example

Input → Cleaning → Validation → Output

| Input (dirty) | Output (clean) |
|---|---|
| `"  Ana  "` | `Ana` |
| `"12/05/2026"` (dayfirst=true) | `2026-05-12` |
| `"$ 1.250,50"` / `"(150,00)"` | `1250.5` / `-150.0` |
| row with only empty cells | removed (reported) |
| `"Ana"` vs `" Ana "` (duplicates) | deduplicated after trim (reported) |

- **Cleaning:** only the actions you approved are executed; every transformation is logged per column (input/output dtype, nulls before/after, values changed).
- **Validation:** the Validator *mathematically re-projects* what the approved actions should produce and compares cell by cell. Any deviation (unauthorized mutation) blocks the export.
- **Output:** file with the same name in the output folder + audit report. If a previous result exists, `name_limpio_1.ext` is created instead — never overwrites.

## Privacy

- All processing is **local**. No file is ever sent to external services.
- The AI integration is optional and talks only to a **local Ollama server** (defaults defined in `ai.py`: URL `http://127.0.0.1:11434`, model `phi4-mini:latest`, timeout 30 s; overridable via `config.py` attributes — `config.py` currently does not define them, so the defaults apply).
- The AI receives **structural metadata only** (types, counts, column names). Cell values never leave the process (verified by the `test_ai_privacy` suite).
- Logs and reports contain metrics and file names, not spreadsheet content.

## Tests

```bash
# unittest suite (GUI, AI, E2E)
python -m unittest discover -s tests -p "test_*.py"

# Function-style suites
python tests/test_cleaner.py
python tests/test_validators.py
python tests/test_exporter.py
python tests/test_batch.py
python tests/test_user_workflow.py
python tests/test_edge_cases_ca.py
python tests/test_ai_config.py
python tests/test_ai_offline.py
python tests/test_ai_privacy.py
python tests/test_ai_e2e.py
```

## Project structure

```
main.py               → GUI launcher
config.py             → limits and configuration (currently MAX_FILE_SIZE_BYTES = 1 GB)
models.py             → contracts: CleaningAction, CleaningResult, ValidationResult, AuditReport...
analyzer.py           → READ-ONLY loading + analysis (problem detectors)
cleaner.py            → deterministic action executor + multi-pass engine
validators.py         → Zero-Trust barrier (mathematical projection of transformations)
exporter.py           → safe writing (zero-write) + audit reports
ai.py                 → Ollama integration (metadata-only, action whitelist)
batch_processor.py    → batch engine: folder/multi-select, error isolation, master report, ZIP
gui/                  → app (flow & workers), dashboard, issues_panel
tests/                → unittest + function-style suites
.agents/skills/       → engineering rules applied by the development agents
```

## Known limitations

**Resolved — previously reported issues:**

- ✅ GUI loading uses the Analyzer engine (semicolon/encoding fallbacks + sheet picker for multi-sheet workbooks).
- ✅ Multi-select batch from the GUI (`archivos` mode) works.
- ✅ Blank headers are auto-renamed (`Columna_N`) and reported for review instead of rejecting the file.
- ✅ Completely empty cover sheets are skipped to the first sheet with data.
- ✅ Batch master report distinguishes **CLEANED** vs **UNCHANGED**; quarantined files get plain-language reasons (no raw stack traces).
- ✅ Split & merge keep Excel-style positional structure: a split→merge round-trip restores the original column order.
- ✅ Common garbage values (`N/A`, `null`, `-`, `None`, `sin dato`, …) become real nulls with the built-in `convertir_basura_a_nulo` action (optional extra patterns and text zeros, always with the Validator mirror and audit trail).
- ✅ Exported `.xlsx` files embed the `_Reporte_Auditoria` sheet (plus the `_audit_report.txt` sidecar); CSV export stays clean.
- ✅ Standalone Windows build (`dist/ExcelCleaner.exe`) verified: one file, no console, corrected modules packaged (a full functional pass on a Python-free machine is still recommended before delivery).

**Still open (current limitations):**

- **.xls** requires installing `xlrd` (not included in requirements); otherwise convert to `.xlsx`.
- Password-protected files are not processed (they are quarantined in `errors/` with the reason).
- The Analyzer's email check is **format-only** (detects suspicious patterns); it does not confirm the mailbox actually exists.
- In batch, a file rejected by the Validator is **not exported** (Zero-Trust by design): its copy and the reason remain in `errors/`.
- Output `.xlsx` files are regenerated from the data: formulas become their calculated values.
- Automatic date/currency column detection is conservative (80% parseable threshold); edge cases may require manual action approval.
- Ambiguous EU thousands-only patterns (e.g. `1.250.000`) are not auto-interpreted in `locale=auto`; pass an explicit `locale` parameter.
- **Rejected by design:** files with real duplicate header names (e.g. two `Nombre` columns) — pandas would silently mangle them (`Nombre.1`); they need manual attention instead of a silent guess.

## Project status

MVP under active development, with a Zero-Trust architecture proven internally (phases 1–9). Data safety is prioritized over aggressive cleaning: **if an operation risks altering important information, it warns or blocks.**

---

# Español

## Qué hace y qué problema resuelve

Los datos reales llegan sucios: espacios invisibles, fechas con formatos mixtos, montos con símbolos de moneda de distintas regiones, filas vacías, duplicados "disfrazados". Excel Cleaner toma esos archivos y produce versiones limpias **con un comprobante verificable de todo lo que se hizo** — sin tocar jamás los originales.

```
ENTRADA (.csv/.xlsx/.xls)
   ↓
ANÁLISIS    →  detección de problemas (solo lectura)
   ↓
LIMPIEZA    →  pipeline multi-pass determinista, solo acciones aprobadas
   ↓
VALIDACIÓN  →  barrera Zero-Trust: proyección matemática de lo esperado
   ↓
SALIDA      →  archivo limpio + reporte de auditoría individual
```

**Principio fundamental:** la IA propone, el usuario aprueba, el Cleaner ejecuta, el Validator verifica y el Exporter escribe **solo si la validación fue válida** (zero-write). Los archivos originales nunca se modifican.

## Funcionalidades actuales

- **Formatos:** `.csv` (fallbacks de encoding: UTF-8, BOM, cp1252, latin-1; detección de delimitador `,` `;` tab `|`), `.xlsx`, `.xls` (requiere `xlrd`).
- **Pipeline multi-pass** (3 pasadas con log por pasada):
  - **Pass 1 — Limpieza estructural:** trim de espacios, caracteres invisibles (NBSP, zero-width, BOM), casing inconsistente.
  - **Pass 2 — Normalización tipológica:** fechas a ISO 8601 (`dayfirst` configurable para ambigüedad regional), montos monetarios locale-aware (US/EU, `$ € £ US$ U$S USD`, negativos contables `(150,00)`, porcentajes).
  - **Pass 3 — Consolidación:** vacíos a nulo, filas vacías, duplicados exactos **sobre datos ya limpios** (elimina duplicados "sucios" que difieren solo por espacios).
- **Procesamiento por lotes:** carpeta completa o multi-selección de archivos, con progreso por archivo, aislamiento de errores (un archivo corrupto no detiene el lote), reporte maestro y ZIP opcional de resultados. Cada archivo procesado queda etiquetado **CLEANED** (con cambios efectivos) o **UNCHANGED** (verificado idéntico celda a celda), y los archivos en cuarentena reciben causas legibles para el cliente — nunca stack traces crudos.
- **Reportes de auditoría:** individual por archivo (TXT/JSON) + resumen maestro del lote (JSON/TXT) con métricas: filas antes/después, eliminadas, cambios por celda, acciones ejecutadas, advertencias y veredicto de validación Zero-Trust.
- **IA local opcional (Ollama):** solo recibe **metadata estructural** (tipos, conteos, nombres de columnas) — jamás valores de celdas. Toda propuesta llega `pending` y requiere aprobación manual.
- **Configuración:** cada pase del batch se puede activar/desactivar; cada acción individual se aprueba/rechaza en el panel.

## Instalación

```bash
pip install -r requirements.txt
```

Dependencias: `pandas`, `numpy`, `openpyxl` (motor XLSX), `requests` (solo para Ollama local).

## Uso — GUI

```bash
python main.py
```

Flujo con un archivo:

1. **Seleccionar** — carga el archivo (los originales jamás se tocan).
2. **Analizar Base** — detecta problemas y propone acciones (desmarcadas por defecto).
3. **✦ Consultar IA** *(opcional)* — propuestas de Ollama local, todas `pending`.
4. Marcar las acciones que apruebe en el panel y **Aplicar Limpieza** — el Validator audita el resultado al instante.
5. **Exportar** — elige ruta y formato; se genera el archivo limpio **+** `<nombre>_audit_report.txt` en la misma carpeta.

Flujo batch (decenas/cientos de archivos):

1. Configurar en el panel **"Batch: pases a aplicar"** qué pasadas ejecutar (y si querés ZIP).
2. **📁 Batch (Carpeta)** → escribir modo `carpeta` (procesa todos los de una carpeta) o `archivos` (multi-selección con Ctrl+clic).
3. Elegir carpeta de salida → el proceso corre en segundo plano con progreso por archivo.
4. Al terminar: popup con resumen (OK / rechazados / errores / filas / cambios) y ruta del reporte maestro.

Estructura de salida del batch:

```
output/
├── clientes_01.xlsx                 ← nombre original conservado
├── clientes_01_audit_report.txt     ← auditoría individual
├── batch_audit_summary.json/.txt    ← resumen global del lote
├── batch_results.zip                ← si marcaste "Crear ZIP"
└── errors/                          ← corruptos (movidos) y rechazados (copiados + motivo)
```

## Uso — CLI (batch)

```bash
python batch_processor.py <carpeta_entrada> <carpeta_salida> [--zip]
```

Ejemplo de reporte maestro (`batch_audit_summary.txt`):

```
Archivos encontrados : 25 | OK: 24 | Rechazados por Validator: 0 | Errores: 1
  Detalle de OK      : CLEANED (con cambios): 22 | UNCHANGED (sin mutaciones): 2
Filas antes/después : 78.420 -> 76.903 (eliminadas: 1.517)
Changes totales     : 14.208 (celdas modificadas + filas eliminadas)

[CLEANED  ] clientes_01.xlsx -> clientes_01.xlsx (filas 1200->1180, cambios: 340, acciones: 6)
[UNCHANGED] clientes_02.xlsx -> clientes_02.xlsx (filas 980->980, cambios: 0, acciones: 0)
[ERROR]   clientes_09.xlsx -> No se pudo procesar este archivo. Causa: <motivo en lenguaje claro>
```

`UNCHANGED` es honesto por construcción: el pipeline compara el original y el resultado con `DataFrame.equals` — no con heurísticas. Un archivo que no necesitaba limpieza se reporta como tal, y su salida es una copia fiel de la entrada.

## Ejemplo

Input → Cleaning → Validation → Output

| Input (sucio) | Output (limpio) |
|---|---|
| `"  Ana  "` | `Ana` |
| `"12/05/2026"` (dayfirst=true) | `2026-05-12` |
| `"$ 1.250,50"` / `"(150,00)"` | `1250.5` / `-150.0` |
| fila con solo celdas vacías | eliminada (reportada) |
| `"Ana"` vs `" Ana "` (duplicados) | deduplicados tras el trim (reportados) |

- **Cleaning:** solo se ejecutan las acciones que aprobaste; cada transformación queda registrada por columna (dtype entrada/salida, nulos antes/después, valores cambiados).
- **Validation:** el Validator *reproyecta matemáticamente* lo que las acciones aprobadas debían producir y compara celda a celda. Cualquier desvío (mutación no autorizada) bloquea la exportación.
- **Output:** archivo con el mismo nombre en la carpeta de salida + reporte de auditoría. Si ya existiera un resultado previo, se crea `nombre_limpio_1.ext` — jamás sobrescribe.

## Privacidad

- Todo el procesamiento es **local**. Ningún archivo se envía a servicios externos.
- La integración IA es opcional y habla únicamente con un servidor **Ollama local** (valores por defecto definidos en `ai.py`: URL `http://127.0.0.1:11434`, modelo `phi4-mini:latest`, timeout 30 s; sobrescribibles mediante atributos en `config.py` — actualmente `config.py` no los define, así que aplican los defaults).
- La IA recibe **solo metadata estructural** (tipos, conteos, nombres de columna). Los valores de celdas jamás salen del proceso (verificado por la suite `test_ai_privacy`).
- Los logs y reportes contienen métricas y nombres de archivo, no contenido de planillas.

## Tests

```bash
# Suite unittest (GUI, IA, E2E)
python -m unittest discover -s tests -p "test_*.py"

# Suites por patrón función
python tests/test_cleaner.py
python tests/test_validators.py
python tests/test_exporter.py
python tests/test_batch.py
python tests/test_user_workflow.py
python tests/test_edge_cases_ca.py
python tests/test_ai_config.py
python tests/test_ai_offline.py
python tests/test_ai_privacy.py
python tests/test_ai_e2e.py
```

## Estructura del proyecto

```
main.py               → lanzador de la GUI
config.py             → límites y configuración (actualmente MAX_FILE_SIZE_BYTES = 1 GB)
models.py             → contratos: CleaningAction, CleaningResult, ValidationResult, AuditReport...
analyzer.py           → carga + análisis READ-ONLY (detectores de problemas)
cleaner.py            → ejecutor determinista de acciones + motor multi-pass
validators.py         → barrera Zero-Trust (proyección matemática de transformaciones)
exporter.py           → escritura segura (zero-write) + reportes de auditoría
ai.py                 → integración Ollama (metadata-only, whitelist de acciones)
batch_processor.py    → motor de lotes: carpeta/multi-select, aislamiento, reporte maestro, ZIP
gui/                  → app (flujo y workers), dashboard, issues_panel
tests/                → suites unittest + patrón función
.agents/skills/       → reglas de ingeniería aplicadas por los agentes de desarrollo
```

## Limitaciones conocidas

**Resueltos — problemas reportados anteriormente:**

- ✅ La carga de la GUI usa el motor del Analyzer (fallbacks de delimitador/encoding + selector de hoja para multi-hoja).
- ✅ El batch multi-selección desde la GUI (modo `archivos`) funciona.
- ✅ Los encabezados vacíos se auto-renombran (`Columna_N`) y se reportan para revisión en lugar de rechazar el archivo.
- ✅ Las hojas de portada completamente vacías se saltan automáticamente a la primera hoja con datos.
- ✅ El reporte maestro del lote distingue **CLEANED** vs **UNCHANGED**; los archivos en cuarentena reciben motivos en lenguaje claro (sin stack traces crudos).
- ✅ Split y merge mantienen la estructura posicional estilo Excel: un round-trip split→merge restaura el orden original de las columnas.
- ✅ Los valores de basura comunes (`N/A`, `null`, `-`, `None`, `sin dato`…) se convierten en nulos reales con la acción integrada `convertir_basura_a_nulo` (patrones extra y ceros textuales opcionales, siempre con espejo en el Validator y trazabilidad de auditoría).
- ✅ Los `.xlsx` exportados llevan embebida la hoja `_Reporte_Auditoria` (además del sidecar `_audit_report.txt`); el CSV de salida se mantiene limpio.
- ✅ El build standalone de Windows (`dist/ExcelCleaner.exe`) está verificado: un solo archivo, sin consola, con los módulos corregidos empaquetados (igual se recomienda la pasada funcional completa en una máquina sin Python antes de entregar).

**Aún abiertas (limitaciones vigentes):**

- **.xls** requiere instalar `xlrd` (no incluido en requirements); para el resto de los casos se recomienda convertir a `.xlsx`.
- Archivos protegidos con contraseña no se procesan (quedan aislados en `errors/` con el motivo).
- La validación de emails del Analyzer es **de formato** (detecta patrones sospechosos); no confirma existencia real de la casilla.
- En batch, un archivo rechazado por el Validator **no se exporta** (por diseño Zero-Trust): su copia y el motivo quedan en `errors/`.
- Los `.xlsx` de salida se regeneran desde los datos: las fórmulas se convierten a sus valores calculados.
- La detección de columnas de fechas/moneda en modo automático es conservadora (umbral 80% de valores parseables); casos límite pueden requerir aprobación manual de acciones.
- Patrones ambiguos de miles EU solo-puntos (ej. `1.250.000`) no se interpretan automáticamente en `locale=auto`; pasar un parámetro `locale` explícito.
- **Se rechazan por diseño:** archivos con nombres de encabezado realmente duplicados (ej. dos columnas `Nombre`) — pandas los corrompería en silencio (`Nombre.1`); requieren atención manual en vez de una adivinanza silenciosa.

## Estado del proyecto

MVP en desarrollo activo, con arquitectura Zero-Trust probada en producción interna (fases 1–9). Seguridad de datos priorizada por sobre limpieza agresiva: **si una operación tiene riesgo de alterar información importante, se advierte o se bloquea.**
