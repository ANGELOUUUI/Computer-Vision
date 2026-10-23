"""
Agregaciones temporales a partir de eventos.csv:
  * conteos_5min.csv          vehículos por acceso, movimiento y clase cada 5 min
  * tau_10min.csv             vehículos por acceso cada 10 min (formato τ de Wu)
  * proporciones_vuelta.csv   fracción de cada vuelta por acceso (total y por clase)

Reglas:
  * El tiempo de referencia de cada vehículo es su cruce de la línea de ACCESO
    (timestamp real del video, no número de frame).
  * Se excluyen los vehículos cuyo acceso cae en una ventana de
    ventanas_descartadas.csv (y esos intervalos se marcan con valido = False).
  * Los vehículos con acceso "desconocido" (seguimiento sin_acceso) no entran
    a los conteos por acceso; se reportan en notas.md.
  * La rejilla incluye intervalos con 0 vehículos, y la columna `cobertura`
    indica qué fracción del intervalo tiene video (intervalos de borde < 1).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import MOVIMIENTOS_VALIDOS, MOVIMIENTO_DESCONOCIDO

COLUMNAS_DESCARTES = ["fecha", "hora_inicio", "hora_fin", "acceso", "motivo"]


# ---------------------------------------------------------------------------
# Lectura de insumos
# ---------------------------------------------------------------------------
def leer_eventos(ruta: Path) -> pd.DataFrame:
    ev = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    ev["t_acceso"] = pd.to_datetime(ev["t_acceso"].replace("", None), errors="coerce")
    ev["t_salida"] = pd.to_datetime(ev["t_salida"].replace("", None), errors="coerce")
    return ev


def leer_spans_video(ruta_videos: Path) -> list:
    """Intervalos [inicio, fin) con video, a partir de videos.csv."""
    spans = []
    if not ruta_videos.exists() or ruta_videos.stat().st_size == 0:
        return spans
    df = pd.read_csv(ruta_videos, dtype=str, keep_default_na=False)
    for _, r in df.iterrows():
        try:
            ini = pd.Timestamp(f"{r['fecha']} {r['hora_inicio']}")
            fin = ini + pd.to_timedelta(float(r["duracion_s"]), unit="s")
            spans.append((ini, fin))
        except (ValueError, KeyError):
            continue
    return spans


def leer_descartes(ruta: Path) -> list:
    """Lista de (inicio, fin, acceso|None, motivo). acceso vacío = aplica a todo el cruce."""
    if not ruta.exists() or ruta.stat().st_size == 0:
        return []
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    out = []
    for _, r in df.iterrows():
        if not r.get("fecha") or not r.get("hora_inicio") or not r.get("hora_fin"):
            continue
        ini = pd.Timestamp(f"{r['fecha']} {r['hora_inicio']}")
        fin = pd.Timestamp(f"{r['fecha']} {r['hora_fin']}")
        out.append((ini, fin, (r.get("acceso") or "").strip() or None, r.get("motivo", "")))
    return out


def _en_descarte(t, acceso, descartes) -> bool:
    if pd.isna(t):
        return False
    return any(ini <= t < fin and (acc is None or acc == acceso) for ini, fin, acc, _ in descartes)


def _intervalo_valido(ini, fin, acceso, descartes) -> bool:
    return not any(d_ini < fin and ini < d_fin and (acc is None or acc == acceso)
                   for d_ini, d_fin, acc, _ in descartes)


def _rejilla(spans, ev_t: pd.Series, freq: str) -> pd.DatetimeIndex:
    """Inicios de intervalo que cubren todos los videos (o, sin videos.csv, los eventos)."""
    puntos = []
    for ini, fin in spans:
        puntos += list(pd.date_range(ini.floor(freq), fin - pd.Timedelta(microseconds=1), freq=freq))
    puntos += list(ev_t.dropna().dt.floor(freq).unique())
    return pd.DatetimeIndex(sorted(set(puntos)))


def _cobertura(ini, fin, spans) -> float:
    if not spans:
        return 1.0
    seg = sum(max(0.0, (min(fin, f) - max(ini, i)).total_seconds()) for i, f in spans)
    return round(min(1.0, seg / (fin - ini).total_seconds()), 4)


def eventos_utiles(ev: pd.DataFrame, descartes) -> pd.DataFrame:
    """Eventos con acceso conocido y fuera de ventanas descartadas."""
    ev = ev[(ev["acceso"] != MOVIMIENTO_DESCONOCIDO) & ev["t_acceso"].notna()].copy()
    if descartes:
        mask = [not _en_descarte(t, a, descartes) for t, a in zip(ev["t_acceso"], ev["acceso"])]
        ev = ev[mask]
    return ev


# ---------------------------------------------------------------------------
# Agregaciones
# ---------------------------------------------------------------------------
def conteos_por_intervalo(cfg, ev, spans, descartes, minutos: int) -> pd.DataFrame:
    freq = f"{minutos}min"
    ev = ev.assign(intervalo_inicio=ev["t_acceso"].dt.floor(freq))
    rejilla = _rejilla(spans, ev["t_acceso"], freq)
    filas = []
    for a in cfg.accesos:
        movs = cfg.movimientos_de(a.id) + [MOVIMIENTO_DESCONOCIDO]
        for mov in movs:
            for cl in cfg.nombres_clases:
                for ini in rejilla:
                    filas.append((ini, a.id, mov, cl))
    base = pd.DataFrame(filas, columns=["intervalo_inicio", "acceso", "movimiento", "clase"])
    cnt = ev.groupby(["intervalo_inicio", "acceso", "movimiento", "clase"]).size().rename("vehiculos").reset_index()
    df = base.merge(cnt, how="outer", on=["intervalo_inicio", "acceso", "movimiento", "clase"])
    df["vehiculos"] = df["vehiculos"].fillna(0).astype(int)
    delta = pd.Timedelta(minutes=minutos)
    df["intervalo_fin"] = df["intervalo_inicio"] + delta
    df["cobertura"] = [_cobertura(i, i + delta, spans) for i in df["intervalo_inicio"]]
    df["valido"] = [_intervalo_valido(i, i + delta, a, descartes)
                    for i, a in zip(df["intervalo_inicio"], df["acceso"])]
    df = df.sort_values(["intervalo_inicio", "acceso", "movimiento", "clase"])
    return df[["intervalo_inicio", "intervalo_fin", "acceso", "movimiento", "clase",
               "vehiculos", "cobertura", "valido"]]


def tau(cfg, ev, spans, descartes, minutos: int) -> pd.DataFrame:
    """
    Formato τ: un renglón por (intervalo de 10 min, acceso) con el número de
    vehículos que entran y el flujo equivalente en veh/h (corrigiendo cobertura).
    """
    freq = f"{minutos}min"
    ev = ev.assign(intervalo_inicio=ev["t_acceso"].dt.floor(freq))
    rejilla = _rejilla(spans, ev["t_acceso"], freq)
    base = pd.MultiIndex.from_product([rejilla, [a.id for a in cfg.accesos]],
                                      names=["intervalo_inicio", "acceso"]).to_frame(index=False)
    cnt = ev.groupby(["intervalo_inicio", "acceso"]).size().rename("vehiculos").reset_index()
    df = base.merge(cnt, how="outer", on=["intervalo_inicio", "acceso"])
    df["vehiculos"] = df["vehiculos"].fillna(0).astype(int)
    delta = pd.Timedelta(minutes=minutos)
    df["intervalo_fin"] = df["intervalo_inicio"] + delta
    df["tau"] = df.groupby("acceso").cumcount() + 1          # índice del intervalo τ por acceso
    df["cobertura"] = [_cobertura(i, i + delta, spans) for i in df["intervalo_inicio"]]
    horas = df["cobertura"] * minutos / 60.0
    df["flujo_veh_h"] = (df["vehiculos"] / horas.where(horas > 0)).round(1)
    df["valido"] = [_intervalo_valido(i, i + delta, a, descartes)
                    for i, a in zip(df["intervalo_inicio"], df["acceso"])]
    df = df.sort_values(["acceso", "intervalo_inicio"])
    return df[["tau", "intervalo_inicio", "intervalo_fin", "acceso", "vehiculos",
               "flujo_veh_h", "cobertura", "valido"]]


def proporciones(cfg, ev) -> pd.DataFrame:
    """
    Fracción de cada vuelta por acceso. El denominador son los vehículos con
    movimiento identificado; los 'desconocido' se reportan aparte para que se
    vea qué tan confiable es la proporción.
    """
    filas = []
    for clase in ["todas"] + cfg.nombres_clases:
        sub = ev if clase == "todas" else ev[ev["clase"] == clase]
        for a in cfg.accesos:
            sa = sub[sub["acceso"] == a.id]
            n_total = len(sa)
            n_desc = int((sa["movimiento"] == MOVIMIENTO_DESCONOCIDO).sum())
            n_ident = n_total - n_desc
            for mov in MOVIMIENTOS_VALIDOS:
                n = int((sa["movimiento"] == mov).sum())
                filas.append({
                    "acceso": a.id, "clase": clase, "movimiento": mov,
                    "permitido": (a.id, mov) in {(x, m) for (x, _), m in cfg.movimientos.items()},
                    "vehiculos": n, "identificados_acceso": n_ident,
                    "proporcion": round(n / n_ident, 4) if n_ident else "",
                    "desconocidos_acceso": n_desc,
                    "fraccion_desconocido": round(n_desc / n_total, 4) if n_total else "",
                })
    return pd.DataFrame(filas)


def generar_agregaciones(cfg, carpeta: Path) -> dict:
    ev = leer_eventos(carpeta / "eventos.csv")
    spans = leer_spans_video(carpeta / "videos.csv")
    descartes = leer_descartes(carpeta / "ventanas_descartadas.csv")
    util = eventos_utiles(ev, descartes)
    fmt = "%Y-%m-%d %H:%M:%S"

    c5 = conteos_por_intervalo(cfg, util, spans, descartes, int(cfg.agregacion["minutos_conteo"]))
    t10 = tau(cfg, util, spans, descartes, int(cfg.agregacion["minutos_tau"]))
    for df in (c5, t10):
        df["intervalo_inicio"] = df["intervalo_inicio"].dt.strftime(fmt)
        df["intervalo_fin"] = df["intervalo_fin"].dt.strftime(fmt)
    c5.to_csv(carpeta / "conteos_5min.csv", index=False, encoding="utf-8")
    t10.to_csv(carpeta / "tau_10min.csv", index=False, encoding="utf-8")
    proporciones(cfg, util).to_csv(carpeta / "proporciones_vuelta.csv", index=False, encoding="utf-8")
    return {"eventos_totales": len(ev), "eventos_utiles": len(util),
            "descartados_por_ventana": int(((ev["acceso"] != MOVIMIENTO_DESCONOCIDO) & ev["t_acceso"].notna()).sum()) - len(util),
            "ventanas_descartadas": len(descartes)}
