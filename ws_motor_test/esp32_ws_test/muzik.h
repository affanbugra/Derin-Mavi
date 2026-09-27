// =====================================================================================
//  MUZIK — GPIO12 pasif piezo (seri 220-270 ohm), ENGELLEMEYEN coklu sarki motoru.
//  PC "MZ<n>" ile n. sarkiyi calar, "MZ0" susturur (bkz. esp32_ws_test.ino muzikKomutu).
//  Durum yayini: MZK1,<calan sarki (0 = sus)>,<sarki adedi>,<buzzer hazir>.
//
//  SARKI NOTALARI AYRI DOSYADA: `sarkilar.h` (27.09 itibariyla repoda). Dosya yoksa firmware
//  yine derlenir, sarki adedi 0 olur (MZK1,0,0,..) ve PC "Sarki" dugmesini pasif gosterir.
//  sarkilar.h iki sey tanimlar:
//    constexpr int SARKI_ADEDI;
//    int sarkiKur(int no, muzik::Adim* cikti, int azami);   // no: 1..ADET, doner: adim sayisi
//
//  Neden boyle (24.09 "Kum Gibi" deneyimi, kum_gibi.h'den genellestirildi):
//   * delay() YOK: nota degisimleri loop()'ta millis() ile ilerler. Asil .ino ornekleri
//     calarken islemciyi 30-61 sn bekletiyordu; bu kartta motor darbeleri, nabiz bekcisi
//     (350 ms) ve lazer olu adam anahtari loop()'ta — durmak kolu/pan'i dondururdu.
//   * Lazerle AYNI LEDC zamanlayicisi YASAK: ledcWriteTone zamanlayiciyi yeniden kurar.
//     Cekirdek 3.3.x ledcAttach, frekansi ve cozunurlugu ayni olan zamanlayiciyi
//     PAYLASTIRIR; lazer 1000 Hz / 8 bit. Burada 2000 Hz / 10 bit ile baglanir ve
//     acilista zamanlayici numarasi lazerinkiyle karsilastirilir — ayniysa HIC calmaz.
//   * ACIL DURDUR (STOP / buton) susturur; kart acil kilitliyken MZ<n> reddedilir.
// =====================================================================================
#pragma once
#include <Arduino.h>
#include "esp32-hal-ledc.h"
#include "esp32-hal-periman.h"

namespace muzik {

constexpr uint8_t PIN = 12;
constexpr uint32_t KUR_FREK = 2000;   // lazerin 1000 Hz'inden FARKLI olmali (bkz. baslik)
constexpr uint8_t KUR_COZ = 10;
constexpr uint8_t NOTA_ARASI_MS = 12; // ayni notalar pes pese ayri duyulsun
constexpr int ADIM_AZAMI = 640;

struct Adim { uint16_t frekans, ms; };   // frekans 0 = sus

// Ses notasini (frekans, sure) ADIMLARA yazar: ses + kisa bosluk (ayni nota tekrarinda
// ayri duyulsun diye). Sus notasi tek adimdir. Doner: yeni adim sayisi.
inline int notaEkle(Adim* a, int n, int azami, uint16_t frekans, uint16_t ms) {
  if (frekans == 0) { if (n < azami) a[n++] = {0, ms}; return n; }
  const uint16_t bosluk = (ms / 8 < NOTA_ARASI_MS) ? ms / 8 : NOTA_ARASI_MS;
  if (n < azami) a[n++] = {frekans, (uint16_t)(ms - bosluk)};
  if (n < azami) a[n++] = {0, bosluk};
  return n;
}

}  // namespace muzik

#if defined(MUZIK_SARKI_DOSYASI)          // testler kendi kisa sarkilarini verir
#include MUZIK_SARKI_DOSYASI
#elif __has_include("sarkilar.h")
#include "sarkilar.h"
#else
constexpr int SARKI_ADEDI = 0;
inline int sarkiKur(int, muzik::Adim*, int) { return 0; }
#endif

namespace muzik {

inline Adim ADIMLAR[ADIM_AZAMI];   // baslat() doldurur: calinacak (frekans, ms) dizisi
inline int ADET = 0;
inline bool hazir = false;
inline int calan = 0;              // calan sarki (0 = susuyor)
inline int sira = -1;              // calan adim; -1 = susuyor
inline uint32_t notaBas = 0;       // calan adimin baslangici (millis)

inline int zamanlayici(uint8_t pin) {
  auto* b = (ledc_channel_handle_t*)perimanGetPinBus(pin, ESP32_BUS_TYPE_LEDC);
  return b ? (int)b->timer_num : -1;
}

inline void ses(uint16_t frekans) {
  if (hazir) ledcWriteTone(PIN, frekans);
}

// setup() icinde, LAZER PWM'i baglandiktan SONRA cagrilir.
inline void kur(uint8_t lazerPin) {
  hazir = false;
  sira = -1;
  calan = 0;
  if constexpr (SARKI_ADEDI <= 0) return;   // sarki yok: pine hic dokunma
  if (!ledcAttach(PIN, KUR_FREK, KUR_COZ)) return;
  const int bz = zamanlayici(PIN), lz = zamanlayici(lazerPin);
  if (bz < 0 || bz == lz) {             // lazerin zamanlayicisi: dokunma, sessiz kal
    ledcDetach(PIN);
    pinMode(PIN, OUTPUT);
    digitalWrite(PIN, LOW);
    return;
  }
  ledcWrite(PIN, 0);
  hazir = true;
}

inline void durdur() {
  if (sira < 0 && calan == 0) return;
  sira = -1;
  calan = 0;
  ses(0);
}

// no: 1..SARKI_ADEDI. Doner: nullptr (caliyor) ya da hata kodu (ERR,MZ<n>,<kod>).
inline const char* baslat(int no, uint32_t simdi) {
  if (no < 1 || no > SARKI_ADEDI) return "NO_SONG";
  if (!hazir) return "NO_BUZZER";
  const int n = sarkiKur(no, ADIMLAR, ADIM_AZAMI);
  if (n <= 0) return "NO_SONG";
  ADET = n;
  sira = 0;
  calan = no;
  notaBas = simdi;
  ses(ADIMLAR[0].frekans);
  return nullptr;
}

// loop() her turunda. Adim degisiminde tek ledcWriteTone.
inline void tik(uint32_t simdi) {
  if (sira < 0) return;
  if (uint32_t(simdi - notaBas) < ADIMLAR[sira].ms) return;
  notaBas += ADIMLAR[sira].ms;          // kayma birikmesin (loop gecikse de tempo korunur)
  if (++sira >= ADET) { durdur(); return; }
  if (ADIMLAR[sira].frekans != ADIMLAR[sira - 1].frekans) ses(ADIMLAR[sira].frekans);
}

}  // namespace muzik
