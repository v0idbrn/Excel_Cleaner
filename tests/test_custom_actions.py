"""Tests de Acciones Personalizadas (Fase 9.1): dedup por columna, dividir, unir, reemplazar.

Cobertura:
  1. Builders puros de gui.app (validaciones y acción generada) — sin Tkinter.
  2. Handler on_custom end-to-end con diálogos simulados (stub de simpledialog/messagebox).
  3. Round-trip Zero-Trust: acción creada pendiente -> aprobada -> Cleaner -> Validator
     -> export -> reporte de auditoría menciona la acción.
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.app import (  # noqa: E402
    ExcelCleanerApp,
    _build_dedup_action,
    _build_merge_action,
    _build_replace_action,
    _build_split_action,
    _parse_column_list,
)
from models import CleaningAction  # noqa: E402


class TestPureBuilders(unittest.TestCase):
    """Los builders validan la entrada y producen acciones PENDIENTES (approved=False)."""

    def test_parse_column_list_ok_y_errores(self):
        avail = ["Email", "ID", "Teléfono"]
        self.assertEqual(_parse_column_list("Email, ID", avail), ["Email", "ID"])
        self.assertEqual(_parse_column_list("  ID  ", avail), ["ID"])
        with self.assertRaises(ValueError):
            _parse_column_list(None, avail)
        with self.assertRaises(ValueError):
            _parse_column_list("   ", avail)
        with self.assertRaises(ValueError):
            _parse_column_list("Email, NoExiste", avail)

    def test_build_dedup_action(self):
        act = _build_dedup_action(["Email", "ID"], "first")
        self.assertIsInstance(act, CleaningAction)
        self.assertEqual(act.action_id, "eliminar_duplicados_por_columna")
        self.assertFalse(act.approved)  # SIEMPRE pendiente
        self.assertEqual(act.parameters, {"subset_columns": ["Email", "ID"], "keep": "first"})
        with self.assertRaises(ValueError):
            _build_dedup_action([], "first")
        with self.assertRaises(ValueError):
            _build_dedup_action(["Email"], "middle")

    def test_build_split_action(self):
        act = _build_split_action("Nombre", " ", ["Nombre", "Apellido"], ["Nombre", "Edad"])
        self.assertEqual(act.action_id, "dividir_columna")
        self.assertFalse(act.approved)
        self.assertEqual(act.parameters["delimiter"], " ")
        self.assertEqual(act.parameters["new_column_names"], ["Nombre", "Apellido"])
        # Delimitador vacío
        with self.assertRaises(ValueError):
            _build_split_action("Nombre", "", ["A"], ["Nombre"])
        # Colisión con columna existente
        with self.assertRaises(ValueError):
            _build_split_action("Nombre", " ", ["Edad"], ["Nombre", "Edad"])
        # Nombres repetidos
        with self.assertRaises(ValueError):
            _build_split_action("Nombre", " ", ["A", "A"], ["Nombre"])
        # Columna inexistente
        with self.assertRaises(ValueError):
            _build_split_action("Fantasma", " ", ["A"], ["Nombre"])

    def test_build_merge_action(self):
        act = _build_merge_action(["Nombre", "Apellido"], "Full", "-", True, ["Nombre", "Apellido"])
        self.assertEqual(act.action_id, "unir_columnas")
        self.assertFalse(act.approved)
        self.assertEqual(act.parameters["new_column_name"], "Full")
        self.assertTrue(act.parameters["drop_source_columns"])
        # Colisión: destino existe y NO es fuente
        with self.assertRaises(ValueError):
            _build_merge_action(["Nombre"], "Apellido", " ", False, ["Nombre", "Apellido"])
        # Fuente inexistente
        with self.assertRaises(ValueError):
            _build_merge_action(["NoExiste"], "X", " ", False, ["Nombre"])
        # Sin nombre destino
        with self.assertRaises(ValueError):
            _build_merge_action(["Nombre"], "  ", " ", False, ["Nombre"])

    def test_build_replace_action(self):
        act = _build_replace_action(
            "V", [{"find": "N/A", "replace": None, "match": "exact"}], ["V", "W"]
        )
        self.assertEqual(act.action_id, "reemplazar_valores")
        self.assertFalse(act.approved)
        self.assertEqual(act.parameters["mappings"], [{"find": "N/A", "replace": None, "match": "exact"}])
        # Sin reglas
        with self.assertRaises(ValueError):
            _build_replace_action("V", [], ["V"])
        # find vacío
        with self.assertRaises(ValueError):
            _build_replace_action("V", [{"find": "", "replace": None, "match": "exact"}], ["V"])
        # Modo inválido
        with self.assertRaises(ValueError):
            _build_replace_action("V", [{"find": "a", "replace": "b", "match": "como"}], ["V"])
        # Regex inválida se detecta ANTES de llegar al motor
        with self.assertRaises(ValueError):
            _build_replace_action("V", [{"find": "([", "replace": "x", "match": "regex"}], ["V"])
        # Regex válida pasa
        ok = _build_replace_action("V", [{"find": r"x(\d)y", "replace": r"n=\1", "match": "regex"}], ["V"])
        self.assertEqual(ok.parameters["mappings"][0]["match"], "regex")


class TestCustomHandlerEndToEnd(unittest.TestCase):
    """El handler crea la acción pendiente, la muestra en el panel y permite el flujo completo."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as exc:  # sin display (CI headless): saltar la suite
            raise unittest.SkipTest(f"Tkinter no disponible en este entorno: {exc}")

    def setUp(self):
        self.app = ExcelCleanerApp(self.root)
        self.app.original_df = pd.DataFrame({
            "Nombre Completo": ["Ana Silva", "Juan Perez"],
            "Email": ["a@x.com", "a@x.com"],
        })
        # TODOS los diálogos van simulados: un messagebox real bloquearía el test
        # esperando un clic humano (lección de la primera corrida).
        # Los mocks se enchufan a los SEAMS de diálogo (gui.app._ask_*), que es
        # por donde ahora pasa la conversación. _ask_option y _ask_text comparten
        # UN mock de askstring: las secuencias side_effect de los tests describen
        # la conversación completa en orden (menú -> prompts).
        import gui.app as gui_app
        for target, attr in (("gui.app.messagebox", "showerror"),
                             ("gui.app.messagebox", "showinfo"),
                             ("gui.app.messagebox", "showwarning"),
                             ("gui.app.messagebox", "askyesno")):
            patcher = patch(f"{target}.{attr}")
            setattr(self, f"mock_{attr}", patcher.start())
            self.addCleanup(patcher.stop)

        shared_dialog = MagicMock(name="simpledialog_shared")
        self.mock_simpledialog = shared_dialog  # compat: .askstring.side_effect = [...]
        for seam in ("_ask_option", "_ask_text"):
            patcher = patch.object(gui_app, seam, new=shared_dialog.askstring)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(gui_app, "_ask_yes_no",
                               new=lambda *a, **k: self.mock_askyesno(*a, **k))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _approve_all(self):
        for var in self.app.issues_panel.action_vars:
            var.set(True)
        self.app.actions = self.app.issues_panel.get_approved_actions()

    def test_handler_crea_dedup_pendiente(self):
        self.mock_simpledialog.askstring.side_effect = ["1", "Email", "first"]
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 1)
        act = self.app.actions[0]
        self.assertEqual(act.action_id, "eliminar_duplicados_por_columna")
        self.assertFalse(act.approved)  # Pendiente: NADA se ejecuta sin aprobación
        self.assertEqual(len(self.app.issues_panel.action_vars), 1)

    def test_handler_valida_columna_inexistente(self):
        self.mock_simpledialog.askstring.side_effect = ["1", "NoExiste"]
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 0)  # Rechazada con mensaje, no agregada
        self.mock_showerror.assert_called_once()  # mensaje amable, sin crash

    def test_handler_split_completo_hasta_validator(self):
        self.mock_simpledialog.askstring.side_effect = ["2", "Nombre Completo", " ", "Nombre, Apellido"]
        self.app.on_custom()
        self._approve_all()
        from cleaner import clean_dataframe
        from models import CleaningResult
        from validators import validate_cleaning

        dfc, res = clean_dataframe(self.app.original_df, self.app.actions)
        val = validate_cleaning(self.app.original_df, dfc, self.app.actions,
                                CleaningResult(self.app.actions, 2, 2, 2, 3, res.warnings))
        self.assertTrue(val.valid)
        self.assertEqual(list(dfc.columns), ["Nombre", "Apellido", "Email"])

    def test_handler_merge_completo_hasta_validator(self):
        self.mock_simpledialog.askstring.side_effect = ["3", "Nombre Completo", "Full", "-"]
        self.mock_askyesno.return_value = False
        self.app.on_custom()
        self._approve_all()
        from cleaner import clean_dataframe
        from models import CleaningResult
        from validators import validate_cleaning

        dfc, res = clean_dataframe(self.app.original_df, self.app.actions)
        val = validate_cleaning(self.app.original_df, dfc, self.app.actions,
                                CleaningResult(self.app.actions, 2, 2, 2, 3, res.warnings))
        self.assertTrue(val.valid)
        self.assertIn("Full", dfc.columns)
        self.assertEqual(list(dfc["Full"]), ["Ana Silva", "Juan Perez"])

    def test_handler_replace_basura_a_nulo_hasta_validator(self):
        self.app.original_df = pd.DataFrame({"V": ["N/A", "10"], "W": ["a", "b"]})
        self.mock_simpledialog.askstring.side_effect = ["4", "V", "N/A", "", "exact"]
        self.app.on_custom()
        self._approve_all()
        from cleaner import clean_dataframe
        from models import CleaningResult
        from validators import validate_cleaning

        dfc, res = clean_dataframe(self.app.original_df, self.app.actions)
        val = validate_cleaning(self.app.original_df, dfc, self.app.actions,
                                CleaningResult(self.app.actions, 2, 2, 2, 2, res.warnings))
        self.assertTrue(val.valid)
        self.assertTrue(pd.isna(dfc["V"].iloc[0]))
        self.assertEqual(dfc["V"].iloc[1], "10")

    def test_handler_opcion_invalida(self):
        self.mock_simpledialog.askstring.side_effect = ["9"]
        self.app.on_custom()
        self.assertEqual(len(self.app.actions), 0)
        self.mock_showerror.assert_called_once()


