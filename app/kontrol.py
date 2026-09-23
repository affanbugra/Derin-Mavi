# -*- coding: utf-8 -*-
"""Kontrol katmani — arayuzun ESP32 ile konusma API'si (mock/gercek TEK arayuz).

ESP32'de iki step motor (pan = yatay, tilt = dikey) ve lazer var; bu katman arayuzun
tek muhatabidir — arayuz hicbir yerde elle komut satiri kurmaz (bkz. protokol.py).

Kaynak secimi (donanim-bagimsiz, CLAUDE.md ilke 7):
    DERINMAVI_ESP=mock   -> MockESP32 (varsayilan; donanimsiz gelistirme)
    DERINMAVI_ESP=COM5   -> gercek seri port (pyserial; donanim gelince)
    DERINMAVI_ESP=off    -> kontrol kapali (yalniz goruntu isleme)

DIKEY EKSEN (tilt) AYRI BIR KARTA VERILEBILIR — `DERINMAVI_TILT` ile:
    DERINMAVI_TILT=off   -> tilt eski kartta kalir ("T<derece>"), varsayilan
    DERINMAVI_TILT=mock  -> sahte ESP32-S3/HSD57 karti (donanimsiz test)
    DERINMAVI_TILT=COM3  -> gercek ESP32-S3 + HSD57 karti (bkz. tilt_surucu.py)

Neden: tilt ekseni artik KOL-BIYEL mekanizmasiyla, kapali cevrim HSD57 surucu ve
ayri bir ESP32-S3 ile suruluyor. Ham kart 0..60 fiziksel kol acisi konusur; bu
katmanin dis API'si -30..+30 operator acisidir (0 = fiziksel kol 30) ve KONUMU
GERI BILDIRIR (STATE3). Pan tarafi degismez.

YONLENDIRME NEREDE: yalniz `aci()` icinde. Arayuz hicbir sey bilmez — hareketin
tek kapisi (arayuz_qt._aci_hareket) yine buraya, buradan da dogru karta gider.
Ekseni ikiye bolen ikinci bir yol acilsaydi (arayuz bazen suruculeri dogrudan
cagirsaydi) E-Stop/yasak alan/limit kontrollerinden KACAN bir hareket yolu
olusurdu — bu mimaride hareketin tek kapisi olmasinin sebebi tam olarak budur.

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
import tilt_surucu as T
from mock_esp32 import MockESP32

KAYNAK = os.environ.get("DERINMAVI_ESP", "mock").strip() or "mock"


class Kontrol:
    def __init__(self, kaynak=None, tilt_kaynak=None):
        self.kaynak = (kaynak or KAYNAK).lower()
        # DIKEY EKSEN SURUCUSU (ayri kart). "off" ise tilt eski kartta kalir ve
        # bu nesne hicbir seyi degistirmez — mevcut davranis birebir korunur.
        self.tilt = T.TiltSurucu(tilt_kaynak)
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
        # ACILIS HIZALAMASI: kart (ESP32-S3) uygulama kapaninca resetlenmez; eksenler en
        # son neredeyse oradadir. Hedefler 0 kabul edilirse ilk komut (or. "tilt 5")
        # pan'i hic gondermez (0 == 0) ve namlu yana bakarken yazilim onu merkezde sanir
        # — sahada pan 28 derecede kalirken test "merkeze aldim" dedi. Ilk konum
        # raporunda hedefler OLCULENE esitlenir; arayuz `acilis_hizalama`yi tuketir.
        self._olculen_hizalandi = False
        self.acilis_hizalama = None
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
        # Tilt ayri kartta ise pan karti olmasa da (DERINMAVI_ESP=off) sistem
        # "bagli"dir: arayuzun 250 ms'lik yoklama dongusu bu bayraga bakar ve o
        # dongu durursa tilt kartinin CANLILIGI kesilir, kart kendini kilitler.
        return self.mock is not None or self.seri is not None or self.tilt.bagli

    @property
    def mock_mu(self):
        return self.mock is not None

    @property
    def tilt_ayri(self):
        """Dikey eksen ayri kartta mi? (yonlendirmenin tek kosulu)"""
        return self.tilt.bagli

    @property
    def pan_ayri(self):
        """Pan ekseni tilt karti uzerinden mi suruluyor?

        Yeni ESP32-S3 firmware'i pan motorunu da (GPIO10/11) surer ve PAN1 yayinlar.
        Gercek bir eski pan karti (DERINMAVI_ESP=COMx) bagliysa pan ORADA kalir:
        iki kart ayni ekseni surmesin. Pan karti mock/off ise pan buraya gelir."""
        return self.seri is None and self.tilt_ayri and self.tilt.pan_destekli

    @property
    def pan_olculen(self):
        """Kartin bildirdigi pan acisi (darbe sayimindan) — yoksa None."""
        return self.tilt.pan_aci if self.pan_ayri else None

    @property
    def takip_geri_bildirimli(self):
        """Iki eksen de konumunu bildiriyor mu? (surekli takip kontrolcusunun sarti)"""
        return self.tilt_ayri and self.pan_ayri

    @property
    def yorunge_destekli(self):
        """Otonom takip YORUNGE kipinde mi surulebilir? (iki eksen bu kartta + firmware Y/PY)"""
        return self.pan_ayri and self.tilt.yorunge_destekli is True

    def yorunge(self, pan_der=None, pan_hiz=None, tilt_der=None, tilt_hiz=None):
        """YORUNGE komutu: "hedef su an burada ve bu HIZLA gidiyor" (otonom takip).

        Konum kipinden (aci) farki: kart referansi kendisi ilerletir, motor hedefin
        hizinda akar, varis/durus ani olmaz (bkz. firmware yorunge_core.h). None
        verilen eksene bu turda komut gitmez; kart o eksenin son komutunu 150 ms
        ilerletip yumusakca durur. Hareketin tek kapisi yine arayuz_qt._aci_hareket."""
        if pan_der is not None and pan_hiz is not None:
            pan_der = T.pan_kirp(pan_der)
            self.pan_hedef = pan_der
            self.tilt.pan_yorunge(pan_der, pan_hiz)
        if tilt_der is not None and tilt_hiz is not None:
            tilt_der = T.aci_kirp(tilt_der)
            self.tilt_hedef = tilt_der
            self.tilt.yorunge(tilt_der, tilt_hiz)
        return self.durum

    def tilt_zamaninda(self, t):
        """Kolun `t` anindaki acisi (kare cekildigi an) — yoksa None."""
        return self.tilt.aci_zamaninda(t) if self.tilt_ayri else None

    def pan_zamaninda(self, t):
        """Pan'in `t` anindaki acisi — yoksa None."""
        return self.tilt.pan_zamaninda(t) if self.pan_ayri else None

    def pan_sifirla(self):
        """Pan'in su anki konumunu 0 kabul ettir; arayuz hedefi de 0'a ceker."""
        if not self.pan_ayri:
            return False
        ok = self.tilt.pan_sifirla()
        if ok:
            self.pan_hedef = 0.0
        return ok

    @property
    def tilt_tavan(self):
        """Dikey eksenin operator cercevesindeki tavani. Kol-biyel mekanizmasinda
        +30 (fiziksel kol 60), eski dogrudan tahrikte P.TILT_MAX."""
        return T.ACI_MAX if self.tilt_ayri else P.TILT_MAX

    @property
    def tilt_olculen(self):
        """Kartin bildirdigi operator acisi (-30..+30 derece) — yoksa None.

        kontrol.py'nin bas yorumundaki "kart konum geri bildirimi kazanirsa tek
        degisecek yer burasi" notu: yeni tilt karti kazandi. Arayuz dikey aci
        referansini buradan tazeler, boylece kaybolan/geciken komut kalici
        sapmaya donusmez. Eski kart icin None doner ve davranis degismez."""
        return self.tilt.aci if self.tilt_ayri else None

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
                # Dikey eksen ayri karttaysa OLCULEN aci da verilir. Arayuz
                # "hedef" ile "olculen"i ayri yazmali: ikisi ayni sanilirsa kartin
                # yetisemedigi durum gorunmez olur.
                "tilt_ayri": self.tilt_ayri,
                "tilt_olculen": self.tilt_olculen,
                "tilt_ozet": self.tilt.ozet(),
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
                # ⚠ Dikey eksen AYRI KARTTAYSA eski kartin bildirdigi tilt bizi
                # ILGILENDIRMEZ: o kartin tilt motoru bu mekanizmada bagli degil,
                # dolayisiyla hep 0 yazar ve kolun gercek acisini SIFIRLAR
                # (ekranda kol 34 derecedeyken "0" gorunurdu). Yalniz pan alinir.
                if self.tilt_ayri:
                    self.pan_hedef = konum[0]
                    olculen = self.tilt.aci
                    konum = (konum[0], olculen if olculen is not None else self.tilt_hedef)
                else:
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
        monitorden elle verilen STOP gibi olaylardan haberimiz olmaz.

        TILT KARTININ NABZI DA BURADA. Bu dongu (arayuzde 250 ms'lik esp_timer)
        durursa tilt karti 350 ms icinde KENDINI KILITLER — uygulama donarsa/kapanirsa
        kol komut almaya devam etmesin diye. Yani nabiz ayri bir zamanlayiciya
        tasinmamali: okuma dongusuyle ayni kaderi paylasmasi bilincli bir tercihtir."""
        if self.tilt.bagli:
            self.tilt.yokla()
            # Yeni tek kartta PAN1 + STATE3 birlikte beklenir. Ayrı eski pan kartı
            # bağlıysa pan konumu zaten yazılımın inancıdır; tilt STATE3 gelir
            # gelmez hizalanıp açılışta -30'dan 0'a çıkabilmelidir.
            if (not self._olculen_hizalandi and self.tilt.aci is not None
                    and (self.seri is not None or
                         (self.pan_ayri and self.tilt.pan_aci is not None))):
                self._olculen_hizalandi = True
                if self.pan_ayri:
                    self.pan_hedef = self.tilt.pan_aci
                self.tilt_hedef = self.tilt.aci
                self.acilis_hizalama = (self.pan_hedef, self.tilt_hedef)
            for s in self.tilt.yeni_satirlar():
                self._kart_yaziyor(f"TILT: {s}")
            if self.tilt.hata:
                self.hata, self.tilt.hata = self.tilt.hata, None
            if self.tilt.kart_resetlendi:
                # Kart acilista "kol fiziksel olarak 0'da" varsayar. Kol yukaridayken
                # reset olduysa bildirdigi aci artik GERCEK degildir; arayuz uyarir.
                self.tilt.kart_resetlendi = False
                self.kart_resetlendi = True
                self.tilt_hedef = self.tilt.aci or 0.0
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
        Yalnizca DEGISEN eksen gonderilir: hatta gereksiz komut dolastirmayiz.

        TILT AYRI KARTTAYSA dikey eksen oraya yonlendirilir (tilt_surucu). Eski
        karta "T" gitmez: iki kart ayni anda ayni ekseni surerse mekanik ikisinin
        ortasinda bir yerde kalir."""
        satirlar = []
        if self.pan_ayri:
            pan_der = T.pan_kirp(pan_der)
            if abs(pan_der - self.pan_hedef) > 0.005:
                self.pan_hedef = pan_der
                self.tilt.pan_git(pan_der)
        elif abs(pan_der - self.pan_hedef) > 0.005:
            satirlar.append(P.pan(pan_der))
            self.pan_hedef = pan_der
        if self.tilt_ayri:
            tilt_der = T.aci_kirp(tilt_der)         # operator araligi (-30..+30)
            if abs(tilt_der - self.tilt_hedef) > 0.005:
                self.tilt_hedef = tilt_der
                # Kart mesgulse surucu PC tarafinda bekletir ve EN TAZE hedefi
                # yollar (bkz. tilt_surucu: tek bekleme yuvasi uyarisi).
                self.tilt.git(tilt_der)
        else:
            tilt_der = P.tilt_kirp(tilt_der)
            if abs(tilt_der - self.tilt_hedef) > 0.005:
                satirlar.append(P.tilt(tilt_der))
                self.tilt_hedef = tilt_der
        if not satirlar:
            return self.durum
        return self._gonder(*satirlar)

    def tilt_sifirla(self):
        """Dikey eksen: "kol SU AN fiziksel olarak en altta" (bkz. TiltSurucu.sifirla).

        Arayuzun inandigi hedef de 0'a cekilir; yoksa ekran eski aciyi gosterir ve
        bir sonraki manuel dokunus oradan hesaplanirdi."""
        if not self.tilt_ayri:
            return False
        ok = self.tilt.sifirla()
        if ok:
            self.tilt_hedef = T.ACI_MIN
        return ok

    def tilt_dur(self):
        """Dikey ekseni OLDUGU YERDE durdurur ve hedefi gercege geri ceker.

        Basili-tutma birakildiginda cagrilir. Surekli hareket, karta "sinira kadar
        git" diye TEK bir uzak hedef verir; tus birakildiginda kol yolun ortasinda
        durur. `tilt_hedef` o uzak degerde kalirsa arayuz kolun gercekte olmadigi
        bir aciyi gosterir ve bir sonraki manuel dokunus oradan hesaplanir —
        yani her basili-tutma ekrani gercekten biraz daha koparirdi."""
        if not self.tilt_ayri:
            return self.durum
        self.tilt.dur()
        olculen = self.tilt.aci
        if olculen is not None:
            self.tilt_hedef = olculen
        return self.durum

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
            if self.tilt_ayri:
                # ⚠ YENI TILT KARTINDA DAVRANIS FARKLI: kol OLDUGU YERDE DURUR,
                # 0'a PARK ETMEZ. Acil durdurma yeni bir hareket BASLATMAMALIDIR;
                # eski karttaki park davranisi lazerli namlunun yukarida asili
                # kalmamasi icindi, ama bu mekanizmada 0'a inmek 60 dereceden
                # asagi dogru komutlu bir hareket demektir — acil durdurmada
                # istenmeyen sey tam olarak budur.
                # ⚠ TAKIMA SORU: lazer bu kola binecekse park davranisi yeniden
                # degerlendirilmeli (kol yukarida kalir). Karar takimin.
                self.tilt.dur()
                self.tilt_hedef = self.tilt.aci if self.tilt.aci is not None else self.tilt_hedef
            else:
                # ⚠ 23.09: ESKI YOLDA DA PARK YOK, olundugu yerde donulur.
                # Sebep tercih degil TUTARLILIK: mock/kart acil durdurmada iki ekseni
                # de KILITLIYOR (mock_esp32: "pan_hedef, tilt_hedef = pan, tilt").
                # Laptop tarafi tilt'i 0 kabul edince ekrandaki aci kartin gercek
                # konumundan KOPUYORDU. Sartname Yetenek 3 de "sistem durur" diyor;
                # park etmek bir HAREKETTIR. Yeni tilt karti da zaten donduruyor.
                pass
        return self._gonder(P.DUR if aktif else P.DEVAM)

    def home(self):
        """Merkeze al (0°, 0°). ESP'de limit switch homing'i YOK — bu yalnizca
        'bilinen merkeze don' demektir; gercek homing kart tarafina eklenecek.
        Ayri tilt kartinda operator 0° = fiziksel kol 30°'dir."""
        self.pan_hedef = self.tilt_hedef = 0.0
        if self.tilt_ayri:
            self.tilt.git(0.0)             # operator merkezi = fiziksel kol 30 derece
            if self.pan_ayri:
                self.tilt.pan_git(0.0)
                return self.durum
            return self._gonder(P.pan(0.0))
        return self._gonder(P.pan(0.0), P.tilt(0.0))

    def guc_ayarla(self, yuzde):
        """Lazer gucu (%). Kalicidir: sonraki her ates bu gucte olur.

        Tam guc kullanilmiyor (varsayilan %40). ⚠ Dusuk guc dwell suresini uzatir —
        gercek patlama suresi olculup bu deger yeniden degerlendirilmelidir."""
        self.lazer_guc = P.guc_kirp(yuzde)
        return self._gonder(P.lazer_guc(self.lazer_guc))

    def hiz_ayarla(self, seviye):
        """Motor hiz duzeyi (tavan hiz + ivme). ESP'ye iki satir olarak gider.

        Dikey eksen ayri karttaysa AYNI kademe oraya da bildirilir (Z komutu).
        Kademeler her iki tarafta da 1/2/3 olarak numaralandirildigi icin
        arayuzdeki tek secim iki ekseni birden ayarlar; yalniz sayisal karsiliklari
        farklidir (pan derece/sn konusur, tilt darbe/sn)."""
        self.hiz = P.hiz_kirp(seviye)
        if self.tilt_ayri:
            self.tilt.hiz_ayarla(self.hiz)
        return self._gonder(*P.hiz(self.hiz))

    def hiz_profilleri(self, seviye=None):
        """Secili kademenin gercek pan ve tilt (hiz, ivme) profillerini dondur.

        Ayri HSD57 tilt kartinin mekanigi ve ivmesi pan ekseninden farklidir.
        Takip dongusu komut kirpma/mesgul suresini hesaplarken tek bir profil
        kullanirsa tilt'i oldugundan yavas sanir ve gereksiz bekler.  Tek kartli
        eski sistemde iki eksen de protokol profilini kullanmaya devam eder.
        """
        kademe = self.hiz if seviye is None else P.hiz_kirp(seviye)
        pan = T.PAN_HIZ_TABLO[kademe] if self.pan_ayri else P.HIZ_TABLO[kademe]
        tilt = T.HIZ_TABLO[kademe] if self.tilt_ayri else pan
        return pan, tilt

    def kapat(self):
        # Tilt karti KALICI olarak kapatilir (D): uygulama kapanirken kol komut
        # kabul eder halde kalmamali. Kart zaten canlilik kesilince kilitlenir,
        # ama acikca soylemek 350 ms'lik boslugu da kapatir.
        self.tilt.kapat(kalici=True)
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
    assert k.hiz_profilleri() == (P.HIZ_TABLO[P.HIZ_VARSAYILAN],) * 2

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

    # tilt ayri kart KAPALIYKEN (varsayilan) davranis birebir eskisi gibi olmali
    assert not k.tilt_ayri and k.tilt_olculen is None
    assert k.tilt_tavan == P.TILT_MAX

    # ---------------------------------------------------------------
    #  DIKEY EKSEN AYRI KARTTA (ESP32-S3 + HSD57, kol-biyel mekanizmasi)
    # ---------------------------------------------------------------
    k2 = Kontrol("mock", tilt_kaynak="mock")
    saat = [5000.0]
    k2.tilt._saat = lambda: saat[0]                 # testte gercek zamani beklemeyelim
    k2.tilt.mock.t = k2.tilt.mock.son_canli = saat[0]
    k2.tilt.mock.pan_destek = False   # PAN'SIZ (eski) tilt firmware'i; pan'li hal: test 6

    def tilt_tik(sure=0.25):
        saat[0] += sure
        k2.oku()                                    # arayuzdeki 250 ms'lik yoklama

    tilt_tik(); tilt_tik()
    assert k2.tilt_ayri and k2.tilt.hazir, k2.tilt.ozet()
    # Operator cercevesi: kol 0..60 -> -30..+30 (bkz. tilt_surucu "IKI ACI CERCEVESI")
    assert k2.tilt_tavan == T.ACI_MAX == 30.0       # kol-biyel tavani, 180 DEGIL
    assert k2.hiz_profilleri(P.H_NORMAL) == \
        (P.HIZ_TABLO[P.H_NORMAL], T.HIZ_TABLO[T.H_NORMAL])
    assert k2.hiz_profilleri(P.H_NORMAL)[1][1] > k2.hiz_profilleri(P.H_NORMAL)[0][1], \
        "ayri tilt kartinin ivmesi pan profiliyle ezilmemeli"

    # 1. ⭐ YONLENDIRME: tilt ESKI KARTA GITMEZ, yeni karta gider. Iki kart ayni
    #    ekseni surerse mekanik ikisinin ortasinda kalir.
    eski_tilt = k2.mock.tilt_hedef
    k2.aci(45.0, 12.0)
    assert k2.mock.pan_hedef == 45.0, "pan eski kartta kalmaliydi"
    assert k2.mock.tilt_hedef == eski_tilt, "tilt eski karta da gitti"
    assert not any(s.startswith("T") for s in k2.mock.kayit), k2.mock.kayit
    for _ in range(40):
        tilt_tik()
        if not k2.tilt.hareket and k2.tilt._bekleyen_hedef is None:
            break
    assert abs(k2.tilt_olculen - 12.0) < 0.5, k2.tilt_olculen

    # 2. Kirpma kol araligina gore yapilir (P.TILT_MAX=180 degil, +30)
    k2.aci(45.0, 500.0)
    assert k2.tilt_hedef == 30.0, k2.tilt_hedef

    # 3. E-STOP: kol OLDUGU YERDE durur, 0'a park ETMEZ (acil durdurma yeni bir
    #    hareket baslatmamali) ve ozet gercekten durdugu yeri gosterir.
    for _ in range(6):
        tilt_tik()
    durdugu = k2.tilt_olculen
    assert durdugu > 12.0, "kol ust uca dogru ilerlemis olmaliydi"
    d = k2.estop(True)
    assert d["durum_ad"] == "E-STOP" and d["tilt"] != 0.0, d
    assert abs(d["tilt"] - durdugu) < 0.01, (d["tilt"], durdugu)
    tilt_tik()
    assert not k2.tilt.hareket, "E-Stop hareketi kesmeliydi"
    k2.estop(False)

    # 4. Ozet: HEDEF ile OLCULEN ayri ayri verilir (kartin yetisemedigi gorunsun)
    d = k2.durum
    assert d["tilt_ayri"] and d["tilt_olculen"] is not None
    assert d["tilt_ozet"]["kalibre"] and d["tilt_ozet"]["ad"] in ("hazır", "hareket")

    # 5. KALIBRE DEGILSE hicbir hareket gecmez (mekanigi korur)
    k3 = Kontrol("mock", tilt_kaynak="mock")
    saat3 = [6000.0]
    k3.tilt._saat = lambda: saat3[0]
    k3.tilt.mock.t = k3.tilt.mock.son_canli = saat3[0]
    k3.tilt.mock.kalibre = False
    for _ in range(3):
        saat3[0] += 0.25
        k3.oku()
    assert not k3.tilt.kalibre and not k3.tilt.hazir
    k3.aci(0.0, 30.0)
    saat3[0] += 0.25
    k3.oku()
    assert not any(s.startswith("G") for s in k3.tilt.mock.kayit), k3.tilt.mock.kayit

    # 5b. ACILIS HIZALAMASI: kart pan 20 / tilt 10 derecede kalmisken acilan kontrol,
    #     hedefleri olculene esitler; "pan 0, tilt 5" komutu pan'i da GERCEKTEN gonderir.
    kh = Kontrol("off", tilt_kaynak="mock")
    saat5 = [6500.0]
    kh.tilt._saat = lambda: saat5[0]
    kh.tilt.mock.t = kh.tilt.mock.son_canli = saat5[0]
    kh.tilt.mock.pan_pos = kh.tilt.mock.pan_hedef = int(round(20.0 * T.PAN_DARBE_DER))
    kh.tilt.mock.pos = kh.tilt.mock.hedef = kh.tilt.mock._darbe(10.0)
    for _ in range(4):
        saat5[0] += 0.1
        kh.oku()
    assert kh.acilis_hizalama is not None and abs(kh.acilis_hizalama[0] - 20.0) < 0.05, kh.acilis_hizalama
    # mock KOL 10 derecede; operator cercevesinde bu T.aci_karsiligi(10) = -20
    assert abs(kh.pan_hedef - 20.0) < 0.05 and abs(kh.tilt_hedef - T.aci_karsiligi(10.0)) < 0.1
    kh.aci(0.0, 5.0)
    for _ in range(40):
        saat5[0] += 0.1
        kh.oku()
    assert abs(kh.pan_olculen) < 0.1 and abs(kh.tilt_olculen - 5.0) < 0.2, (kh.pan_olculen, kh.tilt_olculen)

    # 6. PAN tilt kartinda (yeni firmware): pan oraya gider, eski (mock) karta GITMEZ
    k4 = Kontrol("mock", tilt_kaynak="mock")
    saat4 = [7000.0]
    k4.tilt._saat = lambda: saat4[0]
    k4.tilt.mock.t = k4.tilt.mock.son_canli = saat4[0]
    for _ in range(3):
        saat4[0] += 0.25; k4.oku()
    assert k4.pan_ayri
    eski_pan = k4.mock.pan_hedef
    k4.aci(15.0, 10.0)
    assert k4.tilt.mock.kayit[-1] == "P15.000" or "P15.000" in k4.tilt.mock.kayit
    assert k4.mock.pan_hedef == eski_pan, "pan iki karta birden gitmemeli"
    for _ in range(12):
        saat4[0] += 0.25; k4.oku()
    assert abs(k4.pan_olculen - 15.0) < 0.05, k4.pan_olculen
    assert k4.hiz_profilleri()[0] == T.PAN_HIZ_TABLO[k4.hiz]
    k4.home()
    for _ in range(12):
        saat4[0] += 0.25; k4.oku()
    assert abs(k4.pan_olculen) < 0.05
    k4.tilt.mock.pan_destek = False                 # eski firmware: pan eski yola doner
    for _ in range(4):
        saat4[0] += 0.25; k4.oku()
    assert not k4.pan_ayri
    k4.aci(5.0, 0.0)
    assert k4.mock.pan_hedef == 5.0

    print("kontrol testleri OK — mutlak aci, ates/estop, eksene ozel hiz profili, "
          "kart metni, tilt yonlendirmesi (ayri kart), kol araligi, E-Stop'ta yerinde durma")
