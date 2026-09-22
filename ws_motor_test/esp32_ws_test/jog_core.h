#pragma once
#include <stdint.h>

// Shared by the ESP32 sketch and desktop tests. No Arduino dependency.
class JogCore {
 public:
  JogCore(int32_t upperSteps, bool wiringChecked,
          uint32_t intervalUs = 20000, uint32_t timeoutMs = 250)
      : upper_(upperSteps), configured_(wiringChecked && upperSteps > 0),
        intervalUs_(intervalUs), timeoutMs_(timeoutMs) {
    if (intervalUs < 1000 || timeoutMs < 10) configured_ = false;
  }

  void command(char key, uint32_t nowMs) {
    if (key == 'X') {
      direction_ = 0;
      neutralRequired_ = false;
      return;
    }
    if (key == 'H') {
      // Never permit an in-session re-zero to bypass the travel limit.
      if (configured_ && !homed_) {
        position_ = 0;
        homed_ = true;
        direction_ = 0;
        neutralRequired_ = true;  // Require X after HOME, before W/S.
      }
      return;
    }
    if (!configured_ || !homed_ || neutralRequired_) return;
    if (key == 'W' || key == 'S') {
      direction_ = (key == 'W') ? 1 : -1;
      lastCommandMs_ = nowMs;
    }
  }

  void checkTimeout(uint32_t nowMs) {
    if (direction_ && uint32_t(nowMs - lastCommandMs_) >= timeoutMs_) {
      direction_ = 0;
      neutralRequired_ = true;
    }
  }

  int nextStep(uint32_t nowMs, uint32_t nowUs) {
    checkTimeout(nowMs);
    if (!configured_ || !homed_ || neutralRequired_ || !direction_) return 0;
    if (uint32_t(nowUs - lastStepUs_) < intervalUs_) return 0;
    if ((direction_ > 0 && position_ >= upper_) ||
        (direction_ < 0 && position_ <= 0)) return 0;
    return direction_;
  }

  // Call immediately AFTER emitting exactly one STEP pulse.
  void pulseEmitted(int direction, uint32_t nowUs) {
    position_ += direction;
    lastStepUs_ = nowUs;  // Never catch up missed time with a burst of pulses.
  }

  int32_t position() const { return position_; }
  int32_t upper() const { return upper_; }
  bool configured() const { return configured_; }
  bool homed() const { return homed_; }
  bool neutralRequired() const { return neutralRequired_; }

 private:
  int32_t upper_;
  bool configured_;
  uint32_t intervalUs_, timeoutMs_;
  int32_t position_ = 0;
  bool homed_ = false, neutralRequired_ = true;
  int direction_ = 0;
  uint32_t lastCommandMs_ = 0, lastStepUs_ = 0;
};
