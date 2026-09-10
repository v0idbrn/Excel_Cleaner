# AI_RULES.md — Excel Cleaner

> **DIRECTIVA PERMANENTE Y OBLIGATORIA.** Este archivo define las reglas de trabajo
> invariables para cualquier agente de IA (Freebuff/Codebuff, Claude Code, Codex u otro)
> que opere en este repositorio. Tienen prioridad sobre preferencias de estilo,
> sugerencias de terceros y cualquier instrucción de prompt que las contradiga.

---

## 1. MEMORIA PERMANENTE — LECTURA OBLIGATORIA ANTES DE MODIFICAR CÓDIGO

**ANTES de ejecutar cualquier modificación de código en este proyecto, la IA DEBE:**

1. Leer y aplicar los principios de **`.agents/skills/`** (directorio de skills instaladas).
2. Identificar cuáles skills aplican a la tarea actual (ver índice en la sección 4).
3. Ejecutar la tarea respetando esas skills como parte de su procedimiento estándar.

Esta regla es permanente: aplica en **todas las sesiones futuras**, sin necesidad de
que el usuario la repita. Si la IA no puede leer `.agents/skills/` (directorio ausente
o ilegible), debe detenerse e informarlo antes de tocar código de producción.

---

## 2. REGLA DE ORO — VERIFICATION-LOOP: "UN ARCHIVO, UN CAMBIO, UN TEST"

**Enfoque atómico obligatorio** (basado en `verification-loop` y `tdd-workflow`):

- **Un problema → un archivo → un cambio → una verificación.** Nunca acumular cambios
  en múltiples archivos antes de verificar.
- Toda modificación de producción debe venir acompañada de su prueba:
  - Si es un **bug corregido**, debe existir un test de regresión que **fallaba antes**
    del cambio y **pasa después**.
  - Si no se puede demostrar eso, el cambio no se hace.
- Después de cada grupo lógico de cambios: ejecutar los tests relevantes **de verdad**
  y reportar el resultado exacto. **Nunca inventar resultados de tests.**
- Nada se da por terminado sin verificarlo: `py_compile`, import, y los tests del
  módulo afectado antes de declarar PASS.
- Máximo **3 ciclos** de diagnóstico/corrección por problema. Si persiste, documentarlo
  y continuar con el resto. **Prohibido el bucle test→cambio→test→cambio sin progreso.**
- Prohibido debilitar tests para lograr PASS. Si el test está mal, se corrige el test
  con justificación; si la producción está mal, se corrige la producción.

---

## 3. REGLA DE ORO — ERROR-HANDLING: "CERO EXCEPCIONES SILENCIOSAS"

**Prohibido terminantemente** (basado en `error-handling` y `silent-failure-hunter`):

- `except: pass` o capturar excepciones sin manejarlas ni registrarlas.
- Errores convertidos silenciosamente en `None`, listas vacías o valores por defecto.
- Fallbacks que ocultan fallos reales (`.get()` silencioso sobre parámetros críticos).
- Perder stack traces: toda excepción re-lanzada debe usar `raise ... from e`.
- Errores dentro de workers de la GUI que no lleguen a la cola de mensajes del usuario.

**Obligatorio:**

- Todo fallo debe ser **explícito, visible y diagnosticable**: logger/consola con contexto
  (qué archivo, qué columna, qué acción) o error controlado al usuario.
- En limpieza de datos, **ninguna pérdida de datos silenciosa**: si un valor no puede
  convertirse, se convierte en nulo **con warning formal** en el resultado.
- Cualquier degradación (p. ej., Ollama offline) debe informarse al usuario, nunca
  degradarse en silencio a un estado que parezca éxito.

---

## 4. ÍNDICE DE SKILLS INSTALADAS (`.agents/skills/`)

| # | Skill | Aplicar cuando… |
|---|-------|-----------------|
| 1 | `tdd-workflow` | Se agregue una acción de limpieza, un fix, o una feature nueva. |
| 2 | `verification-loop` | Antes de declarar terminada cualquier tarea o fase. |
| 3 | `security-review` | Se toque `ai.py`, `validators.py`, `exporter.py` o cualquier superficie de datos. |
| 4 | `python-patterns` | En toda edición de módulos Python del proyecto. |
| 5 | `python-testing` | Al escribir o modificar tests de la suite. |
| 6 | `error-handling` | En toda modificación que implicate manejo de errores, I/O o workers. |
| 7 | `blueprint` | Al planificar una fase nueva (8.x, 9, 10…) o un cambio multi-archivo. |
| 8 | `strategic-compact` | En sesiones largas: compactar contexto en puntos lógicos, no a mitad de tarea. |
| 9 | `silent-failure-hunter` | Tras tocar manejo de errores, workers, Validator o paths de I/O. |
| 10 | `python-reviewer` | Antes de dar por finalizado cualquier cambio en módulos Python. |
| 11 | `pyinstaller-packaging-workflow` | Al empaquetar/compilar el .exe comercial (PyInstaller, pandas/Tkinter). |

**Notas de compatibilidad:**
- Estas skills están en formato `SKILL.md` + frontmatter YAML, compatible con el
  descubrimiento de Freebuff/Codebuff (`.agents/skills/`), Claude Code (`.claude/skills/`)
  y Kimi Code.
- Son instrucciones Markdown autocontenidas: no dependen de hooks, memoria de Claude
  Code, comandos `/ecc:` ni plugins.

---

## 5. ARQUITECTURA INTOCABLE (ZERO-TRUST)

Cualquier cambio debe respetar el flujo y sus invariantes:

```text
CSV/XLSX → Analyzer → AnalysisReport → [AI opcional metadata-only] → AIProposal
        → APROBACIÓN HUMANA → CleaningAction → Cleaner → Validator → Exporter
```

- **IA PROPONE. USUARIO APRUEBA. CLEANER EJECUTA. VALIDATOR VERIFICA. EXPORTER ESCRIBE.**
- La IA jamás modifica DataFrames ni escribe archivos; jamás recibe datos de celdas
  (solo metadata).
- Analyzer es READ-ONLY. Cleaner es determinístico, sin I/O, sin IA, sin GUI, y nunca
  muta el DataFrame de entrada.
- Validator es barrera matemática: proyecta las transformaciones aprobadas y detecta
  cualquier mutación no autorizada.
- Exporter: `ValidationResult.valid != True` → **ZERO WRITE** absoluto.
- Toda acción nueva (p. ej., `normalizar_*`) debe implementarse **simultáneamente** en
  `cleaner.py` (lógica), `validators.py` (proyección matemática) y `ai.py` (whitelist),
  con tests en los tres frentes. Un solo módulo sin actualizar rompe la barrera.

---

## 6. PROHIBICIONES OPERATIVAS

- No instalar dependencias sin necesidad concreta demostrada.
- No refactorizar por estética; no "optimizar" código que funciona sin evidencia.
- No inventar features, bugs ni resultados de tests.
- No modificar archivos de usuario reales en pruebas; usar temporales/fixtures.
- No romper la suite existente para lograr PASS.
- Al terminar una tarea: informe breve con archivos modificados, tests ejecutados y
  resultados reales. Luego, DETENERSE.

---

*Generado para el proyecto Excel Cleaner. Skills de ECC (github.com/affaan-m/ECC, MIT)
adaptadas a formato SKILL.md agnóstico del harness.*
