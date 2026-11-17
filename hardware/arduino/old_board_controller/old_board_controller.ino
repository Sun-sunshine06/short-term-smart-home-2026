#include <Arduino.h>
#include <SPI.h>
#include <U8g2lib.h>
#include <DHT.h>
#include <Adafruit_NeoPixel.h>
#include <Servo.h>
#include <math.h>

// ---------- Pin map ----------
#define DHT_PIN 2
#define DHT_TYPE DHT11

// Light sensor module:
// VCC -> 5V
// GND -> GND
// D0  -> A2
#define LIGHT_DO_PIN A2

// Access control:
// Servo signal -> D3
// Buzzer signal -> D4
#define SERVO_PIN 3
#define BUZZER_PIN 4

// RGB LED ring, WS2812/NeoPixel style:
// GND  -> GND
// VCC  -> 5V
// DIN  -> D7
#define RGB_LED_PIN 7
#define RGB_LED_COUNT 8

// Voice command line:
// New Arduino D10 -> old Arduino D5
// New Arduino GND -> old Arduino GND
// Idle LOW. Commands are encoded as several HIGH pulses.
#define VOICE_COMMAND_PIN 5

// Fan motor driver module pins:
// GND -> GND
// VCC -> 5V or external 5V
// INA -> not connected
// INB -> D6    (PWM speed control)
#define FAN_INB_PIN 6

// OLED old wiring:
// GND -> GND
// VCC -> 3.3V or 5V
// SCK -> D13
// SDA -> D11
// RES -> D8
// DC  -> D9
// CS  -> D10
#define OLED_CS 10
#define OLED_DC 9
#define OLED_RESET 8

// 4x4 keypad.
// Your keypad cable order is reversed:
// pin 1 = C4, pin 2 = C3, pin 3 = C2, pin 4 = C1,
// pin 5 = R4, pin 6 = R3, pin 7 = R2, pin 8 = R1.
//
// Keypad pin 1 -> A0
// Keypad pin 2 -> A1
// Keypad pin 3 -> A3
// Keypad pin 4 -> A4
// Keypad pin 5 -> A5
// Keypad pin 6 -> D12
// Keypad pin 7 -> D0
// Keypad pin 8 -> D1
#define KEYPAD_ROW_1 1
#define KEYPAD_ROW_2 0
#define KEYPAD_ROW_3 12
#define KEYPAD_ROW_4 A5
#define KEYPAD_COL_1 A4
#define KEYPAD_COL_2 A3
#define KEYPAD_COL_3 A1
#define KEYPAD_COL_4 A0

// ---------- System settings ----------
// Lowered from 30 C so the fan responds earlier.
const float FAN_TEMP_THRESHOLD = 28.0;

// DHT11 should be read no faster than about once every two seconds.
const unsigned long DHT_INTERVAL_MS = 2000;

// The light module has a digital D0 output, so it can be checked much faster.
const unsigned long LIGHT_INTERVAL_MS = 150;
const byte FAN_RUN_PWM = 150;
const bool LIGHT_DARK_WHEN_LOW = false;
const byte RGB_BRIGHTNESS = 35;
const int DOOR_CLOSED_ANGLE = 0;
const int DOOR_OPEN_ANGLE = 90;
const unsigned long DOOR_OPEN_MS = 4000;
const bool BUZZER_ACTIVE_LOW = true;
const unsigned int VOICE_PULSE_MIN_HIGH_MS = 40;
const unsigned int VOICE_FRAME_GAP_MS = 250;

// Password:
// Press digits, press # to confirm, press * to clear.
const char PASSWORD[] = "1234";
const byte MAX_CODE_LEN = 4;

