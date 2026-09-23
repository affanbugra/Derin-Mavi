# -*- coding: utf-8 -*-
"""ARAYUZ GUVENLIK KAPILARI — pencere ACMADAN kosar (kamera/motor gerekmez).

`kapi_testleri.py` birlesik arayuzu gercek bir pencereyle dener; bu dosya ise
E-Stop / ates / yasak alan / merkeze alma kapilarini sahte bir pencere uzerinde
dener. Ikisi birbirinin yerine gecmez: burasi mantigi, oradaki pencereyi korur.

Calistir:  python app/kapi_testleri_arayuz.py
DERIN MAVI — GUVENLIK KAPILARI regresyon testi (donanim ve pencere GEREKTIRMEZ).

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
import bolge as B


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

    def __init__(self, pan=0.0, tilt=0.0, basili=(), kenar=None, kopuk=False):
        self.ad = "Sahte Pad"
        self._kopuk = kopuk
        self.bagli = not kopuk
        self._d = gamepad_mod.Durum()
        self._d.pan, self._d.tilt = pan, tilt
        self._d.basili = set(basili)
        # kenar verilmezse "yeni basildi" sayilir (tek yoklamalik testler icin)
        self._d.kenar = set(basili if kenar is None else kenar)

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


class SahteKol:
    """Kol gostergesinin test yuzu: yanan tuslari tutar (cizim yapmaz)."""

    def __init__(self):
        self.yanan = set()

    def isiklari_ayarla(self, adlar):
        self.yanan = set(adlar)


class SahtePencere:
    """MainWindow'un hareket/ates/hiz kapilari icin ihtiyac duydugu asgari yuzey."""
    _aci_hareket = A.MainWindow._aci_hareket
    _hareket_kilitli = A.MainWindow._hareket_kilitli   # E-Stop kilidi: TEK tanim
    _aci_reset = A.MainWindow._aci_reset               # [R] / MERKEZ — kademeli merkeze al
    _merkez_tik = A.MainWindow._merkez_tik
    _merkez_durdur = A.MainWindow._merkez_durdur
    _merkez_kurma_baslat = A.MainWindow._merkez_kurma_baslat
    _merkez_kurma_iptal = A.MainWindow._merkez_kurma_iptal
    _merkez_kurma_bitti = A.MainWindow._merkez_kurma_bitti
    MERKEZ_KURMA_MS = A.MainWindow.MERKEZ_KURMA_MS
    TEKRAR_PERIYOT_MS = A.MainWindow.TEKRAR_PERIYOT_MS
    _acilis_hizala = A.MainWindow._acilis_hizala          # birlesik surumde eklendi
    _acilis_yukselisini_dene = A.MainWindow._acilis_yukselisini_dene
    tilt_taban_deg = A.MainWindow.tilt_taban_deg
    _dpad_press = A.MainWindow._dpad_press
    _dpad_release = A.MainWindow._dpad_release
    TEKRAR_GECIKME_MS = A.MainWindow.TEKRAR_GECIKME_MS
    _ates_bas = A.MainWindow._ates_bas
    _ates_kes = A.MainWindow._ates_kes
    _ates_kisayolu = A.MainWindow._ates_kisayolu
    _ates_tusu = A.MainWindow._ates_tusu
    _ates_kurma_bitti = A.MainWindow._ates_kurma_bitti
    _ates_kurma_iptal = A.MainWindow._ates_kurma_iptal
    _ates_kurma_baslat = A.MainWindow._ates_kurma_baslat
    _ates_kurma_gecerli = A.MainWindow._ates_kurma_gecerli
    _ates_isigi = A.MainWindow._ates_isigi
    _kol_isik = A.MainWindow._kol_isik
    _kol_parla = A.MainWindow._kol_parla
    _kol_gamepad_isik = A.MainWindow._kol_gamepad_isik
    _kol_yenile = A.MainWindow._kol_yenile
    _tus_bas = A.MainWindow._tus_bas
    _tus_birak = A.MainWindow._tus_birak
    _tus_yonu = A.MainWindow._tus_yonu
    ATES_TUSLARI = A.MainWindow.ATES_TUSLARI
    ATES_KURMA_MS = A.MainWindow.ATES_KURMA_MS
    atis_yasak_mi = A.MainWindow.atis_yasak_mi
    _gamepad_tik = A.MainWindow._gamepad_tik
    _gamepad_durum_yaz = A.MainWindow._gamepad_durum_yaz
    GP_TARAMA_TIK = A.MainWindow.GP_TARAMA_TIK
    _esp_goster = A.MainWindow._esp_goster      # gercegi: lazer + donanimsal E-Stop yansimasi
    _esp_yokla = A.MainWindow._esp_yokla
    _estop_konum_uygula = A.MainWindow._estop_konum_uygula
    _tilt_goster = A.MainWindow._tilt_goster       # yukselis etiketi + arac ikonu tek kapi
    _pan_goster = A.MainWindow._pan_goster         # azimut etiketi + ust gorunus ikonu tek kapi
    _tekrar_tik = A.MainWindow._tekrar_tik
    _tekrar_durdur = A.MainWindow._tekrar_durdur
    YON_TABLO = A.MainWindow.YON_TABLO
    _lazer_bilgi_yaz = A.MainWindow._lazer_bilgi_yaz
    _lazer_guc_degisti = A.MainWindow._lazer_guc_degisti
    _lazer_taslak_ayarla = A.MainWindow._lazer_taslak_ayarla

    def _ci(self, ad, renk, alt):               # alt cubuk segmenti — testte gorsel yok
        pass

    def __init__(self):
        self.mod = "Manuel"
        self.thread = None                # isinstance(VideoThread) -> False
        self.pan_aci = 0.0                # ekran (0-360 sarmali)
        self.pan_ham = 0.0                # karta giden sarmasiz azimut
        self.tilt_aci = 0.0
        # gercek pencerenin ayni satiri (arayuz_qt): operator calisma tavani
        self.max_tilt_limit = 30.0 if P.TILT_MAX >= 30 else float(P.TILT_MAX)
        self.bolge = B.Bolgeler()          # hareket/atis pencereleri (hepsi kapali)
        self.pan_val_lbl = SahteEtiket()
        self.tilt_val_lbl = SahteEtiket()
        self.bolge_status = SahteEtiket()
        self.sb_msg = SahteEtiket()
        self.fire_btn = SahteButon()
        self.hiz_seviye = P.HIZ_VARSAYILAN
        self.lazer_guc = P.LAZER_GUC_VARSAYILAN
        self.lazer_durum = SahteEtiket()
        self.lazer_sl = SahteKaydirici(P.LAZER_GUC_VARSAYILAN)
        self.lazer_btns = {g: SahteButon() for g in (20, 40, 70, 100)}
        self._basili_yonler = set()          # tusa basili tutma (surekli hareket)
        self._son_tekrar_t = 0.0
        self._tekrar_gecikme = SahteTimer()
        self._tekrar_timer = SahteTimer()
        self._ates_tuslari = set()
        self._ates_kurma = SahteTimer()
        self._ates_kurma_kaynak = None
        self._gp_ates_basili = False
        self._merkez_calisiyor = False
        self._merkez_son_t = time.time()
        self._merkez_timer = SahteTimer()
        self._merkez_kurma = SahteTimer()
        self._kol_ui, self._kol_gp = set(), set()
        self.kol_ikon = SahteKol()
        self.aci_adim = 1.0
        self._key_normal_style = self._key_active_style = ""
        for ad, _, _ in A.MainWindow.YON_TABLO.values():
            setattr(self, ad, SahteButon())
        self.gamepad = SahteGamepad()
        self._gp_son_t = time.time()
        self._gp_tarama = 0
        self.kontrol = kontrol_mod.Kontrol("mock")
        self._acilis_yukselisi = True          # acilis yukselisi testlerde kapali
        self._acilis_yukselisi_bekliyor = False


