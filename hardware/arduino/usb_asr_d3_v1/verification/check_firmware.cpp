#include <cassert>
#include <iostream>
#include <vector>
#include <array>
#include <limits>
#include "stubs/Arduino.h"
#include "stubs/U8g2lib.h"
#include "stubs/DHT.h"
#include "stubs/Adafruit_NeoPixel.h"
#include "stubs/Servo.h"
#include "stubs/avr/interrupt.h"
#include "stubs/avr/pgmspace.h"
#include "stubs/util/atomic.h"
#include "../OldBoard_Main/HomeLink.h"

uint64_t hostUs=0;
int hostBoard=0;
uint8_t hostModes[2][20]={},hostPins[2][20]={};
int hostAnalog[2][20]={},hostPwm[2][20]={};
char hostKey='\0';
void (*hostWireEdge)(bool)=nullptr;
float hostTemperature=26,hostHumidity=50;
uint8_t PIND=0,PINB=0,PCIFR=0,PCMSK2=0,PCMSK0=0,PCICR=0;
HardwareSerial Serial;
uint8_t TIMSK1=0, EIFR=0, EIMSK=0, EICRA=0, TCCR1A=0, TCCR1B=0, TCCR1C=0, TIFR1=0;
uint16_t TCNT1=0, OCR1A=0;

#define HOME_HOST_TEST 1
namespace Old {
#include "../OldBoard_Main/OldBoard_Main.ino"
}
namespace New {
#include "../NewBoard_Expansion/NewBoard_Expansion.ino"
}

using Edge=std::pair<uint32_t,bool>;
std::vector<Edge> frameEdges(uint8_t command,uint8_t sequence,uint8_t copies=1,uint32_t start=0) {
  HomeLink::Transmitter tx;
  assert(tx.start(command,sequence,copies,start));
  std::vector<Edge> edges={{start,true}};
  uint32_t now=start;
  for(unsigned n=0;tx.active() && n<30000;n++) {
    now+=100;
    if(tx.update(now)) edges.push_back({now,tx.level()});
  }
  assert(!tx.active());
  return edges;
}

unsigned feed(HomeLink::Receiver &rx,const std::vector<Edge> &edges,uint8_t expected=0) {
  unsigned count=0;
  for(auto e:edges) {
    rx.onEdge(e.second,e.first);
    HomeLink::Packet p;
    while(rx.pop(p)) { if(expected) assert(p.command==expected); ++count; }
  }
  return count;
}

std::vector<Edge> rawFrame(std::array<uint8_t,4> bytes) {
  std::vector<Edge> edges;
  uint32_t at=100;
  edges.push_back({at,true}); at+=HomeLink::SYNC_US;
  edges.push_back({at,false}); at+=HomeLink::SYNC_LOW_US;
  for(auto byte:bytes) for(int b=7;b>=0;b--) {
    edges.push_back({at,true}); at+=(byte&(1<<b)) ? HomeLink::ONE_US : HomeLink::ZERO_US;
    edges.push_back({at,false}); at+=HomeLink::BIT_LOW_US;
  }
  return edges;
}

