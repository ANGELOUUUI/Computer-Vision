"""
Núcleo del conteo: convierte las trayectorias del tracker en eventos de movimiento.

Regla del protocolo
-------------------
Un vehículo cuenta para un movimiento cuando cruza la línea de su ACCESO y
después la de su SALIDA. Si el ID se pierde antes de salir, el evento se
registra igual con movimiento "desconocido" (seguimiento = "perdido").

Valores de la columna `seguimiento` en eventos.csv:
  - completo                    : cruzó acceso y salida, y la combinación existe en movimientos
  - perdido                     : cruzó acceso pero el ID se perdió antes de salir
  - sin_acceso                  : solo se le vio cruzar una salida (entró ya dentro del cruce)
  - combinacion_no_configurada  : acceso+salida que no está en movimientos.csv

Estrategia contra oclusiones (2a capa, además del track_buffer del tracker):
  * Un ID no se cierra hasta pasar `segundos_perdida` sin verlo.
  * "Re-vinculación": si aparece un ID NUEVO cerca de donde desapareció hace poco
    un vehículo que ya cruzó su acceso y aún no sale, el nuevo ID hereda su acceso,
    su hora de acceso y su historial de clase. Así un camión que tapa a un auto
    no convierte un movimiento completo en "perdido + sin_acceso".
"""
from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from . import MOVIMIENTO_DESCONOCIDO
from .geometria import cruza_linea, punto_en_poligono

COLUMNAS_EVENTOS = [
    "video", "track_id", "clase", "conf_clase", "acceso", "salida", "movimiento",
    "t_acceso", "t_salida", "frame_acceso", "frame_salida", "seguimiento", "ids_vinculados",
]


@dataclass
class EstadoTrack:
    tid: int
    hist: deque                                  # (t_seg, x, y)
    ultimo_frame: int
    ultimo_t: float
    clases: Counter = field(default_factory=Counter)
    acceso: Optional[str] = None
    t_acceso: Optional[float] = None
    frame_acceso: Optional[int] = None
    salida: Optional[str] = None
    t_salida: Optional[float] = None
    frame_salida: Optional[int] = None
    vinculados: list = field(default_factory=list)

    @property
    def pos(self):
        return (self.hist[-1][1], self.hist[-1][2])

    def velocidad(self, ventana_s: float) -> float:
        """Velocidad media (px/s) en la última ventana de tiempo."""
        if len(self.hist) < 2:
            return 0.0
        t_fin, x_fin, y_fin = self.hist[-1]
        t0, x0, y0 = self.hist[0]
        for t, x, y in reversed(self.hist):
            t0, x0, y0 = t, x, y
            if t_fin - t >= ventana_s:
                break
        dt = t_fin - t0
        return math.hypot(x_fin - x0, y_fin - y0) / dt if dt > 0 else 0.0


