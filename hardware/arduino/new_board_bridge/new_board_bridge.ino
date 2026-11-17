#include <Arduino.h>

// New Arduino expansion board:
// - Receives ASRPRO Serial1 short commands on D0/RX.
// - Sends pulse commands to the old Arduino on D10.
// - Reads rain, soil moisture, touch doorbell, and ultrasonic distance.
//
// Existing cross-board wiring:
// ASRPRO PA_2 / Serial1 TX -> new Arduino D0 / RX
// ASRPRO GND               -> new Arduino GND
// ASRPRO 5V                -> new Arduino 5V
// new Arduino D10          -> old Arduino D5
// new Arduino GND          -> old Arduino GND
//
// Extra sensors on the new Arduino:
// Rain module VCC -> 5V, GND -> GND, AO -> A0
// Soil module VCC -> 5V, GND -> GND, AO -> A1
// Touch module VCC -> 5V, GND -> GND, OUT/SIG -> D2
// Ultrasonic VCC -> 5V, GND -> GND, TRIG -> D8, ECHO -> D9

#define OLD_BOARD_SIGNAL_PIN 10
#define STATUS_LED_PIN 13

#define TOUCH_PIN 2
#define ULTRASONIC_TRIG_PIN 8
#define ULTRASONIC_ECHO_PIN 9
#define RAIN_AO_PIN A0
#define SOIL_AO_PIN A1

const unsigned long ASR_BAUD = 9600;
const unsigned int COMMAND_IDLE_MS = 40;
const unsigned int PULSE_HIGH_MS = 90;
const unsigned int PULSE_LOW_MS = 90;
const unsigned int FRAME_END_MS = 450;

const unsigned long SENSOR_INTERVAL_MS = 1000;
const unsigned long TOUCH_DEBOUNCE_MS = 600;
const unsigned long ULTRASONIC_TIMEOUT_US = 30000;

// Calibrate these four numbers after seeing raw values in Serial Monitor.
// Typical modules: dry/raw is high, wet/raw is low.
const int RAIN_DRY_RAW = 900;
const int RAIN_WET_RAW = 300;
const int SOIL_DRY_RAW = 850;
const int SOIL_WET_RAW = 300;

const int RAIN_ALERT_PERCENT = 45;  // >= this means rain/wet
const int SOIL_DRY_PERCENT = 35;    // <= this means soil is dry
const float PERSON_NEAR_CM = 20.0;

String command = "";
unsigned long lastByteAt = 0;
unsigned long lastSensorAt = 0;
unsigned long lastTouchAt = 0;
bool touchWasPressed = false;

int rainRaw = 0;
int rainPercent = 0;
bool rainDetected = false;

int soilRaw = 0;
int soilPercent = 0;
bool soilDry = false;

float distanceCm = -1.0;
bool personNear = false;

int percentFromRaw(int raw, int dryRaw, int wetRaw) {
  int low = min(dryRaw, wetRaw);
  int high = max(dryRaw, wetRaw);
  raw = constrain(raw, low, high);

  long percent = map(raw, dryRaw, wetRaw, 0, 100);
  return constrain((int)percent, 0, 100);
}

void blinkStatus(byte count) {
  byte blinkCount = constrain(count, 1, 7);

  for (byte i = 0; i < blinkCount; i++) {
    digitalWrite(STATUS_LED_PIN, HIGH);
    delay(70);
    digitalWrite(STATUS_LED_PIN, LOW);
    delay(70);
  }

  delay(160);
}

void blinkUnknownCommand() {
  for (byte i = 0; i < 3; i++) {
    digitalWrite(STATUS_LED_PIN, HIGH);
    delay(35);
    digitalWrite(STATUS_LED_PIN, LOW);
    delay(35);
  }

  delay(160);
}

void sendPulses(byte count) {
  digitalWrite(OLD_BOARD_SIGNAL_PIN, LOW);
  delay(30);

  for (byte i = 0; i < count; i++) {
    digitalWrite(OLD_BOARD_SIGNAL_PIN, HIGH);
    delay(PULSE_HIGH_MS);
    digitalWrite(OLD_BOARD_SIGNAL_PIN, LOW);
    delay(PULSE_LOW_MS);
  }

  delay(FRAME_END_MS);
}

