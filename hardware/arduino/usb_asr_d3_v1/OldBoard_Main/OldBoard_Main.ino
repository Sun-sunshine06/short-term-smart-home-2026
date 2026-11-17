/*
 * OLD / MAIN Arduino UNO R3 -- USB_ASR_D3_V1 paired release 2026-11-17
 * All original external wires stay where they were.
 * Open this .ino with HomeLink.h in the same sketch folder.
 * Update BOTH Arduino boards; V2 does not accept legacy pulse counts.
 * This board's D3 remains the DOOR SERVO. Move ASR TX only on the NEW board.
 * Voice and USB commands arrive over the same existing D5 HomeLink input.
 * Local control logic and pin map are retained from the verified V2 release.
 */
#include <Arduino.h>
#include <U8g2lib.h>
#include <DHT.h>
#include <Adafruit_NeoPixel.h>
#include <Servo.h>
#include <math.h>
#include <string.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include "HomeLink.h"

#if !defined(__AVR_ATmega328P__) && !defined(HOME_HOST_TEST)
#error "Select Arduino Uno (ATmega328P). D5 reception uses the UNO R3 pin-change interrupt."
#endif

// Original pin map -- unchanged.
#define DHT_PIN 2
#define DHT_TYPE DHT11
#define LIGHT_DO_PIN A2
#define SERVO_PIN 3
#define BUZZER_PIN 4
#define VOICE_COMMAND_PIN 5
#define FAN_INB_PIN 6
#define RGB_LED_PIN 7
#define RGB_LED_COUNT 8
#define OLED_RESET 8
#define OLED_DC 9
#define OLED_CS 10
#define OLED_DATA 11
#define OLED_CLOCK 13
#define KEYPAD_ROW_1 1
#define KEYPAD_ROW_2 0
#define KEYPAD_ROW_3 12
#define KEYPAD_ROW_4 A5
#define KEYPAD_COL_1 A4
#define KEYPAD_COL_2 A3
#define KEYPAD_COL_3 A1
#define KEYPAD_COL_4 A0

const float FAN_TEMP_ON = 28.0;
const float FAN_TEMP_OFF = 27.0;  // Hysteresis avoids chatter around 28 C.
const uint32_t DHT_INTERVAL_MS = 2000;
const uint32_t DOOR_OPEN_MS = 4000;
const uint32_t REMOTE_STATE_TIMEOUT_MS = 15000;
const bool LIGHT_DARK_WHEN_LOW = false;  // Original module polarity.
const bool BUZZER_ACTIVE_LOW = true;
const byte FAN_RUN_PWM = 150;
const byte RGB_BRIGHTNESS = 35;
const int DOOR_CLOSED_ANGLE = 0;
const int DOOR_OPEN_ANGLE = 90;
const char PASSWORD[] = "1234";
const byte MAX_CODE_LEN = 4;

