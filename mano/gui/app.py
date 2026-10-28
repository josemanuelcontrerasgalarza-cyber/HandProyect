"""Ventana principal de la aplicación de escritorio."""
import os
import sys

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QSizePolicy, QTabWidget, QToolBar, QWidget)

from ..enlace import IP_AP_POR_DEFECTO, listar_puertos
from ..rutas import DIRECTORIO_RECURSOS
from .controlador import NOMBRES_FUENTE, Controlador
from .estilo import HOJA_ESTILO
from .pestanas import boton
from .pestanas.calibracion import PestanaCalibracion
from .pestanas.camara import PestanaCamara
from .pestanas.consola import PestanaConsola
from .pestanas.graficas import PestanaGraficas
from .pestanas.manual import PestanaManual
from .pestanas.secuencias import PestanaSecuencias
from .widgets import LedEstado

TIPO_USB, TIPO_WIFI, TIPO_SIM = "USB", "WiFi", "Simulación"

AYUDA_ATAJOS = """
<b>Atajos de teclado</b><br><br>
<b>Esc</b> — Parada: deja de enviar y abre la mano<br>
<b>Ctrl+1 … Ctrl+6</b> — Cambiar de pestaña<br>
<b>F5</b> — Iniciar / detener la cámara<br>
<b>F6</b> — Controlar la mano con la cámara<br>
<b>Ctrl+K</b> — Conectar / desconectar<br>
<b>F1</b> — Esta ayuda
"""

ACERCA_DE = """
<b>HandProyect · Mano Biónica ESP32-S3</b><br><br>
Control de una mano robótica de 5 dedos con visión artificial (MediaPipe),
por USB o WiFi, con calibración, secuencias y telemetría.<br><br>
Firmware: <code>firmware/ManoBionicaESP32S3</code>
"""


