import inspect
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import pandas as pd

from ai import generate_proposals
from analyzer import (
    AnalyzerError,
    analyze_dataframe,
    build_file_info,
    list_excel_sheets,
    load_dataframe,
)
from batch_processor import BatchError, process_batch_files, process_batch_folder
from cleaner import clean_dataframe
from exporter import ExportError, export_audit_report, export_dataframe, generate_audit_report
from gui.dashboard import Dashboard
from gui.issues_panel import IssuesPanel
from models import CleaningAction, FileInfo, FileType
# ---------------------------------------------------------------------------
# ACCIONES PERSONALIZADAS (Fase 9.1): constructores PUROS (testeables sin Tk).
# Valida la entrada del usuario y produce CleaningAction con approved=False:
# NADA se ejecuta sin pasar por el panel de aprobación y el Validator.
# ---------------------------------------------------------------------------

def _parse_column_list(raw: str, available: list[str]) -> list[str]:
    """Convierte 'Email, ID' en ['Email', 'ID'] validando contra las columnas reales."""
    if raw is None:
        raise ValueError("No se especificó ninguna columna.")
    cols = [c.strip() for c in raw.split(",") if c.strip()]
    if not cols:
        raise ValueError("No se especificó ninguna columna.")
    unknown = [c for c in cols if c not in available]
    if unknown:
        raise ValueError(f"Columnas inexistentes: {unknown}.\nDisponibles: {available}")
    return cols


def _build_dedup_action(subset: list[str], keep: str) -> CleaningAction:
    """Crea la acción eliminar_duplicados_por_columna (criterio: columnas elegidas)."""
    if not subset:
        raise ValueError("Debe elegir al menos una columna criterio.")
    keep = (keep or "first").strip().lower()
    if keep not in ("first", "last"):
        raise ValueError(f"Criterio de conservación inválido: '{keep}'. Use 'first' o 'last'.")
    return CleaningAction(
        action_id="eliminar_duplicados_por_columna",
        column=subset[0],
        description=f"Duplicados por columna(s): {subset} (conservar '{keep}')",
        approved=False,
        parameters={"subset_columns": list(subset), "keep": keep},
        source="manual",
    )


def _build_split_action(column: str, delimiter: str, new_names: list[str], available: list[str]) -> CleaningAction:
    """Crea la acción dividir_columna (delimitador LITERAL, nunca regex)."""
    if column not in available:
        raise ValueError(f"La columna '{column}' no existe. Disponibles: {available}")
    if not isinstance(delimiter, str) or delimiter == "":
        raise ValueError("El delimitador no puede estar vacío (ej: espacio, coma, guion).")
    if not new_names or not all(isinstance(n, str) and n.strip() for n in new_names):
        raise ValueError("Debe indicar al menos un nombre para las nuevas columnas.")
    new_names = [n.strip() for n in new_names]
    if len(set(new_names)) != len(new_names):
        raise ValueError("Los nombres de las nuevas columnas están repetidos.")
    if any(n in available and n != column for n in new_names):
        clash = [n for n in new_names if n in available and n != column]
        raise ValueError(f"Estos nombres ya existen en el archivo: {clash}. Elija otros.")
    return CleaningAction(
        action_id="dividir_columna",
        column=column,
        description=f"Dividir '{column}' por {delimiter!r} en {new_names}",
        approved=False,
        parameters={"delimiter": delimiter, "new_column_names": new_names},
        source="manual",
    )


def _build_merge_action(sources: list[str], new_name: str, separator: str,
                        drop_sources: bool, available: list[str]) -> CleaningAction:
    """Crea la acción unir_columnas (concatenación con separador opcional)."""
    if not sources:
        raise ValueError("Debe elegir al menos una columna de origen.")
    unknown = [c for c in sources if c not in available]
    if unknown:
        raise ValueError(f"Columnas inexistentes: {unknown}. Disponibles: {available}")
    if not isinstance(new_name, str) or not new_name.strip():
        raise ValueError("Debe indicar el nombre de la columna resultante.")
    new_name = new_name.strip()
    if new_name in available and new_name not in sources:
        raise ValueError(f"El nombre '{new_name}' ya existe en el archivo. Elija otro.")
    if not isinstance(separator, str):
        raise ValueError("El separador debe ser un texto.")
    return CleaningAction(
        action_id="unir_columnas",
        column=None,
        description=f"Unir {sources} en '{new_name}'"
                    + (f" con separador {separator!r}" if separator else " (sin separador)"),
        approved=False,
        parameters={"source_columns": list(sources), "new_column_name": new_name,
                    "separator": separator, "drop_source_columns": bool(drop_sources)},
        source="manual",
    )


