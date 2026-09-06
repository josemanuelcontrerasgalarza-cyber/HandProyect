import cv2
import mediapipe as mp
import numpy as np
import serial
import time
import math

# ==========================================
# 1. CONFIGURACIÓN DEL SISTEMA Y SERIAL
# ==========================================
SERIAL_PORT = 'COM9'
BAUD_RATE = 115200
ENABLE_SERIAL = True

try:
    if ENABLE_SERIAL:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
        time.sleep(1.5)
        print(f"[SISTEMA] Conexión establecida con éxito en {SERIAL_PORT}")
    else:
        arduino = None
except Exception as err:
    print(f"[ADVERTENCIA] No se pudo abrir {SERIAL_PORT}: {err}")
    print("[SISTEMA] Ejecutando en modo simulación visual sin hardware.")
    arduino = None

# ==========================================
# 2. INICIALIZACIÓN DE MEDIAPIPE Y CÁMARA
# ==========================================
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=1,
    min_detection_confidence=0.75,
    min_tracking_confidence=0.75
)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# Índices de referencia anatómica MediaPipe
TIPS = [4, 8, 12, 16, 20]     # Puntas: Pulgar, Índice, Medio, Anular, Meñique
PIPS = [3, 6, 10, 14, 18]     # Articulaciones intermedias
MCPS = [2, 5, 9, 13, 17]      # Nudillos base
DEDOS_NOMBRES = ["PULGAR", "INDICE", "MEDIO", "ANULAR", "MENIQUE"]

# ==========================================
# 3. VARIABLES DE ESTADO Y TELEMETRÍA
# ==========================================
estado_dedos = [1, 1, 1, 1, 1]          # 1: Abierto, 0: Cerrado
porcentajes_flexion = [100, 100, 100, 100, 100]
ultimo_envio_serial = 0
INTERVALO_ENVIO = 0.05                 # 20 Hz de refresco serial

modo_auto = False
tiempo_inicio_auto = time.time()
nombre_gesto_actual = "CALIBRANDO..."

prev_time = 0
fps = 0

# ==========================================
# 4. FUNCIONES AUXILIARES DE CÁLCULO
# ==========================================
def calcular_distancia_3d(p1, p2):
    """Calcula la distancia euclidiana en espacio normalizado 3D."""
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

def clasificar_gesto(dedos, lm):
    """Reconoce posturas complejas de la mano mediante reglas lógicas."""
    if dedos == [0, 0, 0, 0, 0]:
        return "PUNO CERRADO"
    if dedos == [1, 1, 1, 1, 1]:
        return "MANO COMPLETA"
    if dedos == [0, 1, 1, 0, 0]:
        return "PAZ / VICTORIA"
    if dedos == [1, 1, 0, 0, 1]:
        return "ROCK / SPIDERMAN"
    if dedos == [1, 1, 0, 0, 0]:
        return "PISTOLA"
    if dedos == [0, 1, 1, 1, 1]:
        d_ok = calcular_distancia_3d(lm[4], lm[8])
        if d_ok < 0.07:
            return "GESTO OK"
    if dedos == [1, 1, 1, 1, 1]:
        dist_medio_anular = calcular_distancia_3d(lm[12], lm[16])
        if dist_medio_anular > 0.08:
            return "SALUDO VULCANO (SPOCK)"
    return "MOVIMIENTO LIBRE"

