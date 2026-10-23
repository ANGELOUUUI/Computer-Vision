"""
Detección del estado del semáforo por color (HSV) dentro de ROIs fijas.

Dos formas de definir la ROI en la configuración:
  * `focos`: una caja por foco (rojo / amarillo / verde). Es lo más robusto,
    porque cada foco solo se evalúa con su propio color.
  * `roi`: una sola caja con toda la cabeza del semáforo. Se mide la fracción
    de pixeles de cada color dentro de la caja.

Se aplica un filtro anti-parpadeo: un cambio solo se acepta si el nuevo color
aparece en `frames_estables` muestras consecutivas. Si ningún color supera el
umbral (p. ej. un camión tapa el semáforo) se conserva el último estado.

Este módulo NO intenta reconstruir el plan de fases: solo registra cambios.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import cv2
import numpy as np

COLORES = ("rojo", "amarillo", "verde")
COLUMNAS_SEMAFORO = ["video", "semaforo", "timestamp", "frame", "estado", "estado_anterior", "score"]


def _recortar(frame, caja):
    x, y, w, h = caja
    H, W = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return frame[y0:y1, x0:x1]


def fraccion_color(region_bgr, rangos) -> float:
    """Fracción de pixeles de la región que caen en alguno de los rangos HSV del color."""
    if region_bgr is None or region_bgr.size == 0:
        return 0.0
    hsv = cv2.cvtColor(cv2.GaussianBlur(region_bgr, (3, 3), 0), cv2.COLOR_BGR2HSV)
    mascara = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for bajo, alto in rangos:
        mascara |= cv2.inRange(hsv, np.array(bajo, np.uint8), np.array(alto, np.uint8))
    return float(np.count_nonzero(mascara)) / mascara.size


class DetectorSemaforo:
    def __init__(self, semaforo, cfg_sem: dict, video: str, inicio: datetime):
        self.s = semaforo
        self.rangos = cfg_sem["rangos_hsv"]
        self.umbral = float(cfg_sem["umbral_min"])
        self.estables = int(cfg_sem["frames_estables"])
        self.video, self.inicio = video, inicio
        self.estado: Optional[str] = None
        self.candidato: Optional[str] = None
        self.n_candidato = 0

    def medir(self, frame) -> tuple[Optional[str], dict]:
        """Devuelve (color encendido o None, scores por color)."""
        scores = {}
        for color in COLORES:
            caja = self.s.focos.get(color) or self.s.roi
            if caja is None:
                continue
            scores[color] = fraccion_color(_recortar(frame, caja), self.rangos[color])
        if not scores:
            return None, scores
        mejor = max(scores, key=scores.get)
        return (mejor if scores[mejor] >= self.umbral else None), scores

    def actualizar(self, frame, frame_idx: int, t_s: float) -> Optional[dict]:
        """Mide el frame; si se confirma un cambio de estado devuelve el evento."""
        color, scores = self.medir(frame)
        if color is None or color == self.estado:
            self.candidato, self.n_candidato = None, 0
            return None
        if color == self.candidato:
            self.n_candidato += 1
        else:
            self.candidato, self.n_candidato = color, 1
        if self.n_candidato < self.estables:
            return None
        anterior, self.estado = self.estado, color
        self.candidato, self.n_candidato = None, 0
        return {
            "video": self.video,
            "semaforo": self.s.id,
            "timestamp": (self.inicio + timedelta(seconds=t_s)).isoformat(sep=" ", timespec="milliseconds"),
            "frame": frame_idx,
            "estado": color,
            "estado_anterior": anterior or "inicio",
            "score": round(scores[color], 3),
        }
