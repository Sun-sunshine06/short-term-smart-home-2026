#ifndef SMART_HOME_ASR_D3_RX_H
#define SMART_HOME_ASR_D3_RX_H
#include <Arduino.h>
#include <avr/interrupt.h>
#include <util/atomic.h>

// UNO R3 only. Receive-only 9600 8N1 on D3 (INT1).
// Timer1 normal mode, prescaler 8: 0.5 us/tick at 16 MHz.
// Each ISR samples ONE bit; no byte-long interrupt blocking.
// Timer0/millis and the D9 PCINT0 ultrasonic ISR remain independent.
// Timer1 belongs to this receiver on the NEW board: no Servo, tone, or
// PWM on D9/D10 here. The OLD board's Servo uses its own separate MCU.
#if !defined(HOME_HOST_TEST) && F_CPU != 16000000UL
#error "ASR D3 receiver requires a 16 MHz Arduino Uno R3."
#endif
namespace AsrD3Rx {
static const uint16_t BIT_TICKS = 208;
static const uint8_t MASK = 63;
static volatile uint8_t buffer[64], head = 0, tail = 0, errors = 0;
static volatile uint8_t phase = 0, value = 0;

inline void rearm() {
  TIMSK1 &= ~_BV(OCIE1A);
  EIFR = _BV(INTF1);  // Clear data-bit edges before listening for a new start.
  EIMSK |= _BV(INT1);
}

inline void begin() {
  pinMode(3, INPUT_PULLUP);
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    head = tail = errors = phase = value = 0;
    EIMSK &= ~_BV(INT1);
    TCCR1A = 0; TCCR1B = _BV(CS11); TCCR1C = 0;
    TIMSK1 = 0; TCNT1 = 0;
    EICRA = (EICRA & ~(_BV(ISC11) | _BV(ISC10))) | _BV(ISC11);
    rearm();
  }
}

inline void startBit() {
  if (PIND & _BV(PD3)) return;
  EIMSK &= ~_BV(INT1);
  phase = value = 0;
  OCR1A = uint16_t(TCNT1 + BIT_TICKS / 2);
  TIFR1 = _BV(OCF1A);
  TIMSK1 |= _BV(OCIE1A);
}

inline void sampleBit() {
  if (uint16_t(TCNT1 - OCR1A) > BIT_TICKS / 2) {
    errors |= 4; rearm(); return;  // Late sample: never accept a guessed byte.
  }
  const bool high = (PIND & _BV(PD3)) != 0;
  if (phase == 0) {
    if (high) { rearm(); return; }  // Short glitch, not a start bit.
  } else if (phase <= 8) {
    if (high) value |= uint8_t(1u << (phase - 1));
  } else {
    if (!high) errors |= 1;  // Bad stop bit.
    else {
      const uint8_t next = (head + 1) & MASK;
      if (next == tail) errors |= 2;
      else { buffer[head] = value; head = next; }
    }
    rearm(); return;
  }
  ++phase;
  OCR1A = uint16_t(OCR1A + BIT_TICKS);
}

inline int read() {
  int result = -1;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    if (head != tail) { result = buffer[tail]; tail = (tail + 1) & MASK; }
  }
  return result;
}
inline bool available() { return head != tail; }
inline uint8_t takeErrors() {
  uint8_t result;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    result = errors; errors = 0;
    if (result) tail = head;  // Discard bytes around a damaged command.
  }
  return result;
}
}
ISR(INT1_vect) { AsrD3Rx::startBit(); }
ISR(TIMER1_COMPA_vect) { AsrD3Rx::sampleBit(); }
#endif
