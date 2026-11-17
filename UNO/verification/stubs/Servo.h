#pragma once
class Servo {
 public:
  int angle = 0;
  void attach(int) {}
  void write(int v) { angle=v; }
};
