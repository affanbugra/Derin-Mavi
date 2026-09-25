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
    """Metin/stil cagrilarini yutan sahte QLabel (son metni `_metin`de tutar)."""

    def setText(self, metin="", *a):
        self._metin = metin

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
    TEKRAR_PERIYOT_MS = A.MainWindow.TEKRAR_PERIYOT_MS
    _acilis_hizala = A.MainWindow._acilis_hizala          # birlesik surumde eklendi
    _acilis_yukselisini_dene = A.MainWindow._acilis_yukselisini_dene
    tilt_taban_deg = A.MainWindow.tilt_taban_deg
    _dpad_press = A.MainWindow._dpad_press
    _dpad_release = A.MainWindow._dpad_release
    TEKRAR_GECIKME_MS = A.MainWindow.TEKRAR_GECIKME_MS
    _ates_bas = A.MainWindow._ates_bas
    _ates_kes = A.MainWindow._ates_kes
    _takip_korlugu = A.MainWindow._takip_korlugu        # _ates_kes korlugu kisaltir
    _ates_kisayolu = A.MainWindow._ates_kisayolu
    _ates_tusu = A.MainWindow._ates_tusu
    _ates_isigi = A.MainWindow._ates_isigi
    _kol_isik = A.MainWindow._kol_isik
    _kol_parla = A.MainWindow._kol_parla
    _kol_gamepad_isik = A.MainWindow._kol_gamepad_isik
    _kol_yenile = A.MainWindow._kol_yenile
    _zoom_acik = A.MainWindow._zoom_acik
    _hassasiyet = A.MainWindow._hassasiyet
    _manuel_hareket_izni = A.MainWindow._manuel_hareket_izni
    _asama_sec = A.MainWindow._asama_sec
    _mod_sec = A.MainWindow._mod_sec
    _mod_uygula = A.MainWindow._mod_uygula
    _mod_gorunum = A.MainWindow._mod_gorunum
    _otonom_baslat = A.MainWindow._otonom_baslat
    HAZIRLIK = A.MainWindow.HAZIRLIK
    ASAMA_IDX = A.MainWindow.ASAMA_IDX
    _hassasiyet_ayarla = A.MainWindow._hassasiyet_ayarla
    _hassasiyet_basis = A.MainWindow._hassasiyet_basis
    HASSASIYET_TUSU = A.MainWindow.HASSASIYET_TUSU
    HASSASIYET_ARALIK_S = A.MainWindow.HASSASIYET_ARALIK_S
    HASSASIYET = A.MainWindow.HASSASIYET
    HASSASIYET_VARSAYILAN = A.MainWindow.HASSASIYET_VARSAYILAN
    _zoom_katsayi = A.MainWindow._zoom_katsayi
    _zoom_guncelle = A.MainWindow._zoom_guncelle
    _zoom_tusu = A.MainWindow._zoom_tusu
    _zoom_tus_tik = A.MainWindow._zoom_tus_tik
    ZOOM_TUSLARI = A.MainWindow.ZOOM_TUSLARI
    ZOOM_MAX = A.MainWindow.ZOOM_MAX
    ZOOM_HIZ = A.MainWindow.ZOOM_HIZ
    _tus_bas = A.MainWindow._tus_bas
    _tus_birak = A.MainWindow._tus_birak
    _tus_yonu = A.MainWindow._tus_yonu
    ATES_TUSLARI = A.MainWindow.ATES_TUSLARI
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
    _manuel_komut = A.MainWindow._manuel_komut     # basili tutma / cubuk: yorunge + fren
    _manuel_fren = A.MainWindow._manuel_fren
    _yorunge_var = A.MainWindow._yorunge_var
    _fren_yolu = A.MainWindow._fren_yolu
    _fren_tik = A.MainWindow._fren_tik
    _fren_durdur = A.MainWindow._fren_durdur
    FREN_S = A.MainWindow.FREN_S
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
        self._zoom_tuslar, self._zoom_tus_t, self._zoom_timer = set(), 0.0, SahteTimer()
        self._manuel_hiz, self._manuel_hiz_t, self._manuel_kaynak = None, 0.0, None
        self._fren_hiz, self._fren_bitis = None, 0.0
        self._fren_timer = SahteTimer()
        self._gp_ates_basili = False
        self._merkez_calisiyor = False
        self._merkez_son_t = time.time()
        self._merkez_timer = SahteTimer()
        self._kol_ui, self._kol_gp = set(), set()
        self.kol_ikon = SahteKol()
        self.hassasiyet = "Hızlı"            # eski testlerin varsaydigi 1° / 40°/s
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
    # Tavan artik POLITIKA degil: acilistaki hareket penceresi (varsayilan ±30 =
    # kalibre edilmis kolun tamami). Operator daraltmak isterse arayuzden yazar.
    assert w.tilt_aci == w.bolge.hareket_tilt.ust == 30.0, w.tilt_aci
    assert w.kontrol.mock.tilt_hedef == w.tilt_aci, w.kontrol.mock.tilt_hedef

    # Limitte fazladan komut: gonderilecek yeni bir aci yok, bos komut da atilmamali.
    komut = len(w.kontrol.mock.kayit)
    w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == w.bolge.hareket_tilt.ust
    assert len(w.kontrol.mock.kayit) == komut, w.kontrol.mock.kayit[-1]

    w._aci_hareket(0.0, -5.0)                 # asagi normal calisir
    assert w.tilt_aci == 25.0 and w.kontrol.mock.tilt_hedef == 25.0

    # Kismi kirpma: 25°'de +8 istenir, ancak +5 uygulanabilir -> ikisi de 30 olmali.
    w._aci_hareket(0.0, 8.0)
    assert w.tilt_aci == 30.0, w.tilt_aci
    assert w.kontrol.mock.tilt_hedef == 30.0, w.kontrol.mock.tilt_hedef


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


