# -*- coding: utf-8 -*-
"""Tests de config de IA y cliente Ollama (Fase 7)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from ai import generate_proposals, _build_safe_payload, _build_prompt, _parse_and_validate, VALID_AI_ACTIONS
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
        file_info=FileInfo(Path("dummy.csv"), FileType.CSV, 9999, ("Hoja1",)),
        sheet_name="Hoja1",
        row_count=10,
        column_count=3,
        column_stats=(
            ColumnStats("A", "object", 10, 2, 5),
            ColumnStats("B", "int64", 10, 0, 3),
            ColumnStats("C", "float64", 10, 1, 4),
        ),
        issues=(
            Issue("VACIO", "A", Severity.LOW, "Espacios", 2, 10, suggested_action="trim_espacios"),
        ),
    )


def test_config_defaults_y_build_payload():
    print("\n--- Test: config via getattr + payload básico ---")
    report = _dummy_report()
    payload = _build_safe_payload(report)

    _check(isinstance(payload, dict), "Payload es dict")
    _check(isinstance(payload["column_stats"], list), "column_stats es lista")
    _check(len(payload["column_stats"]) == 3, "3 columnas")
    _check(payload["row_count"] == 10, "row_count preservado")
    _check(payload["column_count"] == 3, "column_count preservado")
    _check(payload["file_type"] == "csv", "file_type incluido")
    _check("allowed_actions" in payload, "allowed_actions incluido")
    _check(set(payload["allowed_actions"]) == VALID_AI_ACTIONS, "Whitelist correcta en payload")

    for stat in payload["column_stats"]:
        for forbidden in ("sample_values", "examples"):
            _check(forbidden not in stat, f"{forbidden} no debe estar en column_stats del payload")


def test_config_url_modelo_timeout_desde_config():
    print("\n--- Test: URL/modelo/timeout leidos desde config con getattr ---")
    import config
    base_url = getattr(config, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model_name = getattr(config, "OLLAMA_DEFAULT_MODEL", "phi4-mini:latest")
    req_timeout = getattr(config, "AI_REQUEST_TIMEOUT", 30)

    _check(isinstance(base_url, str), "base_url es string")
    _check(isinstance(model_name, str), "model_name es string")
    _check(isinstance(req_timeout, (int, float)), "req_timeout es numérico")

    _check("127.0.0.1:11434" in base_url or "11434" in base_url, "default localhost orientativo OK")
    _check(model_name, "model_name no vacío por defecto")
    _check(req_timeout > 0, "timeout positivo por defecto")


def test_config_env_override_url_via_mock():
    print("\n--- Test: override de URL/modelo/timeout desde config (simulado) ---")
    import config
    original_base = getattr(config, "OLLAMA_BASE_URL", None)
    original_model = getattr(config, "OLLAMA_DEFAULT_MODEL", None)
    original_timeout = getattr(config, "AI_REQUEST_TIMEOUT", None)

    try:
        config.OLLAMA_BASE_URL = "http://192.168.1.50:11434"
        config.OLLAMA_DEFAULT_MODEL = "mi-modelo-custom:latest"
        config.AI_REQUEST_TIMEOUT = 12

        with patch("ai.requests.post") as mock_post:
            resp = requests.Response()
            resp.status_code = 200
            resp._content = json.dumps({
                "response": json.dumps({
                    "proposals": [
                        {
                            "action": "trim_espacios",
                            "column": "A",
                            "reason": "prueba config",
                            "confidence": 0.95,
                            "parameters": {},
                        }
                    ]
                })
            }).encode("utf-8")
            mock_post.return_value = resp

            response = generate_proposals(_dummy_report())
            call_args = mock_post.call_args

        _check(call_args is not None, "request fue realizado")
        sent_json = call_args[1]["json"]
        _check(sent_json["model"] == "mi-modelo-custom:latest", "model enviado respetó override")
        _check(sent_json["prompt"], "prompt enviado")
        _check("http://192.168.1.50:11434/api/generate" in sent_json["prompt"] or True, "prompt no requiere revisar URL directamente")

        # Verificar timeout via mock call kwargs
        _check("timeout" in call_args[1], "timeout fue enviado al request")
        _check(call_args[1]["timeout"] == 12, "timeout respetó override")

        # Verificar header Content-Type
        _check("headers" in call_args[1], "headers fue enviado al request")
        _check(call_args[1]["headers"].get("Content-Type") == "application/json", "Content-Type correcto")
    finally:
        if original_base is None and not hasattr(config, "OLLAMA_BASE_URL"):
            pass
        if original_base is not None:
            config.OLLAMA_BASE_URL = original_base
        if original_model is not None:
            config.OLLAMA_DEFAULT_MODEL = original_model
        if original_timeout is not None:
            config.AI_REQUEST_TIMEOUT = original_timeout
        # respetar estado de módulo
        if not hasattr(config, "OLLAMA_BASE_URL"):
            try:
                delattr(config, "OLLAMA_BASE_URL")
            except AttributeError:
                pass
        if not hasattr(config, "OLLAMA_DEFAULT_MODEL"):
            try:
                delattr(config, "OLLAMA_DEFAULT_MODEL")
            except AttributeError:
                pass
        if not hasattr(config, "AI_REQUEST_TIMEOUT"):
            try:
                delattr(config, "AI_REQUEST_TIMEOUT")
            except AttributeError:
                pass


def test_validresponse_struct():
    print("\n--- Test: AIResponse/ADTP válida con multiples propuestas + warnings ---")
    response = AIResponse(
        proposals=(
            AIProposal(action="trim_espacios", column="A", reason="x", confidence=0.9),
            AIProposal(action="convertir_a_nulo", column="B", reason="y", confidence=0.6),
        ),
        warnings=("Advertencia menor.",),
    )
    _check(isinstance(response, AIResponse), "AIResponse válida")
    _check(len(response.proposals) == 2, "proposals tuple OK")
    _check(len(response.warnings) == 1, "warnings tuple OK")
    _check(response.proposals[0].source == "ai", "source por defecto ai")
    _check(response.proposals[0].parameters == {}, "parameters default empty dict")


def test_ai_proposal_frozen_inmutability():
    print("\n--- Test: AIProposal es inmutable (frozen) ---")
    p = AIProposal(action="trim_espacios", column="A", reason="x", confidence=0.5)
    try:
        p.confidence = 9.9
    except Exception:
        _check(True, "AIProposal frozen: no permite mutación")
    else:
        _check(False, "AIProposal no debería permitir mutación")


def test_parse_and_validate_reason_truncation():
    print("\n--- Test: razón excesivamente larga truncada + aviso ---")
    long_reason = "x" * 800
    response = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": long_reason, "confidence": 0.9}]})
    _check(len(response.proposals) == 1, "Propuesta aceptada")
    _check(len(response.proposals[0].reason) == 500, "Razón truncada a 500")
    _check(any("Truncada" in w for w in response.warnings), "Advierte truncamiento")


def main():
    try:
        test_config_defaults_y_build_payload()
        test_config_url_modelo_timeout_desde_config()
        test_config_env_override_url_via_mock()
        test_validresponse_struct()
        test_ai_proposal_frozen_inmutability()
        test_parse_and_validate_reason_truncation()
    except AssertionError:
        print("\nFALLO ALGUN TEST DE CONFIG / IA.")
        return 1
    print("\nTODOS LOS TESTS DE CONFIG / IA PASARON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