void checkProtocol() {
  for(uint8_t cmd=1;cmd<=15;cmd++) for(uint8_t seq: std::array<uint8_t,4>{0,1,127,255}) {
    HomeLink::Receiver rx; rx.begin(false,0);
    assert(feed(rx,frameEdges(cmd,seq),cmd)==1);
    HomeLink::Receiver repeat; repeat.begin(false,0);
    assert(feed(repeat,frameEdges(cmd,seq,2),cmd)==2);
    HomeLink::Receiver wrap; wrap.begin(false,0xffffc000);
    assert(feed(wrap,frameEdges(cmd,seq,1,0xffffc000),cmd)==1);
  }
  auto edges=frameEdges(10,19);
  for(size_t cut=1;cut<edges.size();cut++) {
    HomeLink::Receiver rx;
    rx.begin(edges[cut-1].second,edges[cut].first-1);
    assert(feed(rx,{edges.begin()+cut,edges.end()})==0);
  }
  for(size_t drop=0;drop<edges.size();drop++) {
    auto broken=edges; broken.erase(broken.begin()+drop);
    HomeLink::Receiver rx; rx.begin(false,0);
    assert(feed(rx,broken)==0);
  }
  std::array<uint8_t,4> bytes={HomeLink::MAGIC,1,23,0};
  bytes[3]=HomeLink::crc8(bytes.data(),3);
  for(unsigned bit=0;bit<32;bit++) {
    auto corrupt=bytes; corrupt[bit/8]^=1u<<(bit%8);
    HomeLink::Receiver rx; rx.begin(false,0);
    assert(feed(rx,rawFrame(corrupt))==0);
  }
  for(unsigned trial=0;trial<100;trial++) {
    auto jitter=edges;
    for(size_t n=0;n<jitter.size();n++) {
      const int offset=int((trial*197+n*89)%1001)-500;
      jitter[n].first=uint32_t(jitter[n].first+1000+offset);
    }
    HomeLink::Receiver rx; rx.begin(false,0);
    assert(feed(rx,jitter,10)==1);
  }
  HomeLink::Receiver legacy; legacy.begin(false,0);
  uint32_t t=100;
  for(unsigned n=0;n<10;n++) {
    legacy.onEdge(true,t); t+=90000; legacy.onEdge(false,t); t+=90000;
  }
  HomeLink::Packet ignored; assert(!legacy.pop(ignored));
  HomeLink::Receiver stuck; stuck.begin(false,0); stuck.onEdge(true,10);
  assert(stuck.busy(100)); stuck.expire(60000); assert(!stuck.busy(60000));
  std::cout<<"PASS protocol: 1..15, sequences, repeats, timer wrap, every startup cut, every dropped edge, 32 corrupt bits, jitter, legacy rejection, stuck line\n";
}

void wire(bool high) {
  hostPins[0][5]=high;
  PIND=high ? uint8_t(PIND|_BV(PD5)) : uint8_t(PIND&~_BV(PD5));
  Old::PCINT2_vect();
}
void runMs(uint32_t ms,bool runNew=true) {
  const uint64_t end=hostUs+uint64_t(ms)*1000;
  while(hostUs<end) {
    hostBoard=0; Old::loop();
    if(runNew) { hostBoard=1; New::loop(); }
    hostUs+=200;
  }
}
void press(char key) { hostKey=key; runMs(45); hostKey='\0'; runMs(35); }
void waitIdle() {
  for(unsigned n=0;n<2000;n++) {
    if(!New::linkTx.active() && New::commandHead==New::commandTail && !New::rainNeedsSend && !New::soilNeedsSend) return;
    runMs(1);
  }
  assert(false);
}
void rxSample(bool high) {
  PIND = high ? uint8_t(PIND | _BV(PD3)) : uint8_t(PIND & ~_BV(PD3));
  TCNT1 = OCR1A;
  New::TIMER1_COMPA_vect();
}
void rxByte(uint8_t ch, bool goodStop=true) {
  PIND &= uint8_t(0xffu ^ _BV(PD3));
  New::INT1_vect();
  rxSample(false);
  for (unsigned b=0;b<8;++b) rxSample((ch & (1u<<b))!=0);
  rxSample(goodStop);
}
void injectAsr(const char *token) { while (*token) rxByte(uint8_t(*token++)); }
void asr(const char *token,uint32_t wait=1200) { injectAsr(token); runMs(wait); }
void sampleClimate(float temp) {
  waitIdle(); hostTemperature=temp;
  Old::lastSensorRead=millis()-2000;
  runMs(50);
}