def test_yatay_sinir_yalniz_pencereden_gelir():
    """[KESİN 23.09] Yatayda KODDA sınır yoktur: sınırı operatör arayüzdeki hareket
    penceresinden koyar. Pencere kapalıysa gimbal serbesttir; pencere varsa dışına
    çıkamaz ve arkadan dolanamaz (pan sarmasız hesaplanır)."""
    w = SahtePencere()
    # Varsayılan: pencere AÇIK (±90) — ama bu bir VARSAYILAN, kod sınırı değil
    assert w.bolge.hareket_pan.aktif
    assert w.bolge.hareket_pan.ust == B.PAN_VARSAYILAN == 90.0
    w._aci_hareket(120.0, 0.0)
    assert w.pan_ham == 90.0, w.pan_ham

    # Operatör pencereyi GENİŞLETİRSE gimbal oraya gider (eskiden ±60'ta takılırdı)
    w.bolge.hareket_pan = B.Pencere(True, -150.0, 150.0)
    w._aci_hareket(60.0, 0.0)
    assert w.pan_ham == 150.0, w.pan_ham

    # Pencere KAPALIYSA kod hic karismaz (arayuz disinda sinir yok)
    w2 = SahtePencere()
    w2.bolge.hareket_pan = B.Pencere(False, -90.0, 90.0)
    w2._aci_hareket(200.0, 0.0)
    assert w2.pan_ham == 200.0, w2.pan_ham

    # Pencere DARALTILIRSA sınırda kırpılır ve arkadan dolanılamaz
    w3 = SahtePencere()
    w3.bolge.hareket_pan = B.Pencere(True, -45.0, 45.0)
    w3._aci_hareket(200.0, 0.0)
    assert w3.pan_ham == 45.0, w3.pan_ham
    for _ in range(20):
        w3._aci_hareket(-10.0, 0.0)
    assert w3.pan_ham == -45.0 and w3.pan_aci == 315.0, (w3.pan_ham, w3.pan_aci)


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
    w._aci_hareket(0.0, 10.0)                 # 20 -> 30 (tavanda kirpilir)
    assert w.tilt_aci == 30.0 and w.kontrol.mock.tilt_hedef == 30.0
    w._aci_hareket(0.0, -10.0)
    assert w.tilt_aci == 20.0 and w.kontrol.mock.tilt_hedef == 20.0


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


