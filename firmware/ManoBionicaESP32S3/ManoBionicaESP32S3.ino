/**
 * ============================================================================
 *   PROYECTO: MANO BIÓNICA - FIRMWARE ESP32-S3
 *   HARDWARE: ESP32-S3 + Adafruit PCA9685 I2C (0x40) + 5 servos
 *   CONTROL:  USB Serial (115200) | WiFi UDP (puerto 4210) | Panel Web
 * ============================================================================
 *
 *  Cableado (ESP32-S3 DevKitC-1):
 *    ESP32-S3 3V3  -> PCA9685 VCC   (lógica a 3.3 V)
 *    ESP32-S3 GND  -> PCA9685 GND   (GND común con la fuente de los servos)
 *    ESP32-S3 GPIO8 -> PCA9685 SDA
 *    ESP32-S3 GPIO9 -> PCA9685 SCL
 *    Fuente externa 5-6 V -> PCA9685 V+ (bornera azul). ¡Nunca desde la ESP32!
 *    Servos en canales: Pulgar 0, Índice 2, Medio 4, Anular 6, Meñique 8
 *
 *  Protocolo (texto, una línea por mensaje, igual por USB y por UDP):
 *    P:a,b,c,d,e   -> posición proporcional 0..100 (% abierto) por dedo
 *    a,b,c,d,e     -> formato antiguo binario (1 = abierto, 0 = cerrado)
 *    HELP          -> lista de comandos
 *
 *  Librería necesaria: "Adafruit PWM Servo Driver Library"
 *  Placa: "ESP32S3 Dev Module" (Arduino-ESP32 2.x o 3.x)
 */

#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <Adafruit_PWMServoDriver.h>
#include "pagina_web.h"

// ==========================================
// 1. CONFIGURACIÓN
// ==========================================
#define NUM_DEDOS             5
#define PCA_I2C_ADDR          0x40
#define FRECUENCIA_PWM        50
#define PIN_SDA               8
#define PIN_SCL               9

#define SERIAL_TIMEOUT_MS     1500    // Sin tramas -> failsafe (mano abierta)
#define LOOP_TICK_RATE_HZ     100
#define PUERTO_UDP            4210

// WiFi: si WIFI_SSID está vacío (o no conecta), la mano crea su propia red.
#define WIFI_SSID             ""
#define WIFI_PASS             ""
#define AP_SSID               "ManoBionica-S3"
#define AP_PASS               "mano12345"     // mínimo 8 caracteres
#define NOMBRE_MDNS           "mano"          // http://mano.local

// Pulsos por defecto (ticks PCA9685 a 50 Hz, ~130 = 0°, ~520 = 180°)
#define PCA_TICKS_MIN         100
#define PCA_TICKS_MAX         600

// ==========================================
// 2. ESTRUCTURA DE CONTROL CINEMÁTICO
// ==========================================
struct DedoArticulacion {
  const char* nombre;
  uint8_t canalPCA;
  uint16_t pulsoAbierto;   // ticks con el dedo totalmente abierto
  uint16_t pulsoCerrado;   // ticks con el dedo totalmente cerrado
  float posActual;         // [0.0 (Cerrado) - 1.0 (Abierto)]
  float posObjetivo;
};

// Polaridades de la versión Arduino UNO: pulgar normal, los otros 4 invertidos.
// Para invertir un dedo basta con intercambiar abierto/cerrado (comando INV).
const uint16_t DEF_ABIERTO[NUM_DEDOS] = {520, 130, 130, 130, 130};
const uint16_t DEF_CERRADO[NUM_DEDOS] = {130, 520, 520, 520, 520};

DedoArticulacion mano[NUM_DEDOS] = {
  {"PULGAR",  0, 520, 130, 1.0, 1.0},
  {"INDICE",  2, 130, 520, 1.0, 1.0},
  {"MEDIO",   4, 130, 520, 1.0, 1.0},
  {"ANULAR",  6, 130, 520, 1.0, 1.0},
  {"MENIQUE", 8, 130, 520, 1.0, 1.0}
};

