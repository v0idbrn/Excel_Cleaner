"""config.py

Configuraciones globales y constantes del sistema Excel Cleaner.
"""

from __future__ import annotations

# Límite inicial de tamaño de archivo (1 GB)
MAX_FILE_SIZE_BYTES = 1024 * 1024 * 1024

# ---- Integración con IA local (Ollama) — fuente única de verdad ----
# Consumidos por ai.py. Solo se contacta un endpoint LOCAL; nunca se envían
# datos de celdas (ai.py solo trasmite metadatos estructurales).
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_DEFAULT_MODEL = "phi4-mini:latest"
# Timeout del request a Ollama en segundos.
AI_REQUEST_TIMEOUT = 30

# Versión comercial de la aplicación (fuente única de verdad).
# Consumida por: main.py (título de ventana), models.py (metadatos de auditoría)
# y documentación de soporte. Bump aquí al publicar una nueva versión.
APP_VERSION = "1.1.0"