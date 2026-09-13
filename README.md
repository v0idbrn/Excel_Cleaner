# Excel Cleaner & Normalizer Engine (Zero-Cloud Edition)

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/)
[![Automated Data Sanitization](https://img.shields.io/badge/category-automated%20data%20sanitization-brightgreen.svg)](https://github.com/v0idbrn/Excel_Cleaner)
[![License](https://img.shields.io/badge/license-permissive-lightgrey.svg)](LICENSE)

> **Motor local de sanización, normalización de encodings, eliminación de duplicados y formateo determinista de planillas Excel y CSV.**

---

## Resumen ejecutivo

Excel Cleaner es un motor de limpieza de datos **100% local**, diseñado para procesar planillas crudas y heterogéneas provenientes de clientes B2B sin depender de servicios en la nube ni exponer información sensible.

El núcleo del sistema se basa en un **pipeline determinista**:

`Carga → Análisis estático → (IA opcional local) → Aprobación humana → Limpieza determinista → Validación de integridad (Zero-Trust) → Exportación auditada`.

- No se envían datos a servidores externos.
- Cada transformación se valida antes de exportar.
- Cada ejecución genera un **reporte de auditoría** que certifica qué se hizo, cuándo y con qué resultado.

---

## Características principales

### Carga robusta y defensiva

- **CSV**: soporte para UTF-8, UTF-8 con BOM, CP1252, Latin-1 y delimitadores comunes (`,`, `;`, tab, `|`).
- **XLSX / XLS**: apertura de hojas individuales o múltiples hojas, con manejo de headers vacíos, duplicados y codificaciones heterogéneas.
- **Validación previa al procesamiento**: archivo no encontrado, carpeta en lugar de archivo, tamaño 0 bytes, extensión no soportada y tamaño superior a un límite configurado.

### Detección de problemas (Analyzer, solo lectura)

El motor analiza la estructura sin modificar el archivo original e indica, entre otras:

- Filas y columnas vacías.
- Valores faltantes.
- Registros duplicados exactos y posibles duplicados.
- Espacios vacíos a los lados, inconsistencias de mayúsculas/minúsculas, strings vacíos y números almacenados como texto.
- Valores atípicos basados en rango intercuartílico.
- Fechas inconsistentes, correos electrónicos sospechosos y patrones de teléfono sospechosos.

### Limpieza determinista (Cleaner)

Las acciones están diseñadas para ser **reproducibles y revisables**, entre ellas:

- Trim y limpieza de espacios y caracteres basura.
- Normalización de mayúsculas/minúsculas con formato parametrizable.
- Normalización de fechas hacia formato estándar (ISO 8601 `YYYY-MM-DD`), con soporte para ambigüedad regional mediante `dayfirst`.
- Normalización numérica y monetaria con soporte locale-aware (EE. UU. / Europa), remoción de símbolos de moneda y manejo de negativos en formato contable entre paréntesis.
- Manejo ordenado de valores no parseables: se convierten a nulos seguros con registro de advertencias, en lugar de romper el proceso.

### Barrera Zero-Trust (Validator)

Antes de exportar, un validador verifica las transformaciones ejecutadas y bloquea:

- Mutaciones no autorizadas respecto a lo aprobado.
- Pérdida de filas/columnas no esperada.
- Cambios de valores no contemplados en la acción ejecutada.

### Exportación auditada (Exporter)

- Escritura cero en caso de validación inválida.
- Generación de reporte de auditoría con:
  - archivo origen,
  - timestamp,
  - filas iniciales vs. finales,
  - eliminaciones de filas vacías/duplicados,
  - acciones ejecutadas,
  - transformaciones por columna,
  - advertencias,
  - resultado de validación.

- El reporte puede entregarse en formato independiente y, si corresponde, embebido como pestaña adicional en el archivo de salida.

### Privacidad Zero-Cloud

- Los archivos permanecen en la máquina local.
- La inspección de IA, cuando se utiliza, se realiza sobre **metadatos estructurados**, sin exponer valores crudos de celdas sensibles.
- Las recomendaciones de IA son **propuestas** que deben ser aprobadas por el usuario antes de ejecutarse.
- Si no hay modelo local disponible, el motor continúa operando sin depender de él.

---

## Instalación

### Requisitos

- Python 3.14+ recomendado.
- Entorno virtual local.

### Pasos

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate        # Unix-like
pip install -r requirements.txt
```

Dependencias principales del proyecto (confirmar con `requirements.txt`):

- pandas
- numpy
- openpyxl
- requests (solo si se utiliza integración externa/opcional)

---

## Uso rápido

### 1. Como aplicación gráfica

```bash
python main.py
```

Flujo típico:

1. Abrir archivo Excel/CSV.
2. Ejecutar análisis.
3. Revisar problemas detectados.
4. Aprobar acciones deseadas.
5. Ejecutar limpieza.
6. Validar integridad.
7. Exportar archivo limpio + reporte de auditoría.

### 2. Como módulo / script

Puedes usar los componentes directamente según tu caso:

- Cargar y analizar datos.
- Aplicar limpiezas deterministas.
- Validar resultados.
- Exportar con trazabilidad.

ejemplo conceptual:

```python
from pathlib import Path

from analyzer import load_dataframe, analyze_dataframe
from cleaner import run_approved_cleaning
from validators import validate_cleaning
from exporter import export_clean_dataframe, export_audit_report

# 1. Carga
df, info = load_dataframe(Path("datos_cliente.csv"))

# 2. Análisis
issues = analyze_dataframe(df)

# 3. Selección manual de acciones (simplificado)
approved_actions = [...]

# 4. Limpieza
clean_result = run_approved_cleaning(df, approved_actions)

# 5. Validación
validation = validate_cleaning(df, clean_result.dataframe, approved_actions)

# 6. Exportación
export_path = Path("salida_limpias.xlsx")
export_clean_dataframe(clean_result.dataframe, export_path, validation)
export_audit_report(export_path, clean_result, validation, df, clean_result.dataframe)
```

> Importante: los nombres exactos de funciones/clases dependen de la API actual del proyecto. Revisar los módulos `analyzer`, `cleaner`, `validators` y `exporter` antes de integrar.

---

## Procesamiento por lotes

Para trabajar sobre carpetas completas, el proyecto provee procesamiento por lotes con:

- Recorrido de múltiples archivos.
- Aislamiento de errores por archivo (un archivo problemático no detiene el lote completo).
- Registro individual por archivo.
- Reporte global del lote.
- Clasificación de resultado por archivo (ejemplo: limpiado / sin cambios / en quarentena).

---

## Para qué sirve en un contexto B2B

- Recibir planillas de clientes sin saber exactamente qué formato o suciedad tendrán.
- Normalizar columnas críticas (fechas, montos, textos, identificadores).
- Quitar duplicados por clave (email, DNI, SKU, teléfono, etc.).
- Entregar el archivo limpio y un comprobante de lo realizado.
- Mantener el archivo original intacto y sin exposición externa.

---

## Limitaciones conocidas

- Es una herramienta de sanitización y formato, no un sistema de enriquecimiento de datos ni un generador de contenido empresarial.
- Las transformaciones son deterministas y parametrizadas; el motor no debe usarse para adivinar cambios en datos ambiguos sin revisión.
- La detección de problemas no reemplaza la revisión humana en casos sensibles o críticos.
- Algunas funcionalidades avanzadas pueden requerir configuración o aprobación manual según el archivo.

---

## Estado del proyecto

Proyecto Open Source / Permissive, enfocado en:

- privacidad local;
- reproducibilidad de la limpieza;
- trazabilidad por ejecución;
- integración segura con IA opcional local.

---

## Contribución y mantenimiento

Este repositorio está pensado para usarse, auditar y mantener como pieza de infraestructura de limpieza de datos. Se recomienda:

- mantener el archivo original intacto;
- conservar el reporte de auditoría por entrega;
- revisar el pipeline antes de automatizar flujos críticos.

---

*El presente motor está diseñado para trabajar sobre datos locales sin transmitirlos a la nube.*
