# -*- coding: utf-8 -*-
"""Birlesik Affan arayuzu + v1 kontrol katmani regresyon testleri.

Kamera, model ve gercek motor baslatilmaz. Calistir: python app/kapi_testleri.py
Eski arayuzun testleri kapi_testleri_eski_arayuz.py dosyasinda korunur.
"""
import os
import random
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DERINMAVI_ESP"] = "off"
os.environ["DERINMAVI_TILT"] = "off"
os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "derinmavi-yolo-test"))

import algi
import arayuz_qt as A
A.TAKIP_KAYDI = False          # sahte saatli takip kosulari kayit klasorunu doldurmasin
import bolge as B
import hedef_kestirici as HK
import kontrol as kontrol_mod
import protokol as P


class SahteTilt:
    hazir = True
    mock_mu = True
    aci = 0.0


class SahteKontrol:
    def __init__(self):
        self.bagli = True
        self.mock_mu = True
        self.tilt_ayri = True
        self.tilt = SahteTilt()
        self.estop_aktif = False
        self.yorunge_destekli = False
        self.acilis_hizalama = None
        self.pan_hedef = 0.0
        self.tilt_hedef = 0.0
        self.lazer_acik = False
        self.durum = {"lazer": False, "lazer_guc": 40, "durum_ad": "Hazır", "estop": False}

    def aci(self, pan, tilt):
        self.pan_hedef, self.tilt_hedef = pan, tilt
        return self.durum

    def ates(self, ac):
        self.lazer_acik = self.durum["lazer"] = bool(ac)
        return self.durum

    def estop(self, ac, kart_kilidi=True):
        self.estop_aktif = bool(ac)
        self.kart_kilidi = kart_kilidi
        self.ates(False)
        return self.durum

    def tilt_sifirla(self):
        self.sifirlama_sayisi = getattr(self, "sifirlama_sayisi", 0) + 1
        self.tilt_hedef = -30.0
        return True

    def kapat(self):
        pass


def pencere():
    A.InferenceThread.start = lambda self: None
    A.VideoThread.start = lambda self: None
    A.kamera_mod.Kamera.baslat = lambda self: None
    w = A.MainWindow()
    w.kontrol = SahteKontrol()
    w._acilis_sifir_onayi = lambda: True        # modal diyalog testte acilmaz
    return w


def test_hareket_ve_ates(w):
    # 23.09 kullanici karari: GIZLI SINIR YOK. Tilt fiziksel -30..+30 (kol 0..60);
    # yatayin tek siniri arayuzdeki pencere. ACILIS degeri +-90 (operator aracin
    # ARKASINDA durur, namlu on yaridan cikmasin) ama bu bir KOD SINIRI DEGIL:
    # kutular +-180'e kadar yazilir, pencere kapatilirsa sinir hic kalmaz.
    assert w.max_tilt_limit == 30.0
    assert (w.bolge.hareket_pan.alt, w.bolge.hareket_pan.ust) == (-B.PAN_VARSAYILAN,
                                                                  B.PAN_VARSAYILAN)
    assert B.PAN_VARSAYILAN == 90.0
    assert (w.bolge.hareket_tilt.alt, w.bolge.hareket_tilt.ust) == (-30.0, 30.0)
    assert all((spin.minimum(), spin.maximum()) == (-180, 180)
               for spin in w.bolge_spin[("hareket", "pan")])
    assert all((spin.minimum(), spin.maximum()) == (-30, 30)
               for spin in w.bolge_spin[("hareket", "tilt")])
    # Kirpma testleri pencereyi ACIKCA kurar: acilis degeri degisince (90 -> 60 ...)
    # testin anlami degismesin, pencerenin KENDISI sinanmis olsun.
    w.bolge.hareket_pan = B.Pencere(True, -60, 60)
    assert w._aci_hareket(15, -30)
    assert (w.pan_ham, w.tilt_aci) == (15.0, -30.0)
    assert (w.kontrol.pan_hedef, w.kontrol.tilt_hedef) == (15.0, -30.0)
    assert w._aci_hareket(100, -10)
    assert (w.pan_ham, w.tilt_aci) == (60.0, -30.0)            # pan PENCEREDE durur
    assert w._aci_hareket(-60, 60)
    assert (w.pan_ham, w.tilt_aci) == (0.0, 30.0)
    # Pencere kapatilinca yatayda gizli +-60 YOK
    w.bolge.hareket_pan = B.Pencere(False, -60, 60)
    assert w._aci_hareket(90, 0)
    assert w.pan_ham == 90.0, w.pan_ham
    assert w._aci_hareket(-90, 0)
    w.bolge.hareket_pan = B.Pencere(True, -60, 60)

    w.bolge.hareket_tilt = B.Pencere(True, -10, 10)
    assert w._aci_hareket(0, -30)
    assert w.tilt_aci == 0.0
    w.bolge.atis_tilt = B.Pencere(True, -5, 5)
    w.fire_btn.setChecked(True)
    w.kontrol.ates(True)
    assert w._aci_hareket(0, 8)
    assert w.kontrol.durum["lazer"] is False
    assert not w.fire_btn.isChecked()


def test_kart_kilidi_ve_hizalama(w):
    w.kontrol.tilt.hazir = False
    once = w.tilt_aci
    assert not w._aci_hareket(0, -1)
    assert w.tilt_aci == once
    w.kontrol.tilt.hazir = True
    w.kontrol.acilis_hizalama = (12.0, -30.0)
    w._acilis_hizala()
    assert (w.pan_ham, w.tilt_aci) == (12.0, -30.0)
    assert w._acilis_yukselisi_bekliyor
    assert w._aci_hareket(0, 30)
    assert w.tilt_aci == 0.0


def test_acilis_yukselisi_kart_hazir_olana_kadar_bekler(w):
    w._acilis_yukselisi = False
    w._acilis_yukselisi_bekliyor = False
    w.kontrol.tilt.hazir = False
    w.kontrol.acilis_hizalama = (0.0, -30.0)
    w._acilis_hizala()
    w._acilis_yukselisini_dene()
    assert w._acilis_yukselisi_bekliyor
    assert w.kontrol.tilt_hedef == 0.0 and w.tilt_aci == -30.0
    w.kontrol.tilt.hazir = True
    w._acilis_yukselisini_dene()
    assert not w._acilis_yukselisi_bekliyor
    assert w.tilt_aci == w.kontrol.tilt_hedef == 0.0
    assert w.kontrol.sifirlama_sayisi == 1, "acilista tilt sayaci sifirlanmadi (R)"


def test_acilis_onayi_hayir_ise_kol_kipirdamaz(w):
    """23.09 saha: kart kolu 10 derecede saniyordu, kol en alttaydi; yukselis 30 yerine 20
    derece kaldirdi. Operator "kol en altta" demezse kol HIC hareket ettirilmez ve sayac
    sifirlanmaz."""
    w._acilis_yukselisi = False
    w._acilis_yukselisi_bekliyor = False
    w._acilis_sifir_soruldu = False
    w._acilis_sifir_onayi = lambda: False
    w.kontrol.sifirlama_sayisi = 0
    w.kontrol.tilt.hazir = True
    w.kontrol.acilis_hizalama = (0.0, -20.0)
    w._acilis_hizala()
    hedef_once = w.kontrol.tilt_hedef
    w._acilis_yukselisini_dene()
    assert not w._acilis_yukselisi_bekliyor
    assert w.kontrol.sifirlama_sayisi == 0 and w.kontrol.tilt_hedef == hedef_once
    assert w.tilt_aci == -20.0


def test_acilis_sorusu_acil_durdurdan_sonra_gelir(w):
    """24.09 saha: kart onceki oturumdan KILITLI acildi, arayuz E-Stop'a gecti ve bu,
    henuz SORULMAMIS acilis yukselisini iptal etti — 30 derece sorusu hic gelmedi, R gitmedi,
    kart kolu onceki oturumun acisinda sandi. Soru sorulmadiysa DEVAM'dan sonra gelmeli;
    ONAYLANMIS ama yarim kalmis yukselis ise E-Stop'ta iptal (kendiliginden baslamasin)."""
    soru = []
    eski_onay = w._acilis_sifir_onayi
    w._acilis_sifir_onayi = lambda: soru.append(1) or True
    try:
        w._acilis_yukselisi = False
        w._acilis_yukselisi_bekliyor = False
        w._acilis_sifir_soruldu = False
        w.kontrol.sifirlama_sayisi = 0
        w.kontrol.tilt.hazir = True
        w.kontrol.acilis_hizalama = (0.0, -30.0)
        w._acilis_hizala()
        _estop(w, True)                                  # kart kilitli acildi
        w._acilis_yukselisini_dene()
        assert w._acilis_yukselisi_bekliyor, "E-Stop sorulmamis acilis yukselisini iptal etti"
        assert not soru and w.kontrol.sifirlama_sayisi == 0, "E-Stop'ta soru soruldu / R gitti"
        _estop(w, False)                                 # DEVAM ET
        w._acilis_yukselisini_dene()
        assert soru == [1], "DEVAM'dan sonra acilis sorusu gelmedi"
        assert w.kontrol.sifirlama_sayisi == 1 and w.tilt_aci == 0.0
        w._acilis_yukselisi_bekliyor = True              # onaylandi ama hareket yarim kaldi
        _estop(w, True)
        assert not w._acilis_yukselisi_bekliyor, "onaylanmis yukselis E-Stop'tan sonra bekliyor"
        _estop(w, False)
    finally:
        w._acilis_sifir_onayi = eski_onay