const byte keypadRowPins[4] = {KEYPAD_ROW_1, KEYPAD_ROW_2, KEYPAD_ROW_3, KEYPAD_ROW_4};
const byte keypadColPins[4] = {KEYPAD_COL_1, KEYPAD_COL_2, KEYPAD_COL_3, KEYPAD_COL_4};
const char keypadMap[4][4] = {
  {'1', '2', '3', 'A'}, {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'}, {'*', '0', '#', 'D'}
};

DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_NeoPixel rgbRing(RGB_LED_COUNT, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);
Servo doorServo;
// IMPORTANT: software SPI uses the SAME D13/D11/D10/D9/D8 wires.
// Never call SPI.begin(): hardware SPI forces D12/MISO into INPUT mode.
U8G2_SH1106_128X64_NONAME_1_4W_SW_SPI u8g2(
  U8G2_R0, OLED_CLOCK, OLED_DATA, OLED_CS, OLED_DC, OLED_RESET
);
HomeLink::Receiver linkReceiver;

float temperature = NAN, humidity = NAN;
bool sensorOk = false, fanState = false, rgbLightState = false;
bool lightIsDark = false, doorOpen = false;
bool rainKnown = false, rainWet = false, soilKnown = false, soilWet = false;
byte fanMode = 0, lightMode = 0;  // 0 AUTO, 1 manual ON, 2 manual OFF.
char enteredCode[MAX_CODE_LEN + 1] = "";
byte enteredLen = 0;
char keypadStatus[10] = "READY";
uint32_t lastSensorRead = 0, doorOpenedAt = 0;
uint32_t lastRainAt = 0, lastSoilAt = 0;
bool displayDirty = true, displayActive = false;
uint32_t lastDisplayAt = 0;
bool haveLastPacket = false;
byte lastPacketCommand = 0, lastPacketSequence = 0;
uint32_t lastPacketAt = 0;

// The page buffer is only 128 bytes. Draw one page per loop and keep a
// coherent snapshot for all eight pages, so keys/link/buzzer run between pages.
struct DisplaySnapshot {
  float temp, hum;
  bool sensor, fan, light, door, rainValid, rain, soilValid, soil;
  byte fanModeValue, lightModeValue;
  char password[10];
} screen;

// Alternating ON/OFF durations, stored in flash. No millisecond delay().
const uint16_t SOUND_KEY[] PROGMEM = {35};
const uint16_t SOUND_OPEN[] PROGMEM = {60, 40, 60, 40, 160};
const uint16_t SOUND_CLOSE[] PROGMEM = {180};
const uint16_t SOUND_DENIED[] PROGMEM = {220, 110, 220, 110, 220};
const uint16_t SOUND_ERROR[] PROGMEM = {220, 40, 220};
const uint16_t SOUND_BELL[] PROGMEM = {90, 100, 90, 100, 260};
const uint16_t *soundPattern = NULL;
byte soundCount = 0, soundIndex = 0, soundPriority = 0;
uint32_t soundAt = 0;

void updateFanAuto();
void updateRgbLightAuto();

ISR(PCINT2_vect) {
  linkReceiver.onEdge((PIND & _BV(PD5)) != 0, micros());
}

void buzzerWrite(bool on) {
  digitalWrite(BUZZER_PIN, on == BUZZER_ACTIVE_LOW ? LOW : HIGH);
}

void startSound(const uint16_t *pattern, byte count, byte priority) {
  if (soundPattern && priority < soundPriority) return;
  soundPattern = pattern;
  soundCount = count;
  soundIndex = 0;
  soundPriority = priority;
  soundAt = millis();
  buzzerWrite(true);
}

void serviceSound() {
  if (!soundPattern) return;
  const uint32_t now = millis();
  if (now - soundAt < pgm_read_word(soundPattern + soundIndex)) return;
  soundAt = now;
  if (++soundIndex >= soundCount) {
    soundPattern = NULL;
    soundPriority = 0;
    buzzerWrite(false);
  } else buzzerWrite((soundIndex & 1) == 0);
}

void clearCode(const char *text) {
  enteredLen = 0;
  enteredCode[0] = '\0';
  strncpy(keypadStatus, text, sizeof(keypadStatus) - 1);
  keypadStatus[sizeof(keypadStatus) - 1] = '\0';
  displayDirty = true;
}

void setFan(bool on) {
  if (fanState == on) return;
  fanState = on;
  analogWrite(FAN_INB_PIN, on ? FAN_RUN_PWM : 0);
  displayDirty = true;
}

void setRgbLight(bool on) {
  if (rgbLightState == on) return;  // Do not resend the ring every loop.
  rgbLightState = on;
  if (on) {
    for (byte i = 0; i < RGB_LED_COUNT; ++i)
      rgbRing.setPixelColor(i, rgbRing.Color(255, 180, 90));
  } else rgbRing.clear();
  rgbRing.show();
  displayDirty = true;
}

void openDoor() {
  doorServo.write(DOOR_OPEN_ANGLE);
  doorOpen = true;
  doorOpenedAt = millis();
  displayDirty = true;
}

void closeDoor() {
  doorServo.write(DOOR_CLOSED_ANGLE);
  doorOpen = false;
  displayDirty = true;
}

void updateFanAuto() {
  if (fanMode == 1) setFan(true);
  else if (fanMode == 2) setFan(false);
  else if (sensorOk) {
    if (temperature >= FAN_TEMP_ON) setFan(true);
    else if (temperature <= FAN_TEMP_OFF) setFan(false);
  }
  // As in the original: failed DHT readings retain the last fan state.
}

void updateRgbLightAuto() {
  setRgbLight(lightMode == 1 || (lightMode == 0 && lightIsDark));
}

void restoreAuto(byte which) {
  if (which == 1 || which == 3) { fanMode = 0; updateFanAuto(); }
  if (which == 2 || which == 3) { lightMode = 0; updateRgbLightAuto(); }
  clearCode(which == 1 ? "F-AUTO" : which == 2 ? "L-AUTO" : "ALL-AUTO");
  startSound(SOUND_KEY, 1, 1);
}

void executeVoiceCommand(byte id) {
  switch (id) {
    case 1: clearCode("V-OPEN"); openDoor(); startSound(SOUND_OPEN, 5, 3); break;
    case 2: clearCode("V-CLOSE"); closeDoor(); startSound(SOUND_CLOSE, 1, 2); break;
    case 3: fanMode = 1; clearCode("FAN ON"); setFan(true); startSound(SOUND_KEY, 1, 1); break;
    case 4: fanMode = 2; clearCode("FAN OFF"); setFan(false); startSound(SOUND_KEY, 1, 1); break;
    case 5: lightMode = 1; clearCode("L ON"); setRgbLight(true); startSound(SOUND_KEY, 1, 1); break;
    case 6: lightMode = 2; clearCode("L OFF"); setRgbLight(false); startSound(SOUND_KEY, 1, 1); break;
    case 7: clearCode("BELL"); startSound(SOUND_BELL, 5, 2); break;
    case 8: clearCode("TOUCH"); openDoor(); startSound(SOUND_KEY, 1, 1); break;
    case 9: case 10:
      if (!rainKnown || rainWet != (id == 10)) displayDirty = true;
      rainKnown = true; rainWet = (id == 10); lastRainAt = millis(); break;
    case 11: case 12:
      if (!soilKnown || soilWet != (id == 12)) displayDirty = true;
      soilKnown = true; soilWet = (id == 12); lastSoilAt = millis(); break;
    case 13: restoreAuto(1); break;
    case 14: restoreAuto(2); break;
    case 15: restoreAuto(3); break;
    default: break;
  }
}

void serviceLink() {
  HomeLink::Packet packet;
  bool available;
  do {
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
      linkReceiver.expire(micros());
      available = linkReceiver.pop(packet);
    }
    if (available) {
      const uint32_t now = millis();
      const bool duplicate = haveLastPacket && packet.command == lastPacketCommand &&
          packet.sequence == lastPacketSequence && now - lastPacketAt < 1500;
      if (!duplicate) {
        haveLastPacket = true;
        lastPacketCommand = packet.command;
        lastPacketSequence = packet.sequence;
        lastPacketAt = now;
        executeVoiceCommand(packet.command);
      }
    }
  } while (available);
}