def test_klavye_atesi_tek_dokunus():
    """Klavyeden ateş: [Space] + [B] BİRLİKTE → AÇ/KES (bekleme YOK); tek tuş boş (24.09).

    Basılı tutma kuralı 23.09'da kaldırıldı (yarışmada saniye = puan). Klavyenin
    ATEŞ butonundan fazla yetkisi yoktur: E-Stop'ta ve atışa yasak bölgede
    klavyeyle de ateş açılamaz (şartname Yetenek 4)."""
    Qt = A.Qt
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)

    def bas(tus):
        w._tus_bas(SahteTus(tus))

    def birak(tus):
        w._tus_birak(SahteTus(tus))

    def ikili():
        bas(Qt.Key_Space); bas(Qt.Key_B); birak(Qt.Key_B); birak(Qt.Key_Space)

    # TEK TUS bir sey yapmaz (ne Space ne B)
    for tus in (Qt.Key_Space, Qt.Key_B):
        bas(tus); birak(tus)
        assert w.kontrol.mock.lazer is not True and not w.fire_btn.isChecked(), \
            "tek tusla ates acildi"

    # Space + B birlikte acar, tekrar birlikte keser (siranin onemi yok)
    ikili()
    assert w.fire_btn.isChecked() and w.kontrol.mock.lazer is True, "Space+B atesi acmadi"
    bas(Qt.Key_B); bas(Qt.Key_Space)
    assert not w.fire_btn.isChecked() and w.kontrol.mock.lazer is False, "Space+B atesi kesmedi"
    birak(Qt.Key_Space); birak(Qt.Key_B)

    # Basili tutmak tekrarlamaz: ikisi basili kalirken otomatik tekrar gelir
    bas(Qt.Key_Space); bas(Qt.Key_B)
    assert w.kontrol.mock.lazer is True
    w._tus_bas(SahteTus(Qt.Key_B, tekrar=True))
    assert w.kontrol.mock.lazer is True, "basili tutmak atesi kapatti"
    # Tuslari BIRAKMAK atesi kesmez (ac/kapa mantigi)
    birak(Qt.Key_B); birak(Qt.Key_Space)
    assert w.kontrol.mock.lazer is True, "tus birakinca ates kendiliginden kesildi"
    ikili()
    assert w.kontrol.mock.lazer is False

    # Odak kaybi basili kaydini silmeli; yoksa sonra TEK B atesi acardi
    bas(Qt.Key_Space)
    w._ates_tus_basili.clear()                   # FocusOut'un yaptigi (eventFilter)
    bas(Qt.Key_B); birak(Qt.Key_B)
    assert w.kontrol.mock.lazer is False, "takili Space ile tek B atesi acti"

    # E-Stop: buton kilitli -> klavye de acamaz
    w.thread.estop = True
    w.fire_btn.setEnabled(False)
    ikili()
    assert w.kontrol.mock.lazer is False, "E-Stop'ta klavyeden ates acildi"

    # Atisa yasak bolge de reddedilir (ates kapisi ortak)
    w.thread.estop = False
    w.fire_btn.setEnabled(True)
    w.bolge.atis_pan = B.Pencere(True, 40.0, 60.0)   # pan 0 -> pencere DISI (yasak)
    ikili()
    assert w.kontrol.mock.lazer is False, "yasak bolgede klavyeden ates acildi"

    # [L] ates tusu DEGILDIR (gecmiste oyleydi; kaldirildi)
    w.bolge.atis_pan = B.Pencere(False, -180.0, 180.0)
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
    assert yon.ARALIK == (-180.0, 180.0)        # yatayda kod sinir koymaz
    assert dilimler(yon, (True, -45, 45), (True, -30, 20)) == [
        ("hareket", -180.0, -45), ("hareket", 45, 180.0),
        ("atis", -45, -30), ("atis", 20, 45), ("izin", -30, 20)]
    # yalniz atis acik: hareket penceresi tum eksen sayilir
    assert dilimler(yon, (False, 0, 0), (True, -45, 45)) == [
        ("atis", -180.0, -45), ("atis", 45, 180.0), ("izin", -45, 45)]
    # dikey: yalniz MEKANIK aralik boyanir (kolun gidebildigi yer)
    alt, ust = A.AracAciGostergesi.ARALIK
    assert dilimler(A.AracAciGostergesi, (True, -20, 20), (False, 0, 0)) == [
        ("hareket", alt, -20), ("hareket", 20, ust)]


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
    w._ates_kisayolu()                         # ates AC (tek dokunus)
    assert w.fire_btn.isChecked() and {"l2", "r2"} <= w.kol_ikon.yanan, \
        "ates acikken koldaki tetikler yanmiyor"
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

    # --- ATES: L2 + R2 birlikte -> AC/KES (bekleme yok; tek tetik ACMAZ)
    w.thread.estop = False
    w.gamepad = SahteGamepad(basili=("l2",))           # tek tetik
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "tek tetik ates acti"

    w.fire_btn.setEnabled(False)                       # E-Stop benzeri kilit
    w.thread.estop = True
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "E-Stop'ta gamepad ile ateş açıldı"

    w.thread.estop = False
    w.fire_btn.setEnabled(True)
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is True, "gamepad ateş açmadı"

    # Ates ACIKKEN ayni hareket keser
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "gamepad ateşi kesmedi"

    # --- Atışa yasak bölgede ateş reddedilmeli (ortak kapı)
    w.bolge.atis_pan = B.Pencere(True, 100.0, 110.0)  # pan 0 -> pencere DISI
    w.gamepad = SahteGamepad(basili=("l2", "r2"))
    w._gamepad_tik()
    assert w.kontrol.mock.lazer is False, "yasak bölgede gamepad ile ateş açıldı"
    w.bolge.atis_pan.aktif = False

    # --- MERKEZ: L1 + R1 BIRLIKTE -> merkeze al (kademeli); tek omuz tusu bos (24.09)
    w.bolge.atis_pan.aktif = False
    w._aci_hareket(5.0, 5.0)
    w.gamepad = SahteGamepad(basili=("r1",))
    w._gamepad_tik()
    assert not w._merkez_timer.isActive(), "tek R1 merkeze almaya basladi"
    w.gamepad = SahteGamepad(basili=("l1", "r1"))
    w._gamepad_tik()
    assert w._merkez_timer.isActive(), "L1+R1 merkeze almayı başlatmadı"
    _merkeze_yurut(w)
    assert abs(w.pan_aci) < 0.1 and abs(w.tilt_aci) < 0.1, "L1+R1 merkeze almadı"

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
    assert not w._merkez_timer.isActive(), "E-Stop'ta merkeze alma basladi"
    assert (w.pan_ham, w.tilt_aci, w.kontrol.pan_hedef) == once, "E-Stop'ta merkeze alindi"

    # E-Stop kalkinca calisir: 2 sn basili tutma + KADEMELI donus
    w.kontrol.estop(False)
    w._dpad_press("center")
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


