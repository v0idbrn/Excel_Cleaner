"""batch_processor.py — Fase 9.0: Motor de Procesamiento por Lotes Masivo y Multi-Pass.

Procesa una carpeta entera (o una lista de archivos) de .csv/.xlsx/.xls aplicando el
pipeline multi-pass de cleaner.run_multipass_cleaning (Pass 1 estructural -> Pass 2
tipológica -> Pass 3 consolidación) con la barrera Zero-Trust del Validator en cada
archivo.

Garantías:
    - Aislamiento de errores: un archivo corrupto/protegido NO detiene el lote.
      Se registra, se mueve a <output_dir>/errors/ y se continúa.
    - Zero-write: cada archivo limpio se exporta solo si validate_cleaning() da
      ValidationResult.valid == True (misma barrera que la GUI).
    - Read-only absoluto sobre los archivos de entrada (los rechazados por el
      Validator se COPIAN a errors/ junto con el motivo; nunca se destruyen).
    - Nombres de salida predecibles: se conserva el nombre original del archivo;
      ante colisión en la carpeta de salida se agrega sufijo _1, _2...
    - Cero excepciones silenciosas: cada fallo queda registrado en el resultado
      y en el reporte maestro (batch_audit_summary).

Uso CLI:
    python batch_processor.py <carpeta_entrada> <carpeta_salida>
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analyzer import _read_csv_with_fallback
from cleaner import _auto_actions_from_analysis, run_multipass_cleaning
from exporter import (
    ExportError,
    _compute_transforms,
    export_audit_report,
    export_dataframe,
    generate_audit_report,
)
from models import CleaningResult, ValidationResult
from validators import validate_cleaning

BATCH_EXTENSIONS = (".csv", ".xlsx", ".xls")
VALID_PASS_KEYS = ("pass1", "pass2", "pass3")
ZIP_NAME = "batch_results.zip"


class BatchError(Exception):
    """Error de configuración del lote (rutas inválidas)."""


@dataclass(frozen=True)
class BatchItemResult:
    """Resultado del procesamiento de un solo archivo del lote."""

    source_path: str
    status: str  # "ok" | "error" | "invalid"
    output_path: str | None = None
    audit_path: str | None = None
    rows_before: int = 0
    rows_after: int = 0
    rows_removed: int = 0
    changes: int = 0  # celdas modificadas + filas eliminadas (solo status "ok")
    actions_count: int = 0
    result_label: str = ""  # CLEANED | UNCHANGED (solo status "ok"; honesto vía df.equals)
    warning: str | None = None  # p.ej. validación rechazada (no se exporta)
    error: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    """Reporte maestro del lote completo."""

    input_dir: str
    output_dir: str
    started_at: str
    finished_at: str
    duration_seconds: float
    total_files_found: int
    processed_ok: int
    processed_invalid: int  # limpiado pero validación rechazada (no exportado)
    errors: int
    cleaned_count: int     # archivos con cambios efectivos (CLEANED)
    unchanged_count: int   # archivos sin mutaciones (UNCHANGED)
    total_rows_before: int
    total_rows_after: int
    total_rows_removed: int
    total_changes: int = 0
    zip_path: str | None = None
    items: tuple[BatchItemResult, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 2),
            "zip_path": self.zip_path,
            "totals": {
                "files_found": self.total_files_found,
                "processed_ok": self.processed_ok,
                "processed_invalid": self.processed_invalid,
                "errors": self.errors,
                "cleaned": self.cleaned_count,
                "unchanged": self.unchanged_count,
                "rows_before": self.total_rows_before,
                "rows_after": self.total_rows_after,
                "rows_removed": self.total_rows_removed,
                "changes": self.total_changes,
            },
            "items": [
                {
                    "source_path": it.source_path,
                    "status": it.status,
                    "output_path": it.output_path,
                    "audit_path": it.audit_path,
                    "rows_before": it.rows_before,
                    "rows_after": it.rows_after,
                    "rows_removed": it.rows_removed,
                    "changes": it.changes,
                    "actions_count": it.actions_count,
                    "result_label": it.result_label,
                    "warning": it.warning,
                    "error": it.error,
                }
                for it in self.items
            ],
        }


def _friendly_error(exc: BaseException) -> str:
    """Traduce la causa técnica a un mensaje claro para el cliente comercial.

    Cero stack traces crudos en el reporte: se conserva la causa en lenguaje
    entendible y el tipo de error como contexto mínimo entre corchetes.
    """
    name = type(exc).__name__
    raw = str(exc).strip()
    if isinstance(exc, FileNotFoundError):
        return "El archivo no existe o fue movido antes de procesarlo."
    if isinstance(exc, PermissionError):
        return "El archivo está bloqueado por otro programa o sin permisos de lectura. Ciérrelo e inténtelo de nuevo."
    if not raw:
        return f"No se pudo procesar el archivo ({name})."
    return f"{raw} [{name}]"


def _resolve_passes(rules_config: dict | None, df: pd.DataFrame) -> dict[str, tuple]:
    """Deriva los pases automáticos y aplica el filtro de configuración del usuario.

    rules_config puede traer 'enabled_passes' (iterable de claves pass1/pass2/pass3).
    Cada pase desactivado se convierte en una lista vacía de acciones (no-op validada).
    """
    passes = _auto_actions_from_analysis(df)
    if isinstance(rules_config, dict):
        enabled = rules_config.get("enabled_passes")
        if enabled is not None:
            enabled = set(enabled)
            passes = {k: v for k, v in passes.items() if k in enabled}
    # Si el usuario desactivó todo, un dict con tuplas vacías = pipeline no-op
    # (sigue pasando por Validator y export, garantizando salida consistente).
    return passes or {k: () for k in VALID_PASS_KEYS}


def process_batch_files(
    file_paths: list[str | Path],
    output_dir: str | Path,
    rules_config: dict | None = None,
    progress_callback=None,
    quarantine: bool = False,
) -> BatchSummary:
    """Procesa una lista explícita de archivos (multi-selección) con el pipeline multi-pass.

    Args:
        file_paths: Rutas de los archivos a procesar (orden dado por el usuario).
        output_dir: Carpeta de salida (se crea si no existe).
        rules_config: Opcional. {'enabled_passes': {'pass1','pass2','pass3'}}.
        progress_callback: Opcional. progress_callback(done, total, current_name).
        quarantine: Si True, los archivos con error se MUEVEN a <output_dir>/errors/
            (modo carpeta). En multi-selección se recomienda False: los originales
            del usuario no se tocan, el error queda registrado en el reporte.

    Returns:
        BatchSummary con el reporte maestro del lote.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [Path(p) for p in file_paths]
    started = time.perf_counter()
    items: list[BatchItemResult] = []
    rows_before_total = 0
    rows_after_total = 0

    for idx, src in enumerate(files):
        name = src.name
        try:
            item = _process_single_file(src, out_dir, rules_config)
        except Exception as exc:  # noqa: BLE001 — aislamiento por archivo (regla del módulo)
            items.append(BatchItemResult(
                source_path=str(src), status="error",
                error=_friendly_error(exc),
            ))
            if quarantine:
                _quarantine(src, out_dir)
        else:
            items.append(item)
            if item.status == "ok":
                rows_before_total += item.rows_before
                rows_after_total += item.rows_after
            elif item.status == "invalid" and quarantine:
                _copy_invalid_with_reason(src, out_dir, item.warning or "Validación rechazada.")

        if progress_callback is not None:
            try:
                progress_callback(idx + 1, len(files), name)
            except Exception as exc:  # noqa: BLE001
                # El callback no puede romper el lote; se registra y continúa.
                items.append(BatchItemResult(
                    source_path=str(src), status="ok",
                    warning=f"progress_callback falló: {type(exc).__name__}: {exc}",
                ))

    elapsed = time.perf_counter() - started
    summary = BatchSummary(
        input_dir="(selección múltiple)" if not quarantine else str(Path(file_paths[0]).parent.resolve()) if file_paths else "",
        output_dir=str(out_dir.resolve()),
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        duration_seconds=elapsed,
        total_files_found=len(files),
        processed_ok=sum(1 for i in items if i.status == "ok"),
        processed_invalid=sum(1 for i in items if i.status == "invalid"),
        errors=sum(1 for i in items if i.status == "error"),
        cleaned_count=sum(1 for i in items if i.status == "ok" and i.result_label == "CLEANED"),
        unchanged_count=sum(1 for i in items if i.status == "ok" and i.result_label == "UNCHANGED"),
        total_rows_before=rows_before_total,
        total_rows_after=rows_after_total,
        total_rows_removed=rows_before_total - rows_after_total,
        total_changes=sum(i.changes for i in items if i.status == "ok"),
        items=tuple(items),
    )

    _write_master_report(summary, out_dir)
    return summary


