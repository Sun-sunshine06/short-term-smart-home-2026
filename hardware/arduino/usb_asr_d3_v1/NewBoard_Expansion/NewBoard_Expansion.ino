/*
 * NEW / EXPANSION Arduino UNO R3 -- paired revision 2026-11-17
 * ONE moved wire: ASRPRO PA_2/TX -> D3 (formerly D0).
 * USB hardware Serial is now 115200; ASR D3 stays 9600 8N1.
 * D10 -> OLD D5, common GND and all other external wires unchanged.
 * Rain AO A0; soil AO A1; touch D2; ultrasonic TRIG D8 / ECHO D9.
 * Keep HomeLink.h next to this .ino and update BOTH boards together.
 * Keep ALL three .h files next to this .ino. No SoftwareSerial library.
 */
#include <Arduino.h>
#include <string.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include "HomeLink.h"
#include "AsrD3Rx.h"
#include "CommandInput.h"

#if !defined(__AVR_ATmega328P__) && !defined(HOME_HOST_TEST)
#error "Select Arduino Uno (ATmega328P). D9 echo uses the UNO R3 pin-change interrupt."
#endif

#define OLD_BOARD_SIGNAL_PIN 10
#define STATUS_LED_PIN 13
#define TOUCH_PIN 2
#define ULTRASONIC_TRIG_PIN 8
#define ULTRASONIC_ECHO_PIN 9
#define RAIN_AO_PIN A0
#define SOIL_AO_PIN A1

const uint32_t USB_BAUD = 115200;
const uint32_t COMMAND_IDLE_MS = 40;
const uint32_t USB_PARTIAL_TIMEOUT_MS = 1000;
const uint32_t FACE_COOLDOWN_MS = 10000;
const uint32_t SENSOR_INTERVAL_MS = 250;
const uint32_t SENSOR_REFRESH_MS = 5000;
const uint32_t TOUCH_DEBOUNCE_MS = 25;
const uint32_t TOUCH_COOLDOWN_MS = 600;
const uint32_t ULTRASONIC_INTERVAL_MS = 200;
const uint32_t ULTRASONIC_TIMEOUT_US = 30000;
// Original calibration endpoints; adjust only if actual raw readings require it.
const int RAIN_DRY_RAW = 900, RAIN_WET_RAW = 300;
const int SOIL_DRY_RAW = 850, SOIL_WET_RAW = 300;
const int RAIN_ALERT_PERCENT = 45;
const int SOIL_DRY_PERCENT = 35;
const int PERSON_NEAR_TENTHS_CM = 200;

HomeLink::Transmitter linkTx;
byte nextSequence = 0;
byte commandQueue[8], commandHead = 0, commandTail = 0;
bool rainNeedsSend = false, soilNeedsSend = false, haveSamples = false;
bool preferSoilReport = false;
int rainRaw = 0, rainPercent = 0, soilRaw = 0, soilPercent = 0;
bool rainDetected = false, soilDry = false, personNear = false;
int distanceTenthsCm = -1;
uint32_t lastSensorAt = 0, lastRefreshAt = 0, lastTelemetryAt = 0;

CommandInput asrInput, usbInput;
bool faceTriggered = false;
uint32_t lastFaceAt = 0;
byte sendingId = 0, sendingSequence = 0;

// A bounded software output queue prevents long Serial.print lines from
// stretching link pulses or blocking incoming ASR commands at 9600 baud.
char serialOutput[256];
byte serialHead = 0, serialTail = 0;
byte ledFlashesLeft = 0;
bool ledOn = false;
uint32_t ledAt = 0;

volatile byte echoPhase = 0;  // 0 idle, 1 waiting rise, 2 waiting fall, 3 ready.
volatile uint32_t echoRiseAt = 0, echoDurationUs = 0;
uint32_t echoStartedAt = 0, lastUltrasonicAt = 0;

ISR(PCINT0_vect) {
  const uint32_t now = micros();
  const bool high = (PINB & _BV(PB1)) != 0;  // UNO D9.
  if (echoPhase == 1 && high) { echoRiseAt = now; echoPhase = 2; }
  else if (echoPhase == 2 && !high) {
    echoDurationUs = now - echoRiseAt;
    echoPhase = 3;
  }
}

bool queueText(const char *text) {
  const size_t length = strlen(text);
  const byte freeBytes = byte(serialTail - serialHead - 1);
  if (length > freeBytes) return false;  // Logging never delays a command.
  for (size_t i = 0; i < length; ++i) serialOutput[serialHead++] = text[i];
  return true;
}

