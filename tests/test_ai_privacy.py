# -*- coding: utf-8 -*-
"""Tests de privacidad para el payload de IA (Fase 7, metadata-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import _build_safe_payload, _build_prompt, _parse_and_validate, generate_proposals
from models import AnalysisReport, ColumnStats, FileInfo, FileType, Issue, Severity


def _check(condition, description):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def test_payload_no_cell_values():
    print("\n--- Test: payload no contiene valores de celdas ---")
    report = AnalysisReport(
        file_info=FileInfo(
            Path("clientes_confidenciales.csv"),
            FileType.CSV,
            77777,
            ("Hoja1",),
        ),
        sheet_name="Hoja1",
        row_count=5,
        column_count=3,
        column_stats=(
            ColumnStats(
                "RazonSocial",
                "object",
                5,
                0,
                5,
                sample_values=(
                    "Juan Perez S.A.",
                    "Maria Garcia Ltda.",
                    "Carlos Dominguez SRL",
                ),
            ),
            ColumnStats(
                "EmailContacto",
                "object",
                5,
                1,
                4,
                sample_values=(
                    "juan@empresa.com",
                    "maria@empresa.com",
                    "carlos@empresa.com",
                ),
            ),
            ColumnStats(
                "Telefono",
                "object",
                4,
                1,
                3,
                sample_values=(
                    "+54 11 5555-1234",
                    "+54 911 98765-4321",
                    "+54 11 4444-5678",
                ),
            ),
        ),
        issues=(
            Issue(
                "ESPACIOS",
                "RazonSocial",
                Severity.LOW,
                "Espacios al inicio/final",
                3,
                5,
                examples=(
                    " Juan Perez S.A. ",
                    " Maria Garcia Ltda. ",
                    " Carlos Dominguez SRL ",
                ),
                suggested_action="trim_espacios",
            ),
            Issue(
                "TELEFONOS_SOSPECHOSOS",
                "Telefono",
                Severity.LOW,
                "Formato de teléfono atipico",
                1,
                4,
                examples=("+54 911 98765-4321",),
                suggested_action="revisar_manualmente",
            ),
        ),
    )

    payload = _build_safe_payload(report)
    payload_str = json.dumps(payload, ensure_ascii=True)

    secret_tokens = [
        "Juan Perez S.A.",
        "Maria Garcia Ltda.",
        "Carlos Dominguez SRL",
        "juan@empresa.com",
        "maria@empresa.com",
        "carlos@empresa.com",
        "+54 11 5555-1234",
        "+54 911 98765-4321",
        "+54 11 4444-5678",
        " Juan Perez S.A. ",
        " Maria Garcia Ltda. ",
        " Carlos Dominguez SRL ",
    ]

    leak = [token for token in secret_tokens if token in payload_str]
    _check(len(leak) == 0, "No se filtraron valores de celdas al payload")

    _check("RazonSocial" in payload_str, "Los nombres de columna SI pueden llegar (OK esperado)")
    _check("EmailContacto" in payload_str, "Los nombres de columna SI pueden llegar (OK esperado)")
    _check("Telefono" in payload_str, "Los nombres de columna SI pueden llegar (OK esperado)")


def test_prompt_no_cell_values():
    print("\n--- Test: prompt no contiene valores de celdas ---")
    report = AnalysisReport(
        file_info=FileInfo(
            Path("demo.csv"),
            FileType.CSV,
            1234,
            ("Hoja1",),
        ),
        sheet_name="Hoja1",
        row_count=3,
        column_count=2,
        column_stats=(
            ColumnStats(
                "Nombre",
                "object",
                3,
                0,
                3,
                sample_values=("Harry Potter", "Hermione Granger", "Ron Weasley"),
            ),
            ColumnStats(
                "Email",
                "object",
                3,
                0,
                3,
                sample_values=(
                    "harry@hogwarts.uk",
                    "hermione@hogwarts.uk",
                    "ron@hogwarts.uk",
                ),
            ),
        ),
        issues=(
            Issue(
                "ESPACIOS",
                "Nombre",
                Severity.LOW,
                "Espacios al inicio/final",
                2,
                3,
                examples=(" Harry Potter ", " Hermione Granger "),
                suggested_action="trim_espacios",
            ),
            Issue(
                "INCONSISTENCIA_MAYUSCULAS",
                "Nombre",
                Severity.LOW,
                "Variacion en mayusculas",
                1,
                3,
                examples=("Ron Weasley",),
                suggested_action="normalizar_mayusculas",
            ),
        ),
    )

    prompt = _build_prompt(_build_safe_payload(report))
    secret_tokens = [
        "Harry Potter",
        "Hermione Granger",
        "Ron Weasley",
        "harry@hogwarts.uk",
        "hermione@hogwarts.uk",
        "ron@hogwarts.uk",
        " Harry Potter ",
        " Hermione Granger ",
        "hogwarts",
        "wizard",
        "Voldemort",
        "Slytherin",
    ]

    leak = [token for token in secret_tokens if token in prompt]
    _check(len(leak) == 0, "No se filtraron valores de celdas al prompt")

    _check("Nombre" in prompt, "Los nombres de columna SI pueden llegar (OK esperado)")
    _check("Email" in prompt, "Los nombres de columna SI pueden llegar (OK esperado)")


def test_parse_structural_validation():
    from ai import VALID_AI_ACTIONS, _parse_and_validate
    print("\n--- Test: validacion estructural del parser ---")
    print("\n--- Test: validación estructural del parser ---")
    from ai import VALID_AI_ACTIONS

    valid = {"proposals": [{"action": "trim_espacios", "column": "Nombre", "reason": "Espacios", "confidence": 0.9}]}
    r = _parse_and_validate(valid)
    _check(len(r.proposals) == 1, "JSON valido aceptado")
    _check(r.proposals[0].action in VALID_AI_ACTIONS, "Action whitelist validada")

    no_list = {"proposals": "no_es_array"}
    r = _parse_and_validate(no_list)
    _check(len(r.proposals) == 0 and any("no contiene una lista" in w for w in r.warnings), "JSON sin lista rechazado")

    missing_key = {}
    r = _parse_and_validate(missing_key)
    _check(len(r.proposals) == 0 and any("no generó ninguna propuesta" in w for w in r.warnings), "JSON sin key proposals rechazado")

    unknown_action = {"proposals": [{"action": "borra_todo_en_produccion", "column": None, "reason": "malicia", "confidence": 0.9}]}
    r = _parse_and_validate(unknown_action)
    _check(len(r.proposals) == 0 and any("Acción desconocida" in w for w in r.warnings), "Action no whitelist rechazada")

    bad_confidence = {"proposals": [
        {"action": "trim_espacios", "column": "A", "reason": "x", "confidence": "0.9"},
        {"action": "trim_espacios", "column": "B", "reason": "x", "confidence": 1.5},
        {"action": "trim_espacios", "column": "C", "reason": "x", "confidence": -0.4},
    ]}
    r = _parse_and_validate(bad_confidence)
    _check(len(r.proposals) == 0 and any("no numérica" in w or "fuera de rango" in w for w in r.warnings),
           "Confidence inválida rechazada sin clamping")

    many_proposals = {"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": 0.5}] * 40}
    r = _parse_and_validate(many_proposals)
    _check(len(r.proposals) <= 20 and any("superó el límite de 20" in w for w in r.warnings),
           "Límite de propuestas respetado")

    params_invalid = {"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": 0.7, "parameters": "no_es_dict"}]}
    r = _parse_and_validate(params_invalid)
    _check(len(r.proposals) == 1 and r.proposals[0].parameters == {}, "Parámetros invalidos normalizados de forma segura (no inyectan contenido)")


def main():
    try:
        test_payload_no_cell_values()
        test_prompt_no_cell_values()
        test_parse_structural_validation()
    except AssertionError:
        print("\nFALLÓ ALGÚN TEST DE PRIVACIDAD / IA.")
        return 1
    print("\nTODOS LOS TESTS DE PRIVACIDAD / IA PASARON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