// Gestos predefinidos (% abierto: pulgar, índice, medio, anular, meñique)
struct Gesto {
  const char* nombre;
  uint8_t v[NUM_DEDOS];
};

const Gesto GESTOS[] = {
  {"ABIERTA",   {100, 100, 100, 100, 100}},
  {"PUNO",      {  0,   0,   0,   0,   0}},
  {"PAZ",       {  0, 100, 100,   0,   0}},
  {"ROCK",      {100, 100,   0,   0, 100}},
  {"OK",        { 20,  20, 100, 100, 100}},
  {"APUNTAR",   {  0, 100,   0,   0,   0}},
  {"PULGAR",    {100,   0,   0,   0,   0}},
  {"PISTOLA",   {100, 100,   0,   0,   0}},
  {"TELEFONO",  {100,   0,   0,   0, 100}},
  {"PINZA",     { 35,  35, 100, 100, 100}},
  {"RELAJADA",  { 70,  60,  55,  50,  50}},
};
const uint8_t NUM_GESTOS = sizeof(GESTOS) / sizeof(GESTOS[0]);

// Secuencia de demostración: índice de gesto (o 255 = "ola") y duración
struct PasoDemo {
  uint8_t gesto;
  uint16_t ms;
};
const PasoDemo DEMO[] = {
  {0, 1200}, {1, 1200}, {255, 1500}, {0, 800},
  {5, 900}, {2, 900}, {7, 900}, {3, 1200},
  {4, 1200}, {6, 1200}, {8, 1200}, {9, 1200}, {1, 1000},
};
const uint8_t NUM_PASOS_DEMO = sizeof(DEMO) / sizeof(DEMO[0]);

// ==========================================
// 3. INSTANCIAS Y VARIABLES GLOBALES
// ==========================================
Adafruit_PWMServoDriver pcaDriver = Adafruit_PWMServoDriver(PCA_I2C_ADDR);
Preferences prefs;
WebServer servidor(80);
WiFiUDP udp;

enum SistemaModo {
  MODO_STREAMING,      // Recibe tramas de Python (USB o UDP)
  MODO_MANUAL,         // Gestos / sliders / comandos, sin timeout
  MODO_DEMO,
  MODO_FAILSAFE,
  MODO_RELAJADO        // PWM apagado, servos sin fuerza
};
const char* NOMBRES_MODO[] = {"STREAMING", "MANUAL", "DEMO", "FAILSAFE", "RELAJADO"};

SistemaModo modoActual = MODO_MANUAL;
const char* fuenteActual = "NINGUNA";

unsigned long ultimoTickCinematica = 0;
unsigned long ultimaTramaRecibida = 0;
unsigned long inicioDemo = 0;
bool tramaRecibida = false;
bool pcaDetectado = false;
uint8_t velocidadPct = 60;     // 1..100
float velocidadFailsafe = 0;   // > 0 fuerza velocidad lenta en failsafe

char bufferSerial[96];
uint8_t indiceBuffer = 0;

// Print que acumula texto (para responder por UDP y web)
class BufferPrint : public Print {
 public:
  String texto;
  size_t write(uint8_t c) override { texto += (char)c; return 1; }
};

// ==========================================
// 4. CINEMÁTICA
// ==========================================
uint16_t normalizadoATicksPCA(uint8_t i, float valorNorm) {
  valorNorm = constrain(valorNorm, 0.0f, 1.0f);
  return (uint16_t)(mano[i].pulsoCerrado +
                    valorNorm * ((int)mano[i].pulsoAbierto - (int)mano[i].pulsoCerrado));
}

// Recorrido completo por segundo según la velocidad configurada
float pasoMaximoPorTick() {
  float recorridoPorSeg = (velocidadFailsafe > 0) ? velocidadFailsafe
                                                  : 0.5f + (velocidadPct / 100.0f) * 7.5f;
  return recorridoPorSeg / LOOP_TICK_RATE_HZ;
}