def test_tip_secimi(w):
    w.tip_butonlari["drone"].click()
    assert algi.hedef_tipleri() == {"drone"}
    w.tip_butonlari["fuze"].click()
    assert algi.hedef_tipleri() == {"drone", "fuze"}
    w.tip_butonlari["drone"].click()
    w.tip_butonlari["fuze"].click()
    assert algi.hedef_tipleri() is None


def test_kare_arayuze_ulasir(w):
    img = A.QImage(640, 360, A.QImage.Format_RGB888)
    img.fill(0)
    data = {"active": None, "hedefler": [], "dets": [], "balonlar": [],
            "active_idx": -1, "estop": False, "merkezde": False,
            "kirmizi_kaniti": False, "mesaj": "Hedef aranıyor",
            "fps": 0.0, "kamera_fps": 30.0, "a3": False}
    w._kare_geldi(img, data)
    assert w.video.pixmap() is not None


# =====================================================================================
# GUVENLIK KAPILARI — GERCEK Kontrol katmani + sahte kartlar
#
# NEDEN AYRI: yukaridaki testler SahteKontrol kullanir; o nesne komutu yalnizca bir
# degiskene yazar, karta gidip gitmedigini, kartin reddedip etmedigini GOREMEZ.
# Asagidakiler gercek `Kontrol`u sahte ESP (lazer/E-Stop) ve sahte tilt/pan kartiyla
# kurar: "lazer SONDU mu", "karta G GITTI mi" sorulari kartin kendi durumundan okunur.
#
# Bu kapilar eski arayuzde 23 testle korunuyordu; Affan arayuzuyle birlestirmede
# testler kayboldu (davranis dogruydu, 23.09'da tek tek denendi). Gecmiste her biri
# en az bir kez SESSIZCE bozuldu (CLAUDE.md §13.1) — test olmadan yine bozulur.
# =====================================================================================

def gercek_pencere(tek_kart=False):
    """Gercek Kontrol("mock") + sahte tilt/pan karti, SAHTE SAATLE (tekrarlanabilir).

    tek_kart=False: lazer ESKI kartta (sahte S3 lazersiz = eski firmware) — iki kartli yol.
    tek_kart=True : lazer + acil durdurma S3 kartinda (GPIO 18/15) — yarisma duzeni.
    Donanima dokunmaz: kaynaklar acikca "mock" verilir, seri port acilmaz."""
    w = pencere()
    saat = [5000.0]
    k = kontrol_mod.Kontrol("mock", tilt_kaynak="mock")
    k.tilt._saat = lambda: saat[0]
    k.tilt.mock.t = k.tilt.mock.son_canli = saat[0]
    k.tilt.mock.lazer_destek = tek_kart
    w.kontrol = k
    for _ in range(6):                      # kartin ilk STATE3'leri + acilma (E)
        saat[0] += 0.05
        k.oku()
    w._acilis_yukselisi_bekliyor = False    # bu testler acilis yukselisini sinamaz
    w._acilis_hizala()
    w._test_saat = saat
    return w


def _estop(w, basili):
    w.estop_btn.setChecked(basili)
    w._estop_bas()


def _ates_ac(w):
    w.fire_btn.setChecked(True)
    w._ates_bas()


def test_estop_hareketi_keser(w):
    """Yetenek 3: E-Stop'ta hicbir hareket gecmez, ekrandaki aci DEGISMEZ."""
    _estop(w, True)
    p0, t0 = w.pan_ham, w.tilt_aci
    n0 = len(w.kontrol.tilt.mock.kayit)
    assert w._aci_hareket(5.0, 5.0) is False, "E-Stop'ta hareket kapisi ACIK"
    assert (w.pan_ham, w.tilt_aci) == (p0, t0), "E-Stop'ta ekran acisi degisti"
    assert not any(c[:1] in ("G", "P", "Y") and c[:2] not in ("PZ", "PR", "PE")
                   for c in w.kontrol.tilt.mock.kayit[n0:]), "E-Stop'ta karta hareket komutu gitti"
    _estop(w, False)
    assert w._aci_hareket(5.0, 0.0) is True, "DEVAM sonrasi hareket serbest kalmadi"


def test_estop_atesi_keser(w):
    """Yetenek 4: E-Stop lazeri KARTTA keser; E-Stop'tayken ates verilemez."""
    _ates_ac(w)
    assert w.kontrol.mock.lazer is True, "kurulum: lazer acilmadi"
    _estop(w, True)
    assert w.kontrol.mock.lazer is False, "E-Stop lazeri KESMEDI"
    assert not w.fire_btn.isChecked()
    _ates_ac(w)
    assert w.kontrol.mock.lazer is False, "E-Stop'ta ates VERILDI"
    assert not w.fire_btn.isChecked()


def test_donanim_butonu_yazilimdan_kaldirilamaz(w):
    """Fiziksel acil stop basiliyken arayuzden DEVAM ET ise yaramamali; yazilimdan
    gecilebilen E-Stop, E-Stop degildir. Motor ENABLE'i da kesilmemeli (firlama)."""
    _ates_ac(w)
    w.kontrol._kart_yaziyor(w.kontrol.mock.buton_bas(True))
    w._esp_yokla()
    assert w.fire_btn.isChecked() is False, "buton basildi ama ates suruyor"
    assert w.kontrol.mock.lazer is False
    assert w.kontrol.mock.surucu_enerjili is True, "ENABLE kesildi (DEVAM'da firlar)"
    assert w.kontrol.estop_aktif is True
    w.kontrol.estop(False)                               # arayuzden DEVAM ET
    assert w.kontrol.estop_aktif is True, "buton basiliyken yazilimdan DEVAM edildi"
    assert w._aci_hareket(10.0, 0.0) is False, "buton basiliyken hareket gecti"
    w.kontrol.mock.buton_bas(False)                      # buton birakildi
    assert w.kontrol.estop_aktif is True, "buton birakilinca KENDILIGINDEN devam etti"


def test_lazer_olu_adam_anahtari(w):
    """Lazer acikken yoklama karta L1 tazeler; tazeleme kesilirse kart lazeri KENDI
    keser (kablo kopar / laptop coker — "kes" komutu gidemeyebilir)."""
    _ates_ac(w)
    n = len(w.kontrol.mock.kayit)
    w._esp_yokla()
    assert "L1" in w.kontrol.mock.kayit[n:], "yoklama atesi TAZELEMEDI"
    assert w.kontrol.mock.lazer is True, "tazelemeye ragmen lazer sondu"
    w.kontrol.mock.son_ates_t -= P.ATES_ZAMAN_ASIMI_MS / 1000.0 + 0.1
    w.kontrol.mock.islet("")                             # kartin kendi dongusu
    assert w.kontrol.mock.lazer is False, "tazeleme kesildi ama lazer yanik kaldi"


def test_lazer_kapaliyken_tazeleme_gitmez(w):
    """Kapali lazere 250 ms'de bir L1 gitmemeli — kazara ACABILIRDI."""
    n = len(w.kontrol.mock.kayit)
    for _ in range(3):
        w._esp_yokla()
    assert "L1" not in w.kontrol.mock.kayit[n:], "lazer kapaliyken L1 gitti"
    assert w.kontrol.mock.lazer is False


def test_l_kisayolu_estopu_asamaz(w):
    """[L] kisayolu atesin TEK kapisindan gecer; butondan fazla yetkisi yok."""
    _estop(w, True)
    w._ates_kisayolu()
    assert w.kontrol.mock.lazer is False, "[L] kisayolu E-Stop'u asti"


def test_kart_disaridan_durunca_ates_ve_hareket_kesilir(w):
    """Kart kendi durdugunda (seri monitorden STOP) arayuz de E-Stop'a gecmeli."""
    _ates_ac(w)
    w.kontrol._kart_yaziyor(w.kontrol.mock.islet("STOP"))
    w._esp_yokla()
    assert not w.fire_btn.isChecked() and w.kontrol.mock.lazer is False, "kart durdu, ates suruyor"
    assert w._aci_hareket(3.0, 0.0) is False, "kart durdu, hareket gecti"


def _otonom_veri(gorunuyor=True):
    """gorunuyor=False: hedef O KAREDE tespit edilemedi (hayalet kutu)."""
    return {"active": {"tip": "Hedef", "hayalet": not gorunuyor}, "merkezde": True,
            "kirmizi_kaniti": True}


def _dwell_doldu(w):
    w._otonom_hedef_merkezde_t = time.time() - A.OTONOM_DWELL_SURE - 1


def test_otonom_ates_gorunen_hedefe(w):
    """A2/A3 otonom ates: hedef O KAREDE GERCEKTEN gorunuyorsa acilir.

    23.09 kullanici karari: "kirmizi kaniti" sarti KALDIRILDI — isik/boya yuzunden
    renk okunamadiginda sistem hedefi takip bile etmiyordu. Dost korumasi hedef
    SECIMINDE durur (Asama 3'te yalniz "Düşman" secilir), ates kapisinda degil.
    Kapida kalan tek sart: kutu HAYALET olmamali (hayalet kutu kare
    koordinatlarinda DONMUSTUR, namlu oraya bakiyor olmayabilir)."""
    w.mod, w.asama = "Otonom", "Aşama 2"
    w._otonom_ates_aktif = False
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(gorunuyor=False), False)
    assert w.kontrol.mock.lazer is False, "gorunmeyen (hayalet) hedefe OTONOM ATES"
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(), False)
    assert w.kontrol.mock.lazer is True, "hedef goruluyor + dwell doldu ama ates yok"
    w._otonom_ates_kontrol(_otonom_veri(gorunuyor=False), False)
    assert w.kontrol.mock.lazer is False, "hedef kaybolunca ates KESILMEDI"


