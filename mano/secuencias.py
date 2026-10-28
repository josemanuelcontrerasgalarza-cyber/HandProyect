"""
Secuencias de movimiento: una lista de poses (5 dedos, 0-100 % abierto) con
tiempo de transición y pausa. Se guardan en JSON y se reproducen desde el PC
interpolando suavemente entre poses.
"""
import json
import os
import time
from dataclasses import asdict, dataclass, field

from .rutas import DIRECTORIO_DATOS

DIRECTORIO_SECUENCIAS = os.path.join(DIRECTORIO_DATOS, "secuencias")

# Mismos gestos que el firmware (% abierto: pulgar, índice, medio, anular, meñique)
GESTOS = {
    "ABIERTA":  [100, 100, 100, 100, 100],
    "PUNO":     [0, 0, 0, 0, 0],
    "PAZ":      [0, 100, 100, 0, 0],
    "ROCK":     [100, 100, 0, 0, 100],
    "OK":       [20, 20, 100, 100, 100],
    "APUNTAR":  [0, 100, 0, 0, 0],
    "PULGAR":   [100, 0, 0, 0, 0],
    "PISTOLA":  [100, 100, 0, 0, 0],
    "TELEFONO": [100, 0, 0, 0, 100],
    "PINZA":    [35, 35, 100, 100, 100],
    "RELAJADA": [70, 60, 55, 50, 50],
}

CURVAS = ("suave", "lineal", "instantanea")


def _limitar(v, minimo, maximo):
    return max(minimo, min(maximo, v))


@dataclass
class Paso:
    dedos: list
    transicion_ms: int = 600
    pausa_ms: int = 400
    nombre: str = ""
    curva: str = "suave"

    def __post_init__(self):
        if len(self.dedos) != 5:
            raise ValueError("Un paso necesita exactamente 5 valores")
        self.dedos = [int(_limitar(round(float(v)), 0, 100)) for v in self.dedos]
        self.transicion_ms = int(_limitar(int(self.transicion_ms), 0, 60000))
        self.pausa_ms = int(_limitar(int(self.pausa_ms), 0, 60000))
        if self.curva not in CURVAS:
            self.curva = "suave"

    @property
    def duracion_ms(self):
        return self.transicion_ms + self.pausa_ms


