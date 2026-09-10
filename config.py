"""config.py

Configuraciones globales y constantes del sistema Excel Cleaner.
"""

from __future__ import annotations

# Límite inicial de tamaño de archivo (1 GB)
MAX_FILE_SIZE_BYTES = 1024 * 1024 * 1024

# Versión comercial de la aplicación (fuente única de verdad).
# Consumida por: main.py (título de ventana), models.py (metadatos de auditoría)
# y documentación de soporte. Bump aquí al publicar una nueva versión.
APP_VERSION = "1.1.0"