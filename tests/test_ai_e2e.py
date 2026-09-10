# -*- coding: ascii -*-
"""Test E2E: Analyzer -> metadata -> AI (mock) -> aprobacion -> CleaningAction -> Cleaner -> Validator.

No depende de Ollama en ejecucion. Usa mock controlado para el flujo de IA.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from ai import AIResponse, AIProposal
from cleaner import clean_dataframe
from models import CleaningAction
from validators import validate_cleaning


def _check(condition, description):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def _build_ai_response_simple_trim():
    return AIResponse(
        proposals=(
            AIProposal(
                action="trim_espacios",
                column="Email",
                reason="Espacios al final detectados en metadata",
                confidence=0.9,
                parameters={},
            ),
        ),
        warnings=(),
    )


def test_e2e_ai_trim_email():
    print("\n--- Test E2E: AI propone trim sobre Email, usuario aprueba, Cleaner -> Validator ---")
    df = pd.DataFrame({
        "Name": [" Grace Hopper "],
        "Email": ["grace@example.com "],
    })

    mock_ai_response = _build_ai_response_simple_trim()

    with patch("ai.generate_proposals", return_value=mock_ai_response):
        ai_response = __import__("ai").generate_proposals(None)

    _check(isinstance(ai_response, AIResponse), "AI devuelve AIResponse")
    _check(len(ai_response.proposals) == 1, "1 propuesta generada por IA")
    _check(ai_response.proposals[0].action == "trim_espacios", "Accion propuesta: trim_espacios")
    _check(ai_response.proposals[0].column == "Email", "Columna propuesta: Email")
    _check(ai_response.proposals[0].confidence == 0.9, "Confidence correcta")

    user_approved_action = CleaningAction(
        action_id=ai_response.proposals[0].action,
        column=ai_response.proposals[0].column,
        description=ai_response.proposals[0].reason,
        approved=True,
        parameters=ai_response.proposals[0].parameters,
        source=ai_response.proposals[0].source,
    )

    cleaned_df, cleaning_result = clean_dataframe(df, (user_approved_action,))
    validation_result = validate_cleaning(df, cleaned_df, (user_approved_action,), cleaning_result)

    _check(cleaned_df["Email"].iloc[0] == "grace@example.com", "Cleaner ejecuto trim sobre Email")
    _check(cleaned_df["Name"].iloc[0] == " Grace Hopper ", "Name sin modificar (no fue aprobado)")
    _check(validation_result.valid, "Validator acepta resultado autorizado")
    _check(df["Email"].iloc[0] == "grace@example.com ", "Original inmutable")
    _check(df["Name"].iloc[0] == " Grace Hopper ", "Original inmutable (Name)")


def test_e2e_ai_propuesta_rechazada_por_usuario():
    print("\n--- Test E2E: IA propone, usuario rechaza, Cleaner no aplica nada ---")
    df = pd.DataFrame({
        "Name": [" Grace Hopper "],
        "Email": ["grace@example.com "],
    })

    mock_ai_response = _build_ai_response_simple_trim()

    with patch("ai.generate_proposals", return_value=mock_ai_response):
        ai_response = __import__("ai").generate_proposals(None)

    rejected_action = CleaningAction(
        action_id=ai_response.proposals[0].action,
        column=ai_response.proposals[0].column,
        description=ai_response.proposals[0].reason,
        approved=False,
        parameters=ai_response.proposals[0].parameters,
        source=ai_response.proposals[0].source,
    )

    cleaned_df, cleaning_result = clean_dataframe(df, (rejected_action,))
    validation_result = validate_cleaning(df, cleaned_df, (rejected_action,), cleaning_result)

    _check(cleaned_df["Email"].iloc[0] == "grace@example.com ", "Email no modificado porque accion rechazada")
    _check(cleaned_df["Name"].iloc[0] == " Grace Hopper ", "Name intacto")
    _check(validation_result.valid, "Validator OK cuando no se aplico mutacion no autorizada")
    _check(cleaning_result.actions_applied == (), "Cleaner no registro acciones aplicadas si no estaban approved")


def test_e2e_ai_multiple_proposals_usuario_aproba_parcial():
    print("\n--- Test E2E: IA propone 2 acciones, usuario aprueba solo 1 ---")
    df = pd.DataFrame({
        "Name": [" Grace Hopper "],
        "Email": ["grace@example.com "],
    })

    ai_response = AIResponse(
        proposals=(
            AIProposal(action="trim_espacios", column="Name", reason="Espacios Name", confidence=0.8, parameters={}),
            AIProposal(action="trim_espacios", column="Email", reason="Espacios Email", confidence=0.9, parameters={}),
        ),
        warnings=(),
    )

    with patch("ai.generate_proposals", return_value=ai_response):
        __import__("ai").generate_proposals(None)

    approved_only_email = CleaningAction(
        action_id="trim_espacios",
        column="Email",
        description="Espacios Email",
        approved=True,
        parameters={},
        source="ai",
    )
    rejected_name = CleaningAction(
        action_id="trim_espacios",
        column="Name",
        description="Espacios Name",
        approved=False,
        parameters={},
        source="ai",
    )

    cleaned_df, cleaning_result = clean_dataframe(df, (rejected_name, approved_only_email))
    validation_result = validate_cleaning(df, cleaned_df, (rejected_name, approved_only_email), cleaning_result)

    _check(cleaned_df["Email"].iloc[0] == "grace@example.com", "Email trim aplicado")
    _check(cleaned_df["Name"].iloc[0] == " Grace Hopper ", "Name no aplicado (rechazado por usuario)")
    _check(validation_result.valid, "Validator acepta resultado parcialmente aprobado")
    _check(df["Name"].iloc[0] == " Grace Hopper ", "Original Name intacto")
    _check(df["Email"].iloc[0] == "grace@example.com ", "Original Email intacto")


def test_e2e_ai_propuesta_rechazada_luego_usuario_reevalua():
    print("\n--- Test E2E: IA propone, se rechaza, usuario reevalua/acepta luego ---")
    df = pd.DataFrame({
        "Name": [" Grace Hopper "],
        "Email": ["grace@example.com "],
    })

    ai_response = AIResponse(
        proposals=(
            AIProposal(action="trim_espacios", column="Name", reason="Espacios Name", confidence=0.75, parameters={}),
        ),
        warnings=("Confianza moderada, revisar antes de aplicar.",),
    )

    with patch("ai.generate_proposals", return_value=ai_response):
        __import__("ai").generate_proposals(None)

    initially_rejected = CleaningAction(
        action_id="trim_espacios",
        column="Name",
        description="Espacios Name",
        approved=False,
        parameters={},
        source="ai",
    )
    cleaned_df, _ = clean_dataframe(df, (initially_rejected,))
    _check(cleaned_df["Name"].iloc[0] == " Grace Hopper ", "Primera ejecucion sin aplicacion por rejected")

    later_approved = CleaningAction(
        action_id="trim_espacios",
        column="Name",
        description="Espacios Name",
        approved=True,
        parameters={},
        source="ai",
    )
    cleaned_df_2, cleaning_result_2 = clean_dataframe(df, (later_approved,))
    validation_result_2 = validate_cleaning(df, cleaned_df_2, (later_approved,), cleaning_result_2)

    _check(cleaned_df_2["Name"].iloc[0] == "Grace Hopper", "Segunda ejecucion con aprobacion efectiva")
    _check(validation_result_2.valid, "Validator acepta")


def main():
    try:
        test_e2e_ai_trim_email()
        test_e2e_ai_propuesta_rechazada_por_usuario()
        test_e2e_ai_multiple_proposals_usuario_aproba_parcial()
        test_e2e_ai_propuesta_rechazada_luego_usuario_reevalua()
    except AssertionError:
        print("\nFALLO ALGUN TEST E2E IA.")
        return 1
    print("\nTODOS LOS TESTS E2E IA PASARON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
