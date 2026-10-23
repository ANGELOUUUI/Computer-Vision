"""
Herramienta interactiva para obtener coordenadas en pixeles sobre un frame del video.

Uso:  python main.py puntos --video videos/oxxo/archivo.mp4 [--segundo 10]
  - Clic izquierdo : agrega un punto (se imprime en consola)
  - z              : deshace el último punto
  - c              : imprime los puntos como lista YAML y limpia
  - q / Esc        : salir

Las coordenadas impresas están en la resolución ORIGINAL del video aunque la
ventana se muestre reducida, así se pueden pegar directamente en config.yaml.
"""
from __future__ import annotations

import cv2

from .diagrama import leer_frame


def seleccionar_puntos(video: str, segundo: float = 5.0, ancho_max: int = 1400) -> None:
    frame = leer_frame(video, segundo)
    h, w = frame.shape[:2]
    escala = min(1.0, ancho_max / w)
    puntos: list[tuple[int, int]] = []
    ventana = "Selector de puntos (clic: punto | z: deshacer | c: imprimir | q: salir)"

    def redibujar():
        img = cv2.resize(frame, (int(w * escala), int(h * escala))) if escala < 1 else frame.copy()
        for i, (x, y) in enumerate(puntos):
            p = (int(x * escala), int(y * escala))
            cv2.circle(img, p, 5, (0, 255, 255), -1)
            cv2.putText(img, f"{i}:{x},{y}", (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            if i:
                q = puntos[i - 1]
                cv2.line(img, (int(q[0] * escala), int(q[1] * escala)), p, (0, 255, 255), 1)
        cv2.imshow(ventana, img)

    def clic(evento, x, y, *_):
        if evento == cv2.EVENT_LBUTTONDOWN:
            px, py = int(round(x / escala)), int(round(y / escala))
            puntos.append((px, py))
            print(f"  punto {len(puntos) - 1}: [{px}, {py}]")
            redibujar()

    cv2.namedWindow(ventana, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(ventana, clic)
    redibujar()
    print(f"Frame {w}x{h} en t={segundo}s. Haz clic sobre la imagen.")
    while True:
        k = cv2.waitKey(50) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("z") and puntos:
            puntos.pop()
            redibujar()
        if k == ord("c") and puntos:
            print("YAML ->", "[" + ", ".join(f"[{x}, {y}]" for x, y in puntos) + "]")
            puntos.clear()
            redibujar()
    if puntos:
        print("YAML ->", "[" + ", ".join(f"[{x}, {y}]" for x, y in puntos) + "]")
    cv2.destroyAllWindows()
