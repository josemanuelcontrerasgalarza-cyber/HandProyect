sudo apt update
sudo apt install -y python3-pip python3-venv libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 v4l-utils 
this is for kali linux 
sudo systemctl stop brltty-udev.service 2>/dev/null
sudo systemctl mask brltty-udev.service 2>/dev/null
sudo apt remove -y brltty


# 1. Crear entorno virtual dentro de la carpeta del proyecto
python3 -m venv venv

# 2. Activar el entorno
source venv/bin/activate

# 3. Actualizar pip e instalar requirements
pip install --upgrade pip
pip install -r requirements.txt

for read the ports
sudo usermod -aG dialout $USER

and to indentify what is the port of arduino 
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null

and if kali identify your webcam
ls /dev/video*
