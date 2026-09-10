# AGENTS.md — Excel Cleaner

Punto de entrada obligatorio para cualquier agente de IA que opere en este repositorio.

## Orden de lectura obligatorio (memoria permanente)

1. **`AI_RULES.md`** — Reglas invariables del proyecto (directiva estricta).
2. **`.agents/skills/`** — Skills instaladas que DEBEN aplicarse antes de modificar código:
   - `tdd-workflow` · `verification-loop` · `security-review` · `python-patterns`
   - `python-testing` · `error-handling` · `blueprint` · `strategic-compact`
   - `silent-failure-hunter` · `python-reviewer` (adaptaciones locales de ECC)

## Las dos reglas de oro (resumen ejecutivo)

1. **Verification-loop — "un archivo, un cambio, un test":** enfoque atómico; todo cambio
   de producción se demuestra con una prueba que fallaba antes y pasa después; resultados
   de tests reales, nunca inventados; máximo 3 ciclos por problema.
2. **Error-handling — "cero excepciones silenciosas":** prohibido `except: pass`,
   fallbacks que ocultan fallos y pérdida de datos sin warning; todo error es explícito,
   visible y diagnosticable.

## Arquitectura (no negociable)

```text
CSV/XLSX → Analyzer → AnalysisReport → [AI opcional metadata-only] → AIProposal
        → APROBACIÓN HUMANA → CleaningAction → Cleaner → Validator → Exporter
```

IA PROPONE · USUARIO APRUEBA · CLEANER EJECUTA · VALIDATOR VERIFICA · EXPORTER ESCRIBE.
Detalles completos e invariantes: ver `AI_RULES.md` §5.

## Cómo ejecutar

- Aplicación GUI: `python main.py`
- Suite de tests: `python -m unittest discover -s tests -p "test_*.py"` (tests TestCase)
  y `python tests/test_<modulo>.py` (tests por patrón función).

*Skills provenientes de ECC (github.com/affaan-m/ECC, licencia MIT), adaptadas a
formato SKILL.md agnóstico del harness para descubrimiento por Freebuff/Codebuff.*