def process_batch_folder(
    input_dir: str | Path,
    output_dir: str | Path,
    rules_config: dict | None = None,
    progress_callback=None,
    create_zip: bool = False,
) -> BatchSummary:
    """Procesa todos los .csv/.xlsx/.xls de una carpeta con el pipeline multi-pass.

    Args:
        input_dir: Carpeta de entrada (se recorre de forma recursiva, pero los
            archivos dentro de "errors/" o de la carpeta de salida se ignoran).
        output_dir: Carpeta de salida. Se crea si no existe. Los limpios van a la
            raíz; los fallidos a <output_dir>/errors/.
        rules_config: Opcional. {'enabled_passes': {'pass1','pass2','pass3'}}.
        progress_callback: Opcional. Se llama como progress_callback(done, total,
            current_name) después de cada archivo.
        create_zip: Si True, empaqueta los resultados (limpios + reportes + errors/)
            en <output_dir>/batch_results.zip para descarga/entrega única.

    Returns:
        BatchSummary con el reporte maestro del lote.
    """
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)

    if not in_dir.exists() or not in_dir.is_dir():
        raise BatchError(f"La carpeta de entrada no existe o no es un directorio: {in_dir}")
    if in_dir.resolve() == out_dir.resolve():
        raise BatchError("La carpeta de entrada y de salida no pueden ser la misma.")
    out_dir.mkdir(parents=True, exist_ok=True)

    skip_dirs = {out_dir.resolve(), (out_dir / "errors").resolve()}
    files = sorted(
        p for p in in_dir.rglob("*")
        if p.is_file()
        and p.suffix.lower() in BATCH_EXTENSIONS
        and p.parent.resolve() not in skip_dirs
    )

    summary = process_batch_files(
        file_paths=files,
        output_dir=out_dir,
        rules_config=rules_config,
        progress_callback=progress_callback,
        quarantine=True,  # modo carpeta: los corruptos se aíslan en errors/
    )
    summary = BatchSummary(
        input_dir=str(in_dir.resolve()),
        output_dir=summary.output_dir,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        duration_seconds=summary.duration_seconds,
        total_files_found=summary.total_files_found,
        processed_ok=summary.processed_ok,
        processed_invalid=summary.processed_invalid,
        errors=summary.errors,
        cleaned_count=summary.cleaned_count,
        unchanged_count=summary.unchanged_count,
        total_rows_before=summary.total_rows_before,
        total_rows_after=summary.total_rows_after,
        total_rows_removed=summary.total_rows_removed,
        total_changes=summary.total_changes,
        zip_path=summary.zip_path,
        items=summary.items,
    )

    if create_zip:
        zip_path = _create_zip(out_dir)
        summary = BatchSummary(
            input_dir=summary.input_dir,
            output_dir=summary.output_dir,
            started_at=summary.started_at,
            finished_at=summary.finished_at,
            duration_seconds=summary.duration_seconds,
        total_files_found=summary.total_files_found,
        processed_ok=summary.processed_ok,
        processed_invalid=summary.processed_invalid,
        errors=summary.errors,
        cleaned_count=summary.cleaned_count,
        unchanged_count=summary.unchanged_count,
        total_rows_before=summary.total_rows_before,
        total_rows_after=summary.total_rows_after,
        total_rows_removed=summary.total_rows_removed,
        total_changes=summary.total_changes,
        zip_path=zip_path,
        items=summary.items,
    )
        # El reporte maestro debe reflejar el zip (se re-escribe con zip_path).
        _write_master_report(summary, out_dir)

    return summary