def test_ekran_aci_kart_hedefi_ayni():
    """Ekrandaki aci ile kartin hedefi HER durumda ayni olmali (ozellikle limitte).

    Karta MUTLAK aci gider; ekran ve komut ayni kaynaktan turer, dolayisiyla kopma
    yapisal olarak imkansizdir. Test bunun korundugunu dogrular."""
    w = SahtePencere()
    for _ in range(12):                       # limitin otesine zorla
        w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == B.TILT_CALISMA_MAX == 25.0, w.tilt_aci
    assert w.kontrol.mock.tilt_hedef == B.TILT_CALISMA_MAX, w.kontrol.mock.tilt_hedef

    # Limitte fazladan komut: gonderilecek yeni bir aci yok, bos komut da atilmamali.
    komut = len(w.kontrol.mock.kayit)
    w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == B.TILT_CALISMA_MAX
    assert len(w.kontrol.mock.kayit) == komut, w.kontrol.mock.kayit[-1]

    w._aci_hareket(0.0, -5.0)                 # asagi normal calisir
    assert w.tilt_aci == 20.0 and w.kontrol.mock.tilt_hedef == 20.0

    # Kismi kirpma: 20°'de +8 istenir, ancak +5 uygulanabilir -> ikisi de 25 olmali.
    w._aci_hareket(0.0, 8.0)
    assert w.tilt_aci == 25.0, w.tilt_aci
    assert w.kontrol.mock.tilt_hedef == 25.0, w.kontrol.mock.tilt_hedef


def test_azimut_sarmasiz_gider():
    """Ekranda azimut 0-360 sarmalidir ama karta SUREKLI (isaretli) aci gitmeli.

    Sola 30° donulunce ekran 330 yazar, kart −30 hedefi alir. Kart da 330 alsaydi
    motor kisa yoldan degil 330° geri donerdi (AccelStepper mutlak konuma gider)."""
    w = SahtePencere()
    w._aci_hareket(-30.0, 0.0)
    assert w.pan_aci == 330.0, w.pan_aci                      # EKRAN sarmali
    assert w.kontrol.mock.pan_hedef == -30.0, w.kontrol.mock.pan_hedef   # KART isaretli
    w._aci_hareket(60.0, 0.0)
    assert w.pan_aci == 30.0 and w.kontrol.mock.pan_hedef == 30.0