const byte KEYPAD_ROWS = 4;
const byte KEYPAD_COLS = 4;
const byte keypadRowPins[KEYPAD_ROWS] = {
  KEYPAD_ROW_1,
  KEYPAD_ROW_2,
  KEYPAD_ROW_3,
  KEYPAD_ROW_4
};
const byte keypadColPins[KEYPAD_COLS] = {
  KEYPAD_COL_1,
  KEYPAD_COL_2,
  KEYPAD_COL_3,
  KEYPAD_COL_4
};
const char keypadMap[KEYPAD_ROWS][KEYPAD_COLS] = {
  {'1', '2', '3', 'A'},
  {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'},
  {'*', '0', '#', 'D'}
};

DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_NeoPixel rgbRing(RGB_LED_COUNT, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);
Servo doorServo;

U8G2_SH1106_128X64_NONAME_1_4W_HW_SPI u8g2(
  U8G2_R0,
  OLED_CS,
  OLED_DC,
  OLED_RESET
);

float temperature = NAN;
float humidity = NAN;
bool sensorOk = false;
bool fanState = false;
bool lightDigitalHigh = false;
bool lightIsDark = false;
bool rgbLightState = false;
bool doorOpen = false;
bool rainKnown = false;
bool rainWet = false;
bool soilKnown = false;
bool soilWet = false;
byte fanMode = 0;    // 0=AUTO, 1=MANUAL_ON, 2=MANUAL_OFF
byte lightMode = 0;  // 0=AUTO, 1=MANUAL_ON, 2=MANUAL_OFF
char enteredCode[MAX_CODE_LEN + 1] = "";
byte enteredLen = 0;
char keypadStatus[10] = "READY";
unsigned long lastSensorRead = 0;
unsigned long lastLightRead = 0;
unsigned long doorOpenedAt = 0;
bool voiceLineWasHigh = false;
bool voicePulseCounted = false;
byte voicePulseCount = 0;
unsigned long voiceHighStartedAt = 0;
unsigned long voiceLastPulseAt = 0;

void clearCode(const char *statusText);
void updateFanAuto();
void updateRgbLightAuto();
void updateDisplay();

void applyFanPins() {
  if (fanState) {
    analogWrite(FAN_INB_PIN, FAN_RUN_PWM);
  } else {
    analogWrite(FAN_INB_PIN, 0);
    digitalWrite(FAN_INB_PIN, LOW);
  }
}

void setFan(bool state) {
  fanState = state;
  applyFanPins();
}

void readSensor() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    sensorOk = false;
    return;
  }

  humidity = h;
  temperature = t;
  sensorOk = true;
}

void readLightSensor() {
  // Read D0 directly so a bright/dark change is reflected immediately.
  lightDigitalHigh = digitalRead(LIGHT_DO_PIN) == HIGH;
  lightIsDark = LIGHT_DARK_WHEN_LOW ? !lightDigitalHigh : lightDigitalHigh;
}

void setRgbLight(bool state) {
  rgbLightState = state;

  if (state) {
    for (byte i = 0; i < RGB_LED_COUNT; i++) {
      rgbRing.setPixelColor(i, rgbRing.Color(255, 180, 90));
    }
  } else {
    rgbRing.clear();
  }

  rgbRing.show();
}

void updateRgbLightAuto() {
  if (lightMode == 1) {
    setRgbLight(true);
  } else if (lightMode == 2) {
    setRgbLight(false);
  } else {
    setRgbLight(lightIsDark);
  }
}

void buzzerOff() {
  digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_LOW ? HIGH : LOW);
}

void buzzerOn() {
  digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_LOW ? LOW : HIGH);
}

void beep(unsigned int durationMs) {
  buzzerOn();
  delay(durationMs);
  buzzerOff();
  delay(40);
}

void keyBeep() {
  beep(35);
}

void successBeep() {
  beep(80);
  beep(120);
}

void errorBeep() {
  beep(220);
  beep(220);
}

void doorOpenBeep() {
  beep(60);
  beep(60);
  beep(160);
}

void doorCloseBeep() {
  beep(180);
}

void wrongPasswordBeep() {
  beep(220);
  delay(70);
  beep(220);
  delay(70);
  beep(220);
}

void doorbellBeep() {
  beep(90);
  delay(60);
  beep(90);
  delay(60);
  beep(260);
}

void closeDoor() {
  doorServo.write(DOOR_CLOSED_ANGLE);
  doorOpen = false;
}

void openDoor() {
  doorServo.write(DOOR_OPEN_ANGLE);
  doorOpen = true;
  doorOpenedAt = millis();
}

void playMusicDemo() {
  for (byte i = 0; i < 3; i++) {
    beep(80);
    delay(80);
  }
  beep(180);
}

