"""Pestañas de la ventana principal."""
from PySide6.QtWidgets import QPushButton


def boton(texto, rol=None, al_pulsar=None, tooltip=None, marcable=False):
    """Crea un QPushButton con rol de estilo opcional."""
    b = QPushButton(texto)
    if rol:
        b.setProperty("rol", rol)
    if tooltip:
        b.setToolTip(tooltip)
    if marcable:
        b.setCheckable(True)
    if al_pulsar is not None:
        b.clicked.connect(al_pulsar)
    return b