void actualizarMotoresFisicos() {
  if (modoActual == MODO_RELAJADO || !pcaDetectado) return;
  float pasoMax = pasoMaximoPorTick();
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    float error = mano[i].posObjetivo - mano[i].posActual;
    if (fabs(error) < 0.003f) {
      mano[i].posActual = mano[i].posObjetivo;
    } else {
      // Suavizado exponencial con límite de velocidad (evita picos de corriente)
      float paso = constrain(error * 0.35f, -pasoMax, pasoMax);
      mano[i].posActual += paso;
    }
    pcaDriver.setPWM(mano[i].canalPCA, 0, normalizadoATicksPCA(i, mano[i].posActual));
  }
}

void fijarObjetivos(const uint8_t v[NUM_DEDOS]) {
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    mano[i].posObjetivo = constrain(v[i], 0, 100) / 100.0f;
  }
}

void fijarTodos(float valor) {
  for (uint8_t i = 0; i < NUM_DEDOS; i++) mano[i].posObjetivo = valor;
}

void cambiarModo(SistemaModo nuevo) {
  if (modoActual == MODO_RELAJADO && nuevo != MODO_RELAJADO) {
    // Al salir de RELAJADO, partir de la posición objetivo para no dar tirones
    for (uint8_t i = 0; i < NUM_DEDOS; i++) mano[i].posActual = mano[i].posObjetivo;
  }
  if (nuevo != MODO_FAILSAFE) velocidadFailsafe = 0;
  modoActual = nuevo;
}

int buscarGesto(const char* nombre) {
  for (uint8_t g = 0; g < NUM_GESTOS; g++) {
    if (strcasecmp(nombre, GESTOS[g].nombre) == 0) return g;
  }
  return -1;
}

// ==========================================
// 5. MODOS DE COMPORTAMIENTO
// ==========================================
void ejecutarSecuenciaDemo() {
  unsigned long total = 0;
  for (uint8_t p = 0; p < NUM_PASOS_DEMO; p++) total += DEMO[p].ms;
  unsigned long t = (millis() - inicioDemo) % total;

  for (uint8_t p = 0; p < NUM_PASOS_DEMO; p++) {
    if (t < DEMO[p].ms) {
      if (DEMO[p].gesto == 255) {
        // Ola: un dedo cerrado que recorre la mano
        uint8_t dedoOla = (t / (DEMO[p].ms / NUM_DEDOS)) % NUM_DEDOS;
        for (uint8_t i = 0; i < NUM_DEDOS; i++) {
          mano[i].posObjetivo = (i == dedoOla) ? 0.0f : 1.0f;
        }
      } else {
        fijarObjetivos(GESTOS[DEMO[p].gesto].v);
      }
      return;
    }
    t -= DEMO[p].ms;
  }
}

void activarFailsafe() {
  if (modoActual == MODO_FAILSAFE) return;
  cambiarModo(MODO_FAILSAFE);
  velocidadFailsafe = 0.6f;   // apertura lenta
  fijarTodos(1.0f);
  Serial.println(F("[FAILSAFE] Sin datos (>1.5s). Mano en reposo (abierta)."));
}

// ==========================================
// 6. PERSISTENCIA (calibración en flash)
// ==========================================
void guardarConfig() {
  prefs.begin("mano", false);
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    char k[4];
    snprintf(k, sizeof(k), "a%u", i); prefs.putUShort(k, mano[i].pulsoAbierto);
    snprintf(k, sizeof(k), "c%u", i); prefs.putUShort(k, mano[i].pulsoCerrado);
  }
  prefs.putUChar("vel", velocidadPct);
  prefs.end();
}

void cargarConfig() {
  prefs.begin("mano", true);
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    char k[4];
    snprintf(k, sizeof(k), "a%u", i); mano[i].pulsoAbierto = prefs.getUShort(k, DEF_ABIERTO[i]);
    snprintf(k, sizeof(k), "c%u", i); mano[i].pulsoCerrado = prefs.getUShort(k, DEF_CERRADO[i]);
  }
  velocidadPct = prefs.getUChar("vel", 60);
  prefs.end();
}

