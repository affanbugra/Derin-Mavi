# -*- coding: utf-8 -*-
"""Kontrol katmani — arayuzun ESP32 ile konusma API'si (mock/gercek TEK arayuz).

ESP32'de iki step motor (pan = yatay, tilt = dikey) ve lazer var; bu katman arayuzun
tek muhatabidir — arayuz hicbir yerde elle komut satiri kurmaz (bkz. protokol.py).

Kaynak secimi (donanim-bagimsiz, CLAUDE.md ilke 7):
    DERINMAVI_ESP=mock   -> MockESP32 (varsayilan; donanimsiz gelistirme)
    DERINMAVI_ESP=COM5   -> gercek seri port (pyserial; donanim gelince)
    DERINMAVI_ESP=off    -> kontrol kapali (yalniz goruntu isleme)

Kullanim (arayuz):
    k = Kontrol()
    k.hiz_ayarla(P.H_HIZLI)     # motor hiz duzeyi (1=Yavas 2=Normal 3=Hizli)
    k.aci(pan_der, tilt_der)    # MUTLAK hedef aci (pan sarmasiz/birikimli verilir)
    k.guc_ayarla(40)            # lazer gucu % (kalici; varsayilan %40, tam guc DEGIL)
    k.ates(True/False)          # lazer ac/kes (ayarli gucte)
    k.estop(True/False)         # acil durdur / devam
    k.oku()                     # ESP'nin yazdigi bekleyen metin satirlari
    k.durum                     # arayuzun gosterecegi ozet (asagi)

DURUM NEREDEN GELIYOR? Kart yapisal durum paketi YOLLAMAZ (yalniz insan-okur metin).
Bu yuzden `durum` **komut ettigimiz** hedefi ve son bilinen lazer/E-Stop halini tutar,
olculmus konumu DEGIL. Arayuz de bunu "hedef" diye yazar — olcum gibi gostermek
(eskiden mesafe ozelliginde yasandigi gibi) en yaniltici hatadir. Kart konum geri
bildirimi kazanirsa tek degisecek yer burasi.
"""
import os

import protokol as P
from mock_esp32 import MockESP32

KAYNAK = os.environ.get("DERINMAVI_ESP", "mock").strip() or "mock"


