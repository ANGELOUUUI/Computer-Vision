# Pipeline de videos de cruces viales → datos para validar SUMO

Proyecto modular en Python que procesa videos de cruces (YOLO + ByteTrack/BoT-SORT)
y genera, **por cruce y de forma independiente**, exactamente los 14 archivos del
protocolo de investigación en `gdl/<cruce>/`.

```
cruces_sumo/
├── main.py                     # orquestador (CLI con subcomandos)
├── config.yaml                 # ejemplo completo: cruce OXXO
├── requirements.txt
├── trackers/
│   ├── bytetrack_oclusion.yaml # ByteTrack con track_buffer alto (default)
│   └── botsort_oclusion.yaml   # BoT-SORT + ReID + compensación de cámara
├── pipeline_cruces/
│   ├── config.py               # carga/validación del YAML
│   ├── geometria.py            # cruce de líneas, punto en polígono
│   ├── contador.py             # NÚCLEO: trayectorias -> eventos (acceso/salida/movimiento)
│   ├── semaforo.py             # estado del semáforo por HSV en ROIs
│   ├── filas.py                # vehículos detenidos en zona de cola al cambio de luz
│   ├── procesador_video.py     # bucle de video: YOLO.track + contador + semáforo + filas
│   ├── agregacion.py           # conteos_5min, tau_10min, proporciones_vuelta
│   ├── validacion.py           # automático vs manual (error % y GEH)
│   ├── inventario.py           # videos.csv
│   ├── salidas.py              # accesos/movimientos.csv, plantillas, notas.md, contrato
│   ├── diagrama.py             # diagrama.png y video de depuración
│   └── selector_puntos.py      # clic sobre un frame para obtener coordenadas
├── gdl/
│   ├── oxxo/                   # <- aquí quedan los 14 archivos de cada cruce
│   ├── plaza/
│   └── mangueras/
├── videos/                     # (tuyo) videos crudos, p. ej. videos/oxxo/*.mp4
├── logs/                       # (se crea) log y estadísticas por cruce
└── depuracion/                 # (se crea) videos anotados con --video-depuracion
```

`logs/` y `depuracion/` están **fuera** de la carpeta del cruce para no romper el contrato.

---

## 1. Instalación

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# GPU (opcional): instala antes PyTorch con CUDA desde pytorch.org
```

La primera ejecución descarga `yolo11n.pt` automáticamente.

---

## 2. Configurar un cruce (paso a paso)

1. **Copia el ejemplo**: `config.yaml` es el cruce OXXO. Para los otros:
   `cp config.yaml config_plaza.yaml` y cambia `cruce.id`, `cruce.carpeta_salida`
   (`gdl/plaza`) y la lista de `videos`.
2. **Videos**: pon la ruta de cada archivo y su `inicio` (fecha-hora real del primer
   frame, p. ej. leída del reloj de la cámara). Todos los timestamps salen de ahí +
   la posición del frame, así que es el dato más importante.
3. **Obtén coordenadas** sobre un frame:
   ```bash
   python main.py puntos --config config_plaza.yaml --segundo 10
   ```
   Clic = punto (se imprime en consola en pixeles originales), `z` deshace,
   `c` imprime la lista lista para pegar en YAML, `q` sale.
4. **Define en el YAML**
   - `accesos`: una `linea` (2 puntos) que cruce **solo los carriles de entrada**,
     un punto `hacia` del lado al que avanza el vehículo, su `orden` geométrico
     (sentido horario desde el norte), su `zona_cola` (polígono aguas arriba) y el
     `semaforo` que lo controla.
   - `salidas`: igual, con `hacia` apuntando hacia afuera del cruce.
   - `movimientos`: la tabla acceso → salida → `izquierda | frente | derecha | U`.
     Omite las combinaciones prohibidas.
   - `semaforos`: cajas `[x, y, ancho, alto]` por foco (`focos`) o de toda la cabeza
     (`roi`). Si no se ve, `visible: false`.
   - `modelo.clases`: mapeo id de clase → nombre del estudio.
5. **Valida visualmente**:
   ```bash
   python main.py diagrama --config config_plaza.yaml
   ```
   Abre `gdl/plaza/diagrama.png`: líneas verdes = accesos, rojas = salidas,
   flechas = sentido válido, amarillo = zonas de cola, magenta = ROIs de semáforo.

> El pipeline **no** infiere geometría (carriles, retornos) ni el plan de fases del
> semáforo: todo eso es configuración/manual, tal como pide el protocolo.

---

## 3. Correr el pipeline

```bash
# Inicializar carpeta y plantillas de captura manual
python main.py init --config config.yaml

# Prueba rápida: 2 minutos + video anotado para revisar IDs, accesos y semáforo
python main.py procesar --config config.yaml --max-segundos 120 --video-depuracion

# Corrida completa de un cruce
python main.py procesar --config config.yaml

