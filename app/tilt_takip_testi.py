# -*- coding: utf-8 -*-
"""DERIN MAVI — DIKEY EKSEN TAKIBI: KAPALI CEVRIM BENZETIMI (donanimsiz).

Bu dosya `kapi_testleri.py` ile ayni ise yarar: pencere acmadan, kamera ve kart
olmadan, SISTEMIN ASIL DAVRANISINI dener. Burada denenen soru sudur:

    "Ekranda secilen hedefi, kol-biyel mekanizmasi dikeyde GERCEKTEN yakalar mi,
     yoksa asip geri salinir mi?"

Zincirin tamami gercek koddur — yalnizca KAMERA ve MEKANIK taklit edilir:

    (benzetim) hedefin gercek yukselis acisi
        -> kadrajdaki piksel konumu          [kamera modeli, asagida]
        -> nisan.PDNisanci.adim()            ** gercek kod **
        -> hiz kirpmasi + mesgul kapisi      ** arayuz_qt._nisan_geldi AYNASI **
        -> kontrol.Kontrol.aci()             ** gercek kod **
        -> tilt_surucu.TiltSurucu            ** gercek kod **
        -> MockTiltKart                      [mekanik/firmware modeli]

⚠ AYNA UYARISI: hiz kirpmasi ve mesgul kapisi burada YENIDEN yazilidir cunku
  arayuz_qt.py'deki asillari QWidget metodudur (import etmek PySide6 ister ve
  pencere acar). `_nisan_geldi` degisirse BURASI DA degismeli. Ayni yaklasim
  nisan.py'nin kendi `benzet()` dongusunde de kullaniliyor.

⚠ NE OLCULMEZ: gercek motor ivmesi, mekanik esneme, kamera gecikmesi ve
  tespitin kare-kare titremesi. Bu bir ZAMANLAMA olcumu DEGIL, MANTIK ve
  KARARLILIK testidir. Sahadaki Kp/Kd ayari yine olcumle yapilmalidir.
"""
import json
import math
import os

import algi
import nisan
import protokol as P
import tilt_surucu as T
from kontrol import Kontrol

# --- benzetim parametreleri ---
KARE_W, KARE_H = 1280, 720
FPS = 15.0
KARE_SURESI = 1.0 / FPS
YOKLAMA_PERIYODU = P.ATES_TAZELE_MS / 1000.0     # arayuzdeki esp_timer (250 ms)
HEDEF_KUTU_YUKSEKLIK = 120.0                     # olu bolgeyi olcekler (kutuya oranli)

# arayuz_qt.py sabitlerinin aynasi (bkz. AYNA UYARISI)
NISAN_MESGUL_ORANI = 0.4
NISAN_MIN_ARALIK = 0.04


