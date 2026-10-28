# -*- mode: python ; coding: utf-8 -*-
"""
Receta de PyInstaller para crear ManoBionica.exe (Windows) o ManoBionica (Linux).

    pyinstaller --noconfirm mano_app.spec

Resultado: dist/ManoBionica/ con el ejecutable y todo lo que necesita.
Antes de compilar hay que tener el modelo en models/hand_landmarker.task
(crear_exe.bat y el workflow de GitHub lo descargan solos).
"""
import os

from PyInstaller.utils.hooks import collect_all

RAIZ = os.path.abspath(SPECPATH)
MODELO = os.path.join(RAIZ, "models", "hand_landmarker.task")
if not os.path.exists(MODELO):
    raise SystemExit(f"Falta el modelo de MediaPipe: {MODELO}\n"
                     "Ejecuta: python -c \"from mano.vision import asegurar_modelo; asegurar_modelo()\"")

# MediaPipe carga su librería nativa (libmediapipe.dll / .so) con ctypes desde
# su propio paquete: hay que copiar el paquete completo con sus binarios.
mp_datos, mp_binarios, mp_ocultos = collect_all("mediapipe")

datos = mp_datos + [(MODELO, "models"), (os.path.join(RAIZ, "recursos"), "recursos")]

icono = os.path.join(RAIZ, "recursos", "mano.ico")

a = Analysis(
    [os.path.join(RAIZ, "mano_app.py")],
    pathex=[RAIZ],
    binaries=mp_binarios,
    datas=datos,
    hiddenimports=mp_ocultos + ["serial.tools.list_ports"],
    excludes=[
        # matplotlib NO se excluye: mediapipe lo importa al cargarse
        "tkinter", "IPython", "pytest", "scipy", "pandas",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ManoBionica",
    console=False,                      # aplicación de ventana, sin consola negra
    icon=icono if os.path.exists(icono) else None,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name="ManoBionica",
)