void serviceSerialOutput() {
  byte budget = 8;
  while (budget-- && serialTail != serialHead && Serial.availableForWrite() > 0)
    Serial.write(uint8_t(serialOutput[serialTail++]));
}

void blinkStatus(byte count) {
  ledFlashesLeft = constrain(count, 1, 7);
  ledOn = true;
  ledAt = millis();
  digitalWrite(STATUS_LED_PIN, HIGH);
}

void serviceStatusLed() {
  if (!ledFlashesLeft || millis() - ledAt < 70) return;
  ledAt = millis();
  if (ledOn) { ledOn = false; --ledFlashesLeft; }
  else ledOn = true;
  digitalWrite(STATUS_LED_PIN, ledOn ? HIGH : LOW);
}

byte commandToId(const char *cmd) {
  if (!strcmp(cmd, "DO") || !strcmp(cmd, "DOOR_OPEN") || !strcmp(cmd, "OPEN")) return 1;
  if (!strcmp(cmd, "DC") || !strcmp(cmd, "DOOR_CLOSE") || !strcmp(cmd, "CLOSE")) return 2;
  if (!strcmp(cmd, "FO") || !strcmp(cmd, "FAN_ON")) return 3;
  if (!strcmp(cmd, "FC") || !strcmp(cmd, "FAN_OFF")) return 4;
  if (!strcmp(cmd, "LO") || !strcmp(cmd, "LIGHT_ON") || !strcmp(cmd, "LED_ON")) return 5;
  if (!strcmp(cmd, "LC") || !strcmp(cmd, "LIGHT_OFF") || !strcmp(cmd, "LED_OFF")) return 6;
  if (!strcmp(cmd, "BELL") || !strcmp(cmd, "DB") || !strcmp(cmd, "DOORBELL")) return 7;
  if (!strcmp(cmd, "FA") || !strcmp(cmd, "FAN_AUTO")) return 13;
  if (!strcmp(cmd, "LA") || !strcmp(cmd, "LIGHT_AUTO")) return 14;
  if (!strcmp(cmd, "AUTO") || !strcmp(cmd, "ALL_AUTO")) return 15;
  return 0;
}

bool enqueueCommand(byte id) {
  const byte next = (commandHead + 1) & 7;
  if (next == commandTail) return false;
  commandQueue[commandHead] = id;
  commandHead = next;
  return true;
}

void finishCommand(CommandInput &input, bool fromUsb) {
  if (!input.length && !input.overflow) return;
  input.text[input.length] = '\0';
  if (fromUsb && !input.overflow && !strcmp(input.text, "PING")) {
    queueText("PONG,USB_ASR_D3_V1\r\n"); input.reset(); return;
  }
  const bool face = fromUsb && !input.overflow && !strcmp(input.text, "FACE_OPEN");
  if (face && faceTriggered && millis() - lastFaceAt < FACE_COOLDOWN_MS) {
    queueText("USB_CMD:FACE_OPEN,COOLDOWN\r\n"); input.reset(); return;
  }
  const byte id = input.overflow ? 0 : face ? 1 : commandToId(input.text);
  char line[80];
  if (id && enqueueCommand(id)) {
    if (face) { faceTriggered = true; lastFaceAt = millis(); }
    snprintf_P(line, sizeof(line), PSTR("%s_CMD:%s,ID:%u,QUEUED\r\n"),
      fromUsb ? "USB" : "ASR", input.text, id);
    blinkStatus(id);
  } else {
    snprintf_P(line, sizeof(line), PSTR("%s_%s:%s\r\n"),
      fromUsb ? "USB" : "ASR", id ? "BUSY" : "UNKNOWN", input.text);
    blinkStatus(3);
  }
  queueText(line);
  input.reset();
}

void acceptCommandByte(CommandInput &input, char ch, bool fromUsb) {
  input.lastByteAt = millis();
  if (ch == '\r' || ch == '\n' || ch == ';') { finishCommand(input, fromUsb); return; }
  if (ch == ' ' || ch == '\t') return;
  if (ch >= 'a' && ch <= 'z') ch = char(ch - 'a' + 'A');
  if (ch < 32 || ch > 126) { input.overflow = true; return; }
  if (input.length < sizeof(input.text) - 1 && !input.overflow) input.text[input.length++] = ch;
  else input.overflow = true;
}