bool linkBusy() {
  bool result;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { result = linkReceiver.busy(micros()); }
  return result;
}

void setupKeypad() {
  // Unselected rows are high impedance instead of OUTPUT HIGH. This also
  // avoids directly shorting two row outputs when several keys are pressed.
  for (byte r = 0; r < 4; ++r) {
    digitalWrite(keypadRowPins[r], LOW);
    pinMode(keypadRowPins[r], INPUT);
  }
  for (byte c = 0; c < 4; ++c) pinMode(keypadColPins[c], INPUT_PULLUP);
}

char scanKeypadRaw() {
  char found = '\0';
  byte count = 0;
  for (byte r = 0; r < 4; ++r) {
    pinMode(keypadRowPins[r], OUTPUT);
    digitalWrite(keypadRowPins[r], LOW);
    delayMicroseconds(8);
    for (byte c = 0; c < 4; ++c) {
      if (digitalRead(keypadColPins[c]) == LOW) {
        found = keypadMap[r][c];
        ++count;
      }
    }
    pinMode(keypadRowPins[r], INPUT);
  }
  return count == 1 ? found : '\0';  // Ignore ambiguous multi-key chords.
}

char scanKeypad() {
  static char lastRaw = '\0', stable = '\0';
  static uint32_t changedAt = 0;
  const char raw = scanKeypadRaw();
  const uint32_t now = millis();
  if (raw != lastRaw) { lastRaw = raw; changedAt = now; }
  if (now - changedAt < 25 || raw == stable) return '\0';
  stable = raw;
  return stable;
}

