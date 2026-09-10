"""Tests de idioma para el reporte de auditoría (TXT, JSON y pestaña embebida).

Cubre:
- Reporte TXT en inglés ("en") para clientes internacionales (Fiverr).
- Reporte TXT en español ("es") intacto (retrocompatibilidad).
- Regresión: las advertencias de validación NO se pierden en el TXT en inglés
  (bug del borrador interrumpido: el bucle solo agregaba líneas si language=="es").
- generate_audit_report(language=...) valida el idioma y rechaza valores inválidos.
- Pestaña embebida _Reporte_Auditoria localizada en "en" y en "es".
- JSON refleja el idioma del reporte.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from exporter import (  # noqa: E402
    AUDIT_SHEET_NAME,
    ExportError,
    export_audit_report,
    export_dataframe,
    generate_audit_report,
)
from models import CleaningAction, CleaningResult, ValidationResult  # noqa: E402


def _make_report(language: str = "es", with_validation_warnings: bool = True) -> "object":
    """Reporte de auditoría estándar con una acción y advertencias de validación."""
    action = CleaningAction("trim_espacios", "Nombre", "Quitar espacios", approved=True)
    cleaning_result = CleaningResult(
        actions_applied=(action,),
        rows_before=2,
        rows_after=2,
        columns_before=1,
        columns_after=1,
        warnings=("3 celdas recortadas",),
    )
    validation_result = ValidationResult(
        valid=True,
        errors=(),
        warnings=("Columna 'Nombre' con valores mixtos",) if with_validation_warnings else (),
    )
    df_orig = pd.DataFrame({"Nombre": ["  Ana  ", " Beto "]})
    df_clean = pd.DataFrame({"Nombre": ["Ana", "Beto"]})
    return generate_audit_report(
        original_file="clientes.csv",
        export_file="clientes_limpio.xlsx",
        cleaning_result=cleaning_result,
        validation_result=validation_result,
        df_original=df_orig,
        df_clean=df_clean,
        language=language,
    )


class TestTxtLanguage(unittest.TestCase):
    def _write(self, language: str) -> str:
        report = _make_report(language=language)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(export_audit_report(report, output_dir=tmp, format="txt"))
            return path.read_text(encoding="utf-8")

    def test_english_txt_content(self):
        content = self._write("en")
        self.assertIn("AUDIT REPORT - EXCEL CLEANER", content)
        self.assertIn("Timestamp UTC:", content)
        self.assertIn("Cleaner version:", content)
        self.assertIn("Rows before: 2", content)
        self.assertIn("ACTIONS EXECUTED", content)
        self.assertIn("COLUMN TRANSFORMATIONS", content)
        self.assertIn("END OF AUDIT REPORT", content)

    def test_english_txt_has_no_spanish_headers(self):
        content = self._write("en")
        self.assertNotIn("REPORTE DE AUDITORIA", content)
        self.assertNotIn("Filas antes:", content)
        self.assertNotIn("ACCIONES EJECUTADAS", content)

    def test_spanish_txt_remains_default(self):
        content_es = self._write("es")
        self.assertIn("REPORTE DE AUDITORIA - EXCEL CLEANER", content_es)
        self.assertIn("Filas antes: 2", content_es)
        self.assertIn("FIN DEL REPORTE DE AUDITORIA", content_es)

    def test_validation_warnings_present_in_english(self):
        """Regresión: el borrador interrumpido perdía warnings en el TXT en inglés."""
        content = self._write("en")
        self.assertIn("WARNING:", content)
        self.assertIn("Columna 'Nombre' con valores mixtos", content)

    def test_validation_warnings_present_in_spanish(self):
        content = self._write("es")
        self.assertIn("WARNING:", content)
        self.assertIn("Columna 'Nombre' con valores mixtos", content)

    def test_cleaning_warnings_present_in_both_languages(self):
        self.assertIn("3 celdas recortadas", self._write("en"))
        self.assertIn("3 celdas recortadas", self._write("es"))


class TestGenerateLanguageParam(unittest.TestCase):
    def test_default_language_is_spanish(self):
        report = _make_report()
        self.assertEqual(report.language, "es")

    def test_english_language_stored(self):
        report = _make_report(language="en")
        self.assertEqual(report.language, "en")

    def test_invalid_language_rejected(self):
        with self.assertRaises(ExportError):
            _make_report(language="fr")

    def test_json_includes_language(self):
        import json
        report = _make_report(language="en")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(export_audit_report(report, output_dir=tmp, format="json"))
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["language"], "en")
        self.assertIn("export_timestamp", data)
        self.assertIn("cleaner_version", data)


class TestEmbeddedSheetLanguage(unittest.TestCase):
    def _export(self, language: str) -> Path:
        report = _make_report(language=language)
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        out = Path(tmpdir.name) / "salida.xlsx"
        export_dataframe(
            pd.DataFrame({"Nombre": ["Ana", "Beto"]}),
            out,
            ValidationResult(valid=True),
            overwrite=True,
            audit_report=report,
        )
        return out

    def test_english_sheet_labels(self):
        out = self._export("en")
        sheet = pd.read_excel(out, sheet_name=AUDIT_SHEET_NAME, header=None)
        flat = " ".join(str(v) for v in sheet.values.flatten() if pd.notna(v))
        self.assertIn("Audit Report", flat)
        self.assertIn("Rows before", flat)
        self.assertIn("Actions executed", flat)
        self.assertNotIn("REPORTE DE AUDITORIA", flat)
        self.assertNotIn("Filas originales", flat)

    def test_spanish_sheet_labels_default(self):
        out = self._export("es")
        sheet = pd.read_excel(out, sheet_name=AUDIT_SHEET_NAME, header=None)
        flat = " ".join(str(v) for v in sheet.values.flatten() if pd.notna(v))
        self.assertIn("REPORTE DE AUDITORIA", flat)
        self.assertIn("Filas originales", flat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
