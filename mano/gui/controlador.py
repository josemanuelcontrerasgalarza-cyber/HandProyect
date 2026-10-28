"""
Controlador central de la aplicación: mantiene el enlace con la ESP32, decide
qué pose se envía (cámara, sliders manuales, secuencia o demo de la ESP32) y
reparte por señales Qt todo lo que llega de la mano.

Solo hay UNA fuente de control activa a la vez, para que nunca haya dos partes
de la aplicación peleándose por los servos.
"""
import re
import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..enlace import EnlaceNulo, EnlaceSerial, EnlaceWiFi, formatear_trama
from ..secuencias import Reproductor

FUENTE_PARADO = "parado"
FUENTE_CAMARA = "camara"
FUENTE_MANUAL = "manual"
FUENTE_SECUENCIA = "secuencia"
FUENTE_DEMO = "demo"

NOMBRES_FUENTE = {
    FUENTE_PARADO: "Parado",
    FUENTE_CAMARA: "Cámara",
    FUENTE_MANUAL: "Manual",
    FUENTE_SECUENCIA: "Secuencia",
    FUENTE_DEMO: "Demo ESP32",
}

FUENTES_STREAMING = (FUENTE_CAMARA, FUENTE_MANUAL, FUENTE_SECUENCIA)
COMANDOS_MOVIMIENTO = {"OPEN", "ABRIR", "CLOSE", "CERRAR", "GESTO", "SET", "DEMO", "SWEEP",
                       "RELAX", "PULSO"}

FRECUENCIA_ENVIO_HZ = 30
TIMEOUT_CAMARA_S = 0.5      # sin mano durante este tiempo -> no se envía (failsafe ESP32)

# "[1] INDICE   CH2  abierto=130 cerrado=520  actual=100% objetivo=100%"
RE_ESTADO_DEDO = re.compile(r"^\[(\d)\]\s+(\S+)\s+CH(\d+)\s+abierto=\s*(\d+)\s+cerrado=\s*(\d+)"
                            r"\s+actual=\s*(-?\d+)%\s+objetivo=\s*(-?\d+)%")
RE_ESTADO_MODO = re.compile(r"^Modo:\s*(\S+)\s*\|\s*Fuente:\s*(\S+)\s*\|\s*Velocidad:\s*(\d+)%")
RE_ESTADO_HW = re.compile(r"^PCA9685:\s*(.+?)\s*\|\s*WiFi:\s*(\S+)")


