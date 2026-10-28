"""Pestaña Consola: comunicación en texto con la ESP32 (como el Monitor Serie)."""
import html
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLineEdit, QTextEdit,
                               QVBoxLayout, QWidget)

from . import boton

ATAJOS = ["HELP", "STATUS", "PING", "GESTOS", "OPEN", "CLOSE", "DEMO", "STOP", "RELAX", "SAVE"]
MAX_LINEAS = 3000

COLORES = {"tx": "#4dabf7", "rx": "#e6e8ef", "error": "#ff6b6b", "app": "#ffb020", "trama": "#5b6178"}


class EntradaConHistorial(QLineEdit):
    """QLineEdit con historial usando las flechas arriba / abajo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.historial = []
        self.posicion = 0

    def agregar_historial(self, texto):
        if texto and (not self.historial or self.historial[-1] != texto):
            self.historial.append(texto)
        self.posicion = len(self.historial)

    def keyPressEvent(self, evento: QKeyEvent):
        if evento.key() == Qt.Key_Up and self.historial:
            self.posicion = max(0, self.posicion - 1)
            self.setText(self.historial[self.posicion])
        elif evento.key() == Qt.Key_Down and self.historial:
            self.posicion = min(len(self.historial), self.posicion + 1)
            self.setText(self.historial[self.posicion] if self.posicion < len(self.historial) else "")
        else:
            super().keyPressEvent(evento)


class PestanaConsola(QWidget):
    def __init__(self, controlador, parent=None):
        super().__init__(parent)
        self.ctrl = controlador
        self.lineas = 0

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        fuente = QFont("Monospace")
        fuente.setStyleHint(QFont.TypeWriter)
        self.log.setFont(fuente)

        self.entrada = EntradaConHistorial()
        self.entrada.setPlaceholderText("Escribe un comando (HELP para ver la lista) y pulsa Enter")
        self.entrada.returnPressed.connect(self._enviar)

        self.chk_tramas = QCheckBox("Mostrar tramas P: enviadas")
        self.chk_tramas.setToolTip("Muestra las 30 tramas por segundo que se envían (mucho texto)")
        self.chk_hora = QCheckBox("Hora")
        self.chk_hora.setChecked(True)
        self.chk_auto = QCheckBox("Desplazamiento automático")
        self.chk_auto.setChecked(True)

        fila_entrada = QHBoxLayout()
        fila_entrada.addWidget(self.entrada, 1)
        fila_entrada.addWidget(boton("Enviar", "primario", self._enviar))

        fila_atajos = QHBoxLayout()
        for cmd in ATAJOS:
            fila_atajos.addWidget(boton(cmd, al_pulsar=lambda _=False, c=cmd: self.enviar(c)))
        fila_atajos.addStretch(1)

        fila_opciones = QHBoxLayout()
        fila_opciones.addWidget(self.chk_tramas)
        fila_opciones.addWidget(self.chk_hora)
        fila_opciones.addWidget(self.chk_auto)
        fila_opciones.addStretch(1)
        fila_opciones.addWidget(boton("Limpiar", al_pulsar=self.limpiar))
        fila_opciones.addWidget(boton("Guardar registro…", al_pulsar=self._guardar))

        caja = QVBoxLayout(self)
        caja.addLayout(fila_atajos)
        caja.addWidget(self.log, 1)
        caja.addLayout(fila_entrada)
        caja.addLayout(fila_opciones)

        self.ctrl.linea_recibida.connect(lambda t: self.agregar(t, "error" if "[ERROR" in t else
                                                                 "app" if t.startswith("[APP]") else "rx"))
        self.ctrl.linea_enviada.connect(lambda t: self.agregar("» " + t, "tx"))
        self.ctrl.pose_enviada.connect(self._trama)

    def enviar(self, texto):
        self.ctrl.comando(texto)

    def _enviar(self):
        texto = self.entrada.text().strip()
        if not texto:
            return
        self.entrada.agregar_historial(texto)
        self.entrada.clear()
        self.enviar(texto)

    def _trama(self, pose):
        if self.chk_tramas.isChecked():
            self.agregar("» P:" + ",".join(str(int(round(v))) for v in pose), "trama")

    def agregar(self, texto, tipo="rx"):
        prefijo = time.strftime("%H:%M:%S ") if self.chk_hora.isChecked() else ""
        color = COLORES.get(tipo, COLORES["rx"])
        self.log.append(f'<span style="color:#5b6178">{prefijo}</span>'
                        f'<span style="color:{color}">{html.escape(texto)}</span>')
        self.lineas += 1
        if self.lineas > MAX_LINEAS:
            cursor = self.log.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, MAX_LINEAS // 5)
            cursor.removeSelectedText()
            self.lineas -= MAX_LINEAS // 5
        if self.chk_auto.isChecked():
            self.log.moveCursor(QTextCursor.End)

    def limpiar(self):
        self.log.clear()
        self.lineas = 0

    def _guardar(self):
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar registro", "consola_mano.txt", "Texto (*.txt)")
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(self.log.toPlainText())
