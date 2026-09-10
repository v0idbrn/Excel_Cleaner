"""Pruebas unitarias de seguridad y robustez para exporter.py (Fase 5)."""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner import clean_dataframe
from exporter import (
    AUDIT_SHEET_NAME,
    ExportError,
    export_dataframe,
    export_audit_report,
    generate_audit_report,
)
from models import AuditReport, CleaningAction, CleaningResult, ValidationResult


def _check(condition: bool, description: str) -> None:
    status = "[OK]" if condition else "[FAIL]"
    print(f"{status} {description}")
    if not condition:
        raise AssertionError(description)

def get_valid():
    return ValidationResult(valid=True, errors=(), warnings=())

def get_invalid():
    return ValidationResult(valid=False, errors=("Simulated Error",), warnings=())

def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        df_base = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        
        print("\n--- Tests de Seguridad y Barreras ---")
        
        # Test 1 — Validation PASS
        out_t1 = tmp_path / "t1.csv"
        res = export_dataframe(df_base, out_t1, get_valid())
        _check(out_t1.exists() and res.success, "Test 1: valid=True permite exportar.")
        
        # Test 2 — Validation FAIL
        out_t2 = tmp_path / "t2.csv"
        try:
            export_dataframe(df_base, out_t2, get_invalid())
            _check(False, "Test 2: validation=False debió lanzar ExportError.")
        except ExportError:
            _check(not out_t2.exists(), "Test 2: valid=False bloquea exportación y no crea archivo.")
            
        # Test 3 & Ataque A — Zero-write
        out_t3 = tmp_path / "t3.csv"
        try:
            export_dataframe(df_base, out_t3, get_invalid())
        except ExportError:
            _check(not out_t3.exists(), "Test 3 & Ataque A: ZERO-WRITE confirmado en ruta nueva.")
            
        # Test 4 & Ataque B — Existing file protection & Zero Write
        out_t4 = tmp_path / "t4.csv"
        out_t4.write_text("PREV_CONTENT")
        try:
            export_dataframe(df_base, out_t4, get_invalid(), overwrite=True)
        except ExportError:
            _check(out_t4.read_text() == "PREV_CONTENT", "Test 4 & Ataque B: ZERO-WRITE. Archivo existente queda intacto si valid=False.")
            
        # Test 11 — Existing file (Overwrite Policy)
        out_t11 = tmp_path / "t11.csv"
        export_dataframe(df_base, out_t11, get_valid())
        try:
            export_dataframe(df_base, out_t11, get_valid(), overwrite=False)
            _check(False, "Test 11: Debió bloquear sobrescritura.")
        except ExportError as e:
            _check("ya existe" in str(e), "Test 11: Bloqueo de sobrescritura implícita funciona.")
            
        # Test 20 & Ataque C — Validation gate precedence
        out_t20 = tmp_path / "t20.csv"
        try:
            export_dataframe(df_base, out_t20, get_invalid())
        except ExportError as e:
            _check("no ha superado la validación" in str(e), "Test 20 & Ataque C: Validation FAIL bloquea primero antes de cualquier otro chequeo.")

        print("\n--- Tests de Formatos y Datos ---")

        # Test 5, 6, 7, 8, 9, 10 — CSV, XLSX, Unicode, Specials, Nulls, No Index
        df_complex = pd.DataFrame({
            "Unicode": ["José", "Muñoz", "áéíóúñ"],
            "Specials": ["Coma, acá", "Punto; coma", "Salto\nlínea"],
            "Nulls": [pd.NA, np.nan, None]
        })
        out_csv = tmp_path / "complex.csv"
        out_xlsx = tmp_path / "complex.xlsx"
        export_dataframe(df_complex, out_csv, get_valid())
        export_dataframe(df_complex, out_xlsx, get_valid())
        
        txt = out_csv.read_text(encoding="utf-8")
        _check("José" in txt and "Muñoz" in txt, "Test 7: Unicode y acentos preservados en CSV.")
        _check('"Coma, acá"' in txt or "Coma, acá" in txt, "Test 8: Comas y saltos de línea manejados correctamente.")
        _check(txt.startswith("Unicode,Specials,Nulls"), "Test 10: Índice de pandas ignorado (index=False).")
        _check(out_xlsx.exists() and out_xlsx.stat().st_size > 0, "Test 6: XLSX básico exportado con éxito.")
        
        # Test 16 & 17 — Round Trips
        df_round_csv = pd.read_csv(out_csv, encoding="utf-8")
        _check(df_round_csv["Unicode"].iloc[0] == "José", "Test 16: Round-trip CSV exitoso.")
        
        df_round_xlsx = pd.read_excel(out_xlsx)
        _check(df_round_xlsx["Unicode"].iloc[1] == "Muñoz", "Test 17: Round-trip XLSX exitoso.")

        print("\n--- Tests de I/O y Entorno ---")
        
        # Test 12 — Invalid extension
        try:
            export_dataframe(df_base, tmp_path / "test.json", get_valid())
            _check(False, "Debería fallar extensión")
        except ExportError as e:
            _check("Formato no soportado" in str(e), "Test 12: Extensión no soportada falla controladamente.")
            
        # Test 13 & 14 — Dir instead of file / Invalid Dir
        try:
            export_dataframe(df_base, tmp_path, get_valid())
        except ExportError as e:
            _check("directorio" in str(e).lower(), "Test 13: Detecta directorio en lugar de archivo.")
            
        try:
            export_dataframe(df_base, tmp_path / "fake_dir" / "out.csv", get_valid())
        except ExportError as e:
            _check("no existe" in str(e).lower(), "Test 14: Directorio padre inexistente detectado.")
            
        # Test 15 — DataFrame Immutability
        df_imm = pd.DataFrame({"X": [10, 20]})
        df_copy = df_imm.copy(deep=True)
        export_dataframe(df_imm, tmp_path / "imm.csv", get_valid())
        _check(df_imm.equals(df_copy), "Test 15: DataFrame original permanece estrictamente inmutable.")
        
        print("\n--- Tests de Stress y Rendimiento ---")
        
        # Test 18 & 19 — Large Data
        df_large = pd.DataFrame({"A": np.random.randn(50000), "B": ["Text"] * 50000})
        out_large_csv = tmp_path / "large.csv"
        out_large_xlsx = tmp_path / "large.xlsx"
        
        t0 = time.perf_counter()
        export_dataframe(df_large, out_large_csv, get_valid())
        t1 = time.perf_counter()
        _check(True, f"Test 18: CSV 50k rows exportado en {t1-t0:.4f}s.")
        
        t0 = time.perf_counter()
        export_dataframe(df_large, out_large_xlsx, get_valid())
        t1 = time.perf_counter()
        _check(True, f"Test 19: XLSX 50k rows exportado en {t1-t0:.4f}s.")

        print("\n[INFO] Sobre el Ataque D (Mutación post-validación): El Validator provee el pasaporte (ValidationResult). El Exporter confía en este pasaporte. Si el atacante corrompe el DF en la memoria RAM de Python exactamente en la fracción de segundo entre que el Validator responde y el Exporter escribe, el Exporter lo escribirá. Solucionar esto exigiría inyectar un hash criptográfico en el ValidationResult, lo cual excede el MVP actual y fue documentado como limitación aceptada.")

    # ============================================================
    # TESTS DE AUDITORIA (FASE 8.5)
    # ============================================================

    print("\n--- Tests de Auditoria (Fase 8.5) ---")

    # Test A1: Creacion basica del reporte de auditoria
    print("\n--- Test A1: Creacion basica del reporte de auditoria ---")
    df_orig = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})
    df_clean = pd.DataFrame({"A": [1, 3], "B": ["x", "z"]})

    action = CleaningAction("eliminar_filas_vacias", None, "Borrar vacias", approved=True)
    cleaning_result = CleaningResult(
        actions_applied=(action,),
        rows_before=3,
        rows_after=2,
        columns_before=2,
        columns_after=2,
    )
    validation_result = ValidationResult(valid=True)

    report = generate_audit_report(
        original_file="datos_original.csv",
        export_file="datos_limpio.xlsx",
        cleaning_result=cleaning_result,
        validation_result=validation_result,
        df_original=df_orig,
        df_clean=df_clean,
    )

    _check(report.original_file == "datos_original.csv", "Archivo original registrado")
    _check(report.export_file == "datos_limpio.xlsx", "Archivo exportado registrado")
    _check(report.rows_before == 3, "Filas antes correctas")
    _check(report.rows_after == 2, "Filas despues correctas")
    _check(report.rows_removed == 1, "Filas eliminadas correctas")
    _check(report.columns_before == 2, "Columnas antes correctas")
    _check(report.columns_after == 2, "Columnas despues correctas")
    _check(report.validation_valid is True, "Validacion es True")
    _check(len(report.actions_executed) == 1, "1 accion ejecutada registrada")
    _check(report.actions_executed[0].action_id == "eliminar_filas_vacias", "Accion correcta registrada")
    _check(report.is_valid is True, "Propiedad is_valid OK")
    _check(isinstance(report.export_timestamp, datetime), "Timestamp es datetime")

    # Test A2: Transforms calculados automaticamente por columna
    print("\n--- Test A2: Transforms calculados automaticamente ---")
    df_orig2 = pd.DataFrame({
        "Precio": ["$1,250.50", "$500.00", "invalido"],
        "Cantidad": [10, pd.NA, 30],
    })
    df_clean2 = pd.DataFrame({
        "Precio": [1250.5, 500.0, pd.NA],
        "Cantidad": [10, pd.NA, 30],
    })

    action_precio = CleaningAction(
        "normalizar_numerico", "Precio", "", approved=True,
        parameters={"locale": "us"},
    )
    action_cantidad = CleaningAction(
        "convertir_a_nulo", "Cantidad", "", approved=True,
    )

    df_clean_real, cleaning_result2 = clean_dataframe(df_orig2, (action_precio, action_cantidad))
    validation_result2 = ValidationResult(valid=True)

    report2 = generate_audit_report(
        original_file="datos.csv",
        export_file="datos_limpio.csv",
        cleaning_result=cleaning_result2,
        validation_result=validation_result2,
        df_original=df_orig2,
        df_clean=df_clean_real,
    )

    _check(len(report2.transforms) == 2, f"Se generaron {len(report2.transforms)} transforms (esperados 2)")

    transforms_map = {t.column: t for t in report2.transforms}

    if "Precio" in transforms_map:
        t = transforms_map["Precio"]
        _check(t.action_id == "normalizar_numerico", "Transform Precio: action correcto")
        _check(t.input_dtype != t.output_dtype, "Transform Precio: cambio de tipo detectado")
        _check(t.nulls_after == 1, "Transform Precio: 1 nulo al final (invalido)")
        _check(t.values_changed >= 2, "Transform Precio: valores cambiados detectados")

    if "Cantidad" in transforms_map:
        t = transforms_map["Cantidad"]
        _check(t.action_id == "convertir_a_nulo", "Transform Cantidad: action correcto")
        _check(t.nulls_before == 1, "Transform Cantidad: 1 nulo al inicio")
        _check(t.nulls_after == 1, "Transform Cantidad: 1 nulo al final")

    # Test A3: Reporte refleja validacion fallida
    print("\n--- Test A3: Reporte con validacion fallida ---")
    df_orig3 = pd.DataFrame({"A": [1]})
    df_clean3 = pd.DataFrame({"A": [999]})

    action3 = CleaningAction("trim_espacios", "A", "", approved=True)
    cleaning_result3 = CleaningResult(
        actions_applied=(action3,),
        rows_before=1,
        rows_after=1,
        columns_before=1,
        columns_after=1,
    )
    validation_result3 = ValidationResult(
        valid=False,
        errors=("Mutacion no autorizada detectada en la columna 'A'.",),
    )

    report3 = generate_audit_report(
        original_file="original.csv",
        export_file="limpio.xlsx",
        cleaning_result=cleaning_result3,
        validation_result=validation_result3,
        df_original=df_orig3,
        df_clean=df_clean3,
    )

    _check(report3.validation_valid is False, "Validacion es False")
    _check(len(report3.validation_errors) == 1, "1 error de validacion registrado")
    _check("Mutacion no autorizada" in report3.validation_errors[0], "Error especifico registrado")
    _check(report3.is_valid is False, "is_valid refleja invalidacion")

    # Test A4: Serializacion a dict para exportacion JSON
    print("\n--- Test A4: Serializacion a dict ---")
    df_orig4 = pd.DataFrame({"A": [1]})
    df_clean4 = pd.DataFrame({"A": [1]})

    action4 = CleaningAction("trim_espacios", "A", "", approved=True)
    cleaning_result4 = CleaningResult(
        actions_applied=(action4,),
        rows_before=1,
        rows_after=1,
        columns_before=1,
        columns_after=1,
    )
    validation_result4 = ValidationResult(valid=True)

    report4 = generate_audit_report(
        original_file="orig.csv",
        export_file="clean.csv",
        cleaning_result=cleaning_result4,
        validation_result=validation_result4,
        df_original=df_orig4,
        df_clean=df_clean4,
    )

    d = report4.to_dict()

    _check(isinstance(d, dict), "to_dict devuelve dict")
    _check(d["original_file"] == "orig.csv", "Campo original_file")
    _check(d["export_file"] == "clean.csv", "Campo export_file")
    _check(d["rows_before"] == 1, "Campo rows_before")
    _check(d["rows_after"] == 1, "Campo rows_after")
    _check(d["validation_valid"] is True, "Campo validation_valid")
    _check(isinstance(d["actions_executed"], list), "actions_executed es lista")
    _check(len(d["actions_executed"]) == 1, "1 accion en actions_executed")
    _check(d["actions_executed"][0]["action_id"] == "trim_espacios", "action_id serializado")

    # Test A5: Exportacion del reporte a archivo TXT
    print("\n--- Test A5: Exportacion de reporte a TXT ---")
    with tempfile.TemporaryDirectory() as tmpdir5:
        tmpdir5_path = Path(tmpdir5)

        df_orig5 = pd.DataFrame({"A": [1, 2, 3]})
        df_clean5 = pd.DataFrame({"A": [1, 3]})

        action5 = CleaningAction("eliminar_duplicados_exactos", None, "", approved=True)
        cleaning_result5 = CleaningResult(
            actions_applied=(action5,),
            rows_before=3,
            rows_after=2,
            columns_before=1,
            columns_after=1,
        )
        validation_result5 = ValidationResult(valid=True)

        report5 = generate_audit_report(
            original_file="datos_original.csv",
            export_file=tmpdir5_path / "datos_limpio.csv",
            cleaning_result=cleaning_result5,
            validation_result=validation_result5,
            df_original=df_orig5,
            df_clean=df_clean5,
        )

        report_path = Path(export_audit_report(report5, output_dir=tmpdir5_path, format="txt"))

        _check(report_path.exists(), "Archivo TXT creado")
        _check(report_path.stat().st_size > 0, "Archivo TXT no vacio")
        _check(report_path.suffix == ".txt", "Extension .txt")

        content = report_path.read_text(encoding="utf-8")
        _check("REPORTE DE AUDITORIA" in content, "Encabezado presente")
        _check("Archivo Original: datos_original.csv" in content, "Archivo original en contenido")
        _check("Filas antes: 3" in content, "Metrika filas antes")
        _check("Filas despues: 2" in content, "Metrika filas despues")
        _check("Filas eliminadas: 1" in content, "Metrika filas eliminadas")
        _check("VALIDO" in content, "Estado validacion VALIDO")
        _check("eliminar_duplicados_exactos" in content, "Accion en contenido")
        _check("ACCIONES EJECUTADAS" in content, "Seccion acciones presente")
        _check("TRANSFORMACIONES POR COLUMNA" in content, "Seccion transforms presente")
        _check("FIN DEL REPORTE DE AUDITORIA" in content, "Pie de pagina presente")

    # Test A6: Exportacion del reporte a archivo JSON
    print("\n--- Test A6: Exportacion de reporte a JSON ---")
    with tempfile.TemporaryDirectory() as tmpdir6:
        tmpdir6_path = Path(tmpdir6)

        df_orig6 = pd.DataFrame({"X": [1]})
        df_clean6 = pd.DataFrame({"X": [1]})

        action6 = CleaningAction("trim_espacios", "X", "", approved=True)
        cleaning_result6 = CleaningResult(
            actions_applied=(action6,),
            rows_before=1,
            rows_after=1,
            columns_before=1,
            columns_after=1,
        )
        validation_result6 = ValidationResult(valid=True)

        report6 = generate_audit_report(
            original_file="datos.csv",
            export_file=tmpdir6_path / "salida.xlsx",
            cleaning_result=cleaning_result6,
            validation_result=validation_result6,
            df_original=df_orig6,
            df_clean=df_clean6,
        )

        report_path6 = Path(export_audit_report(report6, output_dir=tmpdir6_path, format="json"))

        _check(report_path6.exists(), "Archivo JSON creado")
        _check(report_path6.suffix == ".json", "Extension .json")

        import json as json_mod
        data6 = json_mod.loads(report_path6.read_text(encoding="utf-8"))

        _check(isinstance(data6, dict), "Contenido JSON es dict")
        _check(data6["original_file"] == "datos.csv", "original_file en JSON")
        _check(data6["export_file"] == str(tmpdir6_path / "salida.xlsx"), "export_file en JSON")
        _check(data6["rows_before"] == 1, "rows_before en JSON")
        _check(data6["validation_valid"] is True, "validation_valid en JSON")
        _check("export_timestamp" in data6, "export_timestamp en JSON")
        _check("cleaner_version" in data6, "cleaner_version en JSON")
        _check(isinstance(data6["actions_executed"], list), "actions_executed en JSON")

    # Test A7: export_audit_report usa directorio del archivo exportado si no se especifica
    print("\n--- Test A7: Directorio automatico para reporte ---")
    with tempfile.TemporaryDirectory() as tmpdir7:
        tmpdir7_path = Path(tmpdir7)
        export_path7 = tmpdir7_path / "subcarpeta" / "datos.xlsx"
        export_path7.parent.mkdir(parents=True, exist_ok=True)

        df_orig7 = pd.DataFrame({"A": [1]})
        df_clean7 = pd.DataFrame({"A": [1]})

        action7 = CleaningAction("trim_espacios", "A", "", approved=True)
        cleaning_result7 = CleaningResult(
            actions_applied=(action7,),
            rows_before=1,
            rows_after=1,
            columns_before=1,
            columns_after=1,
        )
        validation_result7 = ValidationResult(valid=True)

        report7 = generate_audit_report(
            original_file="original.csv",
            export_file=str(export_path7),
            cleaning_result=cleaning_result7,
            validation_result=validation_result7,
            df_original=df_orig7,
            df_clean=df_clean7,
        )

        report_path7 = Path(export_audit_report(report7, format="txt"))

        _check(report_path7.parent == export_path7.parent, "Directorio del reporte = directorio del archivo exportado")
        _check(report_path7.name == "datos_audit_report.txt", "Nombre del reporte basado en archivo exportado")

    # Test A8: La generacion del reporte no altera los DataFrames originales
    print("\n--- Test A8: Integridad de DataFrames durante generacion de reporte ---")
    df_orig8 = pd.DataFrame({"A": [1, 2, pd.NA], "B": ["x", "y", "z"]})
    df_clean8 = pd.DataFrame({"A": [1, 2], "B": ["x", "z"]})

    df_orig8_copy = df_orig8.copy(deep=True)
    df_clean8_copy = df_clean8.copy(deep=True)

    action8 = CleaningAction("eliminar_filas_vacias", None, "", approved=True)
    cleaning_result8 = CleaningResult(
        actions_applied=(action8,),
        rows_before=3,
        rows_after=2,
        columns_before=2,
        columns_after=2,
    )
    validation_result8 = ValidationResult(valid=True)

    _ = generate_audit_report(
        original_file="orig.csv",
        export_file="clean.csv",
        cleaning_result=cleaning_result8,
        validation_result=validation_result8,
        df_original=df_orig8,
        df_clean=df_clean8,
    )

    pd.testing.assert_frame_equal(df_orig8, df_orig8_copy)
    pd.testing.assert_frame_equal(df_clean8, df_clean8_copy)
    _check(True, "DataFrames originales intactos despues de generar reporte")

    # ------------------------------------------------------------------
    # Tests Paso 8 — Pestaña de auditoría embebida en XLSX (_Reporte_Auditoria)
    # ------------------------------------------------------------------
    print("\n--- Tests Paso 8: Pestaña _Reporte_Auditoria dentro del XLSX ---")

    with tempfile.TemporaryDirectory() as tmpdir_p8:
        tmp_p8 = Path(tmpdir_p8)
        df_p8_orig = pd.DataFrame({"Nombre": ["  Ana  ", "Beto"], "Monto": [1, 2]})
        df_p8_clean = pd.DataFrame({"Nombre": ["Ana", "Beto"], "Monto": [1, 2]})
        action_p8 = CleaningAction("trim_espacios", "Nombre", "", approved=True)
        cr_p8 = CleaningResult((action_p8,), 2, 2, 2, 2, ())
        val_p8 = ValidationResult(valid=True)
        rep_p8 = generate_audit_report(
            original_file="origen.csv",
            export_file="limpio.xlsx",
            cleaning_result=cr_p8,
            validation_result=val_p8,
            df_original=df_p8_orig,
            df_clean=df_p8_clean,
        )

        # 1. XLSX con auditoría embebida: pestañas Datos + _Reporte_Auditoria
        xlsx_p8 = tmp_p8 / "p8_con_auditoria.xlsx"
        export_dataframe(df_p8_clean, xlsx_p8, val_p8, audit_report=rep_p8)
        with pd.ExcelFile(xlsx_p8) as ef_p8:
            sheets_p8 = list(ef_p8.sheet_names)
        _check(sheets_p8 == ["Datos", AUDIT_SHEET_NAME],
               f"XLSX contiene Datos + {AUDIT_SHEET_NAME} (hay {sheets_p8})")

        # 2. Contenido de la pestaña: resumen, timestamp, acciones, columnas modificadas
        audit_p8 = pd.read_excel(xlsx_p8, sheet_name=AUDIT_SHEET_NAME, header=None)
        pairs_p8 = {}
        for _, row_p8 in audit_p8.iterrows():
            label_p8, value_p8 = row_p8.iloc[0], row_p8.iloc[1]
            if pd.notna(label_p8) and pd.notna(value_p8):
                pairs_p8[str(label_p8)] = value_p8
        _check(pairs_p8.get("Filas originales") == 2 and pairs_p8.get("Filas finales") == 2,
               "Resumen filas originales vs finales en la pestaña")
        _check(pairs_p8.get("Filas eliminadas") == 0 and pairs_p8.get("Columnas finales") == 2,
               "Métricas de columnas y eliminadas en la pestaña")
        _check("Fecha/Hora UTC" in pairs_p8, "Timestamp presente en la pestaña")
        _check(pairs_p8.get("Validación Zero-Trust") == "VÁLIDA", "Veredicto de validación presente")
        _check("Archivo original" in pairs_p8 and pairs_p8.get("Archivo original") == "origen.csv",
               "Trazabilidad del archivo original presente")
        act_rows_p8 = audit_p8[audit_p8.iloc[:, 0] == "trim_espacios"]
        _check(len(act_rows_p8) == 1 and str(act_rows_p8.iloc[0, 1]) == "Nombre",
               "Acción ejecutada listada con su columna")
        _check("Columnas modificadas" in set(audit_p8.iloc[:, 0].dropna().astype(str)),
               "Sección 'Columnas modificadas' presente")

        # 3. La pestaña de datos queda intacta
        datos_p8 = pd.read_excel(xlsx_p8, sheet_name="Datos")
        _check(list(datos_p8["Nombre"]) == ["Ana", "Beto"] and list(datos_p8["Monto"]) == [1, 2],
               "Pestaña Datos intacta tras embeber la auditoría")

        # 4. CSV: plano por diseño, sin pestañas (no es contenedor zip)
        csv_p8 = tmp_p8 / "p8_plano.csv"
        export_dataframe(df_p8_clean, csv_p8, val_p8, audit_report=rep_p8)
        raw_p8 = csv_p8.read_bytes()
        _check(raw_p8.startswith(b"Nombre,Monto"), "CSV se mantiene plano (sin pestañas)")
        _check(not raw_p8.startswith(b"PK"), "CSV no es un contenedor XLSX/zip")

        # 5. Compatibilidad: sin audit_report el XLSX queda solo con 'Datos'
        xlsx_p8b = tmp_p8 / "p8_sin_auditoria.xlsx"
        export_dataframe(df_p8_clean, xlsx_p8b, val_p8)
        with pd.ExcelFile(xlsx_p8b) as ef_p8b:
            _check(list(ef_p8b.sheet_names) == ["Datos"], "Sin audit_report: XLSX solo 'Datos' (compatibilidad)")

        # 6. Zero-write intacto: validación inválida bloquea aunque se pase audit_report
        xlsx_p8c = tmp_p8 / "p8_bloqueado.xlsx"
        try:
            export_dataframe(df_p8_clean, xlsx_p8c, get_invalid(), audit_report=rep_p8)
            _check(False, "Invalid debe bloquear aunque se pase audit_report")
        except ExportError:
            _check(True, "Zero-write intacto: invalid + audit_report => ExportError")
            _check(not xlsx_p8c.exists(), "Ningún archivo creado tras el bloqueo")

    print("\nTODOS LOS TESTS DE AUDITORIA PASARON.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())