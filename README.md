# Excel Cleaner & Normalizer Engine (Zero-Cloud Edition)

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/)
[![Zero-Cloud Data Privacy](https://img.shields.io/badge/privacy-zero--cloud-9c27b0.svg)](#security--privacy)
[![License](https://img.shields.io/badge/license-permissive-lightgrey.svg)](LICENSE)

**English** · [Español](#español)

---

## What it is

Excel Cleaner is a **local-first data cleaning engine** for messy Excel/CSV files,
delivered as a desktop GUI app, a batch CLI, and an importable Python library.

It is built for predictable, auditable transformations — not black-box automation:

1. **Analyze** the file read-only (structure + data-quality issues).
2. **Propose** cleaning actions (deterministic analyzer, optional local AI).
3. **Human approval** — nothing runs without an explicit check.
4. **Clean** deterministically (approved actions only, original never mutated).
5. **Validate** with a zero-trust mathematical barrier (only approved changes pass).
6. **Export** — zero write if validation fails — plus a full audit report.

## The problem it solves

Freelancers, agencies and back-office teams constantly receive spreadsheets with
mixed encodings, invisible characters, `N/A`/`null` garbage, US/EU number formats
(`1,250.50` vs `1.250,50`), inconsistent dates (`15/03/2025` vs `2025-05-10`),
duplicates and trailing spaces. Cleaning them by hand is slow and error-prone;
generic scripts silently corrupt data. Excel Cleaner normalizes the file **and
produces a signed audit trail** proving exactly what changed — the deliverable
clients actually pay for.

## Key features

- **Robust loading** — CSV with encoding fallback chain (`utf-8-sig → utf-8 →
  cp1252 → latin-1`), delimiter sniffing (`,` `;` `\t` `|`), blank headers
  auto-named `Columna_N`, multi-sheet XLSX with empty-cover skip, size limit
  (1 GB) and clear controlled errors for corrupt/empty files.
- **16 deterministic cleaning actions** — trim, invisible-character cleanup,
  case normalization, garbage-to-null (`N/A`, `null`, `-`…), empty rows/columns
  removal, exact and by-key deduplication, date normalization to ISO 8601
  (`dayfirst` aware), locale-aware number/money normalization (US/EU/auto,
  currency symbols, accounting negatives, percentages), split/merge columns,
  ordered value replacement (exact / contains / regex).
- **Data-loss guards** — numeric conversion aborts if incompatible values would
  be destroyed; auto locale refuses to convert leading-zero codes and ≥13-digit
  IDs (float corruption) to numbers, surfacing them as explicit nulls + warnings.
- **Zero-trust validation** — the Validator *projects* the approved actions
  mathematically and compares against the real result cell by cell; any
  unauthorized mutation, row loss or column change blocks the export.
- **Zero-write export** — invalid validation ⇒ nothing touches the disk; existing
  files are never overwritten unless explicitly requested.
- **Formula-injection defense** (CWE-1236) — text cells starting with `= + - @`
  or a tab are exported with an apostrophe prefix so Excel never executes them.
- **Audit deliverables** — per run: `.txt` sidecar (ES/EN), `.json` (structured),
  `.html` certificate (print-to-PDF), and an embedded `_Reporte_Auditoria` sheet
  inside exported XLSX. All dynamic values are HTML-escaped.
- **Batch engine** — folder or multi-file processing with 3-pass pipeline
  (structural → typological → consolidation), per-file error isolation, `errors/`
  quarantine with readable reasons, honest `CLEANED`/`UNCHANGED` labels
  (cell-by-cell comparison), master JSON+TXT report, optional ZIP.
- **Optional local AI (zero-cloud)** — if [Ollama](https://ollama.com) is running,
  it proposes actions from **metadata only** (counts, dtypes, column names — never
  cell values). AI proposals are unapproved suggestions; validation still gates
  everything. If Ollama is offline the app keeps working.

## Requirements

- Python **3.14+**
- `pandas 3.0.5`, `numpy 2.4.3`, `openpyxl 3.1.5`, `requests 2.34.2`
  (see `requirements.txt`)
- Optional: Ollama + a local model for AI proposals.

## Install

```bash
git clone <this-repo> && cd excel-cleaner
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Desktop app (GUI)

```bash
python main.py
```

Workflow: **1. Seleccionar** file → **2. Analizar Base** → review/prove actions →
(✦ optional AI proposals) → **3. Aplicar Limpieza** (runs Cleaner+Validator) →
**4. Exportar** (file + audit report; language `es`/`en`, format `txt`/`html`/`ambos`).
**📁 Batch** processes a folder or a multi-selection; **⚙ Acciones personalizadas**
adds dedup-by-key / split / merge / replace proposals.

### Batch CLI

```bash
python batch_processor.py <input_folder> <output_folder> [--zip]
```

Exit code `0` when every file was processed (errors are isolated per file and
reported in `output_folder/batch_audit_summary.txt` / `.json`).

### As a library

```python
from pathlib import Path
from analyzer import build_file_info, load_dataframe, analyze_dataframe
from cleaner import clean_dataframe
from validators import validate_cleaning
from exporter import export_dataframe, generate_audit_report, export_audit_report
from models import CleaningAction

file_info = build_file_info(Path("input.csv"))
df = load_dataframe(file_info)
report = analyze_dataframe(df, file_info, sheet_name=None)

actions = (CleaningAction("trim_espacios", "Name", "trim", approved=True),)
df_clean, result = clean_dataframe(df, actions)
validation = validate_cleaning(df, df_clean, actions, result)

export_dataframe(df_clean, Path("output.csv"), validation)
audit = generate_audit_report("input.csv", "output.csv", result, validation, df, df_clean)
print(export_audit_report(audit, format="txt"))
```

> Note: function signatures above are the real ones — also check `analyzer.py`,
> `cleaner.py`, `validators.py` and `exporter.py` docstrings before integrating.

### Reproducible demo (INPUT → PROCESSING → OUTPUT)

```bash
python demo_scripts/generate_demo.py
```

Generates in `demo_portfolio/` (synthetic data, never real PII):

| Artifact | Content |
|---|---|
| `1_original_sucio.xlsx` | Dirty mini-B2B dataset (garbage, US/EU money, mixed dates, duplicates) |
| `2_resultado_limpio.xlsx` | Cleaned data + embedded `_Reporte_Auditoria` sheet |
| `3_reporte_auditoria.txt` | Audit report (Spanish) |
| `4_reporte_auditoria_en.txt` | Audit report (English) |
| `2_resultado_limpio_audit_report.html` | Print-to-PDF certificate |

## Architecture (non-negotiable flow)

```text
CSV/XLSX → Analyzer → AnalysisReport → [optional local AI, metadata-only] → AIProposal
        → HUMAN APPROVAL → CleaningAction → Cleaner → Validator → Exporter
```

- **Analyzer**: strictly read-only. **Cleaner**: deterministic, no I/O, no AI,
  never mutates the input DataFrame. **Validator**: mathematical barrier.
  **Exporter**: `validation.valid != True` ⇒ absolute zero write.
- Every new action must be implemented simultaneously in `cleaner.py`,
  `validators.py` (projection mirror) and `ai.py` (whitelist), with tests.

## Project structure

```text
main.py               GUI entry point (global crash handler, windowed-safe)
gui/                  Tkinter UI (dashboard, issues/approval panel, workers)
analyzer.py           Read-only loading + issue detection
cleaner.py            Deterministic cleaning engine (+ multi-pass auto pipeline)
validators.py         Zero-trust mathematical validation barrier
exporter.py           Zero-write export + audit reports (txt/json/html/xlsx sheet)
ai.py                 Optional Ollama integration (metadata-only, whitelisted)
batch_processor.py    Folder/multi-file batch engine + CLI
models.py / config.py Shared dataclasses / global constants
demo_scripts/         Regenerable portfolio demo
demo_portfolio/       Demo artifacts (generated)
tests/                Test suite (unittest + script-style)
```

## Testing

```bash
# unittest suite
python -m unittest discover -s tests -p "test_*.py"

# script-style suites
python tests/test_cleaner.py
python tests/test_validators.py
python tests/test_exporter.py
python tests/test_batch.py
python tests/test_user_workflow.py
python tests/test_edge_cases_ca.py
```

The suite covers: happy paths, invalid/corrupt/empty inputs, encoding fallbacks,
blank/duplicate headers, every cleaning action (including edge cases), validator
mirror attacks (unauthorized mutations must fail), zero-write enforcement,
formula-injection neutralization, HTML escaping, audit languages and batch
isolation — including GUI worker flows.

## Security & privacy

- **Zero cloud**: no data leaves the machine. The AI integration only talks to a
  local Ollama server and only ever receives structural metadata (never cell
  values, never samples).
- **Originals untouched**: input files are read-only; outputs go to a chosen
  destination and are never silently overwritten.
- **Export safety**: zero-write barrier, formula-injection neutralization,
  HTML-escaped audit reports, post-write existence/size verification.
- No telemetry, no network calls other than the optional local Ollama endpoint.

## Known limitations

- `.xls` (legacy) is only read in batch mode and requires `xlrd` (not bundled);
  convert to `.xlsx` first. GUI file dialogs accept `.csv`/`.xlsx`.
- Auto-locale number conversion deliberately refuses leading-zero codes and
  ≥13-digit integers (ID-like) — they become explicit nulls with warnings.
- Excel rows/cols limits apply to XLSX export (1,048,576 × 16,384).
- The Validator trusts the `ValidationResult` produced in the same process;
  a mutation of the DataFrame in the instant between validation and write is a
  documented, accepted theoretical gap (see `tests/test_exporter.py`).
- The GUI interface is Spanish-first; audit reports support `es`/`en`.
- AI proposals require a local Ollama installation; without it, everything else
  still works.

---

## Español

## Qué es

Excel Cleaner es un **motor local de limpieza de datos** para archivos Excel/CSV
desordenados, entregado como app de escritorio (GUI), CLI por lotes y librería
Python importable. Su filosofía: transformaciones **predecibles y auditables**,
no automatización de caja negra.

## El problema que resuelve

Freelancers, agencias y equipos back-office reciben constantemente planillas con
encodings mezclados, caracteres invisibles, basura tipo `N/A`/`null`, montos en
formato US/EU (`1,250.50` vs `1.250,50`), fechas inconsistentes (`15/03/2025` vs
`2025-05-10`), duplicados y espacios sobrantes. Limpiarlas a mano es lento y
propenso a errores; los scripts genéricos corrompen datos en silencio. Excel
Cleaner normaliza el archivo **y produce un reporte de auditoría** que prueba
exactamente qué cambió — el entregable que los clientes pagan.

## Características principales

- **Carga robusta**: fallback de encodings (`utf-8-sig → utf-8 → cp1252 → latin-1`),
  detección de delimitador, encabezados vacíos auto-nombrados `Columna_N`,
  XLSX multi-hoja (salta portadas vacías), límite de 1 GB, errores claros.
- **16 acciones de limpieza determinísticas**: trim, invisibles, mayúsculas,
  basura→nulo, filas/columnas vacías, duplicados exactos y por clave, fechas→ISO
  8601 (dayfirst), números/montos locale-aware (US/EU/auto, símbolos, negativos
  contables, porcentajes), dividir/unir columnas, reemplazos ordenados.
- **Guardas anti-pérdida**: la conversión numérica aborta si se destruirían
  valores; en auto, códigos con ceros a la izquierda e IDs de ≥13 dígitos NO se
  convierten (quedan nulos con warning visible).
- **Barrera Zero-Trust**: el Validator proyecta matemáticamente las acciones
  aprobadas y compara celda a celda; cualquier mutación no autorizada bloquea
  la exportación.
- **Zero-write**: validación inválida ⇒ nada se escribe; jamás se sobrescribe
  sin permiso explícito.
- **Defensa contra fórmulas maliciosas** (CWE-1236): celdas que empiezan con
  `= + - @` o tabulación se exportan con apóstrofe (Excel no las ejecuta).
- **Entregables de auditoría**: `.txt` (es/en), `.json`, certificado `.html`
  imprimible a PDF y pestaña `_Reporte_Auditoria` embebida en el XLSX.
- **Motor por lotes**: carpeta o multi-selección, pipeline de 3 pasadas, aislamiento
  de errores por archivo, cuarentena en `errors/` con motivos legibles, etiquetas
  honestas `CLEANED`/`UNCHANGED`, reporte maestro JSON+TXT y ZIP opcional.
- **IA local opcional (zero-cloud)**: vía Ollama, propone acciones usando SOLO
  metadatos (nunca valores de celdas). Las propuestas requieren aprobación
  humana; sin Ollama la app funciona igual.

## Requisitos e instalación

Python **3.14+** y las dependencias de `requirements.txt`.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

## Uso

```bash
# App de escritorio
python main.py

# Lotes por CLI
python batch_processor.py <carpeta_entrada> <carpeta_salida> [--zip]

# Demo reproducible (datos sintéticos, INPUT → PROCESO → OUTPUT)
python demo_scripts/generate_demo.py
```

Flujo GUI: **1. Seleccionar** → **2. Analizar Base** → revisar/aprobar acciones →
(✦ IA opcional) → **3. Aplicar Limpieza** (Cleaner+Validator) → **4. Exportar**
(archivo + reporte; idioma `es`/`en`, formato `txt`/`html`/`ambos`).
**📁 Batch** procesa carpetas o selecciones múltiples; **⚙ Acciones personalizadas**
agrega dedup por clave / dividir / unir / reemplazar como propuestas pendientes.

Ejemplo como librería y estructura interna: ver sección inglesa (`Usage`,
`Project structure`) — mismas APIs.

## Testing

```bash
python -m unittest discover -s tests -p "test_*.py"
python tests/test_cleaner.py   # + test_validators / test_exporter / test_batch
                               # + test_user_workflow / test_edge_cases_ca
```

## Seguridad y privacidad

- **Zero cloud**: ningún dato sale de la máquina; la IA opcional solo habla con
  un Ollama local y solo recibe metadatos estructurales.
- **Originales intactos**: los archivos de entrada son de solo lectura; las
  salidas nunca se sobrescriben silenciosamente.
- **Export seguro**: barrera zero-write, neutralización de fórmulas, reportes
  HTML escapados, verificación post-escritura.
- Sin telemetría; única llamada de red posible: el endpoint local de Ollama.

## Limitaciones conocidas

- `.xls` legacy: solo en lotes y requiere `xlrd` (convertir a `.xlsx`).
- En locale auto no se convierten códigos con ceros a la izquierda ni enteros
  largos (≥13 dígitos): quedan nulos con warning (anti-corrupción float).
- Límites de Excel para XLSX (1.048.576 filas × 16.384 columnas).
- La GUI está en español; los reportes de auditoría soportan `es`/`en`.
- Las propuestas de IA requieren Ollama local; sin él, todo lo demás funciona.

---

*Excel Cleaner works locally, with local data, and with local control.*
