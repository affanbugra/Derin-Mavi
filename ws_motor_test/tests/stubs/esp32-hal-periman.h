#pragma once
#include "esp32-hal-ledc.h"
enum { ESP32_BUS_TYPE_LEDC = 1 };
extern int buzzerZamanlayici;
// Lazer (18) zamanlayici 0'da; buzzer (12) testin verdigi zamanlayicida.
inline void* perimanGetPinBus(int pin,int){static ledc_channel_handle_t l{18,0,8,0,1000},b{12,1,10,1,2000};if(pin==18)return &l; if(pin==12){b.timer_num=(uint8_t)buzzerZamanlayici;return &b;} return nullptr;}