class Kontrol:
    def __init__(self, kaynak=None):
        self.kaynak = (kaynak or KAYNAK).lower()
        self.mock = None
        self.seri = None
        self.hata = None
        self.satirlar = []          # ESP'den okunan son metinler (en yeni sonda)
        self._yeni = []             # henuz arayuze gosterilmemis satirlar
        # arayuze gosterilen ozet — hepsi BIZIM komut ettigimiz degerler
        self.hiz = P.HIZ_VARSAYILAN
        self.pan_hedef = 0.0
        self.tilt_hedef = 0.0
        self.lazer_acik = False
        self.lazer_guc = P.LAZER_GUC_VARSAYILAN
        self.estop_aktif = False
        # Kart beklenmedik sekilde yeniden basladiysa arayuz bunu gorup uyarir ve
        # ekrandaki aciyi sifirlar (kartin sayaci da sifirdan basladi).
        self.kart_resetlendi = False
        # Kart bizden farkli bir TILT_MAX bildirirse (firmware guncellenmemis) burada
        # (kart_degeri, bizim_deger) durur; arayuz uyarir.
        self.firmware_uyumsuz = None
        # Kart acil durdurmada durdugu konumu bildirir; arayuz ekrani buna gore duzeltir.
        self.estop_konum = None
        if self.kaynak == "off":
            return
        if self.kaynak == "mock":
            self.mock = MockESP32()
        else:                       # gercek seri port (or. COM5, /dev/ttyUSB0)
            try:
                import serial       # pyserial — yalniz gercek portta gerekir
                self.seri = serial.Serial(self.kaynak.upper(), 115200, timeout=0.05)
                # NOT: bircok ESP32 karti port acilinca (DTR/RTS) RESET atar; acilis
                # banner'i ve ilk komutlarin yanki satirlari karisabilir. Komutlar MUTLAK
                # oldugu icin bu kalici bir sapma yaratmaz (bkz. protokol.py).
                self.seri.reset_input_buffer()
            except Exception as e:
                self.hata = f"Seri port açılamadı ({self.kaynak}): {e}"
        if self.bagli:
            self.hiz_ayarla(self.hiz)      # kart acilis degerinde kalmasin, biz soyleyelim
            self.guc_ayarla(self.lazer_guc)

    @property
    def bagli(self):
        return self.mock is not None or self.seri is not None

    @property
    def mock_mu(self):
        return self.mock is not None

    @property
    def durum(self):
        """Alt cubugun gosterdigi ozet (komut edilen hedef + son bilinen haller)."""
        if not self.bagli:
            return None
        if self.estop_aktif:
            ad = "E-STOP"
        elif self.lazer_acik:
            ad = "ATEŞ"
        else:
            ad = "Hazır"
        return {"durum_ad": ad, "pan": self.pan_hedef, "tilt": self.tilt_hedef,
                "lazer": self.lazer_acik, "lazer_guc": self.lazer_guc,
                "estop": self.estop_aktif,
                "hiz": self.hiz, "hiz_ad": P.HIZ_AD[self.hiz],
                "esp_satir": self.satirlar[-1] if self.satirlar else ""}

    # ---- alt seviye: satir gonder / oku ----
    def _kart_yaziyor(self, s):
        """Karttan gelen bir metin satirini kaydeder ve icinden anlam cikarir."""
        self.satirlar.append(s)
        self._yeni.append(s)
        del self.satirlar[:-20]             # yalniz son 20 satir tutulur
        if P.satir_estop_mu(s):             # kart durdugunu bildirdi
            self.estop_aktif = True
            self.lazer_acik = False
            # Kart durdugu KONUMU bildirir; hedefimizi ona cekeriz. Motor hedefe
            # varmadan durduysa (or. 90'a giderken 45'te E-Stop) laptop'un hedefi
            # gercekten ayrisirdi ve ekrandaki aci yalan soylerdi.
            konum = P.satir_konum(s)
            if konum is not None:
                self.pan_hedef, self.tilt_hedef = konum
                self.estop_konum = konum        # arayuz ekrani buna gore duzeltir
        kart_tilt_max = P.satir_tilt_max(s)
        if kart_tilt_max is not None and abs(kart_tilt_max - P.TILT_MAX) > 0.01:
            # Firmware guncellenmemis: kart bizden farkli bir tavan biliyor. Sessiz
            # kalirsa gimbal eski limitte takilir ve sebebi gorunmez.
            self.firmware_uyumsuz = (kart_tilt_max, P.TILT_MAX)
        if P.satir_yeniden_baslama_mi(s):
            # KART RESET ATTI (besleme dalgalanmasi, reset dugmesi, yeni yukleme).
            # Kartin konum sayaci sifirdan basladi; bizim hedefimiz de sifirlanmali,
            # yoksa sonraki her komut kaymis referansa gore gider ve ekrandaki aci
            # sessizce yalan soyler. Arayuz bunu gorup operatoru uyarir.
            self.kart_resetlendi = True
            self.pan_hedef = self.tilt_hedef = 0.0
            self.lazer_acik = False         # acilista lazer duty 0
            self.estop_aktif = False        # reset sonrasi kart aktif basliyor

    def _gonder(self, *satirlar):
        for s in satirlar:
            if self.mock is not None:
                cevap = self.mock.islet(s)
                if cevap:
                    self._kart_yaziyor(cevap)
            elif self.seri is not None:
                try:
                    self.seri.write(s.encode("ascii"))
                except Exception as e:
                    self.hata = f"Seri iletişim hatası: {e}"
                    return self.durum
        if self.seri is not None:
            self.oku()
        return self.durum

    def oku(self):
        """Karttan gelen YENI satirlari dondurur (bloklamaz; okunanlar kuyruktan duser).

        Kart her komuta metin yankilar; okunmazsa hem seri tampon dolar hem de seri
        monitorden elle verilen STOP gibi olaylardan haberimiz olmaz."""
        if self.seri is not None:
            try:
                while self.seri.in_waiting:
                    s = self.seri.readline().decode("ascii", "replace").strip()
                    if s:
                        self._kart_yaziyor(s)
            except Exception as e:
                self.hata = f"Seri iletişim hatası: {e}"
        yeni, self._yeni = self._yeni, []
        return yeni

    # ---- yuksek seviye API ----
    def aci(self, pan_der, tilt_der):
        """MUTLAK hedef aci. pan SARMASIZ (birikimli) verilmeli — bkz. protokol.py.
        Yalnizca DEGISEN eksen gonderilir: hatta gereksiz komut dolastirmayiz."""
        satirlar = []
        if abs(pan_der - self.pan_hedef) > 0.005:
            satirlar.append(P.pan(pan_der))
            self.pan_hedef = pan_der
        tilt_der = P.tilt_kirp(tilt_der)
        if abs(tilt_der - self.tilt_hedef) > 0.005:
            satirlar.append(P.tilt(tilt_der))
            self.tilt_hedef = tilt_der
        if not satirlar:
            return self.durum
        return self._gonder(*satirlar)

    def ates(self, ac: bool):
        # NOT: eskiden bir `mod` (Manuel/Otonom) argumani vardi — karttaki kod mod
        # kavramini bilmiyor, komutlar her iki modda birebir ayni. Olu parametre silindi.
        self.lazer_acik = bool(ac)
        return self._gonder(P.lazer(ac))

    def ates_tazele(self):
        """Lazer ACIKKEN periyodik cagrilir — kartin olu adam anahtarini besler.

        Kart, tazeleme kesilirse lazeri kendi keser (bkz. protokol.ATES_TAZELE_MS).
        Ates kapaliyken hicbir sey gondermez: hat bos kalsin."""
        if not self.lazer_acik or self.estop_aktif:
            return None
        return self._gonder(P.lazer(True))

    def estop(self, aktif: bool):
        """Acil durdur / devam.

        ACIL DURDURMADA kart: lazeri keser, PAN'i oldugu yerde kilitler, TILT'i 0° park
        konumuna indirir, komutlari reddeder. Surucu ENABLE **kesilmez** (motorlar tutar),
        bu yuzden mil kaymaz ve KONUM SIFIRLANMAZ — pan hedefi oldugu gibi gecerli kalir.
        Bizim ozetimiz de kartla ayni sey soylemeli: yalniz tilt sifirlanir."""
        self.estop_aktif = bool(aktif)
        if aktif:
            self.lazer_acik = False        # kart da keser; ozet onunla ayni kalsin
            self.tilt_hedef = 0.0          # kart tilt'i park konumuna indiriyor
        return self._gonder(P.DUR if aktif else P.DEVAM)

    def home(self):
        """Merkeze al (0°, 0°). ESP'de limit switch homing'i YOK — bu yalnizca
        'bilinen baslangica don' demektir; gercek homing kart tarafina eklenecek."""
        self.pan_hedef = self.tilt_hedef = 0.0
        return self._gonder(P.pan(0.0), P.tilt(0.0))

    def guc_ayarla(self, yuzde):
        """Lazer gucu (%). Kalicidir: sonraki her ates bu gucte olur.

        Tam guc kullanilmiyor (varsayilan %40). ⚠ Dusuk guc dwell suresini uzatir —
        gercek patlama suresi olculup bu deger yeniden degerlendirilmelidir."""
        self.lazer_guc = P.guc_kirp(yuzde)
        return self._gonder(P.lazer_guc(self.lazer_guc))

    def hiz_ayarla(self, seviye):
        """Motor hiz duzeyi (tavan hiz + ivme). ESP'ye iki satir olarak gider."""
        self.hiz = P.hiz_kirp(seviye)
        return self._gonder(*P.hiz(self.hiz))

    def kapat(self):
        if self.seri is not None:
            try:
                self.seri.close()
            except Exception:
                pass


