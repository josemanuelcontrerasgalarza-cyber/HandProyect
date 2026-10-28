"""Widgets propios: esquema de la mano, barras de dedos, gráfica en tiempo real y LED."""
import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..vision import DEDOS_NOMBRES_BONITOS

COLORES_DEDOS = [QColor("#ff6b6b"), QColor("#ffb020"), QColor("#00e0b0"),
                 QColor("#4dabf7"), QColor("#c77dff")]
COLOR_FONDO = QColor("#141722")
COLOR_REJILLA = QColor("#262b3b")
COLOR_TEXTO = QColor("#9aa0b4")
COLOR_ACENTO = QColor("#00e0b0")


def _limitar(v, a, b):
    return max(a, min(b, v))


class EsquemaMano(QWidget):
    """Dibujo frontal de la mano robótica según el % de apertura de cada dedo.

    Al cerrarse, cada dedo se acorta (se dobla hacia la palma) y muestra la
    falange doblada encima del nudillo; el pulgar gira hacia el centro.
    """

    LARGOS = [0.55, 0.80, 0.88, 0.82, 0.64]       # relativos a la escala
    ANCHOS = [0.20, 0.17, 0.18, 0.17, 0.15]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.porcentajes = [100.0] * 5
        self.titulo = ""
        self.resaltado = -1
        self.setMinimumSize(180, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(260, 320)

    def fijar(self, porcentajes, titulo=None):
        self.porcentajes = [_limitar(float(p), 0, 100) for p in porcentajes]
        if titulo is not None:
            self.titulo = titulo
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), COLOR_FONDO)

        w, h = self.width(), self.height()
        margen_sup = 30 if self.titulo else 10
        escala = min(w / 1.45, (h - margen_sup - 10) / 1.75)
        alto_palma = escala * 0.66
        ancho_palma = escala * 0.80
        cx = w / 2 + escala * 0.08
        # La mano completa (dedos + palma + muñeca) ocupa ~1.75 escalas: centrarla
        top = margen_sup + ((h - margen_sup - 10) - escala * 1.75) / 2
        palma = QRectF(cx - ancho_palma / 2, top + escala * 0.92, ancho_palma, alto_palma)

        # Muñeca y palma
        p.setPen(QPen(QColor("#3a4157"), 2))
        p.setBrush(QColor("#232838"))
        p.drawRoundedRect(QRectF(cx - ancho_palma * 0.32, palma.bottom() - 6, ancho_palma * 0.64,
                                 escala * 0.17 + 6), 6, 6)
        p.setBrush(QColor("#2b3144"))
        p.drawRoundedRect(palma, escala * 0.10, escala * 0.10)

        # Cuatro dedos (índice..meñique) desde el borde superior de la palma
        for idx in range(1, 5):
            frac = (idx - 0.5) / 4
            x = palma.left() + palma.width() * (0.07 + 0.86 * frac)
            self._dedo_vertical(p, idx, x, palma.top() + escala * 0.04, escala)

        # Pulgar desde el lateral izquierdo de la palma
        self._pulgar(p, QPointF(palma.left() + escala * 0.06, palma.top() + alto_palma * 0.62), escala)

        if self.titulo:
            p.setPen(COLOR_TEXTO)
            f = QFont(self.font())
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(0, 6, w, 22), Qt.AlignHCenter | Qt.AlignTop, self.titulo)
        p.end()

    def _colores(self, idx):
        apertura = self.porcentajes[idx] / 100.0
        borde = QColor("#ffffff") if idx == self.resaltado else COLORES_DEDOS[idx]
        relleno = QColor(COLORES_DEDOS[idx])
        relleno.setAlpha(120 + int(110 * apertura))
        return borde, relleno, 2.4 if idx == self.resaltado else 1.4

    def _dedo_vertical(self, p, idx, x, base_y, escala):
        apertura = self.porcentajes[idx] / 100.0
        ancho = escala * self.ANCHOS[idx]
        largo_total = escala * self.LARGOS[idx]
        visible = largo_total * (0.22 + 0.78 * apertura)     # se acorta al doblarse
        borde, relleno, grosor = self._colores(idx)

        cuerpo = QRectF(x - ancho / 2, base_y - visible, ancho, visible + ancho * 0.3)
        p.setPen(QPen(borde, grosor))
        p.setBrush(relleno)
        p.drawRoundedRect(cuerpo, ancho / 2, ancho / 2)

        # Líneas de las articulaciones (DIP y PIP) repartidas en la parte visible
        p.setPen(QPen(QColor(17, 19, 27, 170), max(1.0, ancho * 0.08)))
        for frac in (0.36, 0.66):
            y = base_y - visible * (1 - frac) + ancho * 0.1
            if y > base_y - visible + ancho * 0.45:
                p.drawLine(QPointF(x - ancho * 0.32, y), QPointF(x + ancho * 0.32, y))

        # Falange doblada: aparece sobre el nudillo cuando el dedo se cierra
        cierre = 1.0 - apertura
        if cierre > 0.25:
            largo_doblada = largo_total * 0.32 * min(1.0, (cierre - 0.25) / 0.6)
            sombra = QColor(COLORES_DEDOS[idx]).darker(170)
            p.setPen(QPen(borde, 1.0))
            p.setBrush(sombra)
            p.drawRoundedRect(QRectF(x - ancho * 0.42, base_y - visible + ancho * 0.15,
                                     ancho * 0.84, max(ancho * 0.5, largo_doblada)), ancho * 0.4, ancho * 0.4)

        # Punta
        p.setPen(Qt.NoPen)
        p.setBrush(COLORES_DEDOS[idx])
        p.drawEllipse(QPointF(x, base_y - visible + ancho * 0.45), ancho * 0.16, ancho * 0.16)

    def _pulgar(self, p, origen, escala):
        apertura = self.porcentajes[0] / 100.0
        ancho = escala * self.ANCHOS[0]
        largo = escala * self.LARGOS[0] * (0.55 + 0.45 * apertura)
        angulo = -150.0 + (1 - apertura) * 115.0          # abierto: hacia fuera; cerrado: cruza la palma
        borde, relleno, grosor = self._colores(0)
        p.save()
        p.translate(origen)
        p.rotate(angulo)
        p.setPen(QPen(borde, grosor))
        p.setBrush(relleno)
        p.drawRoundedRect(QRectF(-ancho * 0.3, -ancho / 2, largo + ancho * 0.3, ancho), ancho / 2, ancho / 2)
        p.setPen(QPen(QColor(17, 19, 27, 170), max(1.0, ancho * 0.08)))
        p.drawLine(QPointF(largo * 0.55, -ancho * 0.32), QPointF(largo * 0.55, ancho * 0.32))
        p.setPen(Qt.NoPen)
        p.setBrush(COLORES_DEDOS[0])
        p.drawEllipse(QPointF(largo - ancho * 0.25, 0), ancho * 0.16, ancho * 0.16)
        p.restore()


