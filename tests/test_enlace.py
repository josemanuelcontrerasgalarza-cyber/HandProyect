import socket
import time

from mano.enlace import EnlaceNulo, EnlaceWiFi, _BufferLineas, formatear_trama


def test_formatear_trama_redondea_y_limita():
    assert formatear_trama([-5, 49.6, 100.4, 0, 250]) == "P:0,50,100,0,100"


def test_buffer_lineas_parciales():
    b = _BufferLineas()
    b.agregar("HOLA\r\nMUN")
    assert b.extraer() == ["HOLA"]
    b.agregar("DO\n\n\nFIN\n")
    assert b.extraer() == ["MUNDO", "FIN"]
    assert b.extraer() == []


def test_buffer_basura_sin_salto():
    b = _BufferLineas()
    b.agregar("x" * 5000)
    assert len(b.extraer()) == 1


def test_enlace_nulo_responde_ping():
    e = EnlaceNulo()
    assert e.enviar("ping")
    assert e.leer() == ["PONG SIMULACION"]
    assert e.leer() == []


def test_enlace_wifi_envia_y_recibe():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    servidor.bind(("127.0.0.1", 0))
    servidor.settimeout(2)
    puerto = servidor.getsockname()[1]
    enlace = EnlaceWiFi("127.0.0.1", puerto)
    try:
        assert enlace.enviar("P:1,2,3,4,5")
        datos, origen = servidor.recvfrom(100)
        assert datos == b"P:1,2,3,4,5\n"
        servidor.sendto(b"PONG\nOTRA", origen)
        lineas = []
        for _ in range(100):
            lineas += enlace.leer()
            if lineas:
                break
            time.sleep(0.01)
        assert lineas == ["PONG", "OTRA"]
        assert enlace.conectado
    finally:
        enlace.cerrar()
        servidor.close()
