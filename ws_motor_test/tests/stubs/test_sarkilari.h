// Test sarkilari (muzik.h MUZIK_SARKI_DOSYASI ile): gercek notalar yerel sarkilar.h'de, repoda yok.
#pragma once
constexpr int SARKI_ADEDI = 2;
inline int sarkiKur(int no, muzik::Adim* a, int azami) {
  int n = 0;
  if (no == 1) {            // 880 x2 (ayni nota tekrari), sus, 1047
    n = muzik::notaEkle(a, n, azami, 880, 300);
    n = muzik::notaEkle(a, n, azami, 880, 300);
    n = muzik::notaEkle(a, n, azami, 0, 200);
    n = muzik::notaEkle(a, n, azami, 1047, 400);
  } else if (no == 2) {     // uzun: 659 ve 784 sirayla 40 kez (4 sn)
    for (int i = 0; i < 40; ++i) n = muzik::notaEkle(a, n, azami, i % 2 ? 784 : 659, 100);
  }
  return n;
}