class BarrasDedos(QWidget):
    """Cinco barras horizontales con el % de apertura y el estado binario."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.porcentajes = [100.0] * 5
        self.estados = [1] * 5
        self.setMinimumHeight(5 * 26 + 8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def fijar(self, porcentajes, estados=None):
        self.porcentajes = [_limitar(float(v), 0, 100) for v in porcentajes]
        self.estados = list(estados) if estados is not None else [1 if v >= 50 else 0
                                                                  for v in self.porcentajes]
        self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        fm = p.fontMetrics()
        ancho_nombre = fm.horizontalAdvance("Meñique") + 10
        ancho_valor = fm.horizontalAdvance("100% ABR") + 10
        ancho_barra = max(20, w - ancho_nombre - ancho_valor - 8)
        for i in range(5):
            y = 4 + i * 26
            p.setPen(QColor("#e6e8ef"))
            p.drawText(QRectF(0, y, ancho_nombre, 18), Qt.AlignVCenter | Qt.AlignLeft,
                       DEDOS_NOMBRES_BONITOS[i])
            fondo = QRectF(ancho_nombre, y + 3, ancho_barra, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_REJILLA)
            p.drawRoundedRect(fondo, 6, 6)
            relleno = QRectF(fondo.left(), fondo.top(), ancho_barra * self.porcentajes[i] / 100, 12)
            p.setBrush(COLORES_DEDOS[i])
            p.drawRoundedRect(relleno, 6, 6)
            p.setPen(COLOR_ACENTO if self.estados[i] else QColor("#ff6b6b"))
            texto = f"{int(self.porcentajes[i])}% {'ABR' if self.estados[i] else 'CER'}"
            p.drawText(QRectF(ancho_nombre + ancho_barra + 8, y, ancho_valor, 18),
                       Qt.AlignVCenter | Qt.AlignLeft, texto)
        p.end()


class GraficaTiempoReal(QWidget):
    """Gráfica de 5 series (0-100) con ventana temporal deslizante."""

    def __init__(self, titulo="", ventana_s=10.0, parent=None):
        super().__init__(parent)
        self.titulo = titulo
        self.ventana_s = ventana_s
        self.datos = deque(maxlen=6000)        # (t, [5 valores])
        self.visibles = [True] * 5
        self.pausada = False
        self._t_congelado = None
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def agregar(self, valores, t=None):
        self.datos.append((t if t is not None else time.monotonic(), list(valores)))
        if not self.pausada:
            self.update()

    def limpiar(self):
        self.datos.clear()
        self.update()

    def fijar_pausa(self, pausada):
        self.pausada = pausada
        self._t_congelado = time.monotonic() if pausada else None
        self.update()

    def fijar_visible(self, indice, visible):
        self.visibles[indice] = visible
        self.update()

    def a_csv(self):
        lineas = ["t_s," + ",".join(DEDOS_NOMBRES_BONITOS)]
        if self.datos:
            t0 = self.datos[0][0]
            for t, v in self.datos:
                lineas.append(f"{t - t0:.3f}," + ",".join(f"{x:.1f}" for x in v))
        return "\n".join(lineas) + "\n"

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), COLOR_FONDO)
        izq, der, arr, aba = 40, 12, 26, 22
        area = QRectF(izq, arr, self.width() - izq - der, self.height() - arr - aba)

        p.setPen(COLOR_TEXTO)
        p.drawText(QRectF(izq, 4, area.width(), 18), Qt.AlignLeft | Qt.AlignVCenter, self.titulo)

        # Rejilla
        p.setPen(QPen(COLOR_REJILLA, 1))
        for pct in range(0, 101, 25):
            y = area.bottom() - area.height() * pct / 100
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(COLOR_TEXTO)
            p.drawText(QRectF(0, y - 8, izq - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{pct}")
            p.setPen(QPen(COLOR_REJILLA, 1))
        pasos = int(self.ventana_s) if self.ventana_s <= 10 else int(self.ventana_s / 5)
        for k in range(pasos + 1):
            x = area.left() + area.width() * k / max(pasos, 1)
            p.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        p.setPen(COLOR_TEXTO)
        p.drawText(QRectF(area.left(), area.bottom() + 4, area.width(), 16),
                   Qt.AlignRight | Qt.AlignVCenter, f"últimos {self.ventana_s:g} s")

        ahora = self._t_congelado if self.pausada else time.monotonic()
        t_min = ahora - self.ventana_s
        puntos = [(t, v) for t, v in self.datos if t >= t_min]
        if len(puntos) >= 2:
            for i in range(5):
                if not self.visibles[i]:
                    continue
                camino = QPainterPath()
                for n, (t, v) in enumerate(puntos):
                    x = area.left() + area.width() * (t - t_min) / self.ventana_s
                    y = area.bottom() - area.height() * _limitar(v[i], 0, 100) / 100
                    if n == 0:
                        camino.moveTo(x, y)
                    else:
                        camino.lineTo(x, y)
                p.setPen(QPen(COLORES_DEDOS[i], 2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(camino)
        else:
            p.setPen(COLOR_TEXTO)
            p.drawText(area, Qt.AlignCenter, "Sin datos todavía")

        # Leyenda
        x = area.right()
        for i in reversed(range(5)):
            nombre = DEDOS_NOMBRES_BONITOS[i]
            ancho = p.fontMetrics().horizontalAdvance(nombre) + 22
            x -= ancho
            color = COLORES_DEDOS[i] if self.visibles[i] else COLOR_REJILLA
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, 9, 10, 10), 2, 2)
            p.setPen(COLOR_TEXTO if self.visibles[i] else COLOR_REJILLA)
            p.drawText(QRectF(x + 14, 4, ancho, 20), Qt.AlignLeft | Qt.AlignVCenter, nombre)
        p.end()


class LedEstado(QWidget):
    """Pequeño indicador redondo (verde / ámbar / rojo / gris)."""

    COLORES = {"ok": QColor("#2fd27a"), "aviso": QColor("#ffb020"),
               "error": QColor("#ff5c5c"), "apagado": QColor("#4a5066")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.estado = "apagado"
        self.setFixedSize(14, 14)

    def fijar(self, estado):
        if estado != self.estado:
            self.estado = estado
            self.update()

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = self.COLORES.get(self.estado, self.COLORES["apagado"])
        halo = QColor(color)
        halo.setAlpha(70)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(0, 0, 14, 14))
        p.setBrush(color)
        p.drawEllipse(QRectF(3, 3, 8, 8))
        p.end()


class VistaVideo(QWidget):
    """Muestra un QImage manteniendo la proporción, con texto si no hay imagen."""

    clic = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.imagen = None
        self.mensaje = "Cámara detenida"
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def fijar_imagen(self, imagen):
        self.imagen = imagen
        self.update()

    def fijar_mensaje(self, mensaje):
        self.imagen = None
        self.mensaje = mensaje
        self.update()

    def mousePressEvent(self, evento):
        self.clic.emit()
        super().mousePressEvent(evento)

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b0d14"))
        if self.imagen is not None and not self.imagen.isNull():
            tam = self.imagen.size().scaled(self.size(), Qt.KeepAspectRatio)
            x = (self.width() - tam.width()) / 2
            y = (self.height() - tam.height()) / 2
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRectF(x, y, tam.width(), tam.height()), self.imagen)
        else:
            p.setPen(COLOR_TEXTO)
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.mensaje)
        p.end()