def test_yatay_on_yariyi_gecemez():
    """[KESİN] Namlu ÖN YARIDAN çıkamaz: ±90°. Operatör aracın arkasında durur,
    namlu onun eksenine asla giremez (şartname §4.2). Bu bir operatör tercihi
    DEĞİL yapısal sınırdır — hareket penceresi KAPALI olsa da uygulanır ve
    pencere onu yalnızca DARALTABİLİR."""
    w = SahtePencere()
    # Varsayilan: pencere ACIK ve yapisal sinirla ayni (kullanici daraltabilir)
    assert w.bolge.hareket_pan.aktif, "hareket penceresi acilista etkin gelmeli"
    assert (w.bolge.hareket_pan.alt, w.bolge.hareket_pan.ust) == (-B.PAN_MAX, B.PAN_MAX)

    w._aci_hareket(120.0, 0.0)                 # 120° istendi
    assert w.pan_ham == B.PAN_MAX and w.kontrol.mock.pan_hedef == B.PAN_MAX, w.pan_ham
    w._aci_hareket(30.0, 0.0)                  # sinirda: daha ileri YOK
    assert w.pan_ham == B.PAN_MAX
    w._aci_hareket(-200.0, 0.0)                # diger uca: yine sinirda durur
    assert w.pan_ham == -B.PAN_MAX and w.kontrol.mock.pan_hedef == -B.PAN_MAX, w.pan_ham
    assert w.pan_aci == 360.0 - B.PAN_MAX, w.pan_aci     # ekranda 300 (=-60)

    # PENCERE KAPALIYKEN DE yapisal sinir gecerli (operator tercihi degil)
    w2 = SahtePencere()
    w2.bolge.hareket_pan = B.Pencere(False, -B.PAN_MAX, B.PAN_MAX)
    w2._aci_hareket(200.0, 0.0)
    assert w2.pan_ham == B.PAN_MAX, w2.pan_ham

    # Pencere yalniz DARALTIR: ±45 verilince ±45'te durulur
    w.bolge.hareket_pan = B.Pencere(True, -45.0, 45.0)
    w._aci_hareket(200.0, 0.0)
    assert w.pan_ham == 45.0, w.pan_ham


def test_ates_sirasinda_yasak_alan():
    """Lazer acikken atisa-yasak bolgeye GIRILIRSE ates kesilmeli.

    `_ates_bas` yalnizca butona basildigi ani denetler; bolgeye ates surerken
    girmek de engellenmeli (sartname: atisa-yasak alan)."""
    w = SahtePencere()
    w.bolge.atis_pan = B.Pencere(True, -40.0, 40.0)    # atis yalniz on ±40°
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    assert w.kontrol.durum["lazer"] is True

    w._aci_hareket(30.0, 0.0)                 # pencere icinde -> ates surer
    assert w.kontrol.durum["lazer"] is True, "guvenli bolgede ates kesilmemeliydi"

    w._aci_hareket(15.0, 0.0)                 # pan 45 -> pencere DISI (yasak)
    assert w.fire_btn.isChecked() is False, "ates butonu acik kaldi"
    assert w.kontrol.durum["lazer"] is False, "yasak bolgede lazer sonmedi"


def test_harekete_yasak_alan():
    """Hareket penceresinin DISINA cikilamaz: komut sinirda KIRPILIR, kart hedefi
    de ayni sinirda kalir (sartname §4.2 — yasak bolgeye donmesine izin verilmez)."""
    w = SahtePencere()
    w.bolge.hareket_pan = B.Pencere(True, -45.0, 45.0)     # yapisal ±60'i DARALTIR
    assert w._aci_hareket(40.0, 0.0) is True and w.pan_aci == 40.0
    w._aci_hareket(20.0, 0.0)                              # 60'a gitmek isterdi
    assert w.pan_ham == 45.0 and w.kontrol.pan_hedef == 45.0, (w.pan_ham, w.kontrol.pan_hedef)
    # sinirda: daha ileri gitmek ENGELLENIR, geri donmek serbest
    assert w._aci_hareket(5.0, 0.0) is False and w.pan_ham == 45.0
    assert w._aci_hareket(-10.0, 0.0) is True and w.pan_ham == 35.0


def test_estop_hareketi_keser():
    """E-Stop aktifken hicbir hareket komutu gecmez ve ekrandaki aci DEGISMEZ
    (CLAUDE.md §12 B2 — sartname Yetenek 3)."""
    w = SahtePencere()
    # Kamera thread'i CALISTIRILMAZ; yalnizca `_aci_hareket`in baktigi tip + estop
    # alani gerekiyor (isinstance kontrolu bilincli: bkz. _aci_hareket B2 notu).
    w.thread = A.VideoThread(None, None, None)
    w.thread.estop = True
    assert w._aci_hareket(0.0, 5.0) is False
    assert w.tilt_aci == 0.0 and w.kontrol.mock.tilt_hedef == 0.0

    w.thread.estop = False                    # DEVAM -> hareket yeniden serbest
    assert w._aci_hareket(0.0, 5.0) is True
    assert w.tilt_aci == 5.0 and w.kontrol.mock.tilt_hedef == 5.0


