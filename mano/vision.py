"""
Visión artificial: detección de la mano con MediaPipe HandLandmarker (API Tasks),
cálculo de la apertura de cada dedo, calibración y reconocimiento de gestos.
"""
import json
import math
import os
import time
import urllib.request
from dataclasses import dataclass, field

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

DIRECTORIO_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_MODELO = os.path.join(DIRECTORIO_PROYECTO, "models", "hand_landmarker.task")
URL_MODELO = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
              "hand_landmarker/float16/latest/hand_landmarker.task")
RUTA_CALIBRACION = os.path.join(DIRECTORIO_PROYECTO, "calibracion.json")

DEDOS_NOMBRES = ["PULGAR", "INDICE", "MEDIO", "ANULAR", "MENIQUE"]
DEDOS_NOMBRES_BONITOS = ["Pulgar", "Índice", "Medio", "Anular", "Meñique"]
# Cadenas articulares de cada dedo (muñeca, MCP, PIP, DIP, TIP)
CADENAS = [None, [0, 5, 6, 7, 8], [0, 9, 10, 11, 12], [0, 13, 14, 15, 16], [0, 17, 18, 19, 20]]
TIPS = [4, 8, 12, 16, 20]

# Métrica cruda por dedo con mano abierta / puño (se ajusta calibrando).
# Pulgar: distancia punta-base del meñique / ancho de palma. Resto: grados de flexión.
CALIBRACION_DEFECTO = {"abierto": [1.75, 20, 20, 20, 25], "cerrado": [0.95, 200, 210, 205, 195]}

