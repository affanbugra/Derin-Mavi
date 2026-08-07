# -*- coding: utf-8 -*-
"""DERIN MAVI — GUVENLIK KAPILARI regresyon testi (donanim ve pencere GEREKTIRMEZ).

Calistir:  python app/kapi_testleri.py

Neden ayri bir dosya: diger her modul kendi `__main__` blogunda test edilir, ama
`arayuz_qt.py`'nin `__main__`'i uygulamayi ACAR. Oysa sartnamenin can alici davranislari
(E-Stop hareketi keser, ates yasak acida verilmez, ekrandaki aci cihazin hedefinden
kopmaz) tam olarak orada yasiyor ve gecmiste hepsi en az bir kez sessizce bozuldu
(bkz. CLAUDE.md §12 B1/B2/B4). Bu dosya o kapilari Qt penceresi acmadan dener:
MainWindow metodlari, ihtiyac duyduklari asgari yuzeye sahip SAHTE bir nesne uzerinde
calistirilir; ESP32 tarafinda gercek mock kullanilir.
"""
import time

import arayuz_qt as A
import gamepad as gamepad_mod
import kontrol as kontrol_mod
import protokol as P


class SahteEtiket:
    """Metin/stil cagrilarini yutan sahte QLabel."""

    def setText(self, *a):
        pass

    def setStyleSheet(self, *a):
        pass


class SahteButon(SahteEtiket):
    """Isaretli + etkin durumunu tutan sahte QPushButton."""

    def __init__(self):
        self._c = False
        self._e = True

    def isChecked(self):
        return self._c

    def setChecked(self, v):
        self._c = v

    def isEnabled(self):
        return self._e

    def setEnabled(self, v):
        self._e = bool(v)


class SahteKaydirici:
    """Degerini tutan sahte QSlider (blockSignals cagrilarini yutar)."""

    def __init__(self, v=0):
        self._v = int(v)

    def value(self):
        return self._v

    def setValue(self, v):
        self._v = int(v)

    def blockSignals(self, *a):
        pass


class SahteGamepad:
    """Tek bir yoklamanin sonucunu donduren sahte Gamepad (donanim gerektirmez).

    `kopuk=True` cihazin okuma sirasinda cikarilmasini taklit eder: `oku()` bos durum
    dondurur ve `bagli` False'a duser (gercek modulun kopma davranisi)."""

    def __init__(self, pan=0.0, tilt=0.0, ates=False, estop=False, merkez=False,
                 hiz_yukari=False, hiz_asagi=False, kopuk=False):
        self.ad = "Sahte Pad"
        self._kopuk = kopuk
        self.bagli = not kopuk
        self._d = gamepad_mod.Durum()
        self._d.pan, self._d.tilt = pan, tilt
        self._d.ates, self._d.estop, self._d.merkez = ates, estop, merkez
        self._d.hiz_yukari, self._d.hiz_asagi = hiz_yukari, hiz_asagi

    def oku(self):
        if self._kopuk:
            self.bagli = False
            return gamepad_mod.Durum()
        return self._d

    def tara(self):
        return False

    def kapat(self):
        pass


class SahteTimer:
    """Sadece calisiyor/durdu durumunu tutan sahte QTimer."""

    def __init__(self):
        self.aktif = False

    def start(self, *a):
        self.aktif = True

    def stop(self):
        self.aktif = False

    def isActive(self):
        return self.aktif


