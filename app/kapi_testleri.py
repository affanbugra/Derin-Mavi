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

    def estop(self, ac):
        self.estop_aktif = bool(ac)
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
    # yatayin tek siniri arayuzdeki pencere (varsayilan +-60, +-180'e kadar ayarlanir).
    assert w.max_tilt_limit == 30.0
    assert (w.bolge.hareket_pan.alt, w.bolge.hareket_pan.ust) == (-60.0, 60.0)
    assert (w.bolge.hareket_tilt.alt, w.bolge.hareket_tilt.ust) == (-30.0, 30.0)
    assert all((spin.minimum(), spin.maximum()) == (-180, 180)
               for spin in w.bolge_spin[("hareket", "pan")])
    assert all((spin.minimum(), spin.maximum()) == (-30, 30)
               for spin in w.bolge_spin[("hareket", "tilt")])
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

def gercek_pencere():
    """Gercek Kontrol("mock") + sahte tilt/pan karti, SAHTE SAATLE (tekrarlanabilir).

    Donanima dokunmaz: kaynaklar acikca "mock" verilir, seri port acilmaz."""
    w = pencere()
    saat = [5000.0]
    k = kontrol_mod.Kontrol("mock", tilt_kaynak="mock")
    k.tilt._saat = lambda: saat[0]
    k.tilt.mock.t = k.tilt.mock.son_canli = saat[0]
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


def _otonom_veri(kirmizi):
    return {"active": {"tip": "Hedef", "hayalet": False}, "merkezde": True,
            "kirmizi_kaniti": kirmizi}


def _dwell_doldu(w):
    w._otonom_hedef_merkezde_t = time.time() - A.OTONOM_DWELL_SURE - 1


def test_otonom_ates_kirmizi_kaniti_sart(w):
    """A2/A3 otonom ates: yalniz BU KAREDE kirmizi gorulen hedefe. Model insani
    maket sanabiliyor (22.09 sahada) — sinif hafizasi ates izni degildir."""
    w.mod, w.asama = "Otonom", "Aşama 2"
    w._otonom_ates_aktif = False
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(False), False)
    assert w.kontrol.mock.lazer is False, "kirmizi kanitsiz OTONOM ATES"
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(True), False)
    assert w.kontrol.mock.lazer is True, "kirmizi + dwell doldu ama ates yok"
    w._otonom_ates_kontrol(_otonom_veri(False), False)
    assert w.kontrol.mock.lazer is False, "kirmizi kaybolunca ates KESILMEDI"


def test_otonom_ates_estopta_ve_asama1de_yok(w):
    """E-Stop'ta ve Asama 1'de (manuel gorev) otonom ates ASLA acilmaz."""
    w.mod, w.asama = "Otonom", "Aşama 1"
    w._otonom_ates_aktif = False
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(True), False)
    assert w.kontrol.mock.lazer is False, "Asama 1'de otonom ates"
    assert not w._otonom_ates_aktif, "Asama 1'de otonom ates KURULDU"
    w.asama = "Aşama 2"
    _estop(w, True)
    _dwell_doldu(w)
    w._otonom_ates_kontrol(_otonom_veri(True), True)
    # Kart E-Stop'ta L1'i zaten reddeder; arayuzun kendi kapisi da KAPALI kalmali
    # (yalniz karta guvenilmez — eski/farkli firmware'de o katman olmayabilir).
    assert not w._otonom_ates_aktif, "E-Stop'ta otonom ates KURULDU"
    assert w.kontrol.mock.lazer is False, "E-Stop'ta otonom ates"


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
        w._pan_takip = HK.EksenTakip(isaret=+1.0, bosluk=b)
        w._tilt_takip = HK.EksenTakip(isaret=-1.0, bosluk=b)
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


GERCEK_KART_TESTLERI = [
    test_estop_hareketi_keser,
    test_estop_atesi_keser,
    test_donanim_butonu_yazilimdan_kaldirilamaz,
    test_lazer_olu_adam_anahtari,
    test_lazer_kapaliyken_tazeleme_gitmez,
    test_l_kisayolu_estopu_asamaz,
    test_kart_disaridan_durunca_ates_ve_hareket_kesilir,
    test_otonom_ates_kirmizi_kaniti_sart,
    test_otonom_ates_estopta_ve_asama1de_yok,
    test_operator_acisi_karta_kol_acisi_gider,
]
TAKIP_TESTLERI = [
    test_surekli_takip_konum_kipi,
    test_surekli_takip_yorunge_kipi,
    test_surekli_takip_bosluk_buyuk_sanilirsa,
    test_surekli_takip_hareketli_hedef,
    test_otonom_arayuz_penceresine_uyar,
]


if __name__ == "__main__":
    app = A.QApplication([])
    win = pencere()
    try:
        test_hareket_ve_ates(win)
        test_kart_kilidi_ve_hizalama(win)
        test_acilis_yukselisi_kart_hazir_olana_kadar_bekler(win)
        test_acilis_onayi_hayir_ise_kol_kipirdamaz(win)
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
    toplam = 6 + len(GERCEK_KART_TESTLERI) + len(TAKIP_TESTLERI)
    if kalanlar:
        print(f"\nKAPI TESTLERI: {len(kalanlar)}/{toplam} KALDI")
        for ad, neden in kalanlar:
            print(f"  - {ad}: {neden[:160]}")
        sys.exit(1)
    print(f"Birlesik arayuz kapi testleri OK — {toplam} test: "
          "hareket/ates sinirlari, acilis, tip secimi, E-Stop (hareket+ates), donanim butonu, "
          "lazer olu adam anahtari, [L] kisayolu, kartin kendi durmasi, otonom ates kirmizi "
          "kapisi, operator->kol acisi, surekli takip (konum/yorunge/hareketli)")