void handleKey(char key) {
  if (key == '\0') return;
  // Extra keys restore AUTO without changing the ASRPRO module program.
  if (key == 'A') { restoreAuto(1); return; }
  if (key == 'B') { restoreAuto(2); return; }
  if (key == 'D') { restoreAuto(3); return; }
  if (key == 'C') return;
  startSound(SOUND_KEY, 1, 1);
  if (key == '*') { clearCode("CLEAR"); return; }
  if (key == '#') {
    if (strcmp(enteredCode, PASSWORD) == 0) {
      clearCode("OK"); openDoor(); startSound(SOUND_OPEN, 5, 3);
    } else { clearCode("DENIED"); startSound(SOUND_DENIED, 5, 4); }
    return;
  }
  if (key < '0' || key > '9') return;
  if (enteredLen >= MAX_CODE_LEN) {
    clearCode("FULL"); startSound(SOUND_ERROR, 3, 3); return;
  }
  enteredCode[enteredLen++] = key;
  enteredCode[enteredLen] = '\0';
  strcpy(keypadStatus, "INPUT");
  displayDirty = true;
}

void serviceLightSensor() {
  static bool candidate = false;
  static uint32_t changedAt = 0;
  const bool high = digitalRead(LIGHT_DO_PIN) == HIGH;
  const bool dark = LIGHT_DARK_WHEN_LOW ? !high : high;
  const uint32_t now = millis();
  if (dark != candidate) { candidate = dark; changedAt = now; }
  if (dark != lightIsDark && now - changedAt >= 25) {
    lightIsDark = dark;
    updateRgbLightAuto();
  }
}

void serviceClimate() {
  const uint32_t now = millis();
  if (now - lastSensorRead < DHT_INTERVAL_MS || linkBusy()) return;
  lastSensorRead = now;
  const float h = dht.readHumidity();
  const float t = dht.readTemperature();
  sensorOk = !isnan(h) && !isnan(t);
  if (sensorOk) { temperature = t; humidity = h; }
  updateFanAuto();
  displayDirty = true;
}

void serviceDoorAndRemoteStates() {
  const uint32_t now = millis();
  if (doorOpen && now - doorOpenedAt >= DOOR_OPEN_MS) {
    closeDoor(); clearCode("CLOSED"); startSound(SOUND_CLOSE, 1, 2);
  }
  if (rainKnown && now - lastRainAt >= REMOTE_STATE_TIMEOUT_MS) {
    rainKnown = false; displayDirty = true;
  }
  if (soilKnown && now - lastSoilAt >= REMOTE_STATE_TIMEOUT_MS) {
    soilKnown = false; displayDirty = true;
  }
}

