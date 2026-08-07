# -*- coding: utf-8 -*-
"""MOCK ESP32 — karttaki GERCEK kodun yazilimsal taklidi (donanimsiz zincir testi).

esp32/derin_mavi_esp32/derin_mavi_esp32.ino ile ayni protokolu konusur ve ayni sekilde davranir:
  - Satir komutlarini alir (P/T/S/A/L/STOP/START), taninmayani sessizce yok sayar.
  - IKI STEP MOTORU surer: pan (yatay) ve tilt (dikey). Motorlar MUTLAK hedefe
    tavan hizla yurur (aninda isinlanmaz) -> takip/dwell mantigi gercekci test edilir.
  - LAZERi L1 ile acar, L0 ile keser.
  - STOP'ta motorlari kilitler, SURUCU ENABLE hatlarini keser VE lazeri keser;
    START gelene kadar komut kabul etmez.
  - DONANIM ACIL STOP BUTONU: `buton_bas(True/False)` ile taklit edilir. Buton basiliyken
    START REDDEDILIR (yazilimdan devam edilemez — fiziksel buton birakilmali).
  - Kart gibi insan-okur metin dondurur (yapisal durum paketi YOK).

Fark (bilincli): ivme kaydedilir ama trapez hiz profili SIMULE EDILMEZ — takip ve
guvenlik mantigini test etmek icin tavan hiz yeterli, ivme yalnizca gercek mekanikte
adim kacirmayi ilgilendirir.

Gercek donanima gecis: DERINMAVI_ESP=COM<n> — uygulama kodu degismez.
"""
import time

import protokol as P

DT_TAVAN = 0.25    # iki komut arasi uzun duraklamada motor "isinlanmasin"


class MockESP32:
    def __init__(self):
        self.pan = 0.0              # YATAY motor, mutlak konum (der)
        self.tilt = 0.0             # DIKEY motor, mutlak konum (der)
        self.pan_hedef = 0.0
        self.tilt_hedef = 0.0
        self.max_hiz, self.ivme = P.HIZ_TABLO[P.HIZ_VARSAYILAN]   # derece/sn, derece/sn²
        self.lazer = False
        self.lazer_guc = P.LAZER_GUC_VARSAYILAN   # PWM duty yuzdesi (G komutu)
        self.son_ates_t = 0.0       # olu adam anahtari: son L1'in zamani
        self.estop = False          # ESP'deki systemActive'in tersi
        # ENABLE hatlari: acilista enerjilenir ve BIR DAHA KESILMEZ (kart da oyle).
        # Alan duruyor ki "acil durdurmada da enerjili kalir" kurali test edilebilsin.
        self.surucu_enerjili = True
        self.buton = False          # donanim acil stop butonu basili mi
        self._son_t = time.time()
        self.kayit = []             # test/teshis icin alinan komut satirlari

    def _durdur(self, sebep):
        """Acil durdurma — seri STOP ve donanim butonu AYNI yoldan gecer.

        Kart gibi: lazer kesilir, PAN oldugu yerde kilitlenir, TILT 0° park konumuna
        iner (bu tek izinli harekettir), komutlar reddedilir.
        ⚠ Surucu ENABLE **kesilmez**: kapali cevrim surucude serbest kalan mil kayar ve
          ENABLE geri gelince surucu biriken hatayi kendi maksimum hiziyla kapatir —
          gimbal aniden firlar (sahada gozlendi). Motorlar tuttugu icin konum da
          sifirlanmaz, referans korunur."""
        self.estop = True
        self.lazer = False                      # once ATES kesilir
        # HER IKI EKSEN DE OLDUGU YERDE DONAR (sartname Yetenek 3: "sistem durur").
        self.pan_hedef, self.tilt_hedef = self.pan, self.tilt
        return (f"SISTEM DURDURULDU! {sebep} "
                f"Konum P{self.pan:.2f} / T{self.tilt:.2f}")

    def buton_bas(self, basili):
        """Donanim acil stop butonunun taklidi (kart bunu GPIO'dan okur)."""
        onceki, self.buton = self.buton, bool(basili)
        if self.buton and not onceki:
            return self._durdur("(ACIL STOP BUTONU)")
        return ""                               # birakmak sistemi BASLATMAZ

    # ---- fizik adimi: iki motoru da tavan hizla mutlak hedefe yurut ----
    def _adim(self):
        t = time.time()
        dt = min(DT_TAVAN, t - self._son_t)
        self._son_t = t
        # OLU ADAM ANAHTARI: laptop tazelemeyi kesmisse lazeri kart kendi keser.
        if self.lazer and (t - self.son_ates_t) * 1000.0 > P.ATES_ZAMAN_ASIMI_MS:
            self.lazer = False
        if self.estop:
            return          # ACIL DURDURMADA hicbir eksen surulmez (Yetenek 3)
        adim = self.max_hiz * dt
        for eksen in ("pan", "tilt"):
            simdiki = getattr(self, eksen)
            hedef = getattr(self, eksen + "_hedef")
            fark = hedef - simdiki
            if abs(fark) <= adim:
                setattr(self, eksen, hedef)
            else:
                setattr(self, eksen, simdiki + (adim if fark > 0 else -adim))

    def islet(self, satir: str) -> str:
        """Bir komut satirini isler, kartin yazacagi metni dondurur."""
        self._adim()
        k = satir.strip().upper()
        if not k:
            return ""
        self.kayit.append(k)

        if k == "STOP":
            return self._durdur("Motorlar kilitli, lazer kapali.")
        if k == "START":
            if self.buton:
                # Fiziksel buton basiliyken yazilimdan devam ETTIRILEMEZ. Metinde
                # "DURDURUL" gecer ki arayuz E-Stop'ta kaldigimizi gorsun.
                return "START REDDEDILDI — ACIL STOP BUTONU BASILI (SISTEM DURDURULDU)"
            # ⚠ KONUM SIFIRLANMAZ: motorlar acil durdurma boyunca enerjili kaldi, mil
            #   kaymadi, referans gecerli. (Sifir kabulu ENABLE'in kesildigi eski
            #   tasarimin telafisiydi; artik her acil durdurmada acilari kaydirirdi.)
            self.estop = False
            return (f"SISTEM BASLATILDI! Referans korundu "
                    f"(P{self.pan:.2f} / T{self.tilt:.2f})")
        if self.estop:                                  # STOP'tayken diger komutlar YOK SAYILIR
            return ""

        eksen, deger = k[0], k[1:]
        try:
            sayi = float(deger)
        except ValueError:
            return ""                                   # taninmayan komut: ESP de susar

        if eksen == "P":
            self.pan_hedef = sayi
            return f"PAN Merkez: {sayi:.2f}"
        if eksen == "T":
            self.tilt_hedef = P.tilt_kirp(sayi)          # ESP de kendi tarafinda kirpar
            return f"TILT Merkez: {self.tilt_hedef:.2f}"
        if eksen == "S":
            self.max_hiz = sayi                          # derece/sn
            return f">>> YENI TAVAN HIZ AYARLANDI: {sayi:.2f} der/sn"
        if eksen == "A":
            self.ivme = sayi                             # derece/sn²
            return f">>> YENI IVME AYARLANDI: {sayi:.2f} der/sn2"
        if eksen == "G":
            self.lazer_guc = P.guc_kirp(sayi)            # ESP de kendi tarafinda kirpar
            return f">>> LAZER GUCU: %{self.lazer_guc}"
        if eksen == "L":
            self.lazer = (sayi != 0)
            if self.lazer:
                self.son_ates_t = time.time()        # olu adam anahtarini tazele
            durum = "LAZER ACIK" if self.lazer else "LAZER KAPALI"
            return f"{durum} (%{self.lazer_guc})"
        return ""