def test_otonom_ates_estopta_ve_asama1de_yok(w):
    """E-Stop'ta ve Asama 1'de (manuel gorev) otonom ates ASLA acilmaz."""
    w.mod, w.asama = "Otonom", "Aşama 1"
    w._otonom_ates_aktif = False
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(), False)
    assert w.kontrol.mock.lazer is False, "Asama 1'de otonom ates"
    assert not w._otonom_ates_aktif, "Asama 1'de otonom ates KURULDU"
    w.asama = "Aşama 2"
    _estop(w, True)
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(), True)
    # Kart E-Stop'ta L1'i zaten reddeder; arayuzun kendi kapisi da KAPALI kalmali
    # (yalniz karta guvenilmez — eski/farkli firmware'de o katman olmayabilir).
    assert not w._otonom_ates_aktif, "E-Stop'ta otonom ates KURULDU"
    assert w.kontrol.mock.lazer is False, "E-Stop'ta otonom ates"


def test_sahte_lazerde_hedef_vuruldu_sayilmaz(w):
    """Otonom ates suresi dolunca hedef "vuruldu" sayilip 10 sn secilmez — ama YALNIZ
    lazer gercek bir porttaysa. 23.09 saha: lazer sahteydi (DERINMAVI_ESP=mock), her
    kilitten 1.5 sn sonra hedef yasaklandi; "hedefi goruyor ama + cikmiyor" sikayeti."""
    w.mod, w.asama = "Otonom", "Aşama 2"
    cagri = []
    eski = A.algi.hedef_vuruldu
    A.algi.hedef_vuruldu = lambda s, simdi=None: cagri.append(s)

    def ates_turu():
        w._otonom_ates_aktif = False
        _dwell_doldu(w)
        w._otonom_ates_kontrol(_otonom_veri(), False)            # dwell doldu -> ates
        assert w._otonom_ates_aktif, "kurulum: otonom ates baslamadi"
        w._otonom_ates_bitis_t = time.time() - 0.01              # ates suresi doldu
        w._otonom_ates_kontrol(_otonom_veri(), False)
    try:
        assert not w.kontrol.lazer_gercek, "kurulum: test kontrolu sahte olmali"
        ates_turu()
        assert cagri == [], "SAHTE lazerde hedef 'vuruldu' sayildi (10 sn yasak)"
        w.kontrol.__class__ = type("GercekLazerli", (w.kontrol.__class__,),
                                   {"lazer_gercek": property(lambda s: True)})
        ates_turu()
        assert cagri == [A.OTONOM_BEKLEME_SURE], f"gercek lazerde vuruldu sayilmadi: {cagri}"
    finally:
        A.algi.hedef_vuruldu = eski


def test_operator_acisi_karta_kol_acisi_gider(w):
    """Tilt iki cercevelidir: operator -30..+30, kart kolu 0..60. Operator 10
    derece -> karta G40 gitmeli (cevrim tek yerde: tilt_surucu)."""
    saat = w._test_saat
    assert w._aci_hareket(0.0, 10.0 - w.tilt_aci)
    for _ in range(40):
        saat[0] += 0.05
        w.kontrol.oku()
    g = [c for c in w.kontrol.tilt.mock.kayit if c.startswith("G")]
    assert g, "tilt kartina G gitmedi"
    assert abs(float(g[-1][1:]) - 40.0) < 0.05, f"operator 10 -> kol 40 beklenirdi: {g[-1]}"
    assert abs(w.kontrol.tilt_olculen - 10.0) < 0.2, w.kontrol.tilt_olculen


def _pan_komutlari(k, n0):
    """Tilt kartina giden MUTLAK pan konum komutlari (P<derece>), n0'dan sonra."""
    return [float(c[1:]) for c in k.tilt.mock.kayit[n0:]
            if c.startswith("P") and c[:2] not in ("PZ", "PR", "PE", "PY")]


def _kart_bekle(w, sn):
    saat = w._test_saat
    for _ in range(int(sn / 0.05)):
        saat[0] += 0.05
        w.kontrol.oku()


def test_estop_pan_acisini_kaybetmez(w):
    """23.09 saha: pan tilt kartindayken E-Stop ekrani ESKI kartin "Konum P0.00"
    satirina cekiyordu (orada pan motoru yok, hep 0). Pan 28.4 derecedeydi; DEVAM
    sonrasi ilk manuel tus namluyu 28 -> 1 dereceye savurdu."""
    k = w.kontrol
    assert k.pan_ayri, "kurulum: pan tilt kartinda degil"
    assert w._aci_hareket(20.0 - w.pan_ham, 0.0)
    _kart_bekle(w, 3.0)
    assert abs(k.pan_olculen - 20.0) < 0.3, k.pan_olculen
    _estop(w, True)
    assert abs(w.pan_ham - 20.0) < 0.3, f"E-Stop ekrani pan'i {w.pan_ham} yapti (gercek 20)"
    _estop(w, False)
    n0 = len(k.tilt.mock.kayit)
    assert w._aci_hareket(1.0, 0.0)
    p = _pan_komutlari(k, n0)
    assert p and abs(p[-1] - 21.0) < 0.3, f"DEVAM sonrasi +1 derece -> {p} (21 beklenirdi)"


def test_otonomdan_manuele_gecis_olculen_konumdan_devam_eder(w):
    """Otonomun son KOMUT hedefi gercek konumdan ayrisabilir (motor yolda). Manuele
    gecince ilk tus olculen konumdan hesaplanmali; yoksa namlu farki bir anda kapatir."""
    k = w.kontrol
    assert w._aci_hareket(15.0 - w.pan_ham, 0.0)
    _kart_bekle(w, 3.0)
    w._mod_sec("Otonom")
    w.pan_ham = w.pan_aci = 27.0          # otonomun son komutu; kart 15'te (yetismedi)
    k.pan_hedef = 27.0
    w._mod_sec("Manuel")
    assert abs(w.pan_ham - 15.0) < 0.3, f"manuele geciste ekran {w.pan_ham} (gercek 15)"
    n0 = len(k.tilt.mock.kayit)
    assert w._aci_hareket(1.0, 0.0)
    p = _pan_komutlari(k, n0)
    assert p and abs(p[-1] - 16.0) < 0.3, f"ilk manuel tus -> {p} (16 beklenirdi)"


def test_otonomda_takip_ivmesi_yumusak(w):
    """24.09 saha: "balonu sert takip ediyor" — namlu salinan balona kademenin tam ivmesiyle
    (400/500 der/sn^2) firliyordu. Otonomda iki eksenin ivmesi tavanli, tepe hiz ayni;
    manuele donunce kademenin kendi ivmesi (manuel his degismez)."""
    import tilt_surucu as TS
    k = w.kontrol
    _kart_bekle(w, 0.3)
    dpd = k.tilt.darbe_per_derece
    tavan_h, tavan_iv = TS.HIZ_TABLO[k.tilt.hiz_seviye]
    pan_iv = TS.PAN_HIZ_TABLO[k.tilt.hiz_seviye][1]
    assert tavan_iv > TS.TAKIP_IVME and pan_iv > TS.PAN_TAKIP_IVME, "kurulum: kademe ivmesi dusuk"

    def son_pz_ivme():
        return float([c for c in k.tilt.mock.kayit if c.startswith("PZ")][-1][2:].split(",")[1])
    w._mod_sec("Otonom")
    _kart_bekle(w, 0.3)
    assert abs(k.tilt.mock.ivme - round(TS.TAKIP_IVME * dpd, 1)) < 0.2, \
        f"otonomda tilt ivmesi {k.tilt.mock.ivme / dpd:.0f} der/sn2"
    assert abs(k.tilt.mock.maks_hiz - round(tavan_h * dpd, 1)) < 0.2, "otonomda tepe hiz dustu"
    assert abs(son_pz_ivme() - round(TS.PAN_TAKIP_IVME * TS.PAN_DARBE_DER, 1)) < 0.2, \
        f"otonomda pan ivmesi {son_pz_ivme() / TS.PAN_DARBE_DER:.0f} der/sn2"
    w._mod_sec("Manuel")
    _kart_bekle(w, 0.3)
    assert abs(k.tilt.mock.ivme - round(tavan_iv * dpd, 1)) < 0.2, "manuelde ivme geri donmedi"
    assert abs(son_pz_ivme() - round(pan_iv * TS.PAN_DARBE_DER, 1)) < 0.2


def test_yakin_balonda_takip_boya_gore_yumusar(w):
    """24.09 saha: uzakta akici takip yakinda (buyuk balon) titriyordu. Takipciler
    HK.SAHA_AYARI ile kurulur; BALON kutusunun boyu (1280 px'e gore) filtreye gider ve
    buyuk balonda esikler boyla olceklenir. Arac kutusu olcek degistirmez."""
    import hedef_kestirici as HK_
    for e in (w._pan_takip, w._tilt_takip):
        assert e.olcek_ref_px == HK_.SAHA_AYARI["olcek_ref_px"], "takipci saha ayariyla kurulmadi"
        assert e.kayip_dur_s == HK_.SAHA_AYARI["kayip_dur_s"] and e.kayipta_tut
    w._mod_sec("Otonom")
    saat = w._test_saat

    def olc(kaynak, box, gen=1280):
        saat[0] += 1 / 17.0
        w.kontrol.oku()
        w._takip_olcum_geldi({"var": True, "t": saat[0], "ex": 0.0, "ey": 0.0, "olu_x": 7.0,
                              "olu_y": 7.0, "w": gen, "id": "B1", "kaynak": kaynak, "box": box})
    olc("model", (600, 300, 700, 400))                      # 100 px ARAC kutusu
    assert w._pan_takip._s == 1.0 and w._tilt_takip._s == 1.0, "arac kutusu takibi olcekledi"
    olc("balon_pencere", (600, 300, 696, 396))              # 96 px balon: s = 96/24
    assert w._pan_takip._s == 4.0 and w._tilt_takip._s == 4.0, (w._pan_takip._s, w._tilt_takip._s)
    olc("balon_tam", (300, 150, 324, 174), gen=640)         # 640 genislikte 24 px = 1280'de 48
    assert w._pan_takip._s == 2.0, w._pan_takip._s


