"""tests/test_exporter_html_escaping.py — Regresión de seguridad (TDD).

Cubre el escape de HTML en el reporte de auditoría (certificado .html):

  ANTES: _write_html_report interpolaba valores dinámicos sin html.escape:
         rutas de archivos, nombres de columna, descripciones (que pueden
         venir de la IA), parámetros y warnings. Un archivo cuyo nombre
         contenga '<script>' (o una columna '<img src=x onerror=...>')
         inyectaba HTML/Ejecución de scripts en el certificado que el
         cliente abre en su navegador.
  DESPUÉS: todo valor dinámico se escapa (&lt;script&gt;); el documento
         nunca contiene etiquetas crudas provenientes de datos.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter import export_audit_report, generate_audit_report  # noqa: E402
from models import CleaningAction, CleaningResult, ValidationResult  # noqa: E402


class TestHtmlReportEscaping(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _export(self, original_file: str, warning: str | None = None) -> str:
        df = pd.DataFrame({"A": ["  x "]})
        df_clean = pd.DataFrame({"A": ["x"]})
        action = CleaningAction("trim_espacios", "A", "Descripción <b>inocua</b>", approved=True)
        result = CleaningResult(
            actions_applied=(action,), rows_before=1, rows_after=1,
            columns_before=1, columns_after=1,
            warnings=(warning,) if warning else (),
        )
        report = generate_audit_report(
            original_file=original_file,
            export_file=self.tmp / "clean.xlsx",
            cleaning_result=result,
            validation_result=ValidationResult(valid=True),
            df_original=df,
            df_clean=df_clean,
        )
        return Path(export_audit_report(report, self.tmp, format="html")).read_text(encoding="utf-8")

    def test_malicious_filename_is_escaped(self):
        html_out = self._export('orig <script>alert(1)</script>.csv')
        self.assertNotIn("<script>alert(1)</script>", html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_malicious_warning_is_escaped(self):
        html_out = self._export("orig.csv", warning="<img src=x onerror=alert(1)>")
        self.assertNotIn("<img src=x onerror=alert(1)>", html_out)
        self.assertIn("&lt;img", html_out)

    def test_malicious_column_name_is_escaped(self):
        df = pd.DataFrame({"<b>Col</b>": ["  x "]})
        df_clean = pd.DataFrame({"<b>Col</b>": ["x"]})
        action = CleaningAction("trim_espacios", "<b>Col</b>", "", approved=True)
        result = CleaningResult(
            actions_applied=(action,), rows_before=1, rows_after=1,
            columns_before=1, columns_after=1,
        )
        report = generate_audit_report(
            original_file="orig.csv",
            export_file=self.tmp / "clean.xlsx",
            cleaning_result=result,
            validation_result=ValidationResult(valid=True),
            df_original=df,
            df_clean=df_clean,
        )
        html_out = Path(export_audit_report(report, self.tmp, format="html")).read_text(encoding="utf-8")
        self.assertNotIn("<b>Col</b>", html_out)
        self.assertIn("&lt;b&gt;Col&lt;/b&gt;", html_out)

    def test_legitimate_text_still_renders(self):
        html_out = self._export("reporte_cliente.csv")
        self.assertIn("reporte_cliente.csv", html_out)
        self.assertIn("<!DOCTYPE html>", html_out)


if __name__ == "__main__":
    unittest.main()
