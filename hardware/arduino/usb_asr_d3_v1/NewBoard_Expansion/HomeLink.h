#ifndef SMART_HOME_LINK_H
#define SMART_HOME_LINK_H

#include <stdint.h>

// Same wire as before: NEW D10 -> OLD D5, idle LOW. Both sketches must
// be updated together. V2 uses a sync pulse + magic/cmd/sequence/CRC-8.
// There is no return wire: a repeated frame is redundancy, not an ACK.
namespace HomeLink {
static const uint8_t MAGIC = 0xA7;
static const uint32_t SYNC_US = 24000;
static const uint32_t SYNC_LOW_US = 8000;
static const uint32_t ZERO_US = 4000;
static const uint32_t ONE_US = 8000;
static const uint32_t BIT_LOW_US = 4000;
static const uint32_t REPEAT_GAP_US = 40000;

inline uint8_t crc8(const uint8_t *bytes, uint8_t count) {
  uint8_t crc = 0;
  while (count--) {
    crc ^= *bytes++;
    for (uint8_t b = 0; b < 8; ++b)
      crc = (crc & 0x80) ? uint8_t((crc << 1) ^ 0x07) : uint8_t(crc << 1);
  }
  return crc;
}

struct Packet { uint8_t command; uint8_t sequence; };

class Receiver {
 public:
  Receiver() : high_(false), haveRise_(false), receiving_(false), bit_(0),
      value_(0), highAt_(0), edgeAt_(0), gapUs_(0), head_(0), tail_(0) {}

  void begin(bool level, uint32_t now) {
    high_ = level;
    // A boot in the middle of a HIGH pulse must not invent a sync pulse.
    haveRise_ = false;
    receiving_ = false;
    edgeAt_ = now;
    head_ = tail_ = 0;
  }

  // Called only by the old board's D5 pin-change ISR.
  void onEdge(bool high, uint32_t now) {
    if (high == high_) return;
    high_ = high;
    if (high) {
      gapUs_ = now - edgeAt_;
      highAt_ = now;
      haveRise_ = true;
      if (receiving_ && (gapUs_ < 2000 || gapUs_ > 11500)) receiving_ = false;
      edgeAt_ = now;
      return;
    }

    edgeAt_ = now;
    if (!haveRise_) { receiving_ = false; return; }
    haveRise_ = false;
    const uint32_t width = now - highAt_;
    if (width >= 18000 && width <= 40000) {
      receiving_ = true;
      bit_ = value_ = 0;
      return;
    }
    if (!receiving_) return;

    uint8_t bitValue;
    if (width >= 2500 && width <= 5500) bitValue = 0;
    else if (width >= 6500 && width <= 10500) bitValue = 1;
    else { receiving_ = false; return; }

    value_ = uint8_t((value_ << 1) | bitValue);
    ++bit_;
    if ((bit_ & 7) == 0) {
      bytes_[(bit_ >> 3) - 1] = value_;
      value_ = 0;
    }
    if (bit_ != 32) return;
    receiving_ = false;
    if (bytes_[0] != MAGIC || bytes_[1] < 1 || bytes_[1] > 15 ||
        crc8(bytes_, 3) != bytes_[3]) return;

    const uint8_t next = (head_ + 1) & 3;
    if (next == tail_) return;  // Drop an entire packet if the inbox is full.
    inbox_[head_].command = bytes_[1];
    inbox_[head_].sequence = bytes_[2];
    head_ = next;
  }

  // Main-context calls are protected by ATOMIC_BLOCK in the old sketch.
  void expire(uint32_t now) {
    if (receiving_ && now - edgeAt_ > 20000) receiving_ = false;
  }
  bool busy(uint32_t now) const {
    return receiving_ || (high_ && haveRise_ && now - highAt_ < 50000);
  }
  bool pop(Packet &out) {
    if (tail_ == head_) return false;
    out.command = inbox_[tail_].command;
    out.sequence = inbox_[tail_].sequence;
    tail_ = (tail_ + 1) & 3;
    return true;
  }

 private:
  volatile bool high_, haveRise_, receiving_;
  uint8_t bit_, value_, bytes_[4];
  volatile uint32_t highAt_, edgeAt_;
  uint32_t gapUs_;
  volatile uint8_t head_, tail_;
  Packet inbox_[4];
};

class Transmitter {
 public:
  Transmitter() : state_(IDLE), high_(false), bit_(0), copies_(0), at_(0), duration_(0) {}
  bool active() const { return state_ != IDLE; }
  bool level() const { return high_; }

  bool start(uint8_t command, uint8_t sequence, uint8_t copies, uint32_t now) {
    if (active() || command < 1 || command > 15 || copies == 0) return false;
    bytes_[0] = MAGIC;
    bytes_[1] = command;
    bytes_[2] = sequence;
    bytes_[3] = crc8(bytes_, 3);
    copies_ = copies;
    bit_ = 0;
    set(SYNC_HIGH, true, SYNC_US, now);
    return true;
  }

  // Returns true when the GPIO level changes. Deadlines restart at the
  // actual edge; a late tick never compresses the following HIGH/LOW pulse.
  bool update(uint32_t now) {
    if (!active() || now - at_ < duration_) return false;
    const bool before = high_;
    switch (state_) {
      case SYNC_HIGH: set(SYNC_LOW, false, SYNC_LOW_US, now); break;
      case SYNC_LOW: startBit(now); break;
      case BIT_HIGH: set(BIT_LOW, false, BIT_LOW_US, now); break;
      case BIT_LOW:
        if (++bit_ < 32) startBit(now);
        else set(FRAME_GAP, false, REPEAT_GAP_US, now);
        break;
      case FRAME_GAP:
        if (--copies_ == 0) state_ = IDLE;
        else { bit_ = 0; set(SYNC_HIGH, true, SYNC_US, now); }
        break;
      default: break;
    }
    return high_ != before;
  }

 private:
  enum State : uint8_t { IDLE, SYNC_HIGH, SYNC_LOW, BIT_HIGH, BIT_LOW, FRAME_GAP };
  State state_;
  bool high_;
  uint8_t bit_, copies_, bytes_[4];
  uint32_t at_, duration_;
  void set(State state, bool high, uint32_t duration, uint32_t now) {
    state_ = state; high_ = high; at_ = now; duration_ = duration;
  }
  void startBit(uint32_t now) {
    const bool one = (bytes_[bit_ >> 3] & (0x80 >> (bit_ & 7))) != 0;
    set(BIT_HIGH, true, one ? ONE_US : ZERO_US, now);
  }
};
}  // namespace HomeLink
#endif