void handleAsrproSerial() {
  const byte errors = AsrD3Rx::takeErrors();
  if (errors) {
    asrInput.reset(); asrInput.overflow = true; asrInput.lastByteAt = millis();
    queueText("ASR_RX_ERROR,COMMAND_DISCARDED\r\n");
  }
  byte budget = 24;
  while (budget-- && AsrD3Rx::available()) acceptCommandByte(asrInput, char(AsrD3Rx::read()), false);
  if (!AsrD3Rx::available() && millis() - asrInput.lastByteAt >= COMMAND_IDLE_MS)
    finishCommand(asrInput, false);
}

void handleUsbSerial() {
  // USB commands MUST have CR/LF or ';'. A fragmented network/USB message
  // must not turn a prefix into an action merely because the sender paused.
  if (usbInput.length && millis() - usbInput.lastByteAt >= USB_PARTIAL_TIMEOUT_MS) {
    usbInput.reset();
    // Ignore the remainder until a delimiter, even if a suffix is a valid token.
    usbInput.overflow = true;
    usbInput.lastByteAt = millis();
    queueText("USB_TIMEOUT,COMMAND_DISCARDED\r\n");
  }
  byte budget = 24;
  while (budget-- && Serial.available() > 0) acceptCommandByte(usbInput, char(Serial.read()), true);
}

void serviceLinkTx() {
  uint32_t now = micros();
  if (linkTx.update(now)) digitalWrite(OLD_BOARD_SIGNAL_PIN, linkTx.level() ? HIGH : LOW);
  if (linkTx.active()) return;
  if (sendingId) {
    char line[64];
    snprintf_P(line, sizeof(line), PSTR("LINK_TX:ID:%u,SEQ:%u,SENT_NO_ACK\r\n"), sendingId, sendingSequence);
    queueText(line); sendingId = 0;
  }
  byte id = 0, copies = 1;
  // User commands take priority over coalesced periodic sensor reports.
  if (commandTail != commandHead) {
    id = commandQueue[commandTail]; commandTail = (commandTail + 1) & 7;
    copies = 2;
  } else if (rainNeedsSend || soilNeedsSend) {
    if (soilNeedsSend && (!rainNeedsSend || preferSoilReport)) {
      id = soilDry ? 11 : 12; soilNeedsSend = false; preferSoilReport = false;
    } else {
      id = rainDetected ? 10 : 9; rainNeedsSend = false; preferSoilReport = true;
    }
  }
  const byte sequence = nextSequence;
  if (id && linkTx.start(id, sequence, copies, now)) {
    ++nextSequence; sendingId = id; sendingSequence = sequence;
    digitalWrite(OLD_BOARD_SIGNAL_PIN, HIGH);
  }
}

int percentFromRaw(int raw, int dryRaw, int wetRaw) {
  if (dryRaw == wetRaw) return 0;
  raw = constrain(raw, min(dryRaw, wetRaw), max(dryRaw, wetRaw));
  return constrain(int(map(raw, dryRaw, wetRaw, 0, 100)), 0, 100);
}

void serviceSensors() {
  const uint32_t now = millis();
  if (now - lastSensorAt >= SENSOR_INTERVAL_MS) {
    lastSensorAt = now;
    rainRaw = analogRead(RAIN_AO_PIN); soilRaw = analogRead(SOIL_AO_PIN);
    rainPercent = percentFromRaw(rainRaw, RAIN_DRY_RAW, RAIN_WET_RAW);
    soilPercent = percentFromRaw(soilRaw, SOIL_DRY_RAW, SOIL_WET_RAW);
    bool nextRain = rainDetected, nextSoil = soilDry;
    if (!haveSamples) {
      nextRain = rainPercent >= RAIN_ALERT_PERCENT;
      nextSoil = soilPercent <= SOIL_DRY_PERCENT;
    } else {
      if (rainPercent >= RAIN_ALERT_PERCENT) nextRain = true;
      else if (rainPercent <= RAIN_ALERT_PERCENT - 5) nextRain = false;
      if (soilPercent <= SOIL_DRY_PERCENT) nextSoil = true;
      else if (soilPercent >= SOIL_DRY_PERCENT + 5) nextSoil = false;
    }
    if (!haveSamples || nextRain != rainDetected) rainNeedsSend = true;
    if (!haveSamples || nextSoil != soilDry) soilNeedsSend = true;
    rainDetected = nextRain; soilDry = nextSoil; haveSamples = true;
  }
  if (haveSamples && now - lastRefreshAt >= SENSOR_REFRESH_MS) {
    lastRefreshAt = now; rainNeedsSend = soilNeedsSend = true;
  }
}

