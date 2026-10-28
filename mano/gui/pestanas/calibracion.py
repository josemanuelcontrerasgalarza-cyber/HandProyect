"""
Pestaña Calibración:
  1. Asistente guiado para calibrar la cámara a TU mano (abierta / puño).
  2. Ajuste de los pulsos de cada servo (abierto / cerrado) en la ESP32.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QSlider, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...vision import DEDOS_NOMBRES_BONITOS, cargar_calibracion, guardar_calibracion
from ..controlador import FUENTE_PARADO
from . import boton

PULSO_MIN, PULSO_MAX = 100, 600
PULSOS_DEFECTO = [(520, 130), (130, 520), (130, 520), (130, 520), (130, 520)]
CUENTA_ATRAS_S = 3
DURACION_MUESTREO_S = 1.5


class AsistenteCamara(QGroupBox):
    """Asistente paso a paso: mano abierta -> puño -> comprobación."""

    PASOS = [
        ("abierto", "Paso 1 de 2 · Abre la mano del todo",
         "Pon la mano frente a la cámara con los dedos estirados y separados."),
        ("cerrado", "Paso 2 de 2 · Cierra el puño",
         "Cierra el puño con el pulgar por fuera, sin taparlo con los otros dedos."),
    ]

    def __init__(self, pestana_camara, parent=None):
        super().__init__("1 · Calibración de la cámara (asistente guiado)", parent)
        self.camara = pestana_camara
        self.paso = -1
        self.cuenta = 0

        self.lbl_titulo = QLabel("Ajusta la detección a tu mano para que la mano robótica copie todo el recorrido.")
        self.lbl_titulo.setWordWrap(True)
        self.lbl_instruccion = QLabel("")
        self.lbl_instruccion.setProperty("rol", "instruccion")
        self.lbl_instruccion.setWordWrap(True)
        self.lbl_detalle = QLabel("")
        self.lbl_detalle.setProperty("rol", "sub")
        self.lbl_detalle.setWordWrap(True)

        self.btn_empezar = boton("▶  Empezar asistente", "primario", self.empezar)
        self.btn_cancelar = boton("Cancelar", al_pulsar=self.cancelar)
        self.btn_cancelar.setEnabled(False)
        self.btn_restablecer = boton("Restablecer", "aviso", self._restablecer)

        self.tabla = QTableWidget(5, 5)
        self.tabla.setHorizontalHeaderLabels(["Dedo", "Medida actual", "Abierto", "Cerrado", "% abierto"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setMinimumHeight(190)
        for i, nombre in enumerate(DEDOS_NOMBRES_BONITOS):
            for col in range(5):
                item = QTableWidgetItem(nombre if col == 0 else "—")
                editable = col in (2, 3)
                item.setFlags((item.flags() | Qt.ItemIsEditable) if editable
                              else (item.flags() & ~Qt.ItemIsEditable))
                item.setTextAlignment(Qt.AlignCenter)
                self.tabla.setItem(i, col, item)
        self.btn_aplicar_tabla = boton("Aplicar valores editados", al_pulsar=self._aplicar_tabla,
                                       tooltip="Doble clic en Abierto/Cerrado para editar a mano")
        nota = QLabel("Pulgar: distancia relativa de la punta a la base del meñique. "
                      "Resto de dedos: grados totales de flexión.")
        nota.setProperty("rol", "sub")
        nota.setWordWrap(True)

        botones = QHBoxLayout()
        botones.addWidget(self.btn_empezar)
        botones.addWidget(self.btn_cancelar)
        botones.addStretch(1)
        botones.addWidget(self.btn_aplicar_tabla)
        botones.addWidget(self.btn_restablecer)

        caja = QVBoxLayout(self)
        caja.addWidget(self.lbl_titulo)
        caja.addWidget(self.lbl_instruccion)
        caja.addWidget(self.lbl_detalle)
        caja.addLayout(botones)
        caja.addWidget(self.tabla)
        caja.addWidget(nota)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_cuenta)
        self.camara.datos_camara.connect(self._datos)
        self.camara.calibracion_terminada.connect(self._terminada)
        self._mostrar_calibracion(cargar_calibracion())

    def empezar(self):
        if not self.camara.en_marcha:
            self.camara.iniciar_camara()
        self.btn_empezar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self._ir_a_paso(0)

    def cancelar(self):
        self.timer.stop()
        if self.camara.hilo is not None:
            self.camara.hilo.cancelar_calibracion()
        self.paso = -1
        self.lbl_instruccion.setText("Asistente cancelado.")
        self.lbl_detalle.setText("")
        self.btn_empezar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)

    def _ir_a_paso(self, paso):
        self.paso = paso
        _tipo, titulo, detalle = self.PASOS[paso]
        self.cuenta = CUENTA_ATRAS_S
        self.lbl_instruccion.setText(f"{titulo}  ·  {self.cuenta}")
        self.lbl_detalle.setText(detalle)
        self.timer.start(1000)

    def _tick_cuenta(self):
        self.cuenta -= 1
        tipo, titulo, _ = self.PASOS[self.paso]
        if self.cuenta > 0:
            self.lbl_instruccion.setText(f"{titulo}  ·  {self.cuenta}")
            return
        self.timer.stop()
        self.lbl_instruccion.setText(f"{titulo}  ·  ¡no te muevas!")
        if self.camara.hilo is None:
            self.cancelar()
            return
        self.camara.hilo.calibrar(tipo, DURACION_MUESTREO_S)

    def _terminada(self, tipo, calib):
        self._mostrar_calibracion(calib)
        if self.paso < 0:
            return
        if tipo == self.PASOS[self.paso][0]:
            if self.paso + 1 < len(self.PASOS):
                self._ir_a_paso(self.paso + 1)
            else:
                self.paso = -1
                self.lbl_instruccion.setText("✓ Calibración completada")
                self.lbl_detalle.setText("Abre y cierra la mano: la columna «% abierto» debe ir de 0 a 100.")
                self.btn_empezar.setEnabled(True)
                self.btn_cancelar.setEnabled(False)

    def _datos(self, datos):
        crudas = datos.get("crudas")
        if not crudas:
            return
        for i in range(5):
            self.tabla.item(i, 1).setText(f"{crudas[i]:.2f}" if i == 0 else f"{crudas[i]:.0f}°")
            self.tabla.item(i, 4).setText(f"{datos['porcentajes'][i]:.0f} %")

    def _mostrar_calibracion(self, calib):
        self.tabla.blockSignals(True)
        for i in range(5):
            formato = "{:.2f}" if i == 0 else "{:.0f}"
            self.tabla.item(i, 2).setText(formato.format(calib["abierto"][i]))
            self.tabla.item(i, 3).setText(formato.format(calib["cerrado"][i]))
        self.tabla.blockSignals(False)

    def _aplicar_tabla(self):
        try:
            calib = {"abierto": [float(self.tabla.item(i, 2).text().replace(",", ".")) for i in range(5)],
                     "cerrado": [float(self.tabla.item(i, 3).text().replace(",", ".")) for i in range(5)]}
        except ValueError:
            QMessageBox.warning(self, "Valores no válidos", "Escribe solo números en Abierto y Cerrado.")
            return
        if self.camara.hilo is not None:
            self.camara.hilo.fijar_calibracion(calib)
        else:
            guardar_calibracion(calib)
        self.lbl_instruccion.setText("Valores aplicados y guardados en calibracion.json")

    def _restablecer(self):
        self.cancelar()
        self.camara.restablecer_calibracion()
        self.lbl_instruccion.setText("Calibración de la cámara restablecida")


class CalibracionServos(QGroupBox):
    """Pulsos de cada servo y ajuste fino en vivo."""

    def __init__(self, controlador, parent=None):
        super().__init__("2 · Calibración de los servos (ESP32)", parent)
        self.ctrl = controlador
        self.spins_abierto = []
        self.spins_cerrado = []

        explicacion = QLabel("Ajusta el pulso con el que cada dedo queda totalmente ABIERTO y totalmente "
                             "CERRADO sin forzar el hilo. «Probar» mueve el servo a ese pulso.")
        explicacion.setWordWrap(True)

        rejilla = QGridLayout()
        for col, texto in enumerate(["Dedo", "Abierto", "", "Cerrado", "", ""]):
            lbl = QLabel(texto)
            lbl.setProperty("rol", "sub")
            rejilla.addWidget(lbl, 0, col)
        for i, nombre in enumerate(DEDOS_NOMBRES_BONITOS):
            abierto, cerrado = PULSOS_DEFECTO[i]
            spin_a = self._spin(abierto)
            spin_c = self._spin(cerrado)
            rejilla.addWidget(QLabel(nombre), i + 1, 0)
            rejilla.addWidget(spin_a, i + 1, 1)
            rejilla.addWidget(boton("Probar", al_pulsar=lambda _=False, d=i: self._probar(d, "a")), i + 1, 2)
            rejilla.addWidget(spin_c, i + 1, 3)
            rejilla.addWidget(boton("Probar", al_pulsar=lambda _=False, d=i: self._probar(d, "c")), i + 1, 4)
            rejilla.addWidget(boton("⇄ Invertir", al_pulsar=lambda _=False, d=i: self._invertir(d),
                                    tooltip="Intercambia abierto y cerrado"), i + 1, 5)
            self.spins_abierto.append(spin_a)
            self.spins_cerrado.append(spin_c)

        # Ajuste fino en vivo
        grupo_vivo = QGroupBox("Ajuste fino en vivo")
        caja_vivo = QHBoxLayout(grupo_vivo)
        self.combo_dedo = QComboBox()
        self.combo_dedo.addItems(DEDOS_NOMBRES_BONITOS)
        self.slider_pulso = QSlider(Qt.Horizontal)
        self.slider_pulso.setRange(PULSO_MIN, PULSO_MAX)
        self.slider_pulso.setValue(325)
        self.spin_pulso = self._spin(325)
        self.slider_pulso.valueChanged.connect(self._pulso_vivo)
        self.spin_pulso.valueChanged.connect(self.slider_pulso.setValue)
        caja_vivo.addWidget(self.combo_dedo)
        caja_vivo.addWidget(self.slider_pulso, 1)
        caja_vivo.addWidget(self.spin_pulso)
        caja_vivo.addWidget(boton("→ Abierto", al_pulsar=lambda: self._usar_pulso("a")))
        caja_vivo.addWidget(boton("→ Cerrado", al_pulsar=lambda: self._usar_pulso("c")))

        acciones = QHBoxLayout()
        acciones.addWidget(boton("Leer de la ESP32", al_pulsar=self.leer))
        acciones.addWidget(boton("Probar recorrido", al_pulsar=self._recorrido,
                                 tooltip="Cierra y abre el dedo seleccionado arriba"))
        acciones.addWidget(boton("Aplicar", al_pulsar=self.aplicar,
                                 tooltip="Envía los pulsos a la ESP32 (sin guardar)"))
        acciones.addWidget(boton("💾 Guardar en la ESP32", "primario", self.guardar))
        acciones.addWidget(boton("Valores por defecto", "aviso", self._defecto))
        acciones.addWidget(boton("Terminar (abrir mano)", al_pulsar=self._terminar))

        caja = QVBoxLayout(self)
        caja.addWidget(explicacion)
        caja.addLayout(rejilla)
        caja.addWidget(grupo_vivo)
        caja.addLayout(acciones)
        caja.addStretch(1)

        self._pulso_pendiente = None
        self.timer_pulso = QTimer(self)
        self.timer_pulso.setInterval(60)              # máx. ~16 comandos/s al arrastrar
        self.timer_pulso.timeout.connect(self._enviar_pulso_pendiente)
        self.ctrl.calibracion_servo.connect(self._recibida)

    @staticmethod
    def _spin(valor):
        s = QSpinBox()
        s.setRange(PULSO_MIN, PULSO_MAX)
        s.setValue(valor)
        s.setSuffix(" ticks")
        return s

    def _preparar(self):
        """Antes de mover servos a mano hay que parar el streaming."""
        if self.ctrl.fuente != FUENTE_PARADO:
            self.ctrl.fijar_fuente(FUENTE_PARADO)

    def _probar(self, dedo, cual):
        self._preparar()
        spin = self.spins_abierto[dedo] if cual == "a" else self.spins_cerrado[dedo]
        self.ctrl.comando(f"PULSO {dedo} {spin.value()}")

    def _invertir(self, dedo):
        a, c = self.spins_abierto[dedo].value(), self.spins_cerrado[dedo].value()
        self.spins_abierto[dedo].setValue(c)
        self.spins_cerrado[dedo].setValue(a)
        self.ctrl.comando(f"CAL {dedo} {c} {a}")

    def _pulso_vivo(self, valor):
        self.spin_pulso.blockSignals(True)
        self.spin_pulso.setValue(valor)
        self.spin_pulso.blockSignals(False)
        self._preparar()
        self._pulso_pendiente = (self.combo_dedo.currentIndex(), valor)
        if not self.timer_pulso.isActive():
            self._enviar_pulso_pendiente()
            self.timer_pulso.start()

    def _enviar_pulso_pendiente(self):
        if self._pulso_pendiente is None:
            self.timer_pulso.stop()
            return
        dedo, valor = self._pulso_pendiente
        self._pulso_pendiente = None
        self.ctrl.comando(f"PULSO {dedo} {valor}", eco=False)

    def _usar_pulso(self, cual):
        dedo = self.combo_dedo.currentIndex()
        spin = self.spins_abierto[dedo] if cual == "a" else self.spins_cerrado[dedo]
        spin.setValue(self.slider_pulso.value())

    def _recorrido(self):
        self._preparar()
        dedo = self.combo_dedo.currentIndex()
        self.ctrl.comando(f"CAL {dedo} {self.spins_abierto[dedo].value()} {self.spins_cerrado[dedo].value()}")
        self.ctrl.comando(f"SET {dedo} 0")
        QTimer.singleShot(1200, lambda: self.ctrl.comando(f"SET {dedo} 100"))

    def leer(self):
        self.ctrl.comando("STATUS")

    def aplicar(self):
        self._preparar()
        for i in range(5):
            self.ctrl.comando(f"CAL {i} {self.spins_abierto[i].value()} {self.spins_cerrado[i].value()}")

    def guardar(self):
        self.aplicar()
        self.ctrl.comando("SAVE")

    def _defecto(self):
        respuesta = QMessageBox.question(self, "Valores por defecto",
                                         "¿Volver a los pulsos de fábrica (130 / 520)?")
        if respuesta != QMessageBox.Yes:
            return
        for i, (a, c) in enumerate(PULSOS_DEFECTO):
            self.spins_abierto[i].setValue(a)
            self.spins_cerrado[i].setValue(c)
        self.ctrl.comando("DEFAULTS")

    def _terminar(self):
        self.ctrl.comando("OPEN")

    def _recibida(self, dedo, abierto, cerrado):
        if 0 <= dedo < 5:
            self.spins_abierto[dedo].setValue(abierto)
            self.spins_cerrado[dedo].setValue(cerrado)


class PestanaCalibracion(QWidget):
    def __init__(self, controlador, pestana_camara, parent=None):
        super().__init__(parent)
        self.asistente = AsistenteCamara(pestana_camara)
        self.servos = CalibracionServos(controlador)
        caja = QHBoxLayout(self)
        caja.addWidget(self.asistente, 1)
        caja.addWidget(self.servos, 1)
