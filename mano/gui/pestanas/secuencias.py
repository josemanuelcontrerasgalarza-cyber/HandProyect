"""Pestaña Secuencias: editor de poses encadenadas y reproductor."""
import copy
import os
import re
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
                               QSpinBox, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ...secuencias import (CURVAS, DIRECTORIO_SECUENCIAS, GESTOS, Paso, Secuencia,
                           listar_secuencias_guardadas, secuencias_ejemplo)
from ...vision import DEDOS_NOMBRES_BONITOS
from ..controlador import FUENTE_SECUENCIA
from ..widgets import EsquemaMano
from . import boton

COL_NOMBRE = 0
COL_DEDOS = range(1, 6)
COL_TRANSICION = 6
COL_PAUSA = 7
COL_CURVA = 8
CABECERAS = ["Nombre", *DEDOS_NOMBRES_BONITOS, "Trans. ms", "Pausa ms", "Curva"]
NOMBRES_CURVA = {"suave": "Suave", "lineal": "Lineal", "instantanea": "Instantánea"}


class DelegadoPaso(QStyledItemDelegate):
    """Editores adecuados para cada columna de la tabla de pasos."""

    def createEditor(self, parent, opcion, indice):
        col = indice.column()
        if col in COL_DEDOS:
            editor = QSpinBox(parent)
            editor.setRange(0, 100)
            editor.setSuffix(" %")
            return editor
        if col in (COL_TRANSICION, COL_PAUSA):
            editor = QSpinBox(parent)
            editor.setRange(0, 60000)
            editor.setSingleStep(50)
            return editor
        if col == COL_CURVA:
            editor = QComboBox(parent)
            for clave in CURVAS:
                editor.addItem(NOMBRES_CURVA[clave], clave)
            return editor
        return super().createEditor(parent, opcion, indice)

    def setEditorData(self, editor, indice):
        if isinstance(editor, QSpinBox):
            numeros = re.findall(r"\d+", indice.data() or "0")
            editor.setValue(int(numeros[0]) if numeros else 0)
        elif isinstance(editor, QComboBox):
            clave = indice.data(Qt.UserRole) or "suave"
            editor.setCurrentIndex(max(0, editor.findData(clave)))
        else:
            super().setEditorData(editor, indice)

    def setModelData(self, editor, modelo, indice):
        if isinstance(editor, QSpinBox):
            modelo.setData(indice, str(editor.value()))
        elif isinstance(editor, QComboBox):
            modelo.setData(indice, editor.currentData(), Qt.UserRole)
            modelo.setData(indice, editor.currentText())
        else:
            super().setModelData(editor, modelo, indice)


