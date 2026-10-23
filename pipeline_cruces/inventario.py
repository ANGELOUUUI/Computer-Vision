"""
Inventario de videos -> videos.csv

Lee metadatos técnicos con OpenCV (fps, frames, duración, resolución) y toma
fecha/hora de inicio, clima, luz e incidencias de la configuración. Si
videos.csv ya existe y tiene clima/luz/incidencias capturados a mano para un
archivo, esos valores se conservan cuando la configuración los deja vacíos.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pandas as pd

COLUMNAS_VIDEOS = ["archivo", "fecha", "hora_inicio", "duracion_s", "fps", "frames",
                   "resolucion", "clima", "luz", "incidencias"]


def metadatos(ruta: Path) -> dict:
    cap = cv2.VideoCapture(str(ruta))
    if not cap.isOpened():
        return {"fps": "", "frames": "", "duracion_s": "", "resolucion": "NO_ENCONTRADO"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {"fps": round(fps, 3), "frames": frames,
            "duracion_s": round(frames / fps, 2) if fps else "",
            "resolucion": f"{w}x{h}"}


def generar_videos_csv(cfg, destino: Path) -> pd.DataFrame:
    previo = {}
    if destino.exists() and destino.stat().st_size > 0:
        try:
            for _, r in pd.read_csv(destino, dtype=str).fillna("").iterrows():
                previo[r["archivo"]] = r
        except Exception:
            pass
    filas = []
    for v in cfg.videos:
        meta = metadatos(v.archivo)
        ant = previo.get(v.archivo.name, {})
        filas.append({
            "archivo": v.archivo.name,
            "fecha": v.inicio.date().isoformat(),
            "hora_inicio": v.inicio.time().isoformat(timespec="seconds"),
            **meta,
            "clima": v.clima or (ant.get("clima", "") if len(ant) else ""),
            "luz": v.luz or (ant.get("luz", "") if len(ant) else ""),
            "incidencias": v.incidencias or (ant.get("incidencias", "") if len(ant) else ""),
        })
    df = pd.DataFrame(filas, columns=COLUMNAS_VIDEOS)
    df.to_csv(destino, index=False, encoding="utf-8")
    return df