def test_sabit_hiz_duzeyi_karta_gider():
    """Motor hizi arayuzde SECILMEZ (22.09); karta sabit kademe S (tavan hiz) + A
    (ivme) olarak gider. Basili tutma / gamepad / otonom hiz siniri da buna dayanir."""
    w = SahtePencere()
    assert w.hiz_seviye == P.HIZ_VARSAYILAN
    assert (w.kontrol.mock.max_hiz, w.kontrol.mock.ivme) == P.HIZ_TABLO[P.HIZ_VARSAYILAN]


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
    (tavana giderken 15'te E-Stop) laptop'un hedefi gerçekten ayrışır — bildirilmezse
    ekrandaki açı gerçek konumu göstermezdi."""
    w = SahtePencere()
    w._aci_hareket(60.0, 90.0)                      # hedef: pan 60 (tavan), tilt tavan
    # Motor hedefe VARMADAN durduruluyor: gerçek konum 15'te.
    w.kontrol.mock.pan, w.kontrol.mock.tilt = 60.0, 15.0

    w.kontrol.estop(True)
    w._estop_konum_uygula()                          # arayüz tarafı (_estop_bas yolu)

    # Kart: iki eksenin de hedefi konumuna çekildi
    assert w.kontrol.mock.pan_hedef == 60.0
    assert abs(w.kontrol.mock.tilt_hedef - w.kontrol.mock.tilt) < 1e-6, "tilt olduğu yerde donmadı"
    # Ekran: kartın bildirdiği GERÇEK konumu gösterir (tavan değil, 15)
    assert w.pan_aci == 60.0 and w.pan_ham == 60.0
    assert w.tilt_aci == 15.0, (w.tilt_aci, "ekran gerçek konuma çekilmedi")
    assert w.kontrol.pan_hedef == 60.0 and w.kontrol.tilt_hedef == 15.0

    # Zamanı ilerlet: HİÇBİR eksen hareket etmemeli.
    for _ in range(20):
        w.kontrol.mock._son_t -= 0.25
        w.kontrol.mock.islet("")
    assert w.kontrol.mock.pan == 60.0, "acil durdurmada pan hareket etti"
    assert abs(w.kontrol.mock.tilt - 15.0) < 0.01, "acil durdurmada tilt hareket etti"


def test_devam_edince_referans_korunur():
    """DEVAM'da konum SIFIRLANMAMALI — motorlar tuttuğu için referans geçerli kaldı.

    Sıfır kabulü, ENABLE'ın kesildiği eski tasarımın zorunlu telafisiydi (serbest kalan
    mil kayıyordu). ENABLE artık hiç kesilmediğine göre sıfırlamak, her acil durdurmada
    mutlak açıları kaydırmak demek olurdu."""
    w = SahtePencere()
    w._aci_hareket(50.0, 20.0)
    w.kontrol.mock.pan, w.kontrol.mock.tilt = 50.0, 20.0
    w.kontrol.estop(True)
    w._estop_konum_uygula()

    w.kontrol.estop(False)
    assert (w.pan_aci, w.tilt_aci) == (50.0, 20.0), "DEVAM'da ekran açısı sıfırlandı"
    assert w.pan_ham == 50.0
    assert (w.kontrol.mock.pan, w.kontrol.mock.tilt) == (50.0, 20.0), \
        "DEVAM'da kartın referansı sıfırlandı"
    assert w.kontrol.pan_hedef == 50.0 and w.kontrol.tilt_hedef == 20.0

    # Durulan noktadan hareket normal sürer (referans kaymadığı için sıçrama yok).
    w._aci_hareket(0.0, 10.0)                 # 20 -> 25 (tavanda kirpilir)
    assert w.tilt_aci == 25.0 and w.kontrol.mock.tilt_hedef == 25.0
    w._aci_hareket(0.0, -10.0)
    assert w.tilt_aci == 15.0 and w.kontrol.mock.tilt_hedef == 15.0


def test_basili_tutma_motor_hizini_asmaz():
    """Tuşu basılı tutunca hareket SÜRER, ama hedef motorun önüne GEÇMEZ.

    Tik başına açı = seçili kademenin derece/sn'si × geçen süre. Sabit adım (örn. her
    50 ms'de 5° = 100°/s) gönderilseydi hedef motordan hızlı ilerler, tuş bırakıldığında
    gimbal hedefe yetişmek için dönmeye devam ederdi — kullanıcı "durmuyor" derdi."""
    w = SahtePencere()                           # sabit kademe: Normal, 40°/s
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


class SahteTus:
    """QKeyEvent'in kapilarin okudugu kadari."""

    def __init__(self, tus, tekrar=False):
        self._tus, self._tekrar = tus, tekrar

    def key(self):
        return self._tus

    def isAutoRepeat(self):
        return self._tekrar


def test_klavye_atesi_space_b_basili_tutma():
    """Klavyeden ateş: [Space]+[B] birlikte 2 sn basılı → aç; [Esc] → kes.

    Tek tuş, erken bırakma, E-Stop ve atışa yasak bölge ateşi AÇAMAZ. Klavyenin
    butondan fazla yetkisi olamaz — yoksa E-Stop klavyeden aşılabilirdi (Yetenek 4)."""
    Qt = A.Qt
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)

    def bas(*tuslar):
        for t in tuslar:
            w._tus_bas(SahteTus(t))

    def birak(*tuslar):
        for t in tuslar:
            w._tus_birak(SahteTus(t))

    # Tek tus kurma baslatmaz
    bas(Qt.Key_Space)
    assert not w._ates_kurma.isActive(), "yalniz Space ile kurma basladi"
    birak(Qt.Key_Space)

    # Iki tus: kurma baslar; sure dolmadan birakilirsa ates ACILMAZ
    bas(Qt.Key_Space, Qt.Key_B)
    assert w._ates_kurma.isActive()
    birak(Qt.Key_B)
    assert not w._ates_kurma.isActive()
    w._ates_kurma_bitti()                    # gec gelen zamanlayici da acamaz
    assert w.kontrol.mock.lazer is False, "erken birakilinca ates acildi"

    # Tam basili tutma: sure dolunca ates acilir
    bas(Qt.Key_Space, Qt.Key_B)
    w._ates_kurma_bitti()
    assert w.fire_btn.isChecked() and w.kontrol.mock.lazer is True
    birak(Qt.Key_Space, Qt.Key_B)
    assert w.kontrol.mock.lazer is True, "tus birakinca ates kendiliginden kesildi"

    # ESC keser
    bas(Qt.Key_Escape)
    assert not w.fire_btn.isChecked() and w.kontrol.mock.lazer is False

    # E-Stop: buton kilitli -> klavye de acamaz
    w.thread.estop = True
    w.fire_btn.setEnabled(False)
    bas(Qt.Key_Space, Qt.Key_B)
    w._ates_kurma_bitti()
    assert w.kontrol.mock.lazer is False, "E-Stop'ta Space+B ile ates acildi"
    birak(Qt.Key_Space, Qt.Key_B)

    # Atisa yasak bolge de reddedilir (ates kapisi ortak)
    w.thread.estop = False
    w.fire_btn.setEnabled(True)
    w.bolge.atis_pan = B.Pencere(True, 40.0, 60.0)   # pan 0 -> pencere DISI (yasak)
    bas(Qt.Key_Space, Qt.Key_B)
    w._ates_kurma_bitti()
    assert w.kontrol.mock.lazer is False, "yasak bolgede Space+B ile ates acildi"

    # [L] artik ates acmaz (tek tusla ates = 2 sn kuralini delerdi)
    w.bolge.atis_pan = B.Pencere(False, -180.0, 180.0)
    birak(Qt.Key_Space, Qt.Key_B)
    bas(Qt.Key_L)
    assert w.kontrol.mock.lazer is False, "[L] hala ates aciyor"


