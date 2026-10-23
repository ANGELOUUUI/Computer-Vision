"""
Escritura de los archivos del contrato que no son agregaciones:
accesos.csv, movimientos.csv, eventos.csv, semaforo_eventos.csv, filas.csv,
plantillas manuales (ventanas_descartadas.csv, conteo_manual.csv) y notas.md.

Regla de oro: los archivos de captura manual (conteo_manual.csv,
ventanas_descartadas.csv y la sección manual de notas.md) NUNCA se sobrescriben.
"""
from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import ARCHIVOS_CONTRATO, __version__
from .agregacion import COLUMNAS_DESCARTES
from .contador import COLUMNAS_EVENTOS
from .filas import COLUMNAS_FILAS
from .semaforo import COLUMNAS_SEMAFORO
from .validacion import COLUMNAS_MANUAL

MARCA_INI = "<!-- AUTO:INICIO (esta sección la regenera el pipeline; no editar) -->"
MARCA_FIN = "<!-- AUTO:FIN -->"


def escribir_tabla(filas: list, columnas: list, destino: Path) -> None:
    """Escribe una lista de dicts como CSV (con encabezados aunque esté vacía)."""
    pd.DataFrame(filas, columns=columnas).to_csv(destino, index=False, encoding="utf-8")


def escribir_accesos(cfg, destino: Path) -> None:
    filas = []
    for l in sorted(cfg.accesos, key=lambda x: x.orden) + sorted(cfg.salidas, key=lambda x: x.orden):
        filas.append({
            "id": l.id, "nombre": l.nombre, "tipo": l.tipo, "orden": l.orden,
            "x1": l.p1[0], "y1": l.p1[1], "x2": l.p2[0], "y2": l.p2[1],
            "hacia_x": l.hacia[0] if l.hacia else "", "hacia_y": l.hacia[1] if l.hacia else "",
            "semaforo": l.semaforo or "", "tiene_zona_cola": bool(l.zona_cola),
        })
    pd.DataFrame(filas).to_csv(destino, index=False, encoding="utf-8")


def escribir_movimientos(cfg, destino: Path) -> None:
    filas = [{"acceso": a, "salida": s, "movimiento": m} for (a, s), m in cfg.movimientos.items()]
    pd.DataFrame(filas, columns=["acceso", "salida", "movimiento"]).to_csv(destino, index=False, encoding="utf-8")


def crear_plantillas(carpeta: Path) -> list:
    """Crea los archivos manuales vacíos (solo encabezados) si aún no existen."""
    creados = []
    plantillas = {
        "ventanas_descartadas.csv": COLUMNAS_DESCARTES,
        "conteo_manual.csv": COLUMNAS_MANUAL,
    }
    for nombre, cols in plantillas.items():
        ruta = carpeta / nombre
        if not ruta.exists():
            pd.DataFrame(columns=cols).to_csv(ruta, index=False, encoding="utf-8")
            creados.append(nombre)
    for nombre, cols in {"semaforo_eventos.csv": COLUMNAS_SEMAFORO, "filas.csv": COLUMNAS_FILAS,
                         "eventos.csv": COLUMNAS_EVENTOS}.items():
        ruta = carpeta / nombre
        if not ruta.exists():
            pd.DataFrame(columns=cols).to_csv(ruta, index=False, encoding="utf-8")
    if not (carpeta / "notas.md").exists():
        escribir_notas(carpeta / "notas.md", "_Pipeline aún no ejecutado._")
        creados.append("notas.md")
    return creados


def _seccion_manual_por_defecto() -> str:
    return (
        "## Notas manuales\n\n"
        "### Decisiones tomadas\n- \n\n"
        "### Problemas encontrados\n- \n\n"
        "### Observaciones de campo\n- \n"
    )


def escribir_notas(ruta: Path, contenido_auto: str) -> None:
    """Regenera solo la sección automática de notas.md y conserva el resto."""
    manual = _seccion_manual_por_defecto()
    if ruta.exists():
        texto = ruta.read_text(encoding="utf-8")
        if MARCA_INI in texto and MARCA_FIN in texto:
            antes, resto = texto.split(MARCA_INI, 1)
            _, despues = resto.split(MARCA_FIN, 1)
            manual = (antes.strip() + "\n\n" + despues.strip()).strip() or manual
        else:
            manual = texto.strip() or manual
    ruta.write_text(f"{MARCA_INI}\n{contenido_auto.strip()}\n{MARCA_FIN}\n\n{manual}\n", encoding="utf-8")


def _version_ultralytics() -> str:
    try:
        import ultralytics
        return ultralytics.__version__
    except Exception:
        return "no instalado"