def test_sag_cubuk_zoom_otonomda_yok():
    """Sağ joystick Y = görüntü zoom'u; Aşama 1'de ve A2/A3 HAZIRLIĞINDA var, otonom
    BAŞLAYINCA yok (25.09; önce yalnız A1'di). Zoom gimbal'e HİÇ komut göndermez;
    koşul dışında 1×'e döner ve sıfırlanır."""
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)
    w.asama = "Aşama 1"
    w._zoom = 1.0

    def kol(zoom, sure=0.05, adim=20):
        for _ in range(adim):
            w.gamepad = SahteGamepad()
            w.gamepad._d.zoom = zoom
            w._gp_son_t = A.time.time() - sure
            w._gamepad_tik()

    pan0, tilt0 = w.pan_aci, w.tilt_aci
    kol(1.0)                                     # ~1 sn tam yukari
    assert w._zoom_katsayi() > 2.0, f"yukari yakinlastirmadi: {w._zoom}"
    assert "sag_cubuk" in w.kol_ikon.yanan, "zoom sirasinda sag cubuk yanmadi"
    assert (w.pan_aci, w.tilt_aci) == (pan0, tilt0), "zoom gimbal'i oynatti"
    kol(1.0, adim=100)
    assert w._zoom_katsayi() == w.ZOOM_MAX, "zoom tavani asildi"
    kol(-1.0, adim=100)
    assert w._zoom_katsayi() == 1.0, "asagi 1x'e donmedi / 1x altina indi"

    # A2/A3 hazirliginda zoom VAR (Asama 1 gibi); otonom baslayinca YOK
    for asama in ("Aşama 2", "Aşama 3"):
        w.mod, w.asama, w._zoom = w.HAZIRLIK, asama, 1.0
        kol(1.0)
        assert w._zoom_katsayi() > 2.0, f"{asama} hazirliginda zoom calismadi: {w._zoom}"
        w.mod, w._zoom = "Otonom", 1.0
        kol(1.0)
        assert w._zoom_katsayi() == 1.0, f"{asama} otonomda zoom calisti"

    # Klavye: [Z] basili yakinlastirir, [X] uzaklastirir; gimbal oynamaz
    Qt = A.Qt
    w.mod, w.asama, w._zoom = "Manuel", "Aşama 1", 1.0

    def tus(k, sure=1.0, adim=20):
        w._tus_bas(SahteTus(k))
        assert w._zoom_timer.isActive(), "Z/X basinca zoom zamanlayicisi baslamadi"
        for _ in range(adim):
            w._zoom_tus_t = A.time.time() - sure / adim
            w._zoom_tus_tik()
        w._tus_birak(SahteTus(k))
        assert not w._zoom_timer.isActive(), "tus birakilinca zoom durmadi"

    tus(Qt.Key_Z)
    assert w._zoom_katsayi() > 2.0, f"[Z] yakinlastirmadi: {w._zoom}"
    assert (w.pan_aci, w.tilt_aci) == (pan0, tilt0), "[Z] gimbal'i oynatti"
    tus(Qt.Key_X, sure=5.0)
    assert w._zoom_katsayi() == 1.0, "[X] 1x'e donmedi"
    w.mod = "Otonom"
    tus(Qt.Key_Z)
    assert w._zoom_katsayi() == 1.0, "Otonom'da [Z] zoom yapti"
    w.mod = "Manuel"

    # Otonoma gecince sifirlanir; hazirliga donunce eski yakinlik gelmez
    w.mod, w.asama = w.HAZIRLIK, "Aşama 2"
    kol(1.0)
    w.mod = "Otonom"
    assert w._zoom_katsayi() == 1.0
    w.mod = w.HAZIRLIK
    assert w._zoom_katsayi() == 1.0, "hazirliga donunce eski zoom geri geldi"