if __name__ == "__main__":
    k = Kontrol("mock")
    assert k.bagli and k.mock_mu
    # acilista hiz duzeyi karta bildirilir (kart kendi varsayilaninda kalmasin)
    assert (k.mock.max_hiz, k.mock.ivme) == P.HIZ_TABLO[P.HIZ_VARSAYILAN]

    k.aci(45.0, 12.0)
    assert (k.mock.pan_hedef, k.mock.tilt_hedef) == (45.0, 12.0)
    n = len(k.mock.kayit)
    k.aci(45.0, 12.0)                       # ayni aci -> komut gonderilmez
    assert len(k.mock.kayit) == n, k.mock.kayit[-1]
    k.aci(45.0, 20.0)                       # yalniz tilt degisti -> tek satir
    assert len(k.mock.kayit) == n + 1 and k.mock.kayit[-1].startswith("T")

    # acilista lazer gucu de karta bildirilir (tam guc DEGIL, ayarli guc)
    assert k.mock.lazer_guc == P.LAZER_GUC_VARSAYILAN == k.lazer_guc

    d = k.ates(True)
    assert d["lazer"] and k.mock.lazer and d["durum_ad"] == "ATEŞ", d
    assert d["lazer_guc"] == P.LAZER_GUC_VARSAYILAN, d
    k.guc_ayarla(70)                        # ates SIRASINDA guc degisebilir
    assert k.mock.lazer_guc == 70 and k.mock.lazer, "guc degisimi atesi kesmemeli"
    assert k.guc_ayarla(500)["lazer_guc"] == P.LAZER_GUC_MAX
    k.ates(False); k.guc_ayarla(P.LAZER_GUC_VARSAYILAN)
    d = k.estop(True)
    assert d["durum_ad"] == "E-STOP" and not d["lazer"] and not k.mock.lazer, d
    k.estop(False)

    # hiz duzeyi: karta S+A olarak gider ve ozette gorunur
    d = k.hiz_ayarla(P.H_HIZLI)
    assert (k.mock.max_hiz, k.mock.ivme) == P.HIZ_TABLO[P.H_HIZLI]
    assert d["hiz_ad"] == "Hızlı", d
    assert k.hiz_ayarla(99)["hiz"] == P.HIZ_VARSAYILAN                  # gecersiz -> varsayilan

    # tilt limiti kontrol katmaninda da tutulur (ekranla hedef kopmasin)
    k.aci(0.0, 500.0)
    assert k.tilt_hedef == P.TILT_MAX == k.mock.tilt_hedef

    # home: iki ekseni de sifira surer
    k.home()
    assert (k.mock.pan_hedef, k.mock.tilt_hedef) == (0.0, 0.0)

    # kart metni ozete dusuyor mu (alt cubuk bunu gosterir)
    assert k.durum["esp_satir"], k.satirlar
    print("kontrol testleri OK — mutlak aci, ates/estop, hiz duzeyi, kart metni")
