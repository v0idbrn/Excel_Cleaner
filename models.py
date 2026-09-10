"""models.py

Estructuras de datos compartidas por todos los módulos de Excel Cleaner.

Este archivo NO contiene lógica de negocio: solo enums y dataclasses
que representan la información que circula entre analyzer.py, cleaner.py,
ai.py, validators.py, exporter.py y la GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import config


class FileType(str, Enum):
    """Formatos de archivo soportados en esta fase del proyecto."""
    CSV = "csv"
    XLSX = "xlsx"


class Severity(str, Enum):
    """Severidad de un problema detectado por el analyzer."""
    LOW = "BAJA"
    MEDIUM = "MEDIA"
    HIGH = "ALTA"


@dataclass(frozen=True, slots=True)
class FileInfo:
    """Metadatos del archivo seleccionado por el usuario, antes de analizarlo."""
    path: Path
    file_type: FileType
    size_bytes: int
    sheet_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)


@dataclass(frozen=True, slots=True)
class ColumnStats:
    """Estadísticas descriptivas de una columna (sin diagnóstico, solo hechos)."""
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    unique_count: int
    sample_values: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Issue:
    """Un problema concreto detectado por el analyzer."""
    category: str
    column: str | None
    severity: Severity
    description: str
    affected_count: int
    total_count: int
    examples: tuple[str, ...] = field(default_factory=tuple)
    recommendation: str = ""
    suggested_action: str | None = None

    @property
    def affected_ratio(self) -> float:
        if self.total_count == 0:
            return 0.0
        return round(self.affected_count / self.total_count, 4)


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    """Resultado completo del análisis determinista de un archivo/hoja."""
    file_info: FileInfo
    sheet_name: str | None
    row_count: int
    column_count: int
    column_stats: tuple[ColumnStats, ...]
    issues: tuple[Issue, ...]

    def issues_by_severity(self, severity: Severity) -> tuple[Issue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is severity)

    def summary_counts(self) -> dict[str, int]:
        """Resumen apto para mostrar en el dashboard de la GUI."""
        return {
            "filas": self.row_count,
            "columnas": self.column_count,
            "problemas_detectados": len(self.issues),
            "problemas_altos": len(self.issues_by_severity(Severity.HIGH)),
            "problemas_medios": len(self.issues_by_severity(Severity.MEDIUM)),
            "problemas_bajos": len(self.issues_by_severity(Severity.LOW)),
        }


@dataclass(slots=True)
class CleaningAction:
    """Una acción de limpieza propuesta.
    No es inmutable (frozen) para permitir a la GUI alternar el estado
    de aprobación directamente desde la interfaz.
    """
    action_id: str
    column: str | None
    description: str
    approved: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)
    source: str = "analyzer"


@dataclass(frozen=True, slots=True)
class CleaningResult:
    """Resultado de aplicar un conjunto de CleaningAction sobre un DataFrame."""
    actions_applied: tuple[CleaningAction, ...]
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    warnings: tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Resultado de validar un DataFrame limpio frente al original y las acciones aprobadas."""
    valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True, slots=True)
class AuditTransform:
    """Registro detallado de una transformación aplicada a una columna específica."""
    action_id: str
    column: str
    parameters: dict[str, Any]
    input_dtype: str
    output_dtype: str
    nulls_before: int
    nulls_after: int
    values_changed: int
    summary: str = ""


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Reporte de auditoría formal que acompaña al archivo exportado.

    Contiene el historial completo de la sesión de limpieza para propósitos
    de trazabilidad, auditoría y compliance.
    """
    
    # Identificación de la sesión
    export_timestamp: datetime
    original_file: str
    export_file: str

    # Métricas globales de la limpieza
    rows_before: int
    rows_after: int
    rows_removed: int
    columns_before: int
    columns_after: int

    # Resultado de la validación (Zero-Trust)
    validation_valid: bool
    validation_errors: tuple[str, ...]
    validation_warnings: tuple[str, ...]

    # Historial de acciones ejecutadas (solo las aprobadas y efectivamente aplicadas)
    actions_executed: tuple[CleaningAction, ...]

    # Detalles de transformación por columna
    transforms: tuple[AuditTransform, ...]

    # Advertencias del proceso de limpieza
    cleaning_warnings: tuple[str, ...]

    # Idioma del reporte. Valores admitidos: "es" (predeterminado) y "en".
    # Usado por _write_txt_report y _write_audit_sheet.
    language: str = "es"

    # Metadatos adicionales del sistema
    cleaner_version: str = config.APP_VERSION

    @property
    def is_valid(self) -> bool:
        """True si la barrera de validación Zero-Trust aprobó la limpieza."""
        return self.validation_valid

    def to_dict(self) -> dict[str, Any]:
        """Serialización JSON-safe del reporte (usada por _write_json_report)."""
        return {
            "export_timestamp": self.export_timestamp.isoformat(),
            "original_file": self.original_file,
            "export_file": self.export_file,
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "rows_removed": self.rows_removed,
            "columns_before": self.columns_before,
            "columns_after": self.columns_after,
            "validation_valid": self.validation_valid,
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
            "actions_executed": [
                {
                    "action_id": a.action_id,
                    "column": a.column,
                    "description": a.description,
                    "approved": bool(a.approved),
                    "parameters": dict(a.parameters),
                    "source": a.source,
                }
                for a in self.actions_executed
            ],
            "transforms": [
                {
                    "action_id": t.action_id,
                    "column": t.column,
                    "parameters": dict(t.parameters),
                    "input_dtype": t.input_dtype,
                    "output_dtype": t.output_dtype,
                    "nulls_before": t.nulls_before,
                    "nulls_after": t.nulls_after,
                    "values_changed": t.values_changed,
                    "summary": t.summary,
                }
                for t in self.transforms
            ],
            "cleaning_warnings": list(self.cleaning_warnings),
            "language": self.language,
            "cleaner_version": self.cleaner_version,
        }


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Resultado de la exportación a disco de un DataFrame validado."""
    success: bool
    path: str
    rows_exported: int
    columns_exported: int

@dataclass(frozen=True, slots=True)
class AIProposal:
    """Representa una propuesta de modificación generada por la IA."""
    action: str
    column: str | None
    reason: str
    confidence: float
    parameters: dict[str, Any] = field(default_factory=dict)
    source: str = "ai"

@dataclass(frozen=True, slots=True)
class AIResponse:
    """Respuesta estructurada validada del LLM."""
    proposals: tuple[AIProposal, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)