class Benzetim:
    """Kamera + mekanik modeli etrafinda gercek kontrol zincirini dondurur."""

    def __init__(self, hedef_aci, hedef_hizi=0.0, baslangic_aci=0.0,
                 hiz_seviye=P.H_NORMAL, mekanizma=None):
        """mekanizma: komut acisi -> KAMERA acisi fonksiyonu (None = birebir).
        Kamera ile komut arasindaki donus orani 1 degilse dongu kazanci fiilen
        o oranla carpilir; bunu denemek icin verilir."""
        self.mekanizma = mekanizma
        self.saat = 0.0
        self.hedef_aci = float(hedef_aci)       # hedefin GERCEK yukselis acisi
        self.hedef_hizi = float(hedef_hizi)     # derece/sn (hareketli hedef)
        self.hiz_seviye = hiz_seviye

        self.k = Kontrol("off", tilt_kaynak="mock")   # pan karti gerekmiyor
        self.k.tilt._saat = lambda: self.saat
        self.k.tilt.mock.t = self.k.tilt.mock.son_canli = self.saat
        # Kol baslangicta istenen acida olsun (kart sayaci oraya kurulur)
        self.k.tilt.mock.pos = self.k.tilt.mock.hedef = \
            self.k.tilt.mock._darbe(baslangic_aci)

        self.nisanci = nisan.PDNisanci()
        self.tilt_aci = baslangic_aci           # arayuzun inandigi aci (self.tilt_aci)
        self._nisan_son_t = None
        self._nisan_mesgul_ta = 0.0
        self._son_yoklama = 0.0
        self.iz = []                            # her karedeki piksel hatasi

    @property
    def kol_aci(self):
        """Mekanigin GERCEK acisi (kartin bildirdigi; benzetimde ayni sey)."""
        return self.k.tilt.mock._aci(self.k.tilt.mock.pos)

    @property
    def kamera_aci(self):
        """KAMERANIN gercek acisi. Kol-biyelde komut acisindan farklidir ve
        dogrusal olmayabilir; hedef_aci da bu olcektedir."""
        return self.mekanizma(self.kol_aci) if self.mekanizma else self.kol_aci

    def _piksel_y(self):
        """Hedefin kadrajdaki dikey konumu.

        Kol hedefin ALTINDAYSA (kol_aci < hedef_aci) hedef merkezin USTUNDE
        gorunur -> y < KARE_H/2. nisan.adim bu durumda POZITIF d_pitch uretir
        (yukari don) — isaret zinciri boylece uctan uca dogrulanmis olur."""
        dpp = nisan.derece_per_piksel(KARE_W)
        return KARE_H * 0.5 + (self.kamera_aci - self.hedef_aci) / dpp

    def _yokla(self):
        """Arayuzdeki 250 ms'lik esp_timer: kart okunur, canlilik gider, kuyruk bosalir."""
        while self.saat - self._son_yoklama >= YOKLAMA_PERIYODU:
            self._son_yoklama += YOKLAMA_PERIYODU
            self.k.oku()

    def _nisan_geldi(self, d_pitch):
        """arayuz_qt.MainWindow._nisan_geldi'nin dikey eksen aynasi."""
        if self.saat < self._nisan_mesgul_ta:
            return
        _pan, (tavan_hiz, tavan_ivme) = self.k.hiz_profilleri(self.hiz_seviye)
        if self._nisan_son_t is not None:
            dt = min(0.2, self.saat - self._nisan_son_t)
            tavan = tavan_hiz * dt
            d_pitch = max(-tavan, min(tavan, d_pitch))
        self._nisan_son_t = self.saat
        mesafe = abs(d_pitch)                  # mesgul kapisi KAMERA derecesiyle

        # _aci_hareket'in dikey kismi: taban OLCULEN acidir (otonom takip)
        taban = self.k.tilt_olculen
        if taban is None:
            taban = self.tilt_aci
        yeni = max(0.0, min(self.k.tilt_tavan, taban + d_pitch))
        self.tilt_aci = yeni
        self.k.aci(0.0, yeni)

        sure = 2.0 * math.sqrt(mesafe / max(1.0, tavan_ivme)) * NISAN_MESGUL_ORANI
        self._nisan_mesgul_ta = self.saat + max(NISAN_MIN_ARALIK, sure)

    def calistir(self, saniye):
        """Benzetimi `saniye` kadar dondurur; her karedeki piksel hatasini biriktirir."""
        bitis = self.saat + saniye
        while self.saat < bitis:
            self.saat += KARE_SURESI
            self.hedef_aci += self.hedef_hizi * KARE_SURESI
            self._yokla()

            y = self._piksel_y()
            self.iz.append(y - KARE_H * 0.5)
            d_yaw, d_pitch = self.nisanci.adim(
                (KARE_W * 0.5, y), (KARE_W, KARE_H), simdi=self.saat,
                hedef_yukseklik=HEDEF_KUTU_YUKSEKLIK)
            if d_pitch:                         # None / 0.0 = dikeye komut yok
                self._nisan_geldi(d_pitch)
        return self.iz