class Controlador(QObject):
    enlace_cambiado = Signal(str, str)        # (descripción, estado: ok/aviso/error/apagado)
    linea_recibida = Signal(str)
    linea_enviada = Signal(str)
    pose_enviada = Signal(list)
    fuente_cambiada = Signal(str)
    paso_secuencia = Signal(int, float)       # (índice de paso, progreso 0..1)
    secuencia_terminada = Signal()
    calibracion_servo = Signal(int, int, int)  # (dedo, abierto, cerrado)
    posicion_servo = Signal(int, int, int)    # (dedo, actual %, objetivo %)
    estado_esp = Signal(dict)                 # modo, fuente, velocidad, pca, ip
    estadisticas = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enlace = None
        self.fuente = FUENTE_PARADO
        self.modo_binario = False
        self.pose_manual = [100.0] * 5
        self.pose_camara = [100.0] * 5
        self.estados_camara = [1] * 5
        self.t_camara = 0.0
        self.ultima_pose = [100.0] * 5
        self.reproductor = Reproductor()
        self.ultimo_pong = 0.0
        self.esp_info = {}
        self._tramas_enviadas = 0
        self._lineas_recibidas = 0
        self._t_estadisticas = time.monotonic()
        self._ultimo_estado_enlace = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / FRECUENCIA_ENVIO_HZ))

        self.timer_ping = QTimer(self)
        self.timer_ping.timeout.connect(self._ping)
        self.timer_ping.start(3000)

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------
    def conectar_usb(self, puerto=None):
        self.desconectar()
        self.enlace = EnlaceSerial(puerto or None)
        self._notificar_enlace(forzar=True)
        if self.enlace.conectado:
            self.comando("PING", eco=False)
        return self.enlace.conectado

    def conectar_wifi(self, host):
        self.desconectar()
        self.enlace = EnlaceWiFi(host)
        self._notificar_enlace(forzar=True)
        self.comando("PING", eco=False)
        return True

    def conectar_simulacion(self):
        self.desconectar()
        self.enlace = EnlaceNulo()
        self._notificar_enlace(forzar=True)
        return True

    def desconectar(self):
        if self.enlace is not None:
            if self.enlace.conectado:
                self.enlace.enviar("OPEN")
            self.enlace.cerrar()
        self.enlace = None
        self.ultimo_pong = 0.0
        self._notificar_enlace(forzar=True)

    @property
    def conectado(self):
        return self.enlace is not None and self.enlace.conectado

    def estado_enlace(self):
        if self.enlace is None:
            return "Sin conexión", "apagado"
        if not self.enlace.conectado:
            return self.enlace.descripcion, "error"
        if isinstance(self.enlace, EnlaceNulo):
            return self.enlace.descripcion, "aviso"
        responde = time.time() - self.ultimo_pong < 7.0
        if responde:
            return self.enlace.descripcion + " · responde", "ok"
        return self.enlace.descripcion + " · esperando respuesta", "aviso"

    def _notificar_enlace(self, forzar=False):
        estado = self.estado_enlace()
        if forzar or estado != self._ultimo_estado_enlace:
            self._ultimo_estado_enlace = estado
            self.enlace_cambiado.emit(*estado)

    def _ping(self):
        if self.enlace is not None and not isinstance(self.enlace, EnlaceNulo):
            self.enlace.enviar("PING")

    # ------------------------------------------------------------------
    # Comandos y fuente de control
    # ------------------------------------------------------------------
    def comando(self, texto, eco=True):
        texto = texto.strip()
        if not texto:
            return False
        if eco:
            self.linea_enviada.emit(texto)
        # Un comando de movimiento escrito a mano se perdería entre las tramas
        # de la fuente activa: se para la fuente antes de enviarlo.
        palabra = texto.split()[0].upper()
        if palabra in COMANDOS_MOVIMIENTO and self.fuente in FUENTES_STREAMING:
            self.fijar_fuente(FUENTE_PARADO)
        if self.enlace is None:
            if eco:
                self.linea_recibida.emit("[APP] No hay conexión con la mano.")
            return False
        return self.enlace.enviar(texto)

    def fijar_fuente(self, fuente):
        if fuente not in NOMBRES_FUENTE:
            raise ValueError(fuente)
        if fuente == self.fuente:
            return
        anterior = self.fuente
        self.fuente = fuente
        if anterior == FUENTE_SECUENCIA and fuente != FUENTE_SECUENCIA:
            self.reproductor.detener()
        if anterior == FUENTE_DEMO:
            self.comando("STOP", eco=False)
        if fuente == FUENTE_DEMO:
            self.comando("DEMO", eco=False)
        self.fuente_cambiada.emit(fuente)

    def parada(self):
        """Parada: deja de enviar y abre la mano suavemente."""
        self.fijar_fuente(FUENTE_PARADO)
        self.comando("OPEN", eco=False)
        self.ultima_pose = [100.0] * 5
        self.pose_manual = [100.0] * 5

    def tomar_control_manual(self, pose):
        """Pasa a control manual empezando exactamente en 'pose'."""
        self.pose_manual = [float(v) for v in pose]
        self.fijar_fuente(FUENTE_MANUAL)

    def fijar_pose_manual(self, pose):
        self.pose_manual = [float(v) for v in pose]

    def fijar_dedo_manual(self, dedo, valor):
        self.pose_manual[dedo] = float(valor)

    def actualizar_camara(self, porcentajes, estados, detectada):
        if detectada:
            self.pose_camara = list(porcentajes)
            self.estados_camara = list(estados)
            self.t_camara = time.monotonic()

    def reproducir(self, secuencia):
        self.reproductor.iniciar(secuencia, self.ultima_pose)
        self.fijar_fuente(FUENTE_SECUENCIA)

    # ------------------------------------------------------------------
    # Bucle de envío / recepción
    # ------------------------------------------------------------------
    def _pose_actual(self):
        if self.fuente == FUENTE_CAMARA:
            if time.monotonic() - self.t_camara > TIMEOUT_CAMARA_S:
                return None
            if self.modo_binario:
                return [e * 100.0 for e in self.estados_camara]
            return self.pose_camara
        if self.fuente == FUENTE_MANUAL:
            return self.pose_manual
        if self.fuente == FUENTE_SECUENCIA:
            pose, indice = self.reproductor.pose_actual()
            if pose is None:
                # Al terminar, la mano se queda en la última pose (fuente manual)
                self.pose_manual = list(self.ultima_pose)
                self.fijar_fuente(FUENTE_MANUAL)
                self.secuencia_terminada.emit()
                return None
            sec = self.reproductor.secuencia
            total = sec.duracion_ms or 1
            progreso = (self.reproductor.tiempo_ms() % total) / total if sec.bucle else \
                min(1.0, self.reproductor.tiempo_ms() / total)
            self.paso_secuencia.emit(indice, progreso)
            return pose
        return None

    def _tick(self):
        pose = self._pose_actual()
        if pose is not None:
            self.ultima_pose = list(pose)
            if self.enlace is not None:
                if self.enlace.enviar(formatear_trama(pose)):
                    self._tramas_enviadas += 1
            self.pose_enviada.emit(list(pose))

        if self.enlace is not None:
            for linea in self.enlace.leer():
                self._lineas_recibidas += 1
                self._analizar_linea(linea)
        self._notificar_enlace()

        ahora = time.monotonic()
        if ahora - self._t_estadisticas >= 1.0:
            dt = ahora - self._t_estadisticas
            self.estadisticas.emit({
                "tramas_s": self._tramas_enviadas / dt,
                "lineas_s": self._lineas_recibidas / dt,
                "fuente": self.fuente,
            })
            self._tramas_enviadas = 0
            self._lineas_recibidas = 0
            self._t_estadisticas = ahora

    def _analizar_linea(self, linea):
        if linea.startswith("PONG"):
            self.ultimo_pong = time.time()
            return                      # los PING automáticos no ensucian la consola
        self.ultimo_pong = time.time()  # cualquier respuesta demuestra que la mano está viva
        self.linea_recibida.emit(linea)

        m = RE_ESTADO_DEDO.match(linea.strip())
        if m:
            dedo = int(m.group(1))
            self.calibracion_servo.emit(dedo, int(m.group(4)), int(m.group(5)))
            self.posicion_servo.emit(dedo, int(m.group(6)), int(m.group(7)))
            return
        m = RE_ESTADO_MODO.match(linea.strip())
        if m:
            self.esp_info.update(modo=m.group(1), fuente=m.group(2), velocidad=int(m.group(3)))
            self.estado_esp.emit(dict(self.esp_info))
            return
        m = RE_ESTADO_HW.match(linea.strip())
        if m:
            self.esp_info.update(pca=m.group(1), ip=m.group(2))
            self.estado_esp.emit(dict(self.esp_info))

    def cerrar(self):
        self.timer.stop()
        self.timer_ping.stop()
        self.desconectar()
