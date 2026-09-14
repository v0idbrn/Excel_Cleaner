"""tests/test_gui_clean_flow.py — Regresión TDD del flujo central de la GUI.

Cubre el flujo "3. Aplicar Limpieza" (Cleaner -> Validator -> estado exportable):

  ANTES: gui/app.py llamaba validate_cleaning() SIN importarlo: el worker
         capturaba el NameError y la cola recibía un ERROR genérico
         ("Error en Cleaner/Validator: name 'validate_cleaning' is not defined").
         TODA limpieza desde la GUI fallaba aunque los datos y las acciones
         fueran perfectamente válidas. Además, _handle_worker_message anotaba
         `ai_response: AIResponse` sin importar AIResponse (NameError latente).
  DESPUÉS: el flujo completo carga -> limpia -> valida -> habilita export,
         usando el mismo camino que usa el botón real (_worker_clean_validate).
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.app import ExcelCleanerApp  # noqa: E402
from models import CleaningAction  # noqa: E402


class TestGuiCleanValidateFlow(unittest.TestCase):
    """El worker real de la GUI debe producir validación OK y export habilitado."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as exc:  # sin display (CI headless): saltar la suite
            raise unittest.SkipTest(f"Tkinter no disponible en este entorno: {exc}")

    def setUp(self):
        self.app = ExcelCleanerApp(self.root)
        # Dataset trivial: trim sobre una columna con espacios.
        self.app.original_df = pd.DataFrame({"Nombre": ["  Ana  ", "Beto"]})
        self.app.current_filepath = "test.csv"
        self.app.actions = (
            CleaningAction(
                action_id="trim_espacios",
                column="Nombre",
                description="Trim",
                approved=True,
            ),
        )

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _drain_queue(self):
        while not self.app.task_queue.empty():
            self.app.task_queue.get_nowait()

    def test_clean_validate_worker_produces_valid_result(self):
        self._drain_queue()
        self.app._worker_clean_validate()

        msg_type, data = self.app.task_queue.get_nowait()
        self.assertEqual(msg_type, "CLEAN_VALIDATE_DONE")
        cleaned_df, cleaning_res, val_result = data
        self.assertTrue(val_result.valid, f"Errores: {val_result.errors}")
        self.assertEqual(list(cleaned_df["Nombre"]), ["Ana", "Beto"])
        self.assertEqual(cleaning_res.rows_before, 2)

    @patch("gui.app.messagebox.showinfo")
    def test_clean_validate_message_enables_export(self, _mock_msg):
        self._drain_queue()
        self.app._worker_clean_validate()
        # Procesar el mensaje como lo haría el loop real (check_queue).
        # messagebox se parchea: showinfo es un diálogo modal real.
        while not self.app.task_queue.empty():
            self.app._handle_worker_message(*self.app.task_queue.get_nowait())
        self.assertEqual(str(self.app.dashboard.btn_export["state"]), tk.NORMAL)

    def test_worker_swallows_nothing_silently_on_error(self):
        # Si algo falla, el error DEBE llegar a la cola (cero excepciones silenciosas).
        self.app.original_df = None
        self._drain_queue()
        self.app._worker_clean_validate()
        msg_type, data = self.app.task_queue.get_nowait()
        self.assertEqual(msg_type, "ERROR")

    def test_ai_worker_posts_ai_done_message(self):
        # La ruta de IA usa la anotación AIResponse; el worker no debe reventar.
        from models import AIResponse

        self.app.last_report = object()  # truthy; generate_proposals se mockea
        self._drain_queue()
        with patch("gui.app.generate_proposals", return_value=AIResponse(proposals=(), warnings=())):
            self.app._worker_ai()
        msg_type, data = self.app.task_queue.get_nowait()
        self.assertEqual(msg_type, "AI_DONE")


if __name__ == "__main__":
    unittest.main()
