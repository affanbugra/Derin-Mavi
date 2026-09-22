#pragma once
#include <stdint.h>
#include <math.h>
#include <stdlib.h>
// PAN (yatay) ekseni — AYNI ESP32-S3 uzerinde, tilt ile birlikte.
//
// Tilt'ten farki: pan NORMAL, sabit oranli carkli eksendir (motor 15 disli ->
// cark 83 disli). Aci -> darbe donusumu DOGRUSALDIR, olculmus tablo gerekmez.
// Konum ISARETLIDIR: azimut "sarmasiz" (birikimli) gonderilir; 350 -> 10 derece
// gecisinde PC 370 der, motor kisa yoldan doner (bkz. Derin-Mavi protokol.py).
//
// Hareket mantigi MotionCore ile aynidir: ivmeli profil, her cevrimde en fazla bir
// darbe, ve hareket halinde gelen yeni hedef DURMADAN uygulanir (retarget).
// ⚠ ESP32 pan'in da yerini OLCMEZ; darbe sayar. Acilista 0 = acilis konumu. "PR"
//   mevcut konumu 0 kabul ettirir.
class PanCore {
 public:
  static constexpr double STEP_PER_DEG = 6400.0 * (83.0 / 15.0) / 360.0;   // ~98.37
  // Sarmasiz azimut icin pay ama kablo sarmasina karsi yazilimsal sinir.
  static constexpr double ACI_SINIR = 400.0;
  // Varsayilan profil (PC PZ ile degistirir): 60 derece/sn, 500 derece/sn^2.
  // Tavanlar tilt'ten YUKSEK: 83/15 rediksiyon yuzunden pan derece basina ~2.2 kat
  // fazla darbe ister. 5000 darbe/sn tavani pan'i ~50 derece/sn'e kilitliyordu
  // (sahada "yatay cok yavas"). 12000 darbe/sn = ~122 derece/sn; dongu her
  // cevrimde en fazla bir darbe atar, 83 us aralik 20 us darbe + seri okuma icin yeter.
  static constexpr double HIZ_VARSAYILAN = 60.0 * STEP_PER_DEG;
  static constexpr double IVME_VARSAYILAN = 500.0 * STEP_PER_DEG;
  static constexpr double HIZ_TABAN = 100, HIZ_TAVAN = 12000;
  static constexpr double IVME_TABAN = 200, IVME_TAVAN = 150000;

  int32_t pos = 0, target = 0;
  double maxSpeed = HIZ_VARSAYILAN, accel = IVME_VARSAYILAN;

  bool moving() const { return pos != target; }
  static int32_t steps(double deg) { return (int32_t)lround(deg * STEP_PER_DEG); }
  double angle() const { return pos / STEP_PER_DEG; }
  double goal() const { return target / STEP_PER_DEG; }

  void stop() { target = pos; speed_ = 0; pendingSet_ = false; }
  void zero() { stop(); pos = 0; target = 0; }

  // Mutlak aci. Aralik disi / sayi degilse false (komut reddedilir).
  bool go(double deg, uint32_t us) {
    if (!isfinite(deg) || fabs(deg) > ACI_SINIR) return false;
    int32_t t = steps(deg);
    if (moving()) retarget(t, us); else begin(t, us);
    return true;
  }
  bool profile(double h, double iv) {
    if (moving()) return false;
    if (!isfinite(h) || !isfinite(iv) || h < HIZ_TABAN || h > HIZ_TAVAN ||
        iv < IVME_TABAN || iv > IVME_TAVAN) return false;
    maxSpeed = h; accel = iv; return true;
  }
  int next(uint32_t us) const {
    if (!moving() || uint32_t(us - lastPulse_) < interval_) return 0;
    return target > pos ? 1 : -1;
  }
  // YORUNGE KIPI darbesi: sayac ilerler, konum kipi bosta kalir.
  void izle(int d) { pos += d; target = pos; speed_ = 0; pendingSet_ = false; }
  static constexpr int32_t SINIR = (int32_t)(ACI_SINIR * STEP_PER_DEG);
  // Tam olarak BIR fiziksel darbeden hemen sonra cagrilir.
  void emitted(int d, uint32_t us) {
    pos += d; lastPulse_ = us;
    if (pos == target) {
      speed_ = 0;
      if (pendingSet_) { pendingSet_ = false; begin(pending_, us); }
    } else schedule();
  }

 private:
  double speed_ = 0;
  uint32_t lastPulse_ = 0, interval_ = 0;
  int32_t pending_ = 0;
  bool pendingSet_ = false;
  static constexpr int32_t SINIR_DARBE = (int32_t)(ACI_SINIR * STEP_PER_DEG);

  void begin(int32_t t, uint32_t us) { target = t; speed_ = 0; lastPulse_ = us; if (moving()) schedule(); }
  // MotionCore::retarget ile ayni: ayni yonde ve fren mesafesinin otesindeyse hiz
  // korunur; degilse izin verilen ivmeyle en kisa frenle durulup yeni hedefe gidilir.
  void retarget(int32_t t, uint32_t us) {
    int dir = target > pos ? 1 : -1;
    int32_t fren = (int32_t)ceil(speed_ * speed_ / (2.0 * accel));
    int32_t enErken = pos + dir * fren;
    if (enErken > SINIR_DARBE) enErken = SINIR_DARBE;
    if (enErken < -SINIR_DARBE) enErken = -SINIR_DARBE;
    if ((int64_t)(t - pos) * dir > 0 && (int64_t)(t - enErken) * dir >= 0) {
      target = t; pendingSet_ = false; return;
    }
    if (enErken == pos) { pendingSet_ = false; begin(t, us); return; }
    target = enErken; pending_ = t; pendingSet_ = true;
  }
  void schedule() {
    double remaining = fabs((double)(target - pos));
    speed_ = fmin(maxSpeed, fmin(sqrt(speed_ * speed_ + 2 * accel), sqrt(2 * accel * remaining)));
    interval_ = (uint32_t)ceil(1000000.0 / speed_);
  }
};
