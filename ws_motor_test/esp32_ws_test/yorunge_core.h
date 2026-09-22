#pragma once
#include <stdint.h>
#include <math.h>
// YORUNGE KIPI (otonom takip) — "su KONUMA git" degil, "su konumdan su HIZLA ilerle".
//
// NEDEN: konum kipinde PC her 40 ms'de yeni bir hedef verir; motor hedefe yeni komut
// gelmeden varinca YAVASLAYIP DURUR, sonra tekrar hizlanir. Yavas hareket eden hedefte
// (elde tasinan drone) bu saniyede birkac hizlan-dur dongusu demek ve sahada namluyu
// titretiyordu. Burada PC (p, v) verir; kart referansi p + v*t olarak HER DONGUDE
// kendisi ilerletir ve motoru o hizda AKITIR. Varis ani yoktur.
//
//   referans   p_ref(t) = p0 + v0 * (t - t0)            (eksen sinirina kirpilir)
//   hiz komutu v_ist    = v0 + KAZANC * (p_ref - konum)  (ileri besleme + konum duzeltme)
//   motor hizi v       -> v_ist'e IVME sinirinda yaklasir; uca fren mesafesinden
//                         yakinsa ucta duracak hizla sinirlanir
//
// GUVENLIK: ZAMAN_ASIMI_US icinde yeni (p, v) gelmezse hedef hiz 0 olur, motor
// ivme sinirinda YUMUSAKCA durur ve kip kendini kapatir. (Saf hiz komutunda iletisim
// koparsa motor sonsuza kadar kosardi.) Nabiz (H) kesilirse eksen zaten kapanir.
//
// Birim: DARBE ve darbe/sn. Aci -> darbe cevirimi eksen cekirdeginde (kalibrasyon /
// disli orani) yapilir; bu sinif eksenden bagimsizdir.
class Yorunge {
 public:
  static constexpr uint32_t ZAMAN_ASIMI_US = 150000;
  // Konum duzeltme kazanci (1/sn). ~8: 1 derecelik fark ~1/8 sn'de kapanir; PC'nin
  // 25-50 Hz guncellemesi ve 30 ms kamera gecikmesiyle rahatca kararli.
  static constexpr float KAZANC = 8.0f;

  bool aktif = false;
  float hiz = 0.0f;               // anlik motor hizi (darbe/sn, isaretli)

  // Yeni (konum, hiz) — darbe cinsinden. Kip kapaliysa acar (motor duruyor kabul edilir).
  void guncelle(double p, double v, uint32_t us) {
    if (!aktif) { aktif = true; hiz = 0.0f; faz_ = 0.0f; sonUs_ = us; }
    p0_ = p; v0_ = v; t0_ = us;
  }
  void durdur() { aktif = false; hiz = 0.0f; faz_ = 0.0f; }
  bool zamanAsimi(uint32_t us) const { return aktif && uint32_t(us - t0_) > ZAMAN_ASIMI_US; }

  // Her dongude cagrilir. Doner: bu an atilacak TEK darbenin yonu (-1/0/+1).
  // Cagiran darbeyi atar ve konumu kendisi gunceller (eksen cekirdegi sayar).
  int adim(uint32_t us, int32_t konum, double vmax, double ivme, int32_t alt, int32_t ust) {
    if (!aktif) return 0;
    float dt = uint32_t(us - sonUs_) * 1e-6f;
    sonUs_ = us;
    if (dt > 0.01f) dt = 0.01f;           // uzun kesinti sonrasi tek adimda sicrama yok
    float hedefHiz = 0.0f;
    const bool asim = zamanAsimi(us);
    if (!asim) {
      double tr = uint32_t(us - t0_) * 1e-6;
      double pref = p0_ + v0_ * tr;
      if (pref < alt) pref = alt;
      if (pref > ust) pref = ust;
      double e = pref - (konum + faz_);  // faz_: atilmamis darbe kesri
      hedefHiz = (float)(v0_ + KAZANC * e);
      // Referans uca dayandiysa ileri besleme o yonde anlamsiz: yalniz duzeltme kalir.
      if ((pref >= ust && v0_ > 0) || (pref <= alt && v0_ < 0)) hedefHiz = (float)(KAZANC * e);
    }
    const float vm = (float)vmax, a = (float)ivme;
    if (hedefHiz > vm) hedefHiz = vm;
    if (hedefHiz < -vm) hedefHiz = -vm;
    // Uca fren: kalan mesafede durabilecek hizdan hizli gidilmez.
    float ustFren = sqrtf(2.0f * a * (float)fmax(0.0, (double)(ust - konum)));
    float altFren = sqrtf(2.0f * a * (float)fmax(0.0, (double)(konum - alt)));
    if (hedefHiz > ustFren) hedefHiz = ustFren;
    if (hedefHiz < -altFren) hedefHiz = -altFren;
    float dv = hedefHiz - hiz, dvMax = a * dt;
    if (dv > dvMax) dv = dvMax;
    if (dv < -dvMax) dv = -dvMax;
    hiz += dv;
    if (asim && fabsf(hiz) < 1.0f) { durdur(); return 0; }
    faz_ += hiz * dt;
    // Dongu darbe hizindan yavas kalirsa biriken kesir patlama yapmasin.
    if (faz_ > 1.5f) faz_ = 1.5f;
    if (faz_ < -1.5f) faz_ = -1.5f;
    if (faz_ >= 1.0f) {
      if (konum + 1 > ust) { faz_ = 0.0f; hiz = 0.0f; return 0; }
      faz_ -= 1.0f; return 1;
    }
    if (faz_ <= -1.0f) {
      if (konum - 1 < alt) { faz_ = 0.0f; hiz = 0.0f; return 0; }
      faz_ += 1.0f; return -1;
    }
    return 0;
  }

 private:
  double p0_ = 0, v0_ = 0;
  uint32_t t0_ = 0, sonUs_ = 0;
  float faz_ = 0.0f;
};