if __name__ == "__main__":
    # temel zincir: hareket + ates + STOP/START
    m = MockESP32()
    assert "PAN" in m.islet(P.pan(90))
    assert m.pan_hedef == 90.0
    time.sleep(0.05)
    m.islet(P.lazer(True))
    assert m.lazer is True
    # ATES SIRASINDA HAREKET SURER (mutlak protokolde ates hedefi bozmaz)
    assert m.pan_hedef == 90.0 and m.pan < 90.0

    pan_once = m.pan
    cikti = m.islet(P.DUR)
    assert P.satir_estop_mu(cikti), cikti
    assert m.estop and m.lazer is False                  # E-Stop atesi KESTI
    assert m.surucu_enerjili is True, "ENABLE kesildi — kapali cevrimde firlamaya yol acar"
    assert m.pan_hedef == pan_once, "pan oldugu yerde kilitlenmedi"
    assert m.tilt_hedef == 0.0, "tilt park konumuna inmiyor"
    m.islet(P.pan(180)); m.islet(P.lazer(True))          # STOP'ta komutlar yok sayilir
    assert m.pan_hedef != 180.0 and m.lazer is False

    # ACIL DURDURMADA HICBIR EKSEN HAREKET ETMEZ (sartname Yetenek 3: "sistem durur").
    # Motor hedefe VARMADAN durduruluyor: hedef 40, gercek konum 25.
    m2p = MockESP32()
    m2p.islet(P.pan(90)); m2p.islet(P.tilt(40))
    m2p.pan, m2p.tilt = 90.0, 25.0
    cikti = m2p.islet(P.DUR)
    assert P.satir_konum(cikti) == (90.0, 25.0), cikti   # kart durdugu konumu bildirir
    assert m2p.tilt_hedef == 25.0, "tilt hedefi durulan konuma cekilmedi"
    for _ in range(20):                                  # zamani ilerlet
        m2p._son_t -= DT_TAVAN
        m2p.islet("")
    assert m2p.tilt == 25.0, (m2p.tilt, "acil durdurmada tilt hareket etti")
    assert m2p.pan == 90.0, (m2p.pan, "acil durdurmada pan hareket etti")

    # DEVAM: konum SIFIRLANMAZ (motorlar tuttugu icin referans gecerli kaldi)
    m2p.islet(P.DEVAM)
    assert not m2p.estop and m2p.surucu_enerjili
    assert m2p.pan == 90.0, "DEVAM'da referans sifirlandi"

    # DONANIM ACIL STOP BUTONU
    mb = MockESP32()
    mb.islet(P.lazer(True))
    cikti = mb.buton_bas(True)
    assert P.satir_estop_mu(cikti), cikti
    assert mb.estop and not mb.lazer and mb.surucu_enerjili
    assert P.satir_estop_mu(mb.islet(P.DEVAM)), "buton basiliyken START kabul edildi"
    assert mb.estop, "buton basiliyken sistem yeniden basladi"
    assert mb.buton_bas(False) == "" and mb.estop, "buton birakilinca kendiliginden basladi"
    assert not P.satir_estop_mu(mb.islet(P.DEVAM)) and not mb.estop   # buton serbest -> START gecer

    # TILT LIMITI: kart kendi tarafinda da kirpar (arayuze guvenilmez)
    m2 = MockESP32()
    m2.islet("T500")
    assert m2.tilt_hedef == P.TILT_MAX, m2.tilt_hedef
    m2.islet("T-90")
    assert m2.tilt_hedef == P.TILT_MIN == 0.0, m2.tilt_hedef

    # HIZ DUZEYI: S/A komutlari kaydedilir, ayni surede alinan yol duzeyle orantilidir.
    def _yol(duzey):
        mm = MockESP32()
        for satir in P.hiz(duzey):
            mm.islet(satir)
        mm.islet(P.pan(9000))                            # cok uzak hedef
        mm._son_t -= DT_TAVAN                            # tam DT_TAVAN gecmis say
        mm.islet("")                                     # bos satir: yalniz fizik adimi
        return mm.pan

    yavas, normal, hizli = (_yol(h) for h in P.HIZ_SEVIYELER)
    assert yavas < normal < hizli, (yavas, normal, hizli)
    assert abs(hizli - P.derece_sn(P.H_HIZLI) * DT_TAVAN) < 0.5, hizli

    m3 = MockESP32()
    for satir in P.hiz(P.H_YAVAS):
        m3.islet(satir)
    assert (m3.max_hiz, m3.ivme) == P.HIZ_TABLO[P.H_YAVAS], (m3.max_hiz, m3.ivme)

    # LAZER GUCU: ayri komut, kirpilir, ates ac/kes gucu SIFIRLAMAZ
    m5 = MockESP32()
    assert m5.lazer_guc == P.LAZER_GUC_VARSAYILAN == 40
    m5.islet(P.lazer_guc(70))
    assert m5.lazer_guc == 70
    m5.islet(P.lazer(True)); m5.islet(P.lazer(False))
    assert m5.lazer_guc == 70, "ates ac/kes guc ayarini bozmamali"
    m5.islet("G500"); assert m5.lazer_guc == P.LAZER_GUC_MAX
    m5.islet("G-5"); assert m5.lazer_guc == P.LAZER_GUC_MIN
    # E-Stop atesi keser ama guc ayari KALICI (kart da oyle: yalniz duty 0 yazilir)
    m5.islet(P.lazer_guc(40)); m5.islet(P.lazer(True))
    m5.islet(P.DUR)
    assert not m5.lazer and m5.lazer_guc == 40

    # OLU ADAM ANAHTARI: tazeleme kesilirse kart lazeri KENDI keser
    m6 = MockESP32()
    m6.islet(P.lazer(True))
    assert m6.lazer
    m6.islet(P.lazer(True))                          # tazeleme -> acik kalir
    assert m6.lazer
    m6.son_ates_t -= P.ATES_ZAMAN_ASIMI_MS / 1000.0 + 0.1   # tazeleme kesilmis say
    m6.islet("")                                     # bos satir: yalniz zaman adimi
    assert not m6.lazer, "tazeleme kesildigi halde lazer acik kaldi"

    # Taninmayan komut kartı bozmamali (ESP de sessizce yok sayar)
    m4 = MockESP32()
    assert m4.islet("XYZ") == "" and m4.islet("P") == ""
    assert m4.pan_hedef == 0.0

    print("mock_esp32 testleri OK — 2 motor/lazer, mutlak hedef, STOP/START, "
          "tilt limiti, 3 kademe hiz")