def test_kilit_baska_nesneye_gecince_takip_sifirlanir(w):
    """Kilitli hedefin kimligi degisirse iki eksenin hedef kestirimi sifirdan kurulur;
    ayni kimlikte (normal takip) sifirlanmaz. 23.09 kaydi: kimliksiz bir kutu 213 px
    otede kilide girdi, eski hedefin gecmisiyle birlesti, pan'a 62 der/sn komut gitti."""
    w._mod_sec("Otonom")
    sayac = {"pan": 0, "tilt": 0}
    w._pan_takip.hedef_degisti = lambda: sayac.__setitem__("pan", sayac["pan"] + 1)
    w._tilt_takip.hedef_degisti = lambda: sayac.__setitem__("tilt", sayac["tilt"] + 1)
    saat = w._test_saat

    def olc(hid, ex):
        saat[0] += 1 / 30.0
        w.kontrol.oku()
        w._takip_olcum_geldi({"var": True, "t": saat[0], "ex": ex, "ey": 0.0, "olu_x": 7.0,
                              "olu_y": 7.0, "w": 1280, "id": hid})
    for _ in range(5):
        olc(1, 10.0)
    assert sayac == {"pan": 0, "tilt": 0}, f"ayni hedefte takip sifirlandi: {sayac}"
    olc(None, 213.0)
    assert sayac == {"pan": 1, "tilt": 1}, f"kilit baska nesneye gecti, sifirlanmadi: {sayac}"


# ---- BALON TAKIBI (balon_takip.py): kilit + nisan balonda, arac kimlik kaniti ----
def _balon_veri(**ek):
    aktif = {"tip": "Hedef", "hayalet": False, "balon": True}
    aktif.update(ek)
    return {"active": aktif, "merkezde": True, "kirmizi_kaniti": False}


def test_balon_atesi_imha_dogrulamasina_bildirilir(w):
    """Balona ates: baslangic ve bitis balon_takip'e bildirilir (patlayan balon kaybolunca
    imha sayilsin, patlamayana AZAMI_ATES tur sonra birakilsin). Arac yolundaki 10 sn
    "vuruldu" yasagi balonda KULLANILMAZ: balon patlamadiysa tekrar ates edilmeli."""
    import balon_takip
    w.mod, w.asama = "Otonom", "Aşama 2"
    cagri = []
    eski = (balon_takip.ates_basladi, balon_takip.ates_tamamlandi, A.algi.hedef_vuruldu,
            balon_takip.ates_bitti)
    # 24.09 saha: tur suresi balon_takip'e gider (lazer altinda onlemleri o sure boyunca),
    # kesis (_ates_kes) bildirilir. Sure 1 sn'de %55 guc balonu patlatmadi -> 2 sn.
    assert A.OTONOM_ATES_SURE >= 2.0, A.OTONOM_ATES_SURE
    balon_takip.ates_basladi = lambda g, simdi=None, sure=None: cagri.append(("basladi", g, sure))
    balon_takip.ates_tamamlandi = lambda g, simdi=None: cagri.append(("tamam", g))
    balon_takip.ates_bitti = lambda simdi=None: cagri.append(("bitti",))
    A.algi.hedef_vuruldu = lambda s, simdi=None: cagri.append(("vuruldu", s))
    S = A.OTONOM_ATES_SURE

    def ates_turu():
        w._otonom_ates_aktif = False
        _dwell_doldu(w)
        w._otonom_ates_kontrol(_balon_veri(), False)
        assert w._otonom_ates_aktif, "kurulum: balona otonom ates baslamadi"
        w._otonom_ates_bitis_t = time.time() - 0.01
        w._otonom_ates_kontrol(_balon_veri(), False)
    try:
        ates_turu()
        assert [c for c in cagri if c != ("bitti",)] == [("basladi", False, S), ("tamam", False)], cagri
        cagri.clear()
        w.kontrol.__class__ = type("GercekLazerli", (w.kontrol.__class__,),
                                   {"lazer_gercek": property(lambda s: True)})
        ates_turu()
        assert [c for c in cagri if c != ("bitti",)] == [("basladi", True, S), ("tamam", True)], \
            f"gercek lazerde balon atesi bildirilmedi / arac yasagi kullanildi: {cagri}"
        assert ("bitti",) in cagri[cagri.index(("basladi", True, S)):], \
            f"ates kesildi, balon_takip'e bildirilmedi (lazer altinda onlemleri surer): {cagri}"
    finally:
        (balon_takip.ates_basladi, balon_takip.ates_tamamlandi, A.algi.hedef_vuruldu,
         balon_takip.ates_bitti) = eski


def test_dost_onundeyken_otonom_ates_acilmaz(w):
    """A3: balon_takip lazerin yolunda dost gorurse (engel) dwell dolsa da ates ACILMAZ;
    ates surerken engel belirirse ates KESILIR. Dost vurmak -10 puan."""
    w.mod, w.asama = "Otonom", "Aşama 3"
    w._otonom_ates_aktif = False
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_balon_veri(tip="Düşman", engel="Dost araç balonun önünde"), False)
    assert w.kontrol.mock.lazer is False and not w._otonom_ates_aktif, "dost onundeyken ATES"
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_balon_veri(tip="Düşman"), False)
    assert w.kontrol.mock.lazer is True, "kurulum: engelsiz balona ates acilmadi"
    w._otonom_ates_kontrol(_balon_veri(tip="Düşman", engel="Dost balon çizgide"), False)
    assert w.kontrol.mock.lazer is False, "ates surerken dost cizgiye girdi, ates KESILMEDI"


def test_balon_atesi_lazer_altinda_suruyor(w):
    """ATES TAAHHUDU (24.09 saha): lazer noktasi balona degince model balonu tanimiyor —
    21:27 kaydinda uzak balona 37 atisin 37'si ~0.2 sn'de "hedef gorunmuyor" diye kesildi,
    balon hic isinmadi. Balona BASLAMIS ates, AYNI balon kilitli kaldikca OTONOM_ATES_SURE
    boyunca hayalette de surer; takip o surede kaybi "hedef gitti" saymaz (korluk).
    Kesenler aynen keser: dost engeli (hayalette de), kilidin dusmesi, kilidin baska
    balona gecmesi, E-Stop. Hayalette ates BASLAMAZ; arac hedefinde hayalet yine keser."""
    import balon_takip
    w.mod, w.asama = "Otonom", "Aşama 2"
    # Sahte lazerde nokta yok -> model kor olmaz: kayip gercek kayiptir, takip korlugu ACILMAZ.
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_balon_veri(id="B1"), False)
    assert w.kontrol.mock.lazer is True, "kurulum: sahte lazerde ates acilmadi"
    assert w._pan_takip.kor_bitis is None and w._tilt_takip.kor_bitis is None, \
        "sahte lazerde takip korlugu acildi"
    w._ates_kes("kurulum")
    w.kontrol.__class__ = type("GercekLazerli", (w.kontrol.__class__,),
                               {"lazer_gercek": property(lambda s: True)})
    eski = (balon_takip.ates_basladi, balon_takip.ates_tamamlandi, balon_takip.ates_bitti)
    cagri = []
    balon_takip.ates_basladi = lambda g, simdi=None, sure=None: cagri.append("basladi")
    balon_takip.ates_tamamlandi = lambda g, simdi=None: cagri.append("tamam")
    balon_takip.ates_bitti = lambda simdi=None: cagri.append("bitti")
    pay = balon_takip.LAZER_GECIKME_S + balon_takip.KAYIP_S
    takip = (w._pan_takip, w._tilt_takip)

    def baslat(bid="B1"):
        w._otonom_ates_aktif = False
        _dwell_doldu(w)
        w._otonom_ates_kontrol(_balon_veri(id=bid), False)
        assert w.kontrol.mock.lazer is True and w._otonom_ates_aktif, "kurulum: balona ates acilmadi"

    try:
        w._otonom_ates_aktif = False
        _dwell_doldu(w)
        w._otonom_ates_kontrol(_balon_veri(id="B1", hayalet=True), False)
        assert w.kontrol.mock.lazer is False, "gorunmeyen balona ates BASLADI"
        baslat()
        assert all(e.kor_bitis is not None and e.kor_bitis >= w._otonom_ates_bitis_t + pay - 0.01
                   for e in takip), "takip lazer korlugunden haberdar degil (kayipta namlu durur)"
        for _ in range(5):
            w._otonom_ates_kontrol(_balon_veri(id="B1", hayalet=True), False)
        assert w.kontrol.mock.lazer is True and w._otonom_ates_aktif, \
            "lazer altinda gorunmeyen balona ates KESILDI (21:27: 37/37 atis 0.2 sn)"
        w._otonom_ates_bitis_t = time.time() - 0.01                 # tur doldu, balon hala kor
        w._otonom_ates_kontrol(_balon_veri(id="B1", hayalet=True), False)
        assert w.kontrol.mock.lazer is False and "tamam" in cagri, f"tur bitmedi: {cagri}"
        assert all(e.kor_bitis <= time.time() + pay + 0.05 for e in takip), \
            "ates bitti, takip korlugu kisalmadi"
        baslat()
        w._otonom_ates_kontrol(_balon_veri(id="B1", hayalet=True, engel="Dost balon çizgide"), False)
        assert w.kontrol.mock.lazer is False, "hayalette dost cizgiye girdi, ates KESILMEDI"
        baslat()
        w._otonom_ates_kontrol(_balon_veri(id="B2"), False)
        assert w.kontrol.mock.lazer is False, "kilit baska balona gecti, lazer yanarken namlu donecekti"
        baslat()
        w._otonom_ates_kontrol({"active": None, "merkezde": False}, False)
        assert w.kontrol.mock.lazer is False, "kilit dustu (A3 karti), ates KESILMEDI"
        baslat()
        w._otonom_ates_kontrol(_balon_veri(id="B1", hayalet=True), True)
        assert w.kontrol.mock.lazer is False, "E-Stop lazer altindaki balon atesini KESMEDI"
        w._otonom_ates_aktif = False
        _dwell_doldu(w)
        w._otonom_ates_kontrol({"active": {"tip": "Hedef", "hayalet": False, "id": 7},
                                "merkezde": True}, False)
        assert w.kontrol.mock.lazer is True, "kurulum: arac hedefine ates acilmadi"
        w._otonom_ates_kontrol({"active": {"tip": "Hedef", "hayalet": True, "id": 7},
                                "merkezde": True}, False)
        assert w.kontrol.mock.lazer is False, "ARAC hedefi kayboldu, ates KESILMEDI (taahhut yalniz balonda)"
    finally:
        balon_takip.ates_basladi, balon_takip.ates_tamamlandi, balon_takip.ates_bitti = eski