def test_aci_karosu_yasak_alan_dilimleri():
    """Açı karolarındaki renkli dilimler KAYITLI pencereleri doğru bölmeli:
    sarı = hareket penceresinin dışı, kırmızı = hareket içinde ama atış dışında,
    yeşil = atış penceresi. Hiçbir alan kapalıyken dilim çizilmez."""
    import types
    def dilimler(cls, h, a):
        o = types.SimpleNamespace(ARALIK=cls.ARALIK, hareket=h, atis=a)
        return cls.dilimler(o)
    yon = A.AracYonGostergesi
    assert dilimler(yon, (False, -90, 90), (False, -90, 90)) == []
    # Yatayda eksen YALNIZ on yaridir (±90): arka yari yapisal olarak erisilemez,
    # orayi boyamak "yasak alan" degil "olmayan alan" gosterirdi.
    assert yon.ARALIK == (-B.PAN_MAX, B.PAN_MAX) == (-60.0, 60.0)
    assert dilimler(yon, (True, -45, 45), (True, -30, 20)) == [
        ("hareket", -B.PAN_MAX, -45), ("hareket", 45, B.PAN_MAX),
        ("atis", -45, -30), ("atis", 20, 45), ("izin", -30, 20)]
    # yalniz atis acik: hareket penceresi tum eksen sayilir
    assert dilimler(yon, (False, 0, 0), (True, -45, 45)) == [
        ("atis", -B.PAN_MAX, -45), ("atis", 45, B.PAN_MAX), ("izin", -45, 45)]
    # dikey: yalniz CALISMA araligi (-25..+25) boyanir
    assert dilimler(A.AracAciGostergesi, (True, -20, 20), (False, 0, 0)) == [
        ("hareket", B.TILT_CALISMA_MIN, -20), ("hareket", 20, B.TILT_CALISMA_MAX)]


def test_kol_gostergesi_gercek_durumu_yansitir():
    """Ekrandaki oyun kolunda YANAN tuş, sistemin gerçekten aldığı komut olmalı.

    Gösterge yalnız kolu değil KLAVYE ve ekrandaki D-pad'i de yansıtır (üçü aynı
    kapılardan geçer). Yanlış yanan bir ışık operatöre "komut gitti" dedirtir —
    en yanıltıcı hata sınıfı bu (CLAUDE.md §5.1 'hedef mi ölçüm mü' notu)."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)

    # 1. Yon: basinca yanar, birakinca soner
    w._dpad_press("up")
    assert "up" in w.kol_ikon.yanan, w.kol_ikon.yanan
    w._dpad_release("up")
    assert "up" not in w.kol_ikon.yanan

    # 2. Ates kurma (Space+B ya da L2+R2) -> L2/R2 yanar; ates acilinca YANIK KALIR
    w._ates_kurma_baslat("klavye")
    assert {"l2", "r2"} <= w.kol_ikon.yanan, "kurma sirasinda tetikler yanmadi"
    w._gp_ates_basili = False
    w._ates_tuslari = set(w.ATES_TUSLARI)
    w._ates_kurma_bitti()
    assert w.fire_btn.isChecked() and {"l2", "r2"} <= w.kol_ikon.yanan
    w._ates_kes("test")
    assert not ({"l2", "r2"} & w.kol_ikon.yanan), "ates kesildi ama tetikler yanik kaldi"

    # 3. Gamepad'den gelen tuslar arayuzun yaktigi isigi SILMEZ (iki kaynak ayri)
    w._dpad_press("left")
    w._kol_gamepad_isik({"r1"})
    assert {"left", "r1"} <= w.kol_ikon.yanan, w.kol_ikon.yanan
    w._kol_gamepad_isik(set())
    assert "left" in w.kol_ikon.yanan, "gamepad yoklamasi klavyenin isigini sondurdu"
    w._dpad_release("left")


def test_gamepad_ayni_kapilardan_gecer():
    """Gamepad KENDI komut yolunu açmamalı — klavye/D-pad ile aynı kapılardan geçmeli.

    Geçmişte ikinci bir ateş yolu açılmış ve E-Stop denetimini atlamıştı (CLAUDE.md §12
    B1). Gamepad üçüncü giriş; hareket `_aci_hareket`, ateş `_ates_bas`, merkez
    `_aci_reset` üzerinden gitmezse aynı sınıf hata geri gelir."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)

    # --- HAREKET: analog çubuk motor hızını AŞMAMALI (basılı tutmayla aynı matematik)
    w.gamepad = SahteGamepad(pan=1.0)            # sabit kademe: 40°/s            # çubuk sonuna kadar sağda
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

    # --- ATES: L2 + R2 birlikte, 2 sn basili (tek tetik ya da tek dokunus ACMAZ)
    w.thread.estop = False
    w.gamepad = SahteGamepad(basili=("l2",))           # tek tetik
    w._gamepad_tik()
    assert not w._ates_kurma.isActive(), "tek tetik ateşi kurmaya başladı"

    w.fire_btn.setEnabled(False)                       # E-Stop benzeri kilit
    w.thread.estop = True
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    w._ates_kurma_bitti()
    assert w.kontrol.mock.lazer is False, "E-Stop'ta gamepad ile ateş açıldı"

    w.thread.estop = False
    w.fire_btn.setEnabled(True)
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    assert w._ates_kurma.isActive(), "iki tetik ateşi kurmadı"
    w._gp_ates_basili = False                          # tetikler erken birakildi
    w._ates_kurma_bitti()
    assert w.kontrol.mock.lazer is False, "erken bırakılan tetikle ateş açıldı"

    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    w._ates_kurma_bitti()                              # 2 sn doldu, tetikler basili
    assert w.kontrol.mock.lazer is True, "gamepad ateş açmadı"

    # Ates ACIKKEN tek dokunus keser (beklemeye zorlanmaz)
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "gamepad ateşi kesmedi"

    # --- Atışa yasak bölgede ateş reddedilmeli (ortak kapı)
    w.bolge.atis_pan = B.Pencere(True, 100.0, 110.0)  # pan 0 -> pencere DISI
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    w._ates_kurma_bitti()
    assert w.kontrol.mock.lazer is False, "yasak bölgede gamepad ile ateş açıldı"
    w.bolge.atis_pan.aktif = False

    # --- MERKEZ: L1/R1 **2 sn basili** (tek dokunus gimbal'i bastan almamali)
    w._aci_hareket(5.0, 5.0)
    w.gamepad = SahteGamepad(basili=("r1",))
    w._gamepad_tik()
    assert w._merkez_kurma.isActive(), "R1 merkez sayacını başlatmadı"
    assert (w.pan_aci, w.tilt_aci) != (0.0, 0.0), "tek dokunuşta merkeze alındı"
    w.gamepad = SahteGamepad(basili=())            # erken birakildi
    w._gamepad_tik()
    assert not w._merkez_kurma.isActive(), "tetik bırakılınca sayaç durmadı"

    w.gamepad = SahteGamepad(basili=("l1",))
    w._gamepad_tik()
    w._merkez_kurma_bitti()                        # 2 sn doldu
    _merkeze_yurut(w)
    assert abs(w.pan_aci) < 0.1 and abs(w.tilt_aci) < 0.1, "L1 merkeze almadı"

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
    w.thread = A.VideoThread(None, None, None)
    w._basili_yonler.add("right")
    w._son_tekrar_t = time.time() - 0.1
    w._tekrar_timer.start()

    w.thread.estop = True
    w._tekrar_tik()
    assert w.pan_aci == 0.0, "E-Stop'ta hareket etti"
    assert w._tekrar_timer.isActive() is False, "E-Stop'ta tekrar timer'ı durmadı"
    assert not w._basili_yonler