class PestanaSecuencias(QWidget):
    def __init__(self, controlador, parent=None):
        super().__init__(parent)
        self.ctrl = controlador
        self.secuencia = Secuencia()
        self.ruta = None
        self.modificada = False
        self._actualizando = False

        # --- Biblioteca ---
        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(self._abrir_desde_lista)
        grupo_lib = QGroupBox("Biblioteca")
        caja_lib = QVBoxLayout(grupo_lib)
        caja_lib.addWidget(self.lista, 1)
        fila_lib1 = QHBoxLayout()
        fila_lib1.addWidget(boton("Nueva", al_pulsar=self.nueva))
        fila_lib1.addWidget(boton("Abrir…", al_pulsar=self._abrir_archivo))
        fila_lib2 = QHBoxLayout()
        fila_lib2.addWidget(boton("Guardar", "primario", self.guardar))
        fila_lib2.addWidget(boton("Como…", al_pulsar=self.guardar_como, tooltip="Guardar como…"))
        caja_lib.addLayout(fila_lib1)
        caja_lib.addLayout(fila_lib2)
        caja_lib.addWidget(boton("Eliminar archivo", "peligro", self._eliminar_archivo))
        grupo_lib.setFixedWidth(260)

        # --- Editor ---
        self.edit_nombre = QLineEdit()
        self.edit_nombre.textEdited.connect(self._nombre_editado)
        self.chk_bucle = QCheckBox("Repetir en bucle")
        self.chk_bucle.toggled.connect(self._bucle)
        self.lbl_duracion = QLabel("")
        self.lbl_duracion.setProperty("rol", "sub")

        self.tabla = QTableWidget(0, len(CABECERAS))
        self.tabla.setHorizontalHeaderLabels(CABECERAS)
        self.tabla.setItemDelegate(DelegadoPaso(self.tabla))
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.horizontalHeader().setSectionResizeMode(COL_NOMBRE, QHeaderView.ResizeToContents)
        self.tabla.itemChanged.connect(self._celda_editada)
        self.tabla.itemSelectionChanged.connect(self._seleccion)

        self.combo_gesto = QComboBox()
        self.combo_gesto.addItems([g.capitalize() for g in GESTOS])
        fila_pasos = QHBoxLayout()
        fila_pasos.addWidget(boton("+ Pose de la cámara", al_pulsar=self._agregar_camara,
                                   tooltip="Añade la posición actual de tu mano"))
        fila_pasos.addWidget(boton("+ Pose manual", al_pulsar=self._agregar_manual,
                                   tooltip="Añade la posición de los sliders de la pestaña Manual"))
        fila_pasos.addWidget(self.combo_gesto)
        fila_pasos.addWidget(boton("+ Gesto", al_pulsar=self._agregar_gesto))
        fila_pasos.addStretch(1)
        fila_pasos.addWidget(boton("Duplicar", al_pulsar=self._duplicar))
        fila_pasos.addWidget(boton("▲", al_pulsar=lambda: self._mover(-1), tooltip="Subir paso"))
        fila_pasos.addWidget(boton("▼", al_pulsar=lambda: self._mover(1), tooltip="Bajar paso"))
        fila_pasos.addWidget(boton("Eliminar", "peligro", self._eliminar_paso))

        cabecera = QHBoxLayout()
        cabecera.addWidget(QLabel("Nombre:"))
        cabecera.addWidget(self.edit_nombre, 1)
        cabecera.addWidget(self.chk_bucle)
        cabecera.addWidget(self.lbl_duracion)

        editor = QVBoxLayout()
        editor.addLayout(cabecera)
        editor.addWidget(self.tabla, 1)
        editor.addLayout(fila_pasos)

        # --- Reproductor y vista previa ---
        self.esquema = EsquemaMano()
        self.esquema.titulo = "Paso seleccionado"
        self.btn_play = boton("▶ Play", "primario", self.reproducir, "Reproducir la secuencia")
        self.btn_pausa = boton("⏸ Pausa", al_pulsar=self._pausa, marcable=True)
        self.btn_stop = boton("■ Stop", al_pulsar=self.detener, tooltip="Detener y abrir la mano")
        self.spin_velocidad = QDoubleSpinBox()
        self.spin_velocidad.setRange(0.25, 3.0)
        self.spin_velocidad.setSingleStep(0.25)
        self.spin_velocidad.setValue(1.0)
        self.spin_velocidad.setSuffix(" x")
        self.spin_velocidad.valueChanged.connect(self.ctrl.reproductor.cambiar_velocidad)
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.lbl_paso = QLabel("Detenido")
        self.lbl_paso.setAlignment(Qt.AlignCenter)

        grupo_rep = QGroupBox("Reproducción")
        caja_rep = QVBoxLayout(grupo_rep)
        fila_rep = QHBoxLayout()
        fila_rep.addWidget(self.btn_play)
        fila_rep.addWidget(self.btn_pausa)
        fila_rep.addWidget(self.btn_stop)
        caja_rep.addLayout(fila_rep)
        fila_vel = QHBoxLayout()
        fila_vel.addWidget(QLabel("Velocidad:"))
        fila_vel.addWidget(self.spin_velocidad)
        caja_rep.addLayout(fila_vel)
        caja_rep.addWidget(self.barra)
        caja_rep.addWidget(self.lbl_paso)
        caja_rep.addWidget(boton("Probar paso seleccionado", al_pulsar=self._probar_paso,
                                 tooltip="Mueve la mano a la pose del paso seleccionado"))

        derecha = QVBoxLayout()
        derecha.addWidget(self.esquema, 1)
        derecha.addWidget(grupo_rep)
        contenedor_der = QWidget()
        contenedor_der.setLayout(derecha)
        contenedor_der.setFixedWidth(330)

        principal = QHBoxLayout(self)
        principal.addWidget(grupo_lib)
        principal.addLayout(editor, 1)
        principal.addWidget(contenedor_der)

        self.ctrl.paso_secuencia.connect(self._progreso)
        self.ctrl.secuencia_terminada.connect(self._terminada)
        self.ctrl.fuente_cambiada.connect(self._fuente_cambiada)
        self.ctrl.pose_enviada.connect(self._pose_enviada)

        self.refrescar_biblioteca()
        self.cargar(secuencias_ejemplo()[0], None)

    # ------------------------------------------------------------------
    # Biblioteca y archivos
    # ------------------------------------------------------------------
    def refrescar_biblioteca(self):
        self.lista.clear()
        for sec in secuencias_ejemplo():
            item = QListWidgetItem(f"★ {sec.nombre}")
            item.setData(Qt.UserRole, ("ejemplo", sec.nombre))
            item.setToolTip("Secuencia de ejemplo (doble clic para abrir)")
            self.lista.addItem(item)
        for ruta in listar_secuencias_guardadas():
            item = QListWidgetItem(os.path.splitext(os.path.basename(ruta))[0])
            item.setData(Qt.UserRole, ("archivo", ruta))
            item.setToolTip(ruta)
            self.lista.addItem(item)

    def _abrir_desde_lista(self, item):
        if not self._confirmar_descartar():
            return
        tipo, valor = item.data(Qt.UserRole)
        if tipo == "ejemplo":
            sec = next(s for s in secuencias_ejemplo() if s.nombre == valor)
            self.cargar(sec, None)
        else:
            self._cargar_ruta(valor)

    def _abrir_archivo(self):
        if not self._confirmar_descartar():
            return
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir secuencia", DIRECTORIO_SECUENCIAS, "Secuencias (*.json)")
        if ruta:
            self._cargar_ruta(ruta)

    def _cargar_ruta(self, ruta):
        try:
            self.cargar(Secuencia.cargar(ruta), ruta)
        except (OSError, ValueError, TypeError, KeyError) as err:
            QMessageBox.warning(self, "No se pudo abrir", f"{ruta}\n\n{err}")

    def nueva(self):
        if not self._confirmar_descartar():
            return
        self.cargar(Secuencia("Nueva secuencia", [Paso(GESTOS["ABIERTA"], 600, 400, "Inicio")]), None)

    def guardar(self):
        if self.ruta is None:
            return self.guardar_como()
        try:
            self.secuencia.guardar(self.ruta)
        except OSError as err:
            QMessageBox.warning(self, "No se pudo guardar", str(err))
            return False
        self._marcar(False)
        self.refrescar_biblioteca()
        return True

    def guardar_como(self):
        os.makedirs(DIRECTORIO_SECUENCIAS, exist_ok=True)
        nombre = re.sub(r"[^\w\- ]", "", self.secuencia.nombre).strip() or "secuencia"
        sugerida = os.path.join(DIRECTORIO_SECUENCIAS, nombre.replace(" ", "_") + ".json")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar secuencia", sugerida, "Secuencias (*.json)")
        if not ruta:
            return False
        if not ruta.endswith(".json"):
            ruta += ".json"
        self.ruta = ruta
        return self.guardar()

    def _eliminar_archivo(self):
        item = self.lista.currentItem()
        if item is None:
            return
        tipo, valor = item.data(Qt.UserRole)
        if tipo != "archivo":
            QMessageBox.information(self, "Eliminar", "Las secuencias de ejemplo no se pueden borrar.")
            return
        if QMessageBox.question(self, "Eliminar", f"¿Borrar el archivo?\n{valor}") != QMessageBox.Yes:
            return
        try:
            os.remove(valor)
        except OSError as err:
            QMessageBox.warning(self, "No se pudo borrar", str(err))
        if self.ruta == valor:
            self.ruta = None
            self._marcar(True)
        self.refrescar_biblioteca()

    def _confirmar_descartar(self):
        if not self.modificada:
            return True
        r = QMessageBox.question(self, "Cambios sin guardar",
                                 f"«{self.secuencia.nombre}» tiene cambios sin guardar. ¿Guardarlos?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return bool(self.guardar())
        return r == QMessageBox.Discard

    # ------------------------------------------------------------------
    # Tabla <-> modelo
    # ------------------------------------------------------------------
    def cargar(self, secuencia, ruta):
        self.detener()
        self.secuencia = copy.deepcopy(secuencia)
        self.ruta = ruta
        self.edit_nombre.setText(self.secuencia.nombre)
        self.chk_bucle.blockSignals(True)
        self.chk_bucle.setChecked(self.secuencia.bucle)
        self.chk_bucle.blockSignals(False)
        self._rellenar_tabla()
        self._marcar(False)
        if self.secuencia.pasos:
            self.tabla.selectRow(0)

    def _rellenar_tabla(self):
        self._actualizando = True
        self.tabla.setRowCount(len(self.secuencia.pasos))
        for fila, paso in enumerate(self.secuencia.pasos):
            self._escribir_fila(fila, paso)
        self._actualizando = False
        self._actualizar_duracion()

    def _escribir_fila(self, fila, paso):
        valores = [paso.nombre or f"Paso {fila + 1}", *[str(v) for v in paso.dedos],
                   str(paso.transicion_ms), str(paso.pausa_ms), NOMBRES_CURVA[paso.curva]]
        for col, texto in enumerate(valores):
            item = QTableWidgetItem(texto)
            if col != COL_NOMBRE:
                item.setTextAlignment(Qt.AlignCenter)
            if col == COL_CURVA:
                item.setData(Qt.UserRole, paso.curva)
            self.tabla.setItem(fila, col, item)

    def _leer_fila(self, fila):
        def entero(col, defecto=0):
            numeros = re.findall(r"\d+", self.tabla.item(fila, col).text())
            return int(numeros[0]) if numeros else defecto
        curva = self.tabla.item(fila, COL_CURVA).data(Qt.UserRole) or "suave"
        return Paso([entero(c) for c in COL_DEDOS], entero(COL_TRANSICION, 600), entero(COL_PAUSA, 400),
                    self.tabla.item(fila, COL_NOMBRE).text().strip(), curva)

    def _celda_editada(self, item):
        if self._actualizando:
            return
        fila = item.row()
        if fila >= len(self.secuencia.pasos):
            return
        paso = self._leer_fila(fila)
        self.secuencia.pasos[fila] = paso
        # Reescribir para normalizar valores fuera de rango
        self._actualizando = True
        self._escribir_fila(fila, paso)
        self._actualizando = False
        self._marcar(True)
        self._actualizar_duracion()
        self._seleccion()

    def _seleccion(self):
        fila = self._fila_actual()
        if fila is not None:
            self.esquema.fijar(self.secuencia.pasos[fila].dedos,
                               f"Paso {fila + 1}: {self.secuencia.pasos[fila].nombre}")

    def _fila_actual(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        fila = filas[0].row()
        return fila if fila < len(self.secuencia.pasos) else None

    def _insertar(self, paso):
        fila = self._fila_actual()
        posicion = len(self.secuencia.pasos) if fila is None else fila + 1
        self.secuencia.pasos.insert(posicion, paso)
        self._rellenar_tabla()
        self.tabla.selectRow(posicion)
        self._marcar(True)

    def _agregar_camara(self):
        if time.monotonic() - self.ctrl.t_camara > 1.0:
            QMessageBox.information(self, "Sin mano", "Inicia la cámara en la pestaña Cámara y pon la mano delante.")
            return
        self._insertar(Paso(self.ctrl.pose_camara, 600, 400, "Cámara"))

    def _agregar_manual(self):
        self._insertar(Paso(self.ctrl.pose_manual, 600, 400, "Manual"))

    def _agregar_gesto(self):
        nombre = list(GESTOS)[self.combo_gesto.currentIndex()]
        self._insertar(Paso(GESTOS[nombre], 600, 400, nombre.capitalize()))

    def _duplicar(self):
        fila = self._fila_actual()
        if fila is not None:
            self._insertar(copy.deepcopy(self.secuencia.pasos[fila]))

    def _mover(self, delta):
        fila = self._fila_actual()
        if fila is None:
            return
        destino = fila + delta
        if not 0 <= destino < len(self.secuencia.pasos):
            return
        pasos = self.secuencia.pasos
        pasos[fila], pasos[destino] = pasos[destino], pasos[fila]
        self._rellenar_tabla()
        self.tabla.selectRow(destino)
        self._marcar(True)

    def _eliminar_paso(self):
        fila = self._fila_actual()
        if fila is None:
            return
        del self.secuencia.pasos[fila]
        self._rellenar_tabla()
        if self.secuencia.pasos:
            self.tabla.selectRow(min(fila, len(self.secuencia.pasos) - 1))
        self._marcar(True)

    def _nombre_editado(self, texto):
        self.secuencia.nombre = texto.strip() or "Sin nombre"
        self._marcar(True)

    def _bucle(self, activo):
        self.secuencia.bucle = activo
        self._marcar(True)

    def _marcar(self, modificada):
        self.modificada = modificada
        destino = os.path.basename(self.ruta) if self.ruta else "sin guardar"
        self.lbl_duracion.setToolTip(destino + (" · modificada" if modificada else ""))
        self._actualizar_duracion()

    def _actualizar_duracion(self):
        n = len(self.secuencia.pasos)
        marca = " ●" if self.modificada else ""
        self.lbl_duracion.setText(f"{n} pasos · {self.secuencia.duracion_ms / 1000:.1f} s{marca}")

    # ------------------------------------------------------------------
    # Reproducción
    # ------------------------------------------------------------------
    def reproducir(self):
        if not self.secuencia.pasos:
            QMessageBox.information(self, "Secuencia vacía", "Añade al menos un paso.")
            return
        self.ctrl.reproductor.cambiar_velocidad(self.spin_velocidad.value())
        self.ctrl.reproducir(copy.deepcopy(self.secuencia))
        self.btn_pausa.setChecked(False)
        self.btn_pausa.setText("⏸ Pausa")
        self.lbl_paso.setText("Reproduciendo…")

    def _pausa(self, pausada):
        if not self.ctrl.reproductor.activo:
            self.btn_pausa.setChecked(False)
            return
        if pausada:
            self.ctrl.reproductor.pausar()
            self.btn_pausa.setText("▶ Seguir")
        else:
            self.ctrl.reproductor.reanudar()
            self.btn_pausa.setText("⏸ Pausa")

    def detener(self):
        if self.ctrl.fuente == FUENTE_SECUENCIA:
            self.ctrl.reproductor.detener()
            self.ctrl.parada()
        self.barra.setValue(0)
        self.lbl_paso.setText("Detenido")
        self.btn_pausa.setChecked(False)
        self.btn_pausa.setText("⏸ Pausa")

    def _probar_paso(self):
        fila = self._fila_actual()
        if fila is None:
            return
        paso = self.secuencia.pasos[fila]
        self.ctrl.reproducir(Secuencia("Prueba", [Paso(paso.dedos, 500, 800, paso.nombre)]))

    def _progreso(self, indice, progreso):
        self.barra.setValue(int(progreso * 1000))
        sec = self.ctrl.reproductor.secuencia
        if sec is not None and 0 <= indice < len(sec.pasos):
            self.lbl_paso.setText(f"Paso {indice + 1}/{len(sec.pasos)}: {sec.pasos[indice].nombre}")

    def _terminada(self):
        self.barra.setValue(1000)
        self.lbl_paso.setText("Terminada")

    def _fuente_cambiada(self, fuente):
        if fuente != FUENTE_SECUENCIA:
            self.btn_pausa.setChecked(False)
            self.btn_pausa.setText("⏸ Pausa")

    def _pose_enviada(self, pose):
        if self.ctrl.fuente == FUENTE_SECUENCIA:
            self.esquema.fijar(pose, "Reproduciendo")

    def cerrar(self):
        return self._confirmar_descartar()
