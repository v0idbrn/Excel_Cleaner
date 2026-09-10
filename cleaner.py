"""cleaner.py

Motor determinístico de limpieza de datos para Excel Cleaner.

Reglas estandarizadas de este módulo:
    - NUNCA modifica el DataFrame original (trabaja sobre una copia profunda).
    - NUNCA escribe en disco (ni lee).
    - NUNCA interactúa con la IA ni deduce qué limpiar.
    - Ejecuta ESTRICTAMENTE las acciones con `approved=True` en el orden recibido.
    - Lanza `CleanerError` si se intenta una acción desconocida o peligrosa.
"""

from __future__ import annotations

import re

import pandas as pd

from models import CleaningAction, CleaningResult


class CleanerError(Exception):
    """Excepción controlada para operaciones de limpieza inválidas o abortadas por seguridad."""


# Caracteres invisibles/contaminantes estándar (NBSP, zero-width, BOM, word-joiner).
_INVISIBLE_CHARS = ("\u00a0", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff")

# Patrones estándar de "basura textual" para convertir_basura_a_nulo.
# Comparación insensible a mayúsculas sobre x.strip().
# OJO: validators._GARBAGE_PATTERNS_MIRROR debe coincidir EXACTAMENTE con esta tupla.
_GARBAGE_PATTERNS = ("n/a", "na", "null", "none", "nan", "-", "--", "sin dato")


def _clean_invisible_cell(x):
    """Limpia una celda individual: saltos/tabs internos -> espacio; elimina invisibles.
    Los valores no-string (NA, números, fechas) pasan intactos."""
    if not isinstance(x, str):
        return x
    s = x.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    for ch in _INVISIBLE_CHARS:
        s = s.replace(ch, "")
    return s


def _require_column(action: CleaningAction, df: pd.DataFrame) -> str:
    """Verifica que la acción contenga una columna válida y existente."""
    if not action.column:
        raise CleanerError(f"La acción '{action.action_id}' requiere una columna, pero no se especificó.")
    if action.column not in df.columns:
        raise CleanerError(f"La columna '{action.column}' requerida por '{action.action_id}' no existe en los datos.")
    return action.column


def clean_dataframe(
    df: pd.DataFrame, 
    actions: tuple[CleaningAction, ...]
) -> tuple[pd.DataFrame, CleaningResult]:
    """Aplica secuencialmente las acciones de limpieza aprobadas.
    
    Retorna:
        Una tupla con el (Nuevo DataFrame Limpio, Registro de Resultados).
    """
    # 1. Copia profunda INNEGOCIABLE para garantizar read-only absoluto en el original
    df_clean = df.copy(deep=True)
    
    applied_actions: list[CleaningAction] = []
    warnings: list[str] = []
    
    rows_before = len(df_clean)
    cols_before = len(df_clean.columns)

    # 2. Ejecutar acciones secuencialmente
    for action in actions:
        if not action.approved:
            continue

        aid = action.action_id

        # SEGURIDAD: Bloquea parámetros no soportados para evitar inyecciones lógicas.
        # Solo se advierte para acciones que realmente NO consumen parámetros:
        # normalizar_mayusculas/fechas/numerico SÍ leen action.parameters por diseño.
        _ACTIONS_WITHOUT_PARAMS = {
            "eliminar_filas_vacias", "eliminar_columnas_vacias", "eliminar_duplicados_exactos",
            "trim_espacios", "convertir_a_nulo", "convertir_a_numerico",
            "limpiar_invisibles", "revisar_manualmente",
        }  # (convertir_basura_a_nulo y las 4 acciones de manipulación tabular SÍ consumen parameters por diseño)
        if hasattr(action, "parameters") and action.parameters and aid in _ACTIONS_WITHOUT_PARAMS:
            warnings.append(f"Se ignoraron los parámetros proporcionados para '{aid}' (no soportado).")

        if aid == "eliminar_filas_vacias":
            df_clean = df_clean.dropna(how="all").reset_index(drop=True)
            applied_actions.append(action)

        elif aid == "eliminar_columnas_vacias":
            df_clean = df_clean.dropna(axis=1, how="all")
            applied_actions.append(action)

        elif aid == "eliminar_duplicados_exactos":
            df_clean = df_clean.drop_duplicates(keep="first").reset_index(drop=True)
            applied_actions.append(action)

        elif aid == "trim_espacios":
            col = _require_column(action, df_clean)
            col_data = df_clean[col]
            
            # Optimización pandas 3.x (columna pura de strings es vectorizable directamente)
            if pd.api.types.is_string_dtype(col_data):
                df_clean[col] = col_data.str.strip()
            # Fallback seguro sin usar apply(type) ni astype(str) que rompería los pd.NA
            elif pd.api.types.is_object_dtype(col_data):
                df_clean[col] = col_data.map(lambda x: x.strip() if isinstance(x, str) else x)
                
            applied_actions.append(action)

        elif aid == "convertir_a_nulo":
            col = _require_column(action, df_clean)
            col_data = df_clean[col]
            
            if pd.api.types.is_string_dtype(col_data):
                is_empty = col_data.str.strip() == ""
                df_clean[col] = col_data.mask(is_empty, pd.NA)
            elif pd.api.types.is_object_dtype(col_data):
                is_empty_str = col_data.map(lambda x: isinstance(x, str) and x.strip() == "")
                df_clean[col] = col_data.mask(is_empty_str, pd.NA)
                
            applied_actions.append(action)

        elif aid == "convertir_basura_a_nulo":
            col = _require_column(action, df_clean)
            params = action.parameters if isinstance(action.parameters, dict) else {}
            extra = params.get("extra_patterns")
            if extra is not None and (not isinstance(extra, list) or not all(isinstance(p, str) and p for p in extra)):
                raise CleanerError(
                    "convertir_basura_a_nulo: 'extra_patterns' debe ser una lista de strings no vacíos.")
            convert_zeros = bool(params.get("convert_text_zeros", False))

            # Patrones estándar de basura (comparación sobre x.strip(), exacta e insensible a mayúsculas)
            # + extras definidos por el usuario (comparación exacta, respetando mayúsculas).
            std = {p.casefold() for p in _GARBAGE_PATTERNS}
            extras = {p for p in (extra or [])}

            col_data = df_clean[col]

            def _is_garbage(x) -> bool:
                if not isinstance(x, str):
                    return False
                t = x.strip()
                if not t:
                    return False  # vacíos reales los maneja convertir_a_nulo, no esta acción
                if t.casefold() in std or t in extras:
                    return True
                if convert_zeros and set(t) <= {"0"}:
                    return True  # "0", "00", "000"... en columna textual
                return False

            if pd.api.types.is_string_dtype(col_data) or pd.api.types.is_object_dtype(col_data):
                garbage_mask = col_data.map(_is_garbage)
                df_clean[col] = col_data.mask(garbage_mask, pd.NA)
                nulls_created = int(garbage_mask.sum())
                if nulls_created > 0:
                    warnings.append(
                        f"convertir_basura_a_nulo: {nulls_created} valor(es) de basura en columna '{col}' "
                        "fueron convertidos a nulo (patrones aprobados)."
                    )
            else:
                warnings.append(f"convertir_basura_a_nulo: columna '{col}' no es textual; acción sin efecto.")
            applied_actions.append(action)

        elif aid == "convertir_a_numerico":
            col = _require_column(action, df_clean)
            col_data = df_clean[col]
            
            # Intento de conversión conservadora
            converted = pd.to_numeric(col_data, errors="coerce")
            
            # Solo analizamos valores que se perdieron durante la conversión
            became_nan_mask = converted.isna() & col_data.notna()
            
            if became_nan_mask.any():
                original_bad = col_data[became_nan_mask]
                
                # Permite descartar strings vacíos y espacios (se convierten lícitamente a NaN numérico)
                def _is_destructive(val) -> bool:
                    if isinstance(val, str):
                        return val.strip() != ""
                    return True # Cualquier otro tipo no vacío que se rompa, se considera pérdida
                
                really_bad_mask = original_bad.map(_is_destructive)
                
                if really_bad_mask.any():
                    sample = original_bad[really_bad_mask].iloc[0]
                    raise CleanerError(
                        f"Conversión a numérico abortada en la columna '{col}'. "
                        f"Existen valores incompatibles (ej: '{sample}') que se perderían."
                    )
                    
            df_clean[col] = converted
            applied_actions.append(action)

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

        elif aid == "normalizar_fechas":
            col = _require_column(action, df_clean)
            col_data = df_clean[col]

            # Determinar prioridad de día vs mes para fechas ambiguas (con barra)
            # dayfirst=True: 12/05/2026 -> 12 de mayo (LatAm/Europa)
            # dayfirst=False: 12/05/2026 -> 5 de diciembre (USA)
            params = action.parameters if isinstance(action.parameters, dict) else {}
            dayfirst = params.get("dayfirst", True)

            # Estrategia: fechas con barra son ambiguas, fechas ISO (guiones) son explícitas
            # - Fechas con '/': usar dayfirst según parámetro
            # - Fechas con '-': parsear como ISO YYYY-MM-DD explícitamente (no ambiguas)
            # - Otros formatos: usar mixed con dayfirst
            mask_slash = col_data.astype(str).str.contains("/", na=False)
            mask_dash = col_data.astype(str).str.contains("-", na=False) & ~mask_slash
            mask_other = ~mask_slash & ~mask_dash & col_data.notna()

            # Convertir todo con dayfirst según parámetro (para fechas con '/')
            converted = pd.to_datetime(col_data, errors="coerce", format="mixed", dayfirst=dayfirst)

            # Corregir fechas ISO (YYYY-MM-DD) para que no sean malinterpretadas como DD-MM-YYYY
            # Criterio: formato ISO tiene 4 dígitos de año al INICIO (YYYY-MM-DD)
            # Fechas como 09-05-2026 (DD-MM-YYYY) tienen 4 dígitos al FINAL, no son ISO
            def _is_iso_format(s: str) -> bool:
                """Detecta si un string es ISO YYYY-MM-DD (año al inicio, 4 dígitos)."""
                if not isinstance(s, str):
                    return False
                if "/" in s:
                    return False
                parts = s.split("-")
                if len(parts) != 3:
                    return False
                # ISO: primer parte es año (4 dígitos), el resto son mes y día
                return len(parts[0]) == 4 and parts[0].isdigit()

            def _is_iso_mask(col_data) -> pd.Series:
                """Vectorizado: detecta fechas ISO en la columna."""
                str_col = col_data.astype(str)
                # Primero: descartar los que tienen '/' (ambiguos)
                has_slash = str_col.str.contains("/", na=False)
                # Para los que no tienen '/', verificar si son ISO (año al inicio, 4 dígitos)
                # Extraer primer segmento antes del primer '-'
                first_part = str_col.str.extract(r'^([^\-]+)', expand=False)
                is_iso = (~has_slash) & (first_part.str.len() == 4) & (first_part.str.match(r'^\d{4}$'))
                # Excluir NaN/NA originales
                is_iso = is_iso & col_data.notna()
                return is_iso

            mask_iso = _is_iso_mask(col_data)
            mask_other = (~mask_iso) & col_data.notna() & (~(col_data.astype(str).str.contains("/", na=False)))

            # Convertir todo con dayfirst según parámetro (para fechas ambiguas)
            converted = pd.to_datetime(col_data, errors="coerce", format="mixed", dayfirst=dayfirst)

            # Corregir fechas ISO (YYYY-MM-DD) para que se parseen correctamente
            if mask_iso.any():
                iso_values = col_data[mask_iso]
                iso_parsed = pd.to_datetime(iso_values, errors="coerce", format="%Y-%m-%d")
                converted[mask_iso] = iso_parsed

            # Contar cuántos valores no se pudieron parsear (se volvieron NaT)
            loss_mask = converted.isna() & col_data.notna()
            loss_count = loss_mask.sum()
            
            if loss_count > 0:
                warnings.append(
                    f"normalizar_fechas: {loss_count} valor(es) en columna '{col}' no se pudieron interpretar como fecha y se convertirán en nulo."
                )

            # Formatear a ISO 8601 string (YYYY-MM-DD)
            df_clean[col] = converted.dt.strftime("%Y-%m-%d")
            # Los NaT se convierten en NaN, luego en pd.NA al asignar a columna de strings
            df_clean[col] = df_clean[col].where(df_clean[col].notna(), pd.NA)
            
            applied_actions.append(action)

        elif aid == "normalizar_numerico":
            col = _require_column(action, df_clean)
            col_data = df_clean[col]

            params = action.parameters if isinstance(action.parameters, dict) else {}
            locale = params.get("locale", "auto")
            remove_currency = params.get("remove_currency", True)
            handle_parentheses = params.get("handle_parentheses_negatives", True)
            convert_percentages = params.get("convert_percentages", False)

            def _clean_number_val(val) -> float | None:
                """Limpia un valor individual según las reglas locale-aware."""
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return None
                if not isinstance(val, str):
                    return val if isinstance(val, (int, float)) and not (isinstance(val, float) and pd.isna(val)) else None

                s = val.strip()
                if not s:
                    return None

                is_parentheses_negative = False
                if handle_parentheses and s.startswith("(") and s.endswith(")"):
                    s = s[1:-1].strip()
                    is_parentheses_negative = True

                if remove_currency:
                    # Primero los símbolos alfabéticos compuestos (US$, U$S, USD...),
                    # luego los sueltos: el orden evita dejar restos tipo "US".
                    for sym in ["USD", "EUR", "GBP", "U$S", "US$"]:
                        s = s.replace(sym, "")
                    for sym in ["$", "€", "£"]:
                        s = s.replace(sym, "")
                    s = s.strip()

                # Quitar espacios de miles (ej. "1 250,50")
                if " " in s:
                    s = s.replace(" ", "")

                is_percent = False
                if convert_percentages and s.endswith("%"):
                    s = s[:-1].strip()
                    is_percent = True

                if not s:
                    return None

                # Guardas anti-corrupción (auditoría Fiverr) — solo en locale auto:
                #  - Ceros a la izquierda ('08011'): códigos postales/IDs no son el número 8011.
                #  - Enteros largos (>= 13 dígitos, sin separadores): un ID de 17 dígitos
                #    se reescribe a 1.23e+16 en float64 (corrupción irrecuperable).
                # En ambos casos: NO convertir (queda nulo + warning visible de la pérdida).
                # Con locale us/eu explícitos el usuario decidió: no se aplican guardas.
                if locale == "auto" and "." not in s and "," not in s:
                    digits = s.lstrip("+-")
                    if digits.isascii() and digits.isdigit():
                        if (digits.startswith("0") and len(digits) > 1) or len(digits) >= 13:
                            return None

                # Determinar separador decimal según locale
                if locale == "auto" and "." in s and "," in s:
                    # Mixto (ej. 1.250,50 ó 1,250.50): el ÚLTIMO separador es el decimal.
                    if s.rfind(",") > s.rfind("."):
                        # Decimal es coma (EU): eliminar puntos de miles, coma -> punto.
                        s = s.replace(".", "").replace(",", ".")
                    else:
                        # Decimal es punto (US): eliminar comas de miles.
                        s = s.replace(",", "")
                elif locale == "eu" or (locale == "auto" and "," in s and "." not in s):
                    # Formato EU: 1.250,50 (punto miles, coma decimal)
                    # Si hay ambos separadores, el último es el decimal (coma)
                    if "," in s:
                        parts = s.rsplit(",", 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            if locale == "auto" and "." not in s and len(parts[1]) == 3:
                                # Auto + solo comas: último grupo de exactamente 3 dígitos
                                # = miles US (1,250 -> 1250 / 1,250,000 -> 1250000).
                                # Un decimal EU con exactamente 3 decimales es mucho menos
                                # frecuente que un monto US de miles sin centavos.
                                s = s.replace(",", "")
                            else:
                                # 1.250,50 -> 1250.50 (eliminar puntos, cambiar coma a punto)
                                integer_part = parts[0].replace(".", "")
                                decimal_part = parts[1]
                                s = f"{integer_part}.{decimal_part}"
                        else:
                            # 1250,50 -> 1250.50 (solo cambiar coma a punto)
                            s = s.replace(",", ".")

                if locale == "us" or (locale == "auto" and "." in s and "," not in s):
                    # Formato US: 1,250.50 (coma miles, punto decimal)
                    if "," in s:
                        s = s.replace(",", "")

                try:
                    result = float(s)
                    if is_parentheses_negative:
                        result = -result
                    if is_percent:
                        result = result / 100.0
                    return result
                except ValueError:
                    return None

            cleaned = col_data.map(_clean_number_val)
            loss_mask = cleaned.isna() & col_data.notna()
            loss_count = loss_mask.sum()

            if loss_count > 0:
                warnings.append(
                    f"normalizar_numerico: {loss_count} valor(es) en columna '{col}' no se pudieron interpretar como número y se convertirán en nulo."
                )

            df_clean[col] = cleaned.where(cleaned.notna(), pd.NA)
            applied_actions.append(action)

        elif aid == "eliminar_duplicados_por_columna":
            col = _require_column(action, df_clean)
            if isinstance(action.parameters, dict) and action.parameters.get("subset_columns"):
                subset = list(action.parameters["subset_columns"])
            else:
                subset = [col]
            missing = [c for c in subset if c not in df_clean.columns]
            if missing:
                raise CleanerError(
                    f"eliminar_duplicados_por_columna: columnas de criterio inexistentes: {missing}"
                )
            keep = action.parameters.get("keep", "first") if isinstance(action.parameters, dict) else "first"
            if keep not in ("first", "last"):
                raise CleanerError(
                    f"eliminar_duplicados_por_columna: keep inválido '{keep}' (solo 'first' o 'last')."
                )
            df_clean = df_clean.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)
            applied_actions.append(action)

        elif aid == "dividir_columna":
            col = _require_column(action, df_clean)
            params = action.parameters if isinstance(action.parameters, dict) else {}
            delimiter = params.get("delimiter")
            if not isinstance(delimiter, str) or delimiter == "":
                raise CleanerError("dividir_columna: se requiere un delimitador no vacío en parameters.")
            new_names = params.get("new_column_names")
            if not isinstance(new_names, list) or not new_names or not all(isinstance(n, str) and n for n in new_names):
                raise CleanerError(
                    "dividir_columna: se requiere 'new_column_names': lista de nombres no vacíos."
                )
            if len(set(new_names)) != len(new_names):
                raise CleanerError("dividir_columna: 'new_column_names' contiene duplicados.")
            if any(n in df_clean.columns and n != col for n in new_names):
                raise CleanerError(
                    f"dividir_columna: nombre destino ya existe en los datos: "
                    f"{[n for n in new_names if n in df_clean.columns and n != col]}"
                )

            # regex=False: el delimitador SIEMPRE es literal (ej. "." o "|" no se interpretan como regex).
            parts = df_clean[col].astype("string").str.split(delimiter, expand=True, regex=False)
            # Reindexar a la cantidad exacta de columnas pedidas: faltantes quedan <NA>.
            parts = parts.reindex(columns=range(len(new_names)))
            orig_pos = df_clean.columns.get_loc(col)
            for j, new_name in enumerate(new_names):
                part = parts[j] if j in parts.columns else pd.Series(pd.NA, index=df_clean.index, dtype="string")
                df_clean[new_name] = part.str.strip()
            if col not in new_names:
                df_clean = df_clean.drop(columns=[col])
            # Semántica posicional (estilo Excel): las nuevas columnas ocupan el lugar de la original.
            rest = [c for c in df_clean.columns if c not in new_names]
            df_clean = df_clean[rest[:orig_pos] + list(new_names) + rest[orig_pos:]]
            applied_actions.append(action)

        elif aid == "unir_columnas":
            params = action.parameters if isinstance(action.parameters, dict) else {}
            source_cols = params.get("source_columns")
            if not isinstance(source_cols, list) or not source_cols or not all(isinstance(c, str) for c in source_cols):
                raise CleanerError("unir_columnas: se requiere 'source_columns': lista de columnas.")
            missing = [c for c in source_cols if c not in df_clean.columns]
            if missing:
                raise CleanerError(f"unir_columnas: columnas fuente inexistentes: {missing}")
            new_name = params.get("new_column_name")
            if not isinstance(new_name, str) or not new_name:
                raise CleanerError("unir_columnas: se requiere 'new_column_name' no vacío.")
            if new_name in df_clean.columns and new_name not in source_cols:
                raise CleanerError(f"unir_columnas: el nombre destino '{new_name}' ya existe en los datos.")
            separator = params.get("separator", " ")
            if not isinstance(separator, str):
                raise CleanerError("unir_columnas: 'separator' debe ser un string.")
            drop_sources = bool(params.get("drop_source_columns", False))

            # Los nulos NO se propagan: cada celda nula aporta su parte vacía ("A", NA, "C" -> "A  C").
            def _join_parts(vals: tuple) -> str:
                return separator.join("" if pd.isna(v) else str(v) for v in vals)

            is_new_col = new_name not in df_clean.columns
            df_clean[new_name] = df_clean[source_cols].agg(_join_parts, axis=1)
            if is_new_col:
                # Semántica posicional (espejo del split): la nueva columna ocupa el
                # lugar de la PRIMERA fuente, no el final del DataFrame. Así un
                # round-trip dividir->unir reconstruye la estructura original exacta.
                others = [c for c in df_clean.columns if c != new_name]
                pos = others.index(source_cols[0])
                df_clean = df_clean[others[:pos] + [new_name] + others[pos:]]
            if drop_sources:
                # Nunca soltar new_name: si la unión fue in-place sobre una fuente, ya fue reescrita.
                df_clean = df_clean.drop(columns=[c for c in source_cols if c != new_name])
            applied_actions.append(action)

        elif aid == "reemplazar_valores":
            col = _require_column(action, df_clean)
            params = action.parameters if isinstance(action.parameters, dict) else {}
            mappings = params.get("mappings")
            if not isinstance(mappings, list) or not mappings or not all(isinstance(m, dict) for m in mappings):
                raise CleanerError(
                    "reemplazar_valores: se requiere 'mappings': lista de "
                    "{'find': str, 'replace': str|None, 'match': 'exact'|'contains'|'regex'}.")

            col_data = df_clean[col]
            is_str_col = pd.api.types.is_string_dtype(col_data)
            if not is_str_col and not pd.api.types.is_object_dtype(col_data):
                warnings.append(f"reemplazar_valores: columna '{col}' no es textual; acción sin efecto.")
                applied_actions.append(action)
            else:
                # Regex precompiladas una vez (performance: nada de compilar por celda).
                compiled: list[tuple[str, Any, str | None, str]] = []
                for m in mappings:
                    find = m.get("find")
                    if not isinstance(find, str) or find == "":
                        raise CleanerError("reemplazar_valores: cada mapping requiere 'find' no vacío.")
                    replace = m.get("replace")
                    if replace is not None and not isinstance(replace, str):
                        raise CleanerError("reemplazar_valores: 'replace' debe ser string o null (nulo real).")
                    mode = m.get("match", "exact")
                    if mode not in ("exact", "contains", "regex"):
                        raise CleanerError(f"reemplazar_valores: modo de coincidencia inválido '{mode}'.")
                    if mode == "regex":
                        try:
                            compiled.append((find, re.compile(find), replace, mode))
                        except re.error as e:
                            raise CleanerError(f"reemplazar_valores: regex inválida '{find}': {e}") from e
                    else:
                        compiled.append((find, find, replace, mode))

                def _replace_val(x):
                    if not isinstance(x, str):
                        return x
                    for find, pat, replace, mode in compiled:
                        if mode == "exact" and x.strip() == find:
                            return pd.NA if replace is None else replace
                        if mode == "contains" and find in x:
                            return pd.NA if replace is None else x.replace(find, replace)
                        if mode == "regex":
                            if pat.search(x):
                                return pd.NA if replace is None else pat.sub(replace, x)
                    return x

                df_clean[col] = col_data.map(_replace_val)
                nulls_created = int(df_clean[col].isna().sum() - col_data.isna().sum())
                if nulls_created > 0:
                    warnings.append(
                        f"reemplazar_valores: {nulls_created} valor(es) en columna '{col}' fueron convertidos a nulo por los reemplazos aprobados."
                    )
                applied_actions.append(action)

        elif aid == "limpiar_invisibles":
            col = _require_column(action, df_clean)
            col_data = df_clean[col]

            if pd.api.types.is_string_dtype(col_data):
                s = col_data.str.replace(r"[\r\n\t]+", " ", regex=True)
                for ch in _INVISIBLE_CHARS:
                    s = s.str.replace(ch, "", regex=False)
                df_clean[col] = s
            elif pd.api.types.is_object_dtype(col_data):
                df_clean[col] = col_data.map(_clean_invisible_cell)

            applied_actions.append(action)

        elif aid == "revisar_manualmente":
            warnings.append(f"Se omitió acción manual sobre la columna '{action.column or 'N/A'}'")

        else:
            raise CleanerError(f"El Cleaner recibió una acción desconocida o no implementada: '{aid}'")

    # 3. Empaquetar resultado
    result = CleaningResult(
        actions_applied=tuple(applied_actions),
        rows_before=rows_before,
        rows_after=len(df_clean),
        columns_before=cols_before,
        columns_after=len(df_clean.columns),
        warnings=tuple(warnings)
    )

    return df_clean, result


# ---------------------------------------------------------------------------
# MOTOR MULTI-PASS (Fase 9.0)
# ---------------------------------------------------------------------------

def _auto_actions_from_analysis(df: pd.DataFrame) -> dict[str, tuple[CleaningAction, ...]]:
    """Deriva las acciones seguras por pasada a partir de la forma de cada columna.

    Solo acciones conservadoras y revertibles por el Validator:
      - Pass 1 (estructural): trim + invisibles + mayúsculas/minúsculas si hay inconsistencia real.
      - Pass 2 (tipológica): fechas / numérico locale-aware solo en columnas claramente tipadas.
      - Pass 3 (consolidación): nulos seguros + duplicados sobre datos ya limpios.
    Nada de convertir_a_numerico destructivo: ese sigue siendo una decisión del usuario.
    """
    p1: list[CleaningAction] = []
    p2: list[CleaningAction] = []
    p3: list[CleaningAction] = []

    for col in df.columns:
        s = df[col]
        is_text = pd.api.types.is_string_dtype(s) or (
            pd.api.types.is_object_dtype(s)
            and s.map(lambda x: isinstance(x, str)).mean() > 0.5 if len(s) else False
        )

        if is_text:
            strs = s.dropna().astype(str)
            if not strs.empty:
                has_ws = (strs != strs.str.strip()).any()
                has_invis = strs.str.contains(r"[\r\n\t]|\u00a0|\u200b|\ufeff", regex=True, na=False).any()
                if has_ws:
                    p1.append(CleaningAction("trim_espacios", col, "[Pass1] Espacios externos", approved=True, source="batch-auto"))
                if has_invis:
                    p1.append(CleaningAction("limpiar_invisibles", col, "[Pass1] Invisibles/saltos internos", approved=True, source="batch-auto"))

                non_empty = strs[strs.str.strip() != ""]
                if len(non_empty) >= 2:
                    lowered = non_empty.str.strip().str.lower()
                    mixed_case = (lowered.nunique() > 1) and (non_empty.str.strip().nunique() > lowered.nunique())
                    if mixed_case:
                        p1.append(CleaningAction("normalizar_mayusculas", col, "[Pass1] Casing inconsistente", approved=True, parameters={"format": "title"}, source="batch-auto"))

                # Pass 2: fecha solo si la mayoría de valores parsean como fecha
                if not non_empty.empty:
                    parsed = pd.to_datetime(non_empty, errors="coerce", format="mixed", dayfirst=True)
                    if parsed.notna().mean() >= 0.8 and parsed.notna().any():
                        p2.append(CleaningAction("normalizar_fechas", col, "[Pass2] Columna de fechas", approved=True, parameters={"dayfirst": True}, source="batch-auto"))
                        continue
                    # Pass 2: numérico monetario si la mayoría limpia a número.
                    # (incluye negativos contables y porcentajes: se ignoran en la sonda
                    #  para no penalizar columnas legítimamente tipadas)
                    # Evidencia requerida (auditoría Fiverr): símbolos/separadores/contables.
                    # Se EXCLUYEN patrones de identificador (ceros a la izquierda o
                    # >= 13 dígitos sin separadores) y mezclas ambiguas de '%'.
                    probe = non_empty.str.replace(r"USD|EUR|GBP|U\$S|US\$|[$€£\s]", "", regex=True)
                    probe = probe.str.replace(r"^\((.+)\)$", r"\1", regex=True)
                    probe = probe.str.rstrip("%")
                    digits_only = probe.str.fullmatch(r"\+?\d+").fillna(False)
                    id_like = digits_only & (
                        (probe.str.startswith("0") & (probe.str.len() > 1)).fillna(False)
                        | (probe.str.replace(r"\D", "", regex=True).str.len() >= 13).fillna(False)
                    )
                    probe_num = probe.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
                    probe_num = probe_num.where(~id_like, other=None)
                    as_num = pd.to_numeric(probe_num, errors="coerce")
                    pct_ratio = float(non_empty.str.endswith("%").mean())
                    if (
                        as_num.notna().mean() >= 0.8
                        and (non_empty.str.contains(r"[$€£]|,|\.|\(|%", regex=True)).any()
                        and not (0 < pct_ratio < 0.8)
                    ):
                        p2.append(CleaningAction(
                            "normalizar_numerico", col, "[Pass2] Numérico monetario",
                            approved=True,
                            parameters={"locale": "auto", "convert_percentages": pct_ratio >= 0.8},
                            source="batch-auto",
                        ))

        # Pass 3 siempre: basura remanente textual -> nulo seguro
        if is_text:
            p3.append(CleaningAction("convertir_a_nulo", col, "[Pass3] Vacíos a nulo", approved=True, source="batch-auto"))

    # Pass 3 global: duplicados AL FINAL (sobre datos ya limpios) + filas vacías primero
    p3.insert(0, CleaningAction("eliminar_filas_vacias", None, "[Pass3] Filas totalmente vacías", approved=True, source="batch-auto"))
    p3.append(CleaningAction("eliminar_duplicados_exactos", None, "[Pass3] Duplicados sobre datos limpios", approved=True, source="batch-auto"))

    return {"pass1": tuple(p1), "pass2": tuple(p2), "pass3": tuple(p3)}


def run_multipass_cleaning(
    df: pd.DataFrame,
    passes: dict[str, tuple[CleaningAction, ...]] | None = None,
) -> tuple[pd.DataFrame, CleaningResult, list[CleaningResult]]:
    """Pipeline de 3 pasadas obligatorias (Fase 9.0).

    Pass 1: Limpieza estructural (trim, invisibles, casing).
    Pass 2: Normalización tipológica (fechas, numérico locale-aware).
    Pass 3: Consolidación final (nulos seguros, duplicados sobre datos ya limpios).

    Cada pasada se ejecuta vía clean_dataframe (mismo contrato determinístico) y produce
    su propio CleaningResult, para enriquecer la trazabilidad del reporte de auditoría.

    Args:
        df: DataFrame original (nunca se muta).
        passes: dict opcional con claves "pass1"/"pass2"/"pass3". Si es None, se
            derivan acciones conservadoras automáticamente (_auto_actions_from_analysis).

    Returns:
        (df_limpio, CleaningResult agregado de todo el pipeline, [CleaningResult por pasada])

    Raises:
        CleanerError: si las claves del dict de pasadas son inválidas.
    """
    VALID_KEYS = {"pass1", "pass2", "pass3"}
    if passes is None:
        passes = _auto_actions_from_analysis(df)
    if not isinstance(passes, dict) or not set(passes.keys()).issubset(VALID_KEYS) or not passes:
        raise CleanerError(
            f"run_multipass_cleaning: 'passes' debe ser un dict con claves {sorted(VALID_KEYS)} (recibido: {sorted(passes) if isinstance(passes, dict) else type(passes).__name__})"
        )

    per_pass_results: list[CleaningResult] = []
    current = df
    total_warnings: list[str] = []
    all_applied: list[CleaningAction] = []
    rows_before_all = len(df)
    cols_before_all = len(df.columns)

    for pass_name in ("pass1", "pass2", "pass3"):
        actions = passes.get(pass_name, ())
        if not actions:
            continue
        current, res = clean_dataframe(current, tuple(actions))
        per_pass_results.append(res)
        all_applied.extend(res.actions_applied)
        for w in res.warnings:
            total_warnings.append(f"[{pass_name}] {w}")

    aggregate = CleaningResult(
        actions_applied=tuple(all_applied),
        rows_before=rows_before_all,
        rows_after=len(current),
        columns_before=cols_before_all,
        columns_after=len(current.columns),
        warnings=tuple(total_warnings),
    )
    return current, aggregate, per_pass_results