def _merkeze_yurut(w, tik=200):
    """Kademeli merkeze almayi tamamlanana kadar yurutur (gercek zamanlayici yok)."""
    for _ in range(tik):
        if not w._merkez_timer.isActive():
            return
        w._merkez_son_t -= 0.05                 # 50 ms gecmis say
        w._merkez_tik()
    raise AssertionError("merkeze alma bitmedi")


def test_merkeze_alma_kademeli_ve_kesilebilir():
    """Merkeze alma ANINDA DEGIL, motor hiziyla adim adim olmali.

    Eski surum acilari bir anda 0 yapiyordu; gercek motor o mesafeyi aninda
    alamaz, ekran sifira ziplarken gimbal yolda kalirdi (ekran-kart kopmasi).
    Ayrica operator yon verirse ya da E-Stop gelirse donus BIRAKILMALI."""
    w = SahtePencere()
    w._aci_hareket(60.0, 40.0)
    assert w._aci_reset() is True and w._merkez_timer.isActive()

    # Tek tikta hepsi gelmemeli: adim = tavan hiz x gecen sure
    w._merkez_son_t -= 0.05
    w._merkez_tik()
    adim = P.HIZ_TABLO[P.HIZ_VARSAYILAN][0] * 0.05
    assert abs(60.0 - w.pan_ham) <= adim + 0.01, (w.pan_ham, adim)
    assert w.pan_ham > 0.0, "tek tikta merkeze zipladi"
    assert abs(w.kontrol.mock.pan_hedef - w.pan_ham) < 0.01, "kart hedefi ekrandan koptu"

    # Operator yon verirse donus birakilir (iki kaynak hedefi ayni anda surmez)
    w._aci_hareket(0.0, -1.0)
    assert not w._merkez_timer.isActive(), "yon komutu merkeze almayi durdurmadi"

    # Yeniden baslat ve tamamla
    w._aci_reset()
    _merkeze_yurut(w)
    assert abs(w.pan_ham) < 0.1 and abs(w.tilt_aci) < 0.1

    # E-Stop yolda gelirse donus durur
    w._aci_hareket(50.0, 0.0)
    w._aci_reset()
    w.kontrol.estop(True)
    w._merkez_son_t -= 0.05
    w._merkez_tik()
    assert not w._merkez_timer.isActive(), "E-Stop merkeze almayi durdurmadi"