def test_hassasiyet_tek_dokunus_ve_hiz():
    """HASSASİYET (24.09): tek dokunuş adımı ve basılı tutma hızı seçili kademeden gelir;
    kolun D-pad'i de klavye gibi TEK ADIM atar (eskiden kısa basış bile 40°/s akıyordu,
    15 m'de nişan alınamıyordu). Joystick karesel: yarım itiş çeyrek hız."""
    for ad, (adim, hiz) in A.MainWindow.HASSASIYET.items():
        w = SahtePencere()
        w.thread = A.VideoThread(None, None, None)
        w.hassasiyet = ad
        # klavye / ekrandaki D-pad: tek dokunus = adim
        w._dpad_press("right"); w._dpad_release("right")
        assert abs(w.pan_aci - adim) < 0.011, f"{ad}: klavye tek dokunus {w.pan_aci}° (beklenen {adim}°)"
        # kol D-pad: ilk basis TEK ADIM, esik dolmadan akmaz
        once = w.pan_aci
        w.gamepad = SahteGamepad(pan=1.0, basili=("right",))
        w.gamepad._d.dpad = True
        w._gp_son_t = time.time() - 0.1
        w._gamepad_tik()
        assert abs(w.pan_aci - once - adim) < 0.011, f"{ad}: kol D-pad ilk basis {w.pan_aci - once}°"
        w.gamepad = SahteGamepad(pan=1.0, basili=("right",), kenar=())
        w.gamepad._d.dpad = True
        w._gp_son_t = time.time() - 0.1
        w._gamepad_tik()
        assert abs(w.pan_aci - once - adim) < 0.011, f"{ad}: kol D-pad esik dolmadan akti"
        # esik doldu: secili hizla akar (0.1 sn x hiz)
        w._gp_dpad_t0 = time.time() - 1.0
        onc2 = w.pan_aci
        w._gp_son_t = time.time() - 0.1
        w._gamepad_tik()
        assert 0 < w.pan_aci - onc2 <= hiz * 0.1 + 0.02, f"{ad}: basili hiz {w.pan_aci - onc2}"
        # joystick: yarim itis = ceyrek hiz
        w2 = SahtePencere()
        w2.thread = A.VideoThread(None, None, None)
        w2.hassasiyet = ad
        w2.gamepad = SahteGamepad(pan=0.5)
        w2._gp_son_t = time.time() - 0.1
        w2._gamepad_tik()
        assert 0 < w2.pan_aci <= hiz * 0.25 * 0.1 + 0.02, f"{ad}: joystick egrisi {w2.pan_aci}"
    # Hassas kademe 15 m'de balondan kucuk adim atmali
    assert A.MainWindow.HASSASIYET["Hassas"][0] <= 0.1


def test_hassasiyet_kisayolu_ve_kutu_kaymasi():
    """[C] / kol Çarpı: yarım saniyede art arda 1/2/3 basış = Hassas/Orta/Hızlı (25.09).
    Ayrıca kutu gecikme telafisi: kamera dönüşü kadar px kayma, işaret ve boyut doğru."""
    Qt = A.Qt
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)
    w.hassasiyet = "Hızlı"
    T = [100.0]

    def c(ara=0.2):
        T[0] += ara
        w._hassasiyet_basis(T[0])

    c(5.0); assert w.hassasiyet == "Hassas", w.hassasiyet
    c(); assert w.hassasiyet == "Orta", w.hassasiyet
    c(); assert w.hassasiyet == "Hızlı", w.hassasiyet
    c(); assert w.hassasiyet == "Hızlı", "4. basis tavani asti"
    c(1.0); assert w.hassasiyet == "Hassas", "ara verince yeniden saymadi"
    # klavye [C] ve kol Capraz ayni yoldan
    w._hs_son_t = -1e9
    assert w._tus_bas(SahteTus(Qt.Key_C)) and w.hassasiyet == "Hassas"
    w._tus_bas(SahteTus(Qt.Key_C))
    assert w.hassasiyet == "Orta", "[C] ikinci basis Orta yapmadi"
    w._tus_bas(SahteTus(Qt.Key_C, tekrar=True))
    assert w.hassasiyet == "Orta", "[C] otomatik tekrar kademe degistirdi"
    w._hs_son_t = -1e9
    w.gamepad = SahteGamepad(basili=("capraz",))
    w._gamepad_tik()
    assert w.hassasiyet == "Hassas", "kol Capraz hassasiyeti secmedi"

    # Kutu kaymasi: kamera 2° saga dondu -> sahne sola kayar (dx < 0), 1280 px'te ppd px/°
    aci = {1.0: (10.0, 5.0), 2.0: (12.0, 5.5)}
    fn = lambda t: aci[round(t + float(A.algi.AYAR.get("kamera_gecikme", 0.03)), 3)]
    dx, dy = A.kamera_kaymasi_px(fn, 1.0, 2.0, 1280)
    ppd = float(A.algi.AYAR.get("takip_ppd_pan", 18.7))
    assert abs(dx + 2.0 * ppd) < 1e-6 and abs(dy - 0.5 * ppd) < 1e-6, (dx, dy)
    assert A.kamera_kaymasi_px(None, 1.0, 2.0, 1280) is None
    assert A.kamera_kaymasi_px(lambda t: None, 1.0, 2.0, 1280) is None
    assert A.kamera_kaymasi_px(fn, None, 2.0, 1280) is None


