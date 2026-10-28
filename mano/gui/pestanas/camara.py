"""Pestaña Cámara: vídeo en directo, esquema de la mano y control por visión."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

from ...vision import calibracion_defecto, guardar_calibracion
from ..camara import HiloCamara
from ..controlador import FUENTE_CAMARA, FUENTE_PARADO
from ..widgets import BarrasDedos, EsquemaMano, VistaVideo
from . import boton

RESOLUCIONES = [("1280 x 720", 1280, 720), ("960 x 540", 960, 540), ("640 x 480", 640, 480)]


class PestanaCamara(QWidget):
    datos_camara = Signal(dict)              # reenvía los datos del hilo a otras pestañas
    calibracion_terminada = Signal(str, dict)
    estado_camara = Signal(bool)              # True = en marcha

    def __init__(self, controlador, ajustes, parent=None):
        super().__init__(parent)
        self.ctrl = controlador
        self.ajustes = ajustes
        self.hilo = None

        self.video = VistaVideo()
        self.video.fijar_mensaje("Pulsa «Iniciar cámara» para empezar")

        # --- Panel lateral ---
        self.esquema = EsquemaMano()
        self.esquema.titulo = "Mano robótica"
        self.barras = BarrasDedos()
        self.lbl_gesto = QLabel("—")
        self.lbl_gesto.setProperty("rol", "grande")
        self.lbl_gesto.setAlignment(Qt.AlignCenter)
        self.lbl_info = QLabel("FPS: —")
        self.lbl_info.setProperty("rol", "sub")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setProperty("rol", "instruccion")
        self.lbl_aviso.setAlignment(Qt.AlignCenter)
        self.lbl_aviso.setWordWrap(True)

        self.btn_camara = boton("▶  Iniciar cámara", "primario", self.alternar_camara)
        self.btn_enviar = boton("✋  Controlar la mano con la cámara", al_pulsar=self._alternar_envio,
                                marcable=True,
                                tooltip="La mano robótica copiará tu mano en tiempo real")

        self.spin_camara = QSpinBox()
        self.spin_camara.setRange(0, 9)
        self.spin_camara.setValue(int(ajustes.value("camara/indice", 0)))
        self.combo_res = QComboBox()
        for nombre, _w, _h in RESOLUCIONES:
            self.combo_res.addItem(nombre)
        self.combo_res.setCurrentIndex(int(ajustes.value("camara/resolucion", 0)))
        self.chk_espejo = QCheckBox("Imagen en espejo")
        self.chk_espejo.setChecked(ajustes.value("camara/espejo", "true") in ("true", True))
        self.chk_esqueleto = QCheckBox("Dibujar esqueleto")
        self.chk_esqueleto.setChecked(True)
        self.chk_esqueleto.toggled.connect(self._esqueleto)
        self.chk_binario = QCheckBox("Modo binario (abierto / cerrado)")
        self.chk_binario.setToolTip("Como la versión antigua: cada dedo solo se abre o se cierra del todo")
        self.chk_binario.toggled.connect(self._binario)
        self.slider_suave = QSlider(Qt.Horizontal)
        self.slider_suave.setRange(5, 100)
        self.slider_suave.setValue(int(ajustes.value("camara/suavizado", 45)))
        self.slider_suave.valueChanged.connect(self._suavizado)
        self.lbl_suave = QLabel()
        self._suavizado(self.slider_suave.value())

        grupo_cam = QGroupBox("Cámara")
        form = QFormLayout(grupo_cam)
        form.addRow("Índice:", self.spin_camara)
        form.addRow("Resolución:", self.combo_res)
        form.addRow(self.chk_espejo)
        form.addRow(self.chk_esqueleto)
        fila_suave = QHBoxLayout()
        fila_suave.addWidget(self.slider_suave)
        fila_suave.addWidget(self.lbl_suave)
        form.addRow("Respuesta:", fila_suave)
        form.addRow(self.chk_binario)

        grupo_calib = QGroupBox("Calibración rápida")
        fila_calib = QHBoxLayout(grupo_calib)
        fila_calib.addWidget(boton("Mano abierta", al_pulsar=lambda: self.calibrar("abierto"),
                                   tooltip="Abre la mano del todo y pulsa"))
        fila_calib.addWidget(boton("Puño", al_pulsar=lambda: self.calibrar("cerrado"),
                                   tooltip="Cierra el puño y pulsa"))
        fila_calib.addWidget(boton("Restablecer", "aviso", self.restablecer_calibracion))

        lateral = QVBoxLayout()
        lateral.addWidget(self.btn_camara)
        lateral.addWidget(self.btn_enviar)
        lateral.addWidget(self.esquema, 1)
        lateral.addWidget(self.lbl_gesto)
        lateral.addWidget(self.lbl_info)
        lateral.addWidget(self.barras)
        lateral.addWidget(self.lbl_aviso)
        lateral.addWidget(grupo_calib)
        lateral.addWidget(grupo_cam)
        contenedor = QWidget()
        contenedor.setLayout(lateral)
        contenedor.setFixedWidth(360)

        principal = QHBoxLayout(self)
        principal.addWidget(self.video, 1)
        principal.addWidget(contenedor)

        self.ctrl.fuente_cambiada.connect(self._fuente_cambiada)
        self.ctrl.pose_enviada.connect(self._pose_enviada)

    # ------------------------------------------------------------------
    @property
    def en_marcha(self):
        return self.hilo is not None and self.hilo.isRunning()

    def alternar_camara(self):
        if self.en_marcha:
            self.detener_camara()
        else:
            self.iniciar_camara()

    def iniciar_camara(self):
        if self.en_marcha:
            return
        _, ancho, alto = RESOLUCIONES[self.combo_res.currentIndex()]
        self.hilo = HiloCamara(self.spin_camara.value(), ancho, alto, self.chk_espejo.isChecked())
        self.hilo.dibujar_esqueleto = self.chk_esqueleto.isChecked()
        self.hilo.fijar_suavizado(self.slider_suave.value() / 100)
        self.hilo.frame_listo.connect(self.video.fijar_imagen)
        self.hilo.datos_mano.connect(self._datos)
        self.hilo.calibracion_terminada.connect(self._calibracion_terminada)
        self.hilo.error.connect(self._error)
        self.hilo.mensaje.connect(self.video.fijar_mensaje)
        self.hilo.finished.connect(self._hilo_terminado)
        self.hilo.start()
        self.btn_camara.setText("■  Detener cámara")
        for w in (self.spin_camara, self.combo_res, self.chk_espejo):
            w.setEnabled(False)
        self.ajustes.setValue("camara/indice", self.spin_camara.value())
        self.ajustes.setValue("camara/resolucion", self.combo_res.currentIndex())
        self.ajustes.setValue("camara/espejo", self.chk_espejo.isChecked())
        self.estado_camara.emit(True)

    def detener_camara(self):
        if self.hilo is not None:
            self.hilo.detener()
            self.hilo.wait(3000)
        self._hilo_terminado()

    def _hilo_terminado(self):
        if self.hilo is not None and self.hilo.isRunning():
            return
        self.hilo = None
        self.btn_camara.setText("▶  Iniciar cámara")
        for w in (self.spin_camara, self.combo_res, self.chk_espejo):
            w.setEnabled(True)
        if self.ctrl.fuente == FUENTE_CAMARA:
            self.ctrl.fijar_fuente(FUENTE_PARADO)
        if self.video.imagen is not None:
            self.video.fijar_mensaje("Cámara detenida")
        self.estado_camara.emit(False)

    def _error(self, texto):
        self.video.fijar_mensaje(f"⚠  {texto}")
        self.lbl_aviso.setText(texto)

    def _alternar_envio(self, marcado):
        if marcado:
            if not self.en_marcha:
                self.iniciar_camara()
            self.ctrl.fijar_fuente(FUENTE_CAMARA)
        elif self.ctrl.fuente == FUENTE_CAMARA:
            self.ctrl.fijar_fuente(FUENTE_PARADO)

    def _fuente_cambiada(self, fuente):
        self.btn_enviar.blockSignals(True)
        self.btn_enviar.setChecked(fuente == FUENTE_CAMARA)
        self.btn_enviar.blockSignals(False)

    def _pose_enviada(self, pose):
        if self.ctrl.fuente not in (FUENTE_CAMARA, FUENTE_PARADO):
            self.esquema.fijar(pose)

    def _datos(self, datos):
        self.ctrl.actualizar_camara(datos["porcentajes"], datos["estados"], datos["detectada"])
        self.barras.fijar(datos["porcentajes"], datos["estados"])
        # Con otra fuente activa el esquema muestra lo que se envía (ver _pose_enviada)
        if self.ctrl.fuente in (FUENTE_CAMARA, FUENTE_PARADO):
            binario = self.ctrl.modo_binario
            self.esquema.fijar([e * 100 for e in datos["estados"]] if binario else datos["porcentajes"])
        self.lbl_gesto.setText(datos.get("gesto", "—"))
        lado = {"Left": "izquierda", "Right": "derecha"}.get(datos.get("lateralidad", ""), "")
        self.lbl_info.setText(f"FPS: {datos['fps']:.0f}" + (f"  ·  mano {lado}" if lado else ""))
        if datos.get("calibrando"):
            estado = "ABIERTA" if datos["calibrando"] == "abierto" else "CERRADA (puño)"
            self.lbl_aviso.setText(f"Mantén la mano {estado}… {datos['restante']:.1f} s")
        elif self.lbl_aviso.text().startswith("Mantén"):
            self.lbl_aviso.setText("")
        self.datos_camara.emit(datos)

    def _calibracion_terminada(self, tipo, calib):
        textos = {"abierto": "Calibración de mano abierta guardada ✓",
                  "cerrado": "Calibración de puño guardada ✓",
                  "defecto": "Calibración restablecida"}
        self.lbl_aviso.setText(textos.get(tipo, tipo))
        self.calibracion_terminada.emit(tipo, calib)

    def calibrar(self, tipo, duracion=1.0):
        if not self.en_marcha:
            self.iniciar_camara()
        self.hilo.calibrar(tipo, duracion)

    def restablecer_calibracion(self):
        if self.hilo is not None:
            self.hilo.restablecer_calibracion()
        else:
            calib = calibracion_defecto()
            guardar_calibracion(calib)
            self._calibracion_terminada("defecto", calib)

    def _esqueleto(self, activo):
        if self.hilo is not None:
            self.hilo.dibujar_esqueleto = activo

    def _binario(self, activo):
        self.ctrl.modo_binario = activo

    def _suavizado(self, valor):
        self.lbl_suave.setText(f"{valor}%")
        self.ajustes.setValue("camara/suavizado", valor)
        if self.hilo is not None:
            self.hilo.fijar_suavizado(valor / 100)

    def cerrar(self):
        self.detener_camara()
