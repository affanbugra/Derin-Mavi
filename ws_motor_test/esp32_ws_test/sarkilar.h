// =====================================================================================
//  SARKILAR — muzik.h icin (27.09 itibariyla repoda).
//  Uretildi: sarkilar_uret.py (kaynaklardan AYNEN kopya, elle yazilmadi).
//   1: "Kum Gibi" (Ahmet Kaya) — eglence_kum_gibi/kum_gibi.h (Downloads/kum_gibi_gpio12(1).ino):
//      3310 girisi + 20 olcu devam (dortluk 640 ms), orijinal perde, bastaki 429 ms sessizlik yok.
//   2: "Akasya Duragi — Sinan Uckagit" — Downloads/sinan_uckagit_gpio12.ino (sesefektleri.com
//      MP3'unun 30 sn tek sesli uyarlamasi, kaynakta bir oktav tiz). Mutlak zamanlar AYNEN;
//      bastaki 490 ms sessizlik atildi (EVET'e basinca ses hemen gelsin), nota sonu bosluk
//      kaynaktaki gibi min(sure/8, 12 ms).
// =====================================================================================
#pragma once

constexpr int SARKI_ADEDI = 2;

namespace sarki_kum {
constexpr uint16_t DORTLUK_MS = 640;  // devam temposu (dortluk = 24 birim)
enum : uint16_t {
  SUS = 0, SOL5 = 784, SOL_D5 = 831, SI5 = 988, DO6 = 1047,
  RE6 = 1175, RE_D6 = 1245, FA6 = 1397, SOL6 = 1568
};
struct Nota { uint16_t frekans, ms; };
struct RitimliNota { uint16_t frekans; uint8_t birim; };   // dortluk 24, sekizlik 12, onaltilik 6
const Nota GIRIS[] = {
  {DO6,76}, {SUS,168}, {DO6,157}, {SUS,163}, {DO6,159}, {SUS,160},
  {DO6,67}, {RE6,75}, {DO6,70}, {RE6,72},
  {DO6,163}, {RE6,159}, {RE_D6,660}, {SUS,334},

  {RE_D6,156}, {RE6,160}, {DO6,162}, {RE6,159}, {DO6,160},
  {SI5,830}, {SUS,990},

  {RE6,323}, {DO6,329}, {SI5,331}, {SUS,327},
  {RE6,322}, {DO6,332}, {SI5,329},
  {RE_D6,497}, {RE6,151}, {SUS,5},
  {DO6,500}, {SI5,159}, {SOL_D5,473}, {SUS,393}
};
const RitimliNota DEVAM[] = {
  // Girisin devami (kaynak olculeri 5-8)
  {SUS,12}, {SOL_D5,12}, {SOL_D5,12}, {SOL_D5,12}, {SOL_D5,18}, {SI5,6}, {DO6,24},
  {DO6,18}, {SI5,6}, {DO6,18}, {SI5,6}, {SOL_D5,48},
  {SUS,12}, {DO6,12}, {SI5,12}, {SOL_D5,12}, {SUS,12}, {DO6,12}, {SI5,12}, {SOL_D5,12},
  {RE6,18}, {DO6,6}, {SI5,18}, {SOL_D5,6}, {SOL5,48},

  // Kita, ilk cumleler (9-12)
  {SUS,12}, {DO6,12}, {SI5,12}, {DO6,12}, {RE6,12}, {RE6,12}, {RE6,24},
  {SUS,12}, {RE6,24}, {FA6,12}, {RE_D6,18}, {RE6,6}, {DO6,24},
  {SUS,12}, {RE6,12}, {RE6,12}, {RE6,12}, {SOL6,18}, {FA6,6}, {RE_D6,12}, {RE6,6}, {DO6,6},
  {RE6,36}, {DO6,12}, {SI5,12}, {SOL_D5,12}, {SOL5,24},

  // Kitanin devami ve nakarata gecis (13-15, 17)
  {RE6,12}, {RE_D6,12}, {RE6,12}, {DO6,12}, {DO6,18}, {RE6,6}, {RE_D6,24},
  {RE6,12}, {RE_D6,24}, {DO6,12}, {DO6,18}, {SI5,6}, {SOL_D5,24},
  {SUS,12}, {SOL_D5,12}, {SOL_D5,12}, {SI5,12}, {RE6,18}, {DO6,6}, {SI5,12}, {SOL_D5,12},
  {SOL5,48}, {DO6,6}, {RE6,6}, {SI5,6}, {SOL_D5,6}, {SOL5,24},

  // Tam nakarat, ilk yari (18-21)
  {SUS,12}, {DO6,6}, {DO6,6}, {DO6,12}, {DO6,12}, {DO6,18}, {RE6,6}, {RE_D6,24},
  {SUS,6}, {RE_D6,12}, {RE6,6}, {RE6,12}, {DO6,12}, {SI5,48},
  {SUS,12}, {RE6,12}, {DO6,12}, {SI5,12}, {SUS,12}, {RE6,12}, {DO6,12}, {SI5,12},
  {RE_D6,6}, {RE6,18}, {DO6,18}, {SI5,6}, {SOL_D5,48},

  // Tam nakarat, ikinci yari ve bitis (22-25)
  {SUS,18}, {SOL_D5,6}, {SOL_D5,12}, {SOL_D5,12}, {SOL_D5,12}, {SI5,12}, {DO6,12}, {DO6,12},
  {DO6,6}, {SI5,18}, {DO6,12}, {SI5,12}, {SOL_D5,48},
  {SUS,12}, {DO6,12}, {SI5,12}, {SOL_D5,12}, {SUS,12}, {DO6,12}, {SI5,12}, {SOL_D5,12},
  {RE6,6}, {DO6,18}, {SI5,18}, {SOL_D5,6}, {SOL5,48}
};
// Kaynak betikle AYNI yuvarlama: (birim x dortluk + yarim) / 24.
inline uint16_t birimMs(uint8_t birim) {
  return (uint16_t)((uint32_t(birim) * DORTLUK_MS * 100UL + 1200UL) / 2400UL);
}
inline int kur(muzik::Adim* a, int azami) {
  int n = 0;
  for (const Nota& x : GIRIS) if (n < azami) a[n++] = {x.frekans, x.ms};   // giris: sureler AYNEN
  for (const RitimliNota& x : DEVAM) n = muzik::notaEkle(a, n, azami, x.frekans, birimMs(x.birim));
  return n;
}
}  // namespace sarki_kum

