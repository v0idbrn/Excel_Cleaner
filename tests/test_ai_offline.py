# -*- coding: utf-8 -*-
"""Tests de resiliencia offline/timeout/error para ai.py (Fase 7)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from ai import generate_proposals, _parse_and_validate
from models import (
    AIProposal,
    AIResponse,
    AnalysisReport,
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


def _dummy_report():
    return AnalysisReport(
        file_info=FileInfo(Path("demo.csv"), FileType.CSV, 1234, ("Hoja1",)),
        sheet_name="Hoja1",
        row_count=5,
        column_count=2,
        column_stats=(
            ColumnStats("Nombre", "object", 5, 0, 3),
            ColumnStats("Email", "object", 5, 1, 3),
        ),
        issues=(
            Issue(
                "ESPACIOS",
                "Nombre",
                Severity.LOW,
                "Espacios al inicio/final",
                2,
                5,
                suggested_action="trim_espacios",
            ),
            Issue(
                "EMAIL_INVALIDO",
                "Email",
                Severity.MEDIUM,
                "Email invalido",
                1,
                5,
                suggested_action="revisar_manualmente",
            ),
        ),
    )


def test_ollama_offline():
    print("\n--- Test: Ollama apagado (ConnectionError) ---")
    with patch("ai.requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection Refused")
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse incluso con error")
    _check(response.proposals == (), "No genera propuestas con conexión caída")
    _check(any("No se pudo conectar con Ollama" in w for w in response.warnings), "Advierte conexión caída")
    _check(not any("Timeout" in w for w in response.warnings), "No reporta timeout si fue connection error")


def test_ollama_timeout():
    print("\n--- Test: timeout de solicitud ---")
    with patch("ai.requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.Timeout("Read timed out")
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse incluso con timeout")
    _check(response.proposals == (), "No genera propuestas con timeout")
    _check(any("Timeout" in w for w in response.warnings), "Advierte timeout")


def test_http_error_status():
    print("\n--- Test: HTTP error (ej 500) ---")
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 500
        mock_post.return_value = resp
        mock_post.return_value.raise_for_status = lambda: (_ for _ in ()).throw(requests.exceptions.HTTPError("500 Server Error"))
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse incluso con HTTP 500")
    _check(response.proposals == (), "No genera propuestas con HTTP 500")
    _check(any("Error inesperado" in w or "500" in w or "HTTP" in w for w in response.warnings), "Advierte error HTTP")


def test_invalid_json_response():
    print("\n--- Test: Ollama devuelve JSON inválido como texto ---")
    invalid_json_text = "no_es_json_hablar_conmigo"
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"response": invalid_json_text}).encode("utf-8")
        mock_post.return_value = resp
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse incluso con JSON inválido")
    _check(response.proposals == (), "No genera propuestas con JSON inválido")
    _check(any("no es un JSON válido" in w for w in response.warnings), "Advierte JSON inválido")


def test_valid_json_response_via_mock():
    print("\n--- Test: respuesta JSON válida vía mock (Ollama 'apagado' en test) ---")
    valid_payload = {
        "response": json.dumps({
            "proposals": [
                {
                    "action": "trim_espacios",
                    "column": "Nombre",
                    "reason": "Espacios al inicio/final detectados",
                    "confidence": 0.85,
                    "parameters": {},
                },
                {
                    "action": "revisar_manualmente",
                    "column": "Email",
                    "reason": "Formato de email sospechoso, requiere revisión",
                    "confidence": 0.7,
                    "parameters": {},
                },
            ],
        }),
    }
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps(valid_payload).encode("utf-8")
        mock_post.return_value = resp
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse correcta")
    _check(len(response.proposals) == 2, "Parsea correctamente 2 propuestas")
    _check(response.proposals[0].action == "trim_espacios", "Primera propuesta: trim_espacios")
    _check(response.proposals[0].column == "Nombre", "Primera propuesta columna: Nombre")
    _check(response.proposals[0].confidence == 0.85, "Primera propuesta confidence correcta")
    _check(response.proposals[1].action == "revisar_manualmente", "Segunda propuesta: revisar_manualmente")
    _check(response.proposals[1].column == "Email", "Segunda propuesta columna: Email")
    _check(response.proposals[1].confidence == 0.7, "Segunda propuesta confidence correcta")
    _check(response.warnings == (), "Sin warnings en respuesta válida")


def test_empty_response():
    print("\n--- Test: Ollama devuelve string vacío ---")
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"response": ""}).encode("utf-8")
        mock_post.return_value = resp
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse con respuesta vacía")
    _check(response.proposals == (), "No genera propuestas con respuesta vacía")


def test_json_response_without_proposals_key():
    print("\n--- Test: respuesta JSON sin clave 'proposals' ---")
    weird_payload = {
        "response": json.dumps({
            "gracias": "no tenemos propuestas",
            "otra_cosa": 42,
        }),
    }
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps(weird_payload).encode("utf-8")
        mock_post.return_value = resp
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse")
    _check(response.proposals == (), "No genera propuestas sin clave proposals")
    _check(any("no generó ninguna propuesta" in w for w in response.warnings), "Advierte respuesta incompleta")


def test_response_with_ignored_fields_but_valid_core():
    print("\n--- Test: respuesta con campos extra ignorados, pero núcleo válido ---")
    payload_with_extra = {
        "response": json.dumps({
            "proposals": [
                {
                    "action": "trim_espacios",
                    "column": "Nombre",
                    "reason": "Espacios detectados",
                    "confidence": 0.9,
                    "parameters": {},
                    "extra_random_field": "ignorar",
                },
            ],
            "meta_randomo": "ignorar también",
        }),
    }
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps(payload_with_extra).encode("utf-8")
        mock_post.return_value = resp
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse con campos extra ignorados")
    _check(len(response.proposals) == 1, "Acepta propuesta con campos extra")
    _check(response.proposals[0].column == "Nombre", "Columna parseada correctamente")
    _check(response.warnings == (), "Sin warnings")


def test_response_with_heading_markdown_rejected():
    print("\n--- Test: respuesta JSON con markdown alrededor ---")
    markdown_glucose = "```json\n" + json.dumps({
        "proposals": [{"action": "trim_espacios", "column": "Nombre", "reason": "Espacios", "confidence": 0.6}]
    }) + "\n```"
    with patch("ai.requests.post") as mock_post:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({"response": markdown_glucose}).encode("utf-8")
        mock_post.return_value = resp
        response = generate_proposals(_dummy_report())

    _check(isinstance(response, AIResponse), "Devuelve AIResponse")
    _check(response.proposals == (), "Rechaza JSON con markdown circundante (no es JSON válido)")
    _check(any("no es un JSON válido" in w for w in response.warnings), "Advierte JSON inválido (markdown no permitido)")


def main():
    try:
        test_ollama_offline()
        test_ollama_timeout()
        test_http_error_status()
        test_invalid_json_response()
        test_valid_json_response_via_mock()
        test_empty_response()
        test_json_response_without_proposals_key()
        test_response_with_ignored_fields_but_valid_core()
        test_response_with_heading_markdown_rejected()
    except AssertionError:
        print("\nFALLO ALGUN TEST DE RESILIENCIA IA.")
        return 1
    print("\nTODOS LOS TESTS DE RESILIENCIA IA PASARON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
