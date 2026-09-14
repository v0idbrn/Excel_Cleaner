"""tests/test_gui_dialogs.py — Contratos de UI para los flujos de diálogo.

  ANTES: on_custom / on_batch / on_export / on_load_file llamaban directamente
         a tk.simpledialog.askstring / messagebox.askyesno en línea: imposible
         testear el CONTRATO de la conversación (qué se pregunta, en qué orden,
         qué pasa al cancelar) sin reventar los diálogos reales.
  DESPUÉS: la conversación vive en funciones módulo-nivel testeables
         (_ask_option, _ask_text, _ask_yes_no, _ask_sheet) y los handlers solo
         orquestan: cancelar en cualquier paso NO agrega acciones ni arranca
         operaciones; entradas inválidas producen showerror amable.
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gui.app as gui_app  # noqa: E402
from gui.app import ExcelCleanerApp  # noqa: E402


class DialogSeamTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as exc:  # sin display (CI headless): saltar la suite
            raise unittest.SkipTest(f"Tkinter no disponible en este entorno: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.app = ExcelCleanerApp(self.root)
        self.app.original_df = pd.DataFrame({
            "Nombre Completo": ["Ana Silva", "Juan Perez"],
            "Email": ["a@x.com", "a@x.com"],
        })
        for name in ("_ask_option", "_ask_text", "_ask_yes_no"):
            patcher = patch.object(gui_app, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.showerror = patch.object(gui_app.messagebox, "showerror").start()
        self.addCleanup(self.showerror.stop)

    def _drain(self):
        while not self.app.task_queue.empty():
            self.app.task_queue.get_nowait()


class TestCustomDialogContract(DialogSeamTestBase):
    def test_menu_then_prompts_create_pending_action(self):
        self._ask_option.return_value = "1"
        self._ask_text.side_effect = ["Email", "first"]
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 1)
        act = self.app.actions[0]
        self.assertEqual(act.action_id, "eliminar_duplicados_por_columna")
        self.assertFalse(act.approved)  # siempre pendiente de aprobación

    def test_cancel_at_menu_creates_nothing(self):
        self._ask_option.return_value = None
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 0)
        self.assertFalse(self.showerror.called)

    def test_cancel_mid_flow_creates_nothing(self):
        self._ask_option.return_value = "1"
        self._ask_text.return_value = None  # cancela columnas criterio
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 0)

    def test_unknown_column_shows_friendly_error(self):
        self._ask_option.return_value = "1"
        self._ask_text.side_effect = ["NoExiste"]
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 0)
        self.showerror.assert_called_once()

    def test_invalid_option_shows_friendly_error(self):
        self._ask_option.return_value = "9"
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 0)
        self.showerror.assert_called_once()

    def test_merge_flow_uses_yes_no_dialog(self):
        self._ask_option.return_value = "3"
        self._ask_text.side_effect = ["Nombre Completo", "Full", "-"]
        self._ask_yes_no.return_value = False
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 1)
        self.assertEqual(self.app.actions[0].action_id, "unir_columnas")
        self._ask_yes_no.assert_called_once()


class TestBatchDialogContract(DialogSeamTestBase):
    def test_invalid_mode_shows_error_without_opening_dirs(self):
        self._ask_option.return_value = "otro"
        with patch.object(gui_app.filedialog, "askdirectory") as mock_dir:
            self.app.on_batch()
        self.showerror.assert_called_once()
        self.assertFalse(mock_dir.called)

    def test_cancel_at_mode_opens_nothing(self):
        self._ask_option.return_value = None
        with patch.object(gui_app.filedialog, "askdirectory") as mock_dir:
            self.app.on_batch()
        self.assertFalse(mock_dir.called)
        self.assertFalse(self.showerror.called)

    def test_cancel_at_output_dir_starts_nothing(self):
        self._ask_option.return_value = "carpeta"
        with patch.object(gui_app.filedialog, "askdirectory", return_value=""):
            self.app.on_batch()
        self._drain()
        self.assertEqual(str(self.app.dashboard.btn_load["state"]), tk.NORMAL)


class TestSheetPickerContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).resolve().parent

    def test_ask_sheet_prompts_with_real_sheet_names(self):
        with patch.object(gui_app.tk.simpledialog, "askstring", return_value="Clientes") as m:
            result = gui_app._ask_sheet(None, ("Ventas", "Clientes"))
        self.assertEqual(result, "Clientes")
        prompt = m.call_args[0][1]
        self.assertIn("Ventas", prompt)
        self.assertIn("Clientes", prompt)


if __name__ == "__main__":
    unittest.main()