def test_mod_asama_bagi_hazirlikta_elle_kontrol_otonomda_yok():
    """25.09: Manuel = Aşama 1 (kendiliğinden seçili). Aşama 2/3 seçilince HAZIRLIK:
    otonom BAŞLAMAZ; klavye / kol / ekrandaki D-pad / merkeze al Aşama 1'deki gibi
    ÇALIŞIR (25.09 akşam kullanıcı isteği; öğlen hazırlıkta hareket yoktu). Otonom yalnız
    BAŞLAT ile başlar: o an elle hareket ve zoom BİTER, süren merkeze alma DURUR, elle
    ateş AÇILMAZ (kesmek serbest). Tekrar basınca hazırlığa döner, elle kontrol geri
    gelir. Mod değişince elle açılmış ateş kesilir; ACİL DURDUR'dayken BAŞLAT reddedilir."""
    Qt = A.Qt
    import types
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)
    w.inference_thread = types.SimpleNamespace(
        otonom=False, nisanci=types.SimpleNamespace(sifirla=lambda: None))
    w._asama_uygula = lambda: None               # gorunum (stack/pill) testte yok
    w.mod_btns = {m: SahteButon() for m in ("Manuel", "Otonom")}
    w.asama_btns = {a: SahteButon() for a in ("Aşama 1", "Aşama 2", "Aşama 3")}
    w.baslat_btn = SahteButon()
    w.sb_mod = SahteEtiket()

    def yollar():
        """Her elle kontrol yolunu ayri dener. Doner: {yol: calisti mi}."""
        s = {}
        for ad, yap in (("ekran D-pad", lambda: (w._dpad_press("right"), w._dpad_release("right"))),
                        ("klavye", lambda: (w._tus_bas(SahteTus(Qt.Key_W)),
                                            w._tus_birak(SahteTus(Qt.Key_W))))):
            once = (w.pan_aci, w.tilt_aci)
            yap()
            s[ad] = (w.pan_aci, w.tilt_aci) != once
        once = (w.pan_aci, w.tilt_aci)
        w.gamepad = SahteGamepad(pan=1.0)
        w._gp_son_t = time.time() - 0.1
        w._gamepad_tik()
        s["kol cubugu"] = (w.pan_aci, w.tilt_aci) != once
        w.gamepad = SahteGamepad()
        w._gamepad_tik()                                   # cubuk birakildi
        for ad, yap in (("klavye merkez", lambda: w._tus_bas(SahteTus(Qt.Key_R))),
                        ("kol merkez", lambda: (setattr(w, "gamepad", SahteGamepad(basili=("l1", "r1"))),
                                                w._gamepad_tik()))):
            w._merkez_timer.stop()
            yap()
            s[ad] = w._merkez_timer.isActive()
            w._merkez_timer.stop()
        w._tus_birak(SahteTus(Qt.Key_R))
        return s

    # Manuel sekmesi -> Asama 1; Otonom sekmesi -> A2 HAZIRLIK (otonom baslamaz)
    w._mod_sec("Manuel")
    assert (w.mod, w.asama) == ("Manuel", "Aşama 1")
    assert all(yollar().values()), "Asama 1'de elle kontrol calismiyor"
    w._mod_sec("Otonom")
    assert (w.mod, w.asama) == (w.HAZIRLIK, "Aşama 2"), (w.mod, w.asama)
    assert w.mod_btns["Otonom"].isChecked() and not w.baslat_btn.isChecked()
    assert not w.inference_thread.otonom, "hazirlikta otonom nisan dongusu acildi"

    # Hazirlikta elle kontrol Asama 1 gibi: her yol calisir
    s = yollar()
    assert all(s.values()), f"hazirlikta calismayan elle yol: {[k for k, v in s.items() if not v]}"

    # BASLAT -> Otonom: SUREN merkeze alma durur, zoom 1x'e doner, elle kontrol biter
    w._aci_reset()
    assert w._merkez_timer.isActive()
    w._zoom = 3.0
    w._otonom_baslat()
    assert w.mod == "Otonom" and w.baslat_btn.isChecked()
    assert w.inference_thread.otonom, "BASLAT otonom nisan dongusunu acmadi"
    assert not w._merkez_timer.isActive(), "otonom basladi ama merkeze alma suruyor"
    assert w._zoom_katsayi() == 1.0, "otonomda zoom kaldi"
    s = yollar()
    assert not any(s.values()), f"otonomda gecen elle yol: {[k for k, v in s.items() if v]}"
    # Otonomda elle ates ACILMAZ; otonomun actigi atesi KESMEK serbest
    for ac in (lambda: w._ates_kisayolu(),
               lambda: (w._tus_bas(SahteTus(Qt.Key_Space)), w._tus_bas(SahteTus(Qt.Key_B)))):
        ac()
        assert not w.kontrol.mock.lazer and not w.fire_btn.isChecked(), "otonomda elle ates acildi"
        w._tus_birak(SahteTus(Qt.Key_Space)); w._tus_birak(SahteTus(Qt.Key_B))
    w.fire_btn.setChecked(True)
    w._ates_bas()                                # otonomun atesi (ayni tek kapi)
    assert w.kontrol.mock.lazer is True
    w._ates_kisayolu()
    assert w.kontrol.mock.lazer is False and not w.fire_btn.isChecked(), \
        "otonomda kisayol atesi kesmedi"
    # DURDUR -> Hazirlik: elle kontrol geri gelir
    w._otonom_baslat()
    assert w.mod == w.HAZIRLIK and not w.baslat_btn.isChecked()
    assert not w.inference_thread.otonom, "DURDUR otonom dongusunu kapatmadi"
    assert all(yollar().values()), "otonom durdurulunca elle kontrol geri gelmedi"

    # Asama degisirse calisan otonom durur (yeni asama onaysiz baslamaz)
    w._otonom_baslat()
    w._asama_sec("Aşama 3")
    assert w.mod == w.HAZIRLIK, "asama degisince otonom surdu"
    # Asama 3 ayni mantik: hazirlikta elle kontrol, kendi BAŞLAT'i, otonomda yok
    assert "AŞAMA 3" in w.baslat_btn._metin and "BAŞLAT" in w.baslat_btn._metin, w.baslat_btn._metin
    assert all(yollar().values()), "A3 hazirlikta elle kontrol calismiyor"
    w._otonom_baslat()
    assert w.mod == "Otonom" and "DURDUR" in w.baslat_btn._metin
    assert not any(yollar().values()), "A3 otonomda elle hareket gecti"
    w._otonom_baslat()

    # ACIL DURDUR'dayken BASLAT reddedilir
    w.kontrol.estop(True)
    w._otonom_baslat()
    assert w.mod == w.HAZIRLIK, "E-Stop'ta otonom basladi"
    w.kontrol.estop(False)

    # Asama 1 -> Manuel: hareket surer; manuel ates mod degisince kesilir
    w._asama_sec("Aşama 1")
    assert w.mod == "Manuel"
    assert all(yollar().values()), "Manuel'de elle kontrol calismiyor"
    w._ates_kisayolu()
    assert w.kontrol.mock.lazer is True
    w._asama_sec("Aşama 2")
    assert w.kontrol.mock.lazer is False and not w.fire_btn.isChecked(), \
        "Manuel'de acilan ates hazirliga gecince kesilmedi"


