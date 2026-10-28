"""
HandProyect - Control de mano biónica por visión artificial.

Lee tu mano con la webcam (MediaPipe HandLandmarker), calcula cuánto está
abierto cada dedo (0-100 %) y lo envía a la ESP32-S3 por USB o por WiFi.

Uso:
    python hand_control.py                      # USB, puerto autodetectado
    python hand_control.py --puerto /dev/ttyACM0
    python hand_control.py --wifi 192.168.4.1   # sin cable, por UDP
    python hand_control.py --sin-hardware       # solo visión, sin enviar nada

Teclas: [A] calibrar mano ABIERTA  [C] calibrar PUÑO  [R] borrar calibración
        [B] modo binario/proporcional  [D] demo en la ESP32  [ESC/Q] salir
"""
import argparse
import json
import math
import os
import socket
import sys
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
import serial
import serial.tools.list_ports
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
DIRECTORIO = os.path.dirname(os.path.abspath(__file__))
RUTA_MODELO = os.path.join(DIRECTORIO, "models", "hand_landmarker.task")
URL_MODELO = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
              "hand_landmarker/float16/latest/hand_landmarker.task")
RUTA_CALIBRACION = os.path.join(DIRECTORIO, "calibracion.json")

BAUD_RATE = 115200
PUERTO_UDP = 4210
INTERVALO_ENVIO = 1 / 30          # 30 Hz hacia la ESP32
SUAVIZADO = 0.45                  # 0..1, más alto = responde más rápido
DURACION_CALIBRACION = 1.0        # segundos de muestreo al calibrar

DEDOS_NOMBRES = ["PULGAR", "INDICE", "MEDIO", "ANULAR", "MENIQUE"]
# Cadenas articulares de cada dedo (MCP, PIP, DIP, TIP) desde la muñeca (0)
CADENAS = [None, [0, 5, 6, 7, 8], [0, 9, 10, 11, 12], [0, 13, 14, 15, 16], [0, 17, 18, 19, 20]]
TIPS = [4, 8, 12, 16, 20]

# Métrica cruda por dedo para mano abierta / puño (se ajusta con [A] y [C]).
# Pulgar: distancia punta-base del meñique / ancho de palma. Resto: grados de flexión.
CALIBRACION_DEFECTO = {"abierto": [1.75, 20, 20, 20, 25], "cerrado": [0.95, 200, 210, 205, 195]}