void executeVoiceCommand(byte commandId) {
  switch (commandId) {
    case 1:
      clearCode("V-OPEN");
      openDoor();
      doorOpenBeep();
      break;

    case 2:
      clearCode("V-CLOSE");
      closeDoor();
      doorCloseBeep();
      break;

    case 3:
      fanMode = 1;
      clearCode("FAN ON");
      setFan(true);
      keyBeep();
      break;

    case 4:
      fanMode = 2;
      clearCode("FAN OFF");
      setFan(false);
      keyBeep();
      break;

    case 5:
      lightMode = 1;
      clearCode("L ON");
      setRgbLight(true);
      keyBeep();
      break;

    case 6:
      lightMode = 2;
      clearCode("L OFF");
      setRgbLight(false);
      keyBeep();
      break;

    case 7:
      clearCode("BELL");
      doorbellBeep();
      break;

    case 8:
      clearCode("TOUCH");
      keyBeep();
      openDoor();
      break;

    case 9:
      rainKnown = true;
      rainWet = false;
      break;

    case 10:
      rainKnown = true;
      rainWet = true;
      break;

    case 11:
      soilKnown = true;
      soilWet = false;
      break;

    case 12:
      soilKnown = true;
      soilWet = true;
      break;

    default:
      clearCode("V-ERR");
      errorBeep();
      break;
  }

  updateDisplay();
}

void handleVoiceCommandLine() {
  bool lineIsHigh = digitalRead(VOICE_COMMAND_PIN) == HIGH;
  unsigned long now = millis();

  if (lineIsHigh && !voiceLineWasHigh) {
    voiceLineWasHigh = true;
    voicePulseCounted = false;
    voiceHighStartedAt = now;
  }

  if (lineIsHigh && !voicePulseCounted && now - voiceHighStartedAt >= VOICE_PULSE_MIN_HIGH_MS) {
    voicePulseCounted = true;
    if (voicePulseCount < 80) {
      voicePulseCount++;
    }
    voiceLastPulseAt = now;
  }

  if (!lineIsHigh && voiceLineWasHigh) {
    voiceLineWasHigh = false;
    voicePulseCounted = false;
    voiceLastPulseAt = now;
  }

  if (!lineIsHigh && voicePulseCount > 0 && now - voiceLastPulseAt >= VOICE_FRAME_GAP_MS) {
    byte commandId = voicePulseCount;
    voicePulseCount = 0;
    executeVoiceCommand(commandId);
  }
}

void updateDoorAutoClose() {
  if (doorOpen && millis() - doorOpenedAt >= DOOR_OPEN_MS) {
    closeDoor();
    clearCode("CLOSED");
    doorCloseBeep();
    updateDisplay();
  }
}

void setupKeypad() {
  for (byte r = 0; r < KEYPAD_ROWS; r++) {
    pinMode(keypadRowPins[r], OUTPUT);
    digitalWrite(keypadRowPins[r], HIGH);
  }

  for (byte c = 0; c < KEYPAD_COLS; c++) {
    pinMode(keypadColPins[c], INPUT_PULLUP);
  }
}

char scanKeypadRaw() {
  for (byte r = 0; r < KEYPAD_ROWS; r++) {
    digitalWrite(keypadRowPins[r], LOW);
    delayMicroseconds(8);

    for (byte c = 0; c < KEYPAD_COLS; c++) {
      if (digitalRead(keypadColPins[c]) == LOW) {
        digitalWrite(keypadRowPins[r], HIGH);
        return keypadMap[r][c];
      }
    }

    digitalWrite(keypadRowPins[r], HIGH);
  }

  return '\0';
}

char scanKeypad() {
  static char lastRawKey = '\0';
  static char stableKey = '\0';
  static unsigned long lastChangeAt = 0;

  char rawKey = scanKeypadRaw();

  if (rawKey != lastRawKey) {
    lastRawKey = rawKey;
    lastChangeAt = millis();
  }

  if (millis() - lastChangeAt < 35) {
    return '\0';
  }

  if (rawKey != stableKey) {
    stableKey = rawKey;
    if (stableKey != '\0') {
      return stableKey;
    }
  }

  return '\0';
}

void clearCode(const char *statusText) {
  enteredLen = 0;
  enteredCode[0] = '\0';
  strncpy(keypadStatus, statusText, sizeof(keypadStatus));
  keypadStatus[sizeof(keypadStatus) - 1] = '\0';
}

void submitCode() {
  if (strcmp(enteredCode, PASSWORD) == 0) {
    clearCode("OK");
    openDoor();
    doorOpenBeep();
  } else {
    clearCode("DENIED");
    wrongPasswordBeep();
  }
}

void handleKey(char key) {
  if (key == '\0') {
    return;
  }

  if (!((key >= '0' && key <= '9') || key == '*' || key == '#')) {
    return;
  }

  keyBeep();

  if (key == '*') {
    clearCode("CLEAR");
    return;
  }

  if (key == '#') {
    submitCode();
    return;
  }

  if (enteredLen < MAX_CODE_LEN) {
    enteredCode[enteredLen] = key;
    enteredLen++;
    enteredCode[enteredLen] = '\0';
    strncpy(keypadStatus, "INPUT", sizeof(keypadStatus));
    keypadStatus[sizeof(keypadStatus) - 1] = '\0';
  } else {
    clearCode("FULL");
    errorBeep();
  }
}

