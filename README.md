# 🦾 HandProyect — Mano biónica con ESP32-S3

Control de una mano robótica mediante **visión artificial**: la webcam lee tu mano con
**MediaPipe**, Python calcula cuánto está abierto cada dedo (0-100 %) y la **ESP32-S3**
mueve 5 servos a través de un **PCA9685**. Funciona por **USB** o **sin cable por WiFi**, y
la ESP32 tiene además su propio **panel web** para controlarla desde el móvil.

Incluye una **aplicación de escritorio completa** (`mano_app.py`) con cámara, control manual,
editor de secuencias, calibración guiada, gráficas en tiempo real y consola.

## ✨ Novedades respecto a la versión Arduino UNO

| | Antes (Arduino UNO) | Ahora (ESP32-S3) |
|---|---|---|
| Movimiento | Solo abierto / cerrado | **Proporcional 0-100 %** (los dedos copian la posición real) + modo binario con `B` |
| Conexión | Solo USB, puerto `COM9` fijo | **USB autodetectado** (Linux y Windows) o **WiFi UDP** |
| Control sin PC | No | **Panel web** en `http://mano.local`: sliders, gestos, demo |
| Programa en el PC | Ventana OpenCV | **App de escritorio** con 6 pestañas (ver abajo) + versión ligera `hand_control.py` |
| Calibración | Cambiar el código | **Por dedo, desde la web o por serie, guardada en la flash** |
| Calibración de cámara | No | **Teclas `A` / `C`** ajustan a tu mano y se guardan |
| Seguridad | Timeout | Timeout con **apertura lenta**, arranque escalonado de servos, `RELAX` |
| MediaPipe | API antigua `mp.solutions` (**ya no existe** en mediapipe ≥ 0.10.30 / Python 3.13) | Nueva API **HandLandmarker** (Tasks) con coordenadas 3D reales |

> Los sketches antiguos `sketch_aug25a/` y `sketch_aug25b/` (Arduino UNO) se conservan como referencia.

---

## 📋 Hardware

* ESP32-S3 (p. ej. ESP32-S3-DevKitC-1)
* Módulo PCA9685 (I2C, dirección 0x40)
* 5 servomotores (MG90S / SG90 o similares)
* Fuente externa **5-6 V, mínimo 3 A** para los servos
* Webcam + PC con Kali Linux (también funciona en Windows / Ubuntu)

### 🔌 Cableado

| ESP32-S3 | PCA9685 |
|---|---|
| 3V3 | VCC |
| GND | GND |
| GPIO 8 | SDA |
| GPIO 9 | SCL |

* Fuente externa 5-6 V → bornera **V+ / GND** del PCA9685.
* **GND común**: el GND de la fuente, del PCA9685 y de la ESP32 deben estar unidos.
* **Nunca** alimentes los servos desde el pin 5V/3V3 de la ESP32.

| Dedo | Canal PCA9685 |
|---|---|
| Pulgar | 0 |
| Índice | 2 |
| Medio | 4 |
| Anular | 6 |
| Meñique | 8 |

Se pueden cambiar los pines en `PIN_SDA` / `PIN_SCL` y los canales en la tabla `mano[]` del firmware.

---

## 🧠 1. Cargar el firmware en la ESP32-S3