def _build_replace_action(column: str, mappings: list[dict], available: list[str]) -> CleaningAction:
    """Crea la acción reemplazar_valores (reglas ordenadas: gana la primera que coincide)."""
    if column not in available:
        raise ValueError(f"La columna '{column}' no existe. Disponibles: {available}")
    if not mappings:
        raise ValueError("Debe definir al menos una regla de reemplazo.")
    cleaned: list[dict] = []
    for m in mappings:
        find = m.get("find")
        if not isinstance(find, str) or find == "":
            raise ValueError("Cada regla necesita un texto a buscar no vacío.")
        replace = m.get("replace")
        if replace is not None and not isinstance(replace, str):
            raise ValueError("El reemplazo debe ser un texto o vacío (= nulo real).")
        mode = m.get("match", "exact")
        if mode not in ("exact", "contains", "regex"):
            raise ValueError(f"Modo de coincidencia inválido: '{mode}'.")
        if mode == "regex":
            try:
                re.compile(find)
            except re.error as e:
                raise ValueError(f"La expresión regular '{find}' no es válida: {e}") from e
        cleaned.append({"find": find, "replace": replace, "match": mode})
    return CleaningAction(
        action_id="reemplazar_valores",
        column=column,
        description=f"Reemplazar valores en '{column}' ({len(cleaned)} regla(s))",
        approved=False,
        parameters={"mappings": cleaned},
        source="manual",
    )


