"""
Simulador de la ESP32-S3 por UDP: responde al mismo protocolo que el firmware
(tramas P:, comandos, STATUS, calibración...) para probar la aplicación sin hardware.

Uso:
    python tools/simulador_esp32.py               # escucha en 127.0.0.1:4210
    python mano_app.py --wifi 127.0.0.1           # en otra terminal
"""
import argparse
import socket
import time

NOMBRES = ["PULGAR", "INDICE", "MEDIO", "ANULAR", "MENIQUE"]
CANALES = [0, 2, 4, 6, 8]
DEF_ABIERTO = [520, 130, 130, 130, 130]
DEF_CERRADO = [130, 520, 520, 520, 520]
GESTOS = {
    "ABIERTA": [100] * 5, "PUNO": [0] * 5, "PAZ": [0, 100, 100, 0, 0], "ROCK": [100, 100, 0, 0, 100],
    "OK": [20, 20, 100, 100, 100], "APUNTAR": [0, 100, 0, 0, 0], "PULGAR": [100, 0, 0, 0, 0],
    "PISTOLA": [100, 100, 0, 0, 0], "TELEFONO": [100, 0, 0, 0, 100], "PINZA": [35, 35, 100, 100, 100],
    "RELAJADA": [70, 60, 55, 50, 50],
}
TIMEOUT_S = 1.5


class ManoSimulada:
    def __init__(self):
        self.abierto = list(DEF_ABIERTO)
        self.cerrado = list(DEF_CERRADO)
        self.guardado = (list(self.abierto), list(self.cerrado), 60)
        self.actual = [1.0] * 5
        self.objetivo = [1.0] * 5
        self.velocidad = 60
        self.modo = "MANUAL"
        self.fuente = "NINGUNA"
        self.ultima_trama = 0.0
        self.trama_recibida = False
        self.t_prev = time.monotonic()

    # --- Cinemática (misma idea que el firmware) ---
    def paso(self):
        ahora = time.monotonic()
        dt = ahora - self.t_prev
        self.t_prev = ahora
        if (self.modo == "STREAMING" and self.trama_recibida and
                time.monotonic() - self.ultima_trama > TIMEOUT_S):
            self.modo = "FAILSAFE"
            self.objetivo = [1.0] * 5
            print("[FAILSAFE] Sin datos (>1.5s). Mano en reposo (abierta).")
        if self.modo == "RELAJADO":
            return
        recorrido_s = 0.6 if self.modo == "FAILSAFE" else 0.5 + self.velocidad / 100 * 7.5
        paso_max = recorrido_s * dt
        for i in range(5):
            error = self.objetivo[i] - self.actual[i]
            self.actual[i] += max(-paso_max, min(paso_max, error * min(1.0, 35 * dt)))

    # --- Protocolo ---
    def procesar(self, linea, fuente):
        linea = linea.strip()
        if not linea:
            return []
        if "," in linea:
            return self._trama(linea, fuente)
        partes = linea.split()
        cmd = partes[0].upper()
        args = partes[1:]

        def entero(n, defecto=-1):
            try:
                return int(args[n])
            except (IndexError, ValueError):
                return defecto

        if cmd in ("HELP", "?"):
            return ["TRAMAS:   P:a,b,c,d,e (0-100 % abierto) | a,b,c,d,e (binario 1/0)",
                    "COMANDOS: HELP, STATUS, PING, OPEN, CLOSE, DEMO, STOP, RELAX",
                    "          GESTO <nombre>, GESTOS, SET <dedo> <0-100>, SPEED <1-100>",
                    "CALIBRAR: PULSO <dedo> <ticks>, CAL <dedo> <abierto> <cerrado>, INV <dedo>",
                    "          SAVE, LOAD, DEFAULTS   (simulador)"]
        if cmd == "STATUS":
            salida = ["", "--- MANO BIONICA ESP32-S3 ---",
                      f"Modo: {self.modo} | Fuente: {self.fuente} | Velocidad: {self.velocidad}%",
                      "PCA9685: SIMULADO | WiFi: 127.0.0.1"]
            for i in range(5):
                salida.append(f"[{i}] {NOMBRES[i]:<8} CH{CANALES[i]:<2} abierto={self.abierto[i]:3d} "
                              f"cerrado={self.cerrado[i]:3d}  actual={int(self.actual[i] * 100):3d}% "
                              f"objetivo={int(self.objetivo[i] * 100):3d}%")
            salida.append("-----------------------------")
            return salida
        if cmd == "PING":
            return ["PONG MANO-ESP32S3 (simulador)"]
        if cmd in ("OPEN", "ABRIR", "CLOSE", "CERRAR"):
            self._modo("MANUAL")
            valor = 1.0 if cmd in ("OPEN", "ABRIR") else 0.0
            self.objetivo = [valor] * 5
            return ["[ACCION] Mano abierta." if valor else "[ACCION] Mano cerrada."]
        if cmd in ("DEMO", "SWEEP"):
            self._modo("DEMO")
            return ["[MODO] Demo iniciada (STOP para salir)."]
        if cmd in ("STOP", "STREAM"):
            self._modo("MANUAL")
            self.trama_recibida = False
            return ["[MODO] Manual. Las tramas de Python activan el streaming."]
        if cmd == "RELAX":
            self._modo("RELAJADO")
            return ["[ACCION] Servos relajados (sin fuerza)."]
        if cmd == "GESTOS":
            return ["Gestos: " + " ".join(GESTOS)]
        if cmd == "GESTO":
            nombre = args[0].upper() if args else ""
            if nombre not in GESTOS:
                return ["[ERROR] Gesto desconocido (ver GESTOS)."]
            self._modo("MANUAL")
            self.objetivo = [v / 100 for v in GESTOS[nombre]]
            return [f"[GESTO] {nombre}"]
        if cmd == "SET":
            d, v = entero(0), entero(1)
            if not 0 <= d < 5 or v < 0:
                return ["[ERROR] SET <dedo> <0-100>"]
            self._modo("MANUAL")
            self.objetivo[d] = min(100, v) / 100
            return [f"[SET] {NOMBRES[d]} = {min(100, v)}%"]
        if cmd == "SPEED":
            v = entero(0)
            if not 1 <= v <= 100:
                return ["[ERROR] SPEED <1-100>"]
            self.velocidad = v
            return [f"[VELOCIDAD] {v}%"]
        if cmd == "PULSO":
            d, v = entero(0), entero(1)
            if not 0 <= d < 5 or not 100 <= v <= 600:
                return ["[ERROR] PULSO <dedo> <100-600>"]
            self._modo("RELAJADO")
            return [f"[CALIB] {NOMBRES[d]} -> {v} ticks (usa CAL para guardar los extremos)"]
        if cmd == "CAL":
            d, a, c = entero(0), entero(1), entero(2)
            if not 0 <= d < 5 or not 100 <= a <= 600 or not 100 <= c <= 600:
                return ["[ERROR] CAL <dedo> <abierto> <cerrado>  (100-600)"]
            self.abierto[d], self.cerrado[d] = a, c
            return [f"[CALIB] {NOMBRES[d]} abierto={a} cerrado={c} (SAVE para guardar)"]
        if cmd == "INV":
            d = entero(0)
            if not 0 <= d < 5:
                return ["[ERROR] INV <dedo>"]
            self.abierto[d], self.cerrado[d] = self.cerrado[d], self.abierto[d]
            return [f"[CALIB] {NOMBRES[d]} invertido (SAVE para guardar)"]
        if cmd == "SAVE":
            self.guardado = (list(self.abierto), list(self.cerrado), self.velocidad)
            return ["[SISTEMA] Calibración guardada en flash."]
        if cmd == "LOAD":
            self.abierto, self.cerrado = list(self.guardado[0]), list(self.guardado[1])
            self.velocidad = self.guardado[2]
            return ["[SISTEMA] Calibración cargada."]
        if cmd == "DEFAULTS":
            self.abierto, self.cerrado, self.velocidad = list(DEF_ABIERTO), list(DEF_CERRADO), 60
            return ["[SISTEMA] Valores por defecto (SAVE para guardar)."]
        return [f"[ERROR] Comando desconocido: '{partes[0]}' (HELP)"]

    def _modo(self, modo):
        if self.modo == "RELAJADO" and modo != "RELAJADO":
            self.actual = list(self.objetivo)
        self.modo = modo

    def _trama(self, linea, fuente):
        proporcional = linea[:2].upper() == "P:"
        cuerpo = linea[2:] if proporcional else linea
        try:
            valores = [int(v) for v in cuerpo.split(",")]
        except ValueError:
            return ["[ERROR] Trama inválida."]
        if len(valores) != 5:
            return ["[ERROR] Trama inválida."]
        self.ultima_trama = time.monotonic()
        self.trama_recibida = True
        self.fuente = fuente
        if self.modo != "STREAMING":
            self._modo("STREAMING")
        self.objetivo = [max(0, min(100, v if proporcional else (100 if v else 0))) / 100 for v in valores]
        return []


