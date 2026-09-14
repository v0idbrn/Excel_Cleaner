"""tests/test_exporter_formula_injection.py — Regresión de seguridad (TDD).

Cubre la defensa contra Excel Formula Injection (CWE-1236) en exporter.py:

  ANTES: export_dataframe() escribía los valores tal cual. Una celda hostil
         ('=cmd()', '+1', '-2', '@x', tabular '=2+5') arrivaba al CSV/XLSX
         literal y Excel la ejecutaba al abrir el archivo (DDE/COM).
  DESPUÉS: los valores textuales que empiezan con = + - @ (o tabular) se
         prefijo con apóstrofe (') — la convención estándar de Excel para
         texto literal. El prefijo es fiel: '=> cmd se lee como texto => cmd.
         Los números legítimos no se tocan (empiezan con dígito/punto/NA).

Nota de diseño: se neutraliza en la EXPORTACIÓN (barrera final), no en el
Cleaner, para no alterar los datos en memoria ni romper el contrato del
Validator (que compara celda a celda contra su proyección).
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter import ExportError, export_dataframe  # noqa: E402
from models import ValidationResult  # noqa: E402


def _valid():
    return ValidationResult(valid=True, errors=(), warnings=())


class TestFormulaInjectionNeutralized(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_csv_dangerous_cells_get_apostrophe_prefix(self):
        df = pd.DataFrame({
            "cmd": ["=cmd|' /C calc'!A0", "normal"],
            "calc": ["+1+1", "x"],
            "minus": ["-2+3", "y"],
            "at": ["@SUM(1)", "z"],
            "tabbed": ["\t=2+5", "w"],
        })
        out = self.tmp / "out.csv"
        export_dataframe(df, out, _valid())
        raw = out.read_bytes().decode("utf-8")
        # Todas las celdas peligrosas comienzan con apóstrofe (texto literal)
        self.assertIn("'=cmd|' /C calc'!A0", raw)
        self.assertIn("'+1+1", raw)
        self.assertIn("'-2+3", raw)
        self.assertIn("'@SUM(1)", raw)
        self.assertIn("'\t=2+5", raw)
        # Los valores seguros no se alteran
        self.assertIn("\nnormal", raw)
        self.assertIn(",x", raw)

    def test_legitimate_numbers_untouched(self):
        df = pd.DataFrame({"A": [1, -2.5, "3,50", "$5"], "B": ["", "ok", None, pd.NA]})
        out = self.tmp / "nums.csv"
        export_dataframe(df, out, _valid())
        raw = out.read_bytes().decode("utf-8")
        self.assertIn("1,", raw)
        self.assertIn("-2.5", raw)
        self.assertIn("3,50", raw)
        self.assertIn("$5", raw)
        # Ningún número legítimo recibió apóstrofe
        self.assertNotIn("'-2.5", raw)
        self.assertNotIn("'3,50", raw)
        self.assertNotIn("'$5", raw)

    def test_numeric_dtypes_not_stringified(self):
        # Una columna numérica real (int64/float) no debe convertirse a texto.
        df = pd.DataFrame({"A": [1, 2], "B": [-2.5, 0.0]})
        out = self.tmp / "typed.csv"
        export_dataframe(df, out, _valid())
        raw = out.read_bytes().decode("utf-8")
        self.assertIn("1,", raw)
        self.assertIn("-2.5", raw)
        self.assertNotIn("'-2.5", raw)

    def test_zero_write_when_invalid_still_holds(self):
        # La barrera Zero-Write sigue FIRST: valid=False => ni siquiera se neutraliza.
        df = pd.DataFrame({"A": ["=cmd()"]})
        out = self.tmp / "blocked.csv"
        with self.assertRaises(ExportError):
            export_dataframe(df, out, ValidationResult(valid=False, errors=("x",), warnings=()))
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