void configPorDefecto() {
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    mano[i].pulsoAbierto = DEF_ABIERTO[i];
    mano[i].pulsoCerrado = DEF_CERRADO[i];
  }
  velocidadPct = 60;
}

// ==========================================
// 7. PARSER DE TRAMAS Y COMANDOS
// ==========================================
// Devuelve true si la línea era una trama de posición válida
bool procesarTramaStreaming(char* trama, const char* fuente) {
  bool proporcional = false;
  if ((trama[0] == 'P' || trama[0] == 'p') && trama[1] == ':') {
    proporcional = true;
    trama += 2;
  }

  int v[NUM_DEDOS];
  if (sscanf(trama, "%d,%d,%d,%d,%d", &v[0], &v[1], &v[2], &v[3], &v[4]) != NUM_DEDOS) {
    return false;
  }

  ultimaTramaRecibida = millis();
  tramaRecibida = true;
  fuenteActual = fuente;
  if (modoActual != MODO_STREAMING) cambiarModo(MODO_STREAMING);

  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    int pct = proporcional ? v[i] : (v[i] ? 100 : 0);
    mano[i].posObjetivo = constrain(pct, 0, 100) / 100.0f;
  }
  return true;
}

void imprimirEstado(Print& out) {
  out.printf("\n--- MANO BIONICA ESP32-S3 ---\nModo: %s | Fuente: %s | Velocidad: %u%%\n",
             NOMBRES_MODO[modoActual], fuenteActual, velocidadPct);
  out.printf("PCA9685: %s | WiFi: %s\n", pcaDetectado ? "OK" : "NO DETECTADO",
             WiFi.getMode() == WIFI_AP ? WiFi.softAPIP().toString().c_str()
                                       : WiFi.localIP().toString().c_str());
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    out.printf("[%u] %-8s CH%-2u abierto=%3u cerrado=%3u  actual=%3d%% objetivo=%3d%%\n",
               i, mano[i].nombre, mano[i].canalPCA, mano[i].pulsoAbierto, mano[i].pulsoCerrado,
               (int)(mano[i].posActual * 100), (int)(mano[i].posObjetivo * 100));
  }
  out.println(F("-----------------------------"));
}

void imprimirAyuda(Print& out) {
  out.println(F("\nTRAMAS:   P:a,b,c,d,e (0-100 % abierto) | a,b,c,d,e (binario 1/0)"));
  out.println(F("COMANDOS: HELP, STATUS, PING, OPEN, CLOSE, DEMO, STOP, RELAX"));
  out.println(F("          GESTO <nombre>, GESTOS, SET <dedo> <0-100>, SPEED <1-100>"));
  out.println(F("CALIBRAR: PULSO <dedo> <ticks>  (mueve el servo a un pulso crudo)"));
  out.println(F("          CAL <dedo> <abierto> <cerrado>, INV <dedo>"));
  out.println(F("          SAVE, LOAD, DEFAULTS   (dedo: 0=pulgar ... 4=menique)\n"));
}