class ExcelCleanerApp:
    def __init__(self, root):
        self.root = root
        self.task_queue = queue.Queue()
        
        self.original_df: pd.DataFrame | None = None
        self.cleaned_df: pd.DataFrame | None = None
        self.actions = ()
        self.last_report = None
        self.cleaning_result = None
        self.validation_result = None
        self.current_filepath = ""
        self.current_filename = ""
        
        callbacks = {
            "on_load": self.on_load_file,
            "on_analyze": self.on_analyze,
            "on_ai_analyze": self.on_ai_analyze,
            "on_clean": self.on_clean,
            "on_export": self.on_export,
            "on_batch": self.on_batch,
            "on_custom": self.on_custom,
            "on_reset": self.reset_state
        }
        self.dashboard = Dashboard(self.root, callbacks)
        self.dashboard.pack(fill=tk.X)
        
        self.issues_panel = IssuesPanel(self.root)
        self.issues_panel.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.check_queue()
        
    def check_queue(self):
        try:
            while True:
                msg_type, data = self.task_queue.get_nowait()
                self._handle_worker_message(msg_type, data)
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def _handle_worker_message(self, msg_type, data):
        if msg_type == "LOAD_DONE":
            rows = len(self.original_df) if self.original_df is not None else 0
            cols = len(self.original_df.columns) if self.original_df is not None else 0
            self.dashboard.update_info(self.current_filename, rows, cols)
            self.dashboard.update_status("Archivo cargado. Listo para analizar.")
            self.dashboard.set_buttons_state(analyze=tk.NORMAL)
            self.dashboard.progress.stop()
            
        elif msg_type == "ANALYSIS_DONE":
            self.last_report = data
            
            # Compatibilidad con tests (si el mock trae .actions) o reporte real por issues
            if hasattr(data, 'actions') and data.actions:
                report_actions = list(data.actions)
            else:
                report_actions = []
                for issue in getattr(data, 'issues', []):
                    if issue.suggested_action:
                        report_actions.append(CleaningAction(
                            action_id=issue.suggested_action,
                            column=issue.column,
                            description=issue.description,
                            approved=False,
                            source="analyzer"
                        ))
                    
            self.actions = tuple(report_actions)
            self.issues_panel.populate(self.actions)
            self.dashboard.update_status("Análisis completado. Seleccione acciones o consulte a la IA.")
            self.dashboard.set_buttons_state(clean=tk.NORMAL, ai=tk.NORMAL)
            self.dashboard.progress.stop()

        elif msg_type == "AI_DONE":
            ai_response: AIResponse = data
            ai_actions = []

            if ai_response.warnings:
                warnings_str = "\n".join(ai_response.warnings)
                messagebox.showwarning("Avisos de IA", f"La IA devolvió avisos:\n{warnings_str}")

            for prop in ai_response.proposals:
                ai_actions.append(CleaningAction(
                    action_id=prop.action,
                    column=prop.column,
                    description=f"[IA Conf: {prop.confidence}] {prop.reason}",
                    approved=False,  # IA NO DECIDE, REQUIERE APROBACIÓN
                    parameters=prop.parameters,
                    source=prop.source,
                ))

            if ai_actions:
                self.actions = tuple(ai_actions)
                self.issues_panel.populate(self.actions)
                self.dashboard.update_status("Propuestas de IA recibidas. Revise y aplique.")
            else:
                self.dashboard.update_status("La IA no generó propuestas aplicables.")

            self.dashboard.set_buttons_state(clean=tk.NORMAL, ai=tk.NORMAL)
            self.dashboard.progress.stop()
            
        elif msg_type == "CLEAN_VALIDATE_DONE":
            self.cleaned_df, self.cleaning_result, self.validation_result = data
            self.dashboard.progress.stop()
            
            if self.validation_result and self.validation_result.valid:
                self.dashboard.update_status("Limpieza y Validación Exitosa. Seguro para exportar.")
                self.dashboard.set_buttons_state(export=tk.NORMAL)
                messagebox.showinfo("Validación Exitosa", "El resultado es seguro para exportar.")
            elif self.validation_result:
                self.dashboard.update_status("Validación FALLIDA. Exportación bloqueada.")
                self.dashboard.set_buttons_state(export=tk.DISABLED)
                errors_str = "\n".join(self.validation_result.errors)
                messagebox.showerror("Error de Validación", f"Se detectaron mutaciones no autorizadas:\n{errors_str}")
                
        elif msg_type == "EXPORT_DONE":
            # Compatibilidad: data puede ser ExportResult (tests/legacy) o (res, audit_path, audit_error)
            if isinstance(data, tuple) and len(data) == 3:
                res, audit_path, audit_error = data
            else:
                res, audit_path, audit_error = data, None, None
            self.dashboard.progress.stop()
            if audit_path:
                self.dashboard.update_status("Archivo y Reporte de Auditoría guardados correctamente.")
                messagebox.showinfo(
                    "Éxito",
                    f"Archivo y Reporte de Auditoría guardados con éxito.\n"
                    f"Archivo: {res.path}\n"
                    f"Reporte: {audit_path}\n"
                    f"Filas: {res.rows_exported}",
                )
            elif audit_error:
                # Cero excepciones silenciosas: el export OK se informa, el fallo del reporte también.
                self.dashboard.update_status("Archivo exportado. Reporte de auditoría falló.")
                messagebox.showwarning(
                    "Aviso de Auditoría",
                    f"El archivo se generó correctamente:\n{res.path}\nFilas: {res.rows_exported}\n\n"
                    f"Pero hubo un problema con el Reporte de Auditoría:\n{audit_error}",
                )
            else:
                self.dashboard.update_status("Archivo exportado correctamente.")
                messagebox.showinfo("Éxito", f"Archivo generado:\n{res.path}\nFilas: {res.rows_exported}")
            
        elif msg_type == "BATCH_PROGRESS":
            done, total, name = data
            pct = (done / total * 100.0) if total else 0.0
            self.dashboard.set_progress_value(pct)
            self.dashboard.update_status(f"Batch: procesando {name} ({done}/{total})...")

        elif msg_type == "BATCH_DONE":
            summary = data
            self.dashboard.progress.stop()
            self.dashboard.set_progress_value(100.0)
            self.dashboard.set_buttons_state(load=tk.NORMAL, batch=tk.NORMAL)
            self.dashboard.update_status(
                f"Batch: {summary.processed_ok} OK, {summary.processed_invalid} rechazados, {summary.errors} errores."
            )
            icon = "info" if summary.errors == 0 and summary.processed_invalid == 0 else "warning"
            zip_line = f"\nZIP de resultados:\n{summary.zip_path}" if summary.zip_path else ""
            getattr(messagebox, f"show{icon.capitalize()}")(
                "Batch Completado",
                f"Procesamiento por lotes finalizado.\n\n"
                f"Archivos procesados con éxito: {summary.processed_ok}\n"
                f"Rechazados por el Validator: {summary.processed_invalid}\n"
                f"Con errores (en errors/): {summary.errors}\n"
                f"Filas analizadas: {summary.total_rows_before} -> {summary.total_rows_after} "
                f"(eliminadas: {summary.total_rows_removed})\n"
                f"Cambios totales (celdas + filas): {summary.total_changes}\n"
                f"{zip_line}\n\n"
                f"Reporte maestro:\n{Path(summary.output_dir) / 'batch_audit_summary.txt'}",
            )

        elif msg_type == "ERROR":
            self.dashboard.progress.stop()
            self.dashboard.update_status("Error en la operación.")
            messagebox.showerror("Error", str(data))
            self.dashboard.set_buttons_state(clean=tk.NORMAL, analyze=tk.NORMAL, batch=tk.NORMAL)

    def on_custom(self):
        """Diálogo de acciones personalizadas (dedup por columna / dividir / unir / reemplazar).
        Las acciones creadas quedan pendientes (approved=False) en el panel de revisión."""
        if self.original_df is None:
            messagebox.showerror("Acciones personalizadas", "Cargue un archivo primero.")
            return
        available = [str(c) for c in self.original_df.columns]

        op = tk.simpledialog.askstring(
            "Acciones personalizadas",
            "¿Qué operación desea agregar como PROPUESTA (requiere su aprobación)?\n\n"
            "  1. Duplicados por columna (elegí las columnas criterio)\n"
            "  2. Dividir columna (separar 'Nombre Apellido' en dos columnas)\n"
            "  3. Unir columnas (concatenar en una nueva)\n"
            "  4. Reemplazar valores (basura textual -> nulo o texto limpio)\n\n"
            "Opción (1/2/3/4):",
            initialvalue="1",
        )
        if not op:
            return
        op = op.strip()

        try:
            if op == "1":
                subset = _parse_column_list(
                    tk.simpledialog.askstring(
                        "Duplicados por columna",
                        "Columna(s) criterio (separadas por coma):\n\n"
                        f"Columnas disponibles: {', '.join(available)}",
                        initialvalue=available[0] if available else "",
                    ),
                    available,
                )
                keep = tk.simpledialog.askstring(
                    "Duplicados por columna", "¿Cuál conservar? (first/last):", initialvalue="first"
                ) or "first"
                action = _build_dedup_action(subset, keep)

            elif op == "2":
                column = tk.simpledialog.askstring(
                    "Dividir columna", "Columna a dividir:",
                    initialvalue=available[0] if available else "",
                )
                delimiter = tk.simpledialog.askstring(
                    "Dividir columna",
                    "Delimitador LITERAL (ej: espacio, coma, guion):",
                    initialvalue=" ",
                )
                names_raw = tk.simpledialog.askstring(
                    "Dividir columna",
                    "Nombres de las nuevas columnas (separados por coma):",
                    initialvalue="Parte1, Parte2",
                )
                if column is None or delimiter is None or names_raw is None:
                    return
                new_names = [n.strip() for n in names_raw.split(",") if n.strip()]
                action = _build_split_action(column.strip(), delimiter, new_names, available)

            elif op == "3":
                sources = _parse_column_list(
                    tk.simpledialog.askstring(
                        "Unir columnas",
                        "Columnas a unir (separadas por coma, en orden):\n\n"
                        f"Columnas disponibles: {', '.join(available)}",
                        initialvalue=", ".join(available[:2]) if len(available) >= 2 else "",
                    ),
                    available,
                )
                new_name = tk.simpledialog.askstring(
                    "Unir columnas", "Nombre de la columna resultante:", initialvalue="Union"
                )
                separator = tk.simpledialog.askstring(
                    "Unir columnas", "Separador entre valores:", initialvalue=" "
                )
                drop = messagebox.askyesno(
                    "Unir columnas", "¿Eliminar las columnas de origen después de unir?"
                )
                if new_name is None or separator is None:
                    return
                action = _build_merge_action(sources, new_name, separator, drop, available)

            elif op == "4":
                column = tk.simpledialog.askstring(
                    "Reemplazar valores", "Columna donde reemplazar:",
                    initialvalue=available[0] if available else "",
                )
                find = tk.simpledialog.askstring(
                    "Reemplazar valores",
                    "Texto a buscar (ej: N/A, null, ---):", initialvalue="N/A",
                )
                replace = tk.simpledialog.askstring(
                    "Reemplazar valores",
                    "Reemplazo (VACÍO = convertir a nulo real):", initialvalue="",
                )
                mode = tk.simpledialog.askstring(
                    "Reemplazar valores",
                    "Modo de coincidencia (exact/contains/regex):", initialvalue="exact",
                )
                if column is None or find is None or replace is None or mode is None:
                    return
                mappings = [{"find": find, "replace": (replace if replace != "" else None),
                             "match": mode.strip().lower()}]
                action = _build_replace_action(column.strip(), mappings, available)

            else:
                messagebox.showerror("Acciones personalizadas", f"Opción no reconocida: '{op}'.")
                return

        except ValueError as e:
            # Validación amable: mensaje entendible, sin stack traces.
            messagebox.showerror("Acciones personalizadas", str(e))
            return

        # La acción entra al panel como PENDIENTE: nada se ejecuta sin aprobación.
        self.actions = tuple(self.actions) + (action,)
        self.issues_panel.populate(self.actions)
        self.dashboard.update_status(
            f"Acción personalizada agregada como propuesta pendiente: {action.action_id}."
        )
        self.dashboard.set_buttons_state(clean=tk.NORMAL)

    def on_load_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Excel y CSV", "*.xlsx *.csv")])
        if not filepath: return

        # Selector de hoja para XLSX multi-hoja (metadata de solo lectura vía Analyzer).
        sheet_name = None
        if Path(filepath).suffix.lower() == ".xlsx":
            try:
                sheets = list_excel_sheets(Path(filepath))
            except AnalyzerError as e:
                messagebox.showerror("Error", str(e))
                return
            if len(sheets) > 1:
                sheet_name = simpledialog.askstring(
                    "Hoja de Excel",
                    "El archivo tiene varias hojas:\n  - " + "\n  - ".join(sheets)
                    + "\n\nEscriba el nombre de la hoja a procesar:",
                    initialvalue=sheets[0],
                )
                if not sheet_name:
                    return  # el usuario canceló la selección
                sheet_name = sheet_name.strip()
                if sheet_name not in sheets:
                    messagebox.showerror(
                        "Hoja inválida",
                        f"'{sheet_name}' no existe en el archivo.\nHojas disponibles: {', '.join(sheets)}",
                    )
                    return

        self.reset_state()
        self.current_filepath = filepath
        self.current_filename = Path(filepath).name
        self.dashboard.update_status("Cargando archivo...")
        self.dashboard.progress.start(10)
        threading.Thread(target=self._worker_load, args=(filepath, sheet_name), daemon=True).start()

    def _worker_load(self, filepath, sheet_name=None):
        try:
            # Carga vía Analyzer (mismo motor que el batch): fallbacks de encoding,
            # detección de delimitador, límite de tamaño y validación de estructura.
            # Nunca pandas crudo: los CSV con ';' y los XLSX multi-hoja se rompían.
            file_info = build_file_info(Path(filepath))
            if file_info.file_type is FileType.CSV:
                sheet_name = None
            self.original_df = load_dataframe(file_info, sheet_name)
            self.task_queue.put(("LOAD_DONE", None))
        except AnalyzerError as e:
            self.task_queue.put(("ERROR", str(e)))
        except Exception as e:  # noqa: BLE001
            self.task_queue.put(("ERROR", f"Error leyendo archivo: {e}"))

    def on_analyze(self):
        self.dashboard.set_buttons_state(analyze=tk.DISABLED, clean=tk.DISABLED, export=tk.DISABLED, ai=tk.DISABLED)
        self.dashboard.update_status("Analizando archivo...")
        self.dashboard.progress.start(15)
        threading.Thread(target=self._worker_analyze, daemon=True).start()

    def _worker_analyze(self):
        try:
            if self.original_df is None: raise ValueError("DataFrame no inicializado.")
            file_path_obj = Path(self.current_filepath)
            f_size = file_path_obj.stat().st_size if file_path_obj.exists() else 0
            ext = file_path_obj.suffix.lower()
            f_type = FileType.CSV if ext == ".csv" else FileType.XLSX
            file_info = FileInfo(path=file_path_obj, file_type=f_type, size_bytes=f_size)
            
            sig = inspect.signature(analyze_dataframe)
            if 'progress_callback' in sig.parameters:
                report = analyze_dataframe(self.original_df, file_info=file_info, sheet_name=None, progress_callback=lambda c, t, m: None)
            else:
                report = analyze_dataframe(self.original_df, file_info=file_info, sheet_name=None)
                
            self.task_queue.put(("ANALYSIS_DONE", report))
        except Exception as e:  # noqa: BLE001
            self.task_queue.put(("ERROR", f"Error en Analyzer: {e}"))

    def on_ai_analyze(self):
        if self.last_report is None:
            messagebox.showerror("Error", "Debe ejecutar el análisis básico primero.")
            return
        self.dashboard.set_buttons_state(clean=tk.DISABLED, export=tk.DISABLED, ai=tk.DISABLED)
        self.dashboard.update_status("Consultando a la IA Local...")
        self.dashboard.progress.start(15)
        threading.Thread(target=self._worker_ai, daemon=True).start()

    def _worker_ai(self):
        try:
            if self.last_report is None:
                raise ValueError("No hay reporte de análisis disponible.")
            ai_response: AIResponse = generate_proposals(self.last_report)
            self.task_queue.put(("AI_DONE", ai_response))
        except Exception as e:  # noqa: BLE001
            self.task_queue.put(("ERROR", f"Error de IA: {e}"))

    def on_clean(self):
        self.actions = self.issues_panel.get_approved_actions()
        self.dashboard.set_buttons_state(clean=tk.DISABLED, export=tk.DISABLED, ai=tk.DISABLED)
        self.dashboard.update_status("Limpiando y validando...")
        self.dashboard.progress.start(15)
        threading.Thread(target=self._worker_clean_validate, daemon=True).start()

    def _worker_clean_validate(self):
        try:
            if self.original_df is None: raise ValueError("DataFrame no inicializado.")
            cleaned_df, cleaning_res = clean_dataframe(self.original_df, self.actions)
            val_result = validate_cleaning(self.original_df, cleaned_df, self.actions, cleaning_res)
            self.task_queue.put(("CLEAN_VALIDATE_DONE", (cleaned_df, cleaning_res, val_result)))
        except Exception as e:  # noqa: BLE001
            self.task_queue.put(("ERROR", f"Error en Cleaner/Validator: {e}"))

    def on_export(self):
        if not self.validation_result or not self.validation_result.valid:
            messagebox.showerror("Seguridad", "Exportación bloqueada. Validación previa fallida.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")])
        if not filepath: return

        # Idioma del reporte de auditoría ("es" por defecto, "en" para clientes
        # internacionales). Cancelar el diálogo = exportar con reporte en español.
        report_lang = (simpledialog.askstring(
            "Audit report language / Idioma del reporte",
            "Idioma del reporte de auditoría (es/en):\nAudit report language (es/en):",
            initialvalue="es",
        ) or "es").strip().lower()
        if report_lang not in ("es", "en"):
            report_lang = "es"

        self.dashboard.set_buttons_state(export=tk.DISABLED)
        self.dashboard.update_status(f"Exportando archivo... (reporte: {report_lang})")
        self.dashboard.progress.start(15)
        threading.Thread(target=self._worker_export, args=(filepath, report_lang), daemon=True).start()

    def _worker_export(self, filepath, report_lang="es"):
        try:
            if self.cleaned_df is None or self.validation_result is None:
                raise ValueError("Faltan datos limpios o validados para exportar.")

            # --- Reporte de Auditoría (Fase 8.5 + Paso 8) ---
            # Se genera ANTES de escribir para poder embeberlo como pestaña
            # _Reporte_Auditoria dentro del XLSX (y sidecar .txt). Un fallo del
            # reporte NO invalida el export, pero NUNCA se omite en silencio.
            audit_report = None
            audit_path = None
            audit_error = None
            try:
                if self.cleaning_result is not None and self.original_df is not None:
                    audit_report = generate_audit_report(
                        original_file=self.current_filepath,
                        export_file=str(filepath),
                        cleaning_result=self.cleaning_result,
                        validation_result=self.validation_result,
                        df_original=self.original_df,
                        df_clean=self.cleaned_df,
                        language=report_lang,
                    )
            except Exception as e:  # noqa: BLE001
                audit_error = f"{type(e).__name__}: {e}"

            res = export_dataframe(self.cleaned_df, filepath, self.validation_result,
                                   overwrite=True, audit_report=audit_report)

            # Sidecar .txt en el mismo directorio (además de la pestaña embebida).
            try:
                if audit_report is not None:
                    audit_path = export_audit_report(audit_report, format="txt")
            except Exception as e:  # noqa: BLE001
                audit_error = audit_error or f"{type(e).__name__}: {e}"

            self.task_queue.put(("EXPORT_DONE", (res, audit_path, audit_error)))
        except ExportError as e:
            self.task_queue.put(("ERROR", str(e)))
            self.task_queue.put(("CLEAN_VALIDATE_DONE", (self.cleaned_df, self.cleaning_result, self.validation_result)))
        except Exception as e:  # noqa: BLE001
            self.task_queue.put(("ERROR", f"Error crítico exportando: {e}"))

    # ------------------------------------------------------------------
    # BATCH MODE (Fase 9.0): carpeta completa o multi-selección de archivos
    # ------------------------------------------------------------------

    def on_batch(self):
        """Pregunta el modo: carpeta completa o selección manual de archivos."""
        modo = tk.simpledialog.askstring(
            "Batch Mode",
            "Escriba el modo de procesamiento:\n"
            "  - 'carpeta'  : procesa TODOS los .csv/.xlsx/.xls de una carpeta\n"
            "  - 'archivos' : selecciona manualmente varios archivos\n\n"
            "Modo:",
            initialvalue="carpeta",
        )
        if not modo:
            return
        modo = modo.strip().lower()
        if modo not in ("carpeta", "archivos"):
            messagebox.showerror("Batch", "Modo no reconocido. Use 'carpeta' o 'archivos'.")
            return

        output_dir = filedialog.askdirectory(title="Seleccione la CARPETA DE SALIDA para los archivos limpios")
        if not output_dir:
            return

        if modo == "carpeta":
            input_dir = filedialog.askdirectory(title="Seleccione la CARPETA DE ENTRADA con los archivos a limpiar")
            if not input_dir:
                return
            if Path(input_dir).resolve() == Path(output_dir).resolve():
                messagebox.showerror("Batch", "La carpeta de entrada y de salida deben ser distintas.")
                return
            self._start_batch(mode="folder", input_dir=input_dir, output_dir=output_dir)
        else:
            seleccionados = filedialog.askopenfilenames(
                title="Seleccione los archivos a limpiar (Ctrl+clic para varios)",
                filetypes=[("Excel y CSV", "*.xlsx *.xls *.csv"), ("Todos", "*.*")],
            )
            if not seleccionados:
                return
            self._start_batch(mode="files", input_dir=None, output_dir=output_dir,
                              file_paths=list(seleccionados))

    def _start_batch(self, mode: str, input_dir: str | None, output_dir: str,
                     file_paths: list[str] | None = None):
        rules_config = self.dashboard.get_batch_config()
        create_zip = self.dashboard.is_batch_zip()
        self.dashboard.set_buttons_state(batch=tk.DISABLED, load=tk.DISABLED)
        origen = input_dir if mode == "folder" else f"{len(file_paths)} archivos seleccionados"
        self.dashboard.update_status(f"Procesando (Batch Mode): {origen}...")
        threading.Thread(
            target=self._worker_batch,
            args=(mode, input_dir, output_dir, file_paths, rules_config, create_zip),
            daemon=True,
        ).start()

    def _worker_batch(self, mode, input_dir, output_dir, file_paths, rules_config, create_zip):
        def _progress(done, total, name):
            self.task_queue.put(("BATCH_PROGRESS", (done, total, name)))

        try:
            if mode == "folder":
                summary = process_batch_folder(
                    input_dir, output_dir, rules_config=rules_config,
                    progress_callback=_progress, create_zip=create_zip,
                )
            else:
                summary = process_batch_files(
                    file_paths or [], output_dir, rules_config=rules_config,
                    progress_callback=_progress,
                )
            self.task_queue.put(("BATCH_DONE", summary))
        except BatchError as e:
            self.task_queue.put(("ERROR", f"Batch: {e}"))
        except Exception as e:  # noqa: BLE001
            self.task_queue.put(("ERROR", f"Error crítico en batch: {type(e).__name__}: {e}"))

    def reset_state(self):
        self.original_df = None
        self.cleaned_df = None
        self.actions = ()
        self.last_report = None
        self.cleaning_result = None
        self.validation_result = None
        self.current_filepath = ""
        self.current_filename = ""
        
        self.dashboard.update_info("Ninguno", 0, 0)
        self.dashboard.update_status("Esperando archivo...")
        self.dashboard.progress.stop()
        self.dashboard.set_buttons_state(
            load=tk.NORMAL, analyze=tk.DISABLED, clean=tk.DISABLED, export=tk.DISABLED, ai=tk.DISABLED
        )
        self.issues_panel.clear()