class SahtePencere:
    """MainWindow'un hareket/ates/hiz kapilari icin ihtiyac duydugu asgari yuzey."""
    _aci_hareket = A.MainWindow._aci_hareket
    _ates_bas = A.MainWindow._ates_bas
    _ates_kes = A.MainWindow._ates_kes
    _ates_kisayolu = A.MainWindow._ates_kisayolu
    atis_yasak_mi = A.MainWindow.atis_yasak_mi
    _gamepad_tik = A.MainWindow._gamepad_tik
    _gamepad_durum_yaz = A.MainWindow._gamepad_durum_yaz
    GP_TARAMA_TIK = A.MainWindow.GP_TARAMA_TIK
    _esp_goster = A.MainWindow._esp_goster      # gercegi: lazer + donanimsal E-Stop yansimasi
    _esp_yokla = A.MainWindow._esp_yokla
    _estop_konum_uygula = A.MainWindow._estop_konum_uygula
    _hiz_sec = A.MainWindow._hiz_sec
    _tekrar_tik = A.MainWindow._tekrar_tik
    _tekrar_durdur = A.MainWindow._tekrar_durdur
    YON_TABLO = A.MainWindow.YON_TABLO
    _hiz_bilgi_yaz = A.MainWindow._hiz_bilgi_yaz
    _lazer_bilgi_yaz = A.MainWindow._lazer_bilgi_yaz
    _lazer_guc_degisti = A.MainWindow._lazer_guc_degisti
    _step_btn_stil_guncelle = A.MainWindow._step_btn_stil_guncelle

    def _ci(self, ad, renk, alt):               # alt cubuk segmenti — testte gorsel yok
        pass

    def __init__(self):
        self.mod = "Manuel"
        self.thread = None                # isinstance(VideoThread) -> False
        self.pan_aci = 0.0                # ekran (0-360 sarmali)
        self.pan_ham = 0.0                # karta giden sarmasiz azimut
        self.tilt_aci = 0.0
        self.max_tilt_limit = 60.0
        self.pan_yasak_aktif = self.tilt_yasak_aktif = self.atis_yasak_aktif = False
        self.pan_yasak_min = self.pan_yasak_max = 0.0
        self.tilt_yasak_min = self.tilt_yasak_max = 0.0
        self.atis_pan_min = self.atis_pan_max = 0.0
        self.pan_val_lbl = SahteEtiket()
        self.tilt_val_lbl = SahteEtiket()
        self.bolge_status = SahteEtiket()
        self.sb_msg = SahteEtiket()
        self.fire_btn = SahteButon()
        self.hiz_seviye = P.HIZ_VARSAYILAN
        self.hiz_bilgi = SahteEtiket()
        self.hiz_btns = {s: SahteButon() for s in P.HIZ_SEVIYELER}
        self.lazer_guc = P.LAZER_GUC_VARSAYILAN
        self.lazer_durum = SahteEtiket()
        self.lazer_sl = SahteKaydirici(P.LAZER_GUC_VARSAYILAN)
        self.lazer_btns = {g: SahteButon() for g in (20, 40, 70, 100)}
        self._basili_yonler = set()          # tusa basili tutma (surekli hareket)
        self._son_tekrar_t = 0.0
        self._tekrar_gecikme = SahteTimer()
        self._tekrar_timer = SahteTimer()
        self.btn_center = SahteButon()       # gamepad "merkez" kapisi bunun enabled'ina bakar
        self.gamepad = SahteGamepad()
        self._gp_son_t = time.time()
        self._gp_tarama = 0
        self.kontrol = kontrol_mod.Kontrol("mock")


def test_ekran_aci_kart_hedefi_ayni():
    """Ekrandaki aci ile kartin hedefi HER durumda ayni olmali (ozellikle limitte).

    Karta MUTLAK aci gider; ekran ve komut ayni kaynaktan turer, dolayisiyla kopma
    yapisal olarak imkansizdir. Test bunun korundugunu dogrular."""
    w = SahtePencere()
    for _ in range(12):                       # 12 x 5 = 60 -> tam limit
        w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == 60.0, w.tilt_aci
    assert w.kontrol.mock.tilt_hedef == 60.0, w.kontrol.mock.tilt_hedef

    # Limitte fazladan komut: gonderilecek yeni bir aci yok, bos komut da atilmamali.
    komut = len(w.kontrol.mock.kayit)
    w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == 60.0
    assert len(w.kontrol.mock.kayit) == komut, w.kontrol.mock.kayit[-1]

    w._aci_hareket(0.0, -5.0)                 # asagi normal calisir
    assert w.tilt_aci == 55.0 and w.kontrol.mock.tilt_hedef == 55.0

    # Kismi kirpma: 55°'de +8 istenir, ancak +5 uygulanabilir -> ikisi de 60 olmali.
    w._aci_hareket(0.0, 8.0)
    assert w.tilt_aci == 60.0, w.tilt_aci
    assert w.kontrol.mock.tilt_hedef == 60.0, w.kontrol.mock.tilt_hedef


def test_azimut_sarmasiz_gider():
    """Ekranda azimut 0-360 sarmalidir ama karta SUREKLI aci gitmeli.

    350°'den 10°'ye gecerken "P370" denmezse motor kisa yoldan gitmez, 340° geri
    doner (AccelStepper mutlak konuma gider)."""
    w = SahtePencere()
    w._aci_hareket(350.0, 0.0)
    assert w.pan_aci == 350.0 and w.kontrol.mock.pan_hedef == 350.0
    w._aci_hareket(20.0, 0.0)                 # sarma noktasi
    assert w.pan_aci == 10.0, w.pan_aci                       # EKRAN sarmali
    assert w.kontrol.mock.pan_hedef == 370.0, w.kontrol.mock.pan_hedef   # KART surekli


