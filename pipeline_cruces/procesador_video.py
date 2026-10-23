"""
Bucle principal de video: detección + tracking (YOLO / ultralytics), conteo de
movimientos, semáforo y filas, todo en una sola pasada por cada video.

El timestamp de cada frame es el REAL del video:
    hora_real = inicio_del_video (config) + posición del frame (CAP_PROP_POS_MSEC)
Si el contenedor no reporta la posición se usa frame / fps como respaldo.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2

from .contador import ContadorMovimientos
from .diagrama import dibujar_configuracion, dibujar_tracks
from .filas import ContadorFilas
from .geometria import punto_referencia
from .semaforo import DetectorSemaforo

log = logging.getLogger("pipeline")


def cargar_modelo(cfg):
    """Carga YOLO. Sirve igual para yolo11n.pt / yolov8n.pt que para un best.pt reentrenado."""
    from ultralytics import YOLO   # import tardío: el resto del pipeline funciona sin ultralytics
    modelo = YOLO(cfg.modelo["pesos"])
    nombres = getattr(modelo, "names", {}) or {}
    for cid, nombre in cfg.clases.items():
        if cid not in nombres:
            log.warning("La clase %s (%s) no existe en el modelo %s", cid, nombre, cfg.modelo["pesos"])
        else:
            log.info("Clase del modelo %s='%s' -> '%s'", cid, nombres[cid], nombre)
    return modelo


def _detecciones(resultado, cfg) -> list:
    """Extrae (track_id, x, y, clase, xyxy) de un resultado de model.track()."""
    cajas = resultado.boxes
    if cajas is None or cajas.id is None or len(cajas) == 0:
        return []
    ids = cajas.id.int().cpu().tolist()
    xyxy = cajas.xyxy.cpu().numpy()
    cls = cajas.cls.int().cpu().tolist()
    modo = cfg.proc["punto_referencia"]
    salida = []
    for tid, caja, c in zip(ids, xyxy, cls):
        x, y = punto_referencia(caja, modo)
        salida.append((int(tid), x, y, cfg.clases.get(int(c), str(c)), caja))
    return salida


def procesar_video(cfg, video, max_segundos: float | None = None,
                   ruta_depuracion: Path | None = None) -> dict:
    """Procesa un video y devuelve eventos, cambios de semáforo, filas y estadísticas."""
    nombre = video.archivo.name
    cap = cv2.VideoCapture(str(video.archivo))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se pudo abrir el video: {video.archivo}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    log.info("Video %s: %dx%d, %.2f fps, %d frames", nombre, W, H, fps, total)

    # Modelo nuevo por video => el tracker arranca limpio (IDs no se mezclan entre videos)
    modelo = cargar_modelo(cfg)
    contador = ContadorMovimientos(cfg, nombre, video.inicio, fps)
    filas = ContadorFilas(cfg, nombre)
    detectores = [DetectorSemaforo(s, cfg.semaforo_cfg, nombre, video.inicio)
                  for s in cfg.semaforos if s.visible]
    eventos_sem = []

    escritor = None
    if ruta_depuracion is not None:
        ruta_depuracion.parent.mkdir(parents=True, exist_ok=True)
        escritor = cv2.VideoWriter(str(ruta_depuracion), cv2.VideoWriter_fourcc(*"mp4v"),
                                   fps / max(1, int(cfg.proc["frame_stride"])), (W, H))

    m = cfg.modelo
    clases_filtro = list(cfg.clases.keys()) or None
    stride = max(1, int(cfg.proc["frame_stride"]))
    cada_sem = max(1, int(cfg.semaforo_cfg["cada_n_frames"]))
    log_cada = float(cfg.proc["log_cada_segundos"])
    frame_idx, ultimo_log, t0 = -1, 0.0, time.time()

    while True:
        frame_idx += 1
        if frame_idx % stride != 0:          # frames saltados: solo avanzar el decodificador
            if not cap.grab():
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        msec = cap.get(cv2.CAP_PROP_POS_MSEC)
        t_s = msec / 1000.0 if (msec > 0 or frame_idx == 0) else frame_idx / fps
        if max_segundos is not None and t_s > max_segundos:
            break

        # 1) Detección + tracking (persist=True mantiene el estado del tracker entre frames)
        res = modelo.track(frame, persist=True, tracker=m["tracker"], conf=m["confianza"],
                           iou=m["iou"], imgsz=m["imgsz"], classes=clases_filtro,
                           device=m["dispositivo"], verbose=False)[0]
        dets = _detecciones(res, cfg)

        # 2) Cruces de líneas -> eventos
        contador.actualizar(frame_idx, t_s, [(d[0], d[1], d[2], d[3]) for d in dets])

        # 3) Semáforo (y filas en el frame exacto del cambio confirmado)
        if detectores and frame_idx % cada_sem == 0:
            for det in detectores:
                ev = det.actualizar(frame, frame_idx, t_s)
                if ev:
                    eventos_sem.append(ev)
                    if filas.activo:
                        filas.en_cambio(ev, contador)

        if escritor is not None:
            img = dibujar_configuracion(frame, cfg, alpha_zonas=0.15)
            escritor.write(dibujar_tracks(img, dets, contador, {d.s.id: d.estado for d in detectores}))

        if t_s - ultimo_log >= log_cada:
            ultimo_log = t_s
            avance = f"{100 * frame_idx / total:5.1f}%" if total else f"{t_s:.0f}s"
            log.info("  %s  t=%7.1fs  eventos=%d  IDs activos=%d  (%.1f fps de proceso)",
                     avance, t_s, len(contador.eventos), len(contador.tracks),
                     frame_idx / max(1e-6, time.time() - t0))

    cap.release()
    if escritor is not None:
        escritor.release()
    eventos = contador.finalizar()
    stats = dict(contador.stats)
    stats.update({"frames": frame_idx, "fps": fps, "segundos": round(t_s if frame_idx > 0 else 0, 1),
                  "cambios_semaforo": len(eventos_sem), "registros_fila": len(filas.filas),
                  "semaforos_evaluados": len(detectores)})
    log.info("Video %s terminado: %s", nombre, stats)
    return {"eventos": eventos, "semaforo": eventos_sem, "filas": filas.filas, "stats": stats}