def test_kutu_etiketleri_ust_uste_binmez():
    """25.09 saha: yan yana üç maket + altlarındaki balonlar — etiketler hep kutunun sol
    üstüne yazıldığı için birbirini kapatıyordu. `etiket_yerlestir`: hiçbir etiket başka
    etiketin ve (yer varken) başka bir hedefin kutusunun üstüne binmez, kare dışına taşmaz;
    tek başına duran kutunun etiketi eskisi gibi sol üstte kalır."""
    ew, eh = 84.0, 20.0

    def kesisir(a, b):
        return A._kesisim(a, b) > 0

    def dortgen(yer):
        return (yer[0], yer[1], yer[0] + ew, yer[1] + eh)

    # Ekran goruntusundeki dizilis: bitisik uc maket, her birinin hemen altinda balonu.
    kutular = []
    for x in (600.0, 640.0, 680.0):
        kutular.append((x, 440.0, x + 40.0, 480.0))              # maket
        kutular.append((x + 5.0, 482.0, x + 35.0, 505.0))        # balon
    boy = [(ew, eh)] * len(kutular)
    eski = [dortgen((k[0], k[1] - eh - 2.0)) for k in kutular]
    assert any(kesisir(a, b) for i, a in enumerate(eski) for b in eski[i + 1:]), \
        "senaryo eski yerlesimde bile cakismiyor — test bir sey olcmuyor"
    yer = [dortgen(y) for y in A.etiket_yerlestir(kutular, boy, 1280.0, 720.0)]
    for i, a in enumerate(yer):
        for j, b in enumerate(yer[i + 1:], i + 1):
            assert not kesisir(a, b), f"etiket {i} ile {j} ust uste: {a} {b}"
        for j, k in enumerate(kutular):
            assert j == i or not kesisir(a, k), f"etiket {i} baska hedefin ({j}) kutusunu kapatiyor"
        assert 0 <= a[0] and a[2] <= 1280 and 0 <= a[1] and a[3] <= 720, f"kare disi: {a}"
        k = kutular[i]                           # kendi kutusundan en cok bir etiket boyu uzakta
        uzak = max(k[1] - a[3], a[1] - k[3], k[0] - a[2], a[0] - k[2], 0.0)
        assert uzak <= eh + 2.0 + 2.0, f"etiket {i} kutusundan {uzak:.0f} px uzakta: {a} {k}"

    # Tek kutu: etiket eskisi gibi kutunun sol ustunde (alisilmis gorunum bozulmaz)
    assert A.etiket_yerlestir([(100.0, 200.0, 180.0, 260.0)], [(ew, eh)], 1280, 720) == \
        [(100.0, 200.0 - eh - 2.0)]
    # Karenin tepesindeki kutu: etiket kare disina cikmaz, kutunun altina iner
    (x, y), = A.etiket_yerlestir([(100.0, 0.0, 180.0, 60.0)], [(ew, eh)], 1280, 720)
    assert y >= 0 and not kesisir(dortgen((x, y)), (100.0, 0.0, 180.0, 60.0)), (x, y)
    # Oncelik: ilk etiket (kilitli hedef) en iyi yeri alir
    ilk = A.etiket_yerlestir(kutular[2:4] + kutular[:2], boy[:4], 1280, 720)[0]
    assert ilk == (kutular[2][0], kutular[2][1] - eh - 2.0), ilk