void procesarComandoTexto(char* cmd, Print& out) {
  while (*cmd == ' ') cmd++;
  char palabra[16] = {0};
  int a = -1, b = -1, c = -1;
  char argTexto[16] = {0};
  sscanf(cmd, "%15s", palabra);
  const char* resto = cmd + strlen(palabra);
  sscanf(resto, "%d %d %d", &a, &b, &c);
  sscanf(resto, "%15s", argTexto);

  if (!strcasecmp(palabra, "HELP") || !strcmp(palabra, "?")) {
    imprimirAyuda(out);
  } else if (!strcasecmp(palabra, "STATUS")) {
    imprimirEstado(out);
  } else if (!strcasecmp(palabra, "PING")) {
    out.println(F("PONG MANO-ESP32S3"));
  } else if (!strcasecmp(palabra, "OPEN") || !strcasecmp(palabra, "ABRIR")) {
    cambiarModo(MODO_MANUAL); fijarTodos(1.0f);
    out.println(F("[ACCION] Mano abierta."));
  } else if (!strcasecmp(palabra, "CLOSE") || !strcasecmp(palabra, "CERRAR")) {
    cambiarModo(MODO_MANUAL); fijarTodos(0.0f);
    out.println(F("[ACCION] Mano cerrada."));
  } else if (!strcasecmp(palabra, "DEMO") || !strcasecmp(palabra, "SWEEP")) {
    cambiarModo(MODO_DEMO); inicioDemo = millis();
    out.println(F("[MODO] Demo iniciada (STOP para salir)."));
  } else if (!strcasecmp(palabra, "STOP") || !strcasecmp(palabra, "STREAM")) {
    cambiarModo(MODO_MANUAL); tramaRecibida = false;
    out.println(F("[MODO] Manual. Las tramas de Python activan el streaming."));
  } else if (!strcasecmp(palabra, "RELAX")) {
    cambiarModo(MODO_RELAJADO);
    for (uint8_t i = 0; i < NUM_DEDOS; i++) pcaDriver.setPWM(mano[i].canalPCA, 0, 4096);
    out.println(F("[ACCION] Servos relajados (sin fuerza)."));
  } else if (!strcasecmp(palabra, "GESTOS")) {
    out.print(F("Gestos:"));
    for (uint8_t g = 0; g < NUM_GESTOS; g++) { out.print(' '); out.print(GESTOS[g].nombre); }
    out.println();
  } else if (!strcasecmp(palabra, "GESTO")) {
    int g = buscarGesto(argTexto);
    if (g < 0) { out.println(F("[ERROR] Gesto desconocido (ver GESTOS).")); return; }
    cambiarModo(MODO_MANUAL); fijarObjetivos(GESTOS[g].v);
    out.printf("[GESTO] %s\n", GESTOS[g].nombre);
  } else if (!strcasecmp(palabra, "SET")) {
    if (a < 0 || a >= NUM_DEDOS || b < 0) { out.println(F("[ERROR] SET <dedo> <0-100>")); return; }
    if (modoActual != MODO_MANUAL) cambiarModo(MODO_MANUAL);
    mano[a].posObjetivo = constrain(b, 0, 100) / 100.0f;
    out.printf("[SET] %s = %d%%\n", mano[a].nombre, constrain(b, 0, 100));
  } else if (!strcasecmp(palabra, "SPEED")) {
    if (a < 1 || a > 100) { out.println(F("[ERROR] SPEED <1-100>")); return; }
    velocidadPct = a;
    out.printf("[VELOCIDAD] %u%%\n", velocidadPct);
  } else if (!strcasecmp(palabra, "PULSO")) {
    if (a < 0 || a >= NUM_DEDOS || b < PCA_TICKS_MIN || b > PCA_TICKS_MAX) {
      out.printf("[ERROR] PULSO <dedo> <%d-%d>\n", PCA_TICKS_MIN, PCA_TICKS_MAX); return;
    }
    cambiarModo(MODO_RELAJADO);   // detiene la cinemática mientras se calibra
    pcaDriver.setPWM(mano[a].canalPCA, 0, b);
    out.printf("[CALIB] %s -> %d ticks (usa CAL para guardar los extremos)\n", mano[a].nombre, b);
  } else if (!strcasecmp(palabra, "CAL")) {
    if (a < 0 || a >= NUM_DEDOS || b < PCA_TICKS_MIN || b > PCA_TICKS_MAX ||
        c < PCA_TICKS_MIN || c > PCA_TICKS_MAX) {
      out.printf("[ERROR] CAL <dedo> <abierto> <cerrado>  (%d-%d)\n", PCA_TICKS_MIN, PCA_TICKS_MAX);
      return;
    }
    mano[a].pulsoAbierto = b; mano[a].pulsoCerrado = c;
    out.printf("[CALIB] %s abierto=%d cerrado=%d (SAVE para guardar)\n", mano[a].nombre, b, c);
  } else if (!strcasecmp(palabra, "INV")) {
    if (a < 0 || a >= NUM_DEDOS) { out.println(F("[ERROR] INV <dedo>")); return; }
    uint16_t t = mano[a].pulsoAbierto;
    mano[a].pulsoAbierto = mano[a].pulsoCerrado; mano[a].pulsoCerrado = t;
    out.printf("[CALIB] %s invertido (SAVE para guardar)\n", mano[a].nombre);
  } else if (!strcasecmp(palabra, "SAVE")) {
    guardarConfig(); out.println(F("[SISTEMA] Calibración guardada en flash."));
  } else if (!strcasecmp(palabra, "LOAD")) {
    cargarConfig(); out.println(F("[SISTEMA] Calibración cargada."));
  } else if (!strcasecmp(palabra, "DEFAULTS")) {
    configPorDefecto(); out.println(F("[SISTEMA] Valores por defecto (SAVE para guardar)."));
  } else {
    out.printf("[ERROR] Comando desconocido: '%s' (HELP)\n", palabra);
  }
}