def test_ates_sirasinda_yasak_alan():
    """Lazer acikken atisa-yasak bolgeye GIRILIRSE ates kesilmeli.

    `_ates_bas` yalnizca butona basildigi ani denetler; bolgeye ates surerken
    girmek de engellenmeli (sartname: atisa-yasak alan)."""
    w = SahtePencere()
    w.atis_yasak_aktif = True
    w.atis_pan_min, w.atis_pan_max = 40.0, 50.0
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    assert w.kontrol.durum["lazer"] is True

    w._aci_hareket(30.0, 0.0)                 # guvenli bolge -> ates surer
    assert w.kontrol.durum["lazer"] is True, "guvenli bolgede ates kesilmemeliydi"

    w._aci_hareket(15.0, 0.0)                 # pan 45 -> YASAK bolge
    assert w.fire_btn.isChecked() is False, "ates butonu acik kaldi"
    assert w.kontrol.durum["lazer"] is False, "yasak bolgede lazer sonmedi"


def test_harekete_yasak_alan():
    """Harekete yasak aci araligina giren komut UYGULANMAMALI (aci da degismemeli)."""
    w = SahtePencere()
    w.pan_yasak_aktif = True
    w.pan_yasak_min, w.pan_yasak_max = 100.0, 140.0
    assert w._aci_hareket(90.0, 0.0) is True and w.pan_aci == 90.0
    assert w._aci_hareket(20.0, 0.0) is False, "yasak araliga girildi"
    assert w.pan_aci == 90.0, w.pan_aci


def test_estop_hareketi_keser():
    """E-Stop aktifken hicbir hareket komutu gecmez ve ekrandaki aci DEGISMEZ
    (CLAUDE.md §12 B2 — sartname Yetenek 3)."""
    w = SahtePencere()
    # Kamera thread'i CALISTIRILMAZ; yalnizca `_aci_hareket`in baktigi tip + estop
    # alani gerekiyor (isinstance kontrolu bilincli: bkz. _aci_hareket B2 notu).
    w.thread = A.VideoThread(None, None)
    w.thread.estop = True
    assert w._aci_hareket(0.0, 5.0) is False
    assert w.tilt_aci == 0.0 and w.kontrol.mock.tilt_hedef == 0.0

    w.thread.estop = False                    # DEVAM -> hareket yeniden serbest
    assert w._aci_hareket(0.0, 5.0) is True
    assert w.tilt_aci == 5.0 and w.kontrol.mock.tilt_hedef == 5.0


def test_hiz_duzeyi_karta_gider():
    """Secilen motor hiz duzeyi karta S (tavan hiz) + A (ivme) olarak gitmeli."""
    w = SahtePencere()
    assert (w.kontrol.mock.max_hiz, w.kontrol.mock.ivme) == P.HIZ_TABLO[P.HIZ_VARSAYILAN]

    w._hiz_sec(P.H_HIZLI)
    assert w.hiz_seviye == P.H_HIZLI and w.kontrol.hiz == P.H_HIZLI
    assert w.hiz_btns[P.H_HIZLI].isChecked() and not w.hiz_btns[P.H_NORMAL].isChecked()
    assert (w.kontrol.mock.max_hiz, w.kontrol.mock.ivme) == P.HIZ_TABLO[P.H_HIZLI]
    assert w.kontrol.mock.kayit[-2:] == ["S75.0", "A200.0"], w.kontrol.mock.kayit[-2:]

    w._hiz_sec(P.H_YAVAS)                     # hassas nisan duzeyine in
    assert (w.kontrol.mock.max_hiz, w.kontrol.mock.ivme) == P.HIZ_TABLO[P.H_YAVAS]

    # Hiz degisimi hedefi BOZMAMALI (takip surerken kademe degistirilebilmeli)
    w._aci_hareket(30.0, 10.0)
    hedef = (w.kontrol.mock.pan_hedef, w.kontrol.mock.tilt_hedef)
    w._hiz_sec(P.H_NORMAL)
    assert (w.kontrol.mock.pan_hedef, w.kontrol.mock.tilt_hedef) == hedef


