"""Dibujo de la configuración sobre un frame (diagrama.png y video de depuración)."""
from __future__ import annotations

import cv2
import numpy as np

# Colores BGR
C_ACCESO = (60, 200, 60)
C_SALIDA = (40, 40, 230)
C_COLA = (0, 200, 255)
C_SEM = (255, 0, 255)
COLOR_FOCO = {"rojo": (0, 0, 255), "amarillo": (0, 220, 255), "verde": (0, 200, 0)}


def _texto(img, txt, org, color, escala=0.6):
    org = (int(org[0]), int(org[1]))
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, escala, color, 2, cv2.LINE_AA)


def _p(pt):
    return (int(round(pt[0])), int(round(pt[1])))


def dibujar_configuracion(img, cfg, alpha_zonas: float = 0.25):
    """Dibuja líneas de acceso/salida, sentido de cruce, zonas de cola y ROIs de semáforo."""
    out = img.copy()
    capa = img.copy()
    for a in cfg.accesos:
        if a.zona_cola:
            cv2.fillPoly(capa, [np.array(a.zona_cola, np.int32)], C_COLA)
    out = cv2.addWeighted(capa, alpha_zonas, out, 1 - alpha_zonas, 0)
    for a in cfg.accesos:
        if a.zona_cola:
            cv2.polylines(out, [np.array(a.zona_cola, np.int32)], True, C_COLA, 1, cv2.LINE_AA)

    for linea, color in [(l, C_ACCESO) for l in cfg.accesos] + [(l, C_SALIDA) for l in cfg.salidas]:
        cv2.line(out, _p(linea.p1), _p(linea.p2), color, 3, cv2.LINE_AA)
        medio = ((linea.p1[0] + linea.p2[0]) / 2, (linea.p1[1] + linea.p2[1]) / 2)
        if linea.hacia:   # flecha que indica el sentido válido de cruce
            dx, dy = linea.hacia[0] - medio[0], linea.hacia[1] - medio[1]
            n = max(1e-6, (dx * dx + dy * dy) ** 0.5)
            fin = (medio[0] + 40 * dx / n, medio[1] + 40 * dy / n)
            cv2.arrowedLine(out, _p(medio), _p(fin), color, 2, cv2.LINE_AA, tipLength=0.35)
        etiqueta = f"{'A' if linea.tipo == 'acceso' else 'S'}:{linea.id} (#{linea.orden})"
        if linea.tipo == "acceso" and linea.semaforo:
            etiqueta += f" [{linea.semaforo}]"
        _texto(out, etiqueta, (medio[0] + 6, medio[1] - 8), color)

    for s in cfg.semaforos:
        if s.roi:
            x, y, w, h = s.roi
            cv2.rectangle(out, (x, y), (x + w, y + h), C_SEM, 2)
            _texto(out, f"{s.id}{'' if s.visible else ' (no visible)'}", (x, y - 6), C_SEM, 0.5)
        for color, (x, y, w, h) in s.focos.items():
            cv2.rectangle(out, (x, y), (x + w, y + h), COLOR_FOCO.get(color, C_SEM), 2)
        if s.focos and not s.roi:
            x, y, _, _ = next(iter(s.focos.values()))
            _texto(out, s.id, (x, y - 6), C_SEM, 0.5)

    # Leyenda
    leyenda = [("Acceso (A)", C_ACCESO), ("Salida (S)", C_SALIDA), ("Zona de cola", C_COLA), ("ROI semaforo", C_SEM)]
    for i, (t, c) in enumerate(leyenda):
        y = 28 + i * 24
        cv2.rectangle(out, (12, y - 14), (30, y + 2), c, -1)
        _texto(out, t, (38, y), (255, 255, 255), 0.55)
    _texto(out, f"Cruce: {cfg.nombre}", (12, out.shape[0] - 14), (255, 255, 255), 0.6)
    return out


def leer_frame(video_path, segundo: float):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se pudo abrir el video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, segundo) * 1000)
    ok, frame = cap.read()
    if not ok:                      # video más corto que `segundo`: usar el primer frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"No se pudo leer ningún frame de {video_path}")
    return frame


def generar_diagrama(cfg, destino) -> None:
    if not cfg.videos:
        raise ValueError("No hay videos en la configuración para generar el diagrama")
    frame = leer_frame(cfg.videos[0].archivo, float(cfg.proc["diagrama_segundo"]))
    cv2.imwrite(str(destino), dibujar_configuracion(frame, cfg))


def dibujar_tracks(img, detecciones, contador, estados_sem: dict):
    """Anota IDs, acceso asignado y estado de semáforos (video de depuración)."""
    for tid, x, y, clase, xyxy in detecciones:
        st = contador.tracks.get(tid)
        acc = st.acceso if st and st.acceso else "-"
        x1, y1, x2, y2 = map(int, xyxy)
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 0), 1)
        cv2.circle(img, (int(x), int(y)), 3, (255, 255, 0), -1)
        _texto(img, f"{tid} {clase} {acc}", (x1, y1 - 4), (255, 255, 0), 0.45)
    for i, (sid, est) in enumerate(estados_sem.items()):
        _texto(img, f"{sid}: {est or '?'}", (img.shape[1] - 200, 28 + 24 * i),
               COLOR_FOCO.get(est, (255, 255, 255)), 0.6)
    return img
