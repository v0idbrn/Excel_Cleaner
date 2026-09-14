"""Pruebas de integración del flujo de usuario (acciones GUI -> Cleaner -> Validator -> Export).

Verifica el contrato completo desde lo que el usuario aprueba en el panel hasta el
archivo exportado, incluyendo la fidelidad de parámetros (dayfirst, locale) y la
barrera Zero-Trust. Patrón función, consistente con el resto de las suites.

Ejecutar:  python tests/test_user_workflow.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exporter import export_dataframe, generate_audit_report, export_audit_report
from gui.issues_panel import IssuesPanel
from models import CleaningAction, CleaningResult, ValidationResult
from validators import validate_cleaning

_CHECKS = {"pass": 0, "fail": 0}


def _check(condition: bool, description: str) -> None:
    if condition:
        _CHECKS["pass"] += 1
        print(f"  [OK] {description}")
    else:
        _CHECKS["fail"] += 1
        print(f"  [FAIL] {description}")


def _simulate_panel(actions_in: tuple[CleaningAction, ...], approved_flags: tuple[bool, ...]) -> tuple[CleaningAction, ...]:
    """Simula el panel real: populate + toggles del usuario + get_approved_actions.

    Requiere display: en CI headless (sin Xvfb) salta vía unittest.SkipTest,
    que main() cuenta como PASS parcial pero visible ("SKIP")."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as exc:  # sin display (CI headless)
        raise unittest.SkipTest(f"Tkinter no disponible en este entorno: {exc}")
    root.withdraw()
    try:
        panel = IssuesPanel(root)
        panel.populate(actions_in)
        for var, flag in zip(panel.action_vars, approved_flags):
            var.set(flag)  # equivalente exacto a un clic del usuario
        return panel.get_approved_actions()
    finally:
        root.destroy()


def test_actions_roundtrip_preserves_parameters() -> None:
    print("\n--- W1: Round-trip del panel: parameters y source sobreviven ---")
    actions_in = (
        CleaningAction("normalizar_fechas", "Fecha", "[IA Conf: 0.9] Fechas", approved=False,
                       parameters={"dayfirst": False}, source="ai"),
        CleaningAction("normalizar_numerico", "Monto", "Monetario", approved=False,
                       parameters={"locale": "eu"}, source="analyzer"),
        CleaningAction("trim_espacios", "Nombre", "Trim", approved=False, source="analyzer"),
    )
    out = _simulate_panel(actions_in, (True, True, False))

    _check(out[0].parameters == {"dayfirst": False}, f"dayfirst preservado: {out[0].parameters}")
    _check(out[0].source == "ai", f"source preservado: {out[0].source}")
    _check(out[1].parameters == {"locale": "eu"}, f"locale preservado: {out[1].parameters}")
    _check(out[2].parameters == {} and out[2].source == "analyzer", "Acción simple intacta")
    _check(out[0].approved and out[1].approved and not out[2].approved, "Estados de aprobación correctos")


def test_approved_gui_actions_pass_validator_and_export() -> None:
    print("\n--- W2: Acciones aprobadas en panel -> Cleaner -> Validator OK -> Export ---")
    df = pd.DataFrame({
        "Fecha": ["2026-05-12", "13/05/2026", "basura"],
        "Monto": ["1.250,50", "$ 500.00", "X"],
    }).astype("string")

    actions_in = (
        CleaningAction("normalizar_fechas", "Fecha", "Fechas", approved=False,
                       parameters={"dayfirst": True}, source="analyzer"),
        CleaningAction("normalizar_numerico", "Monto", "Monetario", approved=False,
                       parameters={"locale": "auto"}, source="analyzer"),
    )
    approved = _simulate_panel(actions_in, (True, True))

    from cleaner import clean_dataframe
    df_clean, result = clean_dataframe(df, approved)
    validation = validate_cleaning(df, df_clean, approved, result)

    _check(validation.valid, f"Validator aprueba acciones con parámetros: {validation.errors}")
    _check(set(df_clean["Fecha"].dropna()) == {"2026-05-12", "2026-05-13"}, "Fechas ISO con dayfirst del panel")
    montos = pd.to_numeric(df_clean["Monto"], errors="coerce").tolist()
    _check(abs(montos[0] - 1250.5) < 0.01 and abs(montos[1] - 500.0) < 0.01, f"Montos locale-aware: {montos}")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "salida.csv"
        res = export_dataframe(df_clean, out, validation, overwrite=True)
        _check(res.success and out.exists(), "Export permitido tras validación")
        report = generate_audit_report("origen.csv", res.path, result, validation, df, df_clean)
        audit_path = export_audit_report(report, output_dir=Path(tmp), format="txt")
        _check(Path(audit_path).exists(), "Reporte de auditoría generado en el flujo completo")


def test_mutation_attempt_blocked_end_to_end() -> None:
    print("\n--- W3: Mutación simulada -> Validator bloquea -> ZERO-WRITE ---")
    df = pd.DataFrame({"V": ["1", "2"]})
    actions = (CleaningAction("trim_espacios", "V", "Trim", approved=True),)
    result = CleaningResult(
        actions_applied=actions, rows_before=2, rows_after=2,
        columns_before=1, columns_after=1,
    )
    # Ataque: el "resultado" fue alterado tras la limpieza
    df_attacked = df.copy()
    df_attacked.loc[0, "V"] = "999"

    validation = validate_cleaning(df, df_attacked, actions, result)
    _check(not validation.valid, "Validator detecta la mutación")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ataque.csv"
        from exporter import ExportError
        try:
            export_dataframe(df_attacked, out, validation, overwrite=True)
            _check(False, "Export debe lanzar ExportError")
        except ExportError:
            _check(True, "ExportError: ZERO-WRITE respetado")
        _check(not out.exists(), "Ningún archivo creado")


def main() -> int:
    print("=" * 70)
    print("TESTS DE FLUJO DE USUARIO (panel -> cleaner -> validator -> export)")
    print("=" * 70)
    # Los tests que usan el panel real requieren display: en CI headless el
    # SkipTest se reporta como SKIP (visible) y NO cuenta como fallo.
    skipped = 0
    for test_fn in (
        test_actions_roundtrip_preserves_parameters,
        test_approved_gui_actions_pass_validator_and_export,
        test_mutation_attempt_blocked_end_to_end,
    ):
        try:
            test_fn()
        except unittest.SkipTest as exc:
            skipped += 1
            print(f"  [SKIP] {test_fn.__name__}: {exc}")
    print("\n" + "=" * 70)
    print(f"RESULTADO: {_CHECKS['pass']} PASS / {_CHECKS['fail']} FAIL / {skipped} SKIP")
    print("=" * 70)
    return 0 if _CHECKS["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