void checkPairedFirmware() {
  hostAnalog[1][A0]=900;hostAnalog[1][A1]=850;
  hostWireEdge=wire;
  hostBoard=0; Old::setup();
  hostBoard=1; New::setup();
  runMs(2500);
  assert(Old::sensorOk && !Old::fanState && Old::rainKnown && !Old::rainWet && Old::soilKnown && !Old::soilWet);

  hostBoard=0;
  for(char k:std::string("123A456B789C*0#D")) {
    hostKey=k; assert(Old::scanKeypadRaw()==k);
    assert(hostModes[0][0]==INPUT && hostModes[0][1]==INPUT && hostModes[0][12]==INPUT);
  }
  hostKey='\0';
  assert(Old::scanKeypadRaw()=='\0');
  for(char k:std::string("1234#")) press(k);
  assert(Old::doorOpen && Old::doorServo.angle==90);
  runMs(4100); assert(!Old::doorOpen && Old::doorServo.angle==0);

  waitIdle();
  asr("do\r\n"); assert(Old::doorOpen);
  asr("DC\n"); assert(!Old::doorOpen);
  asr("FO\n"); assert(Old::fanState && Old::fanMode==1 && hostPwm[0][6]==150);
  asr("FC\n"); assert(!Old::fanState && Old::fanMode==2);
  sampleClimate(30); assert(!Old::fanState);
  press('A'); assert(Old::fanMode==0 && Old::fanState);
  sampleClimate(27.5); assert(Old::fanState);
  sampleClimate(26.9f); assert(!Old::fanState);
  asr("LO\n"); assert(Old::rgbLightState && Old::lightMode==1);
  asr("LC\n"); assert(!Old::rgbLightState && Old::lightMode==2);
  hostPins[0][A2]=HIGH; runMs(100); assert(!Old::rgbLightState);
  press('B'); assert(Old::rgbLightState && Old::lightMode==0);
  Old::fanMode=1;Old::lightMode=2;press('D');
  assert(Old::fanMode==0 && Old::lightMode==0 && !Old::fanState && Old::rgbLightState);
  asr("FC\nLC\n",2000); assert(Old::fanMode==2 && Old::lightMode==2);
  asr("AUTO\n"); assert(Old::fanMode==0 && Old::lightMode==0);

  waitIdle();
  Old::clearCode("READY");press('9');press('#');
  assert(Old::soundPattern==Old::SOUND_DENIED);
  const auto sent=hostUs;
  Serial.inject("DO\n");
  while(!Old::doorOpen && hostUs-sent<1000000) runMs(1);
  assert(Old::doorOpen && Old::soundPattern==Old::SOUND_DENIED);
  const uint32_t openedAt=Old::doorOpenedAt;
  runMs(1000); assert(Old::doorOpenedAt==openedAt); // Duplicate does not extend the timer.
  std::cout<<"PASS linked action while wrong-password sound active; simulated first-copy latency "<<(openedAt-uint32_t(sent/1000))<<" ms\n";
  runMs(3200); assert(!Old::doorOpen);

  hostAnalog[1][A0]=300;hostAnalog[1][A1]=300;
  runMs(1700);assert(Old::rainWet && Old::soilWet);
  hostAnalog[1][A0]=900;hostAnalog[1][A1]=850;
  runMs(1700);assert(!Old::rainWet && !Old::soilWet);
  waitIdle(); Serial.outgoing.clear();
  hostPins[1][2]=HIGH;runMs(1200);
  assert(!strcmp(Old::keypadStatus,"BELL") && !Old::doorOpen);
  runMs(1500);
  const std::string marker="TOUCH_DOORBELL,QUEUED";
  auto pos=Serial.outgoing.find(marker);
  assert(pos!=std::string::npos && Serial.outgoing.find(marker,pos+1)==std::string::npos);
  hostPins[1][2]=LOW;runMs(50);

  waitIdle();
  Serial.inject("DOXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\n");runMs(1200);
  assert(!Old::doorOpen);
  assert(Serial.outgoing.find("USB_UNKNOWN:")!=std::string::npos);

  hostBoard=1;New::echoPhase=1;New::echoStartedAt=micros();
  PINB|=_BV(PB1);New::PCINT0_vect();hostUs+=580;
  PINB&=uint8_t(0xffu ^ _BV(PB1));New::PCINT0_vect();New::serviceUltrasonic();
  assert(New::distanceTenthsCm==100 && New::personNear);
  New::echoPhase=1;New::echoStartedAt=micros();hostUs+=31000;New::serviceUltrasonic();
  assert(New::distanceTenthsCm==-1 && !New::personNear);

  runMs(16000,false);assert(!Old::rainKnown && !Old::soilKnown);
  Old::doorOpen=true;Old::doorOpenedAt=0xfffffc17u; // millis rollover.
  hostUs=(uint64_t(0x100000000ULL)+500)*1000;
  Old::serviceDoorAndRemoteStates();assert(Old::doorOpen);
  hostUs+=3000000;Old::serviceDoorAndRemoteStates();assert(!Old::doorOpen);
  std::cout<<"PASS firmware: all keys incl. D12 row, PIN/auto-close, ASR 1..6, AUTO keys/tokens, fan hysteresis, rain/soil forwarding, touch bell only, serial overflow, echo timeout, stale states, millis wrap\n";
}