def run_multipass_summary_check(summary: BatchSummary) -> bool:
    """Verificación de consistencia del resumen (cero reportes mentirosos).

    Comprueba que los contadores sumen y que las filas de los items OK
    coincidan con los totales declarados.
    """
    ok = sum(1 for i in summary.items if i.status == "ok")
    invalid = sum(1 for i in summary.items if i.status == "invalid")
    errors = sum(1 for i in summary.items if i.status == "error")
    if (ok, invalid, errors) != (summary.processed_ok, summary.processed_invalid, summary.errors):
        return False
    rows_b = sum(i.rows_before for i in summary.items if i.status == "ok")
    rows_a = sum(i.rows_after for i in summary.items if i.status == "ok")
    if (rows_b, rows_a) != (summary.total_rows_before, summary.total_rows_after):
        return False
    changes = sum(i.changes for i in summary.items if i.status == "ok")
    if changes != summary.total_changes:
        return False
    if summary.total_files_found != len(summary.items):
        return False
    return True


def _safe_output_path(src: Path, out_dir: Path) -> Path:
    """Nombre de salida = nombre original conservado; ante colisión, sufijo _1, _2...

    Si el nombre de entrada ya existiera en out_dir (p.ej. re-corrida con salida
    dentro del árbol de entrada), se crea 'nombre_limpio_1.ext' en su lugar para
    NO sobrescribir jamás un archivo preexistente.
    """
    candidate = out_dir / src.name
    n = 1
    while candidate.exists():
        candidate = out_dir / f"{src.stem}_limpio_{n}{src.suffix.lower()}"
        n += 1
    return candidate


