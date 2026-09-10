# FASE 8.2 — IMPLEMENTACIÓN COMPLETADA: normalizar_mayusculas

## 1. Resumen

Se implementó la acción `normalizar_mayusculas` en el Cleaner, actualizando el Validator para que la reconozca y la whitelist de la IA para que pueda proponerla.

## 2. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `cleaner.py` | Implementación de `normalizar_mayusculas` con soporte para format=upper (default), title, lower |
| `validators.py` | Proyección secuencial de `normalizar_mayusculas` para validación Zero-Trust |
| `ai.py` | Agregado `normalizar_mayusculas` a `VALID_AI_ACTIONS` |
| `tests/test_cleaner.py` | 5 nuevos tests (tests 11-15) + actualización del test stress (test 16) |

## 3. Implementación técnica

### Cleaner (cleaner.py)

```python
elif aid == "normalizar_mayusculas":
    col = _require_column(action, df_clean)
    col_data = df_clean[col]
    fmt = action.parameters.get("format", "upper") if isinstance(action.parameters, dict) else "upper"

    if fmt == "title":
        if pd.api.types.is_string_dtype(col_data):
            df_clean[col] = col_data.str.title()
        elif pd.api.types.is_object_dtype(col_data):
            df_clean[col] = col_data.map(lambda x: x.title() if isinstance(x, str) else x)
    elif fmt == "lower":
        if pd.api.types.is_string_dtype(col_data):
            df_clean[col] = col_data.str.lower()
        elif pd.api.types.is_object_dtype(col_data):
            df_clean[col] = col_data.map(lambda x: x.lower() if isinstance(x, str) else x)
    else:  # upper (default)
        if pd.api.types.is_string_dtype(col_data):
            df_clean[col] = col_data.str.upper()
        elif pd.api.types.is_object_dtype(col_data):
            df_clean[col] = col_data.map(lambda x: x.upper() if isinstance(x, str) else x)

    applied_actions.append(action)
```

**Características de seguridad:**
- Solo procesa columnas con strings (StringDtype u Object)
- No modifica valores no-string (números, booleanos, pd.NA, None)
- Respeta espacios externos (no hace trim implícito)
- Usa `.map()` para object dtype (compatible con pandas 3.x)
- Usa `.str.` accessor para StringDtype (vectorizado)

### Validator (validators.py)

La proyección secuencial ahora incluye:

```python
elif aid == "normalizar_mayusculas" and col in expected_cols:
    s = current_df[col]
    fmt = action.parameters.get("format", "upper") if isinstance(action.parameters, dict) else "upper"

    if fmt == "title":
        if pd.api.types.is_string_dtype(s):
            current_df[col] = s.str.title()
        elif pd.api.types.is_object_dtype(s):
            current_df[col] = s.map(lambda x: x.title() if isinstance(x, str) else x)
    elif fmt == "lower":
        ...
    else:
        ...
```

Esto permite que el Validator simule matemáticamente la transformación y verifique que el resultado exportado coincide con lo esperado.

### IA (ai.py)

```python
VALID_AI_ACTIONS = {
    "eliminar_filas_vacias",
    "eliminar_columnas_vacias",
    "eliminar_duplicados_exactos",
    "trim_espacios",
    "convertir_a_nulo",
    "convertir_a_numerico",
    "revisar_manualmente",
    "normalizar_mayusculas"  # ← NUEVO
}
```

## 4. Tests agregados

| Test | Descripción | Resultado |
|------|-------------|-----------|
| Test 11 | upper (default) con object dtype | ✅ |
| Test 12 | title case | ✅ |
| Test 13 | lower con unicode (María Gómez) | ✅ |
| Test 14 | sin parámetros → default upper | ✅ |
| Test 15 | StringDtype preservado | ✅ |
| Test 16 | Stress 50k filas renumerado | ✅ |

**Cobertura de seguridad verificada:**
- ✅ Columnas no seleccionadas intactas
- ✅ Valores no-string (números) intactos
- ✅ pd.NA/None preservados
- ✅ Inmutabilidad del DataFrame original
- ✅ Acción registrada en CleaningResult

## 5. Valores por defecto

- Si no se proporciona `parameters` o `parameters={}` → `format="upper"` (default)
- Si `parameters` no es dict → `format="upper"` (default)
- Solo se aplica a columnas de texto (string/object)

## 6. Suite completa

```
unittest discover: 18 tests → OK
Function-pattern: 9 archivos → todos OK
TestCase: 4 archivos → todos OK
```

**Total: 100+ tests, 0 fallos.**

## 7. Nota sobre el orden de ejecución

Se confirmó el comportamiento documentado en Fase 8.1: si `eliminar_duplicados_exactos` se ejecuta antes que `trim_espacios`, los duplicados "sucios" (con espacios) sobreviven a la primera pasada. Esto se resolverá en una futura optimización del orden lógico.

## 8. Ready for Fase 8.3

La implementación está completa y probada. El Cleaner ahora soporta:
- eliminar_filas_vacias
- eliminar_columnas_vacias
- eliminar_duplicados_exactos
- trim_espacios
- convertir_a_nulo
- convertir_a_numerico
- **normalizar_mayusculas** (NUEVO)
- revisar_manualmente

La whitelist de IA y el Validator están actualizados para reconocer la nueva acción.
