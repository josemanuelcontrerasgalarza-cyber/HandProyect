import time

import pytest

from mano.secuencias import (GESTOS, Paso, Reproductor, Secuencia, curva, pose_en,
                             secuencias_ejemplo)


def test_paso_limita_valores():
    paso = Paso([-10, 50.4, 150, 0, 100], transicion_ms=-5, pausa_ms=99999999, curva="rara")
    assert paso.dedos == [0, 50, 100, 0, 100]
    assert paso.transicion_ms == 0
    assert paso.pausa_ms == 60000
    assert paso.curva == "suave"


def test_paso_requiere_cinco_dedos():
    with pytest.raises(ValueError):
        Paso([1, 2, 3])


def test_curvas_en_extremos():
    for tipo in ("suave", "lineal"):
        assert curva(0, tipo) == 0
        assert curva(1, tipo) == 1
    assert curva(0.5, "lineal") == 0.5
    assert curva(0.0, "instantanea") == 1.0
    assert curva(0.25, "suave") < 0.25          # arranque suave


def test_pose_en_interpola_y_termina():
    sec = Secuencia("t", [Paso([0] * 5, 1000, 0), Paso([100] * 5, 1000, 500, curva="lineal")])
    inicial = [100] * 5
    assert pose_en(sec, 0, inicial)[0] == [100] * 5
    dedos, indice = pose_en(sec, 999, inicial)
    assert indice == 0 and all(v < 1 for v in dedos)
    dedos, indice = pose_en(sec, 1500, inicial)
    assert indice == 1 and dedos == [50] * 5
    dedos, indice = pose_en(sec, 2200, inicial)
    assert indice == 1 and dedos == [100] * 5    # en la pausa
    assert pose_en(sec, 2500, inicial) == (None, -1)


def test_pose_en_bucle_no_termina():
    sec = Secuencia("t", [Paso([0] * 5, 100, 100), Paso([100] * 5, 100, 100)], bucle=True)
    dedos, indice = pose_en(sec, 10_000 + 350)
    assert dedos is not None and indice == 1


def test_secuencia_vacia():
    assert pose_en(Secuencia(), 0) == (None, -1)


def test_json_ida_y_vuelta(tmp_path):
    sec = Secuencia("Prueba ñ", [Paso(GESTOS["PAZ"], 300, 200, "Paz", "lineal")], bucle=True)
    ruta = tmp_path / "sub" / "prueba.json"
    sec.guardar(str(ruta))
    cargada = Secuencia.cargar(str(ruta))
    assert cargada == sec


def test_desde_dict_ignora_campos_desconocidos():
    sec = Secuencia.desde_dict({"nombre": "x", "pasos": [{"dedos": [1, 2, 3, 4, 5], "extra": 1}]})
    assert sec.pasos[0].dedos == [1, 2, 3, 4, 5]


def test_ejemplos_validos():
    for sec in secuencias_ejemplo():
        assert sec.pasos and sec.duracion_ms > 0


def test_reproductor_pausa_y_velocidad(monkeypatch):
    reloj = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: reloj[0])
    rep = Reproductor()
    sec = Secuencia("t", [Paso([0] * 5, 1000, 0, curva="lineal")])
    rep.iniciar(sec, [100] * 5)
    reloj[0] += 0.5
    assert rep.pose_actual()[0] == [50] * 5
    rep.pausar()
    reloj[0] += 10
    assert rep.pausado and rep.pose_actual()[0] == [50] * 5
    rep.reanudar()
    rep.cambiar_velocidad(2.0)
    reloj[0] += 0.2                               # 0.2 s a 2x = 400 ms
    assert rep.pose_actual()[0] == pytest.approx([10] * 5)
    reloj[0] += 1
    assert rep.pose_actual() == (None, -1)
    assert not rep.activo
