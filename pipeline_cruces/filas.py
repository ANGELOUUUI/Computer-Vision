"""
Conteo de vehículos en fila (cola) por acceso y por ciclo.

En el frame en que se confirma un cambio de semáforo:
  * a VERDE  -> evento "inicio_verde": cola acumulada durante el rojo
  * a ROJO   -> evento "fin_verde"   : cola residual que no alcanzó a pasar
(con `evento_fin_verde: amarillo` el fin del verde se toma al cambio a amarillo)

Se cuentan los IDs únicos cuyo punto de referencia está dentro de la zona de
cola del acceso y cuya velocidad es menor a `velocidad_max_px_s` (detenidos).
El número de ciclo de cada semáforo aumenta en cada inicio de verde.
"""
from __future__ import annotations

from collections import defaultdict

COLUMNAS_FILAS = ["video", "acceso", "semaforo", "ciclo", "evento", "timestamp", "frame",
                  "vehiculos_en_fila", "ids"]


class ContadorFilas:
    def __init__(self, cfg, video: str):
        self.cfg = cfg
        self.video = video
        self.v_max = float(cfg.filas_cfg["velocidad_max_px_s"])
        self.ventana = float(cfg.filas_cfg["ventana_velocidad_s"])
        self.fin = cfg.filas_cfg.get("evento_fin_verde", "rojo")
        self.ciclo = defaultdict(int)
        self.filas: list[dict] = []
        # accesos con zona de cola y semáforo asociado
        self.por_semaforo = defaultdict(list)
        for a in cfg.accesos:
            if a.zona_cola and a.semaforo:
                self.por_semaforo[a.semaforo].append(a)

    @property
    def activo(self) -> bool:
        return bool(self.por_semaforo)

    def en_cambio(self, ev_sem: dict, contador) -> None:
        """Se llama con cada evento de semáforo confirmado."""
        sem, estado = ev_sem["semaforo"], ev_sem["estado"]
        if estado == "verde":
            self.ciclo[sem] += 1
            etiqueta = "inicio_verde"
        elif estado == self.fin and ev_sem["estado_anterior"] != "inicio" and self.ciclo[sem] > 0:
            etiqueta = "fin_verde"
        else:
            return
        for acc in self.por_semaforo.get(sem, []):
            ids = contador.detenidos_en_zona(acc.zona_cola, self.v_max, self.ventana)
            self.filas.append({
                "video": self.video, "acceso": acc.id, "semaforo": sem,
                "ciclo": self.ciclo[sem], "evento": etiqueta,
                "timestamp": ev_sem["timestamp"], "frame": ev_sem["frame"],
                "vehiculos_en_fila": len(ids), "ids": ";".join(map(str, ids)),
            })
