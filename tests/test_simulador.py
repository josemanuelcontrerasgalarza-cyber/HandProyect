import importlib.util
import os
import re
import time

import pytest

from mano.gui.controlador import RE_ESTADO_DEDO, RE_ESTADO_HW, RE_ESTADO_MODO

RUTA = os.path.join(os.path.dirname(__file__), "..", "tools", "simulador_esp32.py")
spec = importlib.util.spec_from_file_location("simulador_esp32", RUTA)
simulador = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simulador)


@pytest.fixture
def mano():
    return simulador.ManoSimulada()


def test_trama_proporcional(mano):
    assert mano.procesar("P:0,25,50,75,100", "USB") == []
    assert mano.modo == "STREAMING"
    assert mano.objetivo == [0, 0.25, 0.5, 0.75, 1.0]


def test_trama_binaria_antigua(mano):
    mano.procesar("1,0,1,0,1", "USB")
    assert mano.objetivo == [1, 0, 1, 0, 1]


def test_trama_invalida(mano):
    assert mano.procesar("P:1,2,3", "USB") == ["[ERROR] Trama inválida."]


def test_comandos_basicos(mano):
    assert mano.procesar("ping", "USB")[0].startswith("PONG")
    assert mano.procesar("GESTO paz", "USB") == ["[GESTO] PAZ"]
    assert mano.objetivo == [0, 1, 1, 0, 0]
    assert mano.procesar("SET 9 10", "USB")[0].startswith("[ERROR]")
    assert mano.procesar("XYZ", "USB")[0].startswith("[ERROR] Comando desconocido")


def test_calibracion_save_load(mano):
    mano.procesar("CAL 1 140 500", "USB")
    mano.procesar("SAVE", "USB")
    mano.procesar("INV 1", "USB")
    assert (mano.abierto[1], mano.cerrado[1]) == (500, 140)
    mano.procesar("LOAD", "USB")
    assert (mano.abierto[1], mano.cerrado[1]) == (140, 500)


def test_status_lo_entiende_la_app(mano):
    """El formato de STATUS debe coincidir con las expresiones de la aplicación."""
    lineas = mano.procesar("STATUS", "USB")
    dedos = [RE_ESTADO_DEDO.match(l) for l in lineas if RE_ESTADO_DEDO.match(l)]
    assert len(dedos) == 5
    assert dedos[0].group(4) == "520" and dedos[0].group(5) == "130"
    assert any(RE_ESTADO_MODO.match(l) for l in lineas)
    assert any(RE_ESTADO_HW.match(l) for l in lineas)


def test_formato_status_igual_al_firmware():
    """Las líneas de dedos del firmware deben cumplir la misma expresión regular."""
    ino = os.path.join(os.path.dirname(__file__), "..", "firmware", "ManoBionicaESP32S3",
                       "ManoBionicaESP32S3.ino")
    with open(ino, encoding="utf-8") as f:
        fuente = f.read()
    formato = re.search(r'out\.printf\("(\[%u\] %-8s CH%-2u[^"]*)\\n"', fuente).group(1)
    ejemplo = formato.replace("%u", "1", 1).replace("%-8s", "INDICE  ").replace("%-2u", "2 ")
    ejemplo = ejemplo.replace("%3u", "130", 1).replace("%3u", "520", 1)
    ejemplo = ejemplo.replace("%3d", " 50", 1).replace("%3d", "100", 1).replace("%%", "%")
    assert RE_ESTADO_DEDO.match(ejemplo), ejemplo


def test_failsafe(mano, monkeypatch):
    reloj = [10.0]
    monkeypatch.setattr(time, "monotonic", lambda: reloj[0])
    mano.t_prev = reloj[0]
    mano.procesar("P:0,0,0,0,0", "USB")
    reloj[0] += 2.0
    mano.paso()
    assert mano.modo == "FAILSAFE"
    assert mano.objetivo == [1.0] * 5
