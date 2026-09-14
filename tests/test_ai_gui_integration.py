# -*- coding: utf-8 -*-
"""Tests de integracion GUI con IA (Fase 7)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk
import unittest
from time import sleep

from ai import AIResponse, AIProposal, generate_proposals
from gui.app import ExcelCleanerApp
from models import (
    AnalysisReport,
    AIProposal as AIProposalModel,
    CleaningAction,
    ColumnStats,
    FileInfo,
    FileType,
    Issue,
    Severity,
)


def _check(condition, description):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


class TestGUIWithAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as exc:  # sin display (CI headless): saltar la suite
            raise unittest.SkipTest(f"Tkinter no disponible en este entorno: {exc}")

    def setUp(self):
        self.app = ExcelCleanerApp(self.root)

    def test_ai_button_on_analysis_done(self):
        print("\n--- Test: boton IA habilitado tras analisis ---")
        self.app._handle_worker_message("LOAD_DONE", None)
        self.app.original_df = None
        self.app.on_load_file = lambda: None
        self.app.current_filename = "dummy.csv"
        self.app._handle_worker_message("LOAD_DONE", None)

        report_mock = MagicMock()
        report_mock.actions = []
        report_mock.issues = ()
        self.app._handle_worker_message("ANALYSIS_DONE", report_mock)

        _check(str(self.app.dashboard.btn_ai["state"]) == tk.NORMAL, "Boton IA habilitado tras analisis")
        _check(str(self.app.dashboard.btn_clean["state"]) == tk.NORMAL, "Boton limpiar habilitado")

    def test_ai_done_populates_actions_panel(self):
        print("\n--- Test: AI_DONE pobla panel de acciones ---")
        self.app.original_df = None
        self.app._handle_worker_message("LOAD_DONE", None)
        self.app.current_filename = "dummy.csv"

        report_mock = MagicMock()
        report_mock.actions = []
        report_mock.issues = ()
        self.app._handle_worker_message("ANALYSIS_DONE", report_mock)

        ai_response = AIResponse(
            proposals=(
                AIProposalModel(
                    action="trim_espacios",
                    column="Nombre",
                    reason="Espacios al inicio/final detectados",
                    confidence=0.9,
                    parameters={},
                ),
                AIProposalModel(
                    action="revisar_manualmente",
                    column="Email",
                    reason="Formato sospechoso",
                    confidence=0.7,
                    parameters={},
                ),
            ),
            warnings=(),
        )
        self.app._handle_worker_message("AI_DONE", ai_response)

        actions = self.app.issues_panel.get_approved_actions()
        _check(len(actions) == 2, "Panel contiene 2 acciones de IA")
        _check(actions[0].action_id == "trim_espacios", "Primera accion: trim_espacios")
        _check(actions[0].column == "Nombre", "Primera columna: Nombre")
        _check(actions[0].approved is False, "Por defecto no aprobada")
        _check(actions[1].action_id == "revisar_manualmente", "Segunda accion: revisar_manualmente")
        _check(actions[1].column == "Email", "Segunda columna: Email")

    def test_gui_approved_actions_from_issues_panel(self):
        print("\n--- Test: usuario aprueba/rechaza desde IssuesPanel -> CleaningActions correctas ---")
        self.app.original_df = None
        self.app._handle_worker_message("LOAD_DONE", None)

        report_mock = MagicMock()
        report_mock.actions = []
        report_mock.issues = ()
        self.app._handle_worker_message("ANALYSIS_DONE", report_mock)

        ai_response = AIResponse(
            proposals=(
                AIProposalModel(action="trim_espacios", column="Nombre", reason="trim", confidence=0.9, parameters={}),
                AIProposalModel(action="eliminar_filas_vacias", column=None, reason="filas vacias", confidence=0.8, parameters={}),
            ),
            warnings=(),
        )
        self.app._handle_worker_message("AI_DONE", ai_response)

        panel = self.app.issues_panel
        self.assertEqual(len(panel.current_actions), 2)

        panel.action_vars[0].set(True)
        panel.action_vars[1].set(False)

        approved = panel.get_approved_actions()
        _check(len(approved) == 2, "get_approved_actions devuelve las 2 acciones")
        _check(approved[0].action_id == "trim_espacios", "accion 0 aprobada")
        _check(approved[0].approved is True, "estado approved=True para 0")
        _check(approved[1].action_id == "eliminar_filas_vacias", "accion 1")
        _check(approved[1].approved is False, "estado approved=False para 1")


def _dummy_main_ai_side_effect(*args, **kwargs):
    return AIResponse(
        proposals=(
            AIProposalModel(
                action="trim_espacios",
                column="Email",
                reason="Espacios al final detectados",
                confidence=0.9,
                parameters={},
            ),
        ),
        warnings=(),
    )


def test_on_ai_analyze_invokes_generate_proposals():
    print("\n--- Test: on_ai_analyze invoca generate_proposals correctamente ---")
    app = ExcelCleanerApp(__import__("tkinter").Tk())
    app.withdraw = lambda: None
    app.root.withdraw()

    report = AnalysisReport(
        file_info=FileInfo(Path("dummy.csv"), FileType.CSV, 1234, ("Hoja1",)),
        sheet_name="Hoja1",
        row_count=5,
        column_count=2,
        column_stats=(ColumnStats("A", "object", 5, 0, 3),),
        issues=(Issue("TEST", "A", Severity.LOW, "Test issue", 10, 10, suggested_action="trim_espacios"),),
    )
    app.last_report = report

    with patch("gui.app.generate_proposals", side_effect=_dummy_main_ai_side_effect) as mock_gen:
        app._worker_ai()

        for _ in range(15):
            try:
                _ = app.task_queue.get_nowait()
                break
            except Exception:
                sleep(0.02)
                continue

    _check(mock_gen.called, "generate_proposals fue invocado por el worker")
    if mock_gen.call_args:
        _check(isinstance(mock_gen.call_args[0][0], AnalysisReport), "Worker pasa AnalysisReport a generate_proposals")
    else:
        _check(False, "generate_proposals no fue invocado correctamente")

    # este proceso de test no ejecuta el loop de cola del GUI, de modo que
    # el mensaje que el worker encola puede no estar disponible aqui.
    # por eso solo verificamos aqui la invocacion del worker.


def main():
    try:
        tc = TestGUIWithAI()
        tc.setUpClass()
        tc.setUp()
        tc.test_ai_button_on_analysis_done()
        tc.tearDown = lambda: None
        tc.setUp()
        tc.test_ai_done_populates_actions_panel()
        tc.tearDown = lambda: None
        tc.setUp()
        tc.test_gui_approved_actions_from_issues_panel()
        test_on_ai_analyze_invokes_generate_proposals()
    except unittest.SkipTest as exc:
        # CI headless (sin display): los tests GUI+IA no aplican ahí.
        # Skip visible, NO fallo (el suite unittest de este archivo ya reporta
        # el mismo skip vía setUpClass).
        print(f"\n[SKIP] Tests GUI+IA requieren display: {exc}")
        return 0
    except AssertionError:
        print("\nFALLO ALGUN TEST GUI+IA.")
        return 1
    print("\nTODOS LOS TESTS GUI+IA PASARON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
