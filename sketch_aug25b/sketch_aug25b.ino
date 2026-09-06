#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// Calibración de pulsos
#define SERVOMIN  130 // Abierto (~0°)
#define SERVOMAX  550 // Cerrado (~180°)

// Asignación de canales en la placa PCA9685
const int CANAL_PULGAR  = 0;
const int CANAL_INDICE  = 2;
const int CANAL_MEDIO   = 4;
const int CANAL_ANULAR  = 6;
const int CANAL_MENIQUE = 8;

const int canales[5] = {CANAL_PULGAR, CANAL_INDICE, CANAL_MEDIO, CANAL_ANULAR, CANAL_MENIQUE};
int estadoAnterior[5] = {-1, -1, -1, -1, -1};

char buffer[32];
int bufferIndex = 0;

void setup() {
  Serial.begin(115200);
  pca.begin();
  pca.setPWMFreq(50); // Frecuencia a 50Hz

  // Posición inicial: todos abiertos con pequeña pausa para evitar picos de corriente
  for (int i = 0; i < 5; i++) {
    pca.setPWM(canales[i], 0, SERVOMIN);
    estadoAnterior[i] = 1;
    delay(40);
  }
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      buffer[bufferIndex] = '\0';
      bufferIndex = 0;

      int nuevoEstado[5];
      // Lee los 5 valores [Pulgar, Indice, Medio, Anular, Menique] desde Python
      if (sscanf(buffer, "%d,%d,%d,%d,%d", &nuevoEstado[0], &nuevoEstado[1], &nuevoEstado[2], &nuevoEstado[3], &nuevoEstado[4]) == 5) {
        for (int i = 0; i < 5; i++) {
          if (nuevoEstado[i] != estadoAnterior[i]) {
            int pulso = (nuevoEstado[i] == 1) ? SERVOMIN : SERVOMAX;
            pca.setPWM(canales[i], 0, pulso);
            estadoAnterior[i] = nuevoEstado[i];
            delay(15); // Escalonamiento para proteger la fuente
          }
        }
      }
    } else if (bufferIndex < 31 && c != '\r') {
      buffer[bufferIndex++] = c;
    }
  }
}