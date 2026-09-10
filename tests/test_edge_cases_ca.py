# -*- coding: utf-8 -*-
"""Tests multicanulinea/Aprobacion/Deterministico (Checkpoints intermedios)."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from cleaner import clean_dataframe, CleanerError
from models import CleaningAction, CleaningResult
from validators import validate_cleaning

def _check(condition, description):
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)

def _make_clean(actions, df):
    df_clean, result = clean_dataframe(df, tuple(actions))
    validation = validate_cleaning(df, df_clean, actions, result)
    return df_clean, result, validation

# Caso base multicanulinea
BASE = pd.DataFrame({
    "Name": ["  Alice  ", "  Bob  "],
    "Email": [" [alice@example.com](mailto:alice@example.com) ", " [bob@example.com](mailto:bob@example.com) "],
    "City": ["  Salta  ", "  Rosario  "],
})

def test_A():
    print("\n--- Caso A: solo Name ---")
    df = BASE.copy()
    actions = [CleaningAction("trim_espacios", "Name", "trim name", approved=True)]
    df_clean, result, v = _make_clean(actions, df)
    _check(df_clean["Name"].iloc[0] == "Alice", "Name trim")
    _check(df_clean["Email"].iloc[0] == " [alice@example.com](mailto:alice@example.com) ", "Email intacto")
    _check(df_clean["City"].iloc[0] == "  Salta  ", "City intacto")
    _check(v.valid, "validador OK")
    _check(df["Name"].iloc[0] == "  Alice  ", "original Name intacto")
    _check(df["Email"].iloc[0] == " [alice@example.com](mailto:alice@example.com) ", "original Email intacto")
    _check(df["City"].iloc[0] == "  Salta  ", "original City intacto")

def test_B():
    print("\n--- Caso B: solo Email ---")
    df = BASE.copy()
    actions = [CleaningAction("trim_espacios", "Email", "trim email", approved=True)]
    df_clean, result, v = _make_clean(actions, df)
    _check(df_clean["Email"].iloc[0] == "[alice@example.com](mailto:alice@example.com)", "Email trim")
    _check(df_clean["Name"].iloc[0] == "  Alice  ", "Name intacto")
    _check(df_clean["City"].iloc[0] == "  Salta  ", "City intacto")
    _check(v.valid, "validador OK")

def test_C():
    print("\n--- Caso C: Name + Email ---")
    df = BASE.copy()
    actions = [
        CleaningAction("trim_espacios", "Name", "trim name", approved=True),
        CleaningAction("trim_espacios", "Email", "trim email", approved=True),
    ]
    df_clean, result, v = _make_clean(actions, df)
    _check(df_clean["Name"].iloc[0] == "Alice", "Name trim")
    _check(df_clean["Email"].iloc[0] == "[alice@example.com](mailto:alice@example.com)", "Email trim")
    _check(df_clean["City"].iloc[0] == "  Salta  ", "City intacto")
    _check(v.valid, "validador OK")

def test_D():
    print("\n--- Caso D: ninguna aprobada ---")
    df = BASE.copy()
    actions = [CleaningAction("trim_espacios", "Name", "no approved", approved=False)]
    df_clean, result, v = _make_clean(actions, df)
    _check(df_clean["Name"].iloc[0] == "  Alice  ", "sin cambios")
    _check(result.actions_applied == (), "no se aplicaron acciones")
    _check(v.valid, "validador OK")

def test_cleaner_error_unknown():
    print("\n--- Cleaner: accion desconocida ---")
    df = pd.DataFrame({"A": [1]})
    try:
        clean_dataframe(df, (CleaningAction("borra_todo", None, "", approved=True),))
        raise AssertionError("deberia lanzar")
    except CleanerError as e:
        _check("desconocida" in str(e), "lanza CleanerError")

def test_cleaner_error_column_inexistente():
    print("\n--- Cleaner: columna inexistente ---")
    df = pd.DataFrame({"A": [1]})
    try:
        clean_dataframe(df, (CleaningAction("trim_espacios", "B", "", approved=True),))
        raise AssertionError("deberia lanzar")
    except CleanerError as e:
        _check("no existe" in str(e), "lanza CleanerError columna inexistente")

def test_cleaner_error_columna_requerida():
    print("\n--- Cleaner: columna requerida para trim ---")
    df = pd.DataFrame({"A": [1]})
    try:
        clean_dataframe(df, (CleaningAction("trim_espacios", None, "", approved=True),))
        raise AssertionError("deberia lanzar")
    except CleanerError as e:
        _check("requiere una columna" in str(e), "lanza CleanerError columna requerida")

def test_empty_dataframe():
    print("\n--- Cleaner: DataFrame vacio ---")
    df = pd.DataFrame()
    actions = [CleaningAction("trim_espacios", "A", "", approved=True)]
    try:
        clean_dataframe(df, tuple(actions))
        raise AssertionError("deberia lanzar")
    except CleanerError as e:
        _check("no existe" in str(e), "lanza porque columna no existe")

def test_numeric_preservation():
    print("\n--- Cleaner: preservacion numerica ---")
    df = pd.DataFrame({"N": [1, 2, 3], "Txt": [" a ", "b ", " c"]})
    actions = [CleaningAction("trim_espacios", "Txt", "trim txt", approved=True)]
    df_clean, result, v = _make_clean(actions, df)
    _check(df_clean["N"].tolist() == [1, 2, 3], "numeros intactos")
    _check(pd.api.types.is_integer_dtype(df_clean["N"].dtype) or df_clean["N"].dtype == int, "tipo numerico preservado")
    _check(df_clean["Txt"].iloc[0] == "a", "trim txt")
    _check(v.valid, "validador OK")

def test_boolean_preservation():
    print("\n--- Cleaner: preservacion booleana ---")
    df = pd.DataFrame({"B": [True, False, True]})
    actions = [CleaningAction("trim_espacios", "B", "trim b", approved=True)]
    df_clean, result, v = _make_clean(actions, df)
    from pandas.api.types import is_bool_dtype
    _check(is_bool_dtype(df_clean["B"].dtype) and df_clean["B"].iloc[0] == True, "bool True intacto")
    _check(is_bool_dtype(df_clean["B"].dtype) and df_clean["B"].iloc[1] == False, "bool False intacto")
    _check(v.valid, "validador OK")

def test_na_preservation():
    print("\n--- Cleaner: NA preservado ---")
    import pandas as pd
    df = pd.DataFrame({"A": [pd.NA, " a ", None]}, dtype=object)
    actions = [CleaningAction("trim_espacios", "A", "trim a", approved=True)]
    df_clean, result, v = _make_clean(actions, df)
    _check(pd.isna(df_clean["A"].iloc[0]), "pd.NA intacto (NA->NA)")
    _check(df_clean["A"].iloc[1] == "a", "trim string")
    _check(pd.isna(df_clean["A"].iloc[2]), "None intacto (NA semántico)")
    _check(v.valid, "validador OK")

def test_approved_false_no_exec():
    print("\n--- Cleaner: approved=False no ejecuta ---")
    df = pd.DataFrame({"A": ["  x  "]})
    actions = [CleaningAction("trim_espacios", "A", "no approved", approved=False)]
    df_clean, result, v = _make_clean(actions, df)
    _check(result.actions_applied == (), "no acciones aplicadas")
    _check(df_clean["A"].iloc[0] == "  x  ", "sin cambios")
    _check(v.valid, "validador OK")

def main():
    try:
        test_A()
        test_B()
        test_C()
        test_D()
        test_cleaner_error_unknown()
        test_cleaner_error_column_inexistente()
        test_cleaner_error_columna_requerida()
        test_empty_dataframe()
        test_numeric_preservation()
        test_boolean_preservation()
        test_na_preservation()
        test_approved_false_no_exec()
    except AssertionError:
        print("\nFALLO ALGUN TEST EDGE.")
        return 1
    print("\nTODOS LOS TESTS EDGE PASARON.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
