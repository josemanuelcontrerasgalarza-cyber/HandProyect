"""Pestaña Manual: sliders por dedo, gestos y acciones del firmware."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from ...secuencias import GESTOS
from ...vision import DEDOS_NOMBRES_BONITOS
from ..controlador import FUENTE_DEMO, FUENTE_MANUAL, FUENTE_PARADO
from ..widgets import COLORES_DEDOS, EsquemaMano
from . import boton


class PestanaManual(QWidget):
    def __init__(self, controlador, ajustes, parent=None):
        super().__init__(parent)
        self.ctrl = controlador
        self.ajustes = ajustes
        self.sliders = []
        self.spins = []

        self.btn_vivo = boton("✋  Controlar la mano con los sliders", al_pulsar=self._alternar_vivo,
                              marcable=True,
                              tooltip="Mientras está activo, la mano sigue los sliders en tiempo real")

        # --- Sliders verticales ---
        grupo_dedos = QGroupBox("Dedos (% abierto)")
        rejilla = QGridLayout(grupo_dedos)
        for i, nombre in enumerate(DEDOS_NOMBRES_BONITOS):
            etiqueta = QLabel(nombre)
            etiqueta.setAlignment(Qt.AlignCenter)
            etiqueta.setStyleSheet(f"color: {COLORES_DEDOS[i].name()}; font-weight: bold;")
            slider = QSlider(Qt.Vertical)
            slider.setRange(0, 100)
            slider.setValue(100)
            slider.setMinimumHeight(220)
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setValue(100)
            spin.setSuffix(" %")
            slider.valueChanged.connect(lambda v, d=i: self._cambio(d, v, origen="slider"))
            spin.valueChanged.connect(lambda v, d=i: self._cambio(d, v, origen="spin"))
            rejilla.addWidget(etiqueta, 0, i)
            rejilla.addWidget(slider, 1, i, Qt.AlignHCenter)
            rejilla.addWidget(spin, 2, i)
            self.sliders.append(slider)
            self.spins.append(spin)

        fila_rapida = QHBoxLayout()
        fila_rapida.addWidget(boton("Abrir todo", al_pulsar=lambda: self.fijar_pose([100] * 5)))
        fila_rapida.addWidget(boton("Cerrar todo", al_pulsar=lambda: self.fijar_pose([0] * 5)))
        fila_rapida.addWidget(boton("Mitad", al_pulsar=lambda: self.fijar_pose([50] * 5)))
        rejilla.addLayout(fila_rapida, 3, 0, 1, 5)

        # --- Gestos ---
        grupo_gestos = QGroupBox("Gestos")
        rejilla_g = QGridLayout(grupo_gestos)
        for n, (nombre, pose) in enumerate(GESTOS.items()):
            b = boton(nombre.capitalize(), al_pulsar=lambda _=False, p=pose: self._gesto(p),
                      tooltip=" / ".join(f"{d[:3]} {v}%" for d, v in zip(DEDOS_NOMBRES_BONITOS, pose)))
            rejilla_g.addWidget(b, n // 4, n % 4)

        # --- Acciones del firmware ---
        grupo_esp = QGroupBox("Acciones en la ESP32")
        caja_esp = QVBoxLayout(grupo_esp)
        fila1 = QHBoxLayout()
        self.btn_demo = boton("▶  Demo de la ESP32", al_pulsar=self._demo, marcable=True)
        fila1.addWidget(self.btn_demo)
        fila1.addWidget(boton("Relajar servos", "aviso", lambda: self._accion("RELAX"),
                              "Quita la fuerza a los servos (los dedos quedan sueltos)"))
        fila1.addWidget(boton("Estado", al_pulsar=lambda: self.ctrl.comando("STATUS")))
        caja_esp.addLayout(fila1)

        fila_vel = QHBoxLayout()
        fila_vel.addWidget(QLabel("Velocidad de los servos:"))
        self.slider_vel = QSlider(Qt.Horizontal)
        self.slider_vel.setRange(1, 100)
        self.slider_vel.setValue(int(ajustes.value("manual/velocidad", 60)))
        self.lbl_vel = QLabel(f"{self.slider_vel.value()}%")
        self.slider_vel.valueChanged.connect(lambda v: self.lbl_vel.setText(f"{v}%"))
        self.slider_vel.sliderReleased.connect(self._enviar_velocidad)
        fila_vel.addWidget(self.slider_vel, 1)
        fila_vel.addWidget(self.lbl_vel)
        caja_esp.addLayout(fila_vel)
        nota = QLabel("La velocidad se guarda en la ESP32 al pulsar «Guardar» en Calibración.")
        nota.setProperty("rol", "sub")
        nota.setWordWrap(True)
        caja_esp.addWidget(nota)

        # --- Vista previa ---
        self.esquema = EsquemaMano()
        self.esquema.titulo = "Vista previa"

        izquierda = QVBoxLayout()
        izquierda.addWidget(self.btn_vivo)
        izquierda.addWidget(grupo_dedos, 1)
        izquierda.addWidget(grupo_gestos)
        izquierda.addWidget(grupo_esp)
        principal = QHBoxLayout(self)
        principal.addLayout(izquierda, 3)
        principal.addWidget(self.esquema, 2)

        self.ctrl.fuente_cambiada.connect(self._fuente_cambiada)
        self.ctrl.pose_enviada.connect(self._pose_enviada)

    # ------------------------------------------------------------------
    def pose(self):
        return [s.value() for s in self.sliders]

    def fijar_pose(self, pose):
        for i, v in enumerate(pose):
            for w in (self.sliders[i], self.spins[i]):
                w.blockSignals(True)
                w.setValue(int(round(v)))
                w.blockSignals(False)
        self.ctrl.fijar_pose_manual(self.pose())
        self.esquema.fijar(self.pose())

    def _cambio(self, dedo, valor, origen):
        otro = self.spins[dedo] if origen == "slider" else self.sliders[dedo]
        otro.blockSignals(True)
        otro.setValue(valor)
        otro.blockSignals(False)
        self.ctrl.fijar_dedo_manual(dedo, valor)
        self.esquema.resaltado = dedo
        self.esquema.fijar(self.pose())

    def _gesto(self, pose):
        self.fijar_pose(pose)
        self.ctrl.tomar_control_manual(pose)

    def _alternar_vivo(self, marcado):
        if marcado:
            self.ctrl.tomar_control_manual(self.pose())
        elif self.ctrl.fuente == FUENTE_MANUAL:
            self.ctrl.fijar_fuente(FUENTE_PARADO)

    def _demo(self, marcado):
        self.ctrl.fijar_fuente(FUENTE_DEMO if marcado else FUENTE_PARADO)

    def _accion(self, comando):
        self.ctrl.fijar_fuente(FUENTE_PARADO)
        self.ctrl.comando(comando)

    def _enviar_velocidad(self):
        valor = self.slider_vel.value()
        self.ajustes.setValue("manual/velocidad", valor)
        self.ctrl.comando(f"SPEED {valor}")

    def _fuente_cambiada(self, fuente):
        for b, f in ((self.btn_vivo, FUENTE_MANUAL), (self.btn_demo, FUENTE_DEMO)):
            b.blockSignals(True)
            b.setChecked(fuente == f)
            b.blockSignals(False)
        if fuente == FUENTE_MANUAL:
            # La fuente manual arranca desde la última pose enviada: reflejarla
            self.fijar_pose(self.ctrl.pose_manual)

    def _pose_enviada(self, pose):
        if self.ctrl.fuente != FUENTE_MANUAL and self.isVisible():
            self.esquema.fijar(pose)
