"""
HandProyect - Aplicación de escritorio de la mano biónica (ESP32-S3).

Uso:
    python mano_app.py                    # abre la aplicación
    python mano_app.py --usb              # y conecta por USB (puerto automático)
    python mano_app.py --usb COM9
    python mano_app.py --wifi 192.168.4.1
    python mano_app.py --simulacion       # sin hardware
    python mano_app.py --autoprueba       # comprueba que todo carga y sale (para el .exe)
"""
import argparse
import os
import sys
import traceback


def autoprueba():
    """Carga MediaPipe, procesa una imagen y abre/cierra la ventana.

    Escribe el resultado en autoprueba.log junto al programa y devuelve 0 si todo va bien.
    Sirve para comprobar que el .exe incluye todo lo necesario.
    """
    from mano.rutas import DIRECTORIO_DATOS
    ruta_log = os.path.join(DIRECTORIO_DATOS, "autoprueba.log")
    lineas = []

    def registrar(texto):
        lineas.append(texto)
        print(texto, flush=True)

    codigo = 1
    try:
        import numpy as np
        from mano.vision import RUTA_MODELO, DetectorMano

        registrar(f"Modelo: {RUTA_MODELO} (existe: {os.path.exists(RUTA_MODELO)})")
        detector = DetectorMano()
        resultado = detector.procesar(np.zeros((240, 320, 3), dtype=np.uint8))
        detector.cerrar()
        registrar(f"MediaPipe OK (mano detectada en imagen negra: {resultado.detectada})")

        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from mano.gui.app import VentanaPrincipal
        from mano.gui.estilo import HOJA_ESTILO

        app = QApplication.instance() or QApplication([sys.argv[0]])
        app.setStyleSheet(HOJA_ESTILO)
        ventana = VentanaPrincipal(("Simulación", None))
        ventana.show()
        QTimer.singleShot(1500, ventana.close)
        QTimer.singleShot(2500, app.quit)
        app.exec()
        registrar("Interfaz OK")
        codigo = 0
    except Exception:                                   # noqa: BLE001 - se registra todo
        registrar("ERROR:\n" + traceback.format_exc())
    registrar("AUTOPRUEBA " + ("SUPERADA" if codigo == 0 else "FALLIDA"))
    try:
        with open(ruta_log, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    except OSError:
        pass
    return codigo


def main():
    p = argparse.ArgumentParser(description="Aplicación de escritorio de la mano biónica")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--usb", nargs="?", const="", metavar="PUERTO",
                       help="Conectar por USB al arrancar (puerto opcional)")
    grupo.add_argument("--wifi", metavar="IP", help="Conectar por WiFi a esta IP al arrancar")
    grupo.add_argument("--simulacion", action="store_true", help="Conectar en modo simulación")
    grupo.add_argument("--autoprueba", action="store_true", help=argparse.SUPPRESS)
    args, resto = p.parse_known_args()

    if args.autoprueba:
        return autoprueba()

    from mano.gui.app import ejecutar

    conexion = None
    if args.usb is not None:
        conexion = ("USB", args.usb or None)
    elif args.wifi:
        conexion = ("WiFi", args.wifi)
    elif args.simulacion:
        conexion = ("Simulación", None)
    return ejecutar([sys.argv[0], *resto], conexion)


if __name__ == "__main__":
    sys.exit(main())
