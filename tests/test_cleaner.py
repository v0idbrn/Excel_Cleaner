"""Prueba manual exhaustiva de cleaner.py (Fase 3 Optimizada).

Sin dependencias externas. Verifica la correcta ejecución determinista,
garantías de solo-lectura y optimizaciones de pandas 3.x.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner import CleanerError, clean_dataframe
from models import CleaningAction


def _check(condition: bool, description: str) -> None:
    status = "[OK]" if condition else "[FAIL]"
    print(f"{status} {description}")
    if not condition:
        raise AssertionError(description)


def test_read_only():
    print("\n--- Test 1: Inmutabilidad (Read-Only) ---")
    df = pd.DataFrame({"A": [1, pd.NA, 3], "B": ["x", pd.NA, "z"]})
    df_original = df.copy(deep=True)
    
    action = CleaningAction("eliminar_filas_vacias", None, "Borrar", approved=True)
    
    # Solo ejecutamos para verificar que df no muta, ignoramos las salidas
    clean_dataframe(df, (action,))
    
    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "El DataFrame original no fue modificado.")


def test_filas_vacias():
    print("\n--- Test 2: Eliminar filas vacías ---")
    df = pd.DataFrame({"A": [1, pd.NA, 2], "B": ["x", pd.NA, "y"]})
    action = CleaningAction("eliminar_filas_vacias", None, "", approved=True)
    
    df_clean, _ = clean_dataframe(df, (action,))
    _check(len(df_clean) == 2, "Se eliminó la fila vacía")
    _check(list(df_clean.index) == [0, 1], "El índice se reseteó correctamente")


def test_columnas_vacias():
    print("\n--- Test 3: Eliminar columnas vacías ---")
    df = pd.DataFrame({"A": [1, 2], "B": [pd.NA, pd.NA], "C": ["x", "y"]})
    action = CleaningAction("eliminar_columnas_vacias", None, "", approved=True)
    
    df_clean, _ = clean_dataframe(df, (action,))
    _check("B" not in df_clean.columns, "Se eliminó la columna 'B' vacía")
    _check(len(df_clean.columns) == 2, "Las columnas restantes se preservaron")


def test_duplicados_exactos():
    print("\n--- Test 4: Eliminar duplicados exactos ---")
    df = pd.DataFrame({"A": [1, 1, 2], "B": ["Juan", "Juan", "Pedro"]})
    action = CleaningAction("eliminar_duplicados_exactos", None, "", approved=True)
    
    df_clean, _ = clean_dataframe(df, (action,))
    _check(len(df_clean) == 2, "Se eliminó el duplicado exacto")
    _check(df_clean.iloc[0]["B"] == "Juan" and df_clean.iloc[1]["B"] == "Pedro", "Conserva la primera aparición")


def test_trim_espacios_multicolumna():
    print("\n--- Test 5b: Trim multi-columna simultáneo (Texto completo) ---")
    df = pd.DataFrame({
        "Name": pd.Series([" Grace Hopper ", "Ada Lovelace "], dtype="string"),
        "Email": ["grace@example.com ", "ada@example.com "],
        "City": [" London ", "  Pisa "],
        "Numbers": [1, 2],
        "Bools": [True, False],
        "Mixed": [pd.NA, None]
    })
    df_original = df.copy(deep=True)

    actions = tuple(
        CleaningAction("trim_espacios", col, "trim", approved=True)
        for col in ["Name", "Email", "City"]
    )
    df_clean, _ = clean_dataframe(df, actions)

    _check(df_clean["Name"].iloc[0] == "Grace Hopper", "Name trim = Grace Hopper")
    _check(df_clean["Name"].iloc[1] == "Ada Lovelace", "Name trim = Ada Lovelace (respeta interno)")
    _check(df_clean["Email"].iloc[0] == "grace@example.com", "Email trim = grace@example.com")
    _check(df_clean["Email"].iloc[1] == "ada@example.com", "Email trim = ada@example.com")
    _check(df_clean["City"].iloc[0] == "London", "City trim = London")
    _check(df_clean["City"].iloc[1] == "Pisa", "City trim = Pisa (respeta interno)")
    _check(df_clean["Numbers"].tolist() == [1, 2], "Números intactos")
    # Booleans no son strings, el trim los deja intactos por valor (no por referencia)
    _check(bool(df_clean["Bools"].iloc[0]) is True and bool(df_clean["Bools"].iloc[1]) is False, "Booleanos intactos por valor")
    _check(pd.isna(df_clean["Mixed"].iloc[0]) and df_clean["Mixed"].iloc[1] is None, "pd.NA/None intactos (valor + identidad)")

    # Inmutabilidad global del original
    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado en ninguna columna (incluye Name/Email/City)")


def test_trim_espacios():
    print("\n--- Test 5: Trim de espacios seguros y optimizados ---")
    df = pd.DataFrame({
        "Name": pd.Series([" Grace Hopper ", "Ada Lovelace "], dtype="string"),
        "Email": ["grace@example.com ", "ada@example.com "],
        "City": [" London ", " Pisa "],
        "Numbers": [1, 2],
        "Bools": [True, False],
        "Mixed": [pd.NA, None]
    })
    df_original = df.copy(deep=True)

    actions = tuple(
        CleaningAction("trim_espacios", col, "trim", approved=True)
        for col in ["Name", "Email", "City"]
    )
    df_clean, _ = clean_dataframe(df, actions)

    _check(df_clean["Name"].iloc[0] == "Grace Hopper", "Name trim = Grace Hopper")
    _check(df_clean["Name"].iloc[1] == "Ada Lovelace", "Name trim = Ada Lovelace")
    _check(df_clean["Email"].iloc[0] == "grace@example.com", "Email trim = grace@example.com")
    _check(df_clean["Email"].iloc[1] == "ada@example.com", "Email trim = ada@example.com")
    _check(df_clean["City"].iloc[0] == "London", "City trim = London")
    _check(df_clean["City"].iloc[1] == "Pisa", "City trim = Pisa")
    _check(df_clean["Numbers"].tolist() == [1, 2], "Números intactos")
    # Booleans no son strings, el trim los deja intactos por valor (no por referencia)
    _check(bool(df_clean["Bools"].iloc[0]) is True and bool(df_clean["Bools"].iloc[1]) is False, "Booleanos intactos por valor")
    _check(pd.isna(df_clean["Mixed"].iloc[0]) and df_clean["Mixed"].iloc[1] is None, "pd.NA/None intactos (valor + identidad)")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado en ninguna columna (incluye Name/Email/City)")


def test_trim_espacios_optimizado():
    print("\n--- Test 5: Trim de espacios seguros y optimizados (StringDtype) ---")
    df = pd.DataFrame({
        "A": pd.Series([" Juan ", "Pedro", " María  "], dtype="string"),
        "B": [10, True, 30.5], 
        "C": [pd.NA, "null", "  "]
    })
    
    act_a = CleaningAction("trim_espacios", "A", "", approved=True)
    act_b = CleaningAction("trim_espacios", "B", "", approved=True)
    act_c = CleaningAction("trim_espacios", "C", "", approved=True)
    
    df_clean, _ = clean_dataframe(df, (act_a, act_b, act_c))
    
    _check(df_clean.iloc[0]["A"] == "Juan", "Se hizo trim sobre la columna vectorizada (StringDtype)")
    _check(df_clean.iloc[2]["A"] == "María", "Ignoró espacios internos")
    _check(df_clean["B"].iloc[1] is True, "Preservó literales booleanos intactos sin crashear")
    _check(pd.isna(df_clean.iloc[0]["C"]), "No corrompió pd.NA genuinos convirtiéndolos en strings 'nan'")
    _check(df_clean.iloc[2]["C"] == "", "Convirtió espacios sueltos en string vacío")


def test_convertir_nulo():
    print("\n--- Test 6: Convertir strings vacíos a nulos verdaderos ---")
    df = pd.DataFrame({"Text": ["Juan", "", "   ", "Pedro", "NA", "null"]})
    action = CleaningAction("convertir_a_nulo", "Text", "", approved=True)
    
    df_clean, _ = clean_dataframe(df, (action,))
    
    _check(df_clean.iloc[0]["Text"] == "Juan", "Respeta textos normales")
    _check(pd.isna(df_clean.iloc[1]["Text"]), "Convierte string vacío a pd.NA")
    _check(pd.isna(df_clean.iloc[2]["Text"]), "Convierte espacios vacíos a pd.NA")
    _check(df_clean.iloc[4]["Text"] == "NA", "No toca literales textuales 'NA'")


def test_convertir_numerico_seguro():
    print("\n--- Test 7: Conversión numérica robusta ---")
    df_ok = pd.DataFrame({"Nums": ["10", "20.5", "30", pd.NA]})
    action = CleaningAction("convertir_a_numerico", "Nums", "", approved=True)
    df_clean, _ = clean_dataframe(df_ok, (action,))
    _check(df_clean["Nums"].iloc[1] == 20.5, "Conversión numérica correcta")
    
    df_bad = pd.DataFrame({"Nums": ["10", "ABC", "30"]})
    try:
        clean_dataframe(df_bad, (action,))
        _check(False, "Debería lanzar error por conversión destructiva")
    except CleanerError as e:
        _check("ABC" in str(e), "Interceptó la pérdida de información (ABC)")


def test_acciones_invalidas():
    print("\n--- Test 8: Acciones desconocidas y manejo de seguridad ---")
    df = pd.DataFrame({"A": [1]})
    
    try:
        act = CleaningAction("fusionar_cosas_raras", "A", "", approved=True)
        clean_dataframe(df, (act,))
        _check(False, "Debería lanzar error por acción desconocida")
    except CleanerError:
        _check(True, "Bloqueó acción desconocida.")


def test_orden_multiacccion():
    print("\n--- Test 9: Ejecución secuencial exacta ---")
    df = pd.DataFrame({"A": ["Juan ", "   ", pd.NA], "B": [1, pd.NA, pd.NA]})
    
    actions = (
        CleaningAction("trim_espacios", "A", "", approved=True),
        CleaningAction("convertir_a_nulo", "A", "", approved=True),
        CleaningAction("eliminar_filas_vacias", None, "", approved=True),
    )
    
    df_clean, res = clean_dataframe(df, actions)
    _check(len(df_clean) == 1, "Las acciones encadenadas eliminaron correctamente la fila combinada")
    _check(len(res.actions_applied) == 3, "Registro histórico almacenado")


def test_normalizar_mayusculas_upper():
    print("\n--- Test 11: Normalizar mayúsculas (format=upper, default) ---")
    df = pd.DataFrame({
        "Name": ["juan perez", "MARIA GOMEZ", "  ana silva  "],
        "City": ["buenos aires", "CORDOBA", None],
        "Num": [1, 2, 3]
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_mayusculas", "Name", "upper",
        approved=True,
        parameters={"format": "upper"}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Name"].iloc[0] == "JUAN PEREZ", "String -> UPPER")
    _check(df_clean["Name"].iloc[1] == "MARIA GOMEZ", "Ya mayúsculas -> UPPER (idéntico)")
    _check(df_clean["Name"].iloc[2] == "  ANA SILVA  ", "String con espacios -> UPPER respeta espacios externos")
    _check(df_clean["City"].iloc[0] == "buenos aires", "Columna no seleccionada intacta")
    _check(pd.isna(df_clean["City"].iloc[2]), "None preservado (como NA)")
    _check(df_clean["Num"].tolist() == [1, 2, 3], "Columna numérica intacta")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    # Inmutabilidad
    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_mayusculas_title():
    print("\n--- Test 12: Normalizar mayúsculas (format=title) ---")
    df = pd.DataFrame({
        "Name": ["juan perez", "MARIA GOMEZ", "  ana maria silva  "],
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_mayusculas", "Name", "title",
        approved=True,
        parameters={"format": "title"}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Name"].iloc[0] == "Juan Perez", "String -> Title Case")
    _check(df_clean["Name"].iloc[1] == "Maria Gomez", "UPPER -> Title Case")
    _check(df_clean["Name"].iloc[2] == "  Ana Maria Silva  ", "Title respeta espacios externos")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_mayusculas_lower():
    print("\n--- Test 13: Normalizar mayúsculas (format=lower) ---")
    df = pd.DataFrame({
        "Name": ["JUAN PEREZ", "María Gómez", pd.NA],
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_mayusculas", "Name", "lower",
        approved=True,
        parameters={"format": "lower"}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Name"].iloc[0] == "juan perez", "UPPER -> lower")
    _check(df_clean["Name"].iloc[1] == "maría gómez", "Mixed -> lower (respeta unicode)")
    _check(pd.isna(df_clean["Name"].iloc[2]), "pd.NA preservado")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_mayusculas_default_upper():
    print("\n--- Test 14: Normalizar mayúsculas (sin parámetros -> default upper) ---")
    df = pd.DataFrame({
        "Name": ["juan perez", "maria"],
    })
    df_original = df.copy(deep=True)

    # Sin parámetros -> debe default a upper
    action = CleaningAction(
        "normalizar_mayusculas", "Name", "default",
        approved=True,
        parameters={}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Name"].iloc[0] == "JUAN PEREZ", "Sin params -> default upper")
    _check(df_clean["Name"].iloc[1] == "MARIA", "Sin params -> default upper")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_mayusculas_string_dtype():
    print("\n--- Test 15: Normalizar mayúsculas con StringDtype ---")
    df = pd.DataFrame({
        "Name": pd.Series(["juan", "maria", "pedro"], dtype="string"),
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_mayusculas", "Name", "",
        approved=True,
        parameters={"format": "upper"}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Name"].iloc[0] == "JUAN", "StringDtype -> UPPER")
    _check(df_clean["Name"].iloc[1] == "MARIA", "StringDtype -> UPPER")
    _check(pd.api.types.is_string_dtype(df_clean["Name"]), "Mantiene StringDtype")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_fechas_iso():
    print("\n--- Test 16: Normalizar fechas a ISO 8601 ---")
    df = pd.DataFrame({
        "Fecha": ["12/05/2026", "2026-05-12", "09-05-2026", "2026/03/15", pd.NA, None, ""],
        "Valor": [1, 2, 3, 4, 5, 6, 7]
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_fechas", "Fecha", "",
        approved=True,
        parameters={}
    )
    df_clean, res = clean_dataframe(df, (action,))

    # Fecha válida DD/MM/YYYY -> ISO
    _check(df_clean["Fecha"].iloc[0] == "2026-05-12", "12/05/2026 -> 2026-05-12")
    # Fecha ya ISO YYYY-MM-DD -> ISO (idéntica)
    _check(df_clean["Fecha"].iloc[1] == "2026-05-12", "2026-05-12 -> 2026-05-12")
    # Fecha DD-MM-YYYY -> ISO
    _check(df_clean["Fecha"].iloc[2] == "2026-05-09", "09-05-2026 -> 2026-05-09")
    # Fecha YYYY/MM/DD -> ISO
    _check(df_clean["Fecha"].iloc[3] == "2026-03-15", "2026/03/15 -> 2026-03-15")
    # pd.NA preservado
    _check(pd.isna(df_clean["Fecha"].iloc[4]), "pd.NA preservado")
    # None preservado (como NA)
    _check(pd.isna(df_clean["Fecha"].iloc[5]), "None preservado")
    # String vacío -> NaT -> pd.NA (es válido perderlo en normalizar_fechas)
    _check(pd.isna(df_clean["Fecha"].iloc[6]), "String vacío -> nulo (válido)")
    # Columna no afectada intacta
    _check(df_clean["Valor"].tolist() == [1, 2, 3, 4, 5, 6, 7], "Columna Valor intacta")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_fechas_con_basura():
    print("\n--- Test 17: Normalizar fechas con texto basura (loss aceptable) ---")
    df = pd.DataFrame({
        "Fecha": ["12/05/2026", "no es fecha", "ABC", "2026-01-01", "   "],
        "Valor": [1, 2, 3, 4, 5]
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_fechas", "Fecha", "",
        approved=True,
        parameters={}
    )
    df_clean, res = clean_dataframe(df, (action,))

    # Fecha válida se conserva
    _check(df_clean["Fecha"].iloc[0] == "2026-05-12", "Fecha válida conservada")
    # Texto basura -> nulo (pérdida aceptable)
    _check(pd.isna(df_clean["Fecha"].iloc[1]), "'no es fecha' -> nulo (loss aceptable)")
    # ABC -> nulo (loss aceptable)
    _check(pd.isna(df_clean["Fecha"].iloc[2]), "'ABC' -> nulo (loss aceptable)")
    # Fecha válida
    _check(df_clean["Fecha"].iloc[3] == "2026-01-01", "Fecha válida conservada")
    # Espacios -> nulo
    _check(pd.isna(df_clean["Fecha"].iloc[4]), "Espacios -> nulo")
    # Columna no afectada intacta
    _check(df_clean["Valor"].tolist() == [1, 2, 3, 4, 5], "Columna Valor intacta")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    # Verificar que el warning fue generado
    _check(any("no se pudieron interpretar" in w for w in res.warnings), "Warning de pérdida generado")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_fechas_string_dtype():
    print("\n--- Test 18: Normalizar fechas con StringDtype ---")
    df = pd.DataFrame({
        "Fecha": pd.Series(["12/05/2026", "2026-06-15", "01-01-2025"], dtype="string"),
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_fechas", "Fecha", "",
        approved=True,
        parameters={}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Fecha"].iloc[0] == "2026-05-12", "StringDtype fecha -> ISO")
    _check(df_clean["Fecha"].iloc[1] == "2026-06-15", "StringDtype ISO -> ISO")
    _check(df_clean["Fecha"].iloc[2] == "2025-01-01", "StringDtype DD-MM-YYYY -> ISO")
    _check(len(res.actions_applied) == 1, "Acción registrada")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_normalizar_fechas_valido_y_invalido_mezclado():
    print("\n--- Test 19: Mezcla de fechas válidas e inválidas ---")
    df = pd.DataFrame({
        "Fecha": ["12/05/2026", "no es fecha", "2026-12-31", "XYZ", "05/06/2025", pd.NA],
    })
    df_original = df.copy(deep=True)

    action = CleaningAction(
        "normalizar_fechas", "Fecha", "",
        approved=True,
        parameters={}
    )
    df_clean, res = clean_dataframe(df, (action,))

    _check(df_clean["Fecha"].iloc[0] == "2026-05-12", "Válida DD/MM/YYYY")
    _check(pd.isna(df_clean["Fecha"].iloc[1]), "Inválida -> nulo")
    _check(df_clean["Fecha"].iloc[2] == "2026-12-31", "Válida ISO")
    _check(pd.isna(df_clean["Fecha"].iloc[3]), "Inválida XYZ -> nulo")
    _check(df_clean["Fecha"].iloc[4] == "2025-06-05", "Válida DD/MM/YYYY año 2025")
    _check(pd.isna(df_clean["Fecha"].iloc[5]), "pd.NA preservado")
    _check(any("no se pudieron interpretar" in w for w in res.warnings), "Warning generado")

    pd.testing.assert_frame_equal(df, df_original)
    _check(True, "DataFrame original no mutado")


def test_stress():
    print("\n--- Test 20: Estrés funcional del Cleaner (50.000 filas) ---")
    # Tipado explícito a dict[str, Any] para que Pylance no infiera dict[str, str] 
    # y permita extender la lista con diccionarios que contienen pd.NA
    base_rows: list[dict[str, Any]] = [{"A": f" Val {i} ", "B": "   ", "C": "100"} for i in range(10)]
    base_rows.extend([{"A": " Val 0 ", "B": "   ", "C": "100"}] * 2) 
    base_rows.extend([{"A": pd.NA, "B": pd.NA, "C": pd.NA}] * 3)
    
    df = pd.DataFrame(base_rows * 3334)  # ~50,000 filas
    
    actions = (
        CleaningAction("trim_espacios", "A", "", approved=True),
        CleaningAction("convertir_a_nulo", "B", "", approved=True),
        CleaningAction("convertir_a_numerico", "C", "", approved=True),
        CleaningAction("eliminar_filas_vacias", None, "", approved=True),
        CleaningAction("eliminar_duplicados_exactos", None, "", approved=True),
    )
    
    start_time = time.perf_counter()
    df_clean, _ = clean_dataframe(df, actions)
    elapsed = time.perf_counter() - start_time
    
    _check(len(df_clean) == 10, f"Estrés superado resolviendo masivamente (Tardó: {elapsed:.3f}s)")


# ---------------------------------------------------------------------------
# DIRECTIVA DE INVARIANZA ESTRUCTURAL (Anti-Desplazamiento)
# ---------------------------------------------------------------------------

def _make_fingerprint_df(n_records: int = 6) -> pd.DataFrame:
    """DataFrame donde cada celda codifica su posición: 'r<i>|c<j>'.

    Cualquier desplazamiento vertical (shift) o mezcla de columnas rompe
    el fingerprint => detectable de forma inequívoca.
    """
    rows = [
        {f"C{j}": f"r{i}|c{j}" for j in range(1, 4)}  # C1, C2, C3
        for i in range(n_records)
    ]
    df = pd.DataFrame(rows, columns=["C1", "C2", "C3"])
    # Fila 2 (medio): totalmente vacía -> debe desaparecer COMO BLOQUE.
    df.loc[2, :] = pd.NA
    # Fila 4 (medio): duplicado exacto de la fila 3 (con espacios para pasar por trim).
    df.loc[4, :] = " r3|c1 ", " r3|c2 ", " r3|c3 "
    return df


def _assert_row_integrity(df: pd.DataFrame, context: str) -> None:
    """Comprueba que ninguna celda se desvió de su fila/columna original.

    - Todas las celdas de una misma fila comparten el mismo ID de fila.
    - Todas las filas comparten el mismo patrón de columnas (c1|c2|c3).
    """
    for idx, row in df.iterrows():
        values = [str(v) for v in row]
        row_ids = {v.split("|")[0].strip() for v in values}
        assert len(row_ids) == 1, (
            f"[{context}] DESALINEACIÓN en fila {idx}: celdas de filas distintas "
            f"conviven -> {values}"
        )
        col_parts = tuple(v.split("|")[1].strip() for v in values)
        assert col_parts == ("c1", "c2", "c3"), (
            f"[{context}] MEZCLA DE COLUMNAS en fila {idx}: {values}"
        )


def test_invarianza_estructural_eliminacion_central():
    print("\n--- Test 21: Invarianza estructural: fila vacía y duplicado EN EL MEDIO ---")
    df = _make_fingerprint_df()
    df_snapshot = df.copy(deep=True)

    actions = (
        CleaningAction("trim_espacios", "C1", "", approved=True),
        CleaningAction("trim_espacios", "C2", "", approved=True),
        CleaningAction("trim_espacios", "C3", "", approved=True),
        CleaningAction("eliminar_filas_vacias", None, "", approved=True),
        CleaningAction("eliminar_duplicados_exactos", None, "", approved=True),
    )
    df_clean, result = clean_dataframe(df, actions)

    # La fila vacía del medio desapareció como BLOQUE (rows_before=6 -> after=4... 
    # 6 filas - 1 vacía - 1 duplicado = 5? No: la fila 4 es duplicado de la 3 TRAS trim,
    # y la fila 3 tiene espacios? No: fila 3 es limpia 'r3|cX', fila 4 es ' r3|cX ' ->
    # solo son duplicadas tras el trim. 6 - 1 vacía - 1 duplicado = 4 filas.
    _check(len(df_clean) == 4, f"Se eliminaron exactamente 2 filas (vacía + duplicada): {len(df_clean)}")
    _check(list(df_clean.columns) == ["C1", "C2", "C3"], "Columnas intactas y en orden")

    # núcleo de la directiva: cada fila restante sigue siendo un bloque horizontal íntegro
    _assert_row_integrity(df_clean, "post-limpieza")
    _check(True, "Sin desplazamiento de celdas: cada fila conserva su bloque horizontal íntegro")

    # Los IDs de fila sobrevivientes son exactamente los legítimos (0,1,3,5)
    surviving_ids = {str(df_clean.iloc[i, 0]).split("|")[0].strip() for i in range(len(df_clean))}
    _check(surviving_ids == {"r0", "r1", "r3", "r5"},
           f"Sobreviven exactamente las filas correctas (en bloque rígido): {sorted(surviving_ids)}")

    # El trim NO desplazó nada: el valor trimmed sigue siendo r3|cX
    row_r3 = df_clean[df_clean.apply(lambda r: str(r["C1"]).strip().startswith("r3|"), axis=1)]
    _check(len(row_r3) == 1, "El duplicado trimado se deduplicó sin afectar a la fila original r3")

    # Read-only del original
    _check(df.equals(df_snapshot), "DataFrame original intacto")

    # El Validator (proyección matemática) también respeta la invarianza:
    from validators import validate_cleaning
    validation = validate_cleaning(df, df_clean, actions, result)
    _check(validation.valid, f"Validator aprueba la eliminación en bloque sin falsos positivos: {validation.errors}")


def test_invarianza_estructural_multipass():
    print("\n--- Test 22: Invarianza estructural a través del motor multi-pass ---")
    from cleaner import run_multipass_cleaning

    df = _make_fingerprint_df()
    df.loc[5, :] = pd.NA  # segunda fila vacía al final
    df_snapshot = df.copy(deep=True)

    df_clean, aggregate, per_pass = run_multipass_cleaning(df)

    _assert_row_integrity(df_clean, "multi-pass")
    _check(True, "Multi-pass: sin desplazamiento de celdas entre pasadas")
    _check(aggregate.rows_before == 6 and aggregate.rows_after == 3,
           f"Métricas del agregado correctas (6 - 2 vacías - 1 duplicado = 3): {aggregate.rows_before} -> {aggregate.rows_after}")
    # Las 2 vacías (inicio-medio y final) se fueron como bloques, no fila a fila mezclada
    surviving_ids = {str(df_clean.iloc[i, 0]).split("|")[0].strip() for i in range(len(df_clean))}
    _check(surviving_ids == {"r0", "r1", "r3"},
           f"Bloques sobrevivientes exactos: {sorted(surviving_ids)}")
    _check(df.equals(df_snapshot), "Original intacto tras el pipeline completo")


def test_normalizar_numerico_auto_guardas_fiverr():
    """Test 23 (Paso 2 plan Fiverr): heurística locale=auto + guardas anti-corrupción.

    Regresiones demostradas en auditoría (antes -> después):
      - '1,250'   -> 1.25  (CORRUPCIÓN validada) -> 1250.0
      - '08011'   -> 8011.0 (código postal destruido) -> NA + warning
      - ID 17 dig -> 1.23e+16 (corrupción float) -> NA + warning
    """
    print("\n--- Test 23: normalizar_numerico auto (miles US + guardas de ID) ---")

    def _run(values, params=None):
        df = pd.DataFrame({"Col": values})
        action = CleaningAction(
            "normalizar_numerico", "Col", "test",
            approved=True, parameters=params or {"locale": "auto"},
        )
        out, res = clean_dataframe(df, (action,))
        return out["Col"].reset_index(drop=True), res

    # 1) Miles US solo-coma: coma de miles, NO decimal (antes: 1.25 / 12.0)
    s, _ = _run(["1,250", "12,000", "150"])
    _check(bool(s.iloc[0] == 1250.0), "'1,250' -> 1250.0 (era 1.25)")
    _check(bool(s.iloc[1] == 12000.0), "'12,000' -> 12000.0 (era 12.0)")
    _check(bool(s.iloc[2] == 150.0), "'150' sin cambios -> 150.0")

    # 2) Multi-grupo: '1,250,000' son miles (antes: NA)
    s, _ = _run(["1,250,000"])
    _check(bool(s.iloc[0] == 1250000.0), "'1,250,000' -> 1250000.0 (antes NA)")

    # 3) Decimales legítimos intactos en auto
    s, _ = _run(["900,00", "1250.50"])
    _check(bool(s.iloc[0] == 900.0), "EU decimal '900,00' -> 900.0")
    _check(bool(s.iloc[1] == 1250.5), "US decimal '1250.50' -> 1250.5")

    # 4) Guarda: ceros a la izquierda (IDs/códigos postales) -> NA + warning visible
    s, res = _run(["08011", "0123", "4567"])
    _check(bool(pd.isna(s.iloc[0]) and pd.isna(s.iloc[1])), "'08011'/'0123' NO convertidos (antes 8011.0/123.0)")
    _check(bool(s.iloc[2] == 4567.0), "'4567' sin ceros sigue convirtiendo")
    _check(len(res.warnings) == 1, "pérdida de IDs reportada con warning (cero silencio)")

    # 5) Guarda: enteros largos (>= 13 dígitos, riesgo float) -> NA + warning
    s, res = _run(["12345678901234567", "999", "888"])
    _check(bool(pd.isna(s.iloc[0])), "ID de 17 dígitos NO convertido (antes 1.23e+16)")
    _check(bool(s.iloc[1] == 999.0 and s.iloc[2] == 888.0), "enteros cortos normales sí convierten")
    _check(len(res.warnings) == 1, "pérdida del ID largo reportada con warning")

    # 6) Los guardas son SOLO de modo auto: el usuario explícito decide
    s, res = _run(["08011", "0123"], {"locale": "eu"})
    _check(bool(s.iloc[0] == 8011.0 and s.iloc[1] == 123.0), "locale=eu explícito bypasea guardas (decisión del usuario)")

    # 7) La sonda automática NO postula columnas de ID/teléfono
    from cleaner import _auto_actions_from_analysis
    df_id = pd.DataFrame({"Otro": ["a", "b", "c", "d"], "ID": ["12345678901234567", "999", "888", "777"]})
    passes = _auto_actions_from_analysis(df_id)
    _check(len(passes["pass2"]) == 0, "sonda: columna de ID largo -> sin acción automática")

    df_tel = pd.DataFrame({"Otro": ["a", "b", "c", "d"], "Tel": ["+54 9 11 5555-1234", "08011-4444", "+1 555 010 9999", "555-0100"]})
    passes = _auto_actions_from_analysis(df_tel)
    _check(len(passes["pass2"]) == 0, "sonda: columna de teléfonos -> sin acción automática")

    # 8) La sonda SÍ detecta % y pasa el parámetro (antes: '15%' -> NA silencioso)
    df_pct = pd.DataFrame({"Otro": ["a", "b", "c", "d"], "Descuento": ["15%", "20%", "30%", "25%"]})
    passes = _auto_actions_from_analysis(df_pct)
    pct_actions = [a for a in passes["pass2"] if a.action_id == "normalizar_numerico"]
    _check(len(pct_actions) == 1, "sonda: columna de % -> normalizar_numerico propuesto")
    _check(pct_actions[0].parameters.get("convert_percentages") is True, "sonda: convert_percentages=True en columna de %")
    s, _ = _run(["15%", "20%"], {"locale": "auto", "convert_percentages": True})
    _check(bool(s.iloc[0] == 0.15 and s.iloc[1] == 0.20), "'15%' -> 0.15 con convert_percentages=True")

    # 9) Mezcla ambigua de % (30% y 25 sin %) -> NO adivinar: no proponer
    df_mix = pd.DataFrame({"Otro": ["a", "b", "c", "d", "e"], "Mixto": ["15%", "20%", "30%", "25", "30"]})
    passes = _auto_actions_from_analysis(df_mix)
    _check(len(passes["pass2"]) == 0, "sonda: % mezclado ambiguo -> no se propone (marcar, no adivinar)")


def test_normalizar_numerico_multi_locale_mixto():
    """Test 24 (Paso 2): los formatos mixtos reales siguen intactos tras el fix."""
    print("\n--- Test 24: formatos monetarios mixtos ---")
    df = pd.DataFrame({"Saldo": ["$1.250,50", "US$ 900,00", "(150,00)", "3.999,99"]})
    action = CleaningAction(
        "normalizar_numerico", "Saldo", "test",
        approved=True, parameters={"locale": "auto"},
    )
    out, res = clean_dataframe(df, (action,))
    col = out["Saldo"].reset_index(drop=True)
    _check(bool(col.iloc[0] == 1250.5), "$1.250,50 -> 1250.5")
    _check(bool(col.iloc[1] == 900.0), "US$ 900,00 -> 900.0")
    _check(bool(col.iloc[2] == -150.0), "(150,00) -> -150.0")
    _check(bool(col.iloc[3] == 3999.99), "3.999,99 -> 3999.99")
    _check(len(res.warnings) == 0, "sin warnings: todo el lote era convertible")


# ---------------------------------------------------------------------------
# TABULAR ACTIONS (Fase 8.6/9.1): dedup por columna, dividir, unir, reemplazar
# ---------------------------------------------------------------------------

def test_dedup_por_columna():
    from models import CleaningAction as CA
    df = pd.DataFrame({"ID": [1, 2, 3, 4], "Email": ["a@x.com", "b@x.com", "a@x.com", "c@x.com"], "Monto": [10, 20, 30, 40]})
    # Criterio: solo Email (mantener la PRIMERA aparición)
    act = CA("eliminar_duplicados_por_columna", "Email", "", approved=True,
             parameters={"subset_columns": ["Email"], "keep": "first"})
    out, res = clean_dataframe(df, (act,))
    _check(len(out) == 3, "dedup por Email: 4 filas -> 3 (queda la primera de cada clave)")
    _check(list(out["ID"]) == [1, 2, 4], "IDs sobrevivientes exactos [1,2,4] (filas enteras, sin shift)")
    _check(list(out["Email"]) == ["a@x.com", "b@x.com", "c@x.com"], "Emails únicos preservados")
    _check(list(out["Monto"]) == [10, 20, 40], "Montos alineados con su fila original (no desplazados)")
    # keep='last'
    act_last = CA("eliminar_duplicados_por_columna", "Email", "", approved=True,
                  parameters={"subset_columns": ["Email"], "keep": "last"})
    out_last, _ = clean_dataframe(df, (act_last,))
    _check(list(out_last["ID"]) == [2, 3, 4], "keep='last' conserva la última aparición [2,3,4]")
    # Sin parameters: criterio = la columna de la acción
    act_default = CA("eliminar_duplicados_por_columna", "Email", "", approved=True)
    out_def, _ = clean_dataframe(df, (act_default,))
    _check(len(out_def) == 3 and list(out_def["ID"]) == [1, 2, 4], "sin parameters: dedup por la columna de la acción")
    # Errores controlados
    for bad_params, desc in (({"keep": "middle"}, "keep inválido"), ({"subset_columns": ["NoExiste"]}, "columna inexistente")):
        try:
            clean_dataframe(df, (CA("eliminar_duplicados_por_columna", "Email", "", approved=True, parameters=bad_params),))
            _check(False, f"Debería rechazar {desc}")
        except CleanerError:
            _check(True, f"Rechazó {desc} con CleanerError")
    # Clave compuesta (varias columnas): combina filas que por UNA sola columna serían
    # duplicados pero por la clave completa no lo son (semántica del Paso 7).
    df_comp = pd.DataFrame({
        "ID":     [1, 2, 3, 4, 5],
        "Email":  ["a@x.com", "a@x.com", "a@x.com", "l@x.com", "l@x.com"],
        "Ciudad": ["Salta", "Salta", "Lima", "Lima", "Lima"],
    })
    act_comp = CA("eliminar_duplicados_por_columna", "Email", "", approved=True,
                  parameters={"subset_columns": ["Email", "Ciudad"], "keep": "first"})
    out_comp, _ = clean_dataframe(df_comp, (act_comp,))
    _check(list(out_comp["ID"]) == [1, 3, 4],
           "clave compuesta (Email,Ciudad): sobreviven [1,3,4] — no [1,4] de Email solo")
    _check(len(df_comp) == 5, "DataFrame compuesto original no mutado")
    _check(len(df) == 4, "DataFrame original no mutado")


def test_dividir_columna():
    from models import CleaningAction as CA
    df = pd.DataFrame({"Nombre Completo": ["Ana Silva", "Juan Pérez", "Sol"], "Edad": [30, 25, 40]})
    act = CA("dividir_columna", "Nombre Completo", "", approved=True,
             parameters={"delimiter": " ", "new_column_names": ["Nombre", "Apellido"]})
    out, res = clean_dataframe(df, (act,))
    _check("Nombre Completo" not in out.columns, "columna original eliminada tras dividir")
    _check(list(out.columns) == ["Nombre", "Apellido", "Edad"], "nuevas columnas en posición de la original")
    _check(list(out["Nombre"]) == ["Ana", "Juan", "Sol"], "primeras partes correctas")
    _check(list(out["Apellido"].iloc[:2]) == ["Silva", "Pérez"] and pd.isna(out["Apellido"].iloc[2]), "sin segunda parte -> nulo real (Sol)")
    _check(list(out["Edad"]) == [30, 25, 40], "columnas adyacentes intactas (sin shift)")
    _check(len(res.actions_applied) == 1, "acción registrada")
    # Reemplazo in-place del mismo nombre
    act_inplace = CA("dividir_columna", "Nombre Completo", "", approved=True,
                     parameters={"delimiter": " ", "new_column_names": ["Nombre Completo", "Apellido"]})
    out2, _ = clean_dataframe(df, (act_inplace,))
    _check(list(out2.columns) == ["Nombre Completo", "Apellido", "Edad"], "split in-place respeta el nombre original")
    _check(list(out2["Nombre Completo"]) == ["Ana", "Juan", "Sol"], "split in-place: primera parte correcta")
    # Errores controlados
    for bad_params, desc in (({"delimiter": " "}, "sin new_column_names"),
                             ({"new_column_names": ["A"]}, "sin delimiter"),
                             ({"delimiter": " ", "new_column_names": ["Edad"]}, "colisión con columna existente"),
                             ({"delimiter": " ", "new_column_names": ["X", "X"]}, "nombres duplicados")):
        try:
            clean_dataframe(df, (CA("dividir_columna", "Nombre Completo", "", approved=True, parameters=bad_params),))
            _check(False, f"Debería rechazar {desc}")
        except CleanerError:
            _check(True, f"Rechazó {desc} con CleanerError")
    _check(list(df.columns) == ["Nombre Completo", "Edad"], "DataFrame original no mutado")


def test_unir_columnas():
    from models import CleaningAction as CA
    df = pd.DataFrame({"Nombre": ["Ana", "Beto"], "Apellido": ["Silva", pd.NA], "Ciudad": ["Salta", "Lima"]})
    act = CA("unir_columnas", None, "", approved=True,
             parameters={"source_columns": ["Nombre", "Apellido", "Ciudad"], "new_column_name": "Full", "separator": "-"})
    out, _ = clean_dataframe(df, (act,))
    _check("Full" in out.columns, "columna unida creada")
    _check(list(out["Full"]) == ["Ana-Silva-Salta", "Beto--Lima"], "NA no propaga: aporta parte vacía (Beto--Lima)")
    _check(all(c in out.columns for c in ("Nombre", "Apellido", "Ciudad")), "fuentes intactas por defecto (no eliminadas)")
    _check(list(out.columns) == ["Full", "Nombre", "Apellido", "Ciudad"],
           "nueva columna en posición de la PRIMERA fuente (semántica posicional espejo del split)")
    # drop_source_columns=True y unión sobre la primera fuente (nombre preexistente)
    act2 = CA("unir_columnas", None, "", approved=True,
              parameters={"source_columns": ["Nombre", "Apellido"], "new_column_name": "Nombre", "separator": " ", "drop_source_columns": True})
    out2, _ = clean_dataframe(df, (act2,))
    _check(list(out2.columns) == ["Nombre", "Ciudad"], "drop_source_columns elimina las fuentes restantes")
    _check(list(out2["Nombre"]) == ["Ana Silva", "Beto "], "unión in-place sobre nombre existente (NA -> vacío)")
    # Errores controlados
    for bad_params, desc in (({}, "sin source_columns"),
                             ({"source_columns": ["NoExiste"], "new_column_name": "X"}, "fuente inexistente"),
                             ({"source_columns": ["Nombre"], "new_column_name": "Ciudad"}, "colisión con existente"),
                             ({"source_columns": ["Nombre"]}, "sin new_column_name")):
        try:
            clean_dataframe(df, (CA("unir_columnas", None, "", approved=True, parameters=bad_params),))
            _check(False, f"Debería rechazar {desc}")
        except CleanerError:
            _check(True, f"Rechazó {desc} con CleanerError")
    _check(len(df) == 2 and list(df.columns) == ["Nombre", "Apellido", "Ciudad"], "DataFrame original no mutado")


def test_split_y_unir_encadenados():
    """Paso 9: split + merge en la MISMA sesión (interacción multi-acción).

    El merge debe poder consumir columnas creadas por el split inmediatamente
    anterior, y la reconstrucción debe ser exacta (round-trip de estructura).
    """
    from models import CleaningAction as CA
    df = pd.DataFrame({"Nombre Completo": ["Ana Silva", "Juan Perez"], "Edad": [30, 25]})
    actions = (
        CA("dividir_columna", "Nombre Completo", "", approved=True,
           parameters={"delimiter": " ", "new_column_names": ["Nombre", "Apellido"]}),
        CA("unir_columnas", None, "", approved=True,
           parameters={"source_columns": ["Nombre", "Apellido"], "new_column_name": "Nombre Completo",
                       "separator": " ", "drop_source_columns": True}),
    )
    out, res = clean_dataframe(df, (actions[0],))
    out, res = clean_dataframe(out, (actions[1],))
    _check(list(out.columns) == ["Nombre Completo", "Edad"],
           "split->merge in-place: estructura final equivalente a la original")
    _check(list(out["Nombre Completo"]) == ["Ana Silva", "Juan Perez"],
           "round-trip de valores: merge reconstruye exactamente lo dividido")
    _check(list(out["Edad"]) == [30, 25], "columna adyacente intacta a través de las 2 acciones")
    _check(len(res.actions_applied) == 1, "cada acción queda registrada en su CleaningResult")
    _check(list(df.columns) == ["Nombre Completo", "Edad"], "original no mutado por la cadena")


def test_reemplazar_valores():
    from models import CleaningAction as CA
    df = pd.DataFrame({"V": ["N/A", "null", "---", "15", "x5y", "OK"], "W": ["a", "b", "c", "d", "e", "f"]})
    act = CA("reemplazar_valores", "V", "", approved=True,
             parameters={"mappings": [  # orden contractual: gana el PRIMER mapping que coincide
                 {"find": "N/A", "replace": None, "match": "exact"},
                 {"find": "null", "replace": None, "match": "exact"},
                 {"find": "---", "replace": None, "match": "exact"},
                 {"find": "x(\\d)y", "replace": "n=\\1", "match": "regex"},
                 {"find": "5", "replace": "CINCO", "match": "contains"},
             ]})
    out, res = clean_dataframe(df, (act,))
    v = out["V"].reset_index(drop=True)
    _check(pd.isna(v.iloc[0]) and pd.isna(v.iloc[1]) and pd.isna(v.iloc[2]), "N/A, null, --- -> nulo real")
    _check(v.iloc[3] == "1CINCO", "contains: 10 -> 1CINCO")
    _check(v.iloc[4] == "n=5", "regex con grupo: x5y -> n=5")
    _check(v.iloc[5] == "OK", "valores limpios intactos")
    _check(list(out["W"]) == ["a", "b", "c", "d", "e", "f"], "columna adyacente intacta (sin shift)")
    _check(any("convertidos a nulo" in w for w in res.warnings), "warning formal de nulos creados (cero silencio)")
    _check(df["V"].iloc[0] == "N/A", "DataFrame original no mutado")
    # Regex inválida -> error controlado ANTES de tocar datos
    try:
        clean_dataframe(df, (CA("reemplazar_valores", "V", "", approved=True, parameters={"mappings": [{"find": "([", "replace": "x", "match": "regex"}]}),))
        _check(False, "Debería rechazar regex inválida")
    except CleanerError:
        _check(True, "Rechazó regex inválida con CleanerError (datos intactos)")
    # Modo inválido
    try:
        clean_dataframe(df, (CA("reemplazar_valores", "V", "", approved=True, parameters={"mappings": [{"find": "a", "match": "como"}]}),))
        _check(False, "Debería rechazar modo inválido")
    except CleanerError:
        _check(True, "Rechazó modo de coincidencia inválido")


def test_convertir_basura_a_nulo():
    print("\n--- Test: convertir_basura_a_nulo (patrones estándar + extras + ceros) ---")
    from models import CleaningResult
    from validators import validate_cleaning

    df = pd.DataFrame({
        "Estado": ["N/A", "null", "None", "Activo", "-", "n.d.", "NULL", "N/A "],
        "Nota": ["0", "00", "7", "--", "sin dato", "None", "0", "5"],
        "Edad": [25, 30, 40, 41, 42, 43, 44, 45],
    })

    # Caso 1: solo patrones estándar (default)
    a1 = (CleaningAction("convertir_basura_a_nulo", "Estado", "", approved=True, parameters={}),)
    df1, r1 = clean_dataframe(df, a1)
    _check(list(df1["Estado"].isna()) == [True, True, True, False, True, False, True, True],
           "Estándar: N/A, null, None, -, NULL y 'N/A ' (espacio) se vuelven nulos")
    _check(df1["Estado"].iloc[3] == "Activo" and df1["Estado"].iloc[5] == "n.d.",
           "Estándar: valores legítimos intactos ('n.d.' NO es basura por defecto)")
    _check(any("convertir_basura_a_nulo" in w for w in r1.warnings), "Warning formal de nulos creados")
    _check(df["Estado"].notna().all(), "DataFrame original intacto (read-only)")

    # Caso 2: patrones extra (exactos, respetan mayúsculas)
    a2 = (CleaningAction("convertir_basura_a_nulo", "Estado", "", approved=True,
                         parameters={"extra_patterns": ["n.d."]}),)
    df2, _ = clean_dataframe(df, a2)
    _check(pd.isna(df2["Estado"].iloc[5]), "Extra 'n.d.' convertido a nulo con extra_patterns")

    # Caso 3: ceros textuales opt-in
    a3 = (CleaningAction("convertir_basura_a_nulo", "Nota", "", approved=True,
                         parameters={"convert_text_zeros": True, "extra_patterns": ["--"]}),)
    df3, _ = clean_dataframe(df, a3)
    _check(pd.isna(df3["Nota"].iloc[0]) and pd.isna(df3["Nota"].iloc[1]),
           "Ceros textuales '0'/'00' -> nulo solo con convert_text_zeros=True")
    _check(df3["Nota"].iloc[2] == "7", "Número textual legítimo '7' intacto")
    _check(pd.isna(df3["Nota"].iloc[3]), "Extra '--' convertido a nulo")

    # Sin el flag, los ceros permanecen
    a3b = (CleaningAction("convertir_basura_a_nulo", "Nota", "", approved=True, parameters={}),)
    df3b, _ = clean_dataframe(df, a3b)
    _check(df3b["Nota"].iloc[0] == "0", "Sin flag, '0' NO se toca (opt-in estricto)")

    # Caso 4: columna no textual -> warning, sin crash
    a4 = (CleaningAction("convertir_basura_a_nulo", "Edad", "", approved=True, parameters={}),)
    df4, r4 = clean_dataframe(df, a4)
    _check(df4["Edad"].tolist() == [25, 30, 40, 41, 42, 43, 44, 45], "Columna numérica intacta")
    _check(any("no es textual" in w for w in r4.warnings), "Warning explícito en columna no textual")

    # Caso 5: parámetro inválido -> error explícito
    try:
        clean_dataframe(df, (CleaningAction("convertir_basura_a_nulo", "Estado", "", approved=True,
                                           parameters={"extra_patterns": [""]}),))
        _check(False, "Debía rechazar extra_patterns vacío")
    except CleanerError:
        _check(True, "Rechaza extra_patterns inválido con CleanerError")

    # Caso 6: espejo del Validator aprueba la transformación legítima
    val = validate_cleaning(df, df1, a1, CleaningResult(a1, len(df), len(df1),
                                                        df.shape[1], df1.shape[1], r1.warnings))
    _check(val.valid, "Validator espejo aprueba basura->nulo legítima sin falsos positivos")

    # Caso 7: ataque — borrado de celda legítima no aprobado es detectado
    df_attack = df1.copy()
    df_attack.loc[3, "Estado"] = pd.NA  # 'Activo' no es basura: mutación ilegal
    val2 = validate_cleaning(df, df_attack, a1, CleaningResult(a1, len(df), len(df_attack),
                                                               df.shape[1], df_attack.shape[1], r1.warnings))
    _check(not val2.valid, "Ataque: nulo no autorizado sobre valor legítimo -> validación FALLA")


def main() -> int:
    try:
        test_read_only()
        test_filas_vacias()
        test_columnas_vacias()
        test_duplicados_exactos()
        test_trim_espacios_multicolumna()
        test_trim_espacios_optimizado()
        test_convertir_nulo()
        test_convertir_numerico_seguro()
        test_acciones_invalidas()
        test_orden_multiacccion()
        test_normalizar_mayusculas_upper()
        test_normalizar_mayusculas_title()
        test_normalizar_mayusculas_lower()
        test_normalizar_mayusculas_default_upper()
        test_normalizar_mayusculas_string_dtype()
        test_normalizar_fechas_iso()
        test_normalizar_fechas_con_basura()
        test_normalizar_fechas_string_dtype()
        test_normalizar_fechas_valido_y_invalido_mezclado()
        test_stress()
        test_invarianza_estructural_eliminacion_central()
        test_invarianza_estructural_multipass()
        test_normalizar_numerico_auto_guardas_fiverr()
        test_normalizar_numerico_multi_locale_mixto()
        test_dedup_por_columna()
        test_dividir_columna()
        test_unir_columnas()
        test_split_y_unir_encadenados()
        test_reemplazar_valores()
        test_convertir_basura_a_nulo()
    except AssertionError:
        print("\nFALLÓ ALGÚN TEST DEL CLEANER.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())