import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import _build_safe_payload, _parse_and_validate, generate_proposals
from models import AnalysisReport, ColumnStats, FileInfo, FileType, Issue, Severity


class TestAIIntegration(unittest.TestCase):
    def setUp(self):
        self.dummy_report = AnalysisReport(
            file_info=FileInfo(Path("test.csv"), FileType.CSV, 100, ()),
            sheet_name=None,
            row_count=10,
            column_count=2,
            column_stats=(ColumnStats("A", "object", 10, 0, 5, sample_values=("SECRET1", "SECRET2")),),
            issues=(Issue("TEST", "A", Severity.MEDIUM, "Test issue", 10, 10, examples=("EX1", "EX2"), suggested_action="trim_espacios"),)
        )

    def test_privacy_payload_strips_samples(self):
        payload = _build_safe_payload(self.dummy_report)
        payload_str = json.dumps(payload, ensure_ascii=True)
        self.assertNotIn("SECRET1", payload_str)
        self.assertNotIn("SECRET2", payload_str)
        self.assertNotIn("EX1", payload_str)
        self.assertNotIn("EX2", payload_str)
        self.assertIn("trim_espacios", payload_str)

    def test_privacy_payload_no_examples_in_issues(self):
        payload = _build_safe_payload(self.dummy_report)
        self.assertNotIn("examples", json.dumps(payload))

    def test_ai_config_getattr_defaults(self):
        import config
        base_url = getattr(config, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        model_name = getattr(config, "OLLAMA_DEFAULT_MODEL", "phi4-mini:latest")
        timeout = getattr(config, "AI_REQUEST_TIMEOUT", 30)
        self.assertIsInstance(base_url, str)
        self.assertIsInstance(model_name, str)
        self.assertIsInstance(timeout, (int, float))
        self.assertGreater(timeout, 0)

    def test_parse_structural_rejections(self):
        from ai import _parse_and_validate

        r = _parse_and_validate({"proposals": "no_es_array"})
        self.assertEqual(len(r.proposals), 0)
        self.assertTrue(any("no contiene una lista" in w for w in r.warnings))

        r = _parse_and_validate({})
        self.assertEqual(len(r.proposals), 0)
        self.assertTrue(any("no generó ninguna propuesta" in w for w in r.warnings))

        r = _parse_and_validate({"proposals": [{"action": "borra_todo", "column": None, "reason": "malicia", "confidence": 0.9}]})
        self.assertEqual(len(r.proposals), 0)
        self.assertTrue(any("Acción desconocida" in w for w in r.warnings))

        r = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": "0.9"}]})
        self.assertEqual(len(r.proposals), 0)
        self.assertTrue(any("no numérica" in w for w in r.warnings))

        r = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": 1.5}]})
        self.assertEqual(len(r.proposals), 0)
        self.assertTrue(any("fuera de rango" in w for w in r.warnings))

        r = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": -0.2}]})
        self.assertEqual(len(r.proposals), 0)
        self.assertTrue(any("fuera de rango" in w for w in r.warnings))

        r = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": 0.5, "parameters": "no_dict"}]})
        self.assertEqual(len(r.proposals), 1)
        self.assertEqual(r.proposals[0].parameters, {})

        r = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": "x", "confidence": 0.5}] * 25})
        self.assertLessEqual(len(r.proposals), 20)
        self.assertTrue(any("superó el límite de 20" in w for w in r.warnings))

        long_reason = "x" * 800
        r = _parse_and_validate({"proposals": [{"action": "trim_espacios", "column": "A", "reason": long_reason, "confidence": 0.9}]})
        self.assertEqual(len(r.proposals), 1)
        self.assertEqual(len(r.proposals[0].reason), 500)
        self.assertTrue(any("Truncada" in w for w in r.warnings))


    @patch('ai.requests.post')
    def test_ollama_offline_handling(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection Refused")
        response = generate_proposals(self.dummy_report)
        self.assertEqual(len(response.proposals), 0)
        self.assertTrue(any("No se pudo conectar con Ollama" in w for w in response.warnings))

if __name__ == '__main__':
    unittest.main()