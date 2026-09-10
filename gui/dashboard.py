import tkinter as tk
from tkinter import ttk


class Dashboard(ttk.Frame):
    def __init__(self, parent, callbacks):
        super().__init__(parent)
        self.callbacks = callbacks
        
        self.info_frame = ttk.LabelFrame(self, text="Resumen del Archivo")
        self.info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_file = ttk.Label(self.info_frame, text="Archivo: Ninguno")
        self.lbl_file.pack(anchor=tk.W, padx=5, pady=2)
        
        self.lbl_stats = ttk.Label(self.info_frame, text="Filas: 0 | Columnas: 0")
        self.lbl_stats.pack(anchor=tk.W, padx=5, pady=2)
        
        self.lbl_status = ttk.Label(self.info_frame, text="Estado: Esperando archivo...", font=("Helvetica", 9, "bold"))
        self.lbl_status.pack(anchor=tk.W, padx=5, pady=2)

        self.btn_frame = ttk.Frame(self)
        self.btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.btn_load = ttk.Button(self.btn_frame, text="1. Seleccionar", command=self.callbacks.get("on_load"))
        self.btn_load.pack(side=tk.LEFT, padx=5)
        
        self.btn_analyze = ttk.Button(self.btn_frame, text="2. Analizar Base", command=self.callbacks.get("on_analyze"), state=tk.DISABLED)
        self.btn_analyze.pack(side=tk.LEFT, padx=5)

        self.btn_ai = ttk.Button(self.btn_frame, text="✦ Consultar IA", command=self.callbacks.get("on_ai_analyze"), state=tk.DISABLED)
        self.btn_ai.pack(side=tk.LEFT, padx=5)
        
        self.btn_clean = ttk.Button(self.btn_frame, text="3. Aplicar Limpieza", command=self.callbacks.get("on_clean"), state=tk.DISABLED)
        self.btn_clean.pack(side=tk.LEFT, padx=5)
        
        self.btn_export = ttk.Button(self.btn_frame, text="4. Exportar", command=self.callbacks.get("on_export"), state=tk.DISABLED)
        self.btn_export.pack(side=tk.LEFT, padx=5)
        
        self.btn_batch = ttk.Button(self.btn_frame, text="📁 Batch (Carpeta)", command=self.callbacks.get("on_batch"))
        self.btn_batch.pack(side=tk.LEFT, padx=5)

        self.btn_custom = ttk.Button(self.btn_frame, text="⚙ Acciones personalizadas", command=self.callbacks.get("on_custom"))
        self.btn_custom.pack(side=tk.LEFT, padx=5)

        # ---- Configuración del pipeline para BATCH (checklist del usuario) ----
        self.batch_cfg_frame = ttk.LabelFrame(self, text="Batch: pases a aplicar")
        self.batch_cfg_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.var_pass1 = tk.BooleanVar(value=True)
        self.var_pass2 = tk.BooleanVar(value=True)
        self.var_pass3 = tk.BooleanVar(value=True)
        self.var_zip = tk.BooleanVar(value=False)

        ttk.Checkbutton(self.batch_cfg_frame, text="Pass 1: Estructural",
                        variable=self.var_pass1).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(self.batch_cfg_frame, text="Pass 2: Fechas/Números",
                        variable=self.var_pass2).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(self.batch_cfg_frame, text="Pass 3: Duplicados/Nulos",
                        variable=self.var_pass3).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(self.batch_cfg_frame, text="Crear ZIP de resultados",
                        variable=self.var_zip).pack(side=tk.LEFT, padx=15)
        
        self.btn_reset = ttk.Button(self.btn_frame, text="Nuevo Archivo", command=self.callbacks.get("on_reset"))
        self.btn_reset.pack(side=tk.RIGHT, padx=5)

        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, padx=10, pady=5)

    def update_info(self, filename, rows, cols):
        self.lbl_file.config(text=f"Archivo: {filename}")
        self.lbl_stats.config(text=f"Filas: {rows} | Columnas: {cols}")

    def update_status(self, text):
        self.lbl_status.config(text=f"Estado: {text}")

    def set_buttons_state(self, load=None, analyze=None, ai=None, clean=None, export=None, batch=None):
        if load is not None: self.btn_load.config(state=load)
        if analyze is not None: self.btn_analyze.config(state=analyze)
        if ai is not None: self.btn_ai.config(state=ai)
        if clean is not None: self.btn_clean.config(state=clean)
        if export is not None: self.btn_export.config(state=export)
        if batch is not None: self.btn_batch.config(state=batch)

    def set_progress_value(self, pct):
        """Progreso determinista por archivo (modo batch): detiene la animación y fija %."""
        self.progress.stop()
        self.progress_var.set(max(0, min(100, float(pct))))

    def get_batch_config(self) -> dict:
        """Checklist del usuario -> rules_config para el motor de lotes."""
        enabled = set()
        if self.var_pass1.get(): enabled.add("pass1")
        if self.var_pass2.get(): enabled.add("pass2")
        if self.var_pass3.get(): enabled.add("pass3")
        return {"enabled_passes": enabled}

    def is_batch_zip(self) -> bool:
        return self.var_zip.get()