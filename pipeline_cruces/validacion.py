"""
Validación: conteo automático (eventos.csv) vs conteo manual (conteo_manual.csv).

conteo_manual.csv (una fila por bloque de 15 min, acceso, movimiento y clase):
    fecha, bloque_inicio, bloque_fin, acceso, movimiento, clase, vehiculos, condicion, observador
    condicion: normal | lluvia | poca_luz | hora_pico (puede combinarse con '+')

validacion.csv contiene varios niveles de comparación (columna `nivel`):
    detalle            cada fila del conteo manual
    acceso             suma de todos los bloques por acceso (usa TODOS los eventos del acceso,
                       incluso los de movimiento desconocido)
    acceso_movimiento  por acceso y movimiento
    clase              por tipo de vehículo
    condicion          por condición del bloque (lluvia, poca luz, hora pico…)
    total              todo el cruce

Métricas:
    error_pct = (automatico - manual) / manual * 100   (signo: + sobreconteo, - subconteo)
    geh       = sqrt(2 (A - M)^2 / (A + M)) calculado sobre flujos horarios equivalentes,
                criterio habitual de calibración (GEH < 5 aceptable).
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from . import MOVIMIENTO_DESCONOCIDO

COLUMNAS_MANUAL = ["fecha", "bloque_inicio", "bloque_fin", "acceso", "movimiento", "clase",
                   "vehiculos", "condicion", "observador"]
COLUMNAS_VALIDACION = ["nivel", "fecha", "bloque_inicio", "bloque_fin", "condicion", "acceso",
                       "movimiento", "clase", "minutos", "manual", "automatico", "diferencia",
                       "error_pct", "error_abs_pct", "geh"]

TODOS = "*"


def _geh(manual, auto, minutos) -> float | str:
    if minutos <= 0:
        return ""
    m, a = manual * 60 / minutos, auto * 60 / minutos
    return round(math.sqrt(2 * (a - m) ** 2 / (a + m)), 2) if (a + m) > 0 else 0.0


def _fila(nivel, manual, auto, minutos, **claves) -> dict:
    dif = auto - manual
    err = round(100 * dif / manual, 2) if manual else ""
    return {"nivel": nivel, **{k: claves.get(k, TODOS) for k in
            ["fecha", "bloque_inicio", "bloque_fin", "condicion", "acceso", "movimiento", "clase"]},
            "minutos": minutos, "manual": int(manual), "automatico": int(auto), "diferencia": int(dif),
            "error_pct": err, "error_abs_pct": abs(err) if err != "" else "",
            "geh": _geh(manual, auto, minutos)}


def validar(carpeta: Path) -> pd.DataFrame:
    ruta_man = carpeta / "conteo_manual.csv"
    destino = carpeta / "validacion.csv"
    man = pd.read_csv(ruta_man, dtype=str, keep_default_na=False) if ruta_man.exists() else pd.DataFrame()
    if man.empty:
        pd.DataFrame(columns=COLUMNAS_VALIDACION).to_csv(destino, index=False, encoding="utf-8")
        return pd.DataFrame(columns=COLUMNAS_VALIDACION)

    ev = pd.read_csv(carpeta / "eventos.csv", dtype=str, keep_default_na=False)
    ev["t"] = pd.to_datetime(ev["t_acceso"].replace("", None), errors="coerce")

    man["vehiculos"] = pd.to_numeric(man["vehiculos"], errors="coerce").fillna(0).astype(int)
    man["ini"] = pd.to_datetime(man["fecha"] + " " + man["bloque_inicio"])
    man["fin"] = pd.to_datetime(man["fecha"] + " " + man["bloque_fin"])
    man["minutos"] = (man["fin"] - man["ini"]).dt.total_seconds() / 60

    def auto_en(ini, fin, acceso=None, movimiento=None, clase=None) -> int:
        m = (ev["t"] >= ini) & (ev["t"] < fin)
        if acceso is not None:
            m &= ev["acceso"] == acceso
        else:   # sin filtro de acceso: solo vehículos con acceso conocido (comparable con el manual)
            m &= ev["acceso"] != MOVIMIENTO_DESCONOCIDO
        if movimiento is not None:
            m &= ev["movimiento"] == movimiento
        if clase is not None:
            m &= ev["clase"] == clase
        return int(m.sum())

    filas = []
    # 1) Detalle: fila por fila del conteo manual
    for _, r in man.iterrows():
        auto = auto_en(r["ini"], r["fin"], r["acceso"], r["movimiento"], r["clase"])
        filas.append(_fila("detalle", r["vehiculos"], auto, r["minutos"], fecha=r["fecha"],
                           bloque_inicio=r["bloque_inicio"], bloque_fin=r["bloque_fin"],
                           condicion=r["condicion"], acceso=r["acceso"],
                           movimiento=r["movimiento"], clase=r["clase"]))

    # Bloques únicos (para no contar dos veces el automático en agregados)
    bloques = man[["fecha", "bloque_inicio", "ini", "fin", "minutos", "condicion"]].drop_duplicates(["ini", "fin"])
    minutos_tot = float(bloques["minutos"].sum())

    def agregado(nivel, filtro_man, kw_auto, bloques_sel, **claves):
        manual = int(man.loc[filtro_man, "vehiculos"].sum())
        auto = sum(auto_en(b["ini"], b["fin"], **kw_auto) for _, b in bloques_sel.iterrows())
        filas.append(_fila(nivel, manual, auto, float(bloques_sel["minutos"].sum()), **claves))

    for acc in sorted(man["acceso"].unique()):
        agregado("acceso", man["acceso"] == acc, {"acceso": acc}, bloques, acceso=acc)
        for mov in sorted(man.loc[man["acceso"] == acc, "movimiento"].unique()):
            agregado("acceso_movimiento", (man["acceso"] == acc) & (man["movimiento"] == mov),
                     {"acceso": acc, "movimiento": mov}, bloques, acceso=acc, movimiento=mov)
    for cl in sorted(man["clase"].unique()):
        agregado("clase", man["clase"] == cl, {"clase": cl}, bloques, clase=cl)
    for cond in sorted(man["condicion"].unique()):
        agregado("condicion", man["condicion"] == cond, {"acceso": None},
                 bloques[bloques["condicion"] == cond], condicion=cond)

    # Total: solo vehículos con acceso conocido para ser comparable con el manual por acceso
    manual_tot = int(man["vehiculos"].sum())
    auto_tot = sum(auto_en(b["ini"], b["fin"]) for _, b in bloques.iterrows())
    filas.append(_fila("total", manual_tot, auto_tot, minutos_tot))

    df = pd.DataFrame(filas, columns=COLUMNAS_VALIDACION)
    df.to_csv(destino, index=False, encoding="utf-8")
    return df
