<!-- AUTO:INICIO (esta sección la regenera el pipeline; no editar) -->
# Notas del cruce: Cruce OXXO (`oxxo`)

- Última ejecución: 2026-10-23T02:23:08
- Pipeline: pipeline_cruces v1.0.0 · Python 3.13.12 · ultralytics 8.4.184
- Modelo de detección: `yolo11n.pt` (conf=0.25, iou=0.5, imgsz=960)
- Clases usadas: 2→auto, 3→moto, 5→autobus, 7→camion
- Tracker: `bytetrack_oclusion.yaml` · punto de referencia: base · frame_stride=1 · segundos_perdida=4.0 · revinculación={'activa': True, 'max_segundos': 2.5, 'max_distancia_px': 90}

## Calidad del seguimiento

- Vehículos en eventos.csv: **3140**
- Completos: 2044 (65.1%)
- Perdidos antes de salir (movimiento *desconocido*): 300 (9.6%)
- Sin acceso (solo se vio la salida): 796 (25.4%)
- Combinación acceso→salida no configurada: 0 (0.0%)

| Acceso | Vehículos | Perdidos | % perdidos |
|---|---:|---:|---:|
| N | 2344 | 300 | 12.8% |

## Videos procesados

- `oxxo_m.avi`: 7315.9 s, 107141 frames, 600.00 fps · revinculaciones=864 · IDs sin cruce de línea=8818 · cambios de semáforo=0

## Agregación

- Eventos usados en conteos: 2344 de 3140
- Eliminados por ventanas descartadas: 0 (0 ventanas)

## Semáforo y filas

- Semáforos evaluados por visión: ninguno (semaforo_eventos.csv vacío)
- El plan de fases completo NO se infiere automáticamente: se documenta manualmente.

<details><summary>Parámetros del tracker</summary>

```yaml
# ByteTrack ajustado para cruces con oclusiones (semáforo en primer plano,
# camiones pegados a la cámara). Basado en el bytetrack.yaml de ultralytics.
#
# Cambios respecto al default y por qué:
#   track_buffer 30 -> 120 : un ID "perdido" se conserva ~4 s (a 30 fps) esperando
#                            reaparecer. Es la palanca principal contra oclusiones.
#   track_low_thresh 0.1   : la 2a asociación de ByteTrack usa detecciones de baja
#                            confianza (vehículos parcialmente tapados) para no cortar IDs.
#   match_thresh 0.8 -> 0.9: acepta asociaciones con menor IoU (vehículo que reaparece
#                            desplazado tras la oclusión).
# Riesgo de subir mucho track_buffer: si dos vehículos cruzan el mismo punto el ID
# puede "saltar" de uno a otro. Revisar el video de depuración (--video-depuracion).
# Nota: ultralytics escala track_buffer por fps/30.
tracker_type: bytetrack
track_high_thresh: 0.25
track_low_thresh: 0.1
new_track_thresh: 0.3
track_buffer: 120
match_thresh: 0.9
fuse_score: True
```

</details>
<!-- AUTO:FIN -->

## Notas manuales

### Decisiones tomadas
- 

### Problemas encontrados
- 

### Observaciones de campo
-