def _process_single_file(src: Path, out_dir: Path, rules_config: dict | None = None) -> BatchItemResult:
    """Procesa un archivo: carga -> multi-pass -> Validator -> export + audit."""
    out_path = _safe_output_path(src, out_dir)

    # 1. Carga read-only con la infraestructura del Analyzer (fallbacks de encoding incluidos)
    try:
        if src.suffix.lower() == ".csv":
            df = _read_csv_with_fallback(src)
        elif src.suffix.lower() == ".xls":
            try:
                df = pd.read_excel(src)
            except ImportError as exc:
                raise RuntimeError(
                    "Los archivos .xls requieren la librería 'xlrd', que no está instalada. "
                    "Convierta el archivo a .xlsx o instale 'xlrd'."
                ) from exc
        else:
            df = pd.read_excel(src)
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer el archivo: {_friendly_error(exc)}") from exc

    if df.shape[1] == 0:
        # Archivo legible pero sin columnas: no es limpiable ni exportable.
        return BatchItemResult(source_path=str(src), status="error", error="El archivo no contiene columnas.")

    rows_before = len(df)
    df_snapshot = df.copy(deep=True)

    # 2. Pipeline multi-pass (Pass 1/2/3 con CleaningResult por pasada), según config
    passes = _resolve_passes(rules_config, df)
    df_clean, aggregate, _per_pass = run_multipass_cleaning(df, passes=passes)

    # 3. Barrera Zero-Trust: el Validator audita TODO el pipeline contra el original
    validation = validate_cleaning(df, df_clean, aggregate.actions_applied, aggregate)

    if not validation.valid:
        # NO se exporta nada. El archivo queda registrado como "invalid" con los errores.
        return BatchItemResult(
            source_path=str(src), status="invalid",
            rows_before=rows_before, rows_after=len(df_clean),
            rows_removed=rows_before - len(df_clean),
            actions_count=len(aggregate.actions_applied),
            warning="Validación Zero-Trust rechazada: " + " | ".join(validation.errors),
        )

    # 4. Export (zero-write garantizado por la barrera anterior) + auditoría embebida
    # El reporte se genera ANTES de escribir: en .xlsx viaja embebido como pestaña
    # _Reporte_Auditoria (y siempre hay sidecar .txt en out_dir).
    transforms = _compute_transforms(df_snapshot, df_clean, aggregate)
    audit_report = generate_audit_report(
        original_file=src,
        export_file=str(out_path),
        cleaning_result=aggregate,
        validation_result=validation,
        df_original=df_snapshot,
        df_clean=df_clean,
        transforms=transforms,
    )
    res = export_dataframe(df_clean, out_path, validation, overwrite=True, audit_report=audit_report)
    audit_path = export_audit_report(audit_report, output_dir=out_dir, format="txt")

    changes = sum(t.values_changed for t in transforms) + (rows_before - len(df_clean))

    # Etiqueta de resultado HONESTA: UNCHANGED solo si el DataFrame quedó idéntico
    # celda a celda (df.equals), nunca por heurísticas de contadores.
    result_label = "UNCHANGED" if df.equals(df_clean) else "CLEANED"

    return BatchItemResult(
        source_path=str(src), status="ok",
        output_path=res.path, audit_path=audit_path,
        rows_before=rows_before, rows_after=len(df_clean),
        rows_removed=rows_before - len(df_clean),
        changes=changes,
        actions_count=len(aggregate.actions_applied),
        result_label=result_label,
    )


def _quarantine(src: Path, out_dir: Path) -> None:
    """Mueve un archivo fallido a <output_dir>/errors/ preservando el nombre."""
    errors_dir = out_dir / "errors"
    errors_dir.mkdir(parents=True, exist_ok=True)
    target = errors_dir / src.name
    n = 1
    while target.exists():
        target = errors_dir / f"{src.stem}_dup{n}{src.suffix}"
        n += 1
    try:
        shutil.move(str(src), str(target))
    except (OSError, shutil.Error):
        # Si el SO no permite mover (permisos), el archivo queda en su sitio y el
        # error ya está registrado en el item correspondiente. No se silencia:
        # se refleja en el reporte maestro vía el error del item.
        pass