1. Instala el **Arduino IDE 2**.
2. En *Archivo → Preferencias → URLs adicionales de gestor de placas* añade:
   ```text
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. *Herramientas → Placa → Gestor de placas* → instala **esp32 de Espressif**.
4. *Herramientas → Gestionar bibliotecas* → instala **Adafruit PWM Servo Driver Library**.
5. Abre `firmware/ManoBionicaESP32S3/ManoBionicaESP32S3.ino`.
6. Selecciona:
   * Placa: **ESP32S3 Dev Module**
   * **USB CDC On Boot: Enabled** (si conectas por el USB nativo, el que pone "USB")
   * Puerto: `/dev/ttyACM0` (o `/dev/ttyUSB0` si usas el conector "UART/COM")
7. Pulsa **Subir**. Si no entra en modo de carga: mantén **BOOT**, pulsa **RST** y suelta **BOOT**.

Abre el Monitor Serie a **115200** y escribe `HELP`. Deberías ver:

```text
[WIFI] Punto de acceso 'ManoBionica-S3' (clave 'mano12345'). IP: 192.168.4.1
[WIFI] Panel web: http://mano.local  |  UDP puerto 4210
[SISTEMA] Mano Biónica ESP32-S3 lista. Escribe HELP.
```

### WiFi

Por defecto la ESP32 crea su propia red **`ManoBionica-S3`** (clave `mano12345`).
Para que se conecte a la WiFi de tu casa, rellena `WIFI_SSID` y `WIFI_PASS` al principio
del firmware; si no consigue conectar en 8 s vuelve a crear su propia red.

### LED RGB integrado

🟢 recibiendo de Python · 🔵 manual / web · 🟣 demo · 🟠 failsafe · 🔴 parpadeando = PCA9685 no detectado

---

## 🐍 2. Instalar el programa de visión en Kali Linux

```bash
sudo apt update
```

```bash
sudo apt install -y git python3 python3-pip python3-venv
```

```bash
git clone https://github.com/josemanuelcontrerasgalarza-cyber/HandProyect.git
```

```bash
cd HandProyect
```

```bash
python3 -m venv venv
```

```bash
source venv/bin/activate
```

```bash
pip install --upgrade pip
```

```bash
pip install -r requirements.txt
```

La primera vez que se ejecuta, el programa descarga automáticamente el modelo de MediaPipe
(`models/hand_landmarker.task`, ~8 MB).

### Permisos del puerto serie

```bash
sudo usermod -aG dialout $USER
```

Cierra la sesión y vuelve a entrar para que se aplique.

---

## ▶️ 3. Ejecutar

Por USB (el puerto de la ESP32 se detecta solo):

```bash
python hand_control.py
```

Indicando el puerto a mano:

```bash
python hand_control.py --puerto /dev/ttyACM0
```

Sin cable, conectado a la red `ManoBionica-S3`:

```bash
python hand_control.py --wifi 192.168.4.1
```

Solo la cámara, sin hardware:

```bash
python hand_control.py --sin-hardware
```

Otras opciones: `--camara 1` (otra webcam), `--ancho 640 --alto 480` (más FPS en PCs lentos),
`--binario` (empezar en modo abierto/cerrado como la versión antigua).

### ⌨️ Controles

| Tecla | Acción |
|---|---|
| `A` | Calibrar: pon la mano **totalmente abierta** y pulsa (muestrea 1 s) |
| `C` | Calibrar: cierra el **puño** y pulsa |
| `R` | Volver a la calibración por defecto |
| `B` | Cambiar entre modo **proporcional** y **binario** |
| `D` / `M` | Ejecutar / parar la **demo** guardada en la ESP32 |
| `ESC` / `Q` | Salir (la mano se abre antes de desconectar) |

La calibración de la cámara se guarda en `calibracion.json`.

---

## 🖥️ 4. Aplicación de escritorio

```bash
python mano_app.py
```

Arriba eliges la conexión (**USB**, **WiFi** o **Simulación**) y pulsas **Conectar**. El
desplegable **Fuente** indica quién mueve la mano en cada momento (cámara, sliders, secuencia o
la demo de la ESP32): solo hay una a la vez, así nunca se pelean por los servos. El botón rojo
**PARADA** (o la tecla `Esc`) deja de enviar y abre la mano.

| Pestaña | Para qué sirve |
|---|---|
| 📷 **Cámara** | Vídeo con el esqueleto de tu mano, gesto reconocido, barras por dedo y esquema de la mano robótica. «Controlar la mano con la cámara» hace que la mano te copie. Modo binario, suavizado y calibración rápida. |
| 🎚 **Manual** | Un slider por dedo, 11 gestos, demo de la ESP32, relajar servos y velocidad. |
| 🎞 **Secuencias** | Editor de movimientos: añade poses (de la cámara, de los sliders o gestos), con tiempo de transición, pausa y curva. Reproduce con pausa, velocidad y bucle. Se guardan en `secuencias/` y trae 5 de ejemplo (Saludo, Contar 1-5, Ola, Piano, Agarre suave). |
| 🎯 **Calibración** | Asistente guiado de la cámara (mano abierta → puño, con cuenta atrás) y ajuste de los pulsos de cada servo con prueba en vivo; se leen y se guardan en la ESP32. |
| 📈 **Gráficas** | Pose enviada y lectura de la cámara en tiempo real, estadísticas y exportación a CSV. |
| ⌨ **Consola** | Monitor serie integrado con historial (↑ / ↓), atajos y registro guardable. |

Atajos: `Esc` parada · `F5` cámara · `F6` controlar con la cámara · `Ctrl+K` conectar ·
`Ctrl+1…6` pestañas · `F1` ayuda.

Para arrancar ya conectado:

```bash
python mano_app.py --usb
```

```bash
python mano_app.py --wifi 192.168.4.1
```

### Probar sin la mano (simulador)

`tools/simulador_esp32.py` imita a la ESP32 (mismo protocolo, calibración, failsafe…) por UDP.
En una terminal:

```bash
python tools/simulador_esp32.py
```

En otra:

```bash
python mano_app.py --wifi 127.0.0.1
```

---

## 🎛️ 5. Calibrar los servos (una sola vez)

Desde la pestaña **🎯 Calibración** de la aplicación de escritorio, o desde el **panel web**
(`http://mano.local` o `http://192.168.4.1`) → sección *Calibración*:

1. Escribe un pulso en **Abierto**, pulsa **Probar** y ajusta hasta que el dedo quede totalmente abierto sin forzar el hilo.
2. Haz lo mismo con **Cerrado**.
3. Pulsa **Aplicar** en esa fila y al final **Guardar en la ESP32**.

O por el Monitor Serie:

```text
PULSO 1 140        mueve el índice a 140 ticks para probar
CAL 1 135 510      índice: abierto=135, cerrado=510
INV 0              invierte el sentido del pulgar
SAVE               guarda en la flash
```

### Todos los comandos

| Comando | Descripción |
|---|---|
| `P:a,b,c,d,e` | Posición de cada dedo 0-100 (% abierto) — lo que envía Python |
| `a,b,c,d,e` | Formato antiguo binario (1 = abierto, 0 = cerrado) |
| `OPEN` / `CLOSE` | Abrir / cerrar toda la mano |
| `GESTO <nombre>` / `GESTOS` | Hacer un gesto / listar gestos (ABIERTA, PUNO, PAZ, ROCK, OK, APUNTAR, PULGAR, PISTOLA, TELEFONO, PINZA, RELAJADA) |
| `SET <dedo> <0-100>` | Mover un dedo (0 = pulgar … 4 = meñique) |
| `SPEED <1-100>` | Velocidad de los servos |
| `DEMO` / `STOP` | Secuencia de demostración / parar |
| `RELAX` | Quitar la fuerza a los servos |
| `PULSO`, `CAL`, `INV`, `SAVE`, `LOAD`, `DEFAULTS` | Calibración |
| `STATUS`, `PING`, `HELP` | Información |

Los mismos comandos funcionan por USB, por UDP (puerto 4210) y desde la web.

---

## 🧪 Tests

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

Comprueban la interpolación de secuencias, la calibración, el cálculo de flexión, la
comunicación UDP, el simulador y que el formato de `STATUS` del firmware coincida con lo que
entiende la aplicación.

---

## 🗂️ Estructura

```text
firmware/ManoBionicaESP32S3/   Firmware de la ESP32-S3 (+ panel web)
mano/                          Núcleo en Python: enlace USB/WiFi, visión, secuencias
mano/gui/                      Aplicación de escritorio (PySide6)
mano_app.py                    Arranca la aplicación de escritorio
hand_control.py                Versión ligera con ventana OpenCV
tools/simulador_esp32.py       Simulador de la ESP32 para probar sin hardware
tests/                         Tests automáticos
sketch_aug25a/, sketch_aug25b/ Versión antigua para Arduino UNO
```

---

## 🛠️ Solución de problemas

**La aplicación no abre en Kali (`libEGL.so.1` / `xcb`)**
Instala las librerías de Qt: `sudo apt install -y libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0`.


**`AttributeError: module 'mediapipe' has no attribute 'solutions'`**
Era el error de la versión anterior con Python 3.13. Usa el nuevo `hand_control.py` de este repositorio.

**`externally-managed-environment` al instalar**
Activa el entorno virtual (`source venv/bin/activate`) antes de `pip install`.

**La ESP32 no aparece como puerto**
Comprueba con `ls /dev/ttyACM* /dev/ttyUSB*`. Usa un cable USB de datos (no solo de carga) y
activa *USB CDC On Boot* si usas el conector USB nativo.

**`[ERROR] PCA9685 no detectado`**
Revisa SDA → GPIO 8, SCL → GPIO 9, VCC → 3V3 y GND.

**Los servos tiemblan o la ESP32 se reinicia**
La fuente de los servos es insuficiente o falta el GND común. Usa 5-6 V y al menos 3 A.

**Un dedo se mueve al revés**
`INV <dedo>` y `SAVE`, o intercambia los valores en el panel web.

**Los dedos no llegan a cerrar / abrir del todo en la cámara**
Calibra con las teclas `A` (mano abierta) y `C` (puño).