@dataclass
class Secuencia:
    nombre: str = "Nueva secuencia"
    pasos: list = field(default_factory=list)
    bucle: bool = False

    @property
    def duracion_ms(self):
        return sum(p.duracion_ms for p in self.pasos)

    def a_dict(self):
        return {"nombre": self.nombre, "bucle": self.bucle,
                "pasos": [asdict(p) for p in self.pasos]}

    @classmethod
    def desde_dict(cls, datos):
        pasos = [Paso(**{k: v for k, v in p.items() if k in Paso.__dataclass_fields__})
                 for p in datos.get("pasos", [])]
        return cls(nombre=str(datos.get("nombre", "Sin nombre")), pasos=pasos,
                   bucle=bool(datos.get("bucle", False)))

    def guardar(self, ruta):
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(self.a_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def cargar(cls, ruta):
        with open(ruta, encoding="utf-8") as f:
            return cls.desde_dict(json.load(f))


def secuencias_ejemplo():
    """Secuencias incluidas de serie."""
    g = GESTOS
    return [
        Secuencia("Saludo", [
            Paso(g["ABIERTA"], 500, 300, "Abrir"),
            Paso(g["PUNO"], 500, 200, "Cerrar"),
            Paso(g["ABIERTA"], 500, 300, "Abrir"),
            Paso(g["PUNO"], 500, 200, "Cerrar"),
            Paso(g["ABIERTA"], 500, 500, "Abrir"),
        ]),
        Secuencia("Contar 1-5", [
            Paso(g["PUNO"], 500, 400, "0"),
            Paso([0, 100, 0, 0, 0], 400, 600, "1"),
            Paso([0, 100, 100, 0, 0], 400, 600, "2"),
            Paso([0, 100, 100, 100, 0], 400, 600, "3"),
            Paso([0, 100, 100, 100, 100], 400, 600, "4"),
            Paso(g["ABIERTA"], 400, 800, "5"),
        ]),
        Secuencia("Ola", [Paso([0 if i == k else 100 for i in range(5)], 250, 50, f"Dedo {k}")
                          for k in range(5)] + [Paso(g["ABIERTA"], 250, 300, "Fin")], bucle=True),
        Secuencia("Piano", [Paso([100 if i != k else 30 for i in range(5)], 180, 80, f"Tecla {k}")
                            for k in (1, 3, 2, 4, 1, 2, 3, 4)], bucle=True),
        Secuencia("Agarre suave", [
            Paso(g["ABIERTA"], 800, 500, "Preparar"),
            Paso([60, 70, 70, 70, 70], 900, 300, "Aproximar"),
            Paso([30, 40, 40, 40, 40], 1200, 2000, "Sujetar"),
            Paso(g["ABIERTA"], 900, 500, "Soltar"),
        ]),
    ]


def curva(t, tipo):
    """Interpolación 0..1 según la curva elegida."""
    t = _limitar(t, 0.0, 1.0)
    if tipo == "lineal":
        return t
    if tipo == "instantanea":
        return 1.0
    return t * t * (3 - 2 * t)           # smoothstep


def pose_en(secuencia, t_ms, pose_inicial=None):
    """Pose interpolada en el instante t_ms y el índice del paso activo.

    Devuelve (dedos, indice) o (None, -1) si la secuencia ha terminado.
    """
    if not secuencia.pasos:
        return None, -1
    total = secuencia.duracion_ms
    if secuencia.bucle and total > 0:
        vueltas = int(t_ms // total)
        t_ms = t_ms % total
    else:
        vueltas = 0
        if t_ms >= total:
            return None, -1

    anterior = pose_inicial or secuencia.pasos[-1].dedos
    if vueltas > 0:
        anterior = secuencia.pasos[-1].dedos          # en bucle se parte del último paso
    for i, paso in enumerate(secuencia.pasos):
        if t_ms < paso.duracion_ms:
            if paso.transicion_ms > 0 and t_ms < paso.transicion_ms:
                k = curva(t_ms / paso.transicion_ms, paso.curva)
            else:
                k = 1.0
            dedos = [a + (b - a) * k for a, b in zip(anterior, paso.dedos)]
            return dedos, i
        t_ms -= paso.duracion_ms
        anterior = paso.dedos
    return None, -1


class Reproductor:
    """Reproduce una secuencia en tiempo real (pausa, reanudar, velocidad)."""

    def __init__(self):
        self.secuencia = None
        self.pose_inicial = None
        self.velocidad = 1.0
        self._t_acumulado = 0.0
        self._t_ref = None

    @property
    def activo(self):
        return self.secuencia is not None

    @property
    def pausado(self):
        return self.activo and self._t_ref is None

    def iniciar(self, secuencia, pose_inicial=None):
        self.secuencia = secuencia
        self.pose_inicial = list(pose_inicial) if pose_inicial else None
        self._t_acumulado = 0.0
        self._t_ref = time.monotonic()

    def detener(self):
        self.secuencia = None
        self._t_ref = None

    def pausar(self):
        if self.activo and self._t_ref is not None:
            self._t_acumulado += (time.monotonic() - self._t_ref) * 1000 * self.velocidad
            self._t_ref = None

    def reanudar(self):
        if self.activo and self._t_ref is None:
            self._t_ref = time.monotonic()

    def cambiar_velocidad(self, velocidad):
        en_marcha = self._t_ref is not None
        self.pausar()
        self.velocidad = _limitar(velocidad, 0.1, 5.0)
        if en_marcha:
            self.reanudar()

    def tiempo_ms(self):
        t = self._t_acumulado
        if self._t_ref is not None:
            t += (time.monotonic() - self._t_ref) * 1000 * self.velocidad
        return t

    def pose_actual(self):
        """(dedos, indice_paso). Si termina, se detiene y devuelve (None, -1)."""
        if not self.activo:
            return None, -1
        dedos, indice = pose_en(self.secuencia, self.tiempo_ms(), self.pose_inicial)
        if dedos is None:
            self.detener()
        return dedos, indice


def listar_secuencias_guardadas(directorio=None):
    directorio = directorio or DIRECTORIO_SECUENCIAS
    if not os.path.isdir(directorio):
        return []
    return sorted(os.path.join(directorio, f) for f in os.listdir(directorio) if f.endswith(".json"))