def test_kart_disaridan_durdurulursa_ates_birakilir():
    """Kart KENDI durursa (seri monitorden STOP, ileride donanim butonu) arayuz de
    atesi birakmali.

    Arayuz basmadigi icin `_estop_bas` calismaz; kart yapisal durum da yollamaz —
    tek ipucu metin cikisidir ("SISTEM DURDURULDU!") ve onu okuma yoklamasi getirir."""
    w = SahtePencere()
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    assert w.kontrol.durum["lazer"] is True

    # Kart disaridan durduruldu ve satirini yazdi (gercek portta bu satir readline
    # ile gelir; mock'ta dogrudan kontrol katmanina veriyoruz).
    w.kontrol._kart_yaziyor(w.kontrol.mock.islet("STOP"))
    w._esp_yokla()
    assert w.fire_btn.isChecked() is False, "kart durdu ama ATEŞ butonu açık kaldı"
    assert w.kontrol.durum["durum_ad"] == "E-STOP", w.kontrol.durum

    # Hareket kapisi da kapanmali: komut gonderilse kart yok sayar ama ekrandaki aci
    # ilerler ve ekran ile kartin hedefi koparadi.
    assert w._aci_hareket(10.0, 0.0) is False, "kart durmusken hareket komutu geçti"
    assert w.pan_aci == 0.0, w.pan_aci


def test_donanim_butonu_yazilimdan_kaldirilamaz():
    """DONANIM acil stop butonu basiliyken arayuzden DEVAM ET işe yaramamalı.

    Şartname E-Stop'u fiziksel bir kesicidir: yazılımdan geçilebiliyorsa E-Stop değildir.
    Kart START'ı reddeder ve "…(SISTEM DURDURULDU)" yazar; kontrol katmanı bu satırdan
    E-Stop'ta kaldığımızı anlar (arayüz de hareketi açmaz)."""
    w = SahtePencere()
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)

    w.kontrol._kart_yaziyor(w.kontrol.mock.buton_bas(True))   # butona basildi
    w._esp_yokla()
    assert w.fire_btn.isChecked() is False, "buton basildi ama ateş sürüyor"
    assert w.kontrol.mock.surucu_enerjili is True, "ENABLE kesildi (fırlamaya yol açar)"
    assert w.kontrol.estop_aktif is True

    w.kontrol.estop(False)                                   # arayüzden DEVAM ET
    assert w.kontrol.estop_aktif is True, "buton basılıyken yazılımdan devam edildi"
    assert w._aci_hareket(10.0, 0.0) is False, "buton basılıyken hareket komutu geçti"

    w.kontrol.mock.buton_bas(False)                          # buton bırakıldı
    assert w.kontrol.estop_aktif is True, "buton bırakılınca kendiliğinden devam etti"
    w.kontrol.estop(False)                                   # bilinçli DEVAM ET
    assert w.kontrol.estop_aktif is False
    assert w._aci_hareket(10.0, 0.0) is True


def test_kart_reseti_yakalanir():
    """Kart kendiliğinden yeniden başlarsa (besleme dalgalanması) arayüz bunu YAKALAMALI.

    Reset sonrası kartın konum sayacı sıfırdan başlar. Fark edilmezse ekrandaki açı eski
    değerde kalır ve sonraki her komut kaymış referansa göre gider — sessiz, tehlikeli bir
    sapma. Kart açılış banner'ı yazdığı için tek ipucu odur."""
    w = SahtePencere()
    w._aci_hareket(120.0, 30.0)
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    assert w.kontrol.mock.lazer is True

    # Kart reset attı ve açılış banner'ını yazdı (gerçek portta readline ile gelir).
    w.kontrol._kart_yaziyor("SISTEM AKTIF! (Gimbal + Lazer + Acil Stop)")
    w._esp_yokla()

    assert (w.pan_aci, w.pan_ham, w.tilt_aci) == (0.0, 0.0, 0.0), "ekran açısı sıfırlanmadı"
    assert (w.kontrol.pan_hedef, w.kontrol.tilt_hedef) == (0.0, 0.0)
    assert w.fire_btn.isChecked() is False, "reset sonrası ateş butonu açık kaldı"
    assert w.kontrol.kart_resetlendi is False, "bayrak temizlenmedi (her karede tekrarlar)"

    # ESP-ROM satırı da tanınmalı (kartın en erken çıktısı)
    w2 = SahtePencere()
    w2.kontrol._kart_yaziyor("ESP-ROM:esp32s3-20210327")
    assert w2.kontrol.kart_resetlendi is True