void updateFanAuto() {
  if (fanMode == 1) {
    setFan(true);
    return;
  }

  if (fanMode == 2) {
    setFan(false);
    return;
  }

  if (!sensorOk) {
    applyFanPins();
    return;
  }

  if (temperature >= FAN_TEMP_THRESHOLD) {
    setFan(true);
  } else {
    setFan(false);
  }
}

void passwordDisplayText(char *out, byte outSize) {
  if (enteredLen == 0) {
    snprintf(out, outSize, "%s", keypadStatus);
    return;
  }

  byte n = min(enteredLen, (byte)(outSize - 1));
  for (byte i = 0; i < n; i++) {
    out[i] = '*';
  }
  out[n] = '\0';
}

void drawContent() {
  char tempText[10];
  char humText[10];
  char passText[10];
  const char *rainText = rainKnown ? (rainWet ? "WET" : "DRY") : "--";
  const char *soilText = soilKnown ? (soilWet ? "WET" : "DRY") : "--";
  char line[24];
  const int x = 4;

  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(x, 8, "Smart Home Climate");
  u8g2.drawLine(x, 11, 123, 11);

  if (sensorOk) {
    dtostrf(temperature, 4, 1, tempText);
    snprintf(line, sizeof(line), "Temp:%s C Fan:%s", tempText, fanState ? "ON" : "OFF");
  } else {
    snprintf(line, sizeof(line), "Temp: ERROR Fan:%s", fanState ? "ON" : "OFF");
  }
  u8g2.drawStr(x, 24, line);

  if (sensorOk) {
    dtostrf(humidity, 4, 0, humText);
    snprintf(line, sizeof(line), "Hum :%s %% LED:%s", humText, rgbLightState ? "ON" : "OFF");
  } else {
    snprintf(line, sizeof(line), "Hum :ERR LED:%s", rgbLightState ? "ON" : "OFF");
  }
  u8g2.drawStr(x, 36, line);

  snprintf(line, sizeof(line), "Rain:%s Soil:%s", rainText, soilText);
  u8g2.drawStr(x, 48, line);

  passwordDisplayText(passText, sizeof(passText));
  snprintf(line, sizeof(line), "Door:%s P:%s", doorOpen ? "OPEN" : "LOCK", passText);
  u8g2.drawStr(x, 60, line);
}

void updateDisplay() {
  u8g2.firstPage();
  do {
    drawContent();
  } while (u8g2.nextPage());
}

void drawStartup() {
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tr);
    u8g2.drawStr(4, 16, "Smart Home System");
    u8g2.drawStr(4, 32, "DHT Light RGB Keypad");
    u8g2.drawStr(4, 48, "Password opens door");
  } while (u8g2.nextPage());
}

void setup() {
  pinMode(FAN_INB_PIN, OUTPUT);
  pinMode(VOICE_COMMAND_PIN, INPUT);
  pinMode(LIGHT_DO_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(OLED_CS, OUTPUT);
  digitalWrite(OLED_CS, HIGH);
  buzzerOff();
  setFan(false);

  setupKeypad();

  doorServo.attach(SERVO_PIN);
  closeDoor();

  dht.begin();
  rgbRing.begin();
  rgbRing.setBrightness(RGB_BRIGHTNESS);
  setRgbLight(false);

  SPI.begin();
  u8g2.begin();

  drawStartup();
  delay(1500);
}

void loop() {
  unsigned long now = millis();
  char key = scanKeypad();

  handleVoiceCommandLine();

  if (key != '\0') {
    handleKey(key);
    updateDisplay();
  }

  updateDoorAutoClose();

  if (now - lastLightRead >= LIGHT_INTERVAL_MS) {
    lastLightRead = now;

    bool oldRgbLightState = rgbLightState;
    readLightSensor();
    updateRgbLightAuto();

    // Refresh the OLED immediately when automatic lighting changes state.
    if (oldRgbLightState != rgbLightState) {
      updateDisplay();
    }
  }

  if (now - lastSensorRead >= DHT_INTERVAL_MS) {
    lastSensorRead = now;

    readSensor();
    updateFanAuto();
    updateDisplay();
  }
}