CONEXIONES_MANO = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
                   (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
                   (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


# ==========================================
# Geometría y métricas
# ==========================================
def vector(a, b):
    return np.array([b.x - a.x, b.y - a.y, b.z - a.z])


def distancia(a, b):
    return float(np.linalg.norm(vector(a, b)))


def angulo_flexion(a, b, c):
    """Grados que se dobla la articulación b (0 = recta)."""
    v1, v2 = vector(a, b), vector(b, c)
    coseno = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
    return math.degrees(math.acos(float(np.clip(coseno, -1.0, 1.0))))


def metricas_crudas(lm):
    """Una métrica por dedo, usando las coordenadas 3D en metros (world landmarks)."""
    ancho_palma = distancia(lm[5], lm[17]) + 1e-6
    valores = [distancia(lm[4], lm[17]) / ancho_palma]
    for cadena in CADENAS[1:]:
        flexion = sum(angulo_flexion(lm[cadena[k]], lm[cadena[k + 1]], lm[cadena[k + 2]])
                      for k in range(3))
        valores.append(flexion)
    return valores


def a_porcentaje(valores, calib):
    """Convierte métricas crudas a % de apertura usando la calibración."""
    salida = []
    for v, abierto, cerrado in zip(valores, calib["abierto"], calib["cerrado"]):
        rango = abierto - cerrado
        pct = (v - cerrado) / rango * 100 if abs(rango) > 1e-6 else 100
        salida.append(float(np.clip(pct, 0, 100)))
    return salida


# ==========================================
# Calibración de la cámara
# ==========================================
def calibracion_defecto():
    return json.loads(json.dumps(CALIBRACION_DEFECTO))


def calibracion_valida(datos):
    try:
        return (len(datos["abierto"]) == 5 and len(datos["cerrado"]) == 5 and
                all(isinstance(v, (int, float)) for v in datos["abierto"] + datos["cerrado"]))
    except (KeyError, TypeError):
        return False


def cargar_calibracion(ruta=None):
    ruta = ruta or RUTA_CALIBRACION
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        if calibracion_valida(datos):
            return datos
    except (OSError, ValueError):
        pass
    return calibracion_defecto()


def guardar_calibracion(calib, ruta=None):
    with open(ruta or RUTA_CALIBRACION, "w", encoding="utf-8") as f:
        json.dump(calib, f, indent=2)


class Calibrador:
    """Toma muestras durante un tiempo y guarda la mediana como 'abierto' o 'cerrado'."""

    def __init__(self, duracion=1.0):
        self.duracion = duracion
        self.tipo = None
        self.fin = 0.0
        self.muestras = []

    @property
    def activo(self):
        return self.tipo is not None

    def restante(self):
        return max(0.0, self.fin - time.time()) if self.activo else 0.0

    def iniciar(self, tipo):
        if tipo not in ("abierto", "cerrado"):
            raise ValueError(tipo)
        self.tipo, self.fin, self.muestras = tipo, time.time() + self.duracion, []

    def cancelar(self):
        self.tipo = None

    def agregar(self, crudas, calib):
        """Devuelve el tipo calibrado cuando termina (y actualiza calib), o None."""
        if not self.activo:
            return None
        self.muestras.append(crudas)
        if time.time() < self.fin:
            return None
        tipo = self.tipo
        self.tipo = None
        if len(self.muestras) < 3:
            return None
        calib[tipo] = [float(np.median(col)) for col in zip(*self.muestras)]
        return tipo


# ==========================================
# Filtro y gestos
# ==========================================
class FiltroDedos:
    """Suavizado exponencial + estado binario con histéresis."""

    def __init__(self, suavizado=0.45, umbral_abrir=60, umbral_cerrar=40):
        self.suavizado = suavizado
        self.umbral_abrir = umbral_abrir
        self.umbral_cerrar = umbral_cerrar
        self.porcentajes = [100.0] * 5
        self.estados = [1] * 5

    def actualizar(self, objetivo):
        a = self.suavizado
        self.porcentajes = [p + a * (o - p) for p, o in zip(self.porcentajes, objetivo)]
        self.estados = [1 if p > self.umbral_abrir else 0 if p < self.umbral_cerrar else e
                        for p, e in zip(self.porcentajes, self.estados)]
        return self.porcentajes


GESTOS_BINARIOS = {
    (0, 0, 0, 0, 0): "PUNO CERRADO",
    (0, 1, 1, 0, 0): "PAZ / VICTORIA",
    (1, 1, 0, 0, 1): "ROCK / SPIDERMAN",
    (1, 1, 0, 0, 0): "PISTOLA",
    (0, 1, 0, 0, 0): "APUNTAR",
    (1, 0, 0, 0, 0): "PULGAR ARRIBA",
    (1, 0, 0, 0, 1): "TELEFONO",
}


def clasificar_gesto(dedos, lm):
    """Reconoce posturas de la mano a partir del estado binario de los dedos."""
    clave = tuple(dedos)
    if clave in GESTOS_BINARIOS:
        return GESTOS_BINARIOS[clave]
    if clave[2:] == (1, 1, 1) and distancia(lm[4], lm[8]) < 0.025:
        return "GESTO OK"
    if clave == (1, 1, 1, 1, 1):
        return "SALUDO VULCANO (SPOCK)" if distancia(lm[12], lm[16]) > 0.035 else "MANO COMPLETA"
    return "MOVIMIENTO LIBRE"


# ==========================================
# Detector
# ==========================================
def asegurar_modelo(ruta=None, progreso=print):
    ruta = ruta or RUTA_MODELO
    if os.path.exists(ruta):
        return ruta
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    progreso("[SISTEMA] Descargando el modelo de MediaPipe (~8 MB)...")
    try:
        urllib.request.urlretrieve(URL_MODELO, ruta + ".tmp")
        os.replace(ruta + ".tmp", ruta)
    except OSError as err:
        raise RuntimeError(f"No se pudo descargar el modelo: {err}\n"
                           f"Descárgalo a mano desde {URL_MODELO} y guárdalo en {ruta}") from err
    return ruta


@dataclass
class ResultadoMano:
    detectada: bool = False
    landmarks_imagen: list = field(default_factory=list)   # normalizados 0..1 (para dibujar)
    landmarks_mundo: list = field(default_factory=list)    # metros (para medir)
    crudas: list = field(default_factory=list)
    lateralidad: str = ""


class DetectorMano:
    """Envuelve HandLandmarker en modo VIDEO gestionando los timestamps."""

    def __init__(self, ruta_modelo=None, confianza=0.7):
        ruta = asegurar_modelo(ruta_modelo)
        opciones = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=ruta),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=confianza,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._detector = vision.HandLandmarker.create_from_options(opciones)
        self._t0 = time.monotonic()
        self._ultimo_ts = -1

    def procesar(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = max(int((time.monotonic() - self._t0) * 1000), self._ultimo_ts + 1)
        self._ultimo_ts = ts
        res = self._detector.detect_for_video(imagen, ts)
        if not res.hand_landmarks:
            return ResultadoMano()
        lado = res.handedness[0][0].category_name if res.handedness else ""
        mundo = res.hand_world_landmarks[0]
        return ResultadoMano(True, res.hand_landmarks[0], mundo, metricas_crudas(mundo), lado)

    def cerrar(self):
        if self._detector is not None:
            self._detector.close()
            self._detector = None


def dibujar_mano(img, lm_img, estados):
    """Dibuja el esqueleto de la mano sobre la imagen BGR."""
    h, w = img.shape[:2]
    puntos = [(int(p.x * w), int(p.y * h)) for p in lm_img]
    for a, b in CONEXIONES_MANO:
        cv2.line(img, puntos[a], puntos[b], (230, 230, 230), 2)
    for p in puntos:
        cv2.circle(img, p, 4, (0, 140, 255), cv2.FILLED)
    for i, tip in enumerate(TIPS):
        col = (0, 255, 0) if estados[i] else (0, 0, 255)
        cv2.circle(img, puntos[tip], 8, col, cv2.FILLED)
        cv2.circle(img, puntos[tip], 14, col, 2)