def test_estopta_enable_kesilmez():
    """ACIL DURDURMADA sürücü ENABLE'ı ASLA kesilmemeli.

    Kapalı çevrim sürücüde ENABLE kesilince rotor serbest kalır, mil kayar ve sürücünün
    encoder'ı bunu izler; ENABLE geri verildiğinde servo döngüsü biriken pozisyon hatasını
    KENDİ maksimum hızıyla kapatır → gimbal aniden fırlar. Sahada gözlendi (07.08).
    Bu hareketi ESP32 üretmez, dolayısıyla hız kademesi de sınırlamaz — tek çare ENABLE'ı
    hiç kesmemek. Bu test o kuralın geri alınmasını yakalar."""
    w = SahtePencere()
    w._aci_hareket(120.0, 30.0)
    w.kontrol.mock.pan, w.kontrol.mock.tilt = 120.0, 30.0   # motorlar hedefe vardı say

    w.kontrol.estop(True)
    assert w.kontrol.mock.surucu_enerjili is True, "E-Stop'ta ENABLE kesildi"
    w.kontrol.estop(False)
    assert w.kontrol.mock.surucu_enerjili is True


def test_estopta_iki_eksen_de_oldugu_yerde_donar():
    """ŞARTNAME Yetenek 3: "hareket ederken E-Stop → SİSTEM DURUR".

    Acil durdurmada sistemin ürettiği HİÇBİR hareket olmamalı. (Bir süre tilt'i 0° park
    konumuna indiriyorduk — lazerli namlu yukarıda kalmasın diye; o da bir HAREKETTİR ve
    videoda "durmadı" gibi değerlendirilebilirdi. Kaldırıldı.)

    Kart durduğu konumu bildirir; ekran ona çekilir. Motor hedefe VARMADAN durduysa
    (90'a giderken 45'te E-Stop) laptop'un hedefi gerçekten ayrışır — bildirilmezse
    ekrandaki açı gerçek konumu göstermezdi."""
    w = SahtePencere()
    w._aci_hareket(120.0, 90.0)                      # hedef: pan 120, tilt 90
    # Motor hedefe VARMADAN durduruluyor: gerçek konum 45'te.
    w.kontrol.mock.pan, w.kontrol.mock.tilt = 120.0, 45.0

    w.kontrol.estop(True)
    w._estop_konum_uygula()                          # arayüz tarafı (_estop_bas yolu)

    # Kart: iki eksenin de hedefi konumuna çekildi
    assert w.kontrol.mock.pan_hedef == 120.0
    assert w.kontrol.mock.tilt_hedef == 45.0, "tilt olduğu yerde donmadı"
    # Ekran: kartın bildirdiği GERÇEK konumu gösterir (90 değil, 45)
    assert w.pan_aci == 120.0 and w.pan_ham == 120.0
    assert w.tilt_aci == 45.0, (w.tilt_aci, "ekran gerçek konuma çekilmedi")
    assert w.kontrol.pan_hedef == 120.0 and w.kontrol.tilt_hedef == 45.0

    # Zamanı ilerlet: HİÇBİR eksen hareket etmemeli.
    for _ in range(20):
        w.kontrol.mock._son_t -= 0.25
        w.kontrol.mock.islet("")
    assert w.kontrol.mock.pan == 120.0, "acil durdurmada pan hareket etti"
    assert w.kontrol.mock.tilt == 45.0, "acil durdurmada tilt hareket etti"


def test_devam_edince_referans_korunur():
    """DEVAM'da konum SIFIRLANMAMALI — motorlar tuttuğu için referans geçerli kaldı.

    Sıfır kabulü, ENABLE'ın kesildiği eski tasarımın zorunlu telafisiydi (serbest kalan
    mil kayıyordu). ENABLE artık hiç kesilmediğine göre sıfırlamak, her acil durdurmada
    mutlak açıları kaydırmak demek olurdu."""
    w = SahtePencere()
    w._aci_hareket(120.0, 30.0)
    w.kontrol.mock.pan, w.kontrol.mock.tilt = 120.0, 30.0
    w.kontrol.estop(True)
    w._estop_konum_uygula()

    w.kontrol.estop(False)
    assert (w.pan_aci, w.tilt_aci) == (120.0, 30.0), "DEVAM'da ekran açısı sıfırlandı"
    assert w.pan_ham == 120.0
    assert (w.kontrol.mock.pan, w.kontrol.mock.tilt) == (120.0, 30.0), \
        "DEVAM'da kartın referansı sıfırlandı"
    assert w.kontrol.pan_hedef == 120.0 and w.kontrol.tilt_hedef == 30.0

    # Durulan noktadan hareket normal sürer (referans kaymadığı için sıçrama yok).
    w._aci_hareket(0.0, 10.0)
    assert w.tilt_aci == 40.0 and w.kontrol.mock.tilt_hedef == 40.0
    w._aci_hareket(0.0, -10.0)
    assert w.tilt_aci == 30.0 and w.kontrol.mock.tilt_hedef == 30.0