def test_panel_aktif_hedefi_hayalet_ve_balon_bilgisi_tasir():
    """Ates kapisinin okudugu `active` sozlugu hayalet/balon/engel bilgisini TASIMALI.
    Eskiden yalniz ad/tip/conf/box yaziliyordu: "gorunmeyen hedefe ates etme" kapisi
    testte calisiyor, canli uygulamada hic tetiklenmiyordu."""
    v = A.VideoThread(None, A.OrtakVeri(), None)
    v.asama = 3
    det = {"cls": "balon", "ad": "Balon", "tip": "Düşman", "conf": 90, "box": (1, 2, 3, 4),
           "id": "B1", "balon": True, "hayalet": True, "engel": "Dost balon çizgide"}
    aktif = v._panel_verisi([det], 0, 30.0)["active"]
    assert aktif["hayalet"] is True and aktif["balon"] is True, aktif
    # kimlik: ates taahhudu yalniz AYNI balonda surer (kilit baska balona gecerse kesilir)
    assert aktif["id"] == "B1", aktif
    assert aktif["engel"] == "Dost balon çizgide", aktif


def test_balon_modunda_kilit_ve_nisan_balonda():
    """Balon modeli yukluyken A2/A3'te kilit BALONA kurulur, arac yolu kilit KURMAZ
    (yalniz tespit + kimlik). "balon_takip" kapatilinca eski arac kilidine donulur."""
    import numpy as np
    import cv2
    import balon_takip

    class Kutu:
        def __init__(self, box, conf=0.95, tid=None):
            self.cls, self.conf = 0, conf
            self.id = type("I", (), {"item": lambda s, v=tid: v})() if tid else None
            self.xyxy = [type("X", (), {"tolist": lambda s, b=box: list(b)})()]

    class Sonuc:
        def __init__(self, kutular, adlar):
            self.boxes, self.names = kutular, adlar

    class AracModeli:
        def track(self, frame, **kw):
            return [Sonuc([Kutu((600, 300, 680, 360), tid=1)], {0: "f16"})]

    class BalonModeli:
        def predict(self, girdiler, **kw):
            cikti = []
            for img in girdiler:
                n, _, ist, _ = cv2.connectedComponentsWithStats(
                    cv2.inRange(img, (0, 0, 255), (0, 0, 255)), 8)
                cikti.append(Sonuc([Kutu((x, y, x + w, y + h), 0.9) for x, y, w, h, _ in ist[1:]],
                                   {0: "red-balloon"}))
            return cikti

    kare = np.full((720, 1280, 3), 128, np.uint8)
    kare[300:360, 600:680] = (10, 10, 245)                        # kirmizi arac
    cv2.circle(kare, (640, 400), 20, (0, 0, 255), -1)             # altinda balon
    th = A.InferenceThread(A.OrtakVeri())
    th.model, th.balon_modelleri, th.asama = AracModeli(), [BalonModeli()], 2
    algi.takip_sifirla()
    balon_takip.sifirla()
    algi.ayar_guncelle(zor_ornek=0)          # sentetik kare veri_toplama/'ya yazilmasin
    try:
        for _ in range(6):
            dets, _b, aktif = th._algila(kare)
        assert aktif >= 0 and dets[aktif].get("balon"), ("kilit balonda degil", dets, aktif)
        assert algi.kilitli_hedef() is None, "balon modunda arac kilidi de kuruldu"
        hx, hy = algi.det_nisan_noktasi(dets[aktif])
        assert abs(hx - 640) <= 1 and abs(hy - 400) <= 1, (hx, hy)
        algi.ayar_guncelle(balon_takip=0)
        for _ in range(6):
            dets, _b, aktif = th._algila(kare)
        assert aktif >= 0 and not dets[aktif].get("balon") and algi.kilitli_hedef() == 1, \
            ("balon takibi kapaliyken arac kilidine donulmedi", dets, aktif)
        assert not any(d.get("balon") for d in dets), "balon takibi kapaliyken balon tarandi"
    finally:
        algi.ayar_guncelle(balon_takip=algi.VARSAYILAN_AYAR["balon_takip"],
                           zor_ornek=algi.VARSAYILAN_AYAR["zor_ornek"])
        algi.takip_sifirla()
        balon_takip.sifirla()



# ---- TEK KART (24.09): lazer GPIO 18 + acil buton GPIO 15 ESP32-S3'te ----
def _tek_pencere():
    w = gercek_pencere(tek_kart=True)
    assert w.kontrol.lazer_tek_kart, "kurulum: lazer S3'e yonlenmedi"
    return w


def _yokla(w, sn=0.05):
    w._test_saat[0] += sn
    w._esp_yokla()


def test_tek_kart_lazer_ve_olu_adam_anahtari():
    """Tek kartta ates S3'e gider (eski karta DEGIL), arayuz yoklamasi L1'i tazeler;
    arayuz donarsa kart lazeri 1 sn'de KENDI keser ve arayuz bunu gorup ATES'i birakir."""
    w = _tek_pencere()
    try:
        k, m = w.kontrol, w.kontrol.tilt.mock
        assert not k.lazer_gercek, "sahte S3 'gercek lazer' sayildi"
        _ates_ac(w)
        assert m.lazer_acik and not k.mock.lazer, "ates S3'e degil eski karta gitti"
        n = len(m.kayit)
        for _ in range(12):
            _yokla(w, 0.25)                                  # 3 sn, arayuz calisiyor
        assert m.kayit[n:].count("L1") >= 10 and m.lazer_acik, "tazelemeye ragmen lazer sondu"
        for _ in range(12):                                  # arayuz dondu: nabiz var, L1 yok
            w._test_saat[0] += 0.1
            k.tilt.yokla()
        assert not m.lazer_acik, "L1 tazelemesi kesildi ama S3 lazeri yakmaya devam etti"
        _yokla(w)
        assert not m.lazer_acik, "arayuz geri gelince lazer KENDILIGINDEN yeniden yandi"
        assert not w.fire_btn.isChecked(), "kart lazeri kesti, ATES butonu yanik gorunuyor"
        n = len(m.kayit)
        for _ in range(4):
            _yokla(w, 0.25)
        assert "L1" not in m.kayit[n:], "lazer kapaliyken S3'e L1 gitti"
        _ates_ac(w)
        w._ates_kes("test")
        assert not m.lazer_acik and "L0" in m.kayit, "ates kesilince S3 lazeri sonmedi"
    finally:
        w.close()


def test_tek_kart_acil_durdurma():
    """Arayuzden E-Stop: S3 lazeri keser ve KILITLENIR (hareket ve L1 reddedilir). Arayuzun
    otomatik yeniden acmasi (E) kilidi KALDIRAMAZ; yalniz DEVAM ET kaldirir."""
    w = _tek_pencere()
    try:
        k, m = w.kontrol, w.kontrol.tilt.mock
        _ates_ac(w)
        assert m.lazer_acik
        w.estop_btn.setChecked(True)
        w._estop_bas()
        assert m.acil and not m.lazer_acik and "STOP" in m.kayit, "E-Stop S3'te kilitlemedi"
        assert m.islet("G40", w._test_saat[0]) == "ERR,G40,ESTOP", "kilitli kart hareket kabul etti"
        assert m.islet("L1", w._test_saat[0]) == "ERR,L1,ESTOP", "kilitli kart ates kabul etti"
        m.acik = False                                       # kart kilitlendi -> arayuz E yollar
        for _ in range(8):
            _yokla(w, 0.2)
        assert m.acil and w.estop_btn.isChecked(), "otomatik yeniden acma acil kilidi kaldirdi"
        w.estop_btn.setChecked(False)
        w._estop_bas()                                       # DEVAM ET
        for _ in range(3):
            _yokla(w, 0.2)
        assert not m.acil and not k.estop_aktif and not w.estop_btn.isChecked(), "DEVAM calismadi"
        _ates_ac(w)
        assert m.lazer_acik, "DEVAM'dan sonra ates acilamadi"
        # Kart BASKA yoldan kilitlendi (seri monitorden STOP) ve metin satiri kacti:
        # surekli yayin (LZR1) arayuzu yine E-Stop'a gecirmeli.
        m.acil, m.lazer_acik = True, False
        for _ in range(3):
            _yokla(w, 0.2)
        assert k.estop_aktif and w.estop_btn.isChecked() and not w.fire_btn.isChecked(), \
            "kart kilitli yayinliyor ama arayuz E-Stop'a gecmedi"
    finally:
        w.close()


