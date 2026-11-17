#pragma once
#define DHT11 11
class DHT {
 public:
  DHT(int,int) {}
  void begin() {}
  float readHumidity() { return hostHumidity; }
  float readTemperature() { return hostTemperature; }
};