# Los tres cruces, uno tras otro (si uno falla, los demás siguen)
python main.py todos config.yaml config_plaza.yaml config_mangueras.yaml

# Tras capturar conteo_manual.csv o ventanas_descartadas.csv: recalcular SIN volver a correr YOLO
python main.py agregar --config config.yaml

# Solo validación / revisar contrato
python main.py validar   --config config.yaml
python main.py verificar --config config.yaml
```

Flujo interno de `procesar`:
`plantillas → accesos/movimientos/videos.csv → diagrama.png → (por video: YOLO.track
→ cruces de línea → semáforo → filas) → eventos/semaforo_eventos/filas.csv →
agregaciones → validación → notas.md → verificación del contrato`.

---

## 4. Archivos que se generan (el contrato)

| # | Archivo | Origen | Contenido |
|---|---|---|---|
| 1 | `accesos.csv` | config | id, nombre, tipo (acceso/salida), orden, coordenadas, semáforo |
| 2 | `movimientos.csv` | config | acceso, salida, movimiento |
| 3 | `diagrama.png` | código | frame con líneas, sentidos, zonas de cola y ROIs |
| 4 | `eventos.csv` | código | **un renglón por vehículo** (ver abajo) |
| 5 | `conteos_5min.csv` | agregación | intervalo, acceso, movimiento, clase, vehiculos, cobertura, valido |
| 6 | `tau_10min.csv` | agregación | tau, intervalo, acceso, vehiculos, flujo_veh_h, cobertura, valido |
| 7 | `proporciones_vuelta.csv` | agregación | por acceso y clase (y `todas`): fracción de cada vuelta |
| 8 | `semaforo_eventos.csv` | visión | semaforo, timestamp, frame, estado, estado_anterior, score |
| 9 | `filas.csv` | visión | acceso, ciclo, evento (inicio_verde/fin_verde), vehiculos_en_fila, ids |
| 10 | `videos.csv` | inventario | archivo, fecha, hora_inicio, duración, fps, frames, resolución, clima, luz, incidencias |
| 11 | `ventanas_descartadas.csv` | **manual** | fecha, hora_inicio, hora_fin, acceso (vacío = todo el cruce), motivo |
| 12 | `conteo_manual.csv` | **manual** | fecha, bloque_inicio, bloque_fin, acceso, movimiento, clase, vehiculos, condicion, observador |
| 13 | `validacion.csv` | script | manual vs automático: error %, error absoluto %, GEH |
| 14 | `notas.md` | mixto | sección automática (modelo, tracker, % perdidos…) + sección manual |

Los archivos manuales (11, 12 y la sección manual de `notas.md`) **nunca se
sobrescriben**; si no existen se crean solo con encabezados.

### `eventos.csv`

| Columna | Significado |
|---|---|
| `video`, `track_id` | archivo y ID del tracker (los IDs reinician por video) |
| `clase`, `conf_clase` | clase por voto mayoritario a lo largo de la trayectoria y fracción de frames con esa clase |
| `acceso`, `salida`, `movimiento` | según las líneas cruzadas y `movimientos.csv` |
| `t_acceso`, `t_salida` | timestamp **real** (inicio del video + posición del frame) |
| `frame_acceso`, `frame_salida` | para ubicar el evento en el video |
| `seguimiento` | `completo` · `perdido` (cruzó acceso, se perdió antes de salir → movimiento *desconocido*) · `sin_acceso` (solo se vio la salida) · `combinacion_no_configurada` |
| `ids_vinculados` | IDs anteriores que se fusionaron por re-vinculación tras una oclusión |

### Reglas de agregación

- Referencia temporal = cruce de la línea de **acceso**.
- Se excluyen vehículos en `ventanas_descartadas.csv`; los intervalos afectados
  quedan con `valido = False` (no los uses para calibrar).
- `cobertura` = fracción del intervalo con video (los intervalos de borde valen < 1);
  `flujo_veh_h` en `tau_10min.csv` ya corrige por cobertura.
- Los de movimiento `desconocido` sí cuentan en el total del acceso (τ) pero no en
  el denominador de `proporciones_vuelta.csv`, que reporta aparte
  `fraccion_desconocido` para saber qué tan confiable es cada proporción.
- `tau_10min.csv` está en formato largo (un renglón por intervalo × acceso). Si tu
  formulación de τ de Wu requiere otra forma (p. ej. matriz intervalo × acceso),
  es un `pivot` directo de este archivo.

### Validación

`conteo_manual.csv` (1 h por cruce, bloques de 15 min). `condicion` libre:
`normal`, `lluvia`, `poca_luz`, `hora_pico` (combina con `+`). Ejemplo:

```csv
fecha,bloque_inicio,bloque_fin,acceso,movimiento,clase,vehiculos,condicion,observador
2026-10-15,07:30:00,07:45:00,N,frente,auto,41,hora_pico,DF
2026-10-15,07:30:00,07:45:00,N,izquierda,camion,3,hora_pico,DF
```

`validacion.csv` trae niveles `detalle`, `acceso`, `acceso_movimiento`, `clase`,
`condicion` y `total`. `error_pct = (auto − manual) / manual × 100` (positivo =
sobreconteo) y `geh` sobre flujos horarios equivalentes (GEH < 5 suele aceptarse).
A nivel `acceso` se usan todos los vehículos del acceso (incluidos los de movimiento
desconocido); a nivel movimiento, solo los identificados. La validación usa los
eventos sin filtrar por ventanas descartadas: no programes el conteo manual dentro
de una ventana descartada.

---

## 5. Decisiones técnicas

### Detección y tracking
- `ultralytics` con `yolo11n.pt` por defecto (o `yolov8n.pt`). Para pickups:
  reentrena, pon `modelo.pesos: modelos/best.pt` y ajusta `modelo.clases` a los ids
  de tu `data.yaml`. El log avisa si un id de clase no existe en el modelo.
- `model.track(frame, persist=True, tracker=...)` frame a frame (no `stream`), para
  tener el timestamp exacto de cada frame y medir el semáforo en el mismo frame.
- Se crea un modelo nuevo por video para que el tracker empiece limpio.
- Punto de referencia del vehículo = **centro inferior de la caja** (toca el piso;
  con cámara elevada es mucho más estable que el centro para cruzar líneas pintadas).

### Estrategia contra oclusiones (semáforo en primer plano, camiones cerca de la cámara)
1. **Tracker** (`trackers/bytetrack_oclusion.yaml`): `track_buffer: 120` (~4 s a
   30 fps) mantiene vivo un ID perdido esperando que reaparezca; `track_low_thresh:
   0.1` deja que ByteTrack asocie detecciones de baja confianza (vehículos tapados a
   medias); `match_thresh: 0.9` acepta reapariciones algo desplazadas.
2. **Contador** (`segundos_perdida: 4`): un ID no se cierra como *perdido* hasta
   pasar ese tiempo sin verlo.
3. **Re-vinculación** (`procesamiento.revinculacion`): si nace un ID nuevo a menos de
   `max_distancia_px` de donde desapareció hace menos de `max_segundos` un vehículo
   que ya cruzó su acceso y no ha salido, el ID nuevo hereda acceso, hora y clase.
   Queda trazado en `ids_vinculados`.
4. Si el % de *perdido* en `notas.md` sigue alto: cambia a
   `trackers/botsort_oclusion.yaml` (ReID por apariencia + compensación de
   movimiento de cámara), sube `imgsz` o mueve las líneas lejos de la zona tapada.

Riesgo: buffers muy grandes pueden hacer que un ID "salte" de un vehículo a otro.
Revísalo siempre con `--video-depuracion`.

### Semáforo
- Máscaras HSV con `cv2.inRange` por color; con `focos` cada foco se evalúa solo con
  su color (más robusto que una sola `roi`).
- Anti-parpadeo: un cambio se acepta tras `frames_estables` muestras iguales. Si
  ningún color supera `umbral_min` (semáforo tapado), se conserva el último estado.
- Si no hay semáforos con `visible: true`, `semaforo_eventos.csv` y `filas.csv` quedan
  vacíos (solo encabezados).
- Calibración: si no detecta, revisa los rangos HSV en `semaforo.rangos_hsv` (las
  cámaras suelen saturar el verde hacia cian y el rojo hacia naranja de noche).

### Filas
- En el frame en que se confirma el cambio a verde (`inicio_verde`) y a rojo
  (`fin_verde`) se cuentan los IDs dentro de la `zona_cola` con velocidad menor a
  `velocidad_max_px_s`. El ciclo aumenta con cada inicio de verde.
- El umbral está en px/s: ajústalo según la escala de la imagen (vehículos lejanos
  se mueven menos pixeles).

---

## 6. Problemas conocidos y recomendaciones

- `inicio` mal capturado desplaza todos los conteos: verifícalo con un evento visible
  (p. ej. el primer cambio de semáforo) contra el reloj de la cámara.
- Videos con fps variable (celulares): el timestamp se toma de
  `CAP_PROP_POS_MSEC`, que respeta el tiempo real; si el contenedor no lo reporta, se
  usa `frame / fps`.
- Un vehículo que entra a cuadro ya pasado el acceso queda como `sin_acceso`; si es
  frecuente, mueve la línea de acceso hacia el cruce.
- El borrado de placas/caras **no** es parte de este pipeline (paso posterior del paper).

La lógica (cruces de línea, re-vinculación, semáforo, filas, agregación y validación)
se probó de punta a punta con un video sintético y un tracker simulado; antes de la
corrida completa haz una prueba de 2 minutos con `--video-depuracion` sobre el video real.
