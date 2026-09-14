"""ai.py

Módulo de integración con IA Local (Ollama) para ExcelCleaner.
Responsable EXCLUSIVAMENTE de analizar metadata y proponer acciones.
NO modifica datos, NO lee archivos, NO tiene acceso a Pandas.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

import config
from models import AIProposal, AIResponse, AnalysisReport

logger = logging.getLogger(__name__)

# Whitelist estricta basada en las capacidades reales de cleaner.py
VALID_AI_ACTIONS = {
    "eliminar_filas_vacias",
    "eliminar_columnas_vacias",
    "eliminar_duplicados_exactos",
    "trim_espacios",
    "convertir_a_nulo",
    "convertir_a_numerico",
    "revisar_manualmente",
    "normalizar_mayusculas",
    "normalizar_fechas",
    "normalizar_numerico",
    "limpiar_invisibles",
    "eliminar_duplicados_por_columna",
    "dividir_columna",
    "unir_columnas",
    "reemplazar_valores",
    "convertir_basura_a_nulo",
}


def _build_safe_payload(report: AnalysisReport) -> dict[str, Any]:
    """
    Construye un payload seguro extrayendo solo metadata estructural.
    NUNCA incluye sample_values ni examples para proteger la privacidad.
    """
    safe_stats = []
    for stat in report.column_stats:
        safe_stats.append({
            "name": stat.name,
            "dtype": stat.dtype,
            "non_null_count": stat.non_null_count,
            "null_count": stat.null_count,
            "unique_count": stat.unique_count
        })

    safe_issues = []
    for issue in report.issues:
        safe_issues.append({
            "category": issue.category,
            "column": issue.column,
            "severity": issue.severity.value,
            "description": issue.description,
            "affected_count": issue.affected_count,
            "total_count": issue.total_count,
            "suggested_action": issue.suggested_action
        })

    return {
        "file_type": report.file_info.file_type.value,
        "row_count": report.row_count,
        "column_count": report.column_count,
        "column_stats": safe_stats,
        "issues": safe_issues,
        "allowed_actions": list(VALID_AI_ACTIONS)
    }


def _build_prompt(safe_payload: dict[str, Any]) -> str:
    system_prompt = """Eres un asistente experto en análisis de datos.
Tu única tarea es proponer acciones de limpieza basándote en la metadata proporcionada.
REGLAS ESTRICTAS:
1. NO modificas archivos ni ejecutas código. Solo propones.
2. SOLO puedes utilizar las acciones listadas en "allowed_actions". NO inventes acciones.
3. Si no tienes suficiente evidencia para una transformación automática, propone "revisar_manualmente".
4. Para la acción "normalizar_numerico" puedes proponer los siguientes parámetros:
   - locale: "us" (formato 1,250.50) o "eu" (formato 1.250,50) o "auto" (detección automática). Default: "auto".
   - remove_currency: bool. Si True, quita símbolos como $, €, £, USD, EUR, GBP. Default: True.
   - handle_parentheses_negatives: bool. Si True, convierte (500.50) a -500.50. Default: True.
   - convert_percentages: bool. Si True, convierte 15% a 0.15. Default: False.
5. Para la acción "eliminar_duplicados_por_columna" los parámetros son:
   - subset_columns: lista de columnas que definen el criterio único (ej. ["Email"]). Default: la columna de la acción.
   - keep: "first" o "last". Default: "first".
6. Para la acción "dividir_columna" los parámetros son OBLIGATORIOS:
   - delimiter: string literal (NO regex), ej. " ", ",", "-", ".", "|".
   - new_column_names: lista exacta de nombres para las nuevas columnas (ej. ["Nombre", "Apellido"]).
7. Para la acción "unir_columnas" los parámetros son OBLIGATORIOS:
   - source_columns: lista de columnas a concatenar (ej. ["Nombre", "Apellido"]).
   - new_column_name: nombre de la columna resultante (si coincide con una fuente, la reemplaza in-place).
   - separator: string de unión. Default: " ".
   - drop_source_columns: bool. Default: false.
8. Para la acción "reemplazar_valores" el parámetro es OBLIGATORIO:
   - mappings: lista de reglas ordenadas (gana la primera que coincida), cada una con:
     find (string no vacío), replace (string, o null para convertir a NULO REAL),
     match: "exact" (celda completa, ignora espacios externos), "contains" o "regex".
     Ejemplo: [{"find": "N/A", "replace": null, "match": "exact"}].
