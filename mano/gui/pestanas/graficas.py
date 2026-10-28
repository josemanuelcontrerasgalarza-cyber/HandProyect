"""Pestaña Gráficas: pose enviada a la mano y lectura de la cámara en tiempo real."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QVBoxLayout, QWidget)

from ...vision import DEDOS_NOMBRES_BONITOS
from ..controlador import NOMBRES_FUENTE
from ..widgets import COLORES_DEDOS, GraficaTiempoReal
from . import boton

VENTANAS_S = [5, 10, 30, 60]


class PestanaGraficas(QWidget):
    def __init__(self, controlador, pestana_camara, parent=None):
        super().__init__(parent)
        self.ctrl = controlador
        self.grafica_envio = GraficaTiempoReal("Pose enviada a la mano (% abierto)")
        self.grafica_camara = GraficaTiempoReal("Cámara sin filtrar (% abierto)")
        self.graficas = (self.grafica_envio, self.grafica_camara)

        # --- Controles ---
        self.combo_ventana = QComboBox()
        for s in VENTANAS_S:
            self.combo_ventana.addItem(f"{s} s", s)
        self.combo_ventana.setCurrentIndex(1)
        self.combo_ventana.currentIndexChanged.connect(self._ventana)
        self.btn_pausa = boton("⏸  Pausar", al_pulsar=self._pausa, marcable=True)

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Ventana:"))
        fila.addWidget(self.combo_ventana)
        fila.addWidget(self.btn_pausa)
        fila.addWidget(boton("Limpiar", al_pulsar=self._limpiar))
        fila.addWidget(boton("Exportar CSV…", al_pulsar=self._exportar))
        fila.addSpacing(20)
        for i, nombre in enumerate(DEDOS_NOMBRES_BONITOS):
            chk = QCheckBox(nombre)
            chk.setChecked(True)
            chk.setStyleSheet(f"color: {COLORES_DEDOS[i].name()};")
            chk.toggled.connect(lambda v, d=i: [g.fijar_visible(d, v) for g in self.graficas])
            fila.addWidget(chk)
        fila.addStretch(1)

        # --- Estadísticas ---
        grupo = QGroupBox("Estadísticas")
        rejilla = QGridLayout(grupo)
        self.lbl_fuente = QLabel("—")
        self.lbl_tramas = QLabel("—")
        self.lbl_lineas = QLabel("—")
        self.lbl_fps = QLabel("—")
        self.lbl_esp = QLabel("Pulsa «Estado» para leerlo")
        for fila_n, (titulo, lbl) in enumerate([("Fuente de control", self.lbl_fuente),
                                                ("Tramas enviadas / s", self.lbl_tramas),
                                                ("Líneas recibidas / s", self.lbl_lineas),
                                                ("FPS de la cámara", self.lbl_fps),
                                                ("ESP32", self.lbl_esp)]):
            t = QLabel(titulo)
            t.setProperty("rol", "sub")
            rejilla.addWidget(t, fila_n, 0)
            rejilla.addWidget(lbl, fila_n, 1)
        rejilla.addWidget(boton("Estado", al_pulsar=lambda: self.ctrl.comando("STATUS")), 0, 2)

        caja = QVBoxLayout(self)
        caja.addLayout(fila)
        caja.addWidget(self.grafica_envio, 1)
        caja.addWidget(self.grafica_camara, 1)
        caja.addWidget(grupo)

        self.ctrl.pose_enviada.connect(self.grafica_envio.agregar)
        self.ctrl.estadisticas.connect(self._estadisticas)
        self.ctrl.estado_esp.connect(self._estado_esp)
        pestana_camara.datos_camara.connect(self._datos_camara)

    def _datos_camara(self, datos):
        if datos.get("sin_filtrar"):
            self.grafica_camara.agregar(datos["sin_filtrar"])
        self.lbl_fps.setText(f"{datos['fps']:.1f}")

    def _estadisticas(self, est):
        self.lbl_fuente.setText(NOMBRES_FUENTE.get(est["fuente"], est["fuente"]))
        self.lbl_tramas.setText(f"{est['tramas_s']:.1f}")
        self.lbl_lineas.setText(f"{est['lineas_s']:.1f}")

    def _estado_esp(self, info):
        partes = []
        if "modo" in info:
            partes.append(f"modo {info['modo']}, fuente {info['fuente']}, velocidad {info['velocidad']}%")
        if "pca" in info:
            partes.append(f"PCA9685 {info['pca']}, IP {info['ip']}")
        self.lbl_esp.setText(" · ".join(partes) or "—")

    def _ventana(self):
        segundos = self.combo_ventana.currentData()
        for g in self.graficas:
            g.ventana_s = float(segundos)
            g.update()

    def _pausa(self, pausada):
        self.btn_pausa.setText("▶  Continuar" if pausada else "⏸  Pausar")
        for g in self.graficas:
            g.fijar_pausa(pausada)

    def _limpiar(self):
        for g in self.graficas:
            g.limpiar()

    def _exportar(self):
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar datos", "pose_enviada.csv", "CSV (*.csv)")
        if not ruta:
            return
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(self.grafica_envio.a_csv())
        base, _, ext = ruta.rpartition(".")
        with open(f"{base}_camara.{ext}" if base else ruta + "_camara", "w", encoding="utf-8") as f:
            f.write(self.grafica_camara.a_csv())