def dibujar_interfaz_hud(img, fps_val, dedos, porcentajes, gesto, modo):
    """Renderiza el HUD futurista y los medidores de telemetría."""
    h, w, _ = img.shape

    # Panel superior de telemetría
    overlay = img.copy()
    cv2.rectangle(overlay, (15, 15), (420, 240), (15, 15, 25), -1)
    cv2.rectangle(overlay, (w - 380, 15), (w - 15, 120), (15, 15, 25), -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)

    # Bordes Sci-Fi
    cv2.rectangle(img, (15, 15), (420, 240), (0, 255, 200), 1)
    cv2.rectangle(img, (w - 380, 15), (w - 15, 120), (0, 200, 255), 1)

    # Texto de cabecera
    cv2.putText(img, "SISTEMA DE TELEMETRIA BIONICA", (30, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)
    cv2.putText(img, f"ESTADO: {'MODO AUTONOMO' if modo else 'CONTROL MANUAL'}", (30, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255) if modo else (0, 255, 100), 1)

    # Barras de flexión por dedo
    for idx, (nom, val, pct) in enumerate(zip(DEDOS_NOMBRES, dedos, porcentajes)):
        y_pos = 100 + (idx * 26)
        color_barra = (0, 255, 120) if val == 1 else (50, 50, 240)

        # Nombre del dedo y valor binario
        cv2.putText(img, f"{nom[:3]}:", (30, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

        # Barra de progreso
        ancho_max = 160
        ancho_actual = int((pct / 100.0) * ancho_max)
        cv2.rectangle(img, (80, y_pos - 12), (80 + ancho_max, y_pos + 2), (50, 50, 50), -1)
        cv2.rectangle(img, (80, y_pos - 12), (80 + ancho_actual, y_pos + 2), color_barra, -1)
        cv2.rectangle(img, (80, y_pos - 12), (80 + ancho_max, y_pos + 2), (180, 180, 180), 1)

        # Porcentaje numérico y estado
        cv2.putText(img, f"{pct}% [{'ABR' if val==1 else 'CER'}]", (255, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color_barra, 1)

    # Panel lateral derecho (FPS y Gesto)
    cv2.putText(img, f"FPS: {int(fps_val)}", (w - 360, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    cv2.putText(img, "GESTO ACTIVO:", (w - 360, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
    cv2.putText(img, gesto, (w - 360, 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

    # Leyenda de comandos
    cv2.putText(img, "[M] Alternar Modo Auto/Manual | [ESC] Salir", (20, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

# ==========================================
# 5. LOOP PRINCIPAL DE EJECUCIÓN
# ==========================================
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("[ERROR] No se detecta señal de la cámara.")
        break

    # Espejo horizontal y conversión de color
    frame = cv2.flip(frame, 1)
    h_frame, w_frame, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)

    # Cálculo de FPS
    current_time = time.time()
    fps = 1.0 / (current_time - prev_time) if (current_time - prev_time) > 0 else 30
    prev_time = current_time

    if not modo_auto:
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Renderizado personalizado de conexiones
                mp_draw.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style()
                )

                lm = hand_landmarks.landmark
                muneca = lm[0]

                # 1. ANÁLISIS DEL PULGAR (Vectorial respecto a base de Meñique y Carpo)
                dist_pulgar_tip_meñique = calcular_distancia_3d(lm[4], lm[17])
                dist_pulgar_mcp_meñique = calcular_distancia_3d(lm[2], lm[17])
                ratio_pulgar = dist_pulgar_tip_meñique / (dist_pulgar_mcp_meñique + 1e-5)

                if ratio_pulgar > 1.25:
                    estado_dedos[0] = 1
                    porcentajes_flexion[0] = min(100, int((ratio_pulgar - 1.0) * 150))
                else:
                    estado_dedos[0] = 0
                    porcentajes_flexion[0] = max(0, int((ratio_pulgar - 0.7) * 120))

                # 2. ANÁLISIS DE LOS 4 DEDOS (Distancia relativa a la Muñeca)
                for i in range(1, 5):
                    d_tip = calcular_distancia_3d(lm[TIPS[i]], muneca)
                    d_pip = calcular_distancia_3d(lm[PIPS[i]], muneca)
                    d_mcp = calcular_distancia_3d(lm[MCPS[i]], muneca)

                    # Normalización porcentual
                    recorrido_total = d_tip - d_mcp
                    porcentaje = int(np.clip((d_tip / (d_pip + 1e-5) - 0.9) * 200, 0, 100))
                    porcentajes_flexion[i] = porcentaje

                    if d_tip > d_pip and d_tip > d_mcp * 1.15:
                        estado_dedos[i] = 1
                    else:
                        estado_dedos[i] = 0

                nombre_gesto_actual = clasificar_gesto(estado_dedos, lm)

                # Efecto visual: Resaltar la punta de los dedos activos
                for i, tip_idx in enumerate(TIPS):
                    cx, cy = int(lm[tip_idx].x * w_frame), int(lm[tip_idx].y * h_frame)
                    col = (0, 255, 0) if estado_dedos[i] == 1 else (0, 0, 255)
                    cv2.circle(frame, (cx, cy), 8, col, cv2.FILLED)
                    cv2.circle(frame, (cx, cy), 14, col, 2)
        else:
            nombre_gesto_actual = "MANO NO DETECTADA"
    else:
        # SECUENCIA AUTOMÁTICA DE DEMOSTRACIÓN (SWEEP)
        t_auto = time.time() - tiempo_inicio_auto
        fase = int(t_auto * 1.5) % 6

        if fase == 0:
            estado_dedos = [1, 1, 1, 1, 1]
            nombre_gesto_actual = "DEMO: APERTURA TOTAL"
        elif fase == 1:
            estado_dedos = [0, 0, 0, 0, 0]
            nombre_gesto_actual = "DEMO: CIERRE TOTAL"
        elif fase == 2:
            estado_dedos = [0, 1, 1, 0, 0]
            nombre_gesto_actual = "DEMO: SIGNO DE PAZ"
        elif fase == 3:
            estado_dedos = [1, 1, 0, 0, 1]
            nombre_gesto_actual = "DEMO: ROCK N ROLL"
        elif fase == 4:
            estado_dedos = [1, 0, 0, 0, 0]
            nombre_gesto_actual = "DEMO: SOLO PULGAR"
        else:
            estado_dedos = [0, 1, 0, 0, 0]
            nombre_gesto_actual = "DEMO: SOLO INDICE"

        porcentajes_flexion = [val * 100 for val in estado_dedos]

    # ==========================================
    # 6. PROTOCOLO DE TRANSMISIÓN SERIAL
    # ==========================================
    tiempo_actual = time.time()
    if (tiempo_actual - ultimo_envio_serial) >= INTERVALO_ENVIO:
        trama_datos = f"{estado_dedos[0]},{estado_dedos[1]},{estado_dedos[2]},{estado_dedos[3]},{estado_dedos[4]}\n"
        if arduino and arduino.is_open:
            try:
                arduino.write(trama_datos.encode('utf-8'))
            except Exception as e:
                print(f"[ERROR COM] Error enviando paquete: {e}")
        ultimo_envio_serial = tiempo_actual

    # Renderizar todos los elementos del HUD
    dibujar_interfaz_hud(frame, fps, estado_dedos, porcentajes_flexion, nombre_gesto_actual, modo_auto)

    # Mostrar la ventana principal
    cv2.imshow("Control Bionico Avanzado - MediaPipe HUD", frame)

    # Control de teclado
    key = cv2.waitKey(1) & 0xFF
    if key == 27:  # ESC para salir
        break
    elif key in (ord('m'), ord('M')):
        modo_auto = not modo_auto
        tiempo_inicio_auto = time.time()
        print(f"[MODO] Cambiado a: {'AUTONOMO' if modo_auto else 'MANUAL'}")

# ==========================================
# 7. CIERRE LIMPIO DE RECURSOS
# ==========================================
cap.release()
cv2.destroyAllWindows()
if arduino and arduino.is_open:
    # Dejar la mano abierta antes de desconectar
    arduino.write(b"1,1,1,1,1\n")
    time.sleep(0.1)
    arduino.close()
    print("[SISTEMA] Conexión Serial cerrada correctamente.")