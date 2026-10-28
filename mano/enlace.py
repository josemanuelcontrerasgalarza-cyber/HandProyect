"""
Comunicación con la ESP32-S3: USB serie (con autodetección y reconexión),
WiFi UDP o un enlace nulo para trabajar sin hardware.

Todos los enlaces son seguros entre hilos y comparten la misma interfaz:
    enviar(linea)  -> envía una línea de texto (se añade '\\n')
    leer()         -> devuelve la lista de líneas recibidas desde la última llamada
    conectado      -> True si hay comunicación
    descripcion    -> texto corto para mostrar en la interfaz
    cerrar()
"""
import socket
import threading
import time

import serial
import serial.tools.list_ports

BAUD_RATE = 115200
PUERTO_UDP = 4210
IP_AP_POR_DEFECTO = "192.168.4.1"

# VID USB: Espressif (USB nativo S3), CH340/CH343, CP210x, FTDI
VIDS_CONOCIDOS = {0x303A, 0x1A86, 0x10C4, 0x0403}


def listar_puertos():
    """Lista de (dispositivo, descripción) con los puertos de la ESP32 primero."""
    puertos = list(serial.tools.list_ports.comports())
    puertos.sort(key=lambda p: (p.vid not in VIDS_CONOCIDOS, p.device))
    return [(p.device, f"{p.device} - {p.description}") for p in puertos]


def buscar_puerto():
    for p in serial.tools.list_ports.comports():
        if p.vid in VIDS_CONOCIDOS:
            return p.device
    for p in serial.tools.list_ports.comports():
        if "ACM" in p.device or "USB" in p.device or p.device.upper().startswith("COM"):
            return p.device
    return None


class _BufferLineas:
    """Acumula texto recibido y lo separa en líneas completas."""

    def __init__(self):
        self.pendiente = ""
        self.lineas = []

    def agregar(self, texto):
        self.pendiente += texto
        *completas, self.pendiente = self.pendiente.replace("\r", "").split("\n")
        self.lineas.extend(l for l in completas if l.strip())
        if len(self.pendiente) > 4096:          # protección ante basura sin '\n'
            self.lineas.append(self.pendiente)
            self.pendiente = ""

    def extraer(self):
        salida, self.lineas = self.lineas, []
        return salida


class EnlaceSerial:
    """USB con autodetección del puerto y reconexión automática."""

    tipo = "USB"

    def __init__(self, puerto=None, reintento_s=2.0):
        self.puerto_fijo = puerto
        self.reintento_s = reintento_s
        self.conexion = None
        self.puerto_actual = None
        self.ultimo_intento = 0.0
        self.descripcion = "USB: desconectado"
        self._lock = threading.Lock()
        self._rx = _BufferLineas()
        self.conectar()

    @property
    def conectado(self):
        return self.conexion is not None

    def conectar(self):
        self.ultimo_intento = time.time()
        puerto = self.puerto_fijo or buscar_puerto()
        if not puerto:
            self.descripcion = "USB: no se encuentra la ESP32"
            return False
        try:
            # DTR/RTS a nivel bajo ANTES de abrir para no reiniciar la ESP32
            conexion = serial.Serial(baudrate=BAUD_RATE, timeout=0, write_timeout=0.05)
            conexion.port = puerto
            conexion.dtr = False
            conexion.rts = False
            conexion.open()
            time.sleep(0.3)
            conexion.reset_input_buffer()
            self.conexion = conexion
            self.puerto_actual = puerto
            self.descripcion = f"USB: {puerto}"
            return True
        except (serial.SerialException, OSError) as err:
            self.conexion = None
            self.descripcion = f"USB: error en {puerto} ({err.__class__.__name__})"
            return False

    def _reintentar_si_toca(self):
        if self.conexion is None and time.time() - self.ultimo_intento > self.reintento_s:
            self.conectar()

    def _perder_conexion(self):
        try:
            self.conexion.close()
        except (serial.SerialException, OSError, AttributeError):
            pass
        self.conexion = None
        self.descripcion = "USB: reconectando..."

    def enviar(self, linea):
        with self._lock:
            self._reintentar_si_toca()
            if self.conexion is None:
                return False
            try:
                self.conexion.write((linea + "\n").encode("utf-8"))
                return True
            except serial.SerialTimeoutException:
                return False                    # buffer lleno: se descarta la trama
            except (serial.SerialException, OSError):
                self._perder_conexion()
                return False

    def leer(self):
        with self._lock:
            self._reintentar_si_toca()
            if self.conexion is not None:
                try:
                    n = self.conexion.in_waiting
                    if n:
                        self._rx.agregar(self.conexion.read(n).decode("utf-8", "replace"))
                except (serial.SerialException, OSError):
                    self._perder_conexion()
            return self._rx.extraer()

    def cerrar(self):
        with self._lock:
            if self.conexion is not None:
                try:
                    self.conexion.close()
                except (serial.SerialException, OSError):
                    pass
            self.conexion = None
            self.descripcion = "USB: cerrado"


class EnlaceWiFi:
    """UDP hacia la ESP32 (por defecto su punto de acceso 192.168.4.1)."""

    tipo = "WiFi"

    def __init__(self, host=IP_AP_POR_DEFECTO, puerto=PUERTO_UDP):
        self.destino = (host, puerto)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.descripcion = f"WiFi: {host}:{puerto}"
        self.ultima_respuesta = 0.0
        self._lock = threading.Lock()
        self._rx = _BufferLineas()
        self._error = False

    @property
    def conectado(self):
        # UDP no tiene conexión: se considera conectado si no hay errores de red
        return not self._error

    def enviar(self, linea):
        with self._lock:
            try:
                self.sock.sendto((linea + "\n").encode("utf-8"), self.destino)
                if self._error:
                    self._error = False
                    self.descripcion = f"WiFi: {self.destino[0]}:{self.destino[1]}"
                return True
            except OSError as err:
                self._error = True
                self.descripcion = f"WiFi: error ({err.strerror or err})"
                return False

    def leer(self):
        with self._lock:
            while True:
                try:
                    datos, _ = self.sock.recvfrom(4096)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    break
                self.ultima_respuesta = time.time()
                texto = datos.decode("utf-8", "replace")
                if not texto.endswith("\n"):
                    texto += "\n"
                self._rx.agregar(texto)
            return self._rx.extraer()

    def cerrar(self):
        with self._lock:
            self.sock.close()
            self._error = True
            self.descripcion = "WiFi: cerrado"


class EnlaceNulo:
    """Simula la ESP32: no envía nada pero responde a PING para pruebas."""

    tipo = "Simulación"
    descripcion = "SIN HARDWARE (simulación)"
    conectado = True

    def __init__(self):
        self._rx = []

    def enviar(self, linea):
        if linea.strip().upper() == "PING":
            self._rx.append("PONG SIMULACION")
        return True

    def leer(self):
        salida, self._rx = self._rx, []
        return salida

    def cerrar(self):
        pass


def formatear_trama(porcentajes):
    """Lista de 5 valores 0-100 -> 'P:a,b,c,d,e'."""
    valores = [int(round(min(100, max(0, v)))) for v in porcentajes]
    return "P:" + ",".join(str(v) for v in valores)
