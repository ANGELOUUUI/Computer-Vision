"""
Carga y validación de la configuración de un cruce (archivo YAML).

La geometría del cruce (líneas de acceso/salida, zonas de cola, ROIs de
semáforo y la tabla de movimientos) SIEMPRE viene de la configuración.
El pipeline nunca intenta inferirla del video.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from . import MOVIMIENTOS_VALIDOS

# ---------------------------------------------------------------------------
# Valores por defecto (se combinan con lo que venga en el YAML)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "modelo": {
        "pesos": "yolo11n.pt",          # o "yolov8n.pt", o "modelos/best.pt" (reentrenado con pickups)
        "confianza": 0.25,
        "iou": 0.5,
        "imgsz": 960,
        "dispositivo": None,            # None = automático, "cpu", "0" (GPU 0)
        "tracker": "trackers/bytetrack_oclusion.yaml",
        "clases": {2: "auto", 3: "moto", 5: "autobus", 7: "camion"},
    },
    "procesamiento": {
        "frame_stride": 1,              # 1 = procesar todos los frames (recomendado para tracking)
        "punto_referencia": "base",     # "base" (centro inferior de la caja) o "centro"
        "segundos_perdida": 4.0,        # tiempo sin ver un ID antes de darlo por perdido
        "revinculacion": {              # 2a capa contra oclusiones (además del track_buffer)
            "activa": True,
            "max_segundos": 2.5,
            "max_distancia_px": 90,
        },
        "diagrama_segundo": 5.0,        # segundo del primer video usado para diagrama.png
        "log_cada_segundos": 60,
    },
    "semaforo": {
        "cada_n_frames": 2,             # muestrear el semáforo cada n frames
        "frames_estables": 3,           # muestras consecutivas para aceptar un cambio (anti-parpadeo)
        "umbral_min": 0.08,             # fracción mínima de pixeles del color para considerarlo encendido
        "rangos_hsv": {                 # [H,S,V] mínimo y máximo (OpenCV: H 0-179)
            "rojo": [[[0, 90, 140], [10, 255, 255]], [[165, 90, 140], [179, 255, 255]]],
            "amarillo": [[[12, 90, 140], [35, 255, 255]]],
            "verde": [[[40, 50, 120], [100, 255, 255]]],
        },
    },
    "filas": {
        "velocidad_max_px_s": 15.0,     # por debajo de esta velocidad el vehículo se considera detenido
        "ventana_velocidad_s": 1.0,     # ventana para estimar la velocidad
        "evento_fin_verde": "rojo",     # "rojo" o "amarillo"
    },
    "agregacion": {
        "minutos_conteo": 5,
        "minutos_tau": 10,
    },
}


@dataclass
class Linea:
    """Línea de conteo (acceso o salida)."""
    id: str
    nombre: str
    tipo: str                         # "acceso" | "salida"
    orden: int                        # orden geométrico (p. ej. sentido horario desde el norte)
    p1: tuple
    p2: tuple
    hacia: Optional[tuple] = None     # punto del lado hacia el que se cruza (sentido válido)
    zona_cola: Optional[list] = None  # polígono de cola (solo accesos)
    semaforo: Optional[str] = None    # id del semáforo que controla el acceso


@dataclass
class Semaforo:
    id: str
    nombre: str
    visible: bool = True
    roi: Optional[tuple] = None       # (x, y, w, h) de toda la cabeza del semáforo
    focos: dict = field(default_factory=dict)  # color -> (x, y, w, h) de cada foco


@dataclass
class VideoCfg:
    archivo: Path
    inicio: datetime                  # fecha-hora real del primer frame
    clima: str = ""
    luz: str = ""
    incidencias: str = ""


@dataclass
class ConfigCruce:
    ruta: Path
    id: str
    nombre: str
    carpeta: Path
    videos: list
    modelo: dict
    proc: dict
    accesos: list
    salidas: list
    movimientos: dict                 # (acceso, salida) -> movimiento
    semaforos: list
    semaforo_cfg: dict
    filas_cfg: dict
    agregacion: dict
    raw: dict

    # Atajos útiles -------------------------------------------------------
    @property
    def clases(self) -> dict:
        return self.modelo.get("clases") or {}

    @property
    def nombres_clases(self) -> list:
        nombres = list(dict.fromkeys(self.clases.values()))
        return nombres or ["vehiculo"]

    def linea(self, id_: str) -> Optional[Linea]:
        for l in self.accesos + self.salidas:
            if l.id == id_:
                return l
        return None

    def movimientos_de(self, acceso: str) -> list:
        return sorted({m for (a, _), m in self.movimientos.items() if a == acceso},
                      key=lambda m: MOVIMIENTOS_VALIDOS.index(m))


# ---------------------------------------------------------------------------
def _combinar(base: dict, extra: dict) -> dict:
    """Combina diccionarios de forma recursiva (extra tiene prioridad)."""
    res = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(res.get(k), dict) and k != "clases":
            res[k] = _combinar(res[k], v)
        else:
            res[k] = v
    return res


def _punto(p, ctx: str) -> tuple:
    if p is None or len(p) != 2:
        raise ValueError(f"{ctx}: se esperaba un punto [x, y], se recibió {p!r}")
    return (float(p[0]), float(p[1]))


def _caja(c, ctx: str) -> tuple:
    if c is None or len(c) != 4:
        raise ValueError(f"{ctx}: se esperaba una caja [x, y, ancho, alto], se recibió {c!r}")
    return tuple(int(v) for v in c)


def _resolver(base: Path, valor: str) -> str:
    """Resuelve rutas relativas al archivo de configuración si existen ahí."""
    p = Path(valor)
    if not p.is_absolute() and (base / p).exists():
        return str(base / p)
    return valor


def _leer_linea(d: dict, tipo: str) -> Linea:
    ctx = f"{tipo} '{d.get('id')}'"
    if "linea" not in d or len(d["linea"]) != 2:
        raise ValueError(f"{ctx}: 'linea' debe tener exactamente 2 puntos")
    return Linea(
        id=str(d["id"]),
        nombre=str(d.get("nombre", d["id"])),
        tipo=tipo,
        orden=int(d.get("orden", 0)),
        p1=_punto(d["linea"][0], ctx),
        p2=_punto(d["linea"][1], ctx),
        hacia=_punto(d["hacia"], ctx) if d.get("hacia") else None,
        zona_cola=[_punto(p, ctx) for p in d["zona_cola"]] if d.get("zona_cola") else None,
        semaforo=str(d["semaforo"]) if d.get("semaforo") else None,
    )


def cargar_config(ruta: str | Path) -> ConfigCruce:
    """Lee el YAML de un cruce, aplica valores por defecto y valida coherencia."""
    ruta = Path(ruta).resolve()
    with open(ruta, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    base = ruta.parent

    cruce = raw.get("cruce") or {}
    if "id" not in cruce:
        raise ValueError("Falta 'cruce.id' en la configuración")
    carpeta = Path(cruce.get("carpeta_salida", f"gdl/{cruce['id']}"))
    if not carpeta.is_absolute():
        carpeta = base / carpeta

    modelo = _combinar(DEFAULTS["modelo"], raw.get("modelo"))
    if raw.get("modelo", {}).get("clases"):
        modelo["clases"] = {int(k): str(v) for k, v in raw["modelo"]["clases"].items()}
    modelo["pesos"] = _resolver(base, modelo["pesos"])
    modelo["tracker"] = _resolver(base, modelo["tracker"])

    videos = []
    for v in raw.get("videos") or []:
        archivo = Path(v["archivo"])
        if not archivo.is_absolute():
            archivo = base / archivo
        inicio = v["inicio"]
        if not isinstance(inicio, datetime):
            inicio = datetime.fromisoformat(str(inicio))
        videos.append(VideoCfg(archivo=archivo, inicio=inicio,
                               clima=str(v.get("clima", "") or ""),
                               luz=str(v.get("luz", "") or ""),
                               incidencias=str(v.get("incidencias", "") or "")))

    accesos = [_leer_linea(d, "acceso") for d in raw.get("accesos") or []]
    salidas = [_leer_linea(d, "salida") for d in raw.get("salidas") or []]

    semaforos = []
    for s in raw.get("semaforos") or []:
        ctx = f"semáforo '{s.get('id')}'"
        semaforos.append(Semaforo(
            id=str(s["id"]),
            nombre=str(s.get("nombre", s["id"])),
            visible=bool(s.get("visible", True)),
            roi=_caja(s["roi"], ctx) if s.get("roi") else None,
            focos={c: _caja(b, ctx) for c, b in (s.get("focos") or {}).items()},
        ))

    movimientos = {}
    for m in raw.get("movimientos") or []:
        movimientos[(str(m["acceso"]), str(m["salida"]))] = str(m["movimiento"])

    cfg = ConfigCruce(
        ruta=ruta, id=str(cruce["id"]), nombre=str(cruce.get("nombre", cruce["id"])),
        carpeta=carpeta, videos=videos, modelo=modelo,
        proc=_combinar(DEFAULTS["procesamiento"], raw.get("procesamiento")),
        accesos=accesos, salidas=salidas, movimientos=movimientos, semaforos=semaforos,
        semaforo_cfg=_combinar(DEFAULTS["semaforo"], raw.get("semaforo")),
        filas_cfg=_combinar(DEFAULTS["filas"], raw.get("filas")),
        agregacion=_combinar(DEFAULTS["agregacion"], raw.get("agregacion")),
        raw=raw,
    )
    validar_config(cfg)
    return cfg


def validar_config(cfg: ConfigCruce) -> None:
    """Revisa que la configuración sea coherente; lanza ValueError si no lo es."""
    errores = []
    ids = [l.id for l in cfg.accesos + cfg.salidas]
    duplicados = {i for i in ids if ids.count(i) > 1}
    if duplicados:
        errores.append(f"IDs repetidos entre accesos/salidas: {sorted(duplicados)}")
    if not cfg.accesos:
        errores.append("No hay accesos definidos")
    if not cfg.salidas:
        errores.append("No hay salidas definidas")

    ids_acc = {l.id for l in cfg.accesos}
    ids_sal = {l.id for l in cfg.salidas}
    for (a, s), mov in cfg.movimientos.items():
        if a not in ids_acc:
            errores.append(f"Movimiento con acceso inexistente: {a}")
        if s not in ids_sal:
            errores.append(f"Movimiento con salida inexistente: {s}")
        if mov not in MOVIMIENTOS_VALIDOS:
            errores.append(f"Movimiento '{mov}' inválido ({a}->{s}); usar {MOVIMIENTOS_VALIDOS}")

    ids_sem = {s.id for s in cfg.semaforos}
    for a in cfg.accesos:
        if a.semaforo and a.semaforo not in ids_sem:
            errores.append(f"Acceso {a.id} referencia semáforo inexistente: {a.semaforo}")
        if a.zona_cola is not None and len(a.zona_cola) < 3:
            errores.append(f"Acceso {a.id}: la zona_cola necesita al menos 3 puntos")
    for s in cfg.semaforos:
        if s.visible and not s.roi and not s.focos:
            errores.append(f"Semáforo {s.id}: define 'roi' o 'focos' (o pon visible: false)")
    if errores:
        raise ValueError("Configuración inválida:\n  - " + "\n  - ".join(errores))
