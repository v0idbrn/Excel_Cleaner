"""exporter.py

Módulo de exportación (Fase 5).
Escribe de manera segura el DataFrame final a disco (CSV/XLSX).

Reglas:
    - ZERO-WRITE si ValidationResult.valid NO ES True.
    - No sobrescribe archivos existentes por defecto (overwrite=False).
    - El DataFrame es inmutable (solo-lectura).
    - No aplica ninguna regla de limpieza ni validación semántica.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from models import (
    AuditReport,
    AuditTransform,
    CleaningAction,
    CleaningResult,
    ExportResult,
    ValidationResult,
)


class ExportError(Exception):
    """Excepción controlada para errores en el proceso de exportación."""


# Nombre fijo de la pestaña de auditoría embebida en los XLSX exportados.
AUDIT_SHEET_NAME = "_Reporte_Auditoria"

# Idiomas soportados para los reportes de auditoría (TXT/JSON/pestaña embebida).
SUPPORTED_LANGUAGES = ("es", "en")


def export_dataframe(
    df: pd.DataFrame,
    output_path: str | Path,
    validation_result: ValidationResult,
    overwrite: bool = False,
    audit_report: AuditReport | None = None,
) -> ExportResult:
    """Exporta el DataFrame a CSV o XLSX si, y solo si, la validación fue exitosa."""
    
    # 1. BARRERA DE SEGURIDAD ABSOLUTA (ZERO-WRITE)
    if not validation_result.valid:
        raise ExportError(
            f"Exportación bloqueada: El DataFrame no ha superado la validación. "
            f"Errores: {validation_result.errors}"
        )

    # 2. Validación de la ruta y extensión
    path = Path(output_path).resolve()
    
    if path.is_dir():
        raise ExportError("La ruta de salida especificada es un directorio, debe ser un archivo.")
    
    if path.suffix.lower() not in [".csv", ".xlsx"]:
        raise ExportError(f"Formato no soportado: '{path.suffix}'. Solo se permite .csv y .xlsx")

    if not path.parent.exists():
        raise ExportError(f"El directorio de destino no existe: {path.parent}")

    # 3. Política de sobrescritura
    if path.exists() and not overwrite:
        raise ExportError("El archivo de destino ya existe y overwrite=False.")

    # 4. Escritura Segura
    try:
        if path.suffix.lower() == ".csv":
            # CSV: formato plano por diseño — SIN pestañas adicionales.
            df.to_csv(path, index=False, encoding="utf-8")
        elif path.suffix.lower() == ".xlsx":
            # XLSX: datos + pestaña de auditoría embebida (_Reporte_Auditoria).
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Datos")
                if audit_report is not None:
                    _write_audit_sheet(writer, audit_report)
    except (OSError, ValueError) as e:
        raise ExportError(f"Error a nivel de I/O durante la escritura: {e}") from e

    # 5. Verificación post-escritura
    if not path.exists():
        raise ExportError("Fallo crítico: El archivo no se encontró tras reportar escritura exitosa.")
        
    if path.stat().st_size == 0:
        raise ExportError("Fallo crítico: El archivo exportado está vacío (0 bytes).")

    return ExportResult(
        success=True,
        path=str(path),
        rows_exported=len(df),
        columns_exported=len(df.columns)
    )


def _write_audit_sheet(writer: "pd.ExcelWriter", report: AuditReport) -> None:
    """Escribe la pestaña _Reporte_Auditoria dentro del XLSX exportado.

    Recorre la fila 1 en columnas A/B para la auditoría. Contenido:
      - Resumen: filas originales vs finales, columnas, eliminadas, timestamp, veredicto.
      - Acciones ejecutadas: acción, columna, parámetros, fuente.
      - Columnas modificadas: por columna, cambios de valores y variación de nulos.
    """
    import openpyxl

    ws = writer.book.create_sheet(title=AUDIT_SHEET_NAME)

    # Textos de interfaz localizables ("es" implicito para retrocompatibilidad).
    language: str = report.language if report.language else "es"
    if language == "en":
        section_title = "Audit Report — Excel Cleaner"
        section_resumen = "Summary"
        rows_before_label = "Rows before"
        rows_after_label = "Rows after"
        rows_removed_label = "Rows removed"
        columns_before_label = "Columns before"
        columns_after_label = "Columns after"
        timestamp_label = "Timestamp UTC"
        original_file_label = "Original file"
        export_file_label = "Exported file"
        validation_label = "Zero-Trust validation"
        validation_ok = "VALID" if report.validation_valid else "NOT VALID"
        actions_header = "Actions executed"
        col_modified_header = "Columns modified"
        actions_col_headers = ("Action", "Column", "Parameters", "Source")
        modified_col_headers = ("Column", "Action", "Changes", "Nulls before", "Nulls after")
        none_action = "(none)"
    else:
        section_title = "REPORTE DE AUDITORIA — Excel Cleaner"
        section_resumen = "Resumen"
        rows_before_label = "Filas originales"
        rows_after_label = "Filas finales"
        rows_removed_label = "Filas eliminadas"
        columns_before_label = "Columnas originales"
        columns_after_label = "Columnas finales"
        timestamp_label = "Fecha/Hora UTC"
        original_file_label = "Archivo original"
        export_file_label = "Archivo exportado"
        validation_label = "Validación Zero-Trust"
        validation_ok = "VÁLIDA" if report.validation_valid else "NO VÁLIDA"
        actions_header = "Acciones ejecutadas"
        col_modified_header = "Columnas modificadas"
        actions_col_headers = ("Acción", "Columna", "Parámetros", "Fuente")
        modified_col_headers = ("Columna", "Acción", "Cambios", "Nulos antes", "Nulos después")
        none_action = "(ninguna)"

    def _cell(row: int, col: int, value, bold: bool = False) -> None:
        c = ws.cell(row=row, column=col, value=value)
        if bold:
            c.font = openpyxl.styles.Font(bold=True)

    r = 1
    _cell(r, 1, section_title, bold=True)
    r += 2
    _cell(r, 1, section_resumen, bold=True)
    r += 1
    _cell(r, 1, rows_before_label); _cell(r, 2, report.rows_before); r += 1
    _cell(r, 1, rows_after_label); _cell(r, 2, report.rows_after); r += 1
    _cell(r, 1, rows_removed_label); _cell(r, 2, report.rows_removed); r += 1
    _cell(r, 1, columns_before_label); _cell(r, 2, report.columns_before); r += 1
    _cell(r, 1, columns_after_label); _cell(r, 2, report.columns_after); r += 1
    _cell(r, 1, timestamp_label); _cell(r, 2, report.export_timestamp.isoformat(timespec="seconds")); r += 1
    _cell(r, 1, original_file_label); _cell(r, 2, report.original_file); r += 1
    _cell(r, 1, export_file_label); _cell(r, 2, report.export_file); r += 1
    _cell(r, 1, validation_label); _cell(r, 2, validation_ok); r += 2

    _cell(r, 1, actions_header, bold=True)
    r += 1
    if report.actions_executed:
        _cell(r, 1, actions_col_headers[0], bold=True)
        _cell(r, 2, actions_col_headers[1], bold=True)
        _cell(r, 3, actions_col_headers[2], bold=True)
        _cell(r, 4, actions_col_headers[3], bold=True)
        r += 1
        for a in report.actions_executed:
            _cell(r, 1, a.action_id); _cell(r, 2, a.column or "GLOBAL")
            _cell(r, 3, str(a.parameters) if a.parameters else ""); _cell(r, 4, a.source)
            r += 1
    else:
        _cell(r, 1, none_action); r += 1
    r += 1

    _cell(r, 1, col_modified_header, bold=True)
    r += 1
    modified = [t for t in report.transforms
                if t.column != "GLOBAL" and (t.values_changed > 0 or t.nulls_after != t.nulls_before)]
    if modified:
        _cell(r, 1, modified_col_headers[0], bold=True)
        _cell(r, 2, modified_col_headers[1], bold=True)
        _cell(r, 3, modified_col_headers[2], bold=True)
        _cell(r, 4, modified_col_headers[3], bold=True)
        _cell(r, 5, modified_col_headers[4], bold=True)
        r += 1
        for t in modified:
            _cell(r, 1, t.column); _cell(r, 2, t.action_id)
            _cell(r, 3, t.values_changed); _cell(r, 4, t.nulls_before); _cell(r, 5, t.nulls_after)
            r += 1
    else:
        _cell(r, 1, none_action); r += 1

def generate_audit_report(
    original_file: str | Path,
    export_file: str | Path,
    cleaning_result: CleaningResult,
    validation_result: ValidationResult,
    df_original: pd.DataFrame,
    df_clean: pd.DataFrame,
    transforms: tuple[AuditTransform, ...] | None = None,
    language: str = "es",
) -> AuditReport:
    """Genera un reporte de auditoría formal con la trazabilidad completa de la limpieza.

    Args:
        original_file: Ruta del archivo origen.
        export_file: Ruta del archivo exportado.
        cleaning_result: Resultado de la limpieza (CleaningResult).
        validation_result: Resultado de la validación (ValidationResult).
        df_original: DataFrame original antes de la limpieza.
        df_clean: DataFrame limpio exportado.
        transforms: Detalles de transformación por columna (opcional, generado si no se provee).
        language: Idioma del reporte ("es" predeterminado, "en" para clientes internacionales).

    Returns:
        AuditReport con toda la trazabilidad de la sesión.

    Raises:
        ExportError: Si `language` no es un idioma soportado.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ExportError(
            f"Idioma de reporte no soportado: '{language}'. "
            f"Idiomas disponibles: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    # Calcular transforms por columna si no se proporcionaron
    if transforms is None:
        transforms = _compute_transforms(df_original, df_clean, cleaning_result)

    return AuditReport(
        export_timestamp=datetime.now(timezone.utc),
        original_file=str(original_file),
        export_file=str(export_file),
        rows_before=cleaning_result.rows_before,
        rows_after=cleaning_result.rows_after,
        rows_removed=cleaning_result.rows_before - cleaning_result.rows_after,
        columns_before=cleaning_result.columns_before,
        columns_after=cleaning_result.columns_after,
        validation_valid=validation_result.valid,
        validation_errors=validation_result.errors,
        validation_warnings=validation_result.warnings,
        actions_executed=cleaning_result.actions_applied,
        transforms=transforms,
        cleaning_warnings=cleaning_result.warnings,
        language=language,
    )


def _compute_transforms(
    df_original: pd.DataFrame,
    df_clean: pd.DataFrame,
    cleaning_result: CleaningResult,
) -> tuple[AuditTransform, ...]:
    """Computa los detalles de transformación por columna comparando original vs limpio."""
    transforms: list[AuditTransform] = []

    for action in cleaning_result.actions_applied:
        # --- Acciones estructurales con columnas nuevas: trazabilidad dedicada ---
        if action.action_id == "dividir_columna" and action.column is not None:
            params = action.parameters if isinstance(action.parameters, dict) else {}
            new_names = params.get("new_column_names") or []
            if action.column in df_original.columns:
                nulls_after = int(df_clean[new_names[0]].isna().sum()) if (
                    new_names and new_names[0] in df_clean.columns) else 0
                transforms.append(AuditTransform(
                    action_id=action.action_id,
                    column=str(action.column),
                    parameters=action.parameters,
                    input_dtype=str(df_original[action.column].dtype),
                    output_dtype=(str(df_clean[new_names[0]].dtype) if new_names and new_names[0] in df_clean.columns else "-"),
                    nulls_before=int(df_original[action.column].isna().sum()),
                    nulls_after=nulls_after,
                    values_changed=len(df_original),
                    summary=f"Dividida por {params.get('delimiter', '?')!r} en {list(new_names)}",
                ))
            continue

        if action.action_id == "unir_columnas":
            params = action.parameters if isinstance(action.parameters, dict) else {}
            new_name = params.get("new_column_name") or ""
            srcs = params.get("source_columns") or []
            if new_name in df_clean.columns:
                transforms.append(AuditTransform(
                    action_id=action.action_id,
                    column=str(new_name),
                    parameters=action.parameters,
                    input_dtype="+".join(str(df_original[c].dtype) for c in srcs if c in df_original.columns) or "-",
                    output_dtype=str(df_clean[new_name].dtype),
                    nulls_before=int(df_original[srcs[0]].isna().sum()) if srcs and srcs[0] in df_original.columns else 0,
                    nulls_after=int(df_clean[new_name].isna().sum()),
                    values_changed=len(df_clean),
                    summary=f"Unió {list(srcs)} con separador {params.get('separator', ' ')!r}"
                            + (" (fuentes eliminadas)" if params.get("drop_source_columns") else ""),
                ))
            continue

        if action.action_id == "eliminar_duplicados_por_columna":
            params = action.parameters if isinstance(action.parameters, dict) else {}
            subset = params.get("subset_columns") or ([action.column] if action.column else [])
            transforms.append(AuditTransform(
                action_id=action.action_id,
                column="GLOBAL",
                parameters=action.parameters,
                input_dtype=f"df_{df_original.shape}",
                output_dtype=f"df_{df_clean.shape}",
                nulls_before=int(df_original.isna().sum().sum()),
                nulls_after=int(df_clean.isna().sum().sum()),
                values_changed=df_original.shape[0] - df_clean.shape[0],
                summary=f"Deduplicación por criterio {subset} (keep={params.get('keep', 'first')!r})"
                        if subset else "Deduplicación por columna",
            ))
            continue

        if action.action_id == "convertir_basura_a_nulo" and action.column is not None:
            params = action.parameters if isinstance(action.parameters, dict) else {}
            extra = params.get("extra_patterns") or []
            zeros = " + ceros textuales" if params.get("convert_text_zeros") else ""
            if action.column in df_original.columns and action.column in df_clean.columns:
                transforms.append(AuditTransform(
                    action_id=action.action_id,
                    column=str(action.column),
                    parameters=action.parameters,
                    input_dtype=str(df_original[action.column].dtype),
                    output_dtype=str(df_clean[action.column].dtype),
                    nulls_before=int(df_original[action.column].isna().sum()),
                    nulls_after=int(df_clean[action.column].isna().sum()),
                    values_changed=max(0, int(df_clean[action.column].isna().sum() - df_original[action.column].isna().sum())),
                    summary=f"Basura -> nulo (patrones estándar{zeros}"
                            + (f" + extra {list(extra)}" if extra else "") + ")",
                ))
            continue

        if action.column is None:
            # Acciones globales como eliminar_filas_vacias o eliminar_duplicados_exactos
            input_count = df_original.shape[0]
            output_count = df_clean.shape[0]
            nulls_before = int(df_original.isna().sum().sum())
            nulls_after = int(df_clean.isna().sum().sum())

            transforms.append(AuditTransform(
                action_id=action.action_id,
                column="GLOBAL",
                parameters=action.parameters,
                input_dtype=f"df_{df_original.shape}",
                output_dtype=f"df_{df_clean.shape}",
                nulls_before=nulls_before,
                nulls_after=nulls_after,
                values_changed=input_count - output_count,
                summary=f"Filas: {input_count} -> {output_count} (eliminadas: {input_count - output_count})",
            ))
        else:
            if action.column not in df_original.columns or action.column not in df_clean.columns:
                continue

            col_orig = df_original[action.column]
            col_clean = df_clean[action.column]

            input_dtype = str(col_orig.dtype)
            output_dtype = str(col_clean.dtype)
            nulls_before = int(col_orig.isna().sum())
            nulls_after = int(col_clean.isna().sum())

            # Contar valores que cambiaron (comparación posición por posición)
            values_changed = 0
            min_len = min(len(col_orig), len(col_clean))
            for i in range(min_len):
                v_orig = col_orig.iloc[i]
                v_clean = col_clean.iloc[i]
                # Detectar cambio: mismo valor o ambos NaN
                if pd.isna(v_orig) and pd.isna(v_clean):
                    continue
                if pd.isna(v_orig) or pd.isna(v_clean):
                    values_changed += 1
                elif v_orig != v_clean:
                    values_changed += 1

            summary_parts = []
            if nulls_after > nulls_before:
                summary_parts.append(f"nulos: +{nulls_after - nulls_before}")
            if values_changed > 0:
                summary_parts.append(f"cambios: {values_changed}")
            if nulls_after < nulls_before:
                summary_parts.append(f"nulos: -{nulls_before - nulls_after}")

            summary = "; ".join(summary_parts) if summary_parts else "sin cambios detectables"

            transforms.append(AuditTransform(
                action_id=action.action_id,
                column=action.column,
                parameters=action.parameters,
                input_dtype=input_dtype,
                output_dtype=output_dtype,
                nulls_before=nulls_before,
                nulls_after=nulls_after,
                values_changed=values_changed,
                summary=summary,
            ))

    return tuple(transforms)


def export_audit_report(
    audit_report: AuditReport,
    output_dir: str | Path | None = None,
    format: str = "txt",
) -> str:
    """Exporta el reporte de auditoría a un archivo legible.

    Args:
        audit_report: El reporte de auditoría a exportar.
        output_dir: Directorio de salida (default: mismo que el archivo exportado).
        format: Formato del reporte ("txt" o "json").

    Returns:
        Ruta absoluta del archivo generado.

    Raises:
        ExportError: Si no se puede escribir el reporte.
    """
    export_path = Path(audit_report.export_file).resolve()
    if output_dir is None:
        output_dir = export_path.parent
    else:
        output_dir = Path(output_dir).resolve()

    if not output_dir.exists():
        raise ExportError(f"El directorio de salida no existe: {output_dir}")

    base_name = export_path.stem

    if format.lower() == "txt":
        report_path = output_dir / f"{base_name}_audit_report.txt"
        _write_txt_report(report_path, audit_report)
    elif format.lower() == "json":
        report_path = output_dir / f"{base_name}_audit_report.json"
        _write_json_report(report_path, audit_report)
    else:
        raise ExportError(f"Formato de reporte no soportado: '{format}'. Use 'txt' o 'json'.")

    if not report_path.exists() or report_path.stat().st_size == 0:
        raise ExportError("Fallo critico: El reporte de auditoría no se pudo generar correctamente.")

    return str(report_path)



def _write_txt_report(path: Path, report: AuditReport) -> None:
    """Escribe el reporte en formato texto legible para humanos.

    Soporta "es" (predeterminado) y "en".
    """
    lines: list[str] = []

    language: str = report.language if report.language else "es"

    # Localizacion: "es" (predeterminado) o "en".
    en = language == "en"
    if en:
        header_line = "AUDIT REPORT - EXCEL CLEANER"
        files_section_title = "FILES"
        original_file_label = "Original file: "
        export_file_label = "Exported file: "
        metrics_section_title = "GLOBAL CLEANING METRICS"
        rows_before_label = "Rows before: "
        rows_after_label = "Rows after: "
        rows_removed_label = "Rows removed: "
        columns_before_label = "Columns before: "
        columns_after_label = "Columns after: "
        validation_section_title = "VALIDATION (ZERO-TRUST)"
        validation_state_line_format = (
            "Status: VALID - Export complies with all integrity rules."
            if report.validation_valid else
            "Status: NOT VALID - Export was blocked by the Validator."
        )
        errors_prefix = "  ERROR:"
        warnings_validation_prefix = "  WARNING:"
        actions_section_title = "ACTIONS EXECUTED"
        col_modified_section_title = "COLUMN TRANSFORMATIONS"
        no_transforms_line = "No column transformations recorded."
        warnings_cleaning_section_title = "CLEANING WARNINGS"
        no_cleaning_warnings_line = "No warnings during cleaning."
        footer_line = "END OF AUDIT REPORT"
        actions_no_executed_line = "No cleaning actions were executed."
    else:  # es (habilitar para otro idioma futuro)
        header_line = "  REPORTE DE AUDITORIA - EXCEL CLEANER"
        files_section_title = "  ARCHIVOS"
        original_file_label = "Archivo Original: "
        export_file_label = "Archivo Exportado: "
        metrics_section_title = "  METRICAS GLOBALES DE LIMPIEZA"
        rows_before_label = "Filas antes: "
        rows_after_label = "Filas despues: "
        rows_removed_label = "Filas eliminadas: "
        columns_before_label = "Columnas antes: "
        columns_after_label = "Columnas despues: "
        validation_section_title = "  VALIDACION (ZERO-TRUST)"
        validation_state_line_format = (
            "Estado: VALIDO - La exportacion cumple con todas las reglas de integridad."
            if report.validation_valid else
            "Estado: NO VALIDO - La exportacion fue bloqueada por el Validator."
        )
        errors_prefix = "  ERROR: "
        warnings_validation_prefix = "  WARNING: "
        actions_section_title = "  ACCIONES EJECUTADAS"
        col_modified_section_title = "  TRANSFORMACIONES POR COLUMNA"
        no_transforms_line = "No hay transformaciones registradas."
        warnings_cleaning_section_title = "  ADVERTENCIAS DE LIMPIEZA"
        no_cleaning_warnings_line = "No hubo advertencias durante la limpieza."
        footer_line = "  FIN DEL REPORTE DE AUDITORIA"
        actions_no_executed_line = "No se ejecutaron acciones de limpieza."



    lines.append("=" * 70)
    lines.append(header_line)
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Fecha/Hora UTC: {report.export_timestamp.isoformat()}" if language == "es"
                  else f"Timestamp UTC: {report.export_timestamp.isoformat()}")
    lines.append(f"Version del Cleaner: {report.cleaner_version}" if language == "es"
                  else f"Cleaner version: {report.cleaner_version}")
    lines.append("")
    lines.append("-" * 70)
    lines.append(files_section_title)
    lines.append("-" * 70)
    lines.append(f"{original_file_label}{report.original_file}")
    lines.append(f"{export_file_label}{report.export_file}")
    lines.append("")
    lines.append("-" * 70)
    lines.append(metrics_section_title)
    lines.append("-" * 70)
    lines.append(f"{rows_before_label}{report.rows_before}")
    lines.append(f"{rows_after_label}{report.rows_after}")
    lines.append(f"{rows_removed_label}{report.rows_removed}")
    lines.append(f"{columns_before_label}{report.columns_before}")
    lines.append(f"{columns_after_label}{report.columns_after}")
    lines.append("")
    lines.append("-" * 70)
    lines.append(validation_section_title)
    lines.append("-" * 70)
    lines.append(validation_state_line_format)
    if report.validation_errors:
        for err in report.validation_errors:
            lines.append(f"  ERROR: {err}")

    if report.validation_warnings:
        for warn in report.validation_warnings:
            lines.append(f"  WARNING: {warn}")

    lines.append("")
    lines.append("-" * 70)
    lines.append(actions_section_title)
    lines.append("-" * 70)
    if report.actions_executed:
        for i, action in enumerate(report.actions_executed, 1):
            col_info = action.column if action.column else ("GLOBAL" if language == "es" else "GLOBAL")
            lines.append(f"{i}. [{action.action_id}] Column: {col_info}" if language == "en"
                          else f"{i}. [{action.action_id}] Columna: {col_info}")
            lines.append(f"   Description: {action.description}" if language == "en"
                          else f"   Descripcion: {action.description}")
            lines.append(f"   Parameters: {action.parameters if action.parameters else '{}'}" if language == "en"
                          else f"   Parametros: {action.parameters if action.parameters else '{}'}")
            lines.append(f"   Source: {action.source}" if language == "en"
                          else f"   Fuente: {action.source}")
            lines.append(f"   Approved: {action.approved}" if language == "en"
                          else f"   Aprobada: {action.approved}")
            lines.append("")
    else:
        lines.append(
            actions_no_executed_line)


    lines.append("-" * 70)
    lines.append(col_modified_section_title)
    lines.append("-" * 70)
    if report.transforms:
        for transform in report.transforms:
            if language == "en":
                lines.append(
                    f"Column: {transform.column}")
                lines.append(f"  Action: {transform.action_id}")
                lines.append(f"  Input type: {transform.input_dtype}")
                lines.append(f"  Output type: {transform.output_dtype}")
                lines.append(f"  Nulls before: {transform.nulls_before}")
                lines.append(f"  Nulls after: {transform.nulls_after}")
                lines.append(f"  Values changed: {transform.values_changed}")
                if transform.summary:
                    lines.append(f"  Summary: {transform.summary}")
            else:
                lines.append(f"Columna: {transform.column}")
                lines.append(f"  Accion: {transform.action_id}")
                lines.append(f"  Tipo entrada: {transform.input_dtype}")
                lines.append(f"  Tipo salida: {transform.output_dtype}")
                lines.append(f"  Nulos antes: {transform.nulls_before}")
                lines.append(f"  Nulos despues: {transform.nulls_after}")
                lines.append(f"  Valores cambiados: {transform.values_changed}")
                if transform.summary:
                    lines.append(f"  Resumen: {transform.summary}")
            lines.append("")
    else:
        lines.append(no_transforms_line)


    lines.append("-" * 70)
    lines.append(warnings_cleaning_section_title)
    lines.append("-" * 70)
    if report.cleaning_warnings:
        for warn in report.cleaning_warnings:
            lines.append(f"  - {warn}")
    else:
        lines.append(no_cleaning_warnings_line)
    lines.append("")
    lines.append("=" * 70)
    lines.append(footer_line)
    lines.append("=" * 70)
    lines.append("")

    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")





def _write_json_report(path: Path, report: AuditReport) -> None:
    """Escribe el reporte en formato JSON estructurado."""
    import json
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )