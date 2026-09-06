# 🦾 HandProyect — Instalación en Kali Linux

Sistema de control de una mano robótica mediante **visión artificial**, utilizando Python, OpenCV, MediaPipe, comunicación Serial y Arduino.

Este documento explica cómo instalar y ejecutar **HandProyect** en un equipo con **Kali Linux**.

---

## 📋 Requisitos

### Hardware

* PC con Kali Linux
* Webcam
* Arduino UNO
* PCA9685
* 5 servomotores
* Mano robótica
* Cable USB para Arduino
* Fuente externa para los servomotores

### Software

* Kali Linux actualizado
* Python 3
* Git
* Arduino IDE
* Arduino conectado por USB

---

# 1. Actualizar Kali Linux

Abrir una terminal:

```bash
sudo apt update
sudo apt full-upgrade -y
```

Después instalar las herramientas necesarias:

```bash
sudo apt install -y git python3 python3-pip python3-venv python3-dev build-essential
```

Kali proporciona `python3-venv` para crear entornos virtuales aislados de Python.

---

# 2. Descargar HandProyect

Clonar el repositorio:

```bash
git clone https://github.com/josemanuelcontrerasgalarza-cyber/HandProyect.git
```

Entrar al proyecto:

```bash
cd HandProyect
```

Comprobar los archivos:

```bash
ls
```

Deberían aparecer los archivos principales del proyecto.

---

# 3. Crear el entorno virtual

Crear un entorno virtual:

```bash
python3 -m venv venv
```

Activarlo:

```bash
source venv/bin/activate
```

Cuando esté activado, la terminal debería mostrar algo similar a:

```text
(venv) user@kali:~/HandProyect$
```

MediaPipe también recomienda utilizar un entorno virtual para instalar su paquete Python.

---

# 4. Actualizar pip

Con el entorno virtual activado:

```bash
python -m pip install --upgrade pip
```

---

# 5. Instalar las dependencias

El proyecto incluye un archivo:

```text
requirements.txt
```

Instalar todas las dependencias:

```bash
pip install -r requirements.txt
```

Entre las dependencias utilizadas por el proyecto se encuentran herramientas para:

* Procesamiento de imágenes.
* Visión artificial.
* Detección de manos.
* Comunicación Serial.
* Cálculos numéricos.

---

# 6. Comprobar MediaPipe

Ejecutar:

```bash
python -c "import mediapipe as mp; print('MediaPipe OK')"
```

Si aparece:

```text
MediaPipe OK
```

la instalación fue correcta.

MediaPipe proporciona paquetes Python precompilados para Linux y permite instalarlo mediante `pip` dentro de un entorno virtual.

---

# 7. Comprobar OpenCV

Ejecutar:

```bash
python -c "import cv2; print(cv2.__version__)"
```

Debería aparecer la versión instalada de OpenCV.

Ejemplo:

```text
4.x.x
```

---

# 8. Comprobar NumPy

```bash
python -c "import numpy; print(numpy.__version__)"
```

---

# 9. Comprobar comunicación Serial

```bash
python -c "import serial; print('PySerial OK')"
```

Si aparece:

```text
PySerial OK
```

la comunicación Serial está disponible.

---

# 🔌 10. Conectar Arduino UNO

Conectar el Arduino UNO mediante USB.

Después ejecutar:

```bash
ls /dev/ttyACM*
```

También se puede comprobar:

```bash
ls /dev/ttyUSB*
```

Dependiendo del sistema, Arduino puede aparecer como:

```text
/dev/ttyACM0
```

o:

```text
/dev/ttyUSB0
```

---

# 🔐 11. Permisos del puerto Serial

Si el programa no puede acceder al Arduino, agregar el usuario al grupo `dialout`:

```bash
sudo usermod -aG dialout $USER
```

Después cerrar sesión y volver a entrar.

También puede reiniciarse el equipo:

```bash
sudo reboot
```

Después comprobar:

```bash
groups
```

Debe aparecer:

```text
dialout
```

---

# ⚙️ 12. Configurar el puerto Arduino

El proyecto necesita conocer el puerto Serial del Arduino.

Primero identificarlo:

```bash
ls /dev/ttyACM*
```

Ejemplo:

```text
/dev/ttyACM0
```

Abrir el archivo principal:

```bash
nano hand_control.py
```

Buscar la configuración del puerto Serial.

Si actualmente existe algo como:

```python
SERIAL_PORT = "COM11"
```

cambiarlo por:

```python
SERIAL_PORT = "/dev/ttyACM0"
```

Guardar:

```text
CTRL + O
ENTER
```

Salir:

```text
CTRL + X
```

> Si Kali asigna otro puerto, utilizar el puerto que aparezca en `/dev/`.

---

# 🧠 13. Configurar Arduino

Antes de ejecutar Python, el Arduino debe tener cargado el programa correspondiente.

Abrir Arduino IDE.

Seleccionar:

```text
Tools → Board → Arduino UNO
```

Después seleccionar el puerto correspondiente.

Cargar el sketch del proyecto.

Una vez cargado correctamente, cerrar el **Serial Monitor** de Arduino IDE antes de ejecutar Python.

Esto es importante porque el Serial Monitor puede ocupar el puerto.

---

# 🔧 14. PCA9685 y servomotores

El PCA9685 se utiliza para controlar los servomotores.

La alimentación de los servos debe realizarse mediante una fuente externa apropiada.

### ⚠️ IMPORTANTE

**NO alimentar los 5 servomotores directamente desde el Arduino UNO.**

El Arduino y la fuente externa deben compartir:

```text
GND Arduino
     │
     └──────── GND fuente de servos
```

La alimentación de los servos debe conectarse según las especificaciones de los servomotores utilizados.

---

# 📷 15. Comprobar la cámara

Antes de ejecutar el proyecto, comprobar que Kali detecta la webcam:

```bash
ls /dev/video*
```

Normalmente aparecerá:

```text
/dev/video0
```

También se puede comprobar mediante:

```bash
v4l2-ctl --list-devices
```

Si el comando no existe:

```bash
sudo apt install v4l-utils
```

---

# ▶️ 16. Ejecutar HandProyect

Activar el entorno virtual:

```bash
source venv/bin/activate
```

Ejecutar:

```bash
python hand_control.py
```

El sistema debería:

```text
📷 Detectar la cámara
        ↓
🖐️ Detectar la mano
        ↓
🧠 Analizar los dedos
        ↓
📊 Calcular estados de los dedos
        ↓
🔌 Enviar datos por Serial
        ↓
🤖 Arduino
        ↓
⚙️ PCA9685
        ↓
🦾 Mover los servomotores
```

---

# ⌨️ Controles

| Tecla | Función                                |
| ----- | -------------------------------------- |
| `M`   | Cambiar entre modo manual y automático |
| `ESC` | Salir del programa                     |

---

# 🛠️ Solución de problemas

## ❌ `externally-managed-environment`

Si aparece:

```text
error: externally-managed-environment
```

no instalar los paquetes globalmente.

Crear y activar nuevamente el entorno:

```bash
python3 -m venv venv
source venv/bin/activate
```

Después:

```bash
pip install -r requirements.txt
```

Kali recomienda utilizar entornos virtuales para paquetes Python que no estén instalados mediante APT.

---

## ❌ `No module named cv2`

Ejecutar:

```bash
pip install opencv-python
```

Después comprobar:

```bash
python -c "import cv2; print('OpenCV OK')"
```

---

## ❌ `No module named mediapipe`

Ejecutar:

```bash
pip install mediapipe
```

Comprobar:

```bash
python -c "import mediapipe; print('MediaPipe OK')"
```

---

## ❌ `No module named serial`

Instalar:

```bash
pip install pyserial
```

Comprobar:

```bash
python -c "import serial; print('PySerial OK')"
```

---

## ❌ Arduino no aparece

Comprobar:

```bash
ls /dev/ttyACM*
```

y:

```bash
ls /dev/ttyUSB*
```

Si no aparece ninguno:

1. Desconectar Arduino.
2. Volver a conectarlo.
3. Ejecutar:

```bash
dmesg | tail -30
```

Buscar una línea relacionada con:

```text
ttyACM
```

o:

```text
ttyUSB
```

---

## ❌ `Permission denied` con Arduino

Ejecutar:

```bash
sudo usermod -aG dialout $USER
```

Cerrar sesión y volver a entrar.

---

## ❌ La cámara no funciona

Comprobar:

```bash
ls /dev/video*
```

Si no aparece ningún dispositivo:

* Comprobar la conexión de la webcam.
* Probar otra webcam.
* Comprobar los permisos del dispositivo.
* Verificar que otra aplicación no esté utilizando la cámara.

---

## ❌ Los servos no se mueven

Comprobar:

* Alimentación externa.
* GND común.
* Cableado del PCA9685.
* Dirección I2C del PCA9685.
* Conexiones de los servos.
* Puerto Serial.
* Sketch cargado en Arduino.

---

# 🧪 Diagnóstico rápido

Ejecutar estos comandos:

```bash
python --version
```

```bash
pip --version
```

```bash
python -c "import cv2; print('OpenCV OK')"
```

```bash
python -c "import mediapipe; print('MediaPipe OK')"
```

```bash
python -c "import serial; print('PySerial OK')"
```

```bash
ls /dev/ttyACM*
```

```bash
ls /dev/video*
```

Si todos funcionan, ejecutar:

```bash
python hand_control.py
```

---

# 🔄 Instalación rápida

Para una instalación desde cero:

```bash
sudo apt update

sudo apt install -y git python3 python3-pip python3-venv python3-dev build-essential

git clone https://github.com/josemanuelcontrerasgalarza-cyber/HandProyect.git

cd HandProyect

python3 -m venv venv

source venv/bin/activate

python -m pip install --upgrade pip

pip install -r requirements.txt

python hand_control.py
```

---

# 🔁 Ejecución después de la instalación

Cada vez que se quiera ejecutar el proyecto:

```bash
cd HandProyect
```

```bash
source venv/bin/activate
```

```bash
python hand_control.py
```

---

# 🛑 Detener el proyecto

Presionar:

```text
ESC
```

El programa cerrará la cámara y finalizará la comunicación Serial.

Para salir del entorno virtual:

```bash
deactivate
```

---

# 📌 Notas

HandProyect requiere:

* Una cámara funcional.
* Un Arduino UNO correctamente configurado.
* Una conexión Serial disponible.
* Una instalación funcional de Python.
* Los componentes electrónicos correctamente conectados.

La configuración del puerto Serial puede variar entre equipos Linux.

**No asumir que `/dev/ttyACM0` será siempre el puerto utilizado.**

---

# 👨‍💻 Autor

**José Manuel Contreras Galarza**

HandProyect — Robótica + Visión Artificial + Arduino

---

## 📄 Licencia

Consultar el repositorio para conocer las condiciones de uso y distribución del proyecto.