def test_basili_tutma_motor_hizini_asmaz():
    """Tuşu basılı tutunca hareket SÜRER, ama hedef motorun önüne GEÇMEZ.

    Tik başına açı = seçili kademenin derece/sn'si × geçen süre. Sabit adım (örn. her
    50 ms'de 5° = 100°/s) gönderilseydi hedef motordan hızlı ilerler, tuş bırakıldığında
    gimbal hedefe yetişmek için dönmeye devam ederdi — kullanıcı "durmuyor" derdi."""
    w = SahtePencere()
    w._hiz_sec(P.H_NORMAL)                       # 40°/s
    w._basili_yonler.add("right")
    w._son_tekrar_t = time.time() - 0.5          # 0.5 sn geçmiş say
    w._tekrar_tik()
    # 0.5 sn x 40°/s = 20° (dt tavanı 0.2 sn -> en fazla 8°)
    assert 7.0 < w.pan_aci <= 8.1, w.pan_aci
    assert w.kontrol.mock.pan_hedef == w.pan_ham

    # Çapraz: iki yön birden basılıysa ikisi de uygulanır
    w._basili_yonler.add("up")
    w._son_tekrar_t = time.time() - 0.1
    once_pan, once_tilt = w.pan_aci, w.tilt_aci
    w._tekrar_tik()
    assert w.pan_aci > once_pan and w.tilt_aci > once_tilt, (w.pan_aci, w.tilt_aci)

    # Yavaş kademede aynı sürede daha az yol
    w2 = SahtePencere()
    w2._hiz_sec(P.H_YAVAS)                       # 15°/s
    w2._basili_yonler.add("right")
    w2._son_tekrar_t = time.time() - 0.1
    w2._tekrar_tik()
    assert 0 < w2.pan_aci < w.pan_aci, (w2.pan_aci, w.pan_aci)