void captureDisplay() {
  screen.temp = temperature; screen.hum = humidity; screen.sensor = sensorOk;
  screen.fan = fanState; screen.light = rgbLightState; screen.door = doorOpen;
  screen.rainValid = rainKnown; screen.rain = rainWet;
  screen.soilValid = soilKnown; screen.soil = soilWet;
  screen.fanModeValue = fanMode; screen.lightModeValue = lightMode;
  if (enteredLen == 0) strcpy(screen.password, keypadStatus);
  else {
    for (byte i = 0; i < enteredLen; ++i) screen.password[i] = '*';
    screen.password[enteredLen] = '\0';
  }
}

void drawContent() {
  char line[24], value[10];
  u8g2.setFont(u8g2_font_6x12_tr);
  snprintf_P(line, sizeof(line), PSTR("Smart Home F:%c L:%c"),
    screen.fanModeValue == 0 ? 'A' : 'M', screen.lightModeValue == 0 ? 'A' : 'M');
  u8g2.drawStr(4, 8, line);
  u8g2.drawLine(4, 11, 123, 11);
  if (screen.sensor) {
    dtostrf(screen.temp, 4, 1, value);
    snprintf_P(line, sizeof(line), PSTR("Temp:%s C Fan:%s"), value, screen.fan ? "ON" : "OFF");
  } else snprintf_P(line, sizeof(line), PSTR("Temp:ERR Fan:%s"), screen.fan ? "ON" : "OFF");
  u8g2.drawStr(4, 24, line);
  if (screen.sensor) {
    dtostrf(screen.hum, 4, 0, value);
    snprintf_P(line, sizeof(line), PSTR("Hum :%s %% LED:%s"), value, screen.light ? "ON" : "OFF");
  } else snprintf_P(line, sizeof(line), PSTR("Hum :ERR LED:%s"), screen.light ? "ON" : "OFF");
  u8g2.drawStr(4, 36, line);
  snprintf_P(line, sizeof(line), PSTR("Rain:%s Soil:%s"),
    screen.rainValid ? (screen.rain ? "WET" : "DRY") : "--",
    screen.soilValid ? (screen.soil ? "WET" : "DRY") : "--");
  u8g2.drawStr(4, 48, line);
  snprintf_P(line, sizeof(line), PSTR("Door:%s P:%s"), screen.door ? "OPEN" : "LOCK", screen.password);
  u8g2.drawStr(4, 60, line);
}

void serviceDisplay() {
  if (!displayActive) {
    if (!displayDirty || millis() - lastDisplayAt < 60) return;
    captureDisplay();
    displayDirty = false;
    displayActive = true;
    lastDisplayAt = millis();
    u8g2.firstPage();
  }
  drawContent();
  if (!u8g2.nextPage()) displayActive = false;
}

void setup() {
  pinMode(FAN_INB_PIN, OUTPUT); analogWrite(FAN_INB_PIN, 0);
  pinMode(BUZZER_PIN, OUTPUT); buzzerWrite(false);
  pinMode(VOICE_COMMAND_PIN, INPUT);
  pinMode(LIGHT_DO_PIN, INPUT);
  setupKeypad();
  doorServo.attach(SERVO_PIN); closeDoor();
  dht.begin();
  rgbRing.begin(); rgbRing.setBrightness(RGB_BRIGHTNESS);
  rgbRing.clear(); rgbRing.show();
  linkReceiver.begin(digitalRead(VOICE_COMMAND_PIN) == HIGH, micros());
  PCIFR = _BV(PCIF2);
  PCMSK2 |= _BV(PCINT21);
  PCICR |= _BV(PCIE2);
  u8g2.begin();  // No hardware SPI.begin(), no 1500 ms startup wait.
}

void loop() {
  serviceLink();
  handleKey(scanKeypad());
  serviceSound();
  serviceDoorAndRemoteStates();
  serviceLightSensor();
  serviceClimate();
  serviceLink();
  serviceDisplay();
}
