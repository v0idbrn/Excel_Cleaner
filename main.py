"""Punto de entrada de Excel Cleaner.

Instala un manejador de errores global ANTES de crear la app, de forma que los
builds windowed (--noconsole / console=False) nunca fallen en silencio.
`tk.report_callback_exception` captura excepciones en callbacks Tkinter sin el
consola de depuración (la ventana en rojo de depuración). El manejador ademas
escribe un registro textual (%APPDATA%\\ExcelCleaner\\crash.log) visible para
soporte, y deja registro para ayuda posterior cuando sea posible.
"""

from __future__ import annotations

import datetime
import os
import sys
import traceback as _traceback

import tkinter as tk
from pathlib import Path

import config
from gui.app import ExcelCleanerApp

# Branding comercial de la ventana principal.
APP_TITLE = "Excel Cleaner Pro"


def _resource_path(relative: str) -> Path:
    """Ruta absoluta a recurso estatico (icono, plantillas), compatible con PyInstaller y dev.

    En builds windowed, PyInstaller extrae todo a sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / relative if base else Path(__file__).resolve().parent / relative


def _crash_log_dir() -> Path:
    """Directorio log (visible para el usuario), preferiblemente en %APPDATA%.

    Si no es accesible (entorno cerrado / sin APPDATA), cae a un directorio
    cercano al ejecutable (builds windowed) o al directorio actual.
    """
    candidates: list[Path] = []
    # 1. logs de aplicacion en directorio de datos del usuario (Windows)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates.append(Path(appdata) / "ExcelCleaner")

    # 2. menos preferible: cercano al ejecutable o al cwd (para if frustrado)
    main_file = Path(sys.argv[0]).resolve() if sys.argv[0] else Path.cwd()
    candidates.append(main_file.parent / "logs")
    candidates.append(Path.cwd() / "logs")

    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            return c
        except OSError:
            continue

    # ultimo recurso: documentar que no se pudo escribir log y dejar fallback por nombre
    Path(os.path.abspath(".")).mkdir(parents=True, exist_ok=True)
    return Path(os.path.abspath(".")) / "logs"


def _write_crash_log(exception_type, exception_value, traceback_object):
    """Escribe un crash.log textual con stacktrace y contexto del proceso."""
    log_dir = _crash_log_dir()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Limpia el nombre para su uso como nombre de archivo (path-operstional)
    safe_ts = ts.replace(":", "_")
    log_path = log_dir / f"crash_{safe_ts}.log"

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("EXCEL CLEANER - INFORME DE FALLA (crash)")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Fecha/Hora (UTC): {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    lines.append(f"Tipo de excepcion: {exception_type.__name__}")
    lines.append(f"Mensaje de excepcion: {exception_value}")
    lines.append("")
    lines.append("--- Datos de entorno ---")
    lines.append(f"Python: {sys.version.splitlines()[0].strip()}")
    lines.append(f"Plataforma: {sys.platform or 'desconocido'}")
    lines.append(f"Directorio ejecutable (argv[0]): {sys.argv[0]!r}")
    lines.append(f"Tipo de proceso (console/windowed): "
                   f"{'console' if getattr(sys, '_MEIPASS', None) else 'desconocido'}")
    lines.append("")
    lines.append("--- Traceback ---")
    lines.append("")
    lines.extend(_traceback.format_exception(exception_type, exception_value, traceback_object))
    lines.append("")
    lines.append("=" * 72)

    try:
        log_text = "\n".join(lines)
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(log_text)
        return log_path, "ok"
    except OSError as e:
        # Si el log mismo falla, intentar con stderr y dignificar sin romper todo
        short = f"No se pudo escribir log en {log_dir}: {e}"
        print(short, file=sys.stderr, flush=True)
        return log_path, f"write_failed: {short}"


def _on_tk_crash(
    _unused_root: object,
    exception_type: type[BaseException],
    exception_value: BaseException,
    traceback_object,
) -> None:
    """Callback de tk.report_callback_exception.

    Imprime una advertencia visible para el usuario y escribe un log. Evita
    fallar sola; no re-lanza.
    """
    try:
        exc_repr = f"{exception_type.__name__}: {exception_value}"
        log_path, status = _write_crash_log(exception_type, exception_value, traceback_object)

        msg = (
            "Ha ocurrido un problema inesperado.\n"
            "El programa intentara continuar.\n"
            f"Tipo de error: {exc_repr}\n"
            f"Archivo de registro: {log_path}\n"
        )
        if status.startswith("write_failed"):
            msg += "ADVERTENCIA: no se pudo escribir el archivo de registro.\n"

        try:
            # mostrar el dialogo lo antes posible; no bloquear con traceback completo
            tk.messagebox.showerror(
                "Error inesperado de Excel Cleaner",
                msg,
            )
        except Exception:
            # Si incluso Tk trabajo lanza (l loop muy dañado), al menos intentar log.
            pass
    except Exception:
        # El manejador en si no debe propagar al loop principal.
        try:
            print(
                "ERROR: excepcion en handler de crash (non-recoverable)",
                "falling back to stderr",
                exc_info=True,
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass


def create_window() -> tk.Tk:
    """Crea la ventana principal con branding comercial (título + icono)."""
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("800x600")
    root.minsize(600, 400)

    # Icono comercial (icono.ico) si existe, sin romper si falta.
    # PyInstaller windowed (--noconsole) no tiene el icono .exe todavia en este hook
    # de arranque; el build define el icono en excel_cleaner.spec.
    icon_path = _resource_path("assets/icono.ico")
    if icon_path.exists():
        try:
            root.iconbitmap(str(icon_path.resolve()))
        except tk.TclError:
            pass  # sin envoltura fs, no mostrar dialogo de error

    # Instalar manejador global ANTES de any UI
    root.report_callback_exception = _on_tk_crash
    return root


def main():
    root = create_window()
    _ = ExcelCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()