# -*- coding: utf-8 -*-
"""DERIN MAVI — KOMUT ACISI -> KAMERA ACISI EGRISI (kol-biyel mekanizmasi).

NEDEN VAR. Tilt karti "kol acisi" konusur (G<derece>, kalibrasyon 0..60), ama
takip KAMERANIN ne kadar dondugune baglidir. Kol-biyel mekanizmasinda ikisi ayni
degildir. Gercek kartta kamera goruntusunun kaymasi olculerek cikarildi
(tilt_yon_testi.py egri, 2026-09-21):

    komut  2 ->  6 : yerel oran -0.60   <- TERS: kol yukari, kamera ASAGI
    komut  6 -> 10 : yerel oran -0.08   <- OLU NOKTA
    komut 10 -> 18 : 0.14 .. 0.24
    komut 18 -> 42 : 0.33 .. 0.45       <- en verimli bolge
    komut 42 -> 50 : ~0.20
    komut 50 -> 58 : olculemedi (guven < 0.05)

Sahada otonom takip "hedef merkezin ustundeyken namlu asagi indi, kol uca dayandi"
diye bozuldu. Sebep bu egri: ~8 derecenin altinda isaret TERSINE doner, yani
kontrolcunun her duzeltmesi hatayi BUYUTUR ve kol uca kacar. Buna ek olarak oran
bolgeden bolgeye 3 kat degistigi icin TEK bir kazanc her yerde dogru olamaz.

Bu modul iki isi yapar:
  1. GECERLI ARALIK: egimin yeterince buyuk VE olcumun guvenilir oldugu en uzun
     kesintisiz bolge. Otonom takip bu aralik disina HIC komut vermez; kol
     disaridaysa ilk duzeltme onu iceri ceker.
  2. DOGRUSALLASTIRMA: "kamerayi d derece cevir" isteigi, o bolgedeki egime gore
     dogru KOMUT acisina cevrilir -> dongu kazanci her bolgede ayni kalir.
"""
import json
import os

# Bir bolgenin kontrol icin kullanilabilmesi icin gereken en kucuk egim
# (kamera derecesi / komut derecesi). 0.10'un altinda kamerayi 1 derece cevirmek
# icin 10 dereceden fazla komut gerekir; olcum gurultusu bile isareti cevirebilir.
EGIM_ESIK = 0.10
# Faz korelasyonu guveni bunun altindaysa o adimin olcumu KULLANILMAZ (goruntu
# fazla kaydi ya da sahne dokusuz). 0.05 alti olcumlerde +1.44 gibi fiziksel
# olarak anlamsiz degerler goruldu.
GUVEN_ESIK = 0.10

VARSAYILAN_DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tilt_egri.json")


class KameraEgrisi:
    """Parca parca dogrusal komut -> kamera egrisi.

        e = KameraEgrisi.yukle()            # yoksa None
        lo, hi = e.gecerli_aralik
        e.kamera(30.0)                       # 30 derece komutta kamera acisi
        e.komut(kamera_derece)               # ters: gecerli aralik icinde, kirpilir
    """

    def __init__(self, noktalar, kaynak=None):
        # noktalar: [(komut, kamera, guven), ...] — komuta gore sirali olmali
        self.noktalar = sorted((float(a), float(k), float(g)) for a, k, g in noktalar)
        if len(self.noktalar) < 2:
            raise ValueError("egri en az iki nokta ister")
        self.kaynak = kaynak
        self.gecerli_aralik = self._gecerli_araligi_bul()

    # ---- kaydet / yukle ----
    @classmethod
    def yukle(cls, yol=VARSAYILAN_DOSYA):
        try:
            with open(yol, encoding="utf-8") as f:
                veri = json.load(f)
            return cls(veri["noktalar"], kaynak=yol)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def kaydet(self, yol=VARSAYILAN_DOSYA, not_=""):
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"not": not_, "gecerli_aralik": list(self.gecerli_aralik),
                       "noktalar": [list(n) for n in self.noktalar]},
                      f, ensure_ascii=False, indent=2)

    # ---- egri ----
    def _parcalar(self):
        for (a0, k0, _), (a1, k1, g) in zip(self.noktalar, self.noktalar[1:]):
            yield a0, k0, a1, k1, g            # g: bu ADIMIN (a0->a1) olcum guveni

    def _gecerli_araligi_bul(self):
        """Egimi >= EGIM_ESIK ve guveni >= GUVEN_ESIK olan en uzun kesintisiz bolge."""
        en_iyi, bas = None, None
        for a0, k0, a1, k1, g in self._parcalar():
            egim = (k1 - k0) / (a1 - a0)
            iyi = egim >= EGIM_ESIK and g >= GUVEN_ESIK
            if iyi:
                bas = a0 if bas is None else bas
                if en_iyi is None or (a1 - bas) > (en_iyi[1] - en_iyi[0]):
                    en_iyi = (bas, a1)
            else:
                bas = None
        if en_iyi is None:
            raise ValueError("egride kontrol icin kullanilabilir bir bolge yok")
        return en_iyi

    def kamera(self, komut):
        """Komut acisinda kameranin acisi (parca parca dogrusal; uclarda sabit)."""
        n = self.noktalar
        if komut <= n[0][0]:
            return n[0][1]
        for a0, k0, a1, k1, _ in self._parcalar():
            if komut <= a1:
                return k0 + (komut - a0) * (k1 - k0) / (a1 - a0)
        return n[-1][1]

    def komut(self, kamera_hedef):
        """Istenen kamera acisina karsilik gelen KOMUT acisi — yalniz gecerli aralikta.

        Gecerli aralikta egri tekduze artar (esik bunu garanti eder), yani ters
        tek anlamlidir. Hedef araligin disindaysa en yakin uca kirpilir: kol ASLA
        olu/ters bolgeye gonderilmez."""
        lo, hi = self.gecerli_aralik
        k_lo, k_hi = self.kamera(lo), self.kamera(hi)
        if kamera_hedef <= k_lo:
            return lo
        if kamera_hedef >= k_hi:
            return hi
        for a0, k0, a1, k1, _ in self._parcalar():
            if a1 <= lo or a0 >= hi:
                continue
            if k0 <= kamera_hedef <= k1:
                return a0 + (kamera_hedef - k0) * (a1 - a0) / (k1 - k0)
        return hi

    def komut_duzeltmesi(self, komut_simdi, kamera_delta):
        """PD'nin "kamerayi kamera_delta derece cevir" istegini KOMUT deltasina cevirir.

        Kol gecerli aralik DISINDAYSA (or. olu bolgede, uca dayali) kamera acisi
        olarak aralikin en yakin ucu esas alinir: ilk komut kolu araliga geri ceker.
        Bunu yapmasaydik olu bolgede "kamera" degeri anlamsiz olur, kol orada
        takili kalirdi — sahadaki ariza tam olarak buydu."""
        lo, hi = self.gecerli_aralik
        taban = min(max(komut_simdi, lo), hi)
        hedef = self.komut(self.kamera(taban) + kamera_delta)
        return hedef - komut_simdi