8b. Para la acción "convertir_basura_a_nulo" los parámetros son OPCIONALES:
   - extra_patterns: lista de strings EXACTOS adicionales a convertir en nulo (respetan mayúsculas).
   - convert_text_zeros: true SOLO si la columna es claramente de texto y sus "0"/"00" significan "sin dato".
   - NO la propongas sobre columnas numéricas ni si el 0 es un valor legítimo.
9. Debes devolver un JSON estrictamente con este formato, sin texto adicional:
{
  "proposals": [
    {
      "action": "nombre_de_la_accion",
      "column": "nombre_de_la_columna_o_null",
      "reason": "Explicación breve y objetiva",
      "confidence": 0.95,
      "parameters": {}
    }
  ]
}
10. "confidence" DEBE ser un número entre 0.0 y 1.0.
"""
    return system_prompt + "\n\nMetadata a analizar:\n" + json.dumps(safe_payload, indent=2)


def _parse_and_validate(response_json: dict[str, Any]) -> AIResponse:
    proposals = []
    warnings = []

    raw_proposals = response_json.get("proposals", [])
    if not isinstance(raw_proposals, list):
        return AIResponse(proposals=(), warnings=("El JSON devuelto no contiene una lista en 'proposals'.",))

    if len(raw_proposals) > 20:
        warnings.append("Se superó el límite de 20 propuestas. Las propuestas excedentes fueron descartadas.")
        raw_proposals = raw_proposals[:20]

    for raw_p in raw_proposals:
        try:
            action = raw_p.get("action")
            confidence = raw_p.get("confidence")
            reason = raw_p.get("reason", "")
            
            if action not in VALID_AI_ACTIONS:
                warnings.append(f"Acción desconocida rechazada: '{action}'.")
                continue
                
            if not isinstance(confidence, (int, float)):
                warnings.append(f"Confidence no numérica en acción '{action}'.")
                continue
                
            if confidence < 0.0 or confidence > 1.0:
                warnings.append(f"Confidence fuera de rango ({confidence}) en acción '{action}'. Rechazada.")
                continue

            if len(reason) > 500:
                warnings.append(f"Razón excesivamente larga en acción '{action}'. Truncada.")
                reason = reason[:500]

            parameters = raw_p.get("parameters", {})
            if not isinstance(parameters, dict):
                parameters = {}

            proposals.append(AIProposal(
                action=action,
                column=raw_p.get("column"),
                reason=reason,
                confidence=float(confidence),
                parameters=parameters
            ))
            
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Error parseando una propuesta: {e}")

    if not proposals and not warnings:
        warnings.append("La IA no generó ninguna propuesta válida.")

    return AIResponse(proposals=tuple(proposals), warnings=tuple(warnings))


def generate_proposals(report: AnalysisReport) -> AIResponse:
    """Envía la metadata al modelo local Ollama y devuelve propuestas validadas."""
    safe_payload = _build_safe_payload(report)
    prompt = _build_prompt(safe_payload)

    # Fuente única de verdad: config.py (lectura directa en vivo; sin
    # defaults duplicados aquí). Un override en config (tests/usuario) aplica
    # en la próxima llamada sin recargar el módulo.
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    data = {
        "model": config.OLLAMA_DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(url, json=data, timeout=config.AI_REQUEST_TIMEOUT, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        result = response.json()
        
        # Ollama devuelve la respuesta en la clave "response"
        ai_response_text: str = str(result.get("response", ""))
        if not ai_response_text:
            return AIResponse(proposals=(), warnings=("Ollama devolvió respuesta vacía.",))
        ai_response_json = json.loads(ai_response_text)
        
        return _parse_and_validate(ai_response_json)

    except requests.exceptions.ConnectionError:
        return AIResponse(proposals=(), warnings=("No se pudo conectar con Ollama. ¿Está el servidor encendido?",))
    except requests.exceptions.Timeout:
        return AIResponse(proposals=(), warnings=("Timeout al esperar respuesta de Ollama.",))
    except json.JSONDecodeError:
        return AIResponse(proposals=(), warnings=("El modelo devolvió una respuesta que no es un JSON válido.",))
    except requests.exceptions.HTTPError:
        return AIResponse(proposals=(), warnings=("Ollama devolvió un error HTTP.",))
    except requests.exceptions.RequestException:
        return AIResponse(proposals=(), warnings=("No se pudo completar la consulta a Ollama.",))
    except Exception as e:  # noqa: BLE001
        return AIResponse(proposals=(), warnings=(f"Error inesperado al consultar la IA: {e}",))