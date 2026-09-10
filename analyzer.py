"""analyzer.py

Análisis determinista y ESTRICTAMENTE DE SOLO LECTURA de archivos CSV/XLSX.

Reglas de este módulo (no negociables):
    - Nunca escribe en disco ni modifica el archivo original.
    - No utiliza threads internamente. El reporte de progreso se delega
      vía callback a la capa superior.
    - Respeta Copy-on-Write y el dtype string de pandas 3.0.x.
"""

from __future__ import annotations

import csv
import re
import zipfile
from collections.abc import Callable
from pathlib import Path

import openpyxl
import pandas as pd

import config
from models import (
    AnalysisReport,
    ColumnStats,
    FileInfo,
    FileType,
    Issue,
    Severity,
)

# Configuración interna
_CSV_ENCODINGS_TO_TRY: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_CSV_CANDIDATE_DELIMITERS = ",;\t|"

# Normalización para detectar encabezados duplicados reales (case/espacios-insensible).
_re_normalized = re.compile(r"[^0-9a-záéíóúñü]+")


class AnalyzerError(Exception):
    """Error controlado durante la lectura o el análisis de un archivo."""


# ---------------------------------------------------------------------------
# Carga de archivos (CSV / XLSX)
# ---------------------------------------------------------------------------

def list_excel_sheets(path: Path) -> tuple[str, ...]:
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        raise AnalyzerError(
            f"No se pudo abrir el archivo Excel (¿está corrupto o no es un .xlsx válido?): {exc}"
        ) from exc
    try:
        sheet_names = tuple(workbook.sheetnames)
    finally:
        workbook.close()
    if not sheet_names:
        raise AnalyzerError("El archivo Excel no tiene ninguna hoja.")
    return sheet_names


def build_file_info(path: Path) -> FileInfo:
    if not path.exists():
        raise AnalyzerError(f"El archivo no existe: {path}")
    if not path.is_file():
        raise AnalyzerError(f"La ruta indicada no es un archivo: {path}")

    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise AnalyzerError("El archivo está vacío (0 bytes).")
    
    if size_bytes > config.MAX_FILE_SIZE_BYTES:
        raise AnalyzerError(
            f"El archivo supera el límite de tamaño permitido "
            f"({config.MAX_FILE_SIZE_BYTES / (1024*1024):.0f} MB)."
        )

    suffix = path.suffix.lower()
    if suffix == ".csv":
        file_type = FileType.CSV
        sheet_names: tuple[str, ...] = ()  # Literal usado en lugar de tuple()
    elif suffix == ".xlsx":
        file_type = FileType.XLSX
        sheet_names = list_excel_sheets(path)
    else:
        raise AnalyzerError(
            f"Formato no soportado: '{suffix}'. Esta fase solo admite .csv y .xlsx."
        )

    return FileInfo(path=path, file_type=file_type, size_bytes=size_bytes, sheet_names=sheet_names)


def _detect_csv_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=_CSV_CANDIDATE_DELIMITERS)
        return dialect.delimiter
    except csv.Error:
        return ","


def _normalize_csv_headers(path: Path, encoding: str, delimiter: str) -> tuple[bool, tuple[str, ...]]:
    """Normaliza los encabezados del CSV antes de cargar (tolerante, plan Fiverr).

    Reglas:
      - Encabezado vacío o de espacios -> se auto-nombra 'Columna_N' (N = posición
        1-based). Ya NO se rechaza el archivo entero: los archivos reales de
        clientes tienen columnas sin nombre y rechazarlos perdía el trabajo.
      - Duplicados reales (tras normalizar espacios) -> sigue siendo rechazo:
        cargarlos implicaría desplazar/renombrar columnas silenciosamente.

    Devuelve (hubo_cambios, encabezados_finales).
    """
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            headers = next(reader)
        except StopIteration:
            return False, ()

        seen: set[str] = set()
        renamed = False
        final: list[str] = []
        for i, h in enumerate(headers, start=1):
            h_str = str(h).strip()
            key = _re_normalized.sub("", h_str.lower())
            if key and key in seen:
                raise AnalyzerError(
                    f"El archivo CSV contiene columnas duplicadas ('{h_str}'). "
                    "Corrija los nombres en el archivo original para evitar pérdida de datos."
                )
            if key:
                seen.add(key)
            else:
                h_str = f"Columna_{i}"
                renamed = True
            final.append(h_str)
        return renamed, tuple(final)