CONEXIONES_MANO = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
                   (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
                   (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


# ==========================================
# 2. COMUNICACIÓN CON LA ESP32-S3
# ==========================================
class EnlaceSerial:
    """USB con autodetección del puerto y reconexión automática."""

    # VID USB: Espressif (USB nativo S3), CH340/CH343, CP210x, FTDI
    VIDS_CONOCIDOS = {0x303A, 0x1A86, 0x10C4, 0x0403}

    def __init__(self, puerto=None):
        self.puerto_fijo = puerto
        self.conexion = None
        self.ultimo_intento = 0
        self.descripcion = "USB: desconectado"
        self.conectar()

    def buscar_puerto(self):
        puertos = list(serial.tools.list_ports.comports())
        for p in puertos:
            if p.vid in self.VIDS_CONOCIDOS:
                return p.device
        for p in puertos:
            if "ACM" in p.device or "USB" in p.device or p.device.upper().startswith("COM"):
                return p.device
        return None

    def conectar(self):
        self.ultimo_intento = time.time()
        puerto = self.puerto_fijo or self.buscar_puerto()
        if not puerto:
            self.descripcion = "USB: no se encuentra la ESP32"
            return
        try:
            # DTR/RTS a nivel bajo ANTES de abrir para no reiniciar la ESP32
            self.conexion = serial.Serial(baudrate=BAUD_RATE, timeout=0, write_timeout=0.05)
            self.conexion.port = puerto
            self.conexion.dtr = False
            self.conexion.rts = False
            self.conexion.open()
            time.sleep(0.3)
            self.conexion.reset_input_buffer()
            self.descripcion = f"USB: {puerto}"
            print(f"[SISTEMA] Conectado a la ESP32 en {puerto}")
        except (serial.SerialException, OSError) as err:
            self.conexion = None
            self.descripcion = f"USB: error en {puerto}"
            print(f"[ADVERTENCIA] No se pudo abrir {puerto}: {err}")

    def enviar(self, linea):
        if self.conexion is None:
            if time.time() - self.ultimo_intento > 2.0:
                self.conectar()
            return
        try:
            self.conexion.write((linea + "\n").encode("utf-8"))
            if self.conexion.in_waiting:
                texto = self.conexion.read(self.conexion.in_waiting).decode("utf-8", "replace")
                for linea_rx in texto.splitlines():
                    if linea_rx.strip():
                        print(f"[ESP32] {linea_rx.strip()}")
        except (serial.SerialException, OSError) as err:
            print(f"[ERROR COM] Conexión perdida: {err}")
            self.cerrar()
            self.descripcion = "USB: reconectando..."

    def cerrar(self):
        if self.conexion is not None:
            try:
                self.conexion.close()
            except (serial.SerialException, OSError):
                pass
        self.conexion = None


class EnlaceWiFi:
    """UDP hacia la ESP32 (por defecto su punto de acceso 192.168.4.1)."""

    def __init__(self, host):
        self.destino = (host, PUERTO_UDP)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.descripcion = f"WiFi: {host}:{PUERTO_UDP}"

    def enviar(self, linea):
        try:
            self.sock.sendto((linea + "\n").encode("utf-8"), self.destino)
            while True:
                datos, _ = self.sock.recvfrom(2048)
                for linea_rx in datos.decode("utf-8", "replace").splitlines():
                    if linea_rx.strip():
                        print(f"[ESP32] {linea_rx.strip()}")
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as err:
            self.descripcion = f"WiFi: error ({err.strerror or err})"

    def cerrar(self):
        self.sock.close()


class EnlaceNulo:
    descripcion = "SIN HARDWARE (simulación)"

    def enviar(self, linea):
        pass

    def cerrar(self):
        pass


# ==========================================
# 3. CÁLCULO DE FLEXIÓN
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


def cargar_calibracion():
    try:
        with open(RUTA_CALIBRACION, encoding="utf-8") as f:
            datos = json.load(f)
        if len(datos["abierto"]) == 5 and len(datos["cerrado"]) == 5:
            print("[SISTEMA] Calibración cargada de calibracion.json")
            return datos
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return json.loads(json.dumps(CALIBRACION_DEFECTO))


def guardar_calibracion(calib):
    with open(RUTA_CALIBRACION, "w", encoding="utf-8") as f:
        json.dump(calib, f, indent=2)


def clasificar_gesto(dedos, lm):
    """Reconoce posturas de la mano a partir del estado binario de los dedos."""
    gestos = {
        (0, 0, 0, 0, 0): "PUNO CERRADO",
        (0, 1, 1, 0, 0): "PAZ / VICTORIA",
        (1, 1, 0, 0, 1): "ROCK / SPIDERMAN",
        (1, 1, 0, 0, 0): "PISTOLA",
        (0, 1, 0, 0, 0): "APUNTAR",
        (1, 0, 0, 0, 0): "PULGAR ARRIBA",
        (1, 0, 0, 0, 1): "TELEFONO",
    }
    clave = tuple(dedos)
    if clave in gestos:
        return gestos[clave]
    if clave[2:] == (1, 1, 1) and distancia(lm[4], lm[8]) < 0.025:
        return "GESTO OK"
    if clave == (1, 1, 1, 1, 1):
        return "SALUDO VULCANO (SPOCK)" if distancia(lm[12], lm[16]) > 0.035 else "MANO COMPLETA"
    return "MOVIMIENTO LIBRE"


# ==========================================
# 4. INTERFAZ HUD
# ==========================================
def dibujar_mano(img, lm_img, estados):
    h, w, _ = img.shape
    puntos = [(int(p.x * w), int(p.y * h)) for p in lm_img]
    for a, b in CONEXIONES_MANO:
        cv2.line(img, puntos[a], puntos[b], (230, 230, 230), 2)
    for p in puntos:
        cv2.circle(img, p, 4, (0, 140, 255), cv2.FILLED)
    for i, tip in enumerate(TIPS):
        col = (0, 255, 0) if estados[i] else (0, 0, 255)
        cv2.circle(img, puntos[tip], 8, col, cv2.FILLED)
        cv2.circle(img, puntos[tip], 14, col, 2)


def dibujar_interfaz_hud(img, fps_val, dedos, porcentajes, gesto, estado, enlace, aviso):
    h, w, _ = img.shape
    overlay = img.copy()
    cv2.rectangle(overlay, (15, 15), (440, 250), (15, 15, 25), -1)
    cv2.rectangle(overlay, (w - 400, 15), (w - 15, 130), (15, 15, 25), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    cv2.rectangle(img, (15, 15), (440, 250), (0, 255, 200), 1)
    cv2.rectangle(img, (w - 400, 15), (w - 15, 130), (0, 200, 255), 1)

    cv2.putText(img, "SISTEMA DE TELEMETRIA BIONICA", (30, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)
    cv2.putText(img, f"ESTADO: {estado}", (30, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    for idx, (nom, val, pct) in enumerate(zip(DEDOS_NOMBRES, dedos, porcentajes)):
        y_pos = 100 + idx * 28
        color_barra = (0, 255, 120) if val == 1 else (50, 50, 240)
        cv2.putText(img, f"{nom[:3]}:", (30, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
        ancho_max = 170
        ancho_actual = int(pct / 100.0 * ancho_max)
        cv2.rectangle(img, (80, y_pos - 12), (80 + ancho_max, y_pos + 2), (50, 50, 50), -1)
        cv2.rectangle(img, (80, y_pos - 12), (80 + ancho_actual, y_pos + 2), color_barra, -1)
        cv2.rectangle(img, (80, y_pos - 12), (80 + ancho_max, y_pos + 2), (180, 180, 180), 1)
        cv2.putText(img, f"{int(pct)}% [{'ABR' if val == 1 else 'CER'}]", (265, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_barra, 1)

    cv2.putText(img, enlace, (30, 238), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    cv2.putText(img, f"FPS: {int(fps_val)}", (w - 380, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    cv2.putText(img, "GESTO ACTIVO:", (w - 380, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
    cv2.putText(img, gesto, (w - 380, 108), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

    if aviso:
        (tw, _), _ = cv2.getTextSize(aviso, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.putText(img, aviso, ((w - tw) // 2, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2)

    cv2.putText(img, "[A] Calib. abierta  [C] Calib. puno  [R] Reset calib.  [B] Binario/Proporcional  "
                "[D] Demo  [ESC] Salir", (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)


# ==========================================
# 5. INICIALIZACIÓN
# ==========================================
def asegurar_modelo():
    if os.path.exists(RUTA_MODELO):
        return
    os.makedirs(os.path.dirname(RUTA_MODELO), exist_ok=True)
    print("[SISTEMA] Descargando el modelo de MediaPipe (~8 MB)...")
    try:
        urllib.request.urlretrieve(URL_MODELO, RUTA_MODELO + ".tmp")
        os.replace(RUTA_MODELO + ".tmp", RUTA_MODELO)
    except OSError as err:
        sys.exit(f"[ERROR] No se pudo descargar el modelo: {err}\n"
                 f"Descárgalo a mano desde {URL_MODELO} y guárdalo en {RUTA_MODELO}")


def crear_detector():
    asegurar_modelo()
    opciones = vision.HandLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=RUTA_MODELO),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    return vision.HandLandmarker.create_from_options(opciones)


def parsear_argumentos():
    p = argparse.ArgumentParser(description="Control de mano biónica con ESP32-S3")
    p.add_argument("--puerto", help="Puerto serie (ej. /dev/ttyACM0 o COM9). Por defecto: autodetectar")
    p.add_argument("--wifi", metavar="IP", help="Enviar por WiFi/UDP a esta IP (ej. 192.168.4.1)")
    p.add_argument("--sin-hardware", action="store_true", help="No enviar nada (solo visión)")
    p.add_argument("--camara", type=int, default=0, help="Índice de la webcam (por defecto 0)")
    p.add_argument("--ancho", type=int, default=1280)
    p.add_argument("--alto", type=int, default=720)
    p.add_argument("--binario", action="store_true", help="Empezar en modo binario (abierto/cerrado)")
    return p.parse_args()


# ==========================================
# 6. LOOP PRINCIPAL
# ==========================================
def main():
    args = parsear_argumentos()

    if args.sin_hardware:
        enlace = EnlaceNulo()
    elif args.wifi:
        enlace = EnlaceWiFi(args.wifi)
    else:
        enlace = EnlaceSerial(args.puerto)
        if enlace.conexion is None:
            print("[SISTEMA] Sin ESP32 por USB: se reintentará cada 2 s (o usa --wifi / --sin-hardware).")

    detector = crear_detector()
    cap = cv2.VideoCapture(args.camara)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.ancho)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.alto)
    if not cap.isOpened():
        sys.exit(f"[ERROR] No se puede abrir la cámara {args.camara}.")

    calib = cargar_calibracion()
    modo_binario = args.binario
    modo_demo = False
    porcentajes = [100.0] * 5
    estado_dedos = [1] * 5
    nombre_gesto = "CALIBRANDO..."
    muestras_calib, tipo_calib, fin_calib = [], None, 0
    aviso, fin_aviso = "", 0
    ultimo_envio = 0
    t_inicio = time.monotonic()
    ultimo_ts = -1
    prev_time = time.time()
    fps = 0.0

    def mostrar_aviso(texto, segundos=2.0):
        nonlocal aviso, fin_aviso
        aviso, fin_aviso = texto, time.time() + segundos
        print(f"[SISTEMA] {texto}")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("[ERROR] No se detecta señal de la cámara.")
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        imagen_mp = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = int((time.monotonic() - t_inicio) * 1000)
        ts = max(ts, ultimo_ts + 1)       # MediaPipe exige timestamps crecientes
        ultimo_ts = ts
        resultado = detector.detect_for_video(imagen_mp, ts)

        ahora = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(ahora - prev_time, 1e-3))
        prev_time = ahora

        mano_detectada = bool(resultado.hand_landmarks)
        if modo_demo:
            nombre_gesto = "DEMO EN LA ESP32"
        elif mano_detectada:
            lm_mundo = resultado.hand_world_landmarks[0]
            crudas = metricas_crudas(lm_mundo)

            if tipo_calib:
                muestras_calib.append(crudas)
                if ahora >= fin_calib:
                    calib[tipo_calib] = [float(np.median(col)) for col in zip(*muestras_calib)]
                    guardar_calibracion(calib)
                    mostrar_aviso(f"CALIBRACION '{tipo_calib.upper()}' GUARDADA")
                    tipo_calib = None

            objetivo = a_porcentaje(crudas, calib)
            porcentajes = [p + SUAVIZADO * (o - p) for p, o in zip(porcentajes, objetivo)]
            # Histéresis para el estado binario (evita parpadeos)
            estado_dedos = [1 if p > 60 else 0 if p < 40 else e for p, e in zip(porcentajes, estado_dedos)]
            nombre_gesto = clasificar_gesto(estado_dedos, lm_mundo)
            dibujar_mano(frame, resultado.hand_landmarks[0], estado_dedos)
        else:
            nombre_gesto = "MANO NO DETECTADA"

        # Envío a la ESP32. Si no se ve la mano no se envía: la ESP32 mantiene la
        # última posición y abre la mano sola tras 1.5 s (failsafe).
        if not modo_demo and mano_detectada and ahora - ultimo_envio >= INTERVALO_ENVIO:
            valores = [e * 100 for e in estado_dedos] if modo_binario else [round(p) for p in porcentajes]
            enlace.enviar("P:" + ",".join(str(int(v)) for v in valores))
            ultimo_envio = ahora

        if tipo_calib:
            restante = max(0.0, fin_calib - ahora)
            texto_aviso = f"MANTEN LA MANO {'ABIERTA' if tipo_calib == 'abierto' else 'CERRADA'}... {restante:.1f}s"
        else:
            texto_aviso = aviso if ahora < fin_aviso else ""

        estado = ("DEMO (ESP32)" if modo_demo else
                  f"CONTROL {'BINARIO' if modo_binario else 'PROPORCIONAL'}")
        dibujar_interfaz_hud(frame, fps, estado_dedos, porcentajes, nombre_gesto, estado,
                             enlace.descripcion, texto_aviso)
        cv2.imshow("Control Bionico ESP32-S3 - MediaPipe HUD", frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            break
        elif key in (ord("a"), ord("A"), ord("c"), ord("C")):
            tipo_calib = "abierto" if key in (ord("a"), ord("A")) else "cerrado"
            muestras_calib, fin_calib = [], ahora + DURACION_CALIBRACION
        elif key in (ord("r"), ord("R")):
            calib = json.loads(json.dumps(CALIBRACION_DEFECTO))
            guardar_calibracion(calib)
            mostrar_aviso("CALIBRACION POR DEFECTO")
        elif key in (ord("b"), ord("B")):
            modo_binario = not modo_binario
            mostrar_aviso(f"MODO {'BINARIO' if modo_binario else 'PROPORCIONAL'}")
        elif key in (ord("d"), ord("D"), ord("m"), ord("M")):
            modo_demo = not modo_demo
            enlace.enviar("DEMO" if modo_demo else "STOP")
            mostrar_aviso("DEMO ACTIVADA" if modo_demo else "CONTROL POR CAMARA")

    # Cierre limpio: dejar la mano abierta
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    enlace.enviar("OPEN")
    time.sleep(0.1)
    enlace.cerrar()
    print("[SISTEMA] Cerrado correctamente.")


if __name__ == "__main__":
    main()
