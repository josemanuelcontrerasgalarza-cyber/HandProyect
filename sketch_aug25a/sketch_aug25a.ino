/**
 * ============================================================================
 *   PROJECT: BIONIC HAND CORE OS (ADVANCED SERVO CONTROLLER) - INVERSION FIX
 *   HARDWARE: Arduino Uno + Adafruit PCA9685 I2C (0x40)
 *   TARGET: 5-DOF Prosthetic Robotic Hand Interface
 *   BAUD RATE: 115200 bps
 * ============================================================================
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ==========================================
// 1. CONSTANTES DE CALIBRACIÓN Y TIMING
// ==========================================
#define NUM_DEDOS             5
#define PCA_I2C_ADDR          0x40
#define FRECUENCIA_PWM        50

#define PCA_TICKS_OPEN        130    // ~0°
#define PCA_TICKS_CLOSED      520    // ~180°

#define SERIAL_TIMEOUT_MS     1500
#define LOOP_TICK_RATE_HZ     100

// ==========================================
// 2. ESTRUCTURA DE CONTROL CINEMÁTICO
// ==========================================
struct DedoArticulacion {
  const char* nombre;
  uint8_t canalPCA;
  bool invertido;
  float posActual;       // [0.0 (Cerrado) - 1.0 (Abierto)]
  float posObjetivo;     
  float velocidad;       
  uint16_t pulsoMin;
  uint16_t pulsoMax;
};

// Configuración con polaridades corregidas:
// Pulgar invertido a FALSE, los otros 4 a TRUE para que coincidan con la cámara
DedoArticulacion mano[NUM_DEDOS] = {
  {"PULGAR",  0, false, 1.0, 1.0, 0.12, PCA_TICKS_OPEN, PCA_TICKS_CLOSED},
  {"INDICE",  2, true,  1.0, 1.0, 0.12, PCA_TICKS_OPEN, PCA_TICKS_CLOSED},
  {"MEDIO",   4, true,  1.0, 1.0, 0.12, PCA_TICKS_OPEN, PCA_TICKS_CLOSED},
  {"ANULAR",  6, true,  1.0, 1.0, 0.12, PCA_TICKS_OPEN, PCA_TICKS_CLOSED},
  {"MENIQUE", 8, true,  1.0, 1.0, 0.12, PCA_TICKS_OPEN, PCA_TICKS_CLOSED}
};

// ==========================================
// 3. INSTANCIAS Y VARIABLES GLOBALES
// ==========================================
Adafruit_PWMServoDriver pcaDriver = Adafruit_PWMServoDriver(PCA_I2C_ADDR);

enum SistemaModo {
  MODO_STREAMING_SERIAL,
  MODO_DEMO_SWEEP,
  MODO_FAILSAFE,
  MODO_CALIBRACION
};

SistemaModo modoActual = MODO_STREAMING_SERIAL;

unsigned long ultimoTickCinematica = 0;
unsigned long ultimaTramaRecibida = 0;
unsigned long ultimoReporteTelemetria = 0;
unsigned long tiempoSweepAuto = 0;

char bufferSerial[64];
uint8_t indiceBuffer = 0;
bool modoSilencioso = false;

// ==========================================
// 4. FUNCIONES DE CÁLCULO Y CINEMÁTICA
// ==========================================
float curvaSuavizado(float actual, float target, float rate) {
  float error = target - actual;
  if (abs(error) < 0.005) return target;
  return actual + (error * rate);
}

uint16_t normalizadoATicksPCA(uint8_t idDedo, float valorNorm) {
  valorNorm = constrain(valorNorm, 0.0, 1.0);
  if (mano[idDedo].invertido) {
    valorNorm = 1.0 - valorNorm;
  }
  return (uint16_t)(mano[idDedo].pulsoMin + (valorNorm * (mano[idDedo].pulsoMax - mano[idDedo].pulsoMin)));
}

void actualizarMotoresFisicos() {
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    mano[i].posActual = curvaSuavizado(mano[i].posActual, mano[i].posObjetivo, mano[i].velocidad);
    uint16_t valorTicks = normalizadoATicksPCA(i, mano[i].posActual);
    pcaDriver.setPWM(mano[i].canalPCA, 0, valorTicks);
  }
}

// ==========================================
// 5. RUTINAS DE COMPORTAMIENTO Y MODOS
// ==========================================
void ejecutarSecuenciaDemo() {
  unsigned long tiempo = millis() - tiempoSweepAuto;
  uint8_t fase = (tiempo / 1200) % 6;

  switch (fase) {
    case 0:
      for (int i = 0; i < NUM_DEDOS; i++) mano[i].posObjetivo = 1.0;
      break;
    case 1:
      for (int i = 0; i < NUM_DEDOS; i++) mano[i].posObjetivo = 0.0;
      break;
    case 2:
      mano[0].posObjetivo = 0.0; mano[1].posObjetivo = 1.0;
      mano[2].posObjetivo = 1.0; mano[3].posObjetivo = 0.0; mano[4].posObjetivo = 0.0;
      break;
    case 3:
      mano[0].posObjetivo = 1.0; mano[1].posObjetivo = 1.0;
      mano[2].posObjetivo = 0.0; mano[3].posObjetivo = 0.0; mano[4].posObjetivo = 1.0;
      break;
    case 4:
      {
        uint8_t dedoOla = (tiempo / 250) % NUM_DEDOS;
        for (int i = 0; i < NUM_DEDOS; i++) {
          mano[i].posObjetivo = (i == dedoOla) ? 1.0 : 0.0;
        }
      }
      break;
    case 5:
      for (int i = 0; i < NUM_DEDOS; i++) mano[i].posObjetivo = 0.5;
      break;
  }
}

void activarFailsafe() {
  if (modoActual != MODO_FAILSAFE) {
    modoActual = MODO_FAILSAFE;
    Serial.println(F("[FAILSAFE] Timeout Serial (>1.5s). Mano en reposo."));
    for (uint8_t i = 0; i < NUM_DEDOS; i++) {
      mano[i].posObjetivo = 1.0;
      mano[i].velocidad = 0.04;
    }
  }
}

// ==========================================
// 6. PARSER DE COMANDOS Y COMUNICACIÓN SERIAL
// ==========================================
void procesarTramaStreaming(char* trama) {
  int v[NUM_DEDOS];
  int campos = sscanf(trama, "%d,%d,%d,%d,%d", &v[0], &v[1], &v[2], &v[3], &v[4]);

  if (campos == NUM_DEDOS) {
    ultimaTramaRecibida = millis();
    modoActual = MODO_STREAMING_SERIAL;

    for (uint8_t i = 0; i < NUM_DEDOS; i++) {
      mano[i].posObjetivo = (v[i] == 1) ? 1.0 : 0.0;
      mano[i].velocidad = 0.15;
    }
  }
}

void procesarComandoTexto(char* cmd) {
  while (*cmd == ' ') cmd++;

  if (strcasecmp(cmd, "HELP") == 0) {
    Serial.println(F("\nCOMANDOS: STATUS, SWEEP, STREAM, OPEN, CLOSE, RESET\n"));
  }
  else if (strcasecmp(cmd, "STATUS") == 0) {
    Serial.println(F("\n--- ESTADO DE MOTORES ---"));
    for (uint8_t i = 0; i < NUM_DEDOS; i++) {
      Serial.print(mano[i].nombre);
      Serial.print(F(" (CH "));
      Serial.print(mano[i].canalPCA);
      Serial.print(F(") Invertido: "));
      Serial.print(mano[i].invertido ? F("SI") : F("NO"));
      Serial.print(F(" | Actual: "));
      Serial.print((int)(mano[i].posActual * 100));
      Serial.println(F("%"));
    }
    Serial.println(F("-------------------------\n"));
  }
  else if (strcasecmp(cmd, "SWEEP") == 0) {
    modoActual = MODO_DEMO_SWEEP;
    tiempoSweepAuto = millis();
    for (uint8_t i = 0; i < NUM_DEDOS; i++) mano[i].velocidad = 0.06;
    Serial.println(F("[MODO] Test Sweep iniciado."));
  }
  else if (strcasecmp(cmd, "STREAM") == 0) {
    modoActual = MODO_STREAMING_SERIAL;
    ultimaTramaRecibida = millis();
    Serial.println(F("[MODO] Escuchando Python en COM7..."));
  }
  else if (strcasecmp(cmd, "OPEN") == 0) {
    modoActual = MODO_CALIBRACION;
    for (uint8_t i = 0; i < NUM_DEDOS; i++) mano[i].posObjetivo = 1.0;
    Serial.println(F("[ACCION] Mano abierta."));
  }
  else if (strcasecmp(cmd, "CLOSE") == 0) {
    modoActual = MODO_CALIBRACION;
    for (uint8_t i = 0; i < NUM_DEDOS; i++) mano[i].posObjetivo = 0.0;
    Serial.println(F("[ACCION] Mano cerrada."));
  }
  else if (strcasecmp(cmd, "RESET") == 0) {
    for (uint8_t i = 0; i < NUM_DEDOS; i++) {
      mano[i].posObjetivo = 1.0;
      mano[i].velocidad = 0.12;
    }
    modoActual = MODO_STREAMING_SERIAL;
    Serial.println(F("[SISTEMA] Reset aplicado."));
  }
}

void atenderPuertoSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (indiceBuffer > 0) {
        bufferSerial[indiceBuffer] = '\0';
        if (strchr(bufferSerial, ',') != NULL) {
          procesarTramaStreaming(bufferSerial);
        } else {
          procesarComandoTexto(bufferSerial);
        }
        indiceBuffer = 0;
      }
    } else if (indiceBuffer < (sizeof(bufferSerial) - 1)) {
      bufferSerial[indiceBuffer++] = c;
    }
  }
}

// ==========================================
// 7. SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Wire.begin();
  Wire.setClock(400000);

  pcaDriver.begin();
  pcaDriver.setPWMFreq(FRECUENCIA_PWM);
  delay(20);

  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    uint16_t tickInicial = normalizadoATicksPCA(i, mano[i].posActual);
    pcaDriver.setPWM(mano[i].canalPCA, 0, tickInicial);
    delay(50);
  }

  ultimaTramaRecibida = millis();
  Serial.println(F("[SISTEMA] Listo con polaridad corregida."));
}

// ==========================================
// 8. LOOP
// ==========================================
void loop() {
  unsigned long tiempoActual = millis();

  atenderPuertoSerial();

  if (tiempoActual - ultimoTickCinematica >= (1000 / LOOP_TICK_RATE_HZ)) {
    ultimoTickCinematica = tiempoActual;

    if (modoActual == MODO_DEMO_SWEEP) {
      ejecutarSecuenciaDemo();
    } 
    else if (modoActual == MODO_STREAMING_SERIAL) {
      if (tiempoActual - ultimaTramaRecibida > SERIAL_TIMEOUT_MS) {
        activarFailsafe();
      }
    }

    actualizarMotoresFisicos();
  }
}