class TestAuditReportIncludesCustomActions(unittest.TestCase):
    """El reporte de auditoría final registra las acciones personalizadas ejecutadas."""

    def test_audit_report_registra_acciones_personalizadas(self):
        import tempfile

        from exporter import export_audit_report, export_dataframe, generate_audit_report
        from models import CleaningResult
        from validators import validate_cleaning

        df = pd.DataFrame({"Nombre Completo": ["Ana Silva", "Juan Perez"], "Email": ["a@x.com", "a@x.com"]})
        actions = (
            _build_split_action("Nombre Completo", " ", ["Nombre", "Apellido"], list(df.columns)),
            _build_dedup_action(["Email"], "first"),
        )
        actions = tuple(CleaningAction(a.action_id, a.column, a.description, approved=True,
                                       parameters=a.parameters, source=a.source) for a in actions)
        from cleaner import clean_dataframe

        dfc, res = clean_dataframe(df, actions)
        val = validate_cleaning(df, dfc, actions, CleaningResult(actions, 2, 1, 2, 3, res.warnings))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.csv"
            export_dataframe(dfc, out, val)
            rep = generate_audit_report("origen.xlsx", out, res, val, df, dfc)
            p = Path(export_audit_report(rep, output_dir=td, format="txt"))
            txt = p.read_text(encoding="utf-8")
            self.assertIn("dividir_columna", txt)
            self.assertIn("eliminar_duplicados_por_columna", txt)
            self.assertIn("Deduplicación por criterio", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
