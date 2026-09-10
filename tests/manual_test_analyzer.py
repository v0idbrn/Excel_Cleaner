"""Prueba manual de analyzer.py (Fase 2 - Refinamiento y Stress final).

Suite de pruebas exhaustiva sin dependencias externas (solo stdlib y pandas).
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer import (
    AnalyzerError,
    analyze_dataframe,
    analyze_file,
    build_file_info,
    load_dataframe,
)


def _check(condition: bool, description: str) -> None:
    status = "[OK]" if condition else "[FAIL]"
    print(f"{status} {description}")
    if not condition:
        raise AssertionError(description)


def _test_csv_variations(tmp_dir: Path) -> None:
    print("\n--- Probando variaciones CSV ---")
    
    # 1. Normal, 2. Separado por ';' y 3. Caracteres Españoles
    csv_normal = tmp_dir / "normal.csv"
    csv_normal.write_text("ID;Nombre;Ciudad\n1;José;España\n2;María;Málaga\n", encoding="utf-8")
    rep = analyze_file(csv_normal)
    _check(rep.row_count == 2 and rep.column_count == 3, "CSV normal, separado por ';' y caracteres españoles")
    
    # 4. Una sola columna
    csv_single = tmp_dir / "single.csv"
    csv_single.write_text("Correos\nuno@test.com\ndos@test.com\n")
    rep2 = analyze_file(csv_single)
    _check(rep2.row_count == 2 and rep2.column_count == 1, "CSV de una sola columna procesado correctamente")
    
    # 5, 6, 7. Valores NA, null y strings vacíos
    csv_na = tmp_dir / "na_test.csv"
    csv_na.write_text("ID,Valor,Vacio\n1,NA,\n2,null, \n")
    
    file_info = build_file_info(csv_na)
    df = load_dataframe(file_info)
    
    _check(df.iloc[0]["Valor"] == "NA" and type(df.iloc[0]["Valor"]) == str, 'Literal "NA" verificado como string exacto')
    _check(df.iloc[1]["Valor"] == "null" and type(df.iloc[1]["Valor"]) == str, 'Literal "null" verificado como string exacto')
    _check(pd.isna(df.iloc[0]["Vacio"]), 'String vacío ("") convertido en valor faltante genuino')


def _test_xlsx_variations(tmp_dir: Path) -> None:
    print("\n--- Probando variaciones XLSX ---")
    xlsx_path = tmp_dir / "multi.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        pd.DataFrame({"A": [1]}).to_excel(writer, sheet_name="Hoja1", index=False)
        pd.DataFrame().to_excel(writer, sheet_name="Vacia", index=False)
        pd.DataFrame({"B": [2]}).to_excel(writer, sheet_name="Hoja3", index=False)
        
    rep = analyze_file(xlsx_path, sheet_name="Hoja1")
    _check(rep.file_info.sheet_names == ("Hoja1", "Vacia", "Hoja3"), "XLSX lee todas las hojas")
    
    try:
        analyze_file(xlsx_path, sheet_name="Vacia")
        _check(False, "XLSX con hoja vacía debería lanzar AnalyzerError")
    except AnalyzerError:
        _check(True, "XLSX hoja vacía lanza AnalyzerError")


def _test_structural_validations(tmp_dir: Path) -> None:
    print("\n--- Probando validaciones estructurales (Seguridad) ---")
    
    # CSV Columnas Duplicadas
    csv_dup = tmp_dir / "dup.csv"
    csv_dup.write_text("Col1,Col1\n1,2\n")
    try:
         analyze_file(csv_dup)
         _check(False, "CSV dup cols debería fallar")
    except AnalyzerError:
         _check(True, "CSV columnas duplicadas interceptado preventivamente")

    # CSV Encabezado Vacío o espacios: desde el plan Fiverr (paso 4) el archivo NO se
    # rechaza: la columna se auto-nombra 'Columna_N' y se emite un issue para revisión.
    csv_empty_header = tmp_dir / "empty_head.csv"
    csv_empty_header.write_text("Col1,  ,Col3\n1,2,3\n")
    report_empty_header = analyze_file(csv_empty_header)
    cols_loaded = [s.name for s in report_empty_header.column_stats]
    unnamed = [i for i in report_empty_header.issues if i.category == "ENCABEZADO_AUTO_GENERADO"]
    _check("Columna_2" in cols_loaded, "CSV encabezado en blanco: columna auto-nombrada y cargada")
    _check(len(unnamed) == 1, "CSV encabezado en blanco: issue de revisión emitido")

    # XLSX Columnas Duplicadas
    xlsx_dup = tmp_dir / "dup.xlsx"
    with pd.ExcelWriter(xlsx_dup, engine="openpyxl") as writer:
        df = pd.DataFrame([[1,2]], columns=["ColA", "ColB"])
        df.columns = ["ColA", "ColA"] # Forzamos duplicado en origen
        df.to_excel(writer, index=False)
    try:
         analyze_file(xlsx_dup)
         _check(False, "XLSX dup cols debería fallar")
    except AnalyzerError:
         _check(True, "XLSX columnas duplicadas interceptado preventivamente")

    # XLSX Encabezado en Blanco: misma tolerancia que CSV (auto-nombre + issue).
    xlsx_empty_header = tmp_dir / "empty_head.xlsx"
    with pd.ExcelWriter(xlsx_empty_header, engine="openpyxl") as writer:
        df2 = pd.DataFrame([[1,2]], columns=["ColA", " "])
        df2.to_excel(writer, index=False)
    report_xlsx_empty = analyze_file(xlsx_empty_header)
    cols_xlsx = [s.name for s in report_xlsx_empty.column_stats]
    unnamed_xlsx = [i for i in report_xlsx_empty.issues if i.category == "ENCABEZADO_AUTO_GENERADO"]
    _check("Columna_2" in cols_xlsx, "XLSX encabezado en blanco: columna auto-nombrada y cargada")
    _check(len(unnamed_xlsx) == 1, "XLSX encabezado en blanco: issue de revisión emitido")

    # Archivo Vacío
    empty_file = tmp_dir / "vacio.csv"
    empty_file.write_bytes(b"")
    try:
         analyze_file(empty_file)
    except AnalyzerError:
         _check(True, "Archivo de 0 bytes lanza AnalyzerError")

    # Límite de tamaño 
    import config
    original_limit = config.MAX_FILE_SIZE_BYTES
    try:
         config.MAX_FILE_SIZE_BYTES = 100 # Reducimos limitación dinámicamente para forzar fallo
         big_file = tmp_dir / "big.csv"
         big_file.write_bytes(b"a" * 200)
         try:
             analyze_file(big_file)
             _check(False, "Archivo supera límite debería fallar")
         except AnalyzerError:
             _check(True, "Límite de tamaño dinámico (config) respetado y probado")
    finally:
         config.MAX_FILE_SIZE_BYTES = original_limit


def _test_analyzer_integrity(tmp_dir: Path) -> None:
    print("\n--- Probando integridad del Analyzer y Progress Callback ---")
    
    csv_path = tmp_dir / "integ.csv"
    csv_path.write_text("Nombre,Edad\nJuan,30\nMaria,25\n")
    
    file_info = build_file_info(csv_path)
    df = load_dataframe(file_info)
    df_original = df.copy(deep=True)
    
    calls = []
    def progress(step: int, total: int, msg: str):
        calls.append((step, total, msg))
        
    analyze_dataframe(df, file_info, None, progress_callback=progress)
    
    _check(len(calls) > 0, "Callback de progreso fue invocado")
    _check(calls[0][0] == 1 and calls[-1][0] == calls[0][1], "Callback recibe iteración y total coherente")
    _check(isinstance(calls[0][2], str), "Callback recibe string de mensaje")
    
    try:
        pd.testing.assert_frame_equal(df, df_original)
        _check(True, "El DataFrame original no fue modificado en absoluto (Read-Only)")
    except AssertionError:
        _check(False, "El Analyzer modificó el DataFrame original (Violación de read-only)")


def _test_stress(tmp_dir: Path) -> None:
    print("\n--- Prueba de Estrés (200.000 filas) ---")
    stress_csv = tmp_dir / "stress.csv"
    
    base = [{"ID": i, "Nombre": f"Test {i}", "Fecha": "2024-01-01", "Correo": "test@test.com", "Valor": 100} for i in range(10)]
    df = pd.DataFrame(base * 20000)
    df.to_csv(stress_csv, index=False)
    
    start_time = time.perf_counter()
    report = analyze_file(stress_csv)
    end_time = time.perf_counter()
    
    elapsed = end_time - start_time
    _check(report.row_count == 200000, f"Stress test funcional superado (Tiempo real estimado: ~{elapsed:.2f}s)")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="excel_cleaner_") as tmp:
        tmp_dir = Path(tmp)
        try:
            _test_csv_variations(tmp_dir)
            _test_xlsx_variations(tmp_dir)
            _test_structural_validations(tmp_dir)
            _test_analyzer_integrity(tmp_dir)
            _test_stress(tmp_dir)
        except AssertionError:
            print("\nALGUNA PRUEBA FALLÓ.")
            return 1

    print("\nTODAS LAS PRUEBAS PASARON CORRECTAMENTE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())