def test_tek_kart_donanim_butonu():
    """S3'e bagli fiziksel acil stop: basinca arayuz E-Stop'a gecer ve ates kesilir;
    basiliyken DEVAM ET ise yaramaz; birakilinca KENDILIGINDEN devam etmez."""
    w = _tek_pencere()
    try:
        k, m = w.kontrol, w.kontrol.tilt.mock
        _ates_ac(w)
        m.buton_bas(True)
        _yokla(w)
        assert w.estop_btn.isChecked() and not w.fire_btn.isChecked() and not m.lazer_acik, \
            "S3 butonuna basildi ama arayuz E-Stop'a gecmedi"
        assert w._aci_hareket(10.0, 0.0) is False, "buton basiliyken hareket gecti"
        w.estop_btn.setChecked(False)
        w._estop_bas()                                       # DEVAM ET (buton hala basili)
        for _ in range(3):
            _yokla(w, 0.2)
        assert m.acil and k.estop_aktif and w.estop_btn.isChecked(), \
            "buton basiliyken yazilimdan DEVAM edildi"
        m.buton_bas(False)
        for _ in range(3):
            _yokla(w, 0.2)
        assert m.acil and w.estop_btn.isChecked(), "buton birakilinca KENDILIGINDEN devam etti"
        w.estop_btn.setChecked(False)
        w._estop_bas()
        for _ in range(3):
            _yokla(w, 0.2)
        assert not m.acil and not w.estop_btn.isChecked(), "buton birakildiktan sonra DEVAM calismadi"
    finally:
        w.close()


def test_tek_kart_otonom_ates_ve_gercek_lazer():
    """Otonom ates tek kartta S3 lazerine ulasir; S3 gercek portta ise lazer "gercek"
    sayilir (balon imhasi ancak o zaman sayilir)."""
    w = _tek_pencere()
    try:
        k, m = w.kontrol, w.kontrol.tilt.mock
        w.mod, w.asama = "Otonom", "Aşama 2"
        w._otonom_ates_aktif = False
        _dwell_doldu(w)
        w._otonom_ates_kontrol(_otonom_veri(), False)
        assert m.lazer_acik and not k.mock.lazer, "otonom ates S3 lazerine gitmedi"
        k.tilt.__class__ = type("GercekS3", (k.tilt.__class__,),
                                {"mock_mu": property(lambda s: False)})
        assert k.lazer_gercek, "gercek S3 lazeri 'sahte' sayildi (imha hic sayilmazdi)"
    finally:
        w.close()


def test_klavye_ve_kol_acil_durdurur_tekrar_basinca_devam():
    """[Esc] ve kolda [Options/Start] ACIL DURDUR AC/KAPA (24.09 kullanici karari): ilk
    basis kurar, tekrar basis DEVAM ettirir — ama kurulduktan ESTOP_KISAYOL_BEKLEME_S
    dolmadan DEGIL (22.09'da kol ikinci basista aninda kaldiriyordu: panikte cift basis).
    Klavyenin otomatik tekrari ve kolda basili tutmak sayilmaz; donanim butonu basiliyken
    kisayol devam ettiremez; devam atesi yeniden ACMAZ. Daire/B acil durdur DEGILDIR."""
    import gamepad as G
    from PySide6.QtGui import QKeyEvent
    w = _tek_pencere()
    try:
        m = w.kontrol.tilt.mock
        bekleme = w.ESTOP_KISAYOL_BEKLEME_S
        assert bekleme >= 0.5, "kisayolla devam beklemesi kaldirildi / cok kisa"

        def esc(tekrar=False):
            return w._tus_bas(QKeyEvent(A.QEvent.KeyPress, A.Qt.Key_Escape, A.Qt.NoModifier,
                                        "", tekrar))

        def gecir():                           # kurulmadan bu yana bekleme doldu
            w._estop_kurulma_t -= bekleme + 0.1

        def yokla3():
            for _ in range(3):
                _yokla(w, 0.2)

        _ates_ac(w)
        assert esc()
        assert w.estop_btn.isChecked() and m.acil and not m.lazer_acik, "Esc acil durdurmadi"
        assert esc() and w.estop_btn.isChecked(), "bekleme dolmadan ikinci Esc DEVAM ettirdi"
        gecir()
        assert esc(tekrar=True) and w.estop_btn.isChecked(), \
            "basili tutulan Esc (otomatik tekrar) DEVAM ettirdi"
        assert esc()
        yokla3()
        assert not w.estop_btn.isChecked() and not m.acil, "tekrar Esc DEVAM ettirmedi"
        assert not w.fire_btn.isChecked() and not m.lazer_acik, "DEVAM atesi yeniden acti"

        # Donanim butonu basiliyken kisayol devam ettiremez (DEVAM ET butonuyla ayni kapi).
        m.buton_bas(True)
        _yokla(w)
        assert w.estop_btn.isChecked(), "kurulum: donanim butonu E-Stop kurmadi"
        gecir()
        esc()
        yokla3()
        assert m.acil and w.estop_btn.isChecked(), "donanim butonu basiliyken Esc DEVAM ettirdi"
        m.buton_bas(False)
        yokla3()
        assert m.acil and w.estop_btn.isChecked(), "buton birakilinca KENDILIGINDEN devam etti"
        gecir()
        esc()
        yokla3()
        assert not m.acil and not w.estop_btn.isChecked(), "buton birakildiktan sonra Esc DEVAM etmedi"

        class SahteKol:
            bagli, ad = True, "test"

            def __init__(self):
                self.d = G.Durum()

            def oku(self):
                return self.d

            def kapat(self):
                pass
        kol = SahteKol()
        w.gamepad = kol

        def kol_bas(tus, kenar=True):
            kol.d = G.Durum()
            kol.d.basili, kol.d.kenar = {tus}, ({tus} if kenar else set())
            w._gamepad_tik()

        kol_bas("daire")
        assert not w.estop_btn.isChecked(), "Daire hala acil durduruyor"
        kol_bas("start")
        assert w.estop_btn.isChecked() and m.acil, "kolda Options acil durdurmadi"
        kol_bas("start")
        assert w.estop_btn.isChecked(), "bekleme dolmadan ikinci Options DEVAM ettirdi"
        gecir()
        kol_bas("start", kenar=False)
        assert w.estop_btn.isChecked(), "Options'i basili tutmak DEVAM ettirdi"
        kol_bas("start")
        yokla3()
        assert not w.estop_btn.isChecked() and not m.acil, "tekrar Options DEVAM ettirmedi"
    finally:
        w.close()

# ---- SUREKLI TAKIP: sahte saatle, gercek Kontrol + sahte pan/tilt karti ----
class _SahteZaman:
    """arayuz_qt'nin `time` modulunun yerine: takip dongusu sahte saati gorur."""
    simdi = [10000.0]

    @classmethod
    def time(cls):
        return cls.simdi[0]

    perf_counter = monotonic = time

    @staticmethod
    def strftime(*a, **k):
        return time.strftime(*a, **k)

    @staticmethod
    def sleep(_):
        pass