class GecikmeliBenzetim(Benzetim):
    """Kamera + cikarim gecikmesini de modelleyen benzetim.

    Gercek zincirde kare YAKALANIR, ~66 ms sonra YOLO sonucu doner; PD o sirada
    kolun ARTIK BULUNMADIGI bir konuma gore karar verir. Gecikme, yuksek kazancta
    salinimin ASIL sebebidir — gecikmesiz bir benzetimde kazanc ne kadar
    yukseltilirse yukseltilsin sistem hep kararli gorunur ve tarama yaniltir.

    Olculdu (2026-09-20, gercek kalibrasyon 2675 darbe/60°):
        gecikmesiz      : kp 0.90'a kadar asma YOK
        1 kare (67 ms)  : kp 0.70'ten itibaren asma basliyor
        2 kare (133 ms) : kp 0.70 + kd 0.06 -> 70 px asma, 3 yon degisimi (SALINIM)
                          kp 0.90 + kd 0.06 -> 132 px asma
    Yani kazanc tavanini gecikme belirler, mekanik degil.
    """
    GECIKME_KARE = 2        # 133 ms @ 15 FPS — kotumser ama gercekci

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._aci_gecmisi = []

    def _piksel_y(self):
        self._aci_gecmisi.append(self.kamera_aci)
        i = self.GECIKME_KARE + 1
        gecikmis = self._aci_gecmisi[-i] if len(self._aci_gecmisi) >= i else self._aci_gecmisi[0]
        dpp = nisan.derece_per_piksel(KARE_W)
        return KARE_H * 0.5 + (gecikmis - self.hedef_aci) / dpp


def yon_degisimi(iz, esik):
    """Hatanin olu bolgenin disinda kac kez ISARET DEGISTIRDIGI — salinim olcutu.

    Tek bir asma kotu ayar demek olmayabilir; SALINIM hedefin iki yanina art arda
    gecmektir ve dwell'i (lazerin hedefte kalma suresi) imkansiz kilar."""
    isaret = [1 if v > esik else (-1 if v < -esik else 0) for v in iz]
    return sum(1 for i in range(1, len(isaret))
               if isaret[i] and isaret[i - 1] and isaret[i] != isaret[i - 1])


def olu_bolge_px():
    """O karedeki isabet olcutu (kutuya oranli) — yakinsama esigi budur."""
    return max(nisan.TABAN_OLU_BOLGE_PX,
               HEDEF_KUTU_YUKSEKLIK * algi.AYAR["olu_bolge_kutu"])


def yakinsama_dogrula(iz, esik, ad):
    """Izin yerlesme / asma / salinim acisindan saglikli oldugunu dogrular.

    ISARET KURALI: iz = (kol_acisi - hedef_acisi) / (derece/piksel). Yani kol
    hedefin ALTINDAYSA hata NEGATIF, ustundeyse POZITIFTIR. Asma, hatanin
    basladigi isaretin TERSINE gecmesidir — bu yuzden esik karsilastirmasi
    baslangic isaretine gore kurulur (iki yonu tek kaliptan denemek icin)."""
    assert abs(iz[-1]) <= esik, f"{ad}: yakinsamadi, son hata {iz[-1]:.1f} px (esik {esik:.1f})"
    basla = iz[0]
    asma = max(iz) if basla < 0 else min(iz)
    assert abs(asma) <= esik or asma * basla > 0, f"{ad}: asma var ({asma:.1f} px)"
    # Esigin USTUNDEKI bolumde hata tek yonlu kucuImeli (salinim/arayis yok).
    buyukler = [abs(v) for v in iz if abs(v) > esik]
    assert all(buyukler[i + 1] <= buyukler[i] + 1e-6 for i in range(len(buyukler) - 1)), \
        f"{ad}: salinim -> {[round(v) for v in buyukler[:25]]}"


def kayitli_ayarlari_yukle():
    """ayarlar.json varsa algi.AYAR'a yukler (arayuzun acilista yaptigi is).

    Neden testte de: kazanc tavanini koruyan test (10) GERCEKTEN calisan
    kazanclari denemeli. Yalnizca kod varsayilanlarini deneseydi, panelden
    kp'yi salinim bolgesine cekmek testten sessizce gecerdi."""
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ayarlar.json")
    try:
        with open(yol, encoding="utf-8") as f:
            algi.ayar_guncelle(**json.load(f))
        return yol
    except (OSError, ValueError, TypeError):
        return None