def main():
    p = argparse.ArgumentParser(description="Simulador UDP de la ESP32-S3 de la mano biónica")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=4210)
    p.add_argument("--silencioso", action="store_true", help="No mostrar las tramas recibidas")
    args = p.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.puerto))
    sock.settimeout(0.01)
    mano = ManoSimulada()
    print(f"[SIMULADOR] Escuchando en {args.host}:{args.puerto}. Ctrl+C para salir.")
    ultimo_print = 0.0
    try:
        while True:
            try:
                datos, origen = sock.recvfrom(2048)
            except socket.timeout:
                datos = None
            if datos:
                respuesta = []
                for linea in datos.decode("utf-8", "replace").splitlines():
                    respuesta += mano.procesar(linea, "WIFI-UDP")
                if respuesta:
                    sock.sendto(("\n".join(respuesta) + "\n").encode("utf-8"), origen)
            mano.paso()
            if not args.silencioso and time.monotonic() - ultimo_print > 0.5:
                ultimo_print = time.monotonic()
                barras = " ".join(f"{n[:3]} {int(v * 100):3d}%" for n, v in zip(NOMBRES, mano.actual))
                print(f"\r[{mano.modo:<9}] {barras}", end="", flush=True)
    except KeyboardInterrupt:
        print("\n[SIMULADOR] Cerrado.")


if __name__ == "__main__":
    main()