void procesarLinea(char* linea, const char* fuente, Print& out) {
  // Quitar espacios/CR finales
  size_t n = strlen(linea);
  while (n > 0 && (linea[n - 1] == ' ' || linea[n - 1] == '\r')) linea[--n] = '\0';
  if (n == 0) return;

  if (strchr(linea, ',') != NULL) {
    if (!procesarTramaStreaming(linea, fuente)) out.println(F("[ERROR] Trama inválida."));
  } else {
    procesarComandoTexto(linea, out);
  }
}

// ==========================================
// 8. COMUNICACIONES: USB, UDP Y WEB
// ==========================================
void atenderPuertoSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (indiceBuffer > 0) {
        bufferSerial[indiceBuffer] = '\0';
        procesarLinea(bufferSerial, "USB", Serial);
        indiceBuffer = 0;
      }
    } else if (indiceBuffer < sizeof(bufferSerial) - 1) {
      bufferSerial[indiceBuffer++] = c;
    }
  }
}

void atenderUDP() {
  int tam = udp.parsePacket();
  while (tam > 0) {
    char paquete[256];
    int len = udp.read(paquete, sizeof(paquete) - 1);
    paquete[max(len, 0)] = '\0';

    BufferPrint respuesta;
    char* guardado = nullptr;
    for (char* linea = strtok_r(paquete, "\n", &guardado); linea;
         linea = strtok_r(nullptr, "\n", &guardado)) {
      procesarLinea(linea, "WIFI-UDP", respuesta);
    }
    if (respuesta.texto.length() > 0) {
      udp.beginPacket(udp.remoteIP(), udp.remotePort());
      udp.print(respuesta.texto);
      udp.endPacket();
    }
    tam = udp.parsePacket();
  }
}

void webRaiz() {
  servidor.send_P(200, "text/html; charset=utf-8", PAGINA_WEB);
}

void webEstado() {
  String json = "{\"modo\":\"";
  json += NOMBRES_MODO[modoActual];
  json += "\",\"fuente\":\"";
  json += fuenteActual;
  json += "\",\"vel\":";
  json += velocidadPct;
  json += ",\"pca\":";
  json += pcaDetectado ? "true" : "false";
  json += ",\"dedos\":[";
  for (uint8_t i = 0; i < NUM_DEDOS; i++) {
    if (i) json += ',';
    json += "{\"n\":\""; json += mano[i].nombre;
    json += "\",\"pos\":"; json += (int)(mano[i].posActual * 100);
    json += ",\"obj\":"; json += (int)(mano[i].posObjetivo * 100);
    json += ",\"a\":"; json += mano[i].pulsoAbierto;
    json += ",\"c\":"; json += mano[i].pulsoCerrado;
    json += '}';
  }
  json += "],\"gestos\":[";
  for (uint8_t g = 0; g < NUM_GESTOS; g++) {
    if (g) json += ',';
    json += '"'; json += GESTOS[g].nombre; json += '"';
  }
  json += "]}";
  servidor.send(200, "application/json", json);
}

