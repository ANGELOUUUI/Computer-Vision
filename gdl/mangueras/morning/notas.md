<!-- AUTO:INICIO (esta sección la regenera el pipeline; no editar) -->
# Notas del cruce: Cruce Mangueras (`mangueras`)

- Última ejecución: 2026-10-23T10:14:48
- Pipeline: pipeline_cruces v1.0.0 · Python 3.13.12 · ultralytics 8.4.184
- Modelo de detección: `yolo11n.pt` (conf=0.25, iou=0.5, imgsz=960)
- Clases usadas: 2→auto, 3→moto, 5→autobus, 7→camion
- Tracker: `bytetrack_oclusion.yaml` · punto de referencia: base · frame_stride=1 · segundos_perdida=4.0 · revinculación={'activa': True, 'max_segundos': 2.5, 'max_distancia_px': 90}

## Calidad del seguimiento

- Vehículos en eventos.csv: **3745**
- Completos: 1377 (36.8%)
- Perdidos antes de salir (movimiento *desconocido*): 1771 (47.3%)
- Sin acceso (solo se vio la salida): 532 (14.2%)
- Combinación acceso→salida no configurada: 65 (1.7%)

| Acceso | Vehículos | Perdidos | % perdidos |
|---|---:|---:|---:|
| E | 1471 | 896 | 60.9% |
| N | 579 | 189 | 32.6% |
| O | 303 | 230 | 75.9% |
| S | 860 | 456 | 53.0% |

## Videos procesados

- `mangueras_m.avi`: 7196.5 s, 107340 frames, 600.00 fps · revinculaciones=317 · IDs sin cruce de línea=5306 · cambios de semáforo=0

## Agregación

- Eventos usados en conteos: 3213 de 3745
- Eliminados por ventanas descartadas: 0 (0 ventanas)

## Semáforo y filas

- Semáforos evaluados por visión: S1
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