byte commandToId(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  // Old Arduino command IDs:
  // 1 door open, 2 door close, 3 fan on, 4 fan off,
  // 5 light on, 6 light off, 7 doorbell.
  if (cmd == "DO" || cmd == "DOOR_OPEN" || cmd == "OPEN") return 1;
  if (cmd == "DC" || cmd == "DOOR_CLOSE" || cmd == "CLOSE") return 2;
  if (cmd == "FO" || cmd == "FAN_ON") return 3;
  if (cmd == "FC" || cmd == "FAN_OFF") return 4;
  if (cmd == "LO" || cmd == "LIGHT_ON" || cmd == "LED_ON") return 5;
  if (cmd == "LC" || cmd == "LIGHT_OFF" || cmd == "LED_OFF") return 6;
  if (cmd == "BELL" || cmd == "DB" || cmd == "DOORBELL") return 7;

  return 0;
}

void handleAsrproSerial() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    lastByteAt = millis();

    if (ch == '\r' || ch == '\n' || ch == ' ') {
      continue;
    }

    if (command.length() < 16) {
      command += ch;
    }
  }

  if (command.length() > 0 && millis() - lastByteAt >= COMMAND_IDLE_MS) {
    byte commandId = commandToId(command);

    if (commandId > 0) {
      Serial.print("ASR_CMD:");
      Serial.print(command);
      Serial.print(",ID:");
      Serial.println(commandId);

      blinkStatus(commandId);
      sendPulses(commandId);
    } else {
      Serial.print("ASR_UNKNOWN:");
      Serial.println(command);
      blinkUnknownCommand();
    }

    command = "";
  }
}

float readDistanceCm() {
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, ULTRASONIC_TIMEOUT_US);
  if (duration == 0) {
    return -1.0;
  }

  return duration / 58.0;
}

void readSensors() {
  rainRaw = analogRead(RAIN_AO_PIN);
  soilRaw = analogRead(SOIL_AO_PIN);

  rainPercent = percentFromRaw(rainRaw, RAIN_DRY_RAW, RAIN_WET_RAW);
  soilPercent = percentFromRaw(soilRaw, SOIL_DRY_RAW, SOIL_WET_RAW);

  rainDetected = rainPercent >= RAIN_ALERT_PERCENT;
  soilDry = soilPercent <= SOIL_DRY_PERCENT;

  distanceCm = readDistanceCm();
  personNear = distanceCm > 0 && distanceCm <= PERSON_NEAR_CM;
}

void printSensorStatus() {
  Serial.print("RAIN_RAW:");
  Serial.print(rainRaw);
  Serial.print(",RAIN:");
  Serial.print(rainPercent);
  Serial.print("%,RAIN_STATE:");
  Serial.print(rainDetected ? "WET" : "DRY");

  Serial.print(",SOIL_RAW:");
  Serial.print(soilRaw);
  Serial.print(",SOIL:");
  Serial.print(soilPercent);
  Serial.print("%,SOIL_STATE:");
  Serial.print(soilDry ? "DRY" : "OK");

  Serial.print(",DIST:");
  if (distanceCm < 0) {
    Serial.print("NO_ECHO");
  } else {
    Serial.print(distanceCm, 1);
    Serial.print("cm");
  }

  Serial.print(",NEAR:");
  Serial.println(personNear ? "YES" : "NO");
}

void handleTouchDoorbell() {
  bool pressed = digitalRead(TOUCH_PIN) == HIGH;
  unsigned long now = millis();

  if (pressed && !touchWasPressed && now - lastTouchAt >= TOUCH_DEBOUNCE_MS) {
    lastTouchAt = now;
    Serial.println("TOUCH_DOORBELL");
    blinkStatus(7);
    sendPulses(7);
  }

  touchWasPressed = pressed;
}

void setup() {
  pinMode(OLD_BOARD_SIGNAL_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(TOUCH_PIN, INPUT);
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);

  digitalWrite(OLD_BOARD_SIGNAL_PIN, LOW);
  digitalWrite(STATUS_LED_PIN, LOW);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  Serial.begin(ASR_BAUD);
  Serial.setTimeout(30);

  delay(300);
  Serial.println("ASR_SENSOR_BRIDGE_READY");
  Serial.println("Commands: DO DC FO FC LO LC, touch sends doorbell.");
}

void loop() {
  handleAsrproSerial();
  handleTouchDoorbell();

  unsigned long now = millis();
  if (now - lastSensorAt >= SENSOR_INTERVAL_MS) {
    lastSensorAt = now;
    readSensors();
    printSensorStatus();
  }
}