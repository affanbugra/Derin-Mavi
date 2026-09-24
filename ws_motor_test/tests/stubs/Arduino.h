#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string>
#define ARDUINO_USB_CDC_ON_BOOT 1
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT 0
extern uint32_t fakeUs;
extern int physicalPulses;
extern int panPulses,panDirLevel,panEnLevel;
inline uint32_t micros(){return fakeUs;}
inline uint32_t millis(){return fakeUs/1000;}
inline void delayMicroseconds(uint32_t us){fakeUs+=us;}
inline void pinMode(int,int){}
#define INPUT_PULLUP 2
// Lazer (GPIO 18) ve acil stop butonu (GPIO 15) taklidi: lazerCikis = pine giden son
// seviye/duty (0 = sonuk), estopSeviye = butonun okunan seviyesi (HIGH = basili degil).
extern int lazerCikis,estopSeviye;
extern bool ledcBasarili;
inline void digitalWrite(int pin,int level){if(pin==4 && level==HIGH)++physicalPulses;if(pin==10 && level==HIGH)++panPulses;if(pin==11)panDirLevel=level;if(pin==16)panEnLevel=level;if(pin==18)lazerCikis=level?256:0;}
inline int digitalRead(int pin){return pin==15?estopSeviye:LOW;}
inline bool ledcAttach(int,int,int){return ledcBasarili;}
inline void ledcWrite(int pin,int duty){if(pin==18)lazerCikis=duty;}
class Stream {
 public:
  std::string incoming,out;
  void begin(int){}
  int available(){return (int)incoming.size();}
  int availableForWrite(){return 1024;}
  int read(){char c=incoming[0];incoming.erase(0,1);return c;}
  void print(const char* s){out+=s;}
  void println(const char* s){out+=s;out+='\n';}
  size_t write(uint8_t* s,int n){out.append((char*)s,n);return n;}
};
extern Stream Serial,Serial0;
