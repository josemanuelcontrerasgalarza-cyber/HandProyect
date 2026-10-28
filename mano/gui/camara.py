"""
Hilo de captura: lee la webcam, detecta la mano con MediaPipe y publica la
imagen anotada y los porcentajes de cada dedo sin bloquear la interfaz.
"""
import threading
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from ..vision import (Calibrador, DetectorMano, FiltroDedos, a_porcentaje, calibracion_defecto,
                      cargar_calibracion, clasificar_gesto, dibujar_mano, guardar_calibracion)


def frame_a_qimage(frame_bgr):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class HiloCamara(QThread):
    frame_listo = Signal(QImage)
    datos_mano = Signal(dict)
    calibracion_terminada = Signal(str, dict)
    error = Signal(str)
    mensaje = Signal(str)

    def __init__(self, indice=0, ancho=1280, alto=720, espejo=True, parent=None):
        super().__init__(parent)
        self.indice = indice
        self.ancho = ancho
        self.alto = alto
        self.espejo = espejo
        self.dibujar_esqueleto = True
        self._seguir = True
        self._lock = threading.Lock()
        self.calib = cargar_calibracion()
        self.filtro = FiltroDedos()
        self.calibrador = Calibrador(1.0)

    # --- Métodos llamados desde el hilo de la interfaz -------------------
    def detener(self):
        self._seguir = False

    def fijar_suavizado(self, valor):
        with self._lock:
            self.filtro.suavizado = max(0.05, min(1.0, valor))

    def calibrar(self, tipo, duracion=1.0):
        with self._lock:
            self.calibrador.duracion = duracion
            self.calibrador.iniciar(tipo)

    def cancelar_calibracion(self):
        with self._lock:
            self.calibrador.cancelar()

    def restablecer_calibracion(self):
        with self._lock:
            self.calib = calibracion_defecto()
            guardar_calibracion(self.calib)
            copia = {k: list(v) for k, v in self.calib.items()}
        self.calibracion_terminada.emit("defecto", copia)

    def fijar_calibracion(self, calib):
        with self._lock:
            self.calib = {k: list(v) for k, v in calib.items()}
            guardar_calibracion(self.calib)

    def calibracion_actual(self):
        with self._lock:
            return {k: list(v) for k, v in self.calib.items()}

    # --- Hilo --------------------------------------------------------------
    def run(self):
        self.mensaje.emit("Cargando el modelo de MediaPipe...")
        try:
            detector = DetectorMano()
        except Exception as err:                        # noqa: BLE001 - se muestra al usuario
            self.error.emit(f"No se pudo iniciar MediaPipe: {err}")
            return

        self.mensaje.emit(f"Abriendo la cámara {self.indice}...")
        cap = cv2.VideoCapture(self.indice)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
        if not cap.isOpened():
            detector.cerrar()
            self.error.emit(f"No se puede abrir la cámara {self.indice}.")
            return

        fps = 0.0
        t_prev = time.monotonic()
        fallos = 0
        try:
            while self._seguir:
                ok, frame = cap.read()
                if not ok:
                    fallos += 1
                    if fallos > 30:
                        self.error.emit("La cámara ha dejado de enviar imágenes.")
                        break
                    time.sleep(0.03)
                    continue
                fallos = 0
                if self.espejo:
                    frame = cv2.flip(frame, 1)

                resultado = detector.procesar(frame)
                ahora = time.monotonic()
                fps = 0.9 * fps + 0.1 * (1.0 / max(ahora - t_prev, 1e-3))
                t_prev = ahora

                datos = {"detectada": resultado.detectada, "fps": fps, "lateralidad": resultado.lateralidad}
                with self._lock:
                    if resultado.detectada:
                        tipo = self.calibrador.agregar(resultado.crudas, self.calib)
                        if tipo:
                            guardar_calibracion(self.calib)
                            self.calibracion_terminada.emit(tipo, {k: list(v) for k, v in self.calib.items()})
                        objetivo = a_porcentaje(resultado.crudas, self.calib)
                        self.filtro.actualizar(objetivo)
                        datos.update(
                            crudas=list(resultado.crudas),
                            sin_filtrar=objetivo,
                            gesto=clasificar_gesto(self.filtro.estados, resultado.landmarks_mundo),
                        )
                        if self.dibujar_esqueleto:
                            dibujar_mano(frame, resultado.landmarks_imagen, self.filtro.estados)
                    else:
                        datos["gesto"] = "MANO NO DETECTADA"
                    datos["porcentajes"] = list(self.filtro.porcentajes)
                    datos["estados"] = list(self.filtro.estados)
                    datos["calibrando"] = self.calibrador.tipo
                    datos["restante"] = self.calibrador.restante()

                self.datos_mano.emit(datos)
                self.frame_listo.emit(frame_a_qimage(frame))
        finally:
            cap.release()
            detector.cerrar()
