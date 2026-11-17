#ifndef HOST_ARDUINO_STUB_H
#define HOST_ARDUINO_STUB_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <deque>
#include <string>
#include <algorithm>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define A0 14
#define A1 15
#define A2 16
#define A3 17
#define A4 18
#define A5 19
using byte = uint8_t;
template<class T> T constrain(T x, T a, T b) { return x < a ? a : x > b ? b : x; }
inline byte constrain(byte x, int a, int b) { return byte(constrain(int(x), a, b)); }
using std::min;
using std::max;
inline long map(long x, long a, long b, long c, long d) { return (x-a)*(d-c)/(b-a)+c; }
extern uint64_t hostUs;
extern int hostBoard;
extern uint8_t hostModes[2][20], hostPins[2][20];
extern int hostAnalog[2][20], hostPwm[2][20];
extern char hostKey;
extern void (*hostWireEdge)(bool);
extern float hostTemperature, hostHumidity;
extern uint8_t PIND, PINB, PCIFR, PCMSK2, PCMSK0, PCICR;
extern uint8_t TIMSK1, EIFR, EIMSK, EICRA, TCCR1A, TCCR1B, TCCR1C, TIFR1;
extern uint16_t TCNT1, OCR1A;
inline uint32_t micros() { return uint32_t(hostUs); }
inline uint32_t millis() { return uint32_t(hostUs / 1000); }
inline void delayMicroseconds(unsigned us) { hostUs += us; }
inline void pinMode(uint8_t pin, uint8_t mode) { hostModes[hostBoard][pin] = mode; }
inline void digitalWrite(uint8_t pin, uint8_t level) {
  const bool changed = hostPins[hostBoard][pin] != level;
  hostPins[hostBoard][pin] = level;
  if (hostBoard == 1 && pin == 10 && changed && hostWireEdge) hostWireEdge(level != 0);
}
inline int digitalRead(uint8_t pin) {
  if (hostBoard == 0) {
    const uint8_t cols[4] = {A4, A3, A1, A0}, rows[4] = {1, 0, 12, A5};
    const char keys[4][4] = {{'1','2','3','A'},{'4','5','6','B'},{'7','8','9','C'},{'*','0','#','D'}};
    for (uint8_t c=0;c<4;c++) if (pin == cols[c]) {
      for (uint8_t r=0;r<4;r++)
        if (hostModes[0][rows[r]] == OUTPUT && hostPins[0][rows[r]] == LOW && hostKey == keys[r][c]) return LOW;
      return HIGH;
    }
  }
  return hostPins[hostBoard][pin];
}
inline int analogRead(uint8_t pin) { return hostAnalog[hostBoard][pin]; }
inline void analogWrite(uint8_t pin, int value) { hostPwm[hostBoard][pin] = value; }
inline char *dtostrf(double v, signed char width, unsigned char digits, char *out) {
  snprintf(out, 10, "%*.*f", int(width), int(digits), v); return out;
}
struct HardwareSerial {
  std::deque<uint8_t> incoming;
  std::string outgoing;
  void begin(uint32_t) {}
  int available() { return int(incoming.size()); }
  int read() { if(incoming.empty()) return -1; auto c=incoming.front(); incoming.pop_front(); return c; }
  int availableForWrite() { return 64; }
  size_t write(uint8_t c) { outgoing += char(c); return 1; }
  void inject(const std::string &s) { for(auto c:s) incoming.push_back(uint8_t(c)); }
};
extern HardwareSerial Serial;
#endif
