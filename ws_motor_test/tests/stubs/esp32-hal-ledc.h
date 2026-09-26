#pragma once
#include <stdint.h>
typedef struct { uint8_t pin; uint8_t channel; uint8_t channel_resolution; uint8_t timer_num; uint32_t freq_hz; } ledc_channel_handle_t;
