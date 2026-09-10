"""validators.py

Módulo de validación post-limpieza (Fase 4.2 - Endurecimiento de Contrato).
Actúa como barrera de seguridad determinista (Zero-Trust) para el Exporter.

Reglas:
    - Solo lectura absoluta.
    - Proyección matemática de estados (O(N)).
    - Tolerancia total (Anti-Crash) a pd.NA, np.nan, y None.
    - Validación cruzada estricta de metadata (CleaningResult vs Authorized Actions).
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from models import CleaningAction, CleaningResult, ValidationResult

# Debe coincidir EXACTAMENTE con cleaner._GARBAGE_PATTERNS (espejo Zero-Trust).
_GARBAGE_PATTERNS_MIRROR = frozenset({"n/a", "na", "null", "none", "nan", "-", "--", "sin dato"})


def validate_cleaning(
    original_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    actions: tuple[CleaningAction, ...],
    cleaning_result: CleaningResult,
) -> ValidationResult:
    """Audita de forma vectorizada que cleaned_df sea un subproducto legítimo de original_df."""
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Validación Estricta de Metadata y Trazabilidad (CleaningResult consistency)
    if len(original_df) != cleaning_result.rows_before:
        errors.append("Inconsistencia: 'rows_before' del CleaningResult no coincide con el original.")
    if len(cleaned_df) != cleaning_result.rows_after:
        errors.append("Inconsistencia: 'rows_after' del CleaningResult no coincide con el resultado.")
    if len(original_df.columns) != cleaning_result.columns_before:
        errors.append("Inconsistencia: 'columns_before' del CleaningResult no coincide con el original.")
    if len(cleaned_df.columns) != cleaning_result.columns_after:
        errors.append("Inconsistencia: 'columns_after' del CleaningResult no coincide con el resultado.")

    # 2. Control Anti-Rogue Cleaner (Verificar que las acciones aplicadas fueron realmente aprobadas)
    approved_set = {(a.action_id, a.column) for a in actions if a.approved}
    for applied_act in cleaning_result.actions_applied:
        if (applied_act.action_id, applied_act.column) not in approved_set:
            errors.append(f"Brecha de seguridad: Cleaner reportó haber aplicado una acción no autorizada ({applied_act.action_id} en {applied_act.column}).")

    applied_not_approved = [a.action_id for a in cleaning_result.actions_applied if not a.approved]
    if applied_not_approved:
        errors.append(f"Brecha de seguridad: Cleaner aplicó acciones con approved=False: {applied_not_approved}")

    # 3. Control de Acciones Desconocidas o Manuales
    known_actions = {
        "eliminar_filas_vacias", "eliminar_columnas_vacias", "eliminar_duplicados_exactos",
        "trim_espacios", "convertir_a_nulo", "convertir_a_numerico", "normalizar_mayusculas",
        "normalizar_fechas", "normalizar_numerico", "limpiar_invisibles", "revisar_manualmente",
        "eliminar_duplicados_por_columna", "dividir_columna", "unir_columnas", "reemplazar_valores",
        "convertir_basura_a_nulo",
    }
    
    for a in actions:
        if a.approved and a.action_id not in known_actions:
            errors.append(f"Acción aprobada desconocida o no soportada: '{a.action_id}'")
            return ValidationResult(False, tuple(errors), tuple(warnings))
        if a.action_id == "revisar_manualmente" and not a.approved:
            warnings.append(f"Revisión manual pendiente en '{a.column or 'General'}'.")

    # Si hubo inconsistencias graves en metadata, abortamos antes de validación costosa
    if errors:
        return ValidationResult(False, tuple(errors), tuple(warnings))

    # 4. Proyección Secuencial de Estados (Vectorizado)
    current_df = original_df.copy(deep=True)
    keep_mask = pd.Series(True, index=current_df.index)
    expected_cols = list(current_df.columns)
    
    for action in actions:
        if not action.approved:
            continue
            
        aid = action.action_id
        col = action.column
        
        if aid == "trim_espacios" and col in expected_cols:
            s = current_df[col]
            if pd.api.types.is_string_dtype(s):
                current_df[col] = s.str.strip()
            elif pd.api.types.is_object_dtype(s):
                current_df[col] = s.map(lambda x: x.strip() if isinstance(x, str) else x)

        elif aid == "limpiar_invisibles" and col in expected_cols:
            # Proyección espejo de cleaner._clean_invisible_cell (Zero-Trust)
            s = current_df[col]
            invisible = ("\u00a0", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff")
            if pd.api.types.is_string_dtype(s):
                proj = s.str.replace(r"[\r\n\t]+", " ", regex=True)
                for ch in invisible:
                    proj = proj.str.replace(ch, "", regex=False)
                current_df[col] = proj
            elif pd.api.types.is_object_dtype(s):
                def _clean_inv(x):
                    if not isinstance(x, str):
                        return x
                    t = x.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
                    for ch in invisible:
                        t = t.replace(ch, "")
                    return t
                current_df[col] = s.map(_clean_inv)
                
        elif aid == "convertir_a_nulo" and col in expected_cols:
            s = current_df[col]
            valid_mask = s.notna()
            cond_empty = pd.Series(False, index=s.index)
            
            if pd.api.types.is_string_dtype(s):
                cond_empty[valid_mask] = s[valid_mask].str.strip() == ""
            elif pd.api.types.is_object_dtype(s):
                cond_empty[valid_mask] = s[valid_mask].map(lambda x: isinstance(x, str) and x.strip() == "")
                
            current_df[col] = s.mask(cond_empty, pd.NA)
                
        elif aid == "convertir_a_numerico" and col in expected_cols:
            s = current_df[col]
            num_s = pd.to_numeric(s, errors="coerce")
            loss = num_s.isna() & s.notna()
            
            if loss.any():
                bad_vals = s[loss]
                really_bad = bad_vals.map(lambda x: not (isinstance(x, str) and x.strip() == ""))
                if really_bad.any():
                    errors.append(f"Pérdida destructiva de información numérica en columna '{col}'.")
            current_df[col] = num_s
            
        elif aid == "eliminar_filas_vacias":
            not_empty = ~current_df[expected_cols].isna().all(axis=1)
            keep_mask = keep_mask & not_empty
            
        elif aid == "eliminar_duplicados_exactos":
            is_dup = current_df.loc[keep_mask, expected_cols].duplicated(keep="first")
            dup_indices = is_dup[is_dup].index
            keep_mask.loc[dup_indices] = False
            
        elif aid == "eliminar_columnas_vacias":
            surviving_rows = current_df.loc[keep_mask, expected_cols]
            for c in list(expected_cols):
                if surviving_rows[c].isna().all():
                    expected_cols.remove(c)
                    
        elif aid == "normalizar_mayusculas" and col in expected_cols:
            s = current_df[col]
            fmt = action.parameters.get("format", "upper") if isinstance(action.parameters, dict) else "upper"

            if fmt == "title":
                if pd.api.types.is_string_dtype(s):
                    current_df[col] = s.str.title()
                elif pd.api.types.is_object_dtype(s):
                    current_df[col] = s.map(lambda x: x.title() if isinstance(x, str) else x)
            elif fmt == "lower":
                if pd.api.types.is_string_dtype(s):
                    current_df[col] = s.str.lower()
                elif pd.api.types.is_object_dtype(s):
                    current_df[col] = s.map(lambda x: x.lower() if isinstance(x, str) else x)
            else:
                if pd.api.types.is_string_dtype(s):
                    current_df[col] = s.str.upper()
                elif pd.api.types.is_object_dtype(s):
                    current_df[col] = s.map(lambda x: x.upper() if isinstance(x, str) else x)

        elif aid == "eliminar_duplicados_por_columna":
            if isinstance(action.parameters, dict) and action.parameters.get("subset_columns"):
                subset = list(action.parameters["subset_columns"])
            else:
                subset = [col]
            # Espejo del Cleaner: misma validación de columnas/keep.
            missing = [c for c in subset if c not in expected_cols]
            if missing:
                errors.append(f"eliminar_duplicados_por_columna: columnas de criterio inexistentes: {missing}.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            keep = action.parameters.get("keep", "first") if isinstance(action.parameters, dict) else "first"
            if keep not in ("first", "last"):
                errors.append(f"eliminar_duplicados_por_columna: keep inválido '{keep}'.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            is_dup = current_df.loc[keep_mask, subset].duplicated(keep=keep)
            dup_indices = is_dup[is_dup].index
            keep_mask.loc[dup_indices] = False

        elif aid == "dividir_columna" and col in expected_cols:
            params = action.parameters if isinstance(action.parameters, dict) else {}
            delimiter = params.get("delimiter")
            new_names = params.get("new_column_names")
            # Espejo del Cleaner: mismas validaciones antes de proyectar.
            if not isinstance(delimiter, str) or delimiter == "":
                errors.append("dividir_columna: delimitador inválido en la acción aprobada.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            if (not isinstance(new_names, list) or not new_names
                    or not all(isinstance(n, str) and n for n in new_names)):
                errors.append("dividir_columna: 'new_column_names' inválido en la acción aprobada.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            if len(set(new_names)) != len(new_names):
                errors.append("dividir_columna: 'new_column_names' contiene duplicados.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            if any(n in expected_cols and n != col for n in new_names):
                errors.append(
                    f"dividir_columna: nombre destino ya existe en los datos: "
                    f"{[n for n in new_names if n in expected_cols and n != col]}.")
                return ValidationResult(False, tuple(errors), tuple(warnings))

            s = current_df[col]
            parts = s.astype("string").str.split(delimiter, expand=True, regex=False)
            parts = parts.reindex(columns=range(len(new_names)))
            orig_pos = expected_cols.index(col)
            for j, new_name in enumerate(new_names):
                part = parts[j] if j in parts.columns else pd.Series(pd.NA, index=current_df.index, dtype="string")
                current_df[new_name] = part.str.strip()
            if col not in new_names:
                expected_cols.remove(col)
            # Mismo posicionamiento que el Cleaner: reemplaza a la original.
            rest = [c for c in expected_cols if c not in new_names]
            expected_cols[:] = rest[:orig_pos] + list(new_names) + rest[orig_pos:]

        elif aid == "unir_columnas":
            params = action.parameters if isinstance(action.parameters, dict) else {}
            source_cols = params.get("source_columns")
            new_name = params.get("new_column_name")
            if (not isinstance(source_cols, list) or not source_cols
                    or not all(isinstance(c, str) for c in source_cols)):
                errors.append("unir_columnas: 'source_columns' inválido en la acción aprobada.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            missing = [c for c in source_cols if c not in expected_cols]
            if missing:
                errors.append(f"unir_columnas: columnas fuente inexistentes: {missing}.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            if not isinstance(new_name, str) or not new_name:
                errors.append("unir_columnas: 'new_column_name' inválido.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            if new_name in expected_cols and new_name not in source_cols:
                errors.append(f"unir_columnas: el nombre destino '{new_name}' ya existe en los datos.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            separator = params.get("separator", " ")
            if not isinstance(separator, str):
                errors.append("unir_columnas: 'separator' debe ser un string.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            drop_sources = bool(params.get("drop_source_columns", False))

            def _join_parts(vals: tuple) -> str:
                return separator.join("" if pd.isna(v) else str(v) for v in vals)

            is_new_col = new_name not in expected_cols
            current_df[new_name] = current_df[source_cols].agg(_join_parts, axis=1)
            if is_new_col:
                # Espejo del Cleaner: la nueva columna toma el lugar de la PRIMERA fuente.
                others = [c for c in expected_cols if c != new_name]
                pos = others.index(source_cols[0])
                expected_cols[:] = others[:pos] + [new_name] + others[pos:]
            if drop_sources:
                for c in source_cols:
                    if c != new_name and c in expected_cols:
                        expected_cols.remove(c)

        elif aid == "convertir_basura_a_nulo" and col in expected_cols:
            params = action.parameters if isinstance(action.parameters, dict) else {}
            extra = params.get("extra_patterns")
            if extra is not None and (not isinstance(extra, list) or not all(isinstance(p, str) and p for p in extra)):
                errors.append("convertir_basura_a_nulo: 'extra_patterns' inválido en la acción aprobada.")
                return ValidationResult(False, tuple(errors), tuple(warnings))
            convert_zeros = bool(params.get("convert_text_zeros", False))
            std = {p.casefold() for p in _GARBAGE_PATTERNS_MIRROR}
            extras = {p for p in (extra or [])}
            s = current_df[col]

            if pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s):
                def _proj_is_garbage(x) -> bool:
                    if not isinstance(x, str):
                        return False
                    t = x.strip()
                    if not t:
                        return False
                    if t.casefold() in std or t in extras:
                        return True
                    if convert_zeros and set(t) <= {"0"}:
                        return True
                    return False

                garbage_mask = s.map(_proj_is_garbage)
                current_df[col] = s.mask(garbage_mask, pd.NA)

        elif aid == "reemplazar_valores" and col in expected_cols:
            params = action.parameters if isinstance(action.parameters, dict) else {}
            mappings = params.get("mappings")
            if not isinstance(mappings, list) or not mappings or not all(isinstance(m, dict) for m in mappings):
                errors.append("reemplazar_valores: 'mappings' inválido en la acción aprobada.")
                return ValidationResult(False, tuple(errors), tuple(warnings))

            s = current_df[col]
            if pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s):
                compiled: list[tuple[str, Any, str | None, str]] = []
                for m in mappings:
                    find = m.get("find")
                    if not isinstance(find, str) or find == "":
                        errors.append("reemplazar_valores: mapping con 'find' vacío.")
                        return ValidationResult(False, tuple(errors), tuple(warnings))
                    replace = m.get("replace")
                    if replace is not None and not isinstance(replace, str):
                        errors.append("reemplazar_valores: 'replace' debe ser string o null.")
                        return ValidationResult(False, tuple(errors), tuple(warnings))
                    mode = m.get("match", "exact")
                    if mode not in ("exact", "contains", "regex"):
                        errors.append(f"reemplazar_valores: modo inválido '{mode}'.")
                        return ValidationResult(False, tuple(errors), tuple(warnings))
                    if mode == "regex":
                        try:
                            compiled.append((find, re.compile(find), replace, mode))
                        except re.error as e:
                            errors.append(f"reemplazar_valores: regex inválida '{find}': {e}.")
                            return ValidationResult(False, tuple(errors), tuple(warnings))
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

                current_df[col] = s.map(_replace_val)

        elif aid == "normalizar_fechas" and col in expected_cols:
            s = current_df[col]
            params = action.parameters if isinstance(action.parameters, dict) else {}
            dayfirst = params.get("dayfirst", True)

            def _is_iso_format(s_str: str) -> bool:
                if not isinstance(s_str, str):
                    return False
                if "/" in s_str:
                    return False
                parts = s_str.split("-")
                if len(parts) != 3:
                    return False
                return len(parts[0]) == 4 and parts[0].isdigit()

            str_s = s.astype(str)
            has_slash = str_s.str.contains("/", na=False)
            first_part = str_s.str.extract(r'^([^\-]+)', expand=False)
            mask_iso = (~has_slash) & (first_part.str.len() == 4) & (first_part.str.match(r'^\d{4}$')) & s.notna()

            converted = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=dayfirst)
            if mask_iso.any():
                iso_parsed = pd.to_datetime(s[mask_iso], errors="coerce", format="%Y-%m-%d")
                converted[mask_iso] = iso_parsed
            current_df[col] = converted.dt.strftime("%Y-%m-%d")
            current_df[col] = current_df[col].where(current_df[col].notna(), pd.NA)

        elif aid == "normalizar_numerico" and col in expected_cols:
            s = current_df[col]
            params = action.parameters if isinstance(action.parameters, dict) else {}
            locale = params.get("locale", "auto")
            remove_currency = params.get("remove_currency", True)
            handle_parentheses = params.get("handle_parentheses_negatives", True)
            convert_percentages = params.get("convert_percentages", False)

            def _project_number_val(val) -> float | None:
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return None
                if not isinstance(val, str):
                    return val if isinstance(val, (int, float)) and not (isinstance(val, float) and pd.isna(val)) else None

                str_val = val.strip()
                if not str_val:
                    return None

                is_parentheses_negative = False
                if handle_parentheses and str_val.startswith("(") and str_val.endswith(")"):
                    str_val = str_val[1:-1].strip()
                    is_parentheses_negative = True

                if remove_currency:
                    # Primero los símbolos alfabéticos compuestos (US$, U$S, USD...),
                    # luego los sueltos: el orden evita dejar restos tipo "US".
                    for sym in ["USD", "EUR", "GBP", "U$S", "US$"]:
                        str_val = str_val.replace(sym, "")
                    for sym in ["$", "€", "£"]:
                        str_val = str_val.replace(sym, "")
                    str_val = str_val.strip()

                if " " in str_val:
                    str_val = str_val.replace(" ", "")

                is_percent = False
                if convert_percentages and str_val.endswith("%"):
                    str_val = str_val[:-1].strip()
                    is_percent = True

                if not str_val:
                    return None

                # Guardas anti-corrupción (espejo EXACTO de cleaner._clean_number_val):
                # solo en locale auto, dígitos puros con ceros a la izquierda o
                # >= 13 dígitos NO se convierten (IDs/códigos postales).
                if locale == "auto" and "." not in str_val and "," not in str_val:
                    digits = str_val.lstrip("+-")
                    if digits.isascii() and digits.isdigit():
                        if (digits.startswith("0") and len(digits) > 1) or len(digits) >= 13:
                            return None

                if locale == "auto" and "." in str_val and "," in str_val:
                    # Mixto (ej. 1.250,50 ó 1,250.50): el ÚLTIMO separador es el decimal.
                    if str_val.rfind(",") > str_val.rfind("."):
                        str_val = str_val.replace(".", "").replace(",", ".")
                    else:
                        str_val = str_val.replace(",", "")
                elif locale == "eu" or (locale == "auto" and "," in str_val and "." not in str_val):
                    if "," in str_val:
                        parts = str_val.rsplit(",", 1)
                        if len(parts) == 2 and parts[1].isdigit():
                            if locale == "auto" and "." not in str_val and len(parts[1]) == 3:
                                # Espejo del Cleaner: auto + solo comas, último grupo de
                                # exactamente 3 dígitos = miles US (1,250 -> 1250).
                                str_val = str_val.replace(",", "")
                            else:
                                integer_part = parts[0].replace(".", "")
                                decimal_part = parts[1]
                                str_val = f"{integer_part}.{decimal_part}"
                        else:
                            str_val = str_val.replace(",", ".")

                if locale == "us" or (locale == "auto" and "." in str_val and "," not in str_val):
                    if "," in str_val:
                        str_val = str_val.replace(",", "")

                try:
                    result = float(str_val)
                    if is_parentheses_negative:
                        result = -result
                    if is_percent:
                        result = result / 100.0
                    return result
                except ValueError:
                    return None

            projected = s.map(_project_number_val)
            current_df[col] = projected.where(projected.notna(), pd.NA)

    # 5. Verificación de Integridad Estructural (Nuevas, faltantes, renombre, reorden)
    clean_cols = list(cleaned_df.columns)
    if clean_cols != expected_cols:
        new_cols = [c for c in clean_cols if c not in expected_cols]
        missing_cols = [c for c in expected_cols if c not in clean_cols]
        errors.append(f"Estructura corrupta. Nuevas: {new_cols}. Faltantes ilegales: {missing_cols}.")
        return ValidationResult(False, tuple(errors), tuple(warnings))
        
    # 6. Alineamiento Vectorizado y Verificación de Celdas
    expected_df = current_df.loc[keep_mask, expected_cols].reset_index(drop=True)
    eval_cleaned = cleaned_df[expected_cols].reset_index(drop=True)
    
    if len(expected_df) != len(eval_cleaned):
        errors.append(f"Discrepancia en filas. Esperadas legítimamente: {len(expected_df)}, Reales resultantes: {len(eval_cleaned)}.")
    else:
        for col in expected_cols:
            s_exp = expected_df[col]
            s_cln = eval_cleaned[col]
            
            # Aislamiento seguro contra Lógica de Kleene (pd.NA crash)
            both_valid = s_exp.notna() & s_cln.notna()
            eq_mask = pd.Series(False, index=s_exp.index)
            
            if both_valid.any():
                eq_mask[both_valid] = s_exp[both_valid] == s_cln[both_valid]
                
            na_mask = s_exp.isna() & s_cln.isna()
            is_valid = eq_mask | na_mask
            
            if not is_valid.all():
                errors.append(f"Mutación no autorizada detectada en la columna '{col}'.")
                
    valid = len(errors) == 0
    return ValidationResult(valid=valid, errors=tuple(errors), warnings=tuple(warnings))