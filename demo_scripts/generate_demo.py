"""Genera la muestra de portfolio (demo) usando el motor REAL de Excel Cleaner.

Pasos:
1) Crea demo_portfolio/1_original_sucio.xlsx  (dataset mini-B2B genuinamente sucio).
2) Ejecuta el pipeline: Analyzer (lectura) -> acciones propuestas -> APROBACION
   -> Cleaner -> Validator -> Exporter con hoja de auditoria + sidecar TXT.
3) Deja en demo_portfolio/:
   - 2_resultado_limpio.xlsx        (hoja "Datos" + hoja "_Reporte_Auditoria")
   - 3_reporte_auditoria.txt        (resumen ejecutivo de auditoria, español)
   - 4_reporte_auditoria_en.txt     (mismo reporte en inglés, clientes intl.)
   - 2_resultado_limpio_audit_report.html (certificado imprimible a PDF)

Nunca pisa archivos de usuario: todo sale dentro de demo_portfolio/.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from analyzer import build_file_info, load_dataframe
from cleaner import clean_dataframe
from exporter import export_audit_report, export_dataframe, generate_audit_report
from models import CleaningAction, CleaningResult
from validators import validate_cleaning

DEMO = ROOT / "demo_portfolio"
DIRTY = DEMO / "1_original_sucio.xlsx"
CLEAN = DEMO / "2_resultado_limpio.xlsx"
TXT = DEMO / "3_reporte_auditoria.txt"
TXT_EN = DEMO / "4_reporte_auditoria_en.txt"


def build_dirty_workbook() -> None:
    """Dataset mini-B2B: espacios invisibles, N/A-null, montos US/EU, fechas DD/MM, duplicados post-trim."""
    rows = [
        # Nombre Completo      Email                Fecha Contrato   Monto          Estado       Ciudad
        ["  Ana Silva  ", " ANA@mail.com ", "15/03/2025", "$1,250.50", "N/A", "  Salta "],
        ["Luis Gomez", "luis@mail.com", "02/04/2025", "1.250,50", "Activo", "Cba"],
        [" Carla Diaz ", "carla@mail.com", "2025-05-10", "US$ 900,00", "null", "Rosario"],
        ["Juan Perez", "juan@mail.com", "31/01/2025", "(450,00)", "-", "Mendoza"],
        ["Maria Lopez", " maria@mail.com ", "10/12/2024", "$ 2.000,00", "None", "  Mendoza"],
        ["Sofia Ruiz", "sofia@mail.com", "05/06/2025", "1.250,50", "sin dato", "Tucuman"],
        ["  Ana Silva  ", " ANA@mail.com ", "15/03/2025", "$1,250.50", "N/A", "  Salta "],
        ["Pedro Sosa", "pedro@mail.com", "n/a", "3.999,99", "Activo", "Salta"],
    ]
    df = pd.DataFrame(rows, columns=[
        "Nombre Completo", "Email", "Fecha Contrato", "Monto", "Estado", "Ciudad"])
    # Fila totalmente vacia (basura estructural)
    df.loc[len(df)] = [None] * len(df.columns)
    DEMO.mkdir(exist_ok=True)
    if DIRTY.exists():
        DIRTY.unlink()  # es un artefacto generado del demo, regenerable
    df.to_excel(DIRTY, index=False)
    print(f"[1/3] Dataset sucio generado: {DIRTY.name} ({len(df)} filas sucias)")


def main() -> int:
    # Limpieza de artefactos previos DEL PROPIO DEMO (todos dentro de demo_portfolio/).
    DEMO.mkdir(exist_ok=True)
    for stale in (CLEAN, TXT, TXT_EN, *DEMO.glob("*_audit_report.txt"),
                  *DEMO.glob("*_audit_report.html")):
        if stale.exists():
            stale.unlink()

    build_dirty_workbook()

    # 1. El motor lee el archivo con el Analyzer (mismo camino que la GUI)
    file_info = build_file_info(DIRTY)
    df = load_dataframe(file_info)
    print(f"[Analyzer] {len(df)} filas x {len(df.columns)} columnas: {list(df.columns)}")

    # 2. Acciones propuestas por el motor (la IA/humano las ve como PENDIENTES)
    proposals = [
        CleaningAction("eliminar_filas_vacias", None, "", approved=False),
        CleaningAction("trim_espacios", "Nombre Completo", "", approved=False),
        CleaningAction("trim_espacios", "Email", "", approved=False),
        CleaningAction("trim_espacios", "Ciudad", "", approved=False),
        CleaningAction("convertir_basura_a_nulo", "Estado", "", approved=False),
        CleaningAction("normalizar_numerico", "Monto", "", approved=False,
                       parameters={"locale": "auto"}),
        CleaningAction("normalizar_fechas", "Fecha Contrato", "", approved=False,
                       parameters={"dayfirst": True}),
        CleaningAction("eliminar_duplicados_por_columna", "Email", "", approved=False,
                       parameters={"subset_columns": ["Email"], "keep": "first"}),
    ]

    # 3. APROBACION HUMANA: sin este paso nada se ejecuta (Zero-Trust)
    approved = tuple(
        CleaningAction(p.action_id, p.column, p.description, approved=True, parameters=p.parameters)
        for p in proposals
    )
    print(f"[Aprobacion] {len(approved)} acciones aprobadas manualmente")

    # 4. Cleaner determinista + Validator espejo
    df_clean, result = clean_dataframe(df, approved)
    validation = validate_cleaning(df, df_clean, approved, result)
    if not validation.valid:
        print("VALIDACION FALLO:", validation.errors)
        return 1
    print(f"[Cleaner+Validator] Filas {result.rows_before} -> {result.rows_after} | "
          f"Nulos creados: {sum(1 for _ in result.warnings)} warnings | VALIDACION: APROBADA")

    # 5. Exporter: reporte de auditoria ANTES de escribir -> hoja embebida + sidecar.
    #    Cero escritura sin validacion (barrera Zero-Trust intacta).
    #    Para el portfolio generamos: TXT (español), HTML (inglés, certificado visual),
    #    y la pestaña embebida _Reporte_Auditoria dentro del XLSX.
    report_es = generate_audit_report(DIRTY, CLEAN, result, validation, df, df_clean, language="es")
    report_en = generate_audit_report(DIRTY, CLEAN, result, validation, df, df_clean, language="en")

    # XLSX con pestaña embebida (usamos el reporte en español por defecto)
    export_dataframe(df_clean, CLEAN, validation, audit_report=report_es)

    # Sidecar TXT en español
    generated_tx = export_audit_report(report_es, DEMO, format="txt")
    shutil.move(generated_tx, TXT)

    # Sidecar TXT en inglés (portfolio bilingüe para clientes internacionales)
    generated_tx_en = export_audit_report(report_en, DEMO, format="txt")
    shutil.move(generated_tx_en, TXT_EN)

    # Sidecar HTML en inglés (certificado tipo PDF para Standard/Premium)
    html_path = Path(export_audit_report(report_en, DEMO, format="html"))

    assert CLEAN.exists() and TXT.exists() and html_path.exists() and TXT_EN.exists()
    print(f"[2/3] Resultado limpio: {CLEAN.name}")
    print(f"[3/3] Reportes de auditoria: {TXT.name} + {TXT_EN.name} + {html_path.name}")

    # Resumen para el portfolio
    print("\n=== RESUMEN DEMO ===")
    print(f"Filas: {result.rows_before} -> {result.rows_after}")
    for w in result.warnings:
        print(" -", w)
    print(f"\nPortfolio listo en {DEMO}:")
    for f in sorted(DEMO.iterdir()):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