if __name__ == "__main__":
    _kaynak = kayitli_ayarlari_yukle()
    print("ayar kaynagi:", _kaynak or "kod varsayilanlari")
    esik = olu_bolge_px()

    # 1-3. SABIT HEDEF, kol altta: yukari cikip hedefe YERLESMELI; asma ve salinim yok.
    #
    #  ⭐ ASIL SINAV BUDUR. Kol-biyel yavastir ve firmware once mevcut hedefi
    #  bitirip sonra bekleyene gecer. Komutlar OLCULEN aciya gore kurulmasaydi
    #  (bkz. arayuz_qt._aci_hareket, taban_olculen) her kare bir oncekinin ustune
    #  biner, namlu hedefi asar ve geri salinirdi.
    b = Benzetim(hedef_aci=25.0, baslangic_aci=0.0)
    iz = b.calistir(8.0)
    yakinsama_dogrula(iz, esik, "asagidan yukari")
    assert abs(b.kol_aci - 25.0) < 1.5, f"kol yanlis acida durdu: {b.kol_aci:.2f}"

    # 4. YUKARIDAN ASAGI da calismali (isaret simetrisi).
    b2 = Benzetim(hedef_aci=8.0, baslangic_aci=45.0)
    iz2 = b2.calistir(8.0)
    yakinsama_dogrula(iz2, esik, "yukaridan asagi")
    assert abs(b2.kol_aci - 8.0) < 1.5, f"kol yanlis acida durdu: {b2.kol_aci:.2f}"

    # 5. HAREKETLI HEDEF: sabit hizda kalici bir GECIKME oturur (PD'de integral
    #    yok — nisan.py bunu aciklar). Kol 15 derece/sn ile ilerleyebiliyor;
    #    2 derece/sn'lik hedefi yakalayip bandin icinde tutmali.
    b3 = Benzetim(hedef_aci=10.0, hedef_hizi=2.0, baslangic_aci=0.0)
    iz3 = b3.calistir(12.0)
    kararli = [abs(v) for v in iz3[-30:]]
    assert max(kararli) < 4 * esik, \
        f"hareketli hedef takibi zayif: {max(kararli):.0f} px (esik {esik:.1f})"

    # 6. KOL ARALIGI ASILMAZ: hedef mekanigin uzerindeyse kol 60'ta durur,
    #    yazilimsal tavana tirmanip dayamaya yuklenmez.
    b4 = Benzetim(hedef_aci=120.0, baslangic_aci=0.0)
    b4.calistir(10.0)
    assert b4.kol_aci <= T.ACI_MAX + 1e-6, f"kol araligi asildi: {b4.kol_aci}"
    assert b4.tilt_aci <= T.ACI_MAX + 1e-6, f"arayuz acisi araligi asti: {b4.tilt_aci}"
    assert not any("BAD_ANGLE" in s for s in b4.k.tilt.satirlar), b4.k.tilt.satirlar

    # 7. KALIBRE DEGILSE hicbir hareket olmaz (mekanigi korur).
    b5 = Benzetim(hedef_aci=25.0, baslangic_aci=0.0)
    b5.k.tilt.mock.kalibre = False
    b5.calistir(4.0)
    assert b5.kol_aci == 0.0, f"kalibresiz kartta kol hareket etti: {b5.kol_aci}"

    # 8. KARTA BAYAT HEDEF GIRMEZ: gonderilen her G, gonderildigi anda kartin
    #    BOS olduguna gore kuruldu (tilt_surucu'nun tek yuvali kuyrugu).
    b6 = Benzetim(hedef_aci=30.0, baslangic_aci=0.0)
    b6.calistir(8.0)
    g_sayisi = len([s for s in b6.k.tilt.mock.kayit if s.startswith("G")])
    kare_sayisi = len(b6.iz)
    assert g_sayisi < kare_sayisi, \
        f"her kareye bir komut gitmis ({g_sayisi}/{kare_sayisi}) — kuyruk calismiyor"

    # 9. ⭐ KARSI DENEY (regresyon koruyucusu): komut OLCULEN aciya degil de
    #    YAZILIMIN INANDIGI aciya gore kurulsaydi sistem calismazdi. Bu test,
    #    _aci_hareket'teki `taban_olculen` yolunun "gereksiz karmasiklik" diye
    #    sadelestirilmesini engeller — olculen 13.08'deki salinim aynen geri gelir.
    class _InancReferansi(Benzetim):
        def _nisan_geldi(self, d_pitch):
            if self.saat < self._nisan_mesgul_ta:
                return
            _pan, (tavan_hiz, tavan_ivme) = self.k.hiz_profilleri(self.hiz_seviye)
            if self._nisan_son_t is not None:
                tavan = tavan_hiz * min(0.2, self.saat - self._nisan_son_t)
                d_pitch = max(-tavan, min(tavan, d_pitch))
            self._nisan_son_t = self.saat
            yeni = max(0.0, min(self.k.tilt_tavan, self.tilt_aci + d_pitch))   # INANC
            self.tilt_aci = yeni
            self.k.aci(0.0, yeni)
            sure = 2.0 * math.sqrt(abs(d_pitch) / max(1.0, tavan_ivme)) * NISAN_MESGUL_ORANI
            self._nisan_mesgul_ta = self.saat + max(NISAN_MIN_ARALIK, sure)

    #     ⚠ OLCUT SON HATA DEGIL, SALINIMDIR. Inanc referansi hedefi buyuk bir
    #     asmayla gecer, geri doner, tekrar gecer — ve sonunda olu bolgeye
    #     DUSEBILIR. Yalnizca son hataya bakan bir test bunu "basarili" sayardi;
    #     oysa dwell (lazerin hedefte kalma suresi) bu salinimla imkansizdir.
    b7 = _InancReferansi(hedef_aci=25.0, baslangic_aci=0.0)
    iz7 = b7.calistir(9.0)
    dgs7 = yon_degisimi(iz7, esik)
    assert dgs7 >= 1 and max(iz7) > 5 * esik, \
        (f"inanc referansi salinmadi (yon degisimi {dgs7}, asma {max(iz7):.0f} px) — "
         f"benzetim artik bu farki olcmuyor, test guncellenmeli.")

    # 10. ⭐ KULLANILAN KAZANCLAR GECIKMEYLE BIRLIKTE KARARLI MI?
    #     Bu test, ayarlar.json'daki (veya varsayilan) kp/kd ile 133 ms gecikmede
    #     SALINIM olup olmadigini dener — yani kazanc tavanini korur. Biri kp'yi
    #     "daha hizli olsun" diye 0.7-0.9'a cekerse burasi kirmiziya duser.
    #     ⚠ Mekanigin GERCEK olcegiyle denenir: kalibrasyonda 60° = 2675 darbe
    #     olculdu; mock'un varsayilani (6400) daha yavas bir kol demek olurdu ve
    #     test gercekte olmayan bir guvenlik payi gosterirdi.
    _eski_ust = T.MockTiltKart.UST_DARBE
    T.MockTiltKart.UST_DARBE = 2675
    try:
        g = GecikmeliBenzetim(hedef_aci=25.0, baslangic_aci=0.0)
        izg = g.calistir(9.0)
        dgs = yon_degisimi(izg, esik)
        assert dgs == 0, (f"kp={algi.AYAR['kp']} kd={algi.AYAR['kd']} ile "
                          f"{GecikmeliBenzetim.GECIKME_KARE} kare gecikmede SALINIM "
                          f"({dgs} yon degisimi). Kazanci dusur.")
        assert max(izg) <= 3 * esik, \
            f"gecikmeli asma cok buyuk: {max(izg):.1f} px (esik {esik:.1f})"
        assert abs(izg[-1]) <= esik, f"gecikmeyle yakinsamadi: {izg[-1]:.1f} px"

        # 10a. Hareketli hedefte kalici hata makul mu? (kp cok DUSUKSE burasi patlar —
        #      0.25'te olculen 72 px idi, yani hedef kadrajda surekli geride kalir.)
        g2 = GecikmeliBenzetim(hedef_aci=10.0, hedef_hizi=3.0, baslangic_aci=0.0)
        iz2 = g2.calistir(12.0)
        kalici = max(abs(v) for v in iz2[-45:])
        assert kalici < 3.5 * esik, \
            (f"hareketli hedefte kalici hata {kalici:.0f} px — kazanc cok dusuk "
             f"(kp={algi.AYAR['kp']}).")
    finally:
        T.MockTiltKart.UST_DARBE = _eski_ust

    print(f"tilt takip benzetimi OK — yerlesme {abs(iz[-1]):.1f} px / esik {esik:.1f} px, "
          f"asma yok, salinim yok, iki yon, hareketli hedef, 0-{T.ACI_MAX:.0f}° araligi, "
          f"kalibrasyon kapisi, {g_sayisi} komut / {kare_sayisi} kare "
          f"(inanc referansi karsi deneyi: {max(iz7):.0f} px asma, {dgs7} yon degisimi) | "
          f"gecikmeli (133 ms) kp={algi.AYAR['kp']} kd={algi.AYAR['kd']}: "
          f"salinim yok, hareketli hata {kalici:.0f} px")