def test_l_kisayolu_ates_kapisindan_gecer():
    """[L] tuşu ATEŞ butonuyla BİREBİR aynı davranmalı — kendi yolunu açmamalı.

    Kısayolun butondan fazla yetkisi olamaz: E-Stop'ta buton kilitliyse [L] de
    geçmemeli, yoksa şartnamenin E-Stop'u klavyeden aşılabilir olurdu (Yetenek 4)."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None)

    w._ates_kisayolu()                      # aç
    assert w.fire_btn.isChecked() and w.kontrol.mock.lazer is True
    w._ates_kisayolu()                      # kapat
    assert not w.fire_btn.isChecked() and w.kontrol.mock.lazer is False

    # E-Stop: buton kilitlenir → kısayol da geçmez
    w.thread.estop = True
    w.fire_btn.setEnabled(False)
    w._ates_kisayolu()
    assert w.kontrol.mock.lazer is False, "E-Stop'ta [L] ile ateş açıldı"
    assert not w.fire_btn.isChecked()

    # Atışa yasak bölgede de reddedilmeli (ateşin tek kapısı ortak)
    w.thread.estop = False
    w.fire_btn.setEnabled(True)
    w.atis_yasak_aktif = True
    w.atis_pan_min, w.atis_pan_max = 0.0, 30.0      # pan 0 → yasak
    w._ates_kisayolu()
    assert w.kontrol.mock.lazer is False, "yasak bölgede [L] ile ateş açıldı"


def test_gamepad_ayni_kapilardan_gecer():
    """Gamepad KENDI komut yolunu açmamalı — klavye/D-pad ile aynı kapılardan geçmeli.

    Geçmişte ikinci bir ateş yolu açılmış ve E-Stop denetimini atlamıştı (CLAUDE.md §12
    B1). Gamepad üçüncü giriş; hareket `_aci_hareket`, ateş `_ates_bas`, merkez
    `_aci_reset` üzerinden gitmezse aynı sınıf hata geri gelir."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None)

    # --- HAREKET: analog çubuk motor hızını AŞMAMALI (basılı tutmayla aynı matematik)
    w._hiz_sec(P.H_NORMAL)                       # 40°/s
    w.gamepad = SahteGamepad(pan=1.0)            # çubuk sonuna kadar sağda
    w._gp_son_t = time.time() - 0.1              # 0.1 sn geçmiş say
    w._gamepad_tik()
    assert 0 < w.pan_aci <= 4.1, w.pan_aci       # 0.1 sn x 40°/s = 4°
    # Protokol aciyi 2 ondaliga yuvarlar ("P4.00"), o yuzden tam esitlik degil tolerans:
    # sapma 0.005°'yi (yarim step) gecmez ve BIRIKMEZ — her komut mutlak aci tasir.
    assert abs(w.kontrol.mock.pan_hedef - w.pan_ham) < 0.01, "ekran ile kart hedefi koptu"

    # Yarım sapma yarım hız (analog çarpan çalışıyor mu)
    once = w.pan_aci
    w.gamepad = SahteGamepad(pan=0.5)
    w._gp_son_t = time.time() - 0.1
    w._gamepad_tik()
    assert 0 < (w.pan_aci - once) <= 2.1, w.pan_aci - once

    # --- E-STOP'ta hareket geçmemeli
    w.thread.estop = True
    duran = w.pan_aci
    w.gamepad = SahteGamepad(pan=1.0)
    w._gp_son_t = time.time() - 0.1
    w._gamepad_tik()
    assert w.pan_aci == duran, "E-Stop'ta gamepad ile hareket edildi"

    # --- E-STOP'ta ateş geçmemeli (buton kilitliyse gamepad de geçmez)
    w.fire_btn.setEnabled(False)
    w.gamepad = SahteGamepad(ates=True)
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "E-Stop'ta gamepad ile ateş açıldı"

    # --- Ateş normal koşulda çalışmalı
    w.thread.estop = False
    w.fire_btn.setEnabled(True)
    w.gamepad = SahteGamepad(ates=True)
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is True, "gamepad ateş açmadı"
    w.gamepad = SahteGamepad(ates=True)
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "gamepad ateşi kesmedi"

    # --- Atışa yasak bölgede ateş reddedilmeli (ortak kapı)
    w.atis_yasak_aktif = True
    w.atis_pan_min, w.atis_pan_max = 0.0, 360.0
    w.gamepad = SahteGamepad(ates=True)
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "yasak bölgede gamepad ile ateş açıldı"
    w.atis_yasak_aktif = False

    # --- Hız kademesi
    w._hiz_sec(P.H_YAVAS)
    w.gamepad = SahteGamepad(hiz_yukari=True)
    w._gamepad_tik()
    assert w.hiz_seviye == P.H_NORMAL, w.hiz_seviye
    w.gamepad = SahteGamepad(hiz_asagi=True)
    w._gamepad_tik()
    assert w.hiz_seviye == P.H_YAVAS
    w.gamepad = SahteGamepad(hiz_asagi=True)     # en alt kademede daha aşağı inmemeli
    w._gamepad_tik()
    assert w.hiz_seviye == P.H_YAVAS

    # --- Cihaz koparsa arayüz kilitlenmemeli (istisna sızmamalı)
    w.gamepad = SahteGamepad(kopuk=True)
    w._gamepad_tik()                             # patlamamalı


def test_lazer_gucu_arayuzden_karta_gider():
    """LAZER kartındaki güç seçimi karta `G<yüzde>` olarak gitmeli ve ATEŞİ KESMEMELİ.

    "Ne kadar" (G) ile "ne zaman" (L) ayrı komutlardır: ateş sürerken güç değiştirmek
    lazeri söndürmemeli, kart yeni duty'yi anında uygulamalı."""
    w = SahtePencere()
    assert w.lazer_guc == w.kontrol.mock.lazer_guc == P.LAZER_GUC_VARSAYILAN

    w._lazer_guc_degisti(70)
    assert w.lazer_guc == 70 and w.kontrol.mock.lazer_guc == 70
    assert w.lazer_sl.value() == 70, "kaydırıcı kademe butonunu izlemedi"
    assert w.kontrol.mock.kayit[-1] == "G70", w.kontrol.mock.kayit[-1]

    # Aynı değer tekrar seçilirse hatta boş komut dolaşmamalı.
    n = len(w.kontrol.mock.kayit)
    w._lazer_guc_degisti(70)
    assert len(w.kontrol.mock.kayit) == n, w.kontrol.mock.kayit[n:]

    # Sınır dışı değer kırpılır (kart da kırpar; tek tarafa güvenilmez).
    w._lazer_guc_degisti(500)
    assert w.lazer_guc == P.LAZER_GUC_MAX == w.kontrol.mock.lazer_guc

    # ATEŞ SÜRERKEN güç değişimi ateşi kesmemeli.
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    w._lazer_guc_degisti(40)
    assert w.kontrol.mock.lazer is True, "güç değişimi ateşi kesti"
    assert w.kontrol.mock.lazer_guc == 40


