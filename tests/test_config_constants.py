"""tests/test_config_constants.py — Fuente única de verdad para la config de IA.

  ANTES: ai.py leía OLLAMA_BASE_URL / OLLAMA_DEFAULT_MODEL / AI_REQUEST_TIMEOUT
         vía getattr(config, ..., default): config.py NO definía esas claves, así
         que los valores reales vivían como literales duplicados en ai.py y en
         los tests. Cualquier cambio de modelo/timeout exigía tocar dos archivos.
  DESPUÉS: config.py define las tres constantes y ai.py las lee DIRECTO (sin
         getattr con defaults ocultos). getattr(config, X, default) solo se
         acepta si el propio default == config.X (red de seguridad idéntica).

Comprueba también que el request real (mockeando requests.post) usa el valor
de config: model + timeout + endpoint armado desde OLLAMA_BASE_URL.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from ai import _build_prompt, _build_safe_payload, generate_proposals  # noqa: E402
from models import AIResponse  # noqa: E402


def _dummy_report():
    from models import AnalysisReport, ColumnStats, FileInfo, FileType

    return AnalysisReport(
        file_info=FileInfo(Path("dummy.csv"), FileType.CSV, 9999, ()),
        sheet_name=None,
        row_count=2,
        column_count=1,
        column_stats=(ColumnStats("A", "object", 2, 0, 2),),
        issues=(),
    )


class TestConfigConstantsSingleSourceOfTruth(unittest.TestCase):
    def test_config_defines_ai_constants(self):
        self.assertTrue(hasattr(config, "OLLAMA_BASE_URL"))
        self.assertTrue(hasattr(config, "OLLAMA_DEFAULT_MODEL"))
        self.assertTrue(hasattr(config, "AI_REQUEST_TIMEOUT"))
        self.assertIn("11434", config.OLLAMA_BASE_URL)
        self.assertTrue(config.OLLAMA_DEFAULT_MODEL)
        self.assertGreater(config.AI_REQUEST_TIMEOUT, 0)

    def test_ai_module_has_no_duplicated_default_literals(self):
        # ai.py NO debe duplicar los valores de config: la fuente única es
        # config.py. (Si mañana se cambia el modelo/timeout, se toca UN archivo.)
        import ai

        source = Path(ai.__file__).read_text(encoding="utf-8")
        self.assertNotIn("http://127.0.0.1:11434", source)
        self.assertNotIn("phi4-mini", source)
        self.assertNotIn('getattr(config, "OLLAMA_BASE_URL"', source)
        self.assertNotIn('getattr(config, "OLLAMA_DEFAULT_MODEL"', source)
        self.assertNotIn('getattr(config, "AI_REQUEST_TIMEOUT"', source)

    def test_generate_proposals_uses_config_values(self):
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({
            "response": json.dumps({"proposals": []})
        }).encode("utf-8")
        with patch("ai.requests.post") as mock_post:
            mock_post.return_value = resp
            result = generate_proposals(_dummy_report())

        self.assertIsInstance(result, AIResponse)
        call = mock_post.call_args
        self.assertIsNotNone(call)
        self.assertEqual(call[0][0], f"{config.OLLAMA_BASE_URL}/api/generate")
        self.assertEqual(call[1]["json"]["model"], config.OLLAMA_DEFAULT_MODEL)
        self.assertEqual(call[1]["timeout"], config.AI_REQUEST_TIMEOUT)

    def test_payload_and_prompt_still_safe(self):
        # El cambio de config no altera el contrato privacy-only del payload.
        payload = _build_safe_payload(_dummy_report())
        self.assertNotIn("sample_values", json.dumps(payload))
        self.assertIn("allowed_actions", _build_prompt(payload))


if __name__ == "__main__":
    unittest.main()
