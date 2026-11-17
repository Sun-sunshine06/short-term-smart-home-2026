#pragma once
#define U8G2_R0 0
const uint8_t u8g2_font_6x12_tr[] = {0};
class U8G2_SH1106_128X64_NONAME_1_4W_SW_SPI {
  uint8_t page = 0;
 public:
  U8G2_SH1106_128X64_NONAME_1_4W_SW_SPI(int,int,int,int,int,int) {}
  void begin() {}
  void firstPage() { page = 0; }
  bool nextPage() { return ++page < 8; }
  void setFont(const uint8_t *) {}
  void drawStr(int,int,const char *) {}
  void drawLine(int,int,int,int) {}
};