def test_ekrandaki_merkez_kol_yoklamasindan_etkilenmez():
    """⚠ GERÇEK HATA (22.09, kullanıcı bildirdi): kol takılıyken ekrandaki MERKEZ
    butonunu basılı tutmak İŞE YARAMIYORDU.

    Sebep: gamepad 50 ms'de bir yoklanıyor ve "L1/R1 basılı değil" diyerek merkez
    sayacını iptal ediyordu — sayacı KİMİN başlattığına bakılmıyordu. Artık sayacı
    yalnız başlatan kaynak iptal edebilir."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)

    w._dpad_press("center")                       # ekrandaki MERKEZ basılı tutuluyor
    assert w._merkez_kurma.isActive()
    for _ in range(5):                            # kol yoklaması akıp gidiyor
        w.gamepad = SahteGamepad(basili=())
        w._gamepad_tik()
    assert w._merkez_kurma.isActive(), "kol yoklaması ekrandaki merkez sayacını iptal etti"
    w._merkez_kurma_bitti()
    assert w._merkez_timer.isActive(), "2 sn dolunca merkeze alma başlamadı"

    # Tersi de doğru: koldan başlatılan sayacı ekrandaki tuşu bırakmak iptal etmez
    w._merkez_durdur()
    w._merkez_kurma_iptal()
    w.gamepad = SahteGamepad(basili=("l1",))
    w._gamepad_tik()
    assert w._merkez_kurma.isActive()
    w._dpad_release("center")
    assert w._merkez_kurma.isActive(), "ekrandaki bırakma kolun sayacını iptal etti"


def test_estopta_r_merkeze_almaz():
    """[R] (ve gamepad Y) E-Stop'ta HICBIR sey yapmamali.

    Eskiden bu koruma yalniz MERKEZ butonunun devre disi kalmasina dayaniyordu;
    klavye yolu (_dpad_press -> _aci_reset) onu atliyordu: E-Stop'ta ekrandaki acilar
    sifirlanir, karta 'eve don' giderdi. Buton kaldirilinca koruma _aci_reset'in
    kendi icine alindi."""
    w = SahtePencere()
    w._aci_hareket(40.0, 20.0)
    w.kontrol.estop(True)
    once = (w.pan_ham, w.tilt_aci, w.kontrol.pan_hedef)
    w._dpad_press("center")                              # MERKEZ'e basildi
    assert not w._merkez_kurma.isActive(), "E-Stop'ta merkez sayaci basladi"
    w._merkez_kurma_bitti()                              # sayac yine de dolsa
    assert not w._merkez_timer.isActive(), "E-Stop'ta merkeze alma basladi"
    assert (w.pan_ham, w.tilt_aci, w.kontrol.pan_hedef) == once, "E-Stop'ta merkeze alindi"

    # E-Stop kalkinca calisir: 2 sn basili tutma + KADEMELI donus
    w.kontrol.estop(False)
    w._dpad_press("center")
    assert w._merkez_kurma.isActive(), "merkez sayaci baslamadi"
    assert (w.pan_ham, w.tilt_aci) == (40.0, 20.0), "sayac dolmadan merkeze alindi"
    w._merkez_kurma_bitti()
    assert w._merkez_timer.isActive(), "kademeli merkeze alma baslamadi"
    _merkeze_yurut(w)
    assert abs(w.pan_ham) < 0.1 and abs(w.tilt_aci) < 0.1, (w.pan_ham, w.tilt_aci)


def test_lazer_isigi_yalniz_gercek_lazer_acikken_yanar():
    """Aci karolarindaki kirmizi isik ARAYUZ tahmini degil, kontrol katmaninin
    (kartla eslenmis) lazer durumudur: ates -> yanar, kes / E-Stop -> soner."""
    class SahteKaro:
        lazer_acik = False
        def lazer_ayarla(self, acik):
            self.lazer_acik = acik
    w = SahtePencere()
    w.arac_ikon, w.arac_yon_ikon = SahteKaro(), SahteKaro()
    w._lazer_bilgi_yaz()
    assert not w.arac_ikon.lazer_acik, "lazer kapaliyken isik yandi"
    w.fire_btn.setChecked(True)                           # ATES (mevcut testlerle ayni yol)
    w._esp_goster(w.kontrol.ates(True))
    assert w.arac_ikon.lazer_acik and w.arac_yon_ikon.lazer_acik, "ates var, isik yok"
    w._esp_goster(w.kontrol.estop(True))                  # E-Stop lazeri keser
    assert not w.arac_ikon.lazer_acik, "E-Stop sonrasi isik hala yaniyor"


def test_dikey_hareket_penceresi_kullanici_ornegi():
    """Dikey pencere operator acisinda −20…+20 (0 = yere paralel).
    Gimbal bu araligin disina CIKAMAZ; pencere kapaliyken bile YAPISAL calisma
    tavani (bolge.TILT_CALISMA_*) gecerlidir."""
    w = SahtePencere()
    w.bolge.hareket_tilt = B.Pencere(True, -20.0, 20.0)    # operator acisi, 0 = yere paralel
    w._aci_hareket(0.0, 40.0)                              # +40 isterdi
    assert w.tilt_aci == 20.0 and w.kontrol.tilt_hedef == 20.0, w.tilt_aci
    w._aci_hareket(0.0, -60.0)                             # asagi dibe isterdi
    # ⚠ Bu testte kontrol MOCK (eski tek kart) yolundadir: orada operator tabani 0'dir,
    #   dolayisiyla -20 degil 0'da durulur. AYRI TILT KARTINDA taban -25'tir
    #   (tilt_surucu.ACI_MIN) ve ayni pencere -20'de durdurur.
    assert w.tilt_aci == 0.0, w.tilt_aci
    # pencere kapaliyken bile yapisal tavan asilamaz
    w.bolge.hareket_tilt = B.Pencere(False, -20.0, 20.0)   # pencere kapali
    w._aci_hareket(0.0, 500.0)
    assert w.tilt_aci == w.max_tilt_limit == 30.0, w.tilt_aci     # mekanik tavan kalir


def test_yatay_pencere_arkadan_dolanilamaz():
    """Yatayda fiziksel sinir yok (360°) ama pencere varken gimbal arkadan dolanip
    yasak bolgeye GECEMEZ — pan sarmasiz hesaplanir."""
    w = SahtePencere()
    w.bolge.hareket_pan = B.Pencere(True, -30.0, 30.0)
    for _ in range(20):                                     # saga israrla basmak
        w._aci_hareket(10.0, 0.0)
    assert w.pan_ham == 30.0, w.pan_ham
    for _ in range(20):                                     # sola israrla basmak
        w._aci_hareket(-10.0, 0.0)
    assert w.pan_ham == -30.0 and w.pan_aci == 330.0, (w.pan_ham, w.pan_aci)


def test_dikey_atis_penceresi_ates_keser():
    """Atis penceresi dikeyde de gecerli: namlu pencereden cikinca ates KESILIR."""
    w = SahtePencere()
    w.bolge.atis_tilt = B.Pencere(True, -10.0, 10.0)       # operator acisi
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    w._aci_hareket(0.0, 5.0)                               # +5: icerde
    assert w.kontrol.durum["lazer"] is True
    w._aci_hareket(0.0, 10.0)                              # +15: DISARIDA
    assert w.kontrol.durum["lazer"] is False, "dikey atis penceresi disinda lazer yandi"


def test_lazer_gucu_onaysiz_degismez():
    """Lazer sayfasi TASLAK uzerinde calisir: kaydirici/kademe ve 'Kaydet' karta
    HICBIR SEY gondermez; yalniz onay ('Değiştir') gonderir. ✕ taslagi atar."""
    w = SahtePencere()
    w.lazer_sl = SahteKaydirici(P.LAZER_GUC_VARSAYILAN)
    w._lazer_taslak_ayarla(70)
    assert w.lazer_guc == P.LAZER_GUC_VARSAYILAN == w.kontrol.mock.lazer_guc, "taslak karta gitti"
    w._lazer_guc_degisti(w.lazer_taslak)                    # 'Değiştir' = tek uygulama kapisi
    assert w.lazer_guc == 70 == w.kontrol.mock.lazer_guc


def test_odunc_kapilar_gercek_pencerede_de_metot():
    """SahtePencere kapilari MainWindow'dan ODUNC alir. Bir metot gercek sinifta
    yanlislikla @staticmethod/@classmethod olursa sinif uzerinden okunan duz fonksiyon
    SahtePencere'de normal calisir — testler YESIL kalir ama gercek pencerede cagri
    patlar. 22.09'da tam bu oldu: `_aci_hareket` ustune sahipsiz bir @staticmethod
    yapismisti; klavye, D-pad, gamepad ve otonom hareketin HEPSI calismiyordu ve hicbir
    test gormedi. Bu test o acigi kapatir."""
    import inspect
    bozuk = []
    for ad, deger in vars(SahtePencere).items():
        if not callable(deger) or ad.startswith("__"):
            continue
        gercek = inspect.getattr_static(A.MainWindow, ad, None)
        if isinstance(gercek, (staticmethod, classmethod)):
            bozuk.append(ad)
    assert not bozuk, f"gercek pencerede metot OLMAYAN kapilar: {bozuk}"


if __name__ == "__main__":
    test_ekran_aci_kart_hedefi_ayni()
    test_azimut_sarmasiz_gider()
    test_yatay_on_yariyi_gecemez()
    test_ates_sirasinda_yasak_alan()
    test_harekete_yasak_alan()
    test_estop_hareketi_keser()
    test_sabit_hiz_duzeyi_karta_gider()
    test_kart_disaridan_durdurulursa_ates_birakilir()
    test_donanim_butonu_yazilimdan_kaldirilamaz()
    test_kart_reseti_yakalanir()
    test_estopta_enable_kesilmez()
    test_estopta_iki_eksen_de_oldugu_yerde_donar()
    test_devam_edince_referans_korunur()
    test_basili_tutma_motor_hizini_asmaz()
    test_klavye_atesi_space_b_basili_tutma()
    test_aci_karosu_yasak_alan_dilimleri()
    test_kol_gostergesi_gercek_durumu_yansitir()
    test_gamepad_ayni_kapilardan_gecer()
    test_lazer_gucu_arayuzden_karta_gider()
    test_ates_tazelemesi_kesilirse_lazer_soner()
    test_ates_kapaliyken_tazeleme_gitmez()
    test_basili_tutma_estopta_kesilir()
    test_estopta_r_merkeze_almaz()
    test_merkeze_alma_kademeli_ve_kesilebilir()
    test_ekrandaki_merkez_kol_yoklamasindan_etkilenmez()
    test_lazer_isigi_yalniz_gercek_lazer_acikken_yanar()
    test_dikey_hareket_penceresi_kullanici_ornegi()
    test_yatay_pencere_arkadan_dolanilamaz()
    test_dikey_atis_penceresi_ates_keser()
    test_lazer_gucu_onaysiz_degismez()
    test_odunc_kapilar_gercek_pencerede_de_metot()
    print("kapi testleri OK — ekran/kart hedefi, sarmasiz azimut, ates sirasinda yasak "
          "alan, harekete yasak alan, E-Stop, hiz duzeyi, kart disaridan durdurma, "
          "donanim acil stop butonu, ENABLE kesilmez, iki eksen donar, referans korunur, basili tutma, "
          "Space+B/ESC klavye atesi, gamepad, lazer gucu, ates olu adam anahtari")