void checkD3Receiver() {
  hostBoard=1;
  New::AsrD3Rx::begin();
  assert(hostModes[1][3]==INPUT_PULLUP && TCCR1A==0 && TCCR1B==_BV(CS11));
  for (unsigned c=0;c<256;++c) {
    TCNT1=uint16_t(65500+c);
    rxByte(uint8_t(c));
    assert(New::AsrD3Rx::read()==int(c));
    assert(New::AsrD3Rx::read()==-1);
    assert((TIMSK1&_BV(OCIE1A))==0 && (EIMSK&_BV(INT1))!=0);
  }
  rxByte('D',false); assert(New::AsrD3Rx::takeErrors()==1);
  assert(!New::AsrD3Rx::available());
  for(unsigned n=0;n<64;++n) rxByte('X');
  assert(New::AsrD3Rx::takeErrors()==2 && !New::AsrD3Rx::available());
  PIND&=uint8_t(0xffu ^ _BV(PD3)); New::INT1_vect();
  TCNT1=uint16_t(OCR1A+105); New::TIMER1_COMPA_vect();
  assert(New::AsrD3Rx::takeErrors()==4);
  PIND&=uint8_t(0xffu ^ _BV(PD3)); New::INT1_vect(); rxSample(true);
  assert(!New::AsrD3Rx::available() && New::AsrD3Rx::takeErrors()==0);
  std::cout<<"PASS D3 RX: all 256 bytes, timer wrap, stop error, overflow flush, late sample, false start\n";
}

void checkUsbAndIsolation() {
  waitIdle(); asr("DC\n"); Serial.outgoing.clear();
  Serial.inject("PING\n"); runMs(50);
  assert(Serial.outgoing.find("PONG,USB_ASR_D3_V1")!=std::string::npos);
  Serial.inject("LO\n"); runMs(1200); assert(Old::rgbLightState);
  Serial.inject("LC\n"); runMs(1200); assert(!Old::rgbLightState);
  Serial.inject("FO\n"); runMs(1200); assert(Old::fanMode==1);
  Serial.inject("FC\n"); runMs(1200); assert(Old::fanMode==2);
  Serial.inject("AUTO\n"); runMs(1200); assert(Old::fanMode==0 && Old::lightMode==0);
  waitIdle();
  injectAsr("D"); Serial.inject("LO\n"); runMs(10); injectAsr("O\n"); runMs(2000);
  assert(Old::doorOpen && Old::rgbLightState);
  asr("DC\n");
  // No USB idle execution, and timed-out tails never become commands.
  Serial.inject("D"); runMs(1100); Serial.inject("DO\n"); runMs(1200);
  assert(!Old::doorOpen);
  Serial.inject("DO"); runMs(100); assert(!Old::doorOpen);
  Serial.inject("\n"); runMs(1200); assert(Old::doorOpen);
  asr("DC\n");
  injectAsr("D"); runMs(5); rxByte('O',false); runMs(100);
  assert(!Old::doorOpen);
  asr("DO"); assert(Old::doorOpen); asr("DC\n");
  Serial.inject("FACE_OPEN\n"); runMs(1200); assert(Old::doorOpen);
  const auto openedAt=Old::doorOpenedAt;
  Serial.inject("FACE_OPEN\n"); runMs(1200); assert(Old::doorOpenedAt==openedAt);
  runMs(3200); assert(!Old::doorOpen);
  Serial.inject("FACE_OPEN\n"); runMs(1200); assert(!Old::doorOpen);
  runMs(5000); Serial.inject("FACE_OPEN\n"); runMs(1200); assert(Old::doorOpen);
  assert(Serial.outgoing.find("COOLDOWN")!=std::string::npos);
  assert(Serial.outgoing.find("SENT_NO_ACK")!=std::string::npos);
  // Bounded command queue rejects excess commands rather than overwriting.
  waitIdle();
  for (unsigned i=0;i<7;++i) assert(New::enqueueCommand(5));
  assert(!New::enqueueCommand(6)); runMs(6500);
  std::cout<<"PASS USB/ASR: PING, lights/fan/auto, source isolation, required delimiter, timeout, framing-error recovery, face cooldown, queue full, honest TX status\n";
}
int main() { checkProtocol();checkD3Receiver();checkPairedFirmware();checkUsbAndIsolation(); }
