#ifndef SMART_HOME_COMMAND_INPUT_H
#define SMART_HOME_COMMAND_INPUT_H
// Separate instances for ASR and USB: bytes from different sources never mix.
struct CommandInput {
  char text[25];
  uint8_t length;
  bool overflow;
  uint32_t lastByteAt;
  CommandInput() : length(0), overflow(false), lastByteAt(0) { text[0] = '\0'; }
  void reset() { length = 0; overflow = false; text[0] = '\0'; }
};
#endif
