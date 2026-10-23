"""
pipeline_cruces
================
Pipeline modular para extraer datos de tráfico de videos de cruces viales
(conteos, movimientos, semáforo y filas) con el fin de validar simulaciones en SUMO.

Cada cruce se procesa de forma independiente y genera, en su carpeta
(p. ej. gdl/oxxo/), exactamente los 14 archivos del "contrato" de salida.
"""

__version__ = "1.0.0"

# Lista oficial de archivos del contrato (en el orden del protocolo).
ARCHIVOS_CONTRATO = [
    "accesos.csv",
    "movimientos.csv",
    "diagrama.png",
    "eventos.csv",
    "conteos_5min.csv",
    "tau_10min.csv",
    "proporciones_vuelta.csv",
    "semaforo_eventos.csv",
    "filas.csv",
    "videos.csv",
    "ventanas_descartadas.csv",
    "conteo_manual.csv",
    "validacion.csv",
    "notas.md",
]

MOVIMIENTOS_VALIDOS = ("izquierda", "frente", "derecha", "U")
MOVIMIENTO_DESCONOCIDO = "desconocido"
