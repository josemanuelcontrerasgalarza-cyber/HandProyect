"""
Rutas del proyecto, válidas tanto ejecutando desde el código fuente como desde
el .exe generado con PyInstaller.

  DIRECTORIO_RECURSOS -> archivos incluidos en el programa (modelo de MediaPipe).
                         En el .exe es la carpeta interna de PyInstaller.
  DIRECTORIO_DATOS    -> archivos que el usuario crea (calibración, secuencias).
                         En el .exe es la carpeta donde está ManoBionica.exe.
"""
import os
import sys

EMPAQUETADO = bool(getattr(sys, "frozen", False))

if EMPAQUETADO:
    DIRECTORIO_RECURSOS = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    DIRECTORIO_DATOS = os.path.dirname(os.path.abspath(sys.executable))
else:
    DIRECTORIO_RECURSOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DIRECTORIO_DATOS = DIRECTORIO_RECURSOS
