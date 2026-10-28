"""
HandProyect - Aplicación de escritorio de la mano biónica (ESP32-S3).

Uso:
    python mano_app.py                    # abre la aplicación
    python mano_app.py --usb              # y conecta por USB (puerto automático)
    python mano_app.py --usb /dev/ttyACM0
    python mano_app.py --wifi 192.168.4.1
    python mano_app.py --simulacion       # sin hardware
"""
import argparse
import sys

from mano.gui.app import ejecutar


def main():
    p = argparse.ArgumentParser(description="Aplicación de escritorio de la mano biónica")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--usb", nargs="?", const="", metavar="PUERTO",
                       help="Conectar por USB al arrancar (puerto opcional)")
    grupo.add_argument("--wifi", metavar="IP", help="Conectar por WiFi a esta IP al arrancar")
    grupo.add_argument("--simulacion", action="store_true", help="Conectar en modo simulación")
    args, resto = p.parse_known_args()

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
