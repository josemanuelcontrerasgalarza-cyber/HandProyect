"""
HandProyect - Control de mano biónica por visión artificial (versión ligera, sin ventana Qt).

Lee tu mano con la webcam (MediaPipe HandLandmarker), calcula cuánto está
abierto cada dedo (0-100 %) y lo envía a la ESP32-S3 por USB o por WiFi.
Para la aplicación de escritorio completa usa:  python mano_app.py

Uso:
    python hand_control.py                      # USB, puerto autodetectado
    python hand_control.py --puerto /dev/ttyACM0
    python hand_control.py --wifi 192.168.4.1   # sin cable, por UDP
    python hand_control.py --sin-hardware       # solo visión, sin enviar nada

Teclas: [A] calibrar mano ABIERTA  [C] calibrar PUÑO  [R] borrar calibración
        [B] modo binario/proporcional  [D] demo en la ESP32  [ESC/Q] salir
"""
import argparse
import sys
import time

import cv2

from mano.enlace import EnlaceNulo, EnlaceSerial, EnlaceWiFi, formatear_trama
from mano.vision import (DEDOS_NOMBRES, Calibrador, DetectorMano, FiltroDedos, a_porcentaje,
                         calibracion_defecto, cargar_calibracion, clasificar_gesto,
                         dibujar_mano, guardar_calibracion)

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
INTERVALO_ENVIO = 1 / 30          # 30 Hz hacia la ESP32
DURACION_CALIBRACION = 1.0        # segundos de muestreo al calibrar


# ==========================================
# 2. INTERFAZ HUD
# ==========================================
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
# 3. LOOP PRINCIPAL
# ==========================================
def main():
    args = parsear_argumentos()

    if args.sin_hardware:
        enlace = EnlaceNulo()
    elif args.wifi:
        enlace = EnlaceWiFi(args.wifi)
    else:
        enlace = EnlaceSerial(args.puerto)
        if enlace.conectado:
            print(f"[SISTEMA] Conectado a la ESP32 en {enlace.puerto_actual}")
        else:
            print("[SISTEMA] Sin ESP32 por USB: se reintentará cada 2 s (o usa --wifi / --sin-hardware).")

    try:
        detector = DetectorMano()
    except RuntimeError as err:
        sys.exit(f"[ERROR] {err}")
    cap = cv2.VideoCapture(args.camara)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.ancho)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.alto)
    if not cap.isOpened():
        sys.exit(f"[ERROR] No se puede abrir la cámara {args.camara}.")

    calib = cargar_calibracion()
    filtro = FiltroDedos()
    calibrador = Calibrador(DURACION_CALIBRACION)
    modo_binario = args.binario
    modo_demo = False
    nombre_gesto = "CALIBRANDO..."
    aviso, fin_aviso = "", 0
    ultimo_envio = 0
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
        resultado = detector.procesar(frame)

        ahora = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(ahora - prev_time, 1e-3))
        prev_time = ahora

        if modo_demo:
            nombre_gesto = "DEMO EN LA ESP32"
        elif resultado.detectada:
            tipo = calibrador.agregar(resultado.crudas, calib)
            if tipo:
                guardar_calibracion(calib)
                mostrar_aviso(f"CALIBRACION '{tipo.upper()}' GUARDADA")
            filtro.actualizar(a_porcentaje(resultado.crudas, calib))
            nombre_gesto = clasificar_gesto(filtro.estados, resultado.landmarks_mundo)
            dibujar_mano(frame, resultado.landmarks_imagen, filtro.estados)
        else:
            nombre_gesto = "MANO NO DETECTADA"

        # Envío a la ESP32. Si no se ve la mano no se envía: la ESP32 mantiene la
        # última posición y abre la mano sola tras 1.5 s (failsafe).
        if not modo_demo and resultado.detectada and ahora - ultimo_envio >= INTERVALO_ENVIO:
            valores = [e * 100 for e in filtro.estados] if modo_binario else filtro.porcentajes
            enlace.enviar(formatear_trama(valores))
            ultimo_envio = ahora
        for linea_rx in enlace.leer():
            print(f"[ESP32] {linea_rx}")

        if calibrador.activo:
            estado_calib = "ABIERTA" if calibrador.tipo == "abierto" else "CERRADA"
            texto_aviso = f"MANTEN LA MANO {estado_calib}... {calibrador.restante():.1f}s"
        else:
            texto_aviso = aviso if ahora < fin_aviso else ""

        estado = ("DEMO (ESP32)" if modo_demo else
                  f"CONTROL {'BINARIO' if modo_binario else 'PROPORCIONAL'}")
        dibujar_interfaz_hud(frame, fps, filtro.estados, filtro.porcentajes, nombre_gesto, estado,
                             enlace.descripcion, texto_aviso)
        cv2.imshow("Control Bionico ESP32-S3 - MediaPipe HUD", frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            break
        elif key in (ord("a"), ord("A")):
            calibrador.iniciar("abierto")
        elif key in (ord("c"), ord("C")):
            calibrador.iniciar("cerrado")
        elif key in (ord("r"), ord("R")):
            calib = calibracion_defecto()
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
    detector.cerrar()
    enlace.enviar("OPEN")
    time.sleep(0.1)
    enlace.cerrar()
    print("[SISTEMA] Cerrado correctamente.")


if __name__ == "__main__":
    main()
