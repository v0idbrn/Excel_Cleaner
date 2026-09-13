# Excel Cleaner & Normalizer Engine (Zero-Cloud Edition)

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/)
[![Automated Data Sanitization](https://img.shields.io/badge/category-automated%20data%20sanitization-brightgreen.svg)](https://github.com/v0idbrn/Excel_Cleaner)
[![License](https://img.shields.io/badge/license-permissive-lightgrey.svg)](LICENSE)
[![Zero-Cloud Data Privacy](https://img.shields.io/badge/privacy-zero--cloud%20data%20privacy-9c27b0.svg)](README.md)

**High-performance, local Python engine designed for automated Excel/CSV data sanitization, encoding normalization, deduplication, and schema formatting.**

---

## Overview

Excel Cleaner is a local-first data cleaning engine for raw and irregular Excel/CSV files.

It focuses on predictable, auditable transformations rather than black-box automation:

- load heterogeneous files defensively,
- analyze structure without modifying the original,
- apply deterministic cleaning actions,
- validate integrity before export,
- and produce a traceable audit report for each run.

No data is sent to third-party services. The engine runs locally and is designed for B2B workflows where privacy, reproducibility, and traceability matter.

---

## Key features

### Zero-Cloud data privacy

- Local execution only.
- No implicit external data transmission.
- Client files remain on the local machine.

### Robust and defensive loading

- CSV support for multiple encodings and common delimiters.
- Excel support for single-sheet and multi-sheet workbooks.
- Early validation for missing files, empty files, unsupported extensions, and oversized inputs.

### Static analysis without side effects

The analyzer inspects structure and data quality, including:

- empty rows and columns
- missing values
- exact and possible duplicates
- whitespace and casing issues
- numeric values stored as text
- suspicious emails and phone patterns
- inconsistent dates and statistical outliers

### Deterministic cleaning

Cleaning actions are explicit, repeatable, and parameterized when needed:

- string trimming and invisible-character cleanup
- case normalization
- date normalization toward ISO 8601
- locale-aware numeric and monetary normalization
- defensive conversion of garbage or unparseable values into safe nulls with warnings

### Zero-trust validation

Before export, the validator checks that only approved transformations were applied and blocks:

- unauthorized mutations
- unexpected row or column loss
- value changes outside the approved operation

### Auditable export

- Export is blocked when validation fails.
- Each run can produce an audit report with:
  - source file
  - timestamp
  - initial vs final row counts
  - removed rows
  - actions executed
  - column-level transformations
  - warnings
  - validation result

---

## Quick start

### 1. Install

```bash
cd "F:\Gigs\Excel Cleaner"

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Run as a desktop app

```bash
python main.py
```

Typical workflow:

1. Open an Excel or CSV file.
2. Run analysis.
3. Review detected issues.
4. Approve the actions you want.
5. Run cleaning.
6. Validate integrity.
7. Export the cleaned file and audit report.

### 3. Use as a module

```python
from pathlib import Path

from analyzer import load_dataframe, analyze_dataframe
from cleaner import run_approved_cleaning
from validators import validate_cleaning
from exporter import export_clean_dataframe, export_audit_report

source = Path("sample.csv")

df, info = load_dataframe(source)
issues = analyze_dataframe(df)

approved_actions = [...]  # chosen manually or via your own logic

clean_result = run_approved_cleaning(df, approved_actions)
validation = validate_cleaning(df, clean_result.dataframe, approved_actions)

export_path = Path("output_clean.xlsx")
export_clean_dataframe(clean_result.dataframe, export_path, validation)
export_audit_report(export_path, clean_result, validation, df, clean_result.dataframe)
```

Exact function and class names may vary by version. Check `analyzer.py`, `cleaner.py`, `validators.py`, and `exporter.py` before integrating.

---

## Batch processing

For folder-level work, the project supports batch execution with:

- recursive or direct processing of supported file types
- error isolation per file
- per-file audit trails
- a global batch summary
- clear outcome classification per file

This is useful when processing many client files without stopping the entire job because of one bad input.

---

## Why this matters for B2B work

- You can take uncertain client files and normalize the parts that matter.
- You can remove duplicates by key when there is enough evidence to do so safely.
- You can standardize dates, numbers, money, and text without guessing.
- You can deliver a cleaned file plus a record of what changed.
- You can keep the original file untouched.

---

## Known limitations

- This is a sanitization and formatting engine, not an enrichment platform.
- Ambiguous data should be reviewed rather than auto-corrected blindly.
- Automated issue detection does not replace human review for sensitive datasets.
- Some advanced behaviors may require explicit configuration or manual approval.

---

## Development and maintenance

This repository is intended to be used, audited, and maintained as a data cleaning utility.

Best practices:

- keep originals untouched,
- preserve audit reports per delivery,
- review the pipeline before automating critical flows.

---

*Excel Cleaner is designed to work locally, with local data, and with local control.*