void serviceUltrasonic() {
  const uint32_t now = micros();
  bool ready = false;
  uint32_t duration = 0;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    if (echoPhase == 3) { duration = echoDurationUs; echoPhase = 0; ready = true; }
    else if (echoPhase != 0 && now - echoStartedAt >= ULTRASONIC_TIMEOUT_US) {
      echoPhase = 0; ready = true;
    }
  }
  if (ready) {
    distanceTenthsCm = (duration > 0 && duration <= ULTRASONIC_TIMEOUT_US) ? int(duration * 10UL / 58UL) : -1;
    personNear = distanceTenthsCm > 0 && distanceTenthsCm <= PERSON_NEAR_TENTHS_CM;
  }
  if (echoPhase == 0 && millis() - lastUltrasonicAt >= ULTRASONIC_INTERVAL_MS) {
    lastUltrasonicAt = millis();
    echoStartedAt = now;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { echoPhase = 1; }
    digitalWrite(ULTRASONIC_TRIG_PIN, LOW); delayMicroseconds(2);
    digitalWrite(ULTRASONIC_TRIG_PIN, HIGH); delayMicroseconds(10);
    digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  }
}

void handleTouchDoorbell() {
  static bool candidate = false, stable = false, haveTouch = false;
  static uint32_t changedAt = 0, lastTouchAt = 0;
  const bool pressed = digitalRead(TOUCH_PIN) == HIGH;
  const uint32_t now = millis();
  if (pressed != candidate) { candidate = pressed; changedAt = now; }
  if (now - changedAt < TOUCH_DEBOUNCE_MS || candidate == stable) return;
  stable = candidate;
  if (stable && (!haveTouch || now - lastTouchAt >= TOUCH_COOLDOWN_MS)) {
    haveTouch = true; lastTouchAt = now;
    // Keep original behavior: TOUCH rings the bell; it does not open the door.
    if (enqueueCommand(7)) { queueText("TOUCH_DOORBELL,QUEUED\r\n"); blinkStatus(7); }
    else queueText("TOUCH_DOORBELL,BUSY\r\n");
  }
}

void serviceTelemetry() {
  if (!haveSamples || millis() - lastTelemetryAt < 1000) return;
  lastTelemetryAt = millis();
  char distance[16], line[190];
  if (distanceTenthsCm < 0) strcpy(distance, "NO_ECHO");
  else snprintf_P(distance, sizeof(distance), PSTR("%d.%dcm"), distanceTenthsCm / 10, distanceTenthsCm % 10);
  snprintf_P(line, sizeof(line),
    PSTR("RAIN_RAW:%d,RAIN:%d%%,RAIN_STATE:%s,SOIL_RAW:%d,SOIL:%d%%,SOIL_STATE:%s,DIST:%s,NEAR:%s\r\n"),
    rainRaw, rainPercent, rainDetected ? "WET" : "DRY", soilRaw, soilPercent,
    soilDry ? "DRY" : "OK", distance, personNear ? "YES" : "NO");
  queueText(line);
}

void setup() {
  pinMode(OLD_BOARD_SIGNAL_PIN, OUTPUT); digitalWrite(OLD_BOARD_SIGNAL_PIN, LOW);
  pinMode(STATUS_LED_PIN, OUTPUT); digitalWrite(STATUS_LED_PIN, LOW);
  pinMode(TOUCH_PIN, INPUT);
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT); digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  PCIFR = _BV(PCIF0); PCMSK0 |= _BV(PCINT1); PCICR |= _BV(PCIE0);
  Serial.begin(USB_BAUD);
  AsrD3Rx::begin();
  queueText("USB_ASR_D3_V1_READY,USB:115200,ASR:9600\r\nCommands: PING DO DC FO FC LO LC BELL FA LA AUTO FACE_OPEN\r\n");
}

void loop() {
  serviceLinkTx();
  handleAsrproSerial();
  handleUsbSerial();
  handleTouchDoorbell();
  serviceStatusLed();
  serviceUltrasonic();
  serviceSensors();
  serviceLinkTx();
  serviceTelemetry();
  serviceSerialOutput();
}