namespace sarki_sinan {
constexpr uint16_t TOPLAM_MS = 30000;
enum : uint16_t {
  SUS = 0,
  SOL4 = 392, LA4 = 440, LA_D4 = 466, SI4 = 494, DO5 = 523, DO_D5 = 554, RE5 = 587, MI5 = 659, FA_D5 = 740, SOL5 = 784, LA5 = 880, SI5 = 988, DO6 = 1047, RE6 = 1175
};
struct Nota { uint16_t baslangicMs, frekans; };   // kaynak MP3 baslangicina gore
const Nota melodi[] = {
  // 0-5 saniye
  {    0, SUS},
  {  490, MI5},
  {  670, SI5},
  {  930, SI5},
  { 1260, SI5},
  { 1590, SI5},
  { 1740, DO6},
  { 1880, SI5},
  { 2040, DO6},
  { 2200, RE6},
  { 2360, DO6},
  { 2500, SI5},
  { 2690, LA5},
  { 2870, SOL5},
  { 3240, SOL5},
  { 3400, SI5},
  { 3560, LA5},
  { 3700, SOL5},
  { 3880, LA5},
  { 4030, SUS},
  { 4290, SOL4},
  { 4560, SUS},
  { 4780, LA4},
  { 4920, LA_D4},
  // 5-10 saniye
  { 5030, SOL4},
  { 5100, LA4},
  { 5490, SUS},
  { 5760, MI5},
  { 6000, SI5},
  { 6170, SI5},
  { 6490, SI5},
  { 6820, SI5},
  { 6990, DO6},
  { 7100, SI5},
  { 7280, DO6},
  { 7440, RE6},
  { 7580, DO6},
  { 7750, SI5},
  { 7990, LA5},
  { 8130, SOL5},
  { 8490, SOL5},
  { 8640, SI5},
  { 8810, LA5},
  { 8950, SOL5},
  { 9120, LA5},
  { 9270, SUS},
  { 9540, SOL4},
  { 9740, SUS},
  // 10-15 saniye
  {10050, LA4},
  {10160, LA_D4},
  {10230, LA4},
  {10290, SOL4},
  {10400, LA4},
  {10840, SUS},
  {10950, LA4},
  {11170, LA_D4},
  {11260, SOL5},
  {11430, LA5},
  {11760, SI5},
  {12150, LA5},
  {12360, SI5},
  {12460, SOL5},
  {12650, FA_D5},
  {12710, SOL5},
  {12770, FA_D5},
  {12850, SUS},
  {12950, FA_D5},
  {13120, MI5},
  {13280, FA_D5},
  {13390, RE5},
  {13740, RE5},
  {13960, SUS},
  {14020, SOL4},
  {14140, LA_D4},
  {14210, SOL4},
  {14310, RE5},
  {14460, FA_D5},
  {14670, MI5},
  {14810, MI5},
  // 15-20 saniye
  {15190, SOL5},
  {15360, SOL5},
  {15610, FA_D5},
  {15680, RE5},
  {15990, RE5},
  {16240, RE5},
  {16400, RE5},
  {16560, RE5},
  {16760, SOL5},
  {16950, SOL5},
  {17030, FA_D5},
  {17180, MI5},
  {17410, MI5},
  {17580, SUS},
  {17810, LA4},
  {18190, DO_D5},
  {18310, RE5},
  {18630, RE5},
  {18980, DO_D5},
  {19130, RE5},
  {19450, RE5},
  {19700, RE5},
  {19900, RE5},
  // 20-25 saniye
  {20250, SUS},
  {20410, RE5},
  {20700, SI4},
  {20850, DO5},
  {20920, SI4},
  {21050, LA4},
  {21320, DO_D5},
  {21600, DO_D5},
  {21810, RE5},
  {22110, DO_D5},
  {22250, RE5},
  {22590, DO_D5},
  {22960, DO_D5},
  {23160, MI5},
  {23280, RE5},
  {23520, RE5},
  {23880, RE5},
  {24320, RE5},
  {24600, RE5},
  {24800, LA4},
  {24900, RE5},
  // 25-30 saniye
  {25100, LA4},
  {25230, RE5},
  {25550, RE5},
  {25940, SI4},
  {26120, DO5},
  {26190, SI4},
  {26340, LA4},
  {26610, DO_D5},
  {26890, DO_D5},
  {27230, RE5},
  {27390, DO_D5},
  {27530, RE5},
  {27900, DO_D5},
  {28220, DO_D5},
  {28380, MI5},
  {28570, RE5},
  {28640, MI5},
  {28780, DO_D5},
  {28860, RE5},
  {29230, MI5},
  {29520, SUS},
  {29590, MI5},
  {29880, SUS},
  {29920, SI5},
};
constexpr int ADET = sizeof(melodi) / sizeof(melodi[0]);
inline int kur(muzik::Adim* a, int azami) {
  int ilk = 0;
  while (ilk < ADET && melodi[ilk].frekans == SUS) ++ilk;          // bastaki sessizlik
  int n = 0;
  for (int i = ilk; i < ADET; ++i) {
    const uint16_t t0 = melodi[i].baslangicMs;
    const uint16_t t1 = (i + 1 < ADET) ? melodi[i + 1].baslangicMs : TOPLAM_MS;
    n = muzik::notaEkle(a, n, azami, melodi[i].frekans, (uint16_t)(t1 - t0));
  }
  return n;
}
}  // namespace sarki_sinan

inline int sarkiKur(int no, muzik::Adim* a, int azami) {
  if (no == 1) return sarki_kum::kur(a, azami);
  if (no == 2) return sarki_sinan::kur(a, azami);
  return 0;
}
