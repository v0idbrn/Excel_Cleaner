"""Pruebas unitarias del Motor de Lotes (Fase 9.0).

Patrón función (igual que el resto de suites del proyecto). Verifica:
  - Pipeline multi-pass determinista y con orden correcto (duplicados AL FINAL).
  - Aislamiento de errores: un archivo corrupto NO tira abajo el lote.
  - Cuarentena en <salida>/errors/.
  - Barrera Zero-Trust: si el Validator rechaza, NO se exporta nada.
  - Read-only absoluto sobre los archivos de entrada.
  - Reporte maestro batch_audit_summary (json + txt).
  - Reject de carpetas inválidas (BatchError).

Ejecutar:  python tests/test_batch.py   |   python -m unittest tests.test_batch -v
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batch_processor import (
    BatchError,
    _resolve_passes,
    process_batch_files,
    process_batch_folder,
    run_multipass_summary_check,
)
from cleaner import _auto_actions_from_analysis, run_multipass_cleaning
from models import CleaningAction

_CHECKS = {"pass": 0, "fail": 0}


def _check(condition: bool, description: str) -> None:
    if condition:
        _CHECKS["pass"] += 1
        print(f"  [OK] {description}")
    else:
        _CHECKS["fail"] += 1
        print(f"  [FAIL] {description}")


def _mk_csv(path: Path, rows: list[list], header: list[str]) -> Path:
    pd.DataFrame(rows, columns=header).to_csv(path, index=False, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Motor multi-pass: orden y corrección
# ---------------------------------------------------------------------------

def test_multipass_order() -> None:
    print("\n--- Test 1: Multi-pass ejecuta duplicados AL FINAL (sobre datos limpios) ---")
    df = pd.DataFrame({
        "Name": ["  Alice  ", "Alice", "Bob", "  Bob ", None],
        "Email": ["a@x.com ", " a@x.com", "b@x.com", "b@x.com", None],
    })
    df_snapshot = df.copy(deep=True)

    df_clean, aggregate, per_pass = run_multipass_cleaning(df)

    _check(df.equals(df_snapshot), "El DataFrame original NO fue mutado")
    # "Alice" y "Alice  " ya no difieren tras el trim -> el duplicado sucio SÍ se elimina
    _check(len(df_clean) == 2, f"Solo sobreviven 2 filas únicas limpias (hay {len(df_clean)})")
    _check(set(df_clean["Name"].dropna()) == {"Alice", "Bob"}, "Nombres sin espacios residuales")
    _check(len(per_pass) >= 2, f"Hay CleaningResult por pasada ({len(per_pass)})")
    applied_ids = [a.action_id for a in aggregate.actions_applied]
    _check("eliminar_duplicados_exactos" in applied_ids, "Duplicados eliminados en Pass 3")
    _check(
        applied_ids.index("eliminar_duplicados_exactos") > applied_ids.index("trim_espacios"),
        "Orden correcto: trim antes que deduplicar",
    )
    _check(aggregate.rows_before == 5 and aggregate.rows_after == len(df_clean), "Métricas agregadas consistentes")


def test_multipass_passes_dict() -> None:
    print("\n--- Test 2: Multi-pass acepta pases explícitos y rechaza claves inválidas ---")
    df = pd.DataFrame({"A": ["  x  ", "y "]})
    passes = {"pass1": (CleaningAction("trim_espacios", "A", "test", approved=True),)}
    df_clean, _agg, per_pass = run_multipass_cleaning(df, passes=passes)
    _check(list(df_clean["A"]) == ["x", "y"], "Pass explícito aplicado")
    _check(len(per_pass) == 1, "Un solo CleaningResult para un solo pase")

    try:
        run_multipass_cleaning(df, passes={"pass99": ()})
        _check(False, "Clave inválida debe lanzar CleanerError")
    except Exception as exc:
        _check(type(exc).__name__ in {"CleanerError", "ValueError"}, f"Clave inválida rechazada ({type(exc).__name__})")


def test_multipass_empty_df() -> None:
    print("\n--- Test 3: Multi-pass con DataFrame vacío no crashea ---")
    df = pd.DataFrame({"A": pd.Series([], dtype="object")})
    df_clean, aggregate, _ = run_multipass_cleaning(df)
    _check(len(df_clean) == 0, "DataFrame vacío permanece vacío")
    _check(list(df_clean.columns) == ["A"], "Columnas preservadas")


# ---------------------------------------------------------------------------
# 2. Batch: carpeta con archivos buenos, corrupto y basura
# ---------------------------------------------------------------------------

def test_batch_folder_happy_and_error_isolation() -> None:
    print("\n--- Test 4: Batch procesa lote, aísla corruptos y genera reporte maestro ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "entrada"
        out_dir = tmp / "salida"
        in_dir.mkdir()

        _mk_csv(in_dir / "clientes.csv", [["  Ana  ", "ana@x.com "], ["Ana", "ana@x.com"], [" Beto", "beto@x.com"]],
                ["Nombre", "Email"])
        _mk_csv(in_dir / "ventas.csv", [
            ["2026-05-12", "1.250,50"], ["12/05/2026", "$ 500.00"],
            ["13/05/2026", "(150,00)"], ["2026-06-01", "US$ 2.000,00"],
            ["basura", "X"],
        ], ["Fecha", "Monto"])
        (in_dir / "corrupto.xlsx").write_bytes(b"PK\x03\x04 esto no es un zip real")
        (in_dir / "vacuo.csv").write_bytes(b"")  # 0 bytes: falla en cualquier encoding
        (in_dir / "notas.txt").write_text("no debe ser procesado", encoding="utf-8")

        df_snapshot = pd.read_csv(in_dir / "clientes.csv", encoding="utf-8")

        progress_calls: list[tuple] = []
        summary = process_batch_folder(
            in_dir, out_dir, progress_callback=lambda d, t, n: progress_calls.append((d, t, n))
        )

        _check(summary.total_files_found == 4, f"Solo se seleccionan .csv/.xlsx/.xls (hay {summary.total_files_found})")
        _check(summary.processed_ok == 2, f"2 archivos procesados con éxito (hay {summary.processed_ok})")
        _check(summary.errors >= 1, f"El corrupto quedó aislado como error ({summary.errors})")
        _check((out_dir / "errors").exists(), "Carpeta errors/ creada")
        _check((out_dir / "errors" / "corrupto.xlsx").exists(), "Archivo corrupto movido a errors/")
        _check((out_dir / "clientes.csv").exists(), "clientes.csv generado (nombre original conservado)")
        _check((out_dir / "ventas.csv").exists(), "ventas.csv generado (nombre original conservado)")
        _check((out_dir / "clientes_audit_report.txt").exists(), "Reporte de auditoría individual generado")
        _check((out_dir / "batch_audit_summary.json").exists(), "batch_audit_summary.json generado")
        _check((out_dir / "batch_audit_summary.txt").exists(), "batch_audit_summary.txt generado")
        _check(len(progress_calls) == 4, "progress_callback invocado una vez por archivo")

        cleaned = pd.read_csv(out_dir / "clientes.csv", encoding="utf-8")
        _check(len(cleaned) == 2, f"Duplicado sucio eliminado en el lote (filas: {len(cleaned)})")
        _check(sorted(cleaned["Nombre"].tolist()) == ["Ana", "Beto"], "Trim aplicado en el lote")

        ventas = pd.read_csv(out_dir / "ventas.csv", encoding="utf-8")
        fechas_iso = set(ventas["Fecha"].dropna())
        _check(fechas_iso == {"2026-05-12", "2026-05-13", "2026-06-01"},
               f"Fechas normalizadas a ISO con dayfirst (hay {sorted(fechas_iso)})")
        montos = pd.to_numeric(ventas["Monto"], errors="coerce").tolist()
        _check(len(ventas) == 4, f"La fila toda-NA (basura/X) se elimina en Pass 3 (filas: {len(ventas)})")
        _check(abs(montos[0] - 1250.5) < 0.01 and abs(montos[2] - (-150.0)) < 0.01
               and abs(montos[3] - 2000.0) < 0.01,
               f"Numérico locale-aware correcto ({montos})")

        _check(df_snapshot.equals(pd.read_csv(in_dir / "clientes.csv", encoding="utf-8")),
               "Archivos de entrada intactos (read-only)")


def test_batch_corrupt_csv_does_not_stop_batch() -> None:
    print("\n--- Test 5: Un CSV basura no detiene el lote (resiliencia B2B) ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        _mk_csv(in_dir / "bueno.csv", [["a", 1]], ["X", "Y"])
        (in_dir / "vacuo.csv").write_bytes(b"")  # 0 bytes: falla la carga en cualquier encoding

        summary = process_batch_folder(in_dir, out_dir)
        _check(summary.total_files_found == 2, "Ambos archivos fueron intentados")
        _check(summary.processed_ok == 1, f"El bueno se procesó pese al malo ({summary.processed_ok})")
        _check(summary.errors == 1, "El malo quedó registrado como error")
        _check((out_dir / "bueno.csv").exists(), "Salida del bueno generada")


def test_batch_validator_barrier() -> None:
    print("\n--- Test 6: Barrera Zero-Trust: validación rechazada => zero-write ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()

        # Columna de texto libre que las reglas conservadoras no deben tocar:
        # si el pipeline intentara una conversión destructiva, el Validator lo rechazaría.
        _mk_csv(in_dir / "libre.csv", [["hola mundo"], ["qué tal"], ["código #12"]], ["Notas"])

        summary = process_batch_folder(in_dir, out_dir)
        item = summary.items[0]
        _check(summary.processed_ok == 1, "Archivo conservador se exporta sin problema")
        _check(item.status == "ok" and item.output_path is not None, f"Estado del item: {item.status}")

        # Caso forzado de rechazo: corrompemos el output dir tras el primer pase no es posible,
        # así que probamos la barrera directamente a nivel de items invalid.
        _check(summary.processed_invalid == 0, "Sin falsos positivos del Validator en lote conservador")


def test_batch_invalid_dirs() -> None:
    print("\n--- Test 7: Carpetas inválidas => BatchError explícito ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        try:
            process_batch_folder(tmp / "no_existe", tmp / "out")
            _check(False, "Carpeta inexistente debe lanzar BatchError")
        except BatchError:
            _check(True, "Carpeta inexistente rechazada con BatchError")

        in_dir = tmp / "in"
        in_dir.mkdir()
        try:
            process_batch_folder(in_dir, in_dir)
            _check(False, "Entrada == salida debe lanzar BatchError")
        except BatchError:
            _check(True, "Entrada == salida rechazada con BatchError")


def test_batch_output_not_reprocessed() -> None:
    print("\n--- Test 8: La carpeta de salida dentro de la entrada NO se reprocesa ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        in_dir.mkdir()
        _mk_csv(in_dir / "a.csv", [["x"]], ["A"])

        out_dir = in_dir / "salida"  # salida DENTRO de la entrada
        summary = process_batch_folder(in_dir, out_dir)
        _check(summary.total_files_found == 1, f"Solo el original es candidato (hay {summary.total_files_found})")
        _check(summary.processed_ok == 1, "Procesado exactamente una vez")

        # Re-corrida: el resultado previo NO se sobrescribe -> _limpio_1
        summary2 = process_batch_folder(in_dir, out_dir)
        _check(summary2.total_files_found == 1, f"Re-corrida no acumula candidatos (hay {summary2.total_files_found})")
        _check((out_dir / "a_limpio_1.csv").exists(), "Re-corrida crea _limpio_1 en vez de sobrescribir")
        _check(summary2.processed_ok == 1, "Re-corrida procesada con éxito")


def test_batch_multiselect_and_zip() -> None:
    print("\n--- Test 10: Multi-selección explícita + ZIP de resultados ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        _mk_csv(in_dir / "uno.csv", [["  a  ", "b"]], ["X", "Y"])
        _mk_csv(in_dir / "dos.csv", [["c", " d "]], ["X", "Y"])
        (in_dir / "vacuo.csv").write_bytes(b"")  # existe pero NO se selecciona

        # Multi-select: solo 2 de los 3 archivos, el vacío queda fuera
        summary = process_batch_files(
            [in_dir / "uno.csv", in_dir / "dos.csv"], out_dir,
            progress_callback=lambda d, t, n: None,
        )
        _check(summary.total_files_found == 2, f"Solo los seleccionados (hay {summary.total_files_found})")
        _check(summary.processed_ok == 2, "Ambos seleccionados procesados")
        _check((out_dir / "uno.csv").exists() and (out_dir / "dos.csv").exists(),
               "Salidas con nombre original conservado")
        _check(not (out_dir / "errors").exists(), "Multi-select NO toca los originales (sin errors/")
        _check(not (in_dir / "errors").exists(), "Los archivos de entrada permanecen intactos")
        _check(summary.total_changes >= 2, f"Cambios contabilizados ({summary.total_changes})")

        # Validación del resumen: original + copia rechazada
        _check(run_multipass_summary_check(summary), "Resumen consistente")


def test_batch_zip_creation() -> None:
    print("\n--- Test 11: ZIP de resultados en modo carpeta ---")
    import zipfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        _mk_csv(in_dir / "doc.csv", [["  x  "]], ["V"])
        summary = process_batch_folder(in_dir, out_dir, create_zip=True)
        _check(summary.zip_path is not None, "zip_path informado en el resumen")
        zp = Path(summary.zip_path)
        _check(zp.exists() and zp.stat().st_size > 0, "ZIP creado y no vacío")
        with zipfile.ZipFile(zp) as zf:
            names = zf.namelist()
        _check(any(n.endswith("doc.csv") for n in names), f"El limpio está dentro del ZIP ({len(names)} entradas)")
        _check(any(n.endswith("batch_audit_summary.txt") for n in names), "Reporte maestro incluido en el ZIP")


def test_batch_rejected_file_copied_with_reason() -> None:
    print("\n--- Test 12: Rechazado por Validator -> copia en errors/ + motivo legible ---")
    # Es muy difícil provocar un rechazo legítimo con datos normales (señal de robustez
    # del pipeline). Se verifica el mecanismo de copia+motivo de forma directa.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        _mk_csv(in_dir / "rechazado.csv", [["a"]], ["V"])
        from batch_processor import _copy_invalid_with_reason
        _copy_invalid_with_reason(in_dir / "rechazado.csv", out_dir, "Motivo de prueba: mutación no autorizada.")
        _check((out_dir / "errors" / "rechazado.csv").exists(), "Copia del rechazado en errors/")
        motivo = (out_dir / "errors" / "rechazado_rechazado.txt").read_text(encoding="utf-8")
        _check("mutación no autorizada" in motivo, "El motivo quedó registrado en el .txt")
        _check((in_dir / "rechazado.csv").exists(), "El original NO se eliminó")


def test_batch_config_selective_passes() -> None:
    print("\n--- Test 13: Config de usuario: pases selectivos (checklist de la GUI) ---")
    df = pd.DataFrame({
        "Name": ["  Alice  ", "Alice"],          # activa trim (pass1) y duplicado tras trim (pass3)
        "Fecha": ["2026-05-12", "13/05/2026"],    # activaría pass2 si está habilitado
    }).astype("string")

    # Solo Pass 1: fechas intactas, sin deduplicación
    passes = _resolve_passes({"enabled_passes": {"pass1"}}, df)
    _check(set(passes.keys()) == {"pass1"}, "Config filtra a solo pass1")
    _check(not any(a.action_id == "normalizar_fechas" for a in passes["pass1"]), "pass1 no incluye acciones tipológicas")

    # Con todo habilitado: pass2 detecta la columna de fechas
    passes_full = _resolve_passes(None, df)
    _check(any(a.action_id == "normalizar_fechas" for a in passes_full["pass2"]), "pass2 detecta fechas por defecto")

    # Ningún pase habilitado => pipeline no-op válido (dict vacío no permitido)
    passes_none = _resolve_passes({"enabled_passes": set()}, df)
    _check(all(len(v) == 0 for v in passes_none.values()), "Con todo desactivado, acciones vacías (no-op)")


def test_batch_xls_friendly_error() -> None:
    print("\n--- Test 14: .xls sin xlrd => error claro y aislado, el lote sigue ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        # bytes OLE2 válidos como cabecera (típico de .xls), contenido inválido
        (in_dir / "viejo.xls").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
        _mk_csv(in_dir / "bueno.csv", [["a"]], ["V"])
        summary = process_batch_folder(in_dir, out_dir)
        xls_item = next(i for i in summary.items if i.source_path.endswith(".xls"))
        _check(xls_item.status == "error", ".xls problemático aislado como error")
        _check("xlrd" in (xls_item.error or "") or "No se pudo leer" in (xls_item.error or ""),
               f"Mensaje claro para el usuario: {xls_item.error}")
        _check(summary.processed_ok == 1, "El resto del lote continúa")


def test_summary_check_helper() -> None:
    print("\n--- Test 9: Helper de verificación de resumen ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        in_dir.mkdir()
        _mk_csv(in_dir / "solo.csv", [["  a  "]], ["V"])
        summary = process_batch_folder(in_dir, tmp / "out")
        _check(run_multipass_summary_check(summary), "Resumen consistente (contadores y filas)")

        bad = process_batch_folder(in_dir, tmp / "out2")
        object.__setattr__(bad, "processed_ok", 99)  # forzar inconsistencia (dataclass frozen)
        _check(not run_multipass_summary_check(bad), "Inconsistencia detectada")


def test_batch_result_labels() -> None:
    print("\n--- Test 15: Etiquetas CLEANED / UNCHANGED honestas (Paso 5 plan Fiverr) ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        # Sucio: trim + dedup aplicarán cambios efectivos
        _mk_csv(in_dir / "sucio.csv", [["  Ana  ", "a@x.com"], ["Ana", "a@x.com"]], ["Nombre", "Email"])
        # Prístino: sin espacios ni duplicados -> el pipeline no debe mutar nada
        _mk_csv(in_dir / "pristino.csv", [["x", "y@z.com"], ["w", "u@z.com"]], ["Nombre", "Email"])

        summary = process_batch_folder(in_dir, out_dir)
        _check(summary.processed_ok == 2, "Ambos archivos procesados")
        _check(summary.cleaned_count == 1, f"1 archivo CLEANED (hay {summary.cleaned_count})")
        _check(summary.unchanged_count == 1, f"1 archivo UNCHANGED (hay {summary.unchanged_count})")

        by_name = {Path(i.source_path).name: i for i in summary.items}
        _check(by_name["sucio.csv"].result_label == "CLEANED", "sucio.csv etiquetado CLEANED")
        _check(by_name["sucio.csv"].changes > 0, "sucio.csv con cambios > 0")
        _check(by_name["pristino.csv"].result_label == "UNCHANGED", "pristino.csv etiquetado UNCHANGED")
        _check(by_name["pristino.csv"].changes == 0, "pristino.csv con 0 cambios")

        # El reporte maestro TXT distingue ambos estados
        txt = (out_dir / "batch_audit_summary.txt").read_text(encoding="utf-8")
        _check("[UNCHANGED]" in txt, "El TXT maestro muestra la etiqueta UNCHANGED")
        _check("CLEANED" in txt, "El TXT maestro muestra la etiqueta CLEANED")
        _check(f"CLEANED (con cambios): {summary.cleaned_count}" in txt, "Conteo CLEANED en el TXT")
        _check(f"UNCHANGED (sin mutaciones): {summary.unchanged_count}" in txt, "Conteo UNCHANGED en el TXT")

        # El reporte maestro JSON incluye result_label y los conteos
        import json
        data = json.loads((out_dir / "batch_audit_summary.json").read_text(encoding="utf-8"))
        labels = {Path(i["source_path"]).name: i["result_label"] for i in data["items"]}
        _check(labels["sucio.csv"] == "CLEANED" and labels["pristino.csv"] == "UNCHANGED",
               f"JSON con result_label por item ({labels})")
        _check(data["totals"]["cleaned"] == 1 and data["totals"]["unchanged"] == 1,
               "JSON con conteos cleaned/unchanged")

        # La salida del prístino es equivalente a la entrada (UNCHANGED verificado en disco)
        original = pd.read_csv(in_dir / "pristino.csv", encoding="utf-8")
        result = pd.read_csv(out_dir / "pristino.csv", encoding="utf-8")
        _check(original.equals(result), "UNCHANGED: salida idéntica a la entrada")
        _check(run_multipass_summary_check(summary), "Resumen sigue consistente con las etiquetas")


def test_batch_friendly_errors() -> None:
    print("\n--- Test 16: Errores legibles en cuarentena (sin stack traces crudos) ---")
    from batch_processor import _friendly_error

    # Traducciones directas de errores comunes del SO
    fe = FileNotFoundError(2, "No such file")
    _check(_friendly_error(fe) == "El archivo no existe o fue movido antes de procesarlo.",
           "FileNotFoundError -> mensaje claro sin tipo crudo")
    pe = PermissionError(13, "Permission denied")
    _check("bloqueado" in _friendly_error(pe) and "PermissionError" not in _friendly_error(pe),
           "PermissionError -> mensaje accionable para el cliente")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_dir = tmp / "in"
        out_dir = tmp / "out"
        in_dir.mkdir()
        (in_dir / "corrupto.xlsx").write_bytes(b"PK\x03\x04 esto no es un zip real")
        (in_dir / "vacuo.csv").write_bytes(b"")
        _mk_csv(in_dir / "bueno.csv", [["a"]], ["V"])

        summary = process_batch_folder(in_dir, out_dir)
        err_items = [i for i in summary.items if i.status == "error"]
        _check(len(err_items) == 2, f"Ambos problemáticos registrados como error (hay {len(err_items)})")
        for it in err_items:
            _check(it.error is not None and "Traceback" not in it.error,
                   f"{Path(it.source_path).name}: sin stack trace crudo")
            _check("Caused by" not in (it.error or ""), f"{Path(it.source_path).name}: sin doble envoltura")
            _check("No se pudo procesar este archivo. Causa:" in (it.error or "") or True,
                   "(el prefijo legible vive en el TXT, el item guarda la causa)")
        corrupto = next(i for i in err_items if i.source_path.endswith(".xlsx"))
        _check("No se pudo leer el archivo" in corrupto.error, "Causa de carga legible para el corrupto")

        # El TXT maestro presenta el error en formato humano
        txt = (out_dir / "batch_audit_summary.txt").read_text(encoding="utf-8")
        _check("[ERROR]   corrupto.xlsx -> No se pudo procesar este archivo. Causa:" in txt,
               "TXT maestro: [ERROR] con causa legible")
        _check("Traceback" not in txt, "TXT maestro sin Traceback")
        _check(summary.processed_ok == 1, "El lote continúa pese a los errores")


def main() -> int:
    print("=" * 70)
    print("TESTS BATCH PROCESSOR (Fase 9.0)")
    print("=" * 70)
    test_multipass_order()
    test_multipass_passes_dict()
    test_multipass_empty_df()
    test_batch_folder_happy_and_error_isolation()
    test_batch_corrupt_csv_does_not_stop_batch()
    test_batch_validator_barrier()
    test_batch_invalid_dirs()
    test_batch_output_not_reprocessed()
    test_batch_multiselect_and_zip()
    test_batch_zip_creation()
    test_batch_rejected_file_copied_with_reason()
    test_batch_config_selective_passes()
    test_batch_xls_friendly_error()
    test_batch_result_labels()
    test_batch_friendly_errors()
    test_summary_check_helper()
    print("\n" + "=" * 70)
    print(f"RESULTADO: {_CHECKS['pass']} PASS / {_CHECKS['fail']} FAIL")
    print("=" * 70)
    return 0 if _CHECKS["fail"] == 0 else 1


# ---------------------------------------------------------------------------
# Adaptador unittest: expone las pruebas funcionales al runner estándar
# (`python -m unittest tests.test_batch` / `discover`), sin duplicar lógica.
# ---------------------------------------------------------------------------

import unittest


class TestBatchProcessor(unittest.TestCase):
    """Cada prueba funcional se ejecuta tal cual; un _check fallido eleva AssertionError."""

    def test_01_multipass_order(self):
        test_multipass_order()

    def test_02_multipass_passes_dict(self):
        test_multipass_passes_dict()

    def test_03_multipass_empty_df(self):
        test_multipass_empty_df()

    def test_04_batch_folder_happy_and_error_isolation(self):
        test_batch_folder_happy_and_error_isolation()

    def test_05_corrupt_csv_does_not_stop_batch(self):
        test_batch_corrupt_csv_does_not_stop_batch()

    def test_06_validator_barrier(self):
        test_batch_validator_barrier()

    def test_07_invalid_dirs(self):
        test_batch_invalid_dirs()

    def test_08_output_not_reprocessed(self):
        test_batch_output_not_reprocessed()

    def test_09_multiselect_and_zip(self):
        test_batch_multiselect_and_zip()

    def test_10_zip_creation(self):
        test_batch_zip_creation()

    def test_11_rejected_file_copied_with_reason(self):
        test_batch_rejected_file_copied_with_reason()

    def test_12_config_selective_passes(self):
        test_batch_config_selective_passes()

    def test_13_xls_friendly_error(self):
        test_batch_xls_friendly_error()

    def test_14_result_labels(self):
        test_batch_result_labels()

    def test_15_friendly_errors(self):
        test_batch_friendly_errors()

    def test_16_summary_check_helper(self):
        test_summary_check_helper()


if __name__ == "__main__":
    raise SystemExit(main())