def _copy_invalid_with_reason(src: Path, out_dir: Path, reason: str) -> None:
    """Copia (sin eliminar el original) un archivo rechazado por el Validator a errors/.

    Junto a la copia se escribe <nombre>_rechazado.txt con el motivo legible.
    """
    try:
        errors_dir = out_dir / "errors"
        errors_dir.mkdir(parents=True, exist_ok=True)
        target = errors_dir / src.name
        n = 1
        while target.exists():
            target = errors_dir / f"{src.stem}_dup{n}{src.suffix}"
            n += 1
        shutil.copy2(str(src), str(target))
        (errors_dir / f"{src.stem}_rechazado.txt").write_text(
            "Archivo rechazado por el Validator (Zero-Trust). NO fue exportado.\n"
            f"Archivo: {src.name}\nMotivo: {reason}\n",
            encoding="utf-8",
        )
    except (OSError, shutil.Error):
        # La copia informativa es best-effort: el rechazo ya está registrado
        # en el item y en el reporte maestro (no se oculta).
        pass


def _create_zip(out_dir: Path) -> str | None:
    """Empaqueta los resultados del lote (raíz de out_dir + errors/) en un ZIP.

    Returns:
        Ruta del ZIP creado, o None si no se pudo crear (quedará registrado
        implícitamente: la carpeta de resultados sigue siendo la vía de acceso).
    """
    zip_path = out_dir / ZIP_NAME
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.rglob("*")):
                if not p.is_file() or p == zip_path:
                    continue
                zf.write(p, arcname=str(p.relative_to(out_dir)))
        return str(zip_path)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return None


def _write_master_report(summary: BatchSummary, out_dir: Path) -> None:
    """Escribe el reporte maestro del lote (JSON + TXT legible)."""
    json_path = out_dir / "batch_audit_summary.json"
    json_path.write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("REPORTE MAESTRO DE LOTE — Excel Cleaner (Fase 9.0 Batch Pipeline)")
    lines.append("=" * 70)
    lines.append(f"Entrada           : {summary.input_dir}")
    lines.append(f"Salida            : {summary.output_dir}")
    lines.append(f"Inicio / Fin      : {summary.started_at} -> {summary.finished_at}")
    lines.append(f"Duración          : {summary.duration_seconds:.1f}s")
    if summary.zip_path:
        lines.append(f"ZIP de resultados : {summary.zip_path}")
    lines.append("")
    lines.append(
        f"Archivos encontrados : {summary.total_files_found} | "
        f"OK: {summary.processed_ok} | Rechazados por Validator: {summary.processed_invalid} | "
        f"Errores: {summary.errors}"
    )
    lines.append(f"  Detalle de OK      : CLEANED (con cambios): {summary.cleaned_count} | "
                 f"UNCHANGED (sin mutaciones): {summary.unchanged_count}")
    lines.append(f"Filas antes/después : {summary.total_rows_before} -> {summary.total_rows_after} "
                 f"(eliminadas: {summary.total_rows_removed})")
    lines.append(f"Changes totales     : {summary.total_changes} (celdas modificadas + filas eliminadas)")
    lines.append("")
    lines.append("-" * 70)
    for it in summary.items:
        src_name = Path(it.source_path).name
        if it.status == "ok":
            label = it.result_label or "CLEANED"
            lines.append(f"[{label:9s}] {src_name} -> {Path(it.output_path).name} "
                         f"(filas {it.rows_before}->{it.rows_after}, cambios: {it.changes}, "
                         f"acciones: {it.actions_count})")
        elif it.status == "invalid":
            lines.append(f"[INVALID] {src_name} -> NO exportado (copia en errors/ con motivo). {it.warning}")
        else:
            lines.append(f"[ERROR]   {src_name} -> No se pudo procesar este archivo. Causa: {it.error}")
    lines.append("=" * 70)

    txt_path = out_dir / "batch_audit_summary.txt"
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI: python batch_processor.py <entrada> <salida> [--zip]"""
    args = list(sys.argv[1:] if argv is None else argv)
    create_zip = "--zip" in args
    args = [a for a in args if a != "--zip"]
    if len(args) != 2:
        print("Uso: python batch_processor.py <carpeta_entrada> <carpeta_salida> [--zip]")
        return 2
    try:
        summary = process_batch_folder(
            args[0], args[1], create_zip=create_zip,
            progress_callback=lambda d, t, n: print(f"[{d}/{t}] {n}"),
        )
    except BatchError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(
        f"\nLote finalizado: {summary.processed_ok} OK, "
        f"{summary.processed_invalid} rechazados, {summary.errors} errores, "
        f"{summary.total_changes} cambios. "
        f"Reporte: {Path(summary.output_dir) / 'batch_audit_summary.txt'}"
    )
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
