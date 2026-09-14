"""tests/test_analyzer_encoding_fallback.py — Regresión de encoding (TDD).

Cubre el fallback de encoding en TODAS las rutas de carga de CSV:

  ANTES: si el header era válido en la primera codificación probada pero los
         DATOS contenían bytes inválidos para utf-8 (decodificables solo como
         cp1252/latin-1), la ruta de auto-renombre (_read_csv_renamed_headers,
         archivos con columnas sin encabezado) dejaba escapar la
         UnicodeDecodeError cruda SIN continuar con las siguientes
         codificaciones: la GUI mostraba "Error leyendo archivo: 'utf-8'
         codec..." y un archivo SALVABLE se rechazaba, mientras que el mismo
         archivo con encabezado completo sí se rescataba vía cp1252.
  DESPUÉS: la ruta de auto-renombre se comporta igual que la ruta normal:
         ante UnicodeDecodeError continúa con las siguientes codificaciones
         (utf-8 -> cp1252 -> latin-1). Nunca escapa UnicodeDecodeError cruda.

Caso reproducible mínimo: la muestra de 8 KB que lee _read_csv_with_fallback
es ASCII puro (decodifica bien en utf-8-sig) pero hay bytes inválidos MÁS
ALLÁ del sample (0x93 = smart quote cp1252).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer import build_file_info, load_dataframe


class TestCsvEncodingFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    @staticmethod
    def _ascii_body(rows: int = 700) -> bytes:
        return b"".join(f"Usuario{i},x,Salta\n".encode("ascii") for i in range(rows))

    def test_bad_bytes_beyond_sample_with_blank_header_loads_via_fallback(self):
        # Header con columna vacía -> ruta de auto-renombre. El error de utf-8
        # aparece solo al leer el archivo COMPLETO (más allá del sample de 8KB).
        # DEBE rescatarse vía cp1252, igual que un archivo con header completo.
        # PROHIBIDO: que escape UnicodeDecodeError cruda al llamador.
        header = b"Nombre,,Ciudad\n"  # columna vacía -> _read_csv_renamed_headers
        tail = b"Luis,\x93 7 \x94,CABA\n"
        p = self.tmp / "mojibake_blank_header.csv"
        p.write_bytes(header + self._ascii_body() + tail)

        df = load_dataframe(build_file_info(p))  # no UnicodeDecodeError
        self.assertEqual(len(df), 701)  # 700 filas ASCII + la fila rescatada

    def test_bad_bytes_beyond_sample_with_valid_header_loads_via_fallback(self):
        # Ruta NORMAL (header completo): comportamiento de referencia, ya funcionaba.
        # La ruta de auto-renombre debe ser equivalente.
        header = b"Nombre,Nota,Ciudad\n"
        tail = b"Luis,\x93 7 \x94,CABA\n"
        p = self.tmp / "mojibake_valid_header.csv"
        p.write_bytes(header + self._ascii_body() + tail)

        df = load_dataframe(build_file_info(p))  # no UnicodeDecodeError
        self.assertEqual(len(df), 701)

    def test_valid_latin1_file_still_loads(self):
        # El fallback multi-encoding sigue vivo: cp1252/latin-1 válidos cargan bien.
        p = self.tmp / "latin.csv"
        p.write_bytes("Nombre,Ciudad\nJosé,Málaga\n".encode("cp1252"))
        df = load_dataframe(build_file_info(p))
        self.assertEqual(list(df.columns), ["Nombre", "Ciudad"])
        self.assertEqual(df.iloc[0, 0], "José")

    def test_utf8_file_still_prefers_utf8(self):
        # Un archivo utf-8 genuino no debe degradarse a cp1252.
        p = self.tmp / "utf8.csv"
        p.write_text("Nombre,Ciudad\nJosé,Málaga\n", encoding="utf-8")
        df = load_dataframe(build_file_info(p))
        self.assertEqual(df.iloc[0, 0], "José")


if __name__ == "__main__":
    unittest.main()