if __name__ == "__main__":
    # Sahada olculen egri (2026-09-21, tilt_yon_testi.py egri, 4 derecelik adimlar).
    OLCULEN = [(2, 0.0, 1.0), (6, -2.40, 0.43), (10, -2.71, 0.88), (14, -2.16, 0.88),
               (18, -1.20, 0.83), (22, 0.17, 0.66), (26, 1.81, 0.66), (30, 3.61, 0.56),
               (34, 5.07, 0.67), (38, 6.48, 0.56), (42, 7.77, 0.52), (46, 8.59, 0.83),
               (50, 9.51, 0.67), (54, 15.27, 0.03), (58, 15.27, 0.02)]
    e = KameraEgrisi(OLCULEN)

    # 1. Gecerli aralik: ters (2-6) ve olu (6-10) bolge ile guvenilmez ust uc (50+) DISARIDA
    lo, hi = e.gecerli_aralik
    assert (lo, hi) == (10.0, 50.0), (lo, hi)

    # 2. Ters cevirme tutarli: komut(kamera(x)) == x (gecerli aralikta)
    for x in (10, 13.5, 22, 30, 41.2, 50):
        assert abs(e.komut(e.kamera(x)) - x) < 1e-9, x

    # 3. Asla araligin disina komut yok
    assert e.komut(-100) == lo and e.komut(+100) == hi

    # 4. DOGRUSALLASTIRMA: ayni kamera istegi, egimin dusuk oldugu yerde DAHA BUYUK
    #    komut uretir (dongu kazanci her bolgede ayni kalsin diye).
    verimli = e.komut_duzeltmesi(28.0, 0.5)     # egim ~0.45
    zayif = e.komut_duzeltmesi(12.0, 0.5)       # egim ~0.14
    assert zayif > verimli * 2.5, (zayif, verimli)

    # 5. ⭐ SAHADAKI ARIZA: kol olu bolgedeyken (0-10) "kamerayi yukari cevir" istegi,
    #    kolu once gecerli araliga CEKMELI; ters bolgede daha da asagi itmemeli.
    for kol in (0.0, 3.0, 8.0):
        d = e.komut_duzeltmesi(kol, +0.3)
        assert kol + d >= lo, (kol, d)
    #    "kamerayi asagi cevir" istegi bile kolu olu bolgeye GONDERMEMELI.
    assert 30.0 + e.komut_duzeltmesi(30.0, -50.0) == lo

    # 6. Kaydet/yukle gidis-donus
    import tempfile
    yol = os.path.join(tempfile.gettempdir(), "tilt_egri_test.json")
    e.kaydet(yol, "test")
    e2 = KameraEgrisi.yukle(yol)
    assert e2 is not None and e2.gecerli_aralik == e.gecerli_aralik
    assert KameraEgrisi.yukle(os.path.join(tempfile.gettempdir(), "yok_boyle.json")) is None

    print(f"tilt_egri testleri OK — gecerli aralik {lo:.0f}-{hi:.0f} derece "
          f"(kamera {e.kamera(lo):+.1f} .. {e.kamera(hi):+.1f}), ters/olu bolge disarida, "
          f"dogrusallastirma, olu bolgeden geri cekme")
