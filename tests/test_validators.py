"""Pruebas unitarias de auditoría para validators.py (Fase 4.1)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner import clean_dataframe
from models import CleaningAction, CleaningResult
from validators import validate_cleaning


def _check(condition: bool, description: str) -> None:
    status = "[OK]" if condition else "[FAIL]"
    print(f"{status} {description}")
    if not condition:
        raise AssertionError(description)


# --- TESTS NUEVOS OBLIGATORIOS (A - Q) ---

def test_A_trim_then_delete():
    print("\n--- Test A: Acción encadenada trim -> eliminación ---")
    df = pd.DataFrame({"Col": [" Juan ", pd.NA, "Pedro"]})
    actions = (
        CleaningAction("trim_espacios", "Col", "", approved=True),
        CleaningAction("eliminar_filas_vacias", None, "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid, "Fila vacía eliminada tras trim, matching preservado (PASS)")


def test_B_trim_then_null():
    print("\n--- Test B: Acción encadenada trim -> null ---")
    df = pd.DataFrame({"Col": ["   "]})
    actions = (
        CleaningAction("trim_espacios", "Col", "", approved=True),
        CleaningAction("convertir_a_nulo", "Col", "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid, "Espacios vacíos transformados legítimamente a NA (PASS)")


def test_C_null_directo():
    print("\n--- Test C: Null directo ---")
    df = pd.DataFrame({"Col": ["   "]})
    actions = (CleaningAction("convertir_a_nulo", "Col", "", approved=True),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid, "Espacios vacíos convertidos directamente a NA (PASS)")


def test_D_trim_then_numeric():
    print("\n--- Test D: Trim + numérico ---")
    df = pd.DataFrame({"Col": [" 123 "]})
    actions = (
        CleaningAction("trim_espacios", "Col", "", approved=True),
        CleaningAction("convertir_a_numerico", "Col", "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid, "String numérico con espacios convertido a int (PASS)")


def test_E_cambio_arbitrario_en_cadena():
    print("\n--- Test E: Cambio arbitrario en secuencia ---")
    df = pd.DataFrame({"Col": [" Juan "]})
    actions = (
        CleaningAction("trim_espacios", "Col", "", approved=True),
        CleaningAction("convertir_a_nulo", "Col", "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    df_clean.loc[0, "Col"] = pd.NA  # Mutación ilegal manual
    val = validate_cleaning(df, df_clean, actions, res)
    _check(not val.valid, "Detecta pérdida de texto válido no amparado por to_null (FAIL)")


def test_F_eliminacion_post_modificacion():
    print("\n--- Test F: Matching resistente (Bug #1 arreglado) ---")
    df = pd.DataFrame({"Col": [" Juan ", "   ", "Pedro"]})
    actions = (
        CleaningAction("trim_espacios", "Col", "", approved=True),
        CleaningAction("convertir_a_nulo", "Col", "", approved=True),
        CleaningAction("eliminar_filas_vacias", None, "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid, "Match determinista superado a pesar de la reestructuración completa (PASS)")


def test_G_duplicados_post_transformacion():
    print("\n--- Test G: Duplicados exactos tras trim ---")
    df = pd.DataFrame({"Col": [" Juan ", "Juan"]})
    actions = (
        CleaningAction("trim_espacios", "Col", "", approved=True),
        CleaningAction("eliminar_duplicados_exactos", None, "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid and len(df_clean) == 1, "Respeta que el trim generó un duplicado legítimo y fue eliminado (PASS)")


def test_H_duplicados_inversos():
    print("\n--- Test H: Duplicados en orden inverso (Seguridad de Estado) ---")
    df = pd.DataFrame({"Col": [" Juan ", "Juan"]})
    actions = (
        CleaningAction("eliminar_duplicados_exactos", None, "", approved=True),
        CleaningAction("trim_espacios", "Col", "", approved=True)
    )
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, res)
    _check(val.valid and len(df_clean) == 2, "Respeta la cronología: no elimina porque originalmente no eran duplicados (PASS)")


def test_I_numeric_loss_attack():
    print("\n--- Test I: Numeric loss attack ---")
    df = pd.DataFrame({"Col": ["10", "ABC"]})
    actions = (CleaningAction("convertir_a_numerico", "Col", "", approved=True),)
    # Bypass al cleaner intencionalmente para forzar el Validator
    df_clean = pd.DataFrame({"Col": [10.0, pd.NA]})
    res = CleaningResult((), 2, 2, 1, 1, ())
    val = validate_cleaning(df, df_clean, actions, res)
    _check(not val.valid, "Detecta conversión silenciosa de ABC a NaN (FAIL)")


def test_J_unauthorized_mutation():
    print("\n--- Test J: Unauthorized mutation attack ---")
    df = pd.DataFrame({"Col": ["Juan"]})
    df_clean = pd.DataFrame({"Col": ["Pedro"]})
    res = CleaningResult((), 1, 1, 1, 1, ())
    val = validate_cleaning(df, df_clean, (), res)
    _check(not val.valid, "Detecta modificación sin ninguna acción que la ampare (FAIL)")


def test_K_unauthorized_row_deletion():
    print("\n--- Test K: Unauthorized row deletion attack ---")
    df = pd.DataFrame({"Col": ["Juan", "Pedro"]})
    df_clean = pd.DataFrame({"Col": ["Juan"]})
    res = CleaningResult((), 2, 1, 1, 1, ())
    val = validate_cleaning(df, df_clean, (), res)
    _check(not val.valid, "Detecta fila con datos desaparecida (FAIL)")


def test_L_unauthorized_column_deletion():
    print("\n--- Test L: Unauthorized column deletion attack ---")
    df = pd.DataFrame({"A": [1], "B": [2]})
    df_clean = pd.DataFrame({"A": [1]})
    actions = (CleaningAction("eliminar_columnas_vacias", None, "", approved=True),)
    res = CleaningResult((), 1, 1, 2, 1, ())
    val = validate_cleaning(df, df_clean, actions, res)
    _check(not val.valid, "Detecta columna con datos eliminada ilegalmente (FAIL)")


def test_M_N_column_structure_attacks():
    print("\n--- Test M y N: Column structure attacks ---")
    df = pd.DataFrame({"A": [1], "B": [2]})
    df_clean_new = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    val1 = validate_cleaning(df, df_clean_new, (), CleaningResult((), 1,1,2,3,()))
    _check(not val1.valid, "Detecta inyección de columnas nuevas (FAIL)")
    
    df_clean_reorder = pd.DataFrame({"B": [2], "A": [1]})
    val2 = validate_cleaning(df, df_clean_reorder, (), CleaningResult((), 1,1,2,2,()))
    _check(not val2.valid, "Detecta reordenamiento no justificado (FAIL)")


def test_O_unauthorized_dtype_change():
    print("\n--- Test O: Unauthorized dtype change ---")
    df = pd.DataFrame({"Col": ["10", "20"]})
    df_clean = pd.DataFrame({"Col": [10, 20]})
    # Cambio a int sin tener to_numeric aprobado
    val = validate_cleaning(df, df_clean, (), CleaningResult((), 2,2,1,1,()))
    _check(not val.valid, "Detecta cambio de dtype no autorizado afectando al type-check estricto (FAIL)")


def test_P_approved_false_attack():
    print("\n--- Test P: Approved=False attack ---")
    df = pd.DataFrame({"Col": [" Juan "]})
    actions = (CleaningAction("trim_espacios", "Col", "", approved=False),)
    df_clean = pd.DataFrame({"Col": ["Juan"]})
    val = validate_cleaning(df, df_clean, actions, CleaningResult((), 1,1,1,1,()))
    _check(not val.valid, "Evita ejecutar/autorizar acciones con approved=False (FAIL)")


def test_Q_immutability():
    print("\n--- Test Q: Original DataFrame integrity ---")
    df = pd.DataFrame({"A": [" test "]})
    df_copy = df.copy(deep=True)
    df_clean = df.copy(deep=True)
    validate_cleaning(df, df_clean, (), CleaningResult((), 1,1,1,1,()))
    pd.testing.assert_frame_equal(df, df_copy)
    _check(True, "DataFrame original permanece idéntico (PASS)")


def test_performance():
    print("\n--- Pruebas de Stress Vectorizado (Sin bucles O(N²) Python) ---")
    
    # 10k 
    df_10k = pd.DataFrame({"A": [" Val "]*10000, "B": [""]*10000})
    actions = (
        CleaningAction("trim_espacios", "A", "", approved=True),
        CleaningAction("convertir_a_nulo", "B", "", approved=True)
    )
    df_clean, res = clean_dataframe(df_10k, actions)
    
    t0 = time.perf_counter()
    val = validate_cleaning(df_10k, df_clean, actions, res)
    t1 = time.perf_counter()
    _check(val.valid, f"10k rows validadas en {t1-t0:.4f}s")
    
    # 50k
    df_50k = pd.DataFrame({"A": [" Val "]*50000, "B": [""]*50000})
    df_clean, res = clean_dataframe(df_50k, actions)
    t0 = time.perf_counter()
    validate_cleaning(df_50k, df_clean, actions, res)
    t1 = time.perf_counter()
    print(f"[OK] 50k rows validadas en {t1-t0:.4f}s")
    
    # 200k (Límite superior solicitado)
    df_200k = pd.DataFrame({"A": [" Val "]*200000, "B": [""]*200000})
    df_clean, res = clean_dataframe(df_200k, actions)
    t0 = time.perf_counter()
    validate_cleaning(df_200k, df_clean, actions, res)
    t1 = time.perf_counter()
    print(f"[OK] 200k rows validadas en {t1-t0:.4f}s")


def test_I_1_pd_NA_seguro():
    print("\n--- Test I.1: pd.NA seguro ---")
    df = pd.DataFrame({"Col": [pd.NA, "Juan"]})
    val = validate_cleaning(df, df.copy(), (), CleaningResult((), 2, 2, 1, 1, ()))
    _check(val.valid, "Comparación pd.NA <-> pd.NA funciona (PASS)")

def test_I_2_None_seguro():
    print("\n--- Test I.2: None seguro ---")
    df = pd.DataFrame({"Col": [None, "Juan"]})
    val = validate_cleaning(df, df.copy(), (), CleaningResult((), 2, 2, 1, 1, ()))
    _check(val.valid, "Comparación None <-> None funciona (PASS)")

def test_I_3_NaN_seguro():
    import numpy as np
    print("\n--- Test I.3: NaN seguro ---")
    df = pd.DataFrame({"Col": [np.nan, "Juan"]})
    val = validate_cleaning(df, df.copy(), (), CleaningResult((), 2, 2, 1, 1, ()))
    _check(val.valid, "Comparación NaN <-> NaN funciona (PASS)")

def test_I_4_Texto_a_NA_ilegal():
    print("\n--- Test I.4: Texto -> NA (sin autorización) ---")
    df = pd.DataFrame({"Col": ["Juan"]})
    df_clean = pd.DataFrame({"Col": [pd.NA]})
    val = validate_cleaning(df, df_clean, (), CleaningResult((), 1, 1, 1, 1, ()))
    _check(not val.valid, "Detectado Texto->NA, sin crasheo de types (PASS)")

def test_I_5_NA_a_texto_ilegal():
    print("\n--- Test I.5: NA -> Texto (sin autorización) ---")
    df = pd.DataFrame({"Col": [pd.NA]})
    df_clean = pd.DataFrame({"Col": ["Juan"]})
    val = validate_cleaning(df, df_clean, (), CleaningResult((), 1, 1, 1, 1, ()))
    _check(not val.valid, "Detectado NA->Texto, sin crasheo de types (PASS)")

def test_I_6_numeric_loss_graceful():
    print("\n--- Test I.6: Numeric loss attack (Graceful fail) ---")
    df = pd.DataFrame({"Col": ["10", "ABC"]})
    df_clean = pd.DataFrame({"Col": [10.0, pd.NA]})
    actions = (CleaningAction("convertir_a_numerico", "Col", "", approved=True),)
    val = validate_cleaning(df, df_clean, actions, CleaningResult((), 2, 2, 1, 1, ()))
    _check(not val.valid and any("Pérdida destructiva" in e for e in val.errors), "Rechaza numeric loss gracefully (PASS)")

def test_I_7_numeric_legitimo():
    print("\n--- Test I.7: Numérico legítimo ---")
    df = pd.DataFrame({"Col": ["10", "20", "30"]})
    df_clean = pd.DataFrame({"Col": [10.0, 20.0, 30.0]})
    actions = (CleaningAction("convertir_a_numerico", "Col", "", approved=True),)
    val = validate_cleaning(df, df_clean, actions, CleaningResult((), 3, 3, 1, 1, ()))
    _check(val.valid, "Conversión numérica correcta sin perder información (PASS)")

def test_I_8_StringDtype():
    print("\n--- Test I.8: StringDtype con pd.NA ---")
    df = pd.DataFrame({"Col": pd.Series([" Juan ", pd.NA], dtype="string")})
    df_clean = pd.DataFrame({"Col": pd.Series(["Juan", pd.NA], dtype="string")})
    actions = (CleaningAction("trim_espacios", "Col", "", approved=True),)
    val = validate_cleaning(df, df_clean, actions, CleaningResult((), 2, 2, 1, 1, ()))
    _check(val.valid, "Manipulación legítima de StringDtype puro superada (PASS)")

def test_I_9_Object_mixto():
    print("\n--- Test I.9: Object mixto anti-crash ---")
    df = pd.DataFrame({"Col": ["Juan", 123, True, None, pd.NA]})
    val = validate_cleaning(df, df.copy(), (), CleaningResult((), 5, 5, 1, 1, ()))
    _check(val.valid, "Columnas con mezcla de todos los tipos auditadas con éxito sin crash (PASS)")

# Agregar las llamadas de test_I_1_pd_NA_seguro() a test_I_9_Object_mixto() en el def main()

def test_R1_metadata_correct():
    print("\n--- Test R1: CleaningResult correcto ---")
    df = pd.DataFrame({"A": [1]})
    val = validate_cleaning(df, df.copy(), (), CleaningResult((), 1, 1, 1, 1, ()))
    _check(val.valid, "Pasa la validación de consistencia (PASS)")

def test_R2_metadata_inconsistent():
    print("\n--- Test R2: CleaningResult inconsistente ---")
    df = pd.DataFrame({"A": [1]})
    val = validate_cleaning(df, df.copy(), (), CleaningResult((), 99, 1, 1, 1, ()))
    _check(not val.valid, "Falla controladamente por rows_before falseado (FAIL)")

def test_R3_applied_unapproved():
    print("\n--- Test R3: CleaningResult con acción no aprobada registrada ---")
    df = pd.DataFrame({"A": ["Juan"]})
    act = CleaningAction("trim_espacios", "A", "", approved=False)
    # El cleaner hipotético dice haberla aplicado
    val = validate_cleaning(df, df.copy(), (act,), CleaningResult((act,), 1, 1, 1, 1, ()))
    _check(not val.valid and any("no autorizada" in str(e) for e in val.errors), "Bloquea mutación auto-reportada no aprobada (FAIL)")

def test_R4_column_renamed():
    print("\n--- Test R4: Cambio de nombre de columna ---")
    df = pd.DataFrame({"name": ["Juan"]})
    df_clean = pd.DataFrame({"nombre": ["Juan"]})
    val = validate_cleaning(df, df_clean, (), CleaningResult((), 1, 1, 1, 1, ()))
    _check(not val.valid and any("Estructura corrupta" in str(e) for e in val.errors), "Detecta renombrado ilegal de columna (FAIL)")

def test_R5_arbitrary_dtype():
    print("\n--- Test R5: Dtype arbitrario (No amparado por conversión) ---")
    df = pd.DataFrame({"age": ["10", "20"]})
    df_clean = pd.DataFrame({"age": [10, 20]})
    # Ausencia deliberada de la acción convertir_a_numerico
    val = validate_cleaning(df, df_clean, (), CleaningResult((), 2, 2, 1, 1, ()))
    _check(not val.valid, "Detecta casteo de string a int no autorizado (FAIL)")

def test_S1_espejo_miles_us_auto():
    """Test S.1 (Paso 3 plan Fiverr): espejo numérico sincronizado con el Cleaner.

    Regresión: con la heurística vieja, '1,250' se corrompía a 1.25 y el espejo
    (igual de erróneo) validaba la corrupción. Hoy el Cleaner produce 1250.0 y
    el espejo debe proyectar exactamente lo mismo -> cero falsos positivos.
    """
    print("\n--- Test S.1: Espejo locale=auto — miles US '1,250' ---")
    from cleaner import clean_dataframe
    df = pd.DataFrame({"Col": ["1,250", "12,000", "150"]})
    actions = (CleaningAction("normalizar_numerico", "Col", "", approved=True, parameters={"locale": "auto"}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 3, 3, 1, 1, res.warnings))
    _check(val.valid, "Cero falsos positivos: limpieza de miles US validada")
    _check(float(df_clean["Col"].iloc[0]) == 1250.0 and float(df_clean["Col"].iloc[1]) == 12000.0,
           "El Cleaner corrigió la corrupción ('1,250' -> 1250.0, antes 1.25)")

def test_S2_espejo_guardas_id():
    print("\n--- Test S.2: Espejo — guardas anti-ID (ceros izq / 17 dígitos) ---")
    from cleaner import clean_dataframe
    actions = (CleaningAction("normalizar_numerico", "Col", "", approved=True, parameters={"locale": "auto"}),)
    df = pd.DataFrame({"Col": ["08011", "0123", "4567"]})
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 3, 3, 1, 1, res.warnings))
    _check(val.valid, "Nulos legítimos por guardas de ID: validación verde")
    _check(len(res.warnings) == 1, "Pérdida de IDs reportada con warning (cero silencio)")
    df2 = pd.DataFrame({"Col": ["12345678901234567", "999"]})
    df2_clean, res2 = clean_dataframe(df2, actions)
    val2 = validate_cleaning(df2, df2_clean, actions, CleaningResult(actions, 2, 2, 1, 1, res2.warnings))
    _check(val2.valid, "ID largo (>= 13 dígitos) NO convertido: espejo de acuerdo")
    _check(bool(pd.isna(df2_clean["Col"].iloc[0])), "El ID largo quedó nulo (antes 1.23e+16)")

def test_S3_espejo_mixtos_y_pct():
    print("\n--- Test S.3: Espejo — formatos mixtos reales y porcentajes ---")
    from cleaner import clean_dataframe
    df = pd.DataFrame({"Saldo": ["$1.250,50", "US$ 900,00", "(150,00)", "3.999,99"]})
    actions = (CleaningAction("normalizar_numerico", "Saldo", "", approved=True, parameters={"locale": "auto"}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 4, 4, 1, 1, res.warnings))
    _check(val.valid, "Mixtos US/EU/contables validados sin falsos positivos")
    _check(float(df_clean["Saldo"].iloc[0]) == 1250.5 and float(df_clean["Saldo"].iloc[2]) == -150.0,
           "Valores correctos ($1.250,50 -> 1250.5, (150,00) -> -150.0)")
    df_pct = pd.DataFrame({"Col": ["15%", "20%", "30%", "25%"]})
    acts_pct = (CleaningAction("normalizar_numerico", "Col", "", approved=True,
                               parameters={"locale": "auto", "convert_percentages": True}),)
    dfp_clean, resp = clean_dataframe(df_pct, acts_pct)
    valp = validate_cleaning(df_pct, dfp_clean, acts_pct, CleaningResult(acts_pct, 4, 4, 1, 1, resp.warnings))
    _check(valp.valid and float(dfp_clean["Col"].iloc[0]) == 0.15, "Porcentajes: 15% -> 0.15 validado")

def test_S4_espejo_bypass_explicito():
    print("\n--- Test S.4: Espejo — locale explícito bypasea guardas ---")
    from cleaner import clean_dataframe
    df = pd.DataFrame({"Col": ["08011", "0123"]})
    actions = (CleaningAction("normalizar_numerico", "Col", "", approved=True, parameters={"locale": "eu"}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 2, 2, 1, 1, res.warnings))
    _check(val.valid, "locale=eu explícito: '08011' -> 8011.0 validado (decisión del usuario)")


# ---------------------------------------------------------------------------
# T: Acciones tabulares (Fase 8.6/9.1) — acuerdo Cleaner<->Validator y ataques
# ---------------------------------------------------------------------------

def test_T1_espejo_dedup_por_columna():
    from cleaner import clean_dataframe
    df = pd.DataFrame({"ID": [1, 2, 3, 4], "Email": ["a@x.com", "b@x.com", "a@x.com", "c@x.com"], "Monto": [10, 20, 30, 40]})
    actions = (CleaningAction("eliminar_duplicados_por_columna", "Email", "", approved=True,
                              parameters={"subset_columns": ["Email"], "keep": "first"}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 4, 3, 3, 3, res.warnings))
    _check(val.valid, "dedup por Email: Validator proyecta exactamente las mismas filas (PASS)")
    # Clave compuesta: el espejo debe respetar el criterio multi-columna exacto.
    df_comp = pd.DataFrame({
        "ID":     [1, 2, 3, 4, 5],
        "Email":  ["a@x.com", "a@x.com", "a@x.com", "l@x.com", "l@x.com"],
        "Ciudad": ["Salta", "Salta", "Lima", "Lima", "Lima"],
    })
    actions_comp = (CleaningAction("eliminar_duplicados_por_columna", "Email", "", approved=True,
                                   parameters={"subset_columns": ["Email", "Ciudad"], "keep": "first"}),)
    df_comp_clean, res_comp = clean_dataframe(df_comp, actions_comp)
    val_comp = validate_cleaning(df_comp, df_comp_clean, actions_comp,
                                 CleaningResult(actions_comp, 5, 3, 3, 3, res_comp.warnings))
    _check(val_comp.valid and list(df_comp_clean["ID"]) == [1, 3, 4],
           "clave compuesta (Email,Ciudad): espejo aprueba y respeta el criterio multi-columna (PASS)")
    # Ataque: cleaner deduplicó por Email SOLO (más agresivo) sin acción que lo ampare.
    actions_solo = (CleaningAction("eliminar_duplicados_por_columna", "Email", "", approved=True,
                                   parameters={"subset_columns": ["Email"], "keep": "first"}),)
    df_solo_clean, _ = clean_dataframe(df_comp, actions_solo)
    val_attack = validate_cleaning(df_comp, df_solo_clean, actions_comp,
                                   CleaningResult(actions_comp, 5, len(df_solo_clean), 3, 3, ()))
    _check(not val_attack.valid,
           "ataque: dedup por criterio MÁS agresivo que el aprobado detectada (FAIL)")
    # Ataque: el cleaner eliminó una fila extra sin acción que lo ampare.
    val2 = validate_cleaning(df, df_clean.iloc[:-1].reset_index(drop=True), actions,
                             CleaningResult(actions, 4, 2, 3, 3, res.warnings))
    _check(not val2.valid, "dedup por Email: fila eliminada extra detectada (FAIL)")
    # Ataque: la acción no está aprobada.
    unapproved = (CleaningAction("eliminar_duplicados_por_columna", "Email", "", approved=False,
                                 parameters={"subset_columns": ["Email"]}),)
    val3 = validate_cleaning(df, df_clean, unapproved, CleaningResult(actions, 4, 3, 3, 3, res.warnings))
    _check(not val3.valid, "dedup no aprobada bloqueada (FAIL)")


def test_T2_espejo_dividir_columna():
    from cleaner import clean_dataframe
    df = pd.DataFrame({"Nombre Completo": ["Ana Silva", "Juan Pérez", "Sol"], "Edad": [30, 25, 40]})
    actions = (CleaningAction("dividir_columna", "Nombre Completo", "", approved=True,
                              parameters={"delimiter": " ", "new_column_names": ["Nombre", "Apellido"]}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 3, 3, 2, 3, res.warnings))
    _check(val.valid, "split Nombre/Apellido: Validator proyecta los mismos valores y posiciones (PASS)")
    # Ataque: valores divididos por otro delimitador -> mutación no autorizada.
    tampered = df_clean.copy()
    tampered["Nombre"] = ["An", "Juan", "Sol"]
    val2 = validate_cleaning(df, tampered, actions, CleaningResult(actions, 3, 3, 2, 3, res.warnings))
    _check(not val2.valid, "split: celda alterada tras dividir detectada (FAIL)")
    # Ataque: columna extra inyectada.
    extra = df_clean.copy()
    extra["Fantasma"] = "x"
    val3 = validate_cleaning(df, extra, actions, CleaningResult(actions, 3, 3, 2, 4, res.warnings))
    _check(not val3.valid, "split: columna extra no aprobada detectada (FAIL)")


def test_T3_espejo_unir_columnas():
    from cleaner import clean_dataframe
    df = pd.DataFrame({"Nombre": ["Ana", "Beto"], "Apellido": ["Silva", pd.NA], "Ciudad": ["Salta", "Lima"]})
    actions = (CleaningAction("unir_columnas", None, "", approved=True,
                              parameters={"source_columns": ["Nombre", "Apellido"], "new_column_name": "Full", "separator": "-"}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 2, 2, 3, 4, res.warnings))
    _check(val.valid, "merge con NA: Validator reproduce el mismo join nulo-por-vacío (PASS)")
    # Ataque: separador cambiado en el resultado.
    tampered = df_clean.copy()
    tampered["Full"] = ["Ana Silva", "Beto "]
    val2 = validate_cleaning(df, tampered, actions, CleaningResult(actions, 2, 2, 3, 4, res.warnings))
    _check(not val2.valid, "merge: separador distinto al aprobado detectado (FAIL)")
    # Variante aprobada: drop_source_columns=True también proyecta igual.
    actions_d = (CleaningAction("unir_columnas", None, "", approved=True,
                                parameters={"source_columns": ["Nombre", "Apellido"], "new_column_name": "Full", "separator": "-", "drop_source_columns": True}),)
    df_clean_d, res_d = clean_dataframe(df, actions_d)
    val3 = validate_cleaning(df, df_clean_d, actions_d, CleaningResult(actions_d, 2, 2, 3, 2, res_d.warnings))
    _check(val3.valid, "merge con drop_source_columns: proyección espejo exacta (PASS)")


def test_T5_split_y_unir_encadenados_espejo():
    """Paso 9: cadena dividir_columna -> unir_columnas en UNA sola validación.

    El espejo debe reconstruir el mismo camino de estructura (crear 2 columnas,
    posicionarlas, fusionar y soltar) y aprobar el round-trip sin falsos positivos.
    """
    from cleaner import clean_dataframe
    df = pd.DataFrame({"Nombre Completo": ["Ana Silva", "Juan Perez"], "Edad": [30, 25]})
    a_split = CleaningAction("dividir_columna", "Nombre Completo", "", approved=True,
                             parameters={"delimiter": " ", "new_column_names": ["Nombre", "Apellido"]})
    a_merge = CleaningAction("unir_columnas", None, "", approved=True,
                             parameters={"source_columns": ["Nombre", "Apellido"],
                                         "new_column_name": "Nombre Completo",
                                         "separator": " ", "drop_source_columns": True})
    actions = (a_split, a_merge)
    # El Cleaner se ejecuta en 2 llamadas (2 CleaningResult); el Validator recibe TODO.
    df1, r1 = clean_dataframe(df, (a_split,))
    df_final, r2 = clean_dataframe(df1, (a_merge,))
    combined = CleaningResult(
        actions_applied=r1.actions_applied + r2.actions_applied,
        rows_before=2, rows_after=2, columns_before=2, columns_after=2,
        warnings=r1.warnings + r2.warnings,
    )
    val = validate_cleaning(df, df_final, actions, combined)
    _check(val.valid, "split->merge encadenados: espejo aprueba el round-trip sin falsos positivos (PASS)")

    # Ataque: en el resultado final, la celda reconstruida fue alterada.
    tampered = df_final.copy()
    tampered["Nombre Completo"] = ["Ana Silva", "Juan Perez!"]
    val2 = validate_cleaning(df, tampered, actions, combined)
    _check(not val2.valid, "ataque: celda alterada tras la cadena split->merge detectada (FAIL)")

    # Ataque: la columna adyacente desapareció durante la cadena.
    missing = df_final.drop(columns=["Edad"])
    val3 = validate_cleaning(df, missing, actions, combined)
    _check(not val3.valid, "ataque: columna Edad eliminada sin amparo durante la cadena (FAIL)")


def test_U_espejo_convertir_basura_a_nulo():
    """Paso 10: espejo exacto de convertir_basura_a_nulo.

    Contratos bloqueados:
    - El Validator proyecta la misma conversión basura->nulo (patrones estándar,
      case-insensitive sobre strip(), extras exactos, ceros opt-in).
    - Cero falsos positivos en transformaciones legítimas (solas y encadenadas).
    - Nulos sobre valores legítimos sin amparo de la acción -> detectados.
    """
    from cleaner import clean_dataframe

    # --- U.1: patrón estándar, múltiple y con espacios/casing (default) ---
    df = pd.DataFrame({"Estado": ["N/A", "NULL", " None ", "Activo", "-", "Sin Dato"],
                       "Nota": ["0", "00", "7", "--", "pendiente", "na"]})
    a1 = (CleaningAction("convertir_basura_a_nulo", "Estado", "", approved=True, parameters={}),)
    df1, r1 = clean_dataframe(df, a1)
    val = validate_cleaning(df, df1, a1, CleaningResult(a1, 6, 6, 2, 2, r1.warnings))
    _check(val.valid, "U.1: basura estándar (N/A/NULL/None/-/'Sin Dato') -> espejo aprueba sin falsos positivos (PASS)")

    # Ataque: el Cleaner NO debería poder convertir 'Activo' (legítimo) y si lo hace, se detecta.
    attack = df1.copy()
    attack.loc[3, "Estado"] = pd.NA
    val_a = validate_cleaning(df, attack, a1, CleaningResult(a1, 6, 6, 2, 2, r1.warnings))
    _check(not val_a.valid, "U.1 ataque: nulo sobre valor legítimo sin amparo detectado (FAIL)")

    # --- U.2: extra_patterns (exactos, respetan mayúsculas) + ceros opt-in ---
    a2 = (CleaningAction("convertir_basura_a_nulo", "Nota", "", approved=True,
                         parameters={"extra_patterns": ["--"], "convert_text_zeros": True}),)
    df2, r2 = clean_dataframe(df, a2)
    val2 = validate_cleaning(df, df2, a2, CleaningResult(a2, 6, 6, 2, 2, r2.warnings))
    _check(val2.valid, "U.2: extras ('--') + ceros textuales opt-in -> espejo aprueba (PASS)")

    # Ataque: convertir ceros SIN el flag aprobado -> el espejo no lo ampara.
    a_noz = (CleaningAction("convertir_basura_a_nulo", "Nota", "", approved=True, parameters={}),)
    df2b, _ = clean_dataframe(df, a_noz)
    zeros_killed = df2b.copy()
    zeros_killed.loc[0, "Nota"] = pd.NA  # '0' sin convert_text_zeros -> no autorizado
    val2b = validate_cleaning(df, zeros_killed, a_noz, CleaningResult(a_noz, 6, 6, 2, 2, ()))
    _check(not val2b.valid, "U.2 ataque: cero textual eliminado sin flag aprobado detectado (FAIL)")

    # --- U.3: cadena trim_espacios -> convertir_basura_a_nulo (transformación compuesta) ---
    df3 = pd.DataFrame({"Ciudad": ["N/A ", "Salta", "null", " Cba "]})
    chain = (
        CleaningAction("trim_espacios", "Ciudad", "", approved=True),
        CleaningAction("convertir_basura_a_nulo", "Ciudad", "", approved=True, parameters={}),
    )
    df3a, r3a = clean_dataframe(df3, (chain[0],))
    df3b, r3b = clean_dataframe(df3a, (chain[1],))
    combined = CleaningResult(chain, 4, 4, 1, 1, r3a.warnings + r3b.warnings)
    val3 = validate_cleaning(df3, df3b, chain, combined)
    _check(val3.valid, "U.3: cadena trim -> basura_a_nulo: espejo encadenado aprueba (PASS)")

    # --- U.4: error de contrato -> extra_patterns inválido en la acción aprobada ---
    bad = (CleaningAction("convertir_basura_a_nulo", "Ciudad", "", approved=True,
                          parameters={"extra_patterns": "N/A"}),)
    val4 = validate_cleaning(df3, df3b, bad, CleaningResult(bad, 4, 4, 1, 1, ()))
    _check(not val4.valid, "U.4: extra_patterns no-lista en acción aprobada -> rechazada (FAIL)")


def test_T4_espejo_reemplazar_valores():
    from cleaner import clean_dataframe
    df = pd.DataFrame({"V": ["N/A", "null", "---", "15", "x5y", "OK"], "W": ["a", "b", "c", "d", "e", "f"]})
    actions = (CleaningAction("reemplazar_valores", "V", "", approved=True,
                              parameters={"mappings": [
                                  {"find": "N/A", "replace": None, "match": "exact"},
                                  {"find": "null", "replace": None, "match": "exact"},
                                  {"find": "---", "replace": None, "match": "exact"},
                                  {"find": "x(\\d)y", "replace": "n=\\1", "match": "regex"},
                              ]}),)
    df_clean, res = clean_dataframe(df, actions)
    val = validate_cleaning(df, df_clean, actions, CleaningResult(actions, 6, 6, 2, 2, res.warnings))
    _check(val.valid, "reemplazos exact->NA + regex: Validator aprueba (PASS)")
    # Ataque: el resultado reemplazó algo NO autorizado (W mutada).
    tampered = df_clean.copy()
    tampered["W"] = ["a", "b", "c", "d", "e", "z"]
    val2 = validate_cleaning(df, tampered, actions, CleaningResult(actions, 6, 6, 2, 2, res.warnings))
    _check(not val2.valid, "reemplazo en columna no aprobada detectado (FAIL)")
    # Ataque: mutación de valor no cubierto por ningún mapping.
    tampered2 = df_clean.copy()
    tampered2["V"] = tampered2["V"].astype("object"); tampered2.loc[5, "V"] = "Cambiado"
    val3 = validate_cleaning(df, tampered2, actions, CleaningResult(actions, 6, 6, 2, 2, res.warnings))
    _check(not val3.valid, "valor limpio mutado sin mapping que lo ampare detectado (FAIL)")


def main() -> int:
    try:
        test_A_trim_then_delete()
        test_B_trim_then_null()
        test_C_null_directo()
        test_D_trim_then_numeric()
        test_E_cambio_arbitrario_en_cadena()
        test_F_eliminacion_post_modificacion()
        test_G_duplicados_post_transformacion()
        test_H_duplicados_inversos()
        test_I_numeric_loss_attack()
        test_J_unauthorized_mutation()
        test_K_unauthorized_row_deletion()
        test_L_unauthorized_column_deletion()
        test_M_N_column_structure_attacks()
        test_O_unauthorized_dtype_change()
        test_P_approved_false_attack()
        test_Q_immutability()
        test_performance()
        test_I_1_pd_NA_seguro()
        test_I_2_None_seguro()
        test_I_3_NaN_seguro()
        test_I_4_Texto_a_NA_ilegal()
        test_I_5_NA_a_texto_ilegal()
        test_I_6_numeric_loss_graceful()
        test_I_7_numeric_legitimo()
        test_I_8_StringDtype()
        test_I_9_Object_mixto()
        test_R1_metadata_correct()
        test_R2_metadata_inconsistent()
        test_R3_applied_unapproved()
        test_R4_column_renamed()
        test_R5_arbitrary_dtype()
        test_S1_espejo_miles_us_auto()
        test_S2_espejo_guardas_id()
        test_S3_espejo_mixtos_y_pct()
        test_S4_espejo_bypass_explicito()
        test_T1_espejo_dedup_por_columna()
        test_T2_espejo_dividir_columna()
        test_T3_espejo_unir_columnas()
        test_T4_espejo_reemplazar_valores()
        test_T5_split_y_unir_encadenados_espejo()
        test_U_espejo_convertir_basura_a_nulo()
    except AssertionError:
        print("\nFALLO EN LOS TESTS DE VALIDACIÓN.")
        return 1

    print("\nTODOS LOS TESTS COMPLETADOS SATISFACTORIAMENTE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())