void webComando() {
  if (!servidor.hasArg("c")) { servidor.send(400, "text/plain", "Falta ?c="); return; }
  String c = servidor.arg("c");
  char linea[96];
  c.toCharArray(linea, sizeof(linea));
  BufferPrint respuesta;
  procesarLinea(linea, "WEB", respuesta);
  servidor.send(200, "text/plain; charset=utf-8", respuesta.texto);
}

void iniciarWiFi() {
  bool conectado = false;
  if (strlen(WIFI_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.printf("[WIFI] Conectando a %s", WIFI_SSID);
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) { delay(250); Serial.print('.'); }
    Serial.println();
    conectado = WiFi.status() == WL_CONNECTED;
    if (conectado) Serial.printf("[WIFI] Conectado. IP: %s\n", WiFi.localIP().toString().c_str());
  }
  if (!conectado) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);
    Serial.printf("[WIFI] Punto de acceso '%s' (clave '%s'). IP: %s\n",
                  AP_SSID, AP_PASS, WiFi.softAPIP().toString().c_str());
  }
  WiFi.setSleep(false);   // menor latencia para el streaming UDP

  if (MDNS.begin(NOMBRE_MDNS)) MDNS.addService("http", "tcp", 80);

  servidor.on("/", webRaiz);
  servidor.on("/api/estado", webEstado);
  servidor.on("/api/cmd", webComando);
  servidor.begin();
  udp.begin(PUERTO_UDP);
  Serial.printf("[WIFI] Panel web: http://%s.local  |  UDP puerto %d\n", NOMBRE_MDNS, PUERTO_UDP);
}

// ==========================================
// 9. LED DE ESTADO (RGB integrado, si existe)
// ==========================================
void actualizarLED() {
#ifdef RGB_BUILTIN
  static unsigned long ultimo = 0;
  if (millis() - ultimo < 100) return;
  ultimo = millis();
  uint8_t r = 0, g = 0, b = 0;
  if (!pcaDetectado)                      { r = (millis() / 250) % 2 ? 40 : 0; }
  else if (modoActual == MODO_STREAMING)  { g = 30; }
  else if (modoActual == MODO_MANUAL)     { b = 30; }
  else if (modoActual == MODO_DEMO)       { r = 20; b = 30; }
  else if (modoActual == MODO_FAILSAFE)   { r = 40; g = 15; }
  else                                    { r = 5; g = 5; b = 5; }
  neopixelWrite(RGB_BUILTIN, r, g, b);
#endif
}

// ==========================================
// 10. SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 1500) delay(10);   // no bloquear sin PC

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  Wire.beginTransmission(PCA_I2C_ADDR);
  pcaDetectado = (Wire.endTransmission() == 0);

  cargarConfig();

  if (pcaDetectado) {
    pcaDriver.begin();
    pcaDriver.setOscillatorFrequency(27000000);
    pcaDriver.setPWMFreq(FRECUENCIA_PWM);
    delay(20);
    // Encendido escalonado de servos para no saturar la fuente
    for (uint8_t i = 0; i < NUM_DEDOS; i++) {
      pcaDriver.setPWM(mano[i].canalPCA, 0, normalizadoATicksPCA(i, mano[i].posActual));
      delay(80);
    }
  } else {
    Serial.println(F("[ERROR] PCA9685 no detectado en 0x40. Revisa SDA=8, SCL=9, VCC y GND."));
  }

  iniciarWiFi();
  Serial.println(F("[SISTEMA] Mano Biónica ESP32-S3 lista. Escribe HELP."));
}

// ==========================================
// 11. LOOP
// ==========================================
void loop() {
  unsigned long ahora = millis();

  atenderPuertoSerial();
  atenderUDP();
  servidor.handleClient();

  if (ahora - ultimoTickCinematica >= (1000 / LOOP_TICK_RATE_HZ)) {
    ultimoTickCinematica = ahora;

    if (modoActual == MODO_DEMO) {
      ejecutarSecuenciaDemo();
    } else if (modoActual == MODO_STREAMING && tramaRecibida &&
               ahora - ultimaTramaRecibida > SERIAL_TIMEOUT_MS) {
      activarFailsafe();
    }
    actualizarMotoresFisicos();
  }
  actualizarLED();
}
