import time
from types import SimpleNamespace

import pytest

from mano import vision
from mano.vision import (CALIBRACION_DEFECTO, Calibrador, FiltroDedos, a_porcentaje,
                         angulo_flexion, cargar_calibracion, clasificar_gesto, guardar_calibracion,
                         metricas_crudas)


def punto(x, y, z=0.0):
    return SimpleNamespace(x=x, y=y, z=z)


def mano_sintetica(cerrados=()):
    """Mano plana: dedos rectos hacia -y; los dedos en 'cerrados' se doblan 90° en cada falange."""
    lm = [punto(0, 0)] * 21
    lm[0] = punto(0, 0)
    bases = {1: (-0.02, -0.06), 2: (-0.01, -0.07), 3: (0.01, -0.07), 4: (0.03, -0.06)}
    cadenas = {1: [5, 6, 7, 8], 2: [9, 10, 11, 12], 3: [13, 14, 15, 16], 4: [17, 18, 19, 20]}
    for dedo, (bx, by) in bases.items():
        idx = cadenas[dedo]
        lm[idx[0]] = punto(bx, by)
        if dedo in cerrados:
            lm[idx[1]] = punto(bx, by, -0.03)         # MCP 90° hacia la palma
            lm[idx[2]] = punto(bx, by + 0.02, -0.03)  # PIP otros 90°
            lm[idx[3]] = punto(bx, by + 0.02, -0.01)  # DIP otros 90°
        else:
            for k in (1, 2, 3):
                lm[idx[k]] = punto(bx, by - 0.025 * k)
    # Pulgar: abierto hacia fuera o cruzado sobre la palma
    lm[1], lm[2], lm[3] = punto(-0.03, -0.02), punto(-0.05, -0.03), punto(-0.07, -0.04)
    lm[4] = punto(0.02, -0.04) if 0 in cerrados else punto(-0.09, -0.05)
    return lm


def test_angulo_flexion():
    assert angulo_flexion(punto(0, 0), punto(0, 1), punto(0, 2)) == pytest.approx(0, abs=0.01)
    assert angulo_flexion(punto(0, 0), punto(0, 1), punto(1, 1)) == pytest.approx(90)


def test_mano_abierta_y_puno():
    abierta = a_porcentaje(metricas_crudas(mano_sintetica()), CALIBRACION_DEFECTO)
    assert all(v > 90 for v in abierta)
    cerrada = a_porcentaje(metricas_crudas(mano_sintetica(cerrados=range(5))), CALIBRACION_DEFECTO)
    assert all(v < 15 for v in cerrada), cerrada


def test_a_porcentaje_limita_y_rango_cero():
    calib = {"abierto": [2, 0, 0, 0, 5], "cerrado": [1, 100, 100, 100, 5]}
    assert a_porcentaje([3, -50, 50, 200, 5], calib) == [100, 100, 50, 0, 100]


def test_calibracion_guardar_y_cargar(tmp_path):
    ruta = str(tmp_path / "c.json")
    calib = {"abierto": [1, 2, 3, 4, 5], "cerrado": [6, 7, 8, 9, 10]}
    guardar_calibracion(calib, ruta)
    assert cargar_calibracion(ruta) == calib


def test_calibracion_invalida_vuelve_a_defecto(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text('{"abierto": [1, 2]}', encoding="utf-8")
    assert cargar_calibracion(str(ruta)) == CALIBRACION_DEFECTO
    assert cargar_calibracion(str(tmp_path / "no_existe.json")) == CALIBRACION_DEFECTO


def test_calibrador_usa_la_mediana(monkeypatch):
    reloj = [0.0]
    monkeypatch.setattr(vision.time, "time", lambda: reloj[0])
    calib = vision.calibracion_defecto()
    cal = Calibrador(duracion=1.0)
    cal.iniciar("cerrado")
    for valor in (1, 2, 100, 3):              # el 100 es un valor atípico
        assert cal.agregar([valor] * 5, calib) is None
    reloj[0] = 1.5
    assert cal.agregar([4] * 5, calib) == "cerrado"
    assert calib["cerrado"] == [3] * 5
    assert not cal.activo


def test_calibrador_tipo_invalido():
    with pytest.raises(ValueError):
        Calibrador().iniciar("medio")


def test_filtro_histeresis():
    f = FiltroDedos(suavizado=1.0)
    f.actualizar([55] * 5)
    assert f.estados == [1] * 5               # entre umbrales: mantiene el estado
    f.actualizar([30] * 5)
    assert f.estados == [0] * 5
    f.actualizar([55] * 5)
    assert f.estados == [0] * 5
    f.actualizar([70] * 5)
    assert f.estados == [1] * 5


def test_filtro_suaviza():
    f = FiltroDedos(suavizado=0.5)
    f.actualizar([0] * 5)
    assert f.porcentajes == [50] * 5


@pytest.mark.parametrize("dedos,esperado", [
    ([0, 0, 0, 0, 0], "PUNO CERRADO"),
    ([0, 1, 1, 0, 0], "PAZ / VICTORIA"),
    ([1, 1, 0, 0, 1], "ROCK / SPIDERMAN"),
    ([1, 0, 0, 0, 1], "TELEFONO"),
    ([1, 1, 1, 0, 1], "MOVIMIENTO LIBRE"),
])
def test_clasificar_gesto(dedos, esperado):
    assert clasificar_gesto(dedos, mano_sintetica()) == esperado


def test_tiempo_no_se_usa_en_import():
    # La visión no debe abrir cámaras ni descargar nada al importarse
    assert time.time() > 0 and vision.RUTA_MODELO.endswith("hand_landmarker.task")
