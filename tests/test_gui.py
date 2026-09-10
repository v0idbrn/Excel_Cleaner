"""Pruebas unitarias y de integración para la GUI MVP (Fase 6)."""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.app import ExcelCleanerApp
from models import CleaningAction, ExportResult, ValidationResult


class TestExcelCleanerGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw() # Ocultar ventana para tests

    def setUp(self):
        self.app = ExcelCleanerApp(self.root)

    # Test 1 & 14: Inicio y Reset
    def test_startup_and_reset(self):
        self.app.reset_state()
        self.assertEqual(str(self.app.dashboard.btn_analyze['state']), tk.DISABLED)
        self.assertEqual(str(self.app.dashboard.btn_clean['state']), tk.DISABLED)
        self.assertEqual(str(self.app.dashboard.btn_export['state']), tk.DISABLED)
        self.assertIsNone(self.app.original_df)

    # Test 2, 3: Selección de archivo (simulada via mensajes de worker)
    def test_file_load_state_transition(self):
        self.app.original_df = pd.DataFrame({"A": [1]})
        self.app.current_filename = "test.csv"
        self.app._handle_worker_message("LOAD_DONE", None)
        self.assertEqual(str(self.app.dashboard.btn_analyze['state']), tk.NORMAL)
        self.assertEqual(str(self.app.dashboard.btn_export['state']), tk.DISABLED)

    # Test 4, 6, 7: Flujo de Analyzer y Renderizado del Issues Panel
    def test_analysis_and_issues_population(self):
        report_mock = MagicMock()
        report_mock.actions = [
            CleaningAction("trim_espacios", "A", "Trim", approved=True),
            CleaningAction("normalizar_fechas", "B", "Fechas", approved=True,
                           parameters={"dayfirst": True}),
        ]
        self.app._handle_worker_message("ANALYSIS_DONE", report_mock)
        
        self.assertEqual(str(self.app.dashboard.btn_clean['state']), tk.NORMAL)
        self.assertEqual(len(self.app.issues_panel.action_vars), 2)
        
        # El usuario desmarca la segunda acción (mismo camino que un clic real)
        self.app.issues_panel.action_vars[1].set(False)
        
        actions = self.app.issues_panel.get_approved_actions()
        self.assertTrue(actions[0].approved)
        self.assertFalse(actions[1].approved)
        # FIDELIDAD: parameters y source deben sobrevivir al round-trip del panel
        self.assertEqual(actions[1].parameters, {"dayfirst": True})
        self.assertEqual(actions[1].source, "analyzer")

    # Test 9, 10, 11: Integración Cleaner -> Validator FAIL/PASS
    @patch('gui.app.messagebox.showerror')
    def test_clean_validate_fail_blocks_export(self, mock_msg):
        self.app.validation_result = ValidationResult(valid=False, errors=("Test Error",), warnings=())
        self.app._handle_worker_message("CLEAN_VALIDATE_DONE", (MagicMock(), MagicMock(), self.app.validation_result))
        self.assertEqual(str(self.app.dashboard.btn_export['state']), tk.DISABLED)
        self.assertTrue(mock_msg.called)

    @patch('gui.app.messagebox.showinfo')
    def test_clean_validate_pass_enables_export(self, mock_msg):
        self.app.validation_result = ValidationResult(valid=True, errors=(), warnings=())
        self.app._handle_worker_message("CLEAN_VALIDATE_DONE", (MagicMock(), MagicMock(), self.app.validation_result))
        self.assertEqual(str(self.app.dashboard.btn_export['state']), tk.NORMAL)

    # Test 12, 13: Exporter y Excepciones
    @patch('gui.app.messagebox.showinfo')
    def test_export_success(self, mock_msg):
        res = ExportResult(True, "path.csv", 10, 2)
        self.app._handle_worker_message("EXPORT_DONE", res)
        self.assertTrue(mock_msg.called)
        
    @patch('gui.app.messagebox.showerror')
    def test_export_error_handling(self, mock_msg):
        self.app._handle_worker_message("ERROR", "Export Error")
        self.assertTrue(mock_msg.called)

    # TEST DE SEGURIDAD (Ataque a la GUI)
    @patch('gui.app.messagebox.showerror')
    @patch('gui.app.filedialog.asksaveasfilename')
    def test_security_export_button_bypass(self, mock_save, mock_err):
        """Simula forzar el clic en exportar cuando valid=False."""
        self.app.validation_result = ValidationResult(valid=False)
        self.app.on_export() # Bypass del botón DISABLED
        self.assertFalse(mock_save.called) # El diálogo ni siquiera debe abrirse
        self.assertTrue(mock_err.called) # Debe lanzar popup de seguridad

if __name__ == '__main__':
    unittest.main()