def _takip_kos(yorunge, hedef_pan=10.0, hedef_tilt=-5.0, sure=5.0, pan_hiz=0.0, tohum=3,
               bosluk=None, tilt_pencere=None):
    """Dunyada duran (ya da pan'da kayan) hedefe otonom takip. Doner: ozet sozluk.

    ⚠ Aci secimi keyfi degil: kameranin derece basina donusu kol acisina gore degisir
    (tilt_surucu.KAMERA_PPD_TABLO). Ust uclarda 7 px'lik olu bolge ~1.3 dereceye
    karsilik gelir; test orta bolgede (ppd ~13) yapilir."""
    saat = _SahteZaman.simdi
    gercek = A.time
    A.time = _SahteZaman
    w = None
    try:
        w = pencere()
        k = kontrol_mod.Kontrol("off", tilt_kaynak="mock")
        k.tilt._saat = lambda: saat[0]
        k.tilt.mock.t = k.tilt.mock.son_canli = saat[0]
        if not yorunge:
            k.tilt.mock.yorunge_destek = False      # eski firmware: konum kipi
        w.kontrol = k
        # Arayuzle AYNI kurulum (arayuz_qt.MainWindow): bosluk ayardan gelir. Eskiden
        # sinif varsayilani (1.5) kullaniliyordu — arayuzden iki kat sert bir bosluk
        # varsayimi; test gercek kurulumu olcmuyordu.
        b = algi.AYAR.get("takip_bosluk", 0.8) if bosluk is None else bosluk
        w._pan_takip = HK.EksenTakip(isaret=+1.0, bosluk=b, **HK.SAHA_AYARI)
        w._tilt_takip = HK.EksenTakip(isaret=-1.0, bosluk=b, **HK.SAHA_AYARI)
        w._nisan_mesgul_ta = 0.0
        for _ in range(6):
            saat[0] += 0.05
            k.oku()
        w._acilis_yukselisi_bekliyor = False
        w._acilis_hizala()
        if tilt_pencere is not None:
            w.bolge.hareket_tilt = B.Pencere(True, *tilt_pencere)
        assert w._aci_hareket(0.0, -18.0 - w.tilt_aci)     # baslangic: operator -18
        for _ in range(80):
            saat[0] += 0.05
            k.oku()
        w.mod = "Otonom"
        ppd = algi.AYAR["takip_ppd_pan"]
        kam = A.TS.kamera_acisi                 # dikeyde goruntu KAMERA acisiyla kayar
        # Kutu merkezinin kare-kare oynamasi sahada medyan ~1.5 px (21.09). Gurultu
        # olmazsa olu bolge kaldirilsa bile titreme OLUSMAZ ve test onu yakalayamaz.
        rng = random.Random(tohum)
        n0 = onceki = len(k.tilt.mock.kayit)
        t0, son_bolum, N = saat[0], 0, int(sure * 60)
        for i in range(N):                      # 60 Hz kareler
            saat[0] += 1 / 60.0
            k.oku()
            hp = hedef_pan + pan_hiz * (saat[0] - t0)
            t_cek = saat[0] - algi.AYAR["kamera_gecikme"]   # kare bu kadar once CEKILDI
            ex = (hp - k.pan_zamaninda(t_cek)) * ppd + rng.gauss(0.0, 1.5)
            ey = -(kam(hedef_tilt) - kam(k.tilt_zamaninda(t_cek))) * ppd + rng.gauss(0.0, 1.5)
            w._takip_olcum_geldi({"var": True, "t": saat[0], "ex": ex, "ey": ey,
                                  "olu_x": 7.0, "olu_y": 7.0, "w": 1280})
            if i >= N * 0.6:
                son_bolum += sum(1 for c in k.tilt.mock.kayit[onceki:]
                                 if c[:1] in ("P", "G", "Y") and c[:2] not in ("PZ", "PR", "PE")
                                 and c != "YQ")
            onceki = len(k.tilt.mock.kayit)
        kayit = k.tilt.mock.kayit[n0:]
        ozet = dict(pan_hata=k.pan_olculen - (hedef_pan + pan_hiz * (saat[0] - t0)),
                    tilt_hata=k.tilt_olculen - hedef_tilt, son_bolum=son_bolum,
                    G=sum(c.startswith("G") for c in kayit),
                    Y=sum(c.startswith("Y") and c != "YQ" for c in kayit),
                    PY=sum(c.startswith("PY") for c in kayit))
        # E-Stop: takip kapisindan TEK komut gecmemeli
        k.estop_aktif = True
        n = len(k.tilt.mock.kayit)
        for _ in range(20):
            saat[0] += 1 / 60.0
            k.oku()
            w._takip_olcum_geldi({"var": True, "t": saat[0], "ex": 80.0, "ey": 80.0,
                                  "olu_x": 7.0, "olu_y": 7.0, "w": 1280})
        ozet["estop_komut"] = sum(1 for c in k.tilt.mock.kayit[n:]
                                  if c[:1] in ("P", "G", "Y") and c[:2] not in ("PZ", "PR", "PE")
                                  and c != "YQ")
        return ozet
    finally:
        A.time = gercek
        if w is not None:
            w.close()


def test_surekli_takip_konum_kipi():
    """Eski firmware (yorunge yok): iki eksen hedefe oturur, oturunca SUSAR (titreme yok)."""
    r = _takip_kos(yorunge=False)
    assert abs(r["pan_hata"]) < 0.7 and abs(r["tilt_hata"]) < 0.7, r
    assert r["son_bolum"] <= 4, f"yerlestikten sonra {r['son_bolum']} komut (titreme): {r}"
    assert r["Y"] == 0 and r["PY"] == 0, "yorungesiz kartta Y/PY gitti"
    assert r["estop_komut"] == 0, f"E-Stop'ta {r['estop_komut']} takip komutu gecti"


def test_surekli_takip_yorunge_kipi():
    """Yorunge kipi: duran hedefe oturur; konum komutu (G/P) degil Y/PY akar.

    Sahadaki kadar tespit gurultusu (1.5 px) eklidir; gurultusuz eski testler titremeyi
    hic goremiyordu. Bosluk varsayimi buyuk oldugunda olusan salinim icin bkz.
    test_surekli_takip_bosluk_buyuk_sanilirsa."""
    r = _takip_kos(yorunge=True)
    assert abs(r["pan_hata"]) < 0.7 and abs(r["tilt_hata"]) < 0.7, r
    assert r["Y"] > 0 and r["PY"] > 0 and r["G"] == 0, r
    assert r["estop_komut"] == 0, f"E-Stop'ta {r['estop_komut']} takip komutu gecti"


def test_surekli_takip_bosluk_buyuk_sanilirsa():
    """Kontrolcu dişli boslugunu GERCEKTEN BUYUK sanarsa (ogrenme buyuttu, ayar yanlis)
    yorunge kipi duran hedefte salinima girmemeli.

    23.09 benzetim (bosluk varsayimi 1.5 -> kestirim 0.75, gercek 0, 1.5 px gurultu):
    eski kod 8 kosunun 6'sinda ~2.6 derece (kamera) tepe-tepe SONMEYEN salinim uretti.
    Sebep: bosluk modeli basamak seklindeydi (yon degisince ofset bir uctan obur uca
    sicriyordu) ve duran hedef karari ANLIK hiza bakiyordu. Duzeltmeyle 2/8. Arayuzun
    gercek ayarinda (0.8) eski ve yeni kod 0/8. Tohum 1 / -5: eski kodda salinan kosu."""
    r = _takip_kos(yorunge=True, hedef_tilt=-5.0, tohum=1, bosluk=1.5)
    assert abs(r["pan_hata"]) < 0.7 and abs(r["tilt_hata"]) < 0.7, r


def test_otonom_arayuz_penceresine_uyar():
    """Otonom takibin tek siniri ARAYUZDEKI hareket penceresidir (23.09 kullanici karari).

    (1) Pencere +5'te bitiyorsa +15'teki hedef icin kol +5'te durur.
    (2) Pencere tam aciksa (-30..+30) hedef +22'de de takip edilir — eskiden gizli otonom
        tavan (+25, kamera acisiyla hesaplanan pay yuzunden fiilen +19.8) kolu tutuyordu;
        sahada 10 m'deki hedefe cikilamadi."""
    r = _takip_kos(yorunge=True, hedef_tilt=15.0, tilt_pencere=(-30.0, 5.0))
    assert r["tilt_hata"] < -9.0 and abs(r["tilt_hata"] + 10.0) < 0.6, r   # +5'te durdu
    r = _takip_kos(yorunge=True, hedef_tilt=22.0, sure=6.0)
    assert abs(r["tilt_hata"]) < 1.5, f"gizli tavan hala var: {r}"


def test_surekli_takip_hareketli_hedef():
    """Yorunge kipi, pan'da 3 der/sn kayan hedef: namlu hedefin ustunde kalir."""
    r = _takip_kos(yorunge=True, pan_hiz=3.0, sure=6.0)
    assert abs(r["pan_hata"]) < 1.5 and abs(r["tilt_hata"]) < 0.7, r


def test_kapanis_karti_kilitlemez():
    """24.09 saha: kapanista giden STOP, USB'den beslenen S3'te sonraki acilisa kadar kaldi;
    acilis ACIL DURDUR'da basladi, 30 derece sorusu gelmedi. Kapanis: lazer soner, eksenler
    durur, kontrol kapanir (D) — ama kart KILITLENMEZ."""
    w = _tek_pencere()
    m = w.kontrol.tilt.mock
    _ates_ac(w)
    assert m.lazer_acik
    n = len(m.kayit)
    w.close()
    son = m.kayit[n:]
    assert not m.acil and "STOP" not in son, ("kapanis karti kilitledi", son)
    assert not m.lazer_acik and "L0" in son and "D" in son, son


def _yorunge_listesi(kayit, onek):
    """Sahte kartin kaydindaki Y / PY komutlari: [(konum, hiz), ...]."""
    out = []
    for c in kayit:
        if c.startswith(onek) and c != "YQ" and not (onek == "Y" and c.startswith("YQ")):
            p, v = c[len(onek):].split(",")
            out.append((float(p), float(v)))
    return out


