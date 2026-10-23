"""Funciones geométricas básicas: cruce de líneas y pertenencia a polígonos."""
from __future__ import annotations

import numpy as np
import cv2


def lado(a, b, p) -> float:
    """Producto cruz: >0 si p está a un lado de la recta a->b, <0 del otro, 0 sobre ella."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def segmentos_se_cruzan(p1, p2, q1, q2) -> bool:
    """
    ¿El desplazamiento p1->p2 atraviesa el segmento q1-q2?
    Se trata el valor 0 como "lado positivo" para no contar dos veces
    un punto que cae exactamente sobre la línea.
    """
    d1, d2 = lado(q1, q2, p1), lado(q1, q2, p2)
    if (d1 >= 0) == (d2 >= 0):
        return False
    d3, d4 = lado(p1, p2, q1), lado(p1, p2, q2)
    return d3 * d4 <= 0


def cruza_linea(prev, actual, linea) -> bool:
    """
    True si el vehículo pasó de `prev` a `actual` atravesando la línea.
    Si la línea define `hacia`, solo cuenta el cruce en ese sentido
    (el punto final debe quedar del mismo lado que `hacia`).
    """
    if not segmentos_se_cruzan(prev, actual, linea.p1, linea.p2):
        return False
    if linea.hacia is None:
        return True
    return (lado(linea.p1, linea.p2, actual) >= 0) == (lado(linea.p1, linea.p2, linea.hacia) >= 0)


def punto_en_poligono(p, poligono) -> bool:
    if not poligono:
        return False
    contorno = np.array(poligono, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contorno, (float(p[0]), float(p[1])), False) >= 0


def punto_referencia(xyxy, modo: str = "base") -> tuple:
    """Punto del vehículo usado para cruzar líneas: centro inferior (base) o centro."""
    x1, y1, x2, y2 = xyxy
    if modo == "centro":
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return ((x1 + x2) / 2.0, float(y2))
