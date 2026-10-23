#!/usr/bin/env python3
"""
Orquestador del pipeline de videos de cruces viales -> datos para validar SUMO.

Subcomandos
-----------
  init       Crea la carpeta del cruce y las plantillas de captura manual.
  puntos     Abre un frame del video para obtener coordenadas con el ratón.
  diagrama   Genera solo accesos.csv, movimientos.csv y diagrama.png (revisar la config).
  procesar   Pipeline completo de UN cruce (detección, tracking, semáforo, filas,
             agregación, validación y notas).
  agregar    Recalcula conteos/τ/proporciones/validación/notas desde eventos.csv
             (sin volver a correr YOLO; útil tras editar ventanas_descartadas.csv).
  validar    Solo compara conteo_manual.csv contra eventos.csv.
  todos      Procesa varios cruces, uno tras otro e independientes entre sí.
  verificar  Revisa que la carpeta del cruce tenga los 14 archivos del contrato.

Ejemplos
--------
  python main.py init      --config config.yaml
  python main.py diagrama  --config config.yaml
  python main.py procesar  --config config.yaml --max-segundos 120 --video-depuracion
  python main.py procesar  --config config.yaml
  python main.py todos     configs/oxxo.yaml configs/plaza.yaml configs/mangueras.yaml
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from pathlib import Path

from pipeline_cruces import ARCHIVOS_CONTRATO
from pipeline_cruces.config import cargar_config

log = logging.getLogger("pipeline")
RAIZ = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def configurar_log(cruce_id: str | None = None, verbose: bool = False) -> None:
    """Log a consola y a logs/<cruce>.log (fuera de la carpeta del cruce, para respetar el contrato)."""
    for h in list(log.handlers):
        log.removeHandler(h)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(fmt)
    log.addHandler(consola)
    if cruce_id:
        (RAIZ / "logs").mkdir(exist_ok=True)
        archivo = logging.FileHandler(RAIZ / "logs" / f"{cruce_id}.log", encoding="utf-8")
        archivo.setFormatter(fmt)
        log.addHandler(archivo)


def preparar_carpeta(cfg) -> Path:
    from pipeline_cruces.salidas import crear_plantillas
    cfg.carpeta.mkdir(parents=True, exist_ok=True)
    creados = crear_plantillas(cfg.carpeta)
    if creados:
        log.info("Plantillas creadas en %s: %s", cfg.carpeta, ", ".join(creados))
    return cfg.carpeta


def paso_configuracion(cfg) -> None:
    """accesos.csv, movimientos.csv, videos.csv y diagrama.png."""
    from pipeline_cruces.diagrama import generar_diagrama
    from pipeline_cruces.inventario import generar_videos_csv
    from pipeline_cruces.salidas import escribir_accesos, escribir_movimientos
    c = cfg.carpeta
    escribir_accesos(cfg, c / "accesos.csv")
    escribir_movimientos(cfg, c / "movimientos.csv")
    generar_videos_csv(cfg, c / "videos.csv")
    try:
        generar_diagrama(cfg, c / "diagrama.png")
        log.info("diagrama.png generado: revísalo antes de procesar todo el video")
    except Exception as e:  # sin video no se puede dibujar, pero el resto puede seguir
        log.error("No se pudo generar diagrama.png: %s", e)


def paso_post(cfg, stats_videos: dict | None = None) -> None:
    """Agregaciones, validación y notas a partir de eventos.csv."""
    from pipeline_cruces.agregacion import generar_agregaciones
    from pipeline_cruces.salidas import escribir_notas, resumen_notas
    from pipeline_cruces.validacion import validar
    c = cfg.carpeta
    stats_agr = generar_agregaciones(cfg, c)
    log.info("Agregación: %s", stats_agr)
    val = validar(c)
    log.info("Validación: %d filas comparadas", len(val))
    if stats_videos is None:   # 'agregar' sin reprocesar: reutilizar estadísticas guardadas en logs/
        ruta = RAIZ / "logs" / f"{cfg.id}_stats.json"
        stats_videos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    escribir_notas(c / "notas.md", resumen_notas(cfg, c, stats_videos, stats_agr, val))


def reportar_contrato(cfg) -> bool:
    from pipeline_cruces.salidas import verificar_contrato
    faltan, extra = verificar_contrato(cfg.carpeta)
    if faltan:
        log.warning("Faltan archivos del contrato en %s: %s", cfg.carpeta, faltan)
    else:
        log.info("Contrato completo: %d/%d archivos en %s", len(ARCHIVOS_CONTRATO), len(ARCHIVOS_CONTRATO), cfg.carpeta)
    if extra:
        log.warning("Archivos que NO son parte del contrato en %s: %s", cfg.carpeta, extra)
    return not faltan


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------
def cmd_init(args) -> int:
    cfg = cargar_config(args.config)
    configurar_log(cfg.id, args.verbose)
    preparar_carpeta(cfg)
    from pipeline_cruces.salidas import escribir_accesos, escribir_movimientos
    escribir_accesos(cfg, cfg.carpeta / "accesos.csv")
    escribir_movimientos(cfg, cfg.carpeta / "movimientos.csv")
    log.info("Cruce '%s' inicializado en %s", cfg.id, cfg.carpeta)
    return 0


def cmd_puntos(args) -> int:
    from pipeline_cruces.selector_puntos import seleccionar_puntos
    video = args.video
    if not video:
        cfg = cargar_config(args.config)
        video = str(cfg.videos[0].archivo)
    seleccionar_puntos(video, args.segundo)
    return 0


def cmd_diagrama(args) -> int:
    cfg = cargar_config(args.config)
    configurar_log(cfg.id, args.verbose)
    preparar_carpeta(cfg)
    paso_configuracion(cfg)
    return 0


def procesar_cruce(cfg, max_segundos=None, depuracion=False) -> bool:
    """Pipeline completo para un cruce. Los archivos quedan completos al terminar."""
    from pipeline_cruces.contador import COLUMNAS_EVENTOS
    from pipeline_cruces.filas import COLUMNAS_FILAS
    from pipeline_cruces.procesador_video import procesar_video
    from pipeline_cruces.salidas import escribir_tabla
    from pipeline_cruces.semaforo import COLUMNAS_SEMAFORO

    log.info("=" * 70)
    log.info("Cruce %s (%s) -> %s", cfg.id, cfg.nombre, cfg.carpeta)
    preparar_carpeta(cfg)
    paso_configuracion(cfg)

    eventos, semaforo, filas, stats = [], [], [], {}
    for v in cfg.videos:
        dep = RAIZ / "depuracion" / f"{cfg.id}_{v.archivo.stem}.mp4" if depuracion else None
        r = procesar_video(cfg, v, max_segundos=max_segundos, ruta_depuracion=dep)
        eventos += r["eventos"]
        semaforo += r["semaforo"]
        filas += r["filas"]
        stats[v.archivo.name] = r["stats"]
        # Se reescriben tras cada video: si un video posterior falla, lo ya procesado queda guardado
        escribir_tabla(eventos, COLUMNAS_EVENTOS, cfg.carpeta / "eventos.csv")
        escribir_tabla(semaforo, COLUMNAS_SEMAFORO, cfg.carpeta / "semaforo_eventos.csv")
        escribir_tabla(filas, COLUMNAS_FILAS, cfg.carpeta / "filas.csv")

    if not any(s.visible for s in cfg.semaforos):
        log.info("Sin semáforo visible configurado: semaforo_eventos.csv y filas.csv quedan vacíos")
    (RAIZ / "logs").mkdir(exist_ok=True)
    (RAIZ / "logs" / f"{cfg.id}_stats.json").write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")

    paso_post(cfg, stats)
    return reportar_contrato(cfg)


def cmd_procesar(args) -> int:
    cfg = cargar_config(args.config)
    configurar_log(cfg.id, args.verbose)
    return 0 if procesar_cruce(cfg, args.max_segundos, args.video_depuracion) else 1


def cmd_agregar(args) -> int:
    cfg = cargar_config(args.config)
    configurar_log(cfg.id, args.verbose)
    preparar_carpeta(cfg)
    paso_post(cfg)
    return 0 if reportar_contrato(cfg) else 1


def cmd_validar(args) -> int:
    from pipeline_cruces.validacion import validar
    cfg = cargar_config(args.config)
    configurar_log(cfg.id, args.verbose)
    df = validar(cfg.carpeta)
    if len(df):
        print(df[df["nivel"].isin(["acceso", "total"])].to_string(index=False))
    else:
        log.info("conteo_manual.csv está vacío: validacion.csv queda solo con encabezados")
    return 0


def cmd_todos(args) -> int:
    resultados = {}
    for ruta in args.configs:
        try:
            cfg = cargar_config(ruta)
            configurar_log(cfg.id, args.verbose)
            resultados[cfg.id] = "OK" if procesar_cruce(cfg, args.max_segundos, args.video_depuracion) else "INCOMPLETO"
        except Exception as e:   # un cruce que falla no detiene a los demás
            configurar_log(None, args.verbose)
            log.error("Error en %s: %s\n%s", ruta, e, traceback.format_exc())
            resultados[str(ruta)] = f"ERROR: {e}"
    configurar_log(None)
    log.info("Resumen: %s", json.dumps(resultados, ensure_ascii=False, indent=2))
    return 0 if all(v == "OK" for v in resultados.values()) else 1


def cmd_verificar(args) -> int:
    cfg = cargar_config(args.config)
    configurar_log(None, args.verbose)
    return 0 if reportar_contrato(cfg) else 1


# ---------------------------------------------------------------------------
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pipeline de videos de cruces viales para validar SUMO")
    p.add_argument("-v", "--verbose", action="store_true", help="log detallado")
    sub = p.add_subparsers(dest="comando", required=True)

    def con_config(nombre, ayuda):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("--config", default="config.yaml", help="YAML del cruce (default: config.yaml)")
        return s

    con_config("init", "crear carpeta y plantillas del cruce").set_defaults(func=cmd_init)
    s = con_config("puntos", "seleccionar coordenadas sobre un frame")
    s.add_argument("--video", help="ruta del video (default: primer video de la config)")
    s.add_argument("--segundo", type=float, default=5.0)
    s.set_defaults(func=cmd_puntos)
    con_config("diagrama", "generar accesos/movimientos/videos.csv y diagrama.png").set_defaults(func=cmd_diagrama)

    for nombre, func in [("procesar", cmd_procesar)]:
        s = con_config(nombre, "pipeline completo de un cruce")
        s.add_argument("--max-segundos", type=float, help="procesar solo los primeros N s de cada video (prueba)")
        s.add_argument("--video-depuracion", action="store_true", help="guardar video anotado en depuracion/")
        s.set_defaults(func=func)

    con_config("agregar", "recalcular agregados, validación y notas desde eventos.csv").set_defaults(func=cmd_agregar)
    con_config("validar", "comparar conteo manual vs automático").set_defaults(func=cmd_validar)
    con_config("verificar", "revisar los 14 archivos del contrato").set_defaults(func=cmd_verificar)

    s = sub.add_parser("todos", help="procesar varios cruces de forma independiente")
    s.add_argument("configs", nargs="+", help="archivos YAML, uno por cruce")
    s.add_argument("--max-segundos", type=float)
    s.add_argument("--video-depuracion", action="store_true")
    s.set_defaults(func=cmd_todos)
    return p


def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