def _read_csv_renamed_headers(
    path: Path, encoding: str, delimiter: str, final_headers: tuple[str, ...]
) -> pd.DataFrame:
    """Lee un CSV cuyo encabezado fue normalizado (auto-nombres) en origen.

    Usa la primera fila como datos (skiprows=0 + names=): la fila 1 son los
    encabezados ORIGINALES (parcialmente vacíos), que se descartan al asignar
    los nombres finales. Las filas de datos empiezan en la fila 2.
    """
    read_kwargs = {
        "filepath_or_buffer": path,
        "sep": delimiter,
        "encoding": encoding,
        "keep_default_na": False,
        "na_values": [""],
        "names": list(final_headers),
        "skiprows": 1,
        "header": None,
    }
    try:
        return pd.read_csv(**read_kwargs, engine="c")
    except pd.errors.ParserError:
        return pd.read_csv(**read_kwargs, engine="python")


def _read_csv_with_fallback(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in _CSV_ENCODINGS_TO_TRY:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(8192)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        if not sample.strip():
            raise AnalyzerError("El archivo CSV parece no tener contenido.")

        delimiter = _detect_csv_delimiter(sample)

        renamed, final_headers = _normalize_csv_headers(path, encoding, delimiter)
        if renamed:
            return _read_csv_renamed_headers(path, encoding, delimiter, final_headers)

        read_kwargs = {
            "filepath_or_buffer": path,
            "sep": delimiter,
            "encoding": encoding,
            "keep_default_na": False,
            "na_values": [""],
        }

        try:
            return pd.read_csv(**read_kwargs, engine="c")
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except pd.errors.EmptyDataError as exc:
            raise AnalyzerError("El archivo CSV no contiene columnas ni datos.") from exc
        except pd.errors.ParserError:
            try:
                return pd.read_csv(**read_kwargs, engine="python")
            except (OSError, ValueError, TypeError, pd.errors.ParserError) as e:
                last_error = e
                continue

    raise AnalyzerError(f"No se pudo leer el CSV. Último error: {last_error}")


def _normalize_xlsx_headers(path: Path, sheet_name: str) -> tuple[bool, tuple[str, ...]]:
    """Normaliza los encabezados de una hoja Excel (tolerante, plan Fiverr).

    Igual que en CSV: encabezado vacío -> 'Columna_N' (ya no rechaza el archivo);
    duplicados reales -> AnalyzerError. Devuelve (hubo_cambios, encabezados_finales).
    """
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        raise AnalyzerError(f"Error al validar la estructura del Excel: {exc}") from exc

    try:
        if sheet_name not in workbook.sheetnames:
            raise AnalyzerError(f"La hoja '{sheet_name}' no existe en el archivo.")
        sheet = workbook[sheet_name]
        first_row: tuple = ()
        for row in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
            first_row = tuple(row)
            break
        if not first_row:
            raise AnalyzerError(f"La hoja '{sheet_name}' está completamente vacía.")

        seen: set[str] = set()
        renamed = False
        final: list[str] = []
        for i, cell in enumerate(first_row, start=1):
            h_str = str(cell).strip() if cell is not None else ""
            key = _re_normalized.sub("", h_str.lower())
            if key and key in seen:
                raise AnalyzerError(
                    f"La hoja Excel contiene columnas duplicadas ('{h_str}'). "
                    "Corrija los nombres en el archivo original."
                )
            if key:
                seen.add(key)
            else:
                h_str = f"Columna_{i}"
                renamed = True
            final.append(h_str)
        return renamed, tuple(final)
    finally:
        workbook.close()


def _first_usable_sheet(path: Path, sheet_names: tuple[str, ...]) -> str | None:
    """Primera hoja con al menos una celda en su fila 1 (salta portadas vacías)."""
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        raise AnalyzerError(f"No se pudo abrir el archivo Excel: {exc}") from exc
    try:
        for name in sheet_names:
            if name not in workbook.sheetnames:
                continue
            sheet = workbook[name]
            for row in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
                if any(c is not None and str(c).strip() != "" for c in row):
                    return name
                break
        return None
    finally:
        workbook.close()


def _read_xlsx(path: Path, sheet_name: str) -> pd.DataFrame:
    renamed, final_headers = _normalize_xlsx_headers(path, sheet_name)
    try:
        if not renamed:
            return pd.read_excel(
                path,
                sheet_name=sheet_name,
                engine="openpyxl",
                keep_default_na=False,
                na_values=[""]
            )

        # Encabezados normalizados: se lee sin encabezado (saltando la fila 1
        # original, que contenía los nombres vacíos) y se asignan los finales.
        df = pd.read_excel(
            path,
            sheet_name=sheet_name,
            engine="openpyxl",
            header=None,
            skiprows=1,
            keep_default_na=False,
            na_values=[""]
        )
    except ValueError as exc:
        raise AnalyzerError(f"La hoja '{sheet_name}' no existe en el archivo.") from exc
    except (OSError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        raise AnalyzerError(f"No se pudo leer el archivo Excel: {exc}") from exc

    if df.shape == (0, 0):
        # Hoja con encabezados pero sin filas de datos.
        return pd.DataFrame(columns=list(final_headers))
    if len(final_headers) != df.shape[1]:
        raise AnalyzerError(
            f"Inconsistencia de encabezados en la hoja '{sheet_name}': "
            f"{len(final_headers)} nombres para {df.shape[1]} columnas de datos."
        )
    df.columns = list(final_headers)
    return df


def _rename_anonymous_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra columnas sin nombre ('Unnamed: N' de pandas / enteros de la fila 1)
    a 'Columna_N' (N = posición 1-based). No toca columnas con nombre válido."""
    renamed = False
    new_cols: list[str] = []
    for i, col in enumerate(df.columns, start=1):
        col_str = str(col)
        if re.fullmatch(r"Unnamed: \d+(\.\d+)?", col_str) or (
            isinstance(col, int) and not isinstance(col, bool)
        ):
            new_cols.append(f"Columna_{i}")
            renamed = True
        else:
            new_cols.append(col)
    if renamed:
        df = df.copy()
        df.columns = new_cols
    return df


def load_dataframe(file_info: FileInfo, sheet_name: str | None = None) -> pd.DataFrame:
    if file_info.file_type is FileType.CSV:
        df = _read_csv_with_fallback(file_info.path)
    else:
        target_sheet = sheet_name or _first_usable_sheet(
            file_info.path, file_info.sheet_names
        )
        if target_sheet is None:
            raise AnalyzerError("El archivo Excel no tiene hojas con datos.")
        df = _read_xlsx(file_info.path, target_sheet)

    # Tolerancia final: pandas llama 'Unnamed: N' a las columnas sobrantes
    # (filas de datos más largas que el encabezado). Se auto-nombran.
    df = _rename_anonymous_columns(df)
    if df.shape[1] == 0:
        raise AnalyzerError("El archivo no contiene columnas.")
    return df


# ---------------------------------------------------------------------------
# Estadísticas por columna
# ---------------------------------------------------------------------------

def _build_column_stats(df: pd.DataFrame) -> tuple[ColumnStats, ...]:
    stats: list[ColumnStats] = []
    for column in df.columns:
        series = df[column]
        samples = tuple(str(value) for value in series.dropna().unique()[:3])
        stats.append(
            ColumnStats(
                name=str(column),
                dtype=str(series.dtype),
                non_null_count=int(series.notna().sum()),
                null_count=int(series.isna().sum()),
                unique_count=int(series.nunique(dropna=True)),
                sample_values=samples,
            )
        )
    return tuple(stats)


# ---------------------------------------------------------------------------
# Detectores de problemas
# ---------------------------------------------------------------------------

def _detect_fully_empty_rows(df: pd.DataFrame) -> Issue | None:
    empty_mask = df.isna().all(axis=1)
    count = int(empty_mask.sum())
    if count == 0: return None
    return Issue(
        category="FILAS_VACIAS",
        column=None,
        severity=Severity.MEDIUM,
        description="Filas completamente vacías (todas las columnas son nulas).",
        affected_count=count,
        total_count=len(df),
        recommendation="Eliminar estas filas antes de continuar.",
        suggested_action="eliminar_filas_vacias",
    )


def _detect_fully_empty_columns(df: pd.DataFrame) -> Issue | None:
    empty_mask = df.isna().all(axis=0)
    count = int(empty_mask.sum())
    if count == 0: return None
    empty_columns = tuple(str(col) for col in df.columns[empty_mask])
    return Issue(
        category="COLUMNAS_VACIAS",
        column=None,
        severity=Severity.MEDIUM,
        description="Columnas completamente vacías.",
        affected_count=count,
        total_count=df.shape[1],
        examples=empty_columns[:5],
        recommendation="Eliminar estas columnas si no aportan información.",
        suggested_action="eliminar_columnas_vacias",
    )


def _detect_missing_values(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    total_rows = len(df)
    if total_rows == 0: return issues
    for column in df.columns:
        null_count = int(df[column].isna().sum())
        if null_count == 0: continue
        ratio = null_count / total_rows
        severity = Severity.HIGH if ratio > 0.5 else Severity.MEDIUM if ratio > 0.1 else Severity.LOW
        issues.append(
            Issue(
                category="VALORES_FALTANTES",
                column=str(column),
                severity=severity,
                description=f"Valores faltantes en la columna '{column}'.",
                affected_count=null_count,
                total_count=total_rows,
                recommendation="Decidir si completar, eliminar o dejar sin modificar.",
                suggested_action="revisar_manualmente",
            )
        )
    return issues


def _detect_exact_duplicates(df: pd.DataFrame) -> Issue | None:
    duplicate_mask = df.duplicated(keep="first")
    count = int(duplicate_mask.sum())
    if count == 0: return None
    return Issue(
        category="DUPLICADOS_EXACTOS",
        column=None,
        severity=Severity.MEDIUM,
        description="Filas exactamente duplicadas (todas las columnas coinciden).",
        affected_count=count,
        total_count=len(df),
        recommendation="Eliminar duplicados exactos, conservando la primera aparición.",
        suggested_action="eliminar_duplicados_exactos",
    )


def _detect_possible_duplicates(df: pd.DataFrame) -> Issue | None:
    string_columns = df.select_dtypes(include=["object", "string"]).columns
    if len(string_columns) == 0:
        return None

    normalized = pd.DataFrame(index=df.index)
    for column in df.columns:
        if column in string_columns:
            normalized[column] = df[column].astype("string").str.strip().str.lower()
        else:
            normalized[column] = df[column]

    already_exact = df.duplicated(keep="first")
    normalized_duplicate = normalized.duplicated(keep="first")
    only_after_normalizing = normalized_duplicate & ~already_exact
    count = int(only_after_normalizing.sum())
    
    if count == 0: return None
    return Issue(
        category="POSIBLES_DUPLICADOS",
        column=None,
        severity=Severity.LOW,
        description="Filas que podrían ser duplicadas si se ignoran mayúsculas/espacios.",
        affected_count=count,
        total_count=len(df),
        recommendation="Revisar manualmente antes de eliminar.",
        suggested_action="revisar_manualmente",
    )


_NUMERIC_LIKE_PATTERN = re.compile(r"^-?\d+([.,]\d+)?$")

def _detect_numbers_as_text(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        series = df[column].dropna().astype(str).str.strip()
        if series.empty: continue
        looks_numeric = series.str.match(_NUMERIC_LIKE_PATTERN)
        count = int(looks_numeric.sum())
        if count > 0 and looks_numeric.mean() >= 0.9:
            issues.append(
                Issue(
                    category="NUMEROS_COMO_TEXTO",
                    column=str(column),
                    severity=Severity.MEDIUM,
                    description=f"La columna '{column}' parece numérica pero es texto.",
                    affected_count=count,
                    total_count=len(series),
                    examples=tuple(series[looks_numeric].head(3)),
                    recommendation="Convertir a tipo numérico si el negocio lo requiere.",
                    suggested_action="convertir_a_numerico",
                )
            )
    return issues


def _detect_extra_whitespace(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        series = df[column].dropna().astype(str)
        if series.empty: continue
        has_extra_space = series != series.str.strip()
        count = int(has_extra_space.sum())
        if count == 0: continue
        issues.append(
            Issue(
                category="ESPACIOS_INNECESARIOS",
                column=str(column),
                severity=Severity.LOW,
                description=f"Espacios al inicio/final de los valores en '{column}'.",
                affected_count=count,
                total_count=len(series),
                recommendation="Aplicar trim (eliminar espacios externos).",
                suggested_action="trim_espacios",
            )
        )
    return issues


def _detect_case_inconsistencies(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        series = df[column].dropna().astype(str).str.strip()
        series = series[series != ""]
        if series.empty: continue
        variants_per_group = series.groupby(series.str.lower()).nunique()
        inconsistent_groups = variants_per_group[variants_per_group > 1]
        if inconsistent_groups.empty: continue
        affected = int(series.str.lower().isin(inconsistent_groups.index).sum())
        issues.append(
            Issue(
                category="INCONSISTENCIA_MAYUSCULAS",
                column=str(column),
                severity=Severity.LOW,
                description=f"Mismos valores escritos con distinta capitalización en '{column}'.",
                affected_count=affected,
                total_count=len(series),
                examples=tuple(str(v) for v in inconsistent_groups.index[:3]),
                recommendation="Normalizar a un único formato.",
                suggested_action="normalizar_mayusculas",
            )
        )
    return issues


def _detect_empty_strings(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        series = df[column].dropna().astype(str)
        if series.empty: continue
        empty_mask = series.str.strip() == ""
        count = int(empty_mask.sum())
        if count == 0: continue
        issues.append(
            Issue(
                category="STRINGS_VACIOS",
                column=str(column),
                severity=Severity.LOW,
                description=f"Valores de texto vacíos (no nulos, pero sin contenido) en '{column}'.",
                affected_count=count,
                total_count=len(series),
                recommendation="Considerar convertir estos valores a nulo explícito.",
                suggested_action="convertir_a_nulo",
            )
        )
    return issues


def _detect_outliers(df: pd.DataFrame, min_samples: int = 10) -> list[Issue]:
    issues: list[Issue] = []
    numeric_columns = df.select_dtypes(include=["number"]).columns
    for column in numeric_columns:
        series = df[column].dropna()
        if len(series) < min_samples: continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0: continue
        lower_bound, upper_bound = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_mask = (series < lower_bound) | (series > upper_bound)
        count = int(outlier_mask.sum())
        if count == 0: continue
        issues.append(
            Issue(
                category="OUTLIERS_NUMERICOS",
                column=str(column),
                severity=Severity.LOW,
                description=f"Valores atípicos (método IQR) en '{column}'.",
                affected_count=count,
                total_count=len(series),
                examples=tuple(str(v) for v in series[outlier_mask].head(3)),
                recommendation="Revisar manualmente.",
                suggested_action="revisar_manualmente",
            )
        )
    return issues


_DATE_HINT_PATTERN = re.compile(r"(fecha|date|nacimiento)", re.IGNORECASE)

def _detect_inconsistent_dates(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        series = df[column].dropna().astype(str).str.strip()
        series = series[series != ""]
        if series.empty: continue

        column_hints_date = bool(_DATE_HINT_PATTERN.search(str(column)))
        
        sample_size = min(100, len(series))
        sample = series.sample(n=sample_size, random_state=42)
        sample_parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        
        if not column_hints_date and sample_parsed.notna().mean() < 0.6:
            continue
            
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        failed_count = int(parsed.isna().sum())
        if failed_count == 0: continue

        issues.append(
            Issue(
                category="FECHAS_INCONSISTENTES",
                column=str(column),
                severity=Severity.MEDIUM,
                description=f"Formatos de fecha inconsistentes o no reconocidos en '{column}'.",
                affected_count=failed_count,
                total_count=len(series),
                examples=tuple(series[parsed.isna()].head(3)),
                recommendation="Unificar el formato de fecha (ej. AAAA-MM-DD).",
                suggested_action="normalizar_fechas",
            )
        )
    return issues


_EMAIL_HINT_PATTERN = re.compile(r"(mail|correo)", re.IGNORECASE)
_EMAIL_VALID_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _detect_suspicious_emails(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    candidate_columns = [c for c in df.columns if _EMAIL_HINT_PATTERN.search(str(c))]
    for column in candidate_columns:
        series = df[column].dropna().astype(str).str.strip()
        if series.empty: continue
        invalid_mask = ~series.str.match(_EMAIL_VALID_PATTERN)
        count = int(invalid_mask.sum())
        if count == 0: continue
        issues.append(
            Issue(
                category="EMAILS_SOSPECHOSOS",
                column=str(column),
                severity=Severity.MEDIUM,
                description=f"Valores que no cumplen un formato de email válido en '{column}'.",
                affected_count=count,
                total_count=len(series),
                examples=tuple(series[invalid_mask].head(3)),
                recommendation="Revisar manualmente.",
                suggested_action="revisar_manualmente",
            )
        )
    return issues


_PHONE_HINT_PATTERN = re.compile(r"(tel|phone|celular|whatsapp)", re.IGNORECASE)
_PHONE_ALLOWED_CHARS_PATTERN = re.compile(r"^[\d\s()+-]+$")

def _detect_suspicious_phones(df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    candidate_columns = [c for c in df.columns if _PHONE_HINT_PATTERN.search(str(c))]
    for column in candidate_columns:
        series = df[column].dropna().astype(str).str.strip()
        if series.empty: continue
        digit_counts = series.str.replace(r"\D", "", regex=True).str.len()
        invalid_mask = (
            ~series.str.match(_PHONE_ALLOWED_CHARS_PATTERN)
            | (digit_counts < 7)
            | (digit_counts > 15)
        )
        count = int(invalid_mask.sum())
        if count == 0: continue
        issues.append(
            Issue(
                category="TELEFONOS_SOSPECHOSOS",
                column=str(column),
                severity=Severity.LOW,
                description=f"Valores con formato o longitud atípica en '{column}'.",
                affected_count=count,
                total_count=len(series),
                examples=tuple(series[invalid_mask].head(3)),
                recommendation="Revisar manualmente.",
                suggested_action="revisar_manualmente",
            )
        )
    return issues


_COLUMN_NAME_HINT_PATTERN = re.compile(r"(columna|column|col|campo|field)", re.IGNORECASE)

def _detect_unnamed_columns(df: pd.DataFrame) -> list[Issue]:
    """Detecta columnas que fueron auto-nombradas por no tener encabezado en origen.

    El archivo YA se cargó (tolerancia del plan Fiverr): estas columnas existen y
    conservan sus datos, pero el cliente debe decidir su nombre final.
    """
    issues: list[Issue] = []
    for i, column in enumerate(df.columns, start=1):
        col_str = str(column)
        if re.fullmatch(r"Columna_\d+", col_str) or col_str.startswith("Unnamed:"):
            issues.append(
                Issue(
                    category="ENCABEZADO_AUTO_GENERADO",
                    column=col_str,
                    severity=Severity.MEDIUM,
                    description=f"La columna {i} no tenía encabezado en el archivo y fue auto-nombrada '{col_str}'.",
                    affected_count=int(df[column].notna().sum()),
                    total_count=len(df),
                    recommendation="Renombrar la columna con su nombre de negocio antes de exportar.",
                    suggested_action="revisar_manualmente",
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def analyze_dataframe(
    df: pd.DataFrame, 
    file_info: FileInfo, 
    sheet_name: str | None,
    progress_callback: Callable[[int, int, str], None] | None = None
) -> AnalysisReport:
    issues: list[Issue] = []
    
    steps = [
        ("Encabezados sin nombre", [_detect_unnamed_columns]),
        ("Estructura base (vacíos y duplicados exactos)", [_detect_fully_empty_rows, _detect_fully_empty_columns, _detect_exact_duplicates]),
        ("Posibles duplicados", [_detect_possible_duplicates]),
        ("Valores faltantes y formato de texto", [_detect_missing_values, _detect_empty_strings, _detect_extra_whitespace, _detect_case_inconsistencies]),
        ("Conversiones y numéricos", [_detect_numbers_as_text, _detect_outliers]),
        ("Análisis de semántica de negocio", [_detect_inconsistent_dates, _detect_suspicious_emails, _detect_suspicious_phones])
    ]
    
    total_steps = len(steps)
    
    for i, (step_name, detectors) in enumerate(steps, 1):
        if progress_callback:
            progress_callback(i, total_steps, f"Fase {i}: {step_name}...")
        
        for detector in detectors:
            result = detector(df)
            if result is None:
                continue
            if isinstance(result, list):
                issues.extend(result)
            else:
                issues.append(result)

    return AnalysisReport(
        file_info=file_info,
        sheet_name=sheet_name,
        row_count=len(df),
        column_count=df.shape[1],
        column_stats=_build_column_stats(df),
        issues=tuple(issues),
    )


def analyze_file(
    path: Path | str, 
    sheet_name: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None
) -> AnalysisReport:
    file_path = Path(path)
    file_info = build_file_info(file_path)
    resolved_sheet = sheet_name or (
        file_info.sheet_names[0] if file_info.sheet_names else None
    )
    df = load_dataframe(file_info, resolved_sheet)
    return analyze_dataframe(df, file_info, resolved_sheet, progress_callback)