def test_ates_tazelemesi_kesilirse_lazer_soner():
    """OLU ADAM ANAHTARI: arayuz tazelemeyi kesince kart lazeri KENDI kesmeli.

    Lazer cok gucludur; "kes" komutunun gitmesine bel baglanamaz, cunku kesmenin
    gerektigi durumlarin cogunda (kablo koptu, laptop coktu, arayuz dondu) komut
    zaten gidemiyordur. Bu yuzden kart "hala aciksin" duymayi surdurmezse keser."""
    w = SahtePencere()
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    assert w.kontrol.mock.lazer is True

    n = len(w.kontrol.mock.kayit)
    w._esp_yokla()                                # normal dongu -> tazeler
    assert "L1" in w.kontrol.mock.kayit[n:], "arayuz yoklamasi atesi TAZELEMEDI"
    assert w.kontrol.mock.lazer is True, "tazelemeye ragmen lazer sondu"

    # Arayuz dondu / kablo koptu: tazeleme gelmiyor, kartin zaman asimi doluyor.
    w.kontrol.mock.son_ates_t -= P.ATES_ZAMAN_ASIMI_MS / 1000.0 + 0.1
    w.kontrol.mock.islet("")                      # kartin kendi dongusu
    assert w.kontrol.mock.lazer is False, "tazeleme kesildi ama lazer yanik kaldi"


def test_ates_kapaliyken_tazeleme_gitmez():
    """Ates KAPALIYKEN tazeleme komutu gonderilmemeli — hatta bos yere L1 dolasmasin
    (ve 250 ms'de bir gonderilen bir L1, kapali lazeri kazara ACMASIN)."""
    w = SahtePencere()
    assert w.fire_btn.isChecked() is False
    n = len(w.kontrol.mock.kayit)
    for _ in range(3):
        w._esp_yokla()
    assert len(w.kontrol.mock.kayit) == n, w.kontrol.mock.kayit[n:]
    assert w.kontrol.mock.lazer is False

    # E-Stop'ta ates butonu kilitli kalsa bile tazeleme GITMEMELI.
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    w.kontrol.estop(True)
    n = len(w.kontrol.mock.kayit)
    w._esp_yokla()
    assert "L1" not in w.kontrol.mock.kayit[n:], "E-Stop'ta ates tazelemesi gonderildi"


def test_basili_tutma_estopta_kesilir():
    """E-Stop sırasında tuş basılı kalsa bile tekrar durmalı (Yetenek 3)."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None)
    w._basili_yonler.add("right")
    w._son_tekrar_t = time.time() - 0.1
    w._tekrar_timer.start()

    w.thread.estop = True
    w._tekrar_tik()
    assert w.pan_aci == 0.0, "E-Stop'ta hareket etti"
    assert w._tekrar_timer.isActive() is False, "E-Stop'ta tekrar timer'ı durmadı"
    assert not w._basili_yonler


if __name__ == "__main__":
    test_ekran_aci_kart_hedefi_ayni()
    test_azimut_sarmasiz_gider()
    test_ates_sirasinda_yasak_alan()
    test_harekete_yasak_alan()
    test_estop_hareketi_keser()
    test_hiz_duzeyi_karta_gider()
    test_kart_disaridan_durdurulursa_ates_birakilir()
    test_donanim_butonu_yazilimdan_kaldirilamaz()
    test_kart_reseti_yakalanir()
    test_estopta_enable_kesilmez()
    test_estopta_iki_eksen_de_oldugu_yerde_donar()
    test_devam_edince_referans_korunur()
    test_basili_tutma_motor_hizini_asmaz()
    test_l_kisayolu_ates_kapisindan_gecer()
    test_gamepad_ayni_kapilardan_gecer()
    test_lazer_gucu_arayuzden_karta_gider()
    test_ates_tazelemesi_kesilirse_lazer_soner()
    test_ates_kapaliyken_tazeleme_gitmez()
    test_basili_tutma_estopta_kesilir()
    print("kapi testleri OK — ekran/kart hedefi, sarmasiz azimut, ates sirasinda yasak "
          "alan, harekete yasak alan, E-Stop, hiz duzeyi, kart disaridan durdurma, "
          "donanim acil stop butonu, ENABLE kesilmez, iki eksen donar, referans korunur, basili tutma, "
          "[L] kisayolu, gamepad, lazer gucu, ates olu adam anahtari")