class ContadorMovimientos:
    """Mantiene el estado de cada ID del tracker y emite eventos (filas de eventos.csv)."""

    def __init__(self, cfg, video_nombre: str, inicio: datetime, fps: float):
        self.cfg = cfg
        self.video = video_nombre
        self.inicio = inicio
        self.fps = fps or 30.0
        p = cfg.proc
        self.frames_perdida = max(1, int(round(float(p["segundos_perdida"]) * self.fps)))
        rv = p.get("revinculacion") or {}
        self.revincular = bool(rv.get("activa", True))
        self.rv_max_s = float(rv.get("max_segundos", 2.5))
        self.rv_max_px = float(rv.get("max_distancia_px", 90))
        self.tracks: dict[int, EstadoTrack] = {}
        self.alias: dict[int, int] = {}           # ID viejo -> ID que heredó su historia
        self.terminados: set[int] = set()         # IDs que ya salieron: se ignoran si siguen visibles
        self.eventos: list[dict] = []
        self.stats = Counter()
        self.frame_actual = -1

    # ------------------------------------------------------------------
    def _dt(self, t_seg: Optional[float]) -> str:
        if t_seg is None:
            return ""
        return (self.inicio + timedelta(seconds=t_seg)).isoformat(sep=" ", timespec="milliseconds")

    def _buscar_revinculacion(self, x, y, t_s, frame_idx) -> Optional[EstadoTrack]:
        """Busca un track 'huérfano' (con acceso, sin salida, no visto en este frame) cercano."""
        mejor, mejor_d = None, self.rv_max_px
        for st in self.tracks.values():
            if st.ultimo_frame >= frame_idx or st.acceso is None or st.salida is not None:
                continue
            if t_s - st.ultimo_t > self.rv_max_s:
                continue
            d = math.hypot(st.pos[0] - x, st.pos[1] - y)
            if d <= mejor_d:
                mejor, mejor_d = st, d
        return mejor

    # ------------------------------------------------------------------
    def actualizar(self, frame_idx: int, t_s: float, detecciones: list) -> None:
        """
        Procesa las detecciones de un frame.
        detecciones: lista de (track_id, x, y, nombre_clase), donde (x, y) es el punto de referencia.
        """
        self.frame_actual = frame_idx
        ventana = max(2.0, float(self.cfg.filas_cfg.get("ventana_velocidad_s", 1.0)) * 2)
        for tid, x, y, clase in detecciones:
            # Si este ID ya fue absorbido por otro, se redirige al heredero (si sigue vivo y no se vio aún)
            if tid in self.alias:
                heredero = self.tracks.get(self.alias[tid])
                if heredero is not None and heredero.ultimo_frame < frame_idx:
                    tid = heredero.tid
            if tid in self.terminados:   # ya cruzó su salida; aún se ve dentro de la imagen
                continue
            st = self.tracks.get(tid)
            if st is None:
                st = EstadoTrack(tid=tid, hist=deque(maxlen=int(self.fps * ventana) + 2),
                                 ultimo_frame=frame_idx, ultimo_t=t_s)
                if self.revincular:
                    viejo = self._buscar_revinculacion(x, y, t_s, frame_idx)
                    if viejo is not None:
                        st.acceso, st.t_acceso, st.frame_acceso = viejo.acceso, viejo.t_acceso, viejo.frame_acceso
                        st.clases = viejo.clases.copy()
                        st.vinculados = viejo.vinculados + [viejo.tid]
                        st.hist.append((viejo.ultimo_t, *viejo.pos))   # permite detectar el cruce de salida
                        self.alias[viejo.tid] = tid
                        del self.tracks[viejo.tid]
                        self.stats["revinculaciones"] += 1
                self.tracks[tid] = st
            prev = st.pos if st.hist else None
            st.hist.append((t_s, x, y))
            st.ultimo_frame, st.ultimo_t = frame_idx, t_s
            st.clases[clase] += 1
            if prev is not None:
                self._revisar_cruces(st, prev, (x, y), t_s, frame_idx)

        # Cerrar los IDs que llevan demasiado tiempo sin verse
        for tid in [t for t, s in self.tracks.items() if frame_idx - s.ultimo_frame > self.frames_perdida]:
            self._cerrar(self.tracks.pop(tid))

    def _revisar_cruces(self, st: EstadoTrack, prev, actual, t_s, frame_idx) -> None:
        if st.acceso is None:
            for linea in self.cfg.accesos:
                if cruza_linea(prev, actual, linea):
                    st.acceso, st.t_acceso, st.frame_acceso = linea.id, t_s, frame_idx
                    break
        if st.salida is None:
            for linea in self.cfg.salidas:
                if cruza_linea(prev, actual, linea):
                    st.salida, st.t_salida, st.frame_salida = linea.id, t_s, frame_idx
                    # El vehículo ya salió: se emite el evento y se deja de seguir
                    self.terminados.update([st.tid, *st.vinculados])
                    self._cerrar(self.tracks.pop(st.tid))
                    return

    def _cerrar(self, st: EstadoTrack) -> None:
        if st.acceso is None and st.salida is None:
            self.stats["sin_cruce"] += 1           # estacionados, peatones mal clasificados, ruido…
            return
        total = sum(st.clases.values()) or 1
        clase, n = st.clases.most_common(1)[0] if st.clases else ("vehiculo", 0)
        acceso, salida = st.acceso, st.salida
        if acceso and salida:
            mov = self.cfg.movimientos.get((acceso, salida))
            seguimiento = "completo" if mov else "combinacion_no_configurada"
            mov = mov or MOVIMIENTO_DESCONOCIDO
        elif acceso:
            mov, seguimiento = MOVIMIENTO_DESCONOCIDO, "perdido"
        else:
            acceso, mov, seguimiento = MOVIMIENTO_DESCONOCIDO, MOVIMIENTO_DESCONOCIDO, "sin_acceso"
        self.stats[seguimiento] += 1
        self.eventos.append({
            "video": self.video,
            "track_id": st.tid,
            "clase": clase,
            "conf_clase": round(n / total, 3),
            "acceso": acceso,
            "salida": salida or MOVIMIENTO_DESCONOCIDO,
            "movimiento": mov,
            "t_acceso": self._dt(st.t_acceso),
            "t_salida": self._dt(st.t_salida),
            "frame_acceso": "" if st.frame_acceso is None else st.frame_acceso,
            "frame_salida": "" if st.frame_salida is None else st.frame_salida,
            "seguimiento": seguimiento,
            "ids_vinculados": ";".join(str(i) for i in st.vinculados),
        })

    def finalizar(self) -> list:
        """Cierra todos los IDs abiertos al terminar el video y devuelve los eventos."""
        for tid in list(self.tracks):
            self._cerrar(self.tracks.pop(tid))
        return self.eventos

    # ------------------------------------------------------------------
    def detenidos_en_zona(self, zona, v_max: float, ventana_s: float) -> list:
        """IDs visibles en el frame actual, dentro de la zona y con velocidad < v_max."""
        ids = []
        for st in self.tracks.values():
            if st.ultimo_frame != self.frame_actual:
                continue
            if punto_en_poligono(st.pos, zona) and st.velocidad(ventana_s) < v_max:
                ids.append(st.tid)
        return sorted(ids)