def test_manuel_basili_tutma_yorunge_ve_yumusak_fren():
    """24.09 saha: basili tutma 50 ms'de bir KONUM hedefi yolluyordu, motor her hedefte
    frenleyip yeniden hizlaniyordu ("sert"). Artik yorunge (konum + hiz); birakinca hiz 0 ve
    hedef = durabilecegi nokta (ziplama yok); capraz tuslarda birakilan eksen de frenlenir;
    E-Stop'ta hicbir yorunge/fren gitmez; yorunge bilmeyen kartta eski konum yolu."""
    import re
    gercek = A.time
    A.time = _SahteZaman
    saat = _SahteZaman.simdi
    w = gercek_pencere()
    try:
        k, m = w.kontrol, w.kontrol.tilt.mock
        assert k.yorunge_destekli, "kurulum: sahte kart yorunge bilmiyor"
        v = w._hassasiyet()[1]           # basili tutma hizi HASSASIYET'ten (24.09)
        (_, pan_ivme), (_, tilt_ivme) = k.hiz_profilleri()

        def tut(*yonler, n=6):
            for y in yonler:
                if y not in w._basili_yonler:
                    w._dpad_press(y)
            w._tekrar_baslat()
            for _ in range(n):
                saat[0] += 0.05
                w._tekrar_tik()

        n0 = len(m.kayit)
        tut("up")
        yeni = m.kayit[n0:]
        Y = _yorunge_listesi(yeni, "Y")
        assert len(Y) >= 5 and all(abs(h - v) < 1e-3 for _, h in Y), ("basili tutmada yorunge yok", yeni)
        assert sum(c.startswith("G") for c in yeni) <= 1, ("tek dokunus disinda konum komutu", yeni)
        son_p = Y[-1][0]
        n1 = len(m.kayit)
        w._dpad_release("up")
        F = _yorunge_listesi(m.kayit[n1:], "Y")
        assert F and F[-1][1] == 0.0, "birakinca hiz 0 yorungesi gitmedi"
        assert abs(F[-1][0] - son_p - v * v / (2 * tilt_ivme)) < 0.05, ("fren hedefi", F, son_p)
        n2 = len(m.kayit)
        saat[0] += 0.05
        w._fren_tik()
        assert _yorunge_listesi(m.kayit[n2:], "Y")[-1] == F[-1], "fren tazelenmedi"
        saat[0] += A.MainWindow.FREN_S
        w._fren_tik()
        n3 = len(m.kayit)
        saat[0] += 0.05
        w._fren_tik()
        assert len(m.kayit) == n3, "fren suresi doldu ama komut gitmeye devam etti"

        # CAPRAZ: yukari + sag; sag birakilinca PAN frenlenir (hiz 0), tilt akmaya devam eder
        n4 = len(m.kayit)
        tut("up", "right", n=4)
        PY = _yorunge_listesi(m.kayit[n4:], "PY")
        assert PY and PY[-1][1] == v, PY
        son_pan = PY[-1][0]
        w._dpad_release("right")
        n5 = len(m.kayit)
        saat[0] += 0.05
        w._tekrar_tik()
        PY2 = _yorunge_listesi(m.kayit[n5:], "PY")
        Y2 = _yorunge_listesi(m.kayit[n5:], "Y")
        assert PY2 and PY2[-1][1] == 0.0, ("birakilan pan frenlenmedi", m.kayit[n5:])
        assert abs(PY2[-1][0] - (son_pan + v * 0.05 + v * v / (2 * pan_ivme))) < 0.05, (PY2, son_pan)
        assert Y2 and Y2[-1][1] == v, "tilt akisi kesildi"
        w._dpad_release("up")

        # E-STOP basili tutarken: hicbir yorunge / fren / konum komutu gitmez
        w._fren_durdur()
        tut("up", n=2)
        _estop(w, True)
        n6 = len(m.kayit)
        saat[0] += 0.05
        w._tekrar_tik()
        w._dpad_release("up")
        w._fren_tik()
        hareket = [c for c in m.kayit[n6:] if re.match(r"^(PY|Y(?!Q)|G|P-?\d)", c)]
        assert not hareket, ("E-Stop'ta hareket komutu", hareket)
        _estop(w, False)

        # Yorunge bilmeyen kart (eski firmware): eski konum yolu, Y yok
        for _ in range(4):
            saat[0] += 0.05
            k.oku()
        k.tilt.yorunge_destekli = None
        n7 = len(m.kayit)
        tut("up", n=3)
        yeni = m.kayit[n7:]
        assert not _yorunge_listesi(yeni, "Y") and sum(c.startswith("G") for c in yeni) >= 3, yeni
        w._dpad_release("up")
    finally:
        w.close()
        A.time = gercek


def test_kol_cubugu_yorunge_ve_birakinca_fren():
    """Kol cubugu da ayni yol: yorunge, cubuk birakilinca bir kez fren. Hiz KARESEL
    egriyle (sapma x |sapma| x HASSASIYET hizi, 24.09): az itince cok yavas."""
    import gamepad as G
    gercek = A.time
    A.time = _SahteZaman
    saat = _SahteZaman.simdi
    w = gercek_pencere()
    try:
        k, m = w.kontrol, w.kontrol.tilt.mock

        class SahteKol:
            bagli, ad = True, "test"

            def __init__(self):
                self.d = G.Durum()

            def oku(self):
                return self.d

            def kapat(self):
                pass
        kol = SahteKol()
        w.gamepad = kol
        w._gp_son_t = saat[0]
        v = w._hassasiyet()[1]
        sapma = 0.5
        vv = sapma * abs(sapma) * v                          # karesel egri
        (_, _), (_, tilt_ivme) = k.hiz_profilleri()
        n0 = len(m.kayit)
        kol.d = G.Durum()
        kol.d.tilt = sapma
        for _ in range(5):
            saat[0] += 0.05
            w._gamepad_tik()
        Y = _yorunge_listesi(m.kayit[n0:], "Y")
        assert len(Y) >= 4 and abs(Y[-1][1] - vv) < 1e-3, Y
        kol.d = G.Durum()                                    # cubuk birakildi
        n1 = len(m.kayit)
        saat[0] += 0.05
        w._gamepad_tik()
        F = _yorunge_listesi(m.kayit[n1:], "Y")
        assert F and F[-1][1] == 0.0, "cubuk birakilinca fren yok"
        assert abs(F[-1][0] - (Y[-1][0] + vv * 0.05 + vv * vv / (2 * tilt_ivme))) < 0.05, (F, Y[-1])
        n2 = len(m.kayit)
        saat[0] += 0.05
        w._gamepad_tik()
        assert not _yorunge_listesi(m.kayit[n2:], "Y"), "cubuk duruyor ama her tikta yeniden fren"
    finally:
        w.close()
        A.time = gercek


GERCEK_KART_TESTLERI = [
    test_estop_hareketi_keser,
    test_estop_atesi_keser,
    test_donanim_butonu_yazilimdan_kaldirilamaz,
    test_lazer_olu_adam_anahtari,
    test_lazer_kapaliyken_tazeleme_gitmez,
    test_l_kisayolu_estopu_asamaz,
    test_kart_disaridan_durunca_ates_ve_hareket_kesilir,
    test_otonom_ates_gorunen_hedefe,
    test_otonom_ates_estopta_ve_asama1de_yok,
    test_sahte_lazerde_hedef_vuruldu_sayilmaz,
    test_operator_acisi_karta_kol_acisi_gider,
    test_estop_pan_acisini_kaybetmez,
    test_otonomdan_manuele_gecis_olculen_konumdan_devam_eder,
    test_otonomda_takip_ivmesi_yumusak,
    test_yakin_balonda_takip_boya_gore_yumusar,
    test_kilit_baska_nesneye_gecince_takip_sifirlanir,
    test_balon_atesi_imha_dogrulamasina_bildirilir,
    test_dost_onundeyken_otonom_ates_acilmaz,
    test_balon_atesi_lazer_altinda_suruyor,
]
TAKIP_TESTLERI = [
    test_tek_kart_lazer_ve_olu_adam_anahtari,
    test_tek_kart_acil_durdurma,
    test_tek_kart_donanim_butonu,
    test_tek_kart_otonom_ates_ve_gercek_lazer,
    test_klavye_ve_kol_acil_durdurur_tekrar_basinca_devam,
    test_panel_aktif_hedefi_hayalet_ve_balon_bilgisi_tasir,
    test_balon_modunda_kilit_ve_nisan_balonda,
    test_surekli_takip_konum_kipi,
    test_surekli_takip_yorunge_kipi,
    test_surekli_takip_bosluk_buyuk_sanilirsa,
    test_surekli_takip_hareketli_hedef,
    test_otonom_arayuz_penceresine_uyar,
    test_kapanis_karti_kilitlemez,
    test_manuel_basili_tutma_yorunge_ve_yumusak_fren,
    test_kol_cubugu_yorunge_ve_birakinca_fren,
]


if __name__ == "__main__":
    app = A.QApplication([])
    win = pencere()
    try:
        test_hareket_ve_ates(win)
        test_kart_kilidi_ve_hizalama(win)
        test_acilis_yukselisi_kart_hazir_olana_kadar_bekler(win)
        test_acilis_onayi_hayir_ise_kol_kipirdamaz(win)
        test_acilis_sorusu_acil_durdurdan_sonra_gelir(win)
        test_tip_secimi(win)
        test_kare_arayuze_ulasir(win)
    finally:
        win.close()
    # Guvenlik kapilari: her test KENDI penceresi + taze sahte kartla (biri digerinin
    # E-Stop/lazer durumunu devralmasin). Ilk hatada DURULMAZ: bir kapinin kirilmasi
    # digerlerinin sonucunu gizlememeli — hepsi calisir, kalanlar sonda listelenir.
    import sys
    import traceback
    kalanlar = []

    def _kos(test, *arg):
        try:
            test(*arg)
        except Exception as e:                  # AssertionError dahil
            kalanlar.append((test.__name__, f"{type(e).__name__}: {e}"))
            traceback.print_exc()

    for test in GERCEK_KART_TESTLERI:
        w = gercek_pencere()
        try:
            _kos(test, w)
        finally:
            w.close()
    for test in TAKIP_TESTLERI:
        _kos(test)
    toplam = 7 + len(GERCEK_KART_TESTLERI) + len(TAKIP_TESTLERI)
    if kalanlar:
        print(f"\nKAPI TESTLERI: {len(kalanlar)}/{toplam} KALDI")
        for ad, neden in kalanlar:
            print(f"  - {ad}: {neden[:160]}")
        sys.exit(1)
    print(f"Birlesik arayuz kapi testleri OK — {toplam} test: "
          "hareket/ates sinirlari, acilis, tip secimi, E-Stop (hareket+ates), donanim butonu, "
          "lazer olu adam anahtari, [L] kisayolu, kartin kendi durmasi, otonom ates kirmizi "
          "kapisi, operator->kol acisi, surekli takip (konum/yorunge/hareketli), balon "
          "takibi (kilit balonda, imha bildirimi, dost onunde ates yok, hayalet kapisi), TEK KART "
          "lazer (olu adam, acil kilit, donanim butonu, otonom) + klavye/kol acil durdur, "
          "kapanis karti kilitlemez, acilis sorusu E-Stop sonrasi, manuel yorunge + yumusak fren")