class VentanaPrincipal(QMainWindow):
    def __init__(self, conexion_inicial=None):
        super().__init__()
        self.setWindowTitle("Mano Biónica · ESP32-S3")
        self.ajustes = QSettings("HandProyect", "ManoBionica")
        self.ctrl = Controlador(self)

        # --- Pestañas ---
        self.pestana_camara = PestanaCamara(self.ctrl, self.ajustes)
        self.pestana_manual = PestanaManual(self.ctrl, self.ajustes)
        self.pestana_calibracion = PestanaCalibracion(self.ctrl, self.pestana_camara)
        self.pestana_graficas = PestanaGraficas(self.ctrl, self.pestana_camara)
        self.pestana_consola = PestanaConsola(self.ctrl)
        self.pestana_secuencias = PestanaSecuencias(self.ctrl)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        for pestana, titulo in ((self.pestana_camara, "📷  Cámara"),
                                (self.pestana_manual, "🎚  Manual"),
                                (self.pestana_secuencias, "🎞  Secuencias"),
                                (self.pestana_calibracion, "🎯  Calibración"),
                                (self.pestana_graficas, "📈  Gráficas"),
                                (self.pestana_consola, "⌨  Consola")):
            self.tabs.addTab(pestana, titulo)
        self.setCentralWidget(self.tabs)

        self._crear_barra_conexion()
        self._crear_menus()
        self._crear_barra_estado()
        self._crear_atajos()

        self.ctrl.enlace_cambiado.connect(self._enlace_cambiado)
        self.ctrl.fuente_cambiada.connect(self._fuente_cambiada)
        self.ctrl.estadisticas.connect(self._estadisticas)
        self._enlace_cambiado(*self.ctrl.estado_enlace())
        self._fuente_cambiada(self.ctrl.fuente)

        self._restaurar_ajustes()
        if conexion_inicial:
            QTimer.singleShot(0, lambda: self._conexion_inicial(*conexion_inicial))

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------
    def _crear_barra_conexion(self):
        barra = QToolBar("Conexión")
        barra.setMovable(False)
        self.addToolBar(barra)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems([TIPO_USB, TIPO_WIFI, TIPO_SIM])
        self.combo_tipo.currentTextChanged.connect(self._tipo_cambiado)
        self.combo_puerto = QComboBox()
        self.combo_puerto.setMinimumWidth(230)
        self.btn_refrescar = boton("⟳", al_pulsar=self._refrescar_puertos, tooltip="Buscar puertos")
        self.edit_ip = QLineEdit(IP_AP_POR_DEFECTO)
        self.edit_ip.setPlaceholderText("IP de la ESP32")
        self.edit_ip.setFixedWidth(150)
        self.btn_conectar = boton("Conectar", "primario", self._alternar_conexion)

        barra.addWidget(QLabel(" Conexión: "))
        barra.addWidget(self.combo_tipo)
        self.accion_puerto = barra.addWidget(self.combo_puerto)
        self.accion_refrescar = barra.addWidget(self.btn_refrescar)
        self.accion_ip = barra.addWidget(self.edit_ip)
        barra.addWidget(self.btn_conectar)
        barra.addSeparator()

        barra.addWidget(QLabel(" Fuente: "))
        self.combo_fuente = QComboBox()
        for clave, nombre in NOMBRES_FUENTE.items():
            self.combo_fuente.addItem(nombre, clave)
        self.combo_fuente.setToolTip("Quién mueve la mano ahora mismo")
        self.combo_fuente.activated.connect(lambda i: self.ctrl.fijar_fuente(self.combo_fuente.itemData(i)))
        barra.addWidget(self.combo_fuente)

        espaciador = QWidget()
        espaciador.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        barra.addWidget(espaciador)
        self.btn_parada = boton("⏹  PARADA (Esc)", "peligro", self.ctrl.parada,
                                "Deja de enviar movimientos y abre la mano")
        barra.addWidget(self.btn_parada)

        self._refrescar_puertos()
        self._tipo_cambiado(self.combo_tipo.currentText())

    def _crear_menus(self):
        menu_archivo = self.menuBar().addMenu("&Archivo")
        accion_salir = QAction("Salir", self)
        accion_salir.setShortcut(QKeySequence.Quit)
        accion_salir.triggered.connect(self.close)
        menu_archivo.addAction(accion_salir)

        menu_mano = self.menuBar().addMenu("&Mano")
        for texto, cmd in (("Abrir", "OPEN"), ("Cerrar", "CLOSE"), ("Relajar servos", "RELAX"),
                           ("Estado", "STATUS"), ("Ayuda del firmware", "HELP")):
            accion = QAction(texto, self)
            accion.triggered.connect(lambda _=False, c=cmd: self.ctrl.comando(c))
            menu_mano.addAction(accion)

        menu_ayuda = self.menuBar().addMenu("A&yuda")
        accion_atajos = QAction("Atajos de teclado", self)
        accion_atajos.setShortcut(QKeySequence.HelpContents)
        accion_atajos.triggered.connect(lambda: QMessageBox.information(self, "Atajos", AYUDA_ATAJOS))
        accion_acerca = QAction("Acerca de", self)
        accion_acerca.triggered.connect(lambda: QMessageBox.about(self, "Acerca de", ACERCA_DE))
        menu_ayuda.addAction(accion_atajos)
        menu_ayuda.addAction(accion_acerca)

    def _crear_barra_estado(self):
        self.led = LedEstado()
        self.lbl_enlace = QLabel("Sin conexión")
        self.lbl_fuente = QLabel("")
        self.lbl_tasa = QLabel("")
        barra = self.statusBar()
        barra.addWidget(self.led)
        barra.addWidget(self.lbl_enlace, 1)
        barra.addPermanentWidget(self.lbl_fuente)
        barra.addPermanentWidget(self.lbl_tasa)

    def _crear_atajos(self):
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.ctrl.parada)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._alternar_conexion)
        QShortcut(QKeySequence(Qt.Key_F5), self, activated=self.pestana_camara.alternar_camara)
        QShortcut(QKeySequence(Qt.Key_F6), self,
                  activated=lambda: self.pestana_camara.btn_enviar.click())
        for i in range(self.tabs.count()):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda i=i: self.tabs.setCurrentIndex(i))

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------
    def _refrescar_puertos(self):
        actual = self.combo_puerto.currentData()
        self.combo_puerto.clear()
        self.combo_puerto.addItem("Automático", None)
        for dispositivo, descripcion in listar_puertos():
            self.combo_puerto.addItem(descripcion, dispositivo)
        indice = self.combo_puerto.findData(actual)
        self.combo_puerto.setCurrentIndex(max(0, indice))

    def _tipo_cambiado(self, tipo):
        self.accion_puerto.setVisible(tipo == TIPO_USB)
        self.accion_refrescar.setVisible(tipo == TIPO_USB)
        self.accion_ip.setVisible(tipo == TIPO_WIFI)

    def _alternar_conexion(self):
        if self.ctrl.enlace is not None:
            self.ctrl.desconectar()
            return
        tipo = self.combo_tipo.currentText()
        if tipo == TIPO_USB:
            ok = self.ctrl.conectar_usb(self.combo_puerto.currentData())
            if not ok:
                self.statusBar().showMessage(
                    "No se encuentra la ESP32 por USB. Se reintentará automáticamente cada 2 s.", 6000)
        elif tipo == TIPO_WIFI:
            ip = self.edit_ip.text().strip() or IP_AP_POR_DEFECTO
            self.ctrl.conectar_wifi(ip)
        else:
            self.ctrl.conectar_simulacion()
        self.ajustes.setValue("conexion/tipo", tipo)
        self.ajustes.setValue("conexion/ip", self.edit_ip.text().strip())
        self.ajustes.setValue("conexion/puerto", self.combo_puerto.currentData() or "")

    def _conexion_inicial(self, tipo, valor):
        self.combo_tipo.setCurrentText(tipo)
        if tipo == TIPO_WIFI and valor:
            self.edit_ip.setText(valor)
        elif tipo == TIPO_USB and valor:
            if self.combo_puerto.findData(valor) < 0:
                self.combo_puerto.addItem(valor, valor)
            self.combo_puerto.setCurrentIndex(self.combo_puerto.findData(valor))
        self._alternar_conexion()

    def _enlace_cambiado(self, descripcion, estado):
        self.led.fijar(estado)
        self.lbl_enlace.setText(descripcion)
        conectado = self.ctrl.enlace is not None
        self.btn_conectar.setText("Desconectar" if conectado else "Conectar")
        self.btn_conectar.setProperty("rol", "aviso" if conectado else "primario")
        self.btn_conectar.style().unpolish(self.btn_conectar)
        self.btn_conectar.style().polish(self.btn_conectar)
        for w in (self.combo_tipo, self.combo_puerto, self.btn_refrescar, self.edit_ip):
            w.setEnabled(not conectado)

    def _fuente_cambiada(self, fuente):
        self.combo_fuente.setCurrentIndex(self.combo_fuente.findData(fuente))
        self.lbl_fuente.setText(f"Fuente: {NOMBRES_FUENTE[fuente]}")

    def _estadisticas(self, est):
        self.lbl_tasa.setText(f"{est['tramas_s']:.0f} tramas/s")

    # ------------------------------------------------------------------
    # Ajustes y cierre
    # ------------------------------------------------------------------
    def _restaurar_ajustes(self):
        geometria = self.ajustes.value("ventana/geometria")
        if geometria is not None:
            self.restoreGeometry(geometria)
        else:
            self.resize(1360, 860)
        self.combo_tipo.setCurrentText(str(self.ajustes.value("conexion/tipo", TIPO_USB)))
        ip = str(self.ajustes.value("conexion/ip", "") or "")
        if ip:
            self.edit_ip.setText(ip)
        puerto = str(self.ajustes.value("conexion/puerto", "") or "")
        if puerto and self.combo_puerto.findData(puerto) >= 0:
            self.combo_puerto.setCurrentIndex(self.combo_puerto.findData(puerto))
        self.tabs.setCurrentIndex(int(self.ajustes.value("ventana/pestana", 0)))

    def closeEvent(self, evento):
        if not self.pestana_secuencias.cerrar():
            evento.ignore()
            return
        self.ajustes.setValue("ventana/geometria", self.saveGeometry())
        self.ajustes.setValue("ventana/pestana", self.tabs.currentIndex())
        self.pestana_camara.cerrar()
        self.ctrl.cerrar()
        evento.accept()


def ejecutar(argv=None, conexion_inicial=None):
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Mano Biónica")
    app.setStyle("Fusion")
    app.setStyleSheet(HOJA_ESTILO)
    icono = os.path.join(DIRECTORIO_RECURSOS, "recursos", "mano.ico")
    if os.path.exists(icono):
        app.setWindowIcon(QIcon(icono))
    ventana = VentanaPrincipal(conexion_inicial)
    ventana.show()
    return app.exec()
