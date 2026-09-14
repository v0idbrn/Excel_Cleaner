"""tests/test_crash_log.py — Regresión del crash log de main.py.

  ANTES: el crash log etiquetaba el tipo de proceso como 'console' cuando
         detectaba PyInstaller (_MEIPASS) — la etiqueta correcta sería
         'windowed (PyInstaller)' — y en desarrollo imprimía 'desconocido',
         poco útil para soporte. Además la cabecera prometía información
         que no siempre era cierta.
  DESPUÉS: la etiqueta es honesta y diagnosticable en ambos entornos:
         'windowed (PyInstaller)' con _MEIPASS, 'python (desarrollo)' sin él.
         El log siempre contiene excepción, entorno y traceback.

Estos tests NO requieren display (no tocan Tk).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as app_main  # noqa: E402


class TestCrashLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._dir_patcher = patch.object(app_main, "_crash_log_dir", return_value=self.tmp)
        self._dir_patcher.start()
        self.addCleanup(self._dir_patcher.stop)

    def _write(self):
        try:
            raise ValueError("boom-de-prueba")
        except ValueError as exc:
            log_path, status = app_main._write_crash_log(type(exc), exc, exc.__traceback__)
        return Path(log_path), status

    def test_crash_log_written_with_status_ok(self):
        log_path, status = self._write()
        self.assertTrue(log_path.exists(), "El crash log debe escribirse en el directorio configurado")
        self.assertEqual(status, "ok")

    def test_crash_log_content_is_diagnosticable(self):
        log_path, _ = self._write()
        content = log_path.read_text(encoding="utf-8")
        self.assertIn("EXCEL CLEANER", content)
        self.assertIn("ValueError", content)
        self.assertIn("boom-de-prueba", content)
        self.assertIn("Traceback", content)
        # Etiqueta de proceso honesta (develop env sin _MEIPASS)
        self.assertIn("python (desarrollo)", content)
        self.assertNotIn("desconocido", content)

    def test_process_label_is_pyinstaller_when_frozen(self):
        with patch.object(sys, "_MEIPASS", "/fake/_MEIPASS", create=True):
            log_path, _ = self._write()
        content = log_path.read_text(encoding="utf-8")
        self.assertIn("pyinstaller (empaquetado)", content)


if __name__ == "__main__":
    unittest.main()
