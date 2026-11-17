#pragma once
#define NEO_GRB 0
#define NEO_KHZ800 0
class Adafruit_NeoPixel {
 public:
  int shows = 0;
  Adafruit_NeoPixel(int,int,int) {}
  void begin() {}
  void setBrightness(int) {}
  void clear() {}
  void show() { ++shows; }
  uint32_t Color(int r,int g,int b) { return uint32_t(r<<16 | g<<8 | b); }
  void setPixelColor(int,uint32_t) {}
};