def test_windows_guc_kisitlamasi_kapanir():
    """25.09 saha: AI saniyede ~10 kareye dustu. Windows guc kisitlamasi (EcoQoS) acikken
    ayni dongu 147 ms/kare, kapaliyken 53 ms (olculdu) — pille ve arka planda uygulanir.
    Uygulama acilisinda (main) bu surec icin kapatilir; API cagrisi Windows'ta basarili."""
    import inspect
    import sys
    assert "windows_kisitlamasini_kapat()" in inspect.getsource(A.main), "main kisitlamayi kapatmiyor"
    if sys.platform == "win32":
        assert A.windows_kisitlamasini_kapat() is True, "SetProcessInformation basarisiz"


def test_kontroller_listesi_gercek_tuslarla_ayni():
    """Arayüzdeki "Kontroller" paneli (kontroller.py) ile arayüzün GERÇEKTEN dinlediği
    klavye tuşları aynı olmalı. Bir tuş eklenir/değişir de liste unutulursa operatör
    yanlış tuşu öğrenir — bu test o unutkanlığı kırmızıya düşürür (24.09)."""
    import kontroller as K
    Qt = A.Qt
    dinlenen = (set(A.TUS_YON) | set(A.MainWindow.ATES_TUSLARI) | {A.ESTOP_TUSU}
                | set(A.MainWindow.ZOOM_TUSLARI) | {A.MainWindow.HASSASIYET_TUSU})
    yazili = K.klavye_tuslari()
    assert dinlenen == yazili, (
        f"kontroller.py ile arayuz ayrisiyor — listede eksik: {dinlenen - yazili}, "
        f"listede fazla: {yazili - dinlenen}")

    # Her tuş gerçekten arayüzün kapısında karşılık buluyor (Manuel modda).
    w = SahtePencere()
    w.thread = A.VideoThread(None, None, None)
    estop = []                                   # gercek E-Stop kapi_testleri.py'de denenir
    w._estop_kisayolu = lambda: estop.append(1)
    for tus in yazili:
        assert w._tus_bas(SahteTus(tus)), f"listede var ama arayuz dinlemiyor: {tus}"
        w._tus_birak(SahteTus(tus))
    assert estop, "listedeki Esc acil durdurmayi cagirmadi"
    assert A.ESTOP_TUSU == Qt.Key_Escape and Qt.Key_Backspace not in yazili
    # Backspace artik BOS: arayuz onu yutmamali (sayi kutularinda silme icin lazim)
    assert not w._tus_bas(SahteTus(Qt.Key_Backspace)), "Backspace hala arayuzun tusu"


if __name__ == "__main__":
    test_ekran_aci_kart_hedefi_ayni()
    test_azimut_sarmasiz_gider()
    test_yatay_sinir_yalniz_pencereden_gelir()
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
    test_klavye_atesi_tek_dokunus()
    test_aci_karosu_yasak_alan_dilimleri()
    test_kol_gostergesi_gercek_durumu_yansitir()
    test_gamepad_ayni_kapilardan_gecer()
    test_lazer_gucu_arayuzden_karta_gider()
    test_ates_tazelemesi_kesilirse_lazer_soner()
    test_ates_kapaliyken_tazeleme_gitmez()
    test_basili_tutma_estopta_kesilir()
    test_estopta_r_merkeze_almaz()
    test_merkeze_alma_kademeli_ve_kesilebilir()
    test_lazer_isigi_yalniz_gercek_lazer_acikken_yanar()
    test_dikey_hareket_penceresi_kullanici_ornegi()
    test_yatay_pencere_arkadan_dolanilamaz()
    test_dikey_atis_penceresi_ates_keser()
    test_lazer_gucu_onaysiz_degismez()
    test_odunc_kapilar_gercek_pencerede_de_metot()
    test_kontroller_listesi_gercek_tuslarla_ayni()
    test_windows_guc_kisitlamasi_kapanir()
    test_sag_cubuk_zoom_otonomda_yok()
    test_hassasiyet_tek_dokunus_ve_hiz()
    test_hassasiyet_kisayolu_ve_kutu_kaymasi()
    test_mod_asama_bagi_hazirlikta_elle_kontrol_otonomda_yok()
    test_kutu_etiketleri_ust_uste_binmez()
    print("kapi testleri OK — ekran/kart hedefi, sarmasiz azimut, ates sirasinda yasak "
          "alan, harekete yasak alan, E-Stop, hiz duzeyi, kart disaridan durdurma, "
          "donanim acil stop butonu, ENABLE kesilmez, iki eksen donar, referans korunur, basili tutma, "
          "Space+B/ESC klavye atesi, gamepad, lazer gucu, ates olu adam anahtari")
