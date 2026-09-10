import tkinter as tk
from tkinter import ttk

from models import CleaningAction


class IssuesPanel(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="Problemas Detectados / Acciones")
        
        self.canvas = tk.Canvas(self)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.scrollbar.pack(side="right", fill="y")
        
        self.action_vars = []
        self.current_actions = []

    def populate(self, actions: tuple[CleaningAction, ...]):
        self.clear()
        self.current_actions = list(actions)
        
        if not actions:
            ttk.Label(self.scrollable_frame, text="No se detectaron problemas.").pack(anchor=tk.W)
            return

        for idx, act in enumerate(self.current_actions):
            var = tk.BooleanVar(value=act.approved)
            self.action_vars.append(var)
            
            text = f"[{act.action_id}] {act.description} (Col: {act.column or 'N/A'})"
            chk = ttk.Checkbutton(self.scrollable_frame, text=text, variable=var)
            chk.pack(anchor=tk.W, padx=5, pady=2)

    def get_approved_actions(self) -> tuple[CleaningAction, ...]:
        # Reconstrucción FIEL: se preservan parameters y source (p.ej. dayfirst de la IA
        # o locale de normalizar_numerico). Perderlos invalidaría la acción ante el
        # Validator y activaría parámetros incorrectos en el Cleaner.
        updated_actions = []
        for idx, act in enumerate(self.current_actions):
            # Acciones deshabilitadas no tienen una variable asociada (populate):
            # se reportan tal cual fueron creadas, con su aprobación original.
            var = self.action_vars[idx] if idx < len(self.action_vars) else None
            updated_actions.append(
                CleaningAction(
                    action_id=act.action_id,
                    column=act.column,
                    description=act.description,
                    approved=act.approved if var is None else var.get(),
                    parameters=dict(act.parameters),
                    source=act.source,
                )
            )
        return tuple(updated_actions)

    def clear(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.action_vars.clear()
        self.current_actions.clear()