def resumen_notas(cfg, carpeta: Path, stats_videos: dict, stats_agr: dict, validacion=None) -> str:
    """Construye el texto automático de notas.md (modelo, parámetros y calidad del seguimiento)."""
    ev = pd.read_csv(carpeta / "eventos.csv", dtype=str, keep_default_na=False)
    n = len(ev)
    seg = ev["seguimiento"].value_counts().to_dict() if n else {}
    pct = lambda k: f"{100 * seg.get(k, 0) / n:.1f}%" if n else "-"
    tracker_txt = ""
    try:
        tracker_txt = Path(cfg.modelo["tracker"]).read_text(encoding="utf-8")
    except Exception:
        tracker_txt = f"(no se pudo leer {cfg.modelo['tracker']})"

    lineas = [
        f"# Notas del cruce: {cfg.nombre} (`{cfg.id}`)",
        "",
        f"- Última ejecución: {datetime.now().isoformat(timespec='seconds')}",
        f"- Pipeline: pipeline_cruces v{__version__} · Python {platform.python_version()} · ultralytics {_version_ultralytics()}",
        f"- Modelo de detección: `{Path(str(cfg.modelo['pesos'])).name}` (conf={cfg.modelo['confianza']}, iou={cfg.modelo['iou']}, imgsz={cfg.modelo['imgsz']})",
        f"- Clases usadas: " + ", ".join(f"{k}→{v}" for k, v in cfg.clases.items()),
        f"- Tracker: `{Path(str(cfg.modelo['tracker'])).name}` · punto de referencia: {cfg.proc['punto_referencia']} · "
        f"frame_stride={cfg.proc['frame_stride']} · segundos_perdida={cfg.proc['segundos_perdida']} · "
        f"revinculación={cfg.proc['revinculacion']}",
        "",
        "## Calidad del seguimiento",
        "",
        f"- Vehículos en eventos.csv: **{n}**",
        f"- Completos: {seg.get('completo', 0)} ({pct('completo')})",
        f"- Perdidos antes de salir (movimiento *desconocido*): {seg.get('perdido', 0)} ({pct('perdido')})",
        f"- Sin acceso (solo se vio la salida): {seg.get('sin_acceso', 0)} ({pct('sin_acceso')})",
        f"- Combinación acceso→salida no configurada: {seg.get('combinacion_no_configurada', 0)} ({pct('combinacion_no_configurada')})",
    ]
    if n:
        perd = ev[ev["seguimiento"] == "perdido"].groupby("acceso").size()
        tot = ev[ev["acceso"] != "desconocido"].groupby("acceso").size()
        if len(tot):
            lineas += ["", "| Acceso | Vehículos | Perdidos | % perdidos |", "|---|---:|---:|---:|"]
            for acc, t in tot.items():
                p = int(perd.get(acc, 0))
                lineas.append(f"| {acc} | {t} | {p} | {100 * p / t:.1f}% |")
    if stats_videos:
        lineas += ["", "## Videos procesados", ""]
        for nombre, s in stats_videos.items():
            lineas.append(f"- `{nombre}`: {s.get('segundos', '?')} s, {s.get('frames', '?')} frames, "
                          f"{s.get('fps', 0):.2f} fps · revinculaciones={s.get('revinculaciones', 0)} · "
                          f"IDs sin cruce de línea={s.get('sin_cruce', 0)} · cambios de semáforo={s.get('cambios_semaforo', 0)}")
    if stats_agr:
        lineas += ["", "## Agregación", "",
                   f"- Eventos usados en conteos: {stats_agr.get('eventos_utiles')} de {stats_agr.get('eventos_totales')}",
                   f"- Eliminados por ventanas descartadas: {stats_agr.get('descartados_por_ventana')} "
                   f"({stats_agr.get('ventanas_descartadas')} ventanas)"]
    sem_visibles = [s.id for s in cfg.semaforos if s.visible]
    lineas += ["", "## Semáforo y filas", "",
               f"- Semáforos evaluados por visión: {', '.join(sem_visibles) if sem_visibles else 'ninguno (semaforo_eventos.csv vacío)'}",
               "- El plan de fases completo NO se infiere automáticamente: se documenta manualmente."]
    if validacion is not None and len(validacion):
        tot = validacion[validacion["nivel"] == "total"]
        if len(tot):
            r = tot.iloc[0]
            lineas += ["", "## Validación contra conteo manual", "",
                       f"- Total manual={r['manual']}, automático={r['automatico']}, "
                       f"error={r['error_pct']}%, GEH={r['geh']}"]
    lineas += ["", "<details><summary>Parámetros del tracker</summary>", "", "```yaml",
               tracker_txt.strip(), "```", "", "</details>"]
    return "\n".join(lineas)


def verificar_contrato(carpeta: Path) -> tuple[list, list]:
    """Devuelve la lista de archivos del contrato que faltan y avisa de archivos extra."""
    faltan = [a for a in ARCHIVOS_CONTRATO if not (carpeta / a).exists()]
    extra = [p.name for p in carpeta.iterdir() if p.is_file() and not p.name.startswith(".")
             and p.name not in ARCHIVOS_CONTRATO] if carpeta.exists() else []
    return faltan, extra
