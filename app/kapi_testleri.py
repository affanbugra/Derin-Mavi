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
import arayuz_qt as A
import kontrol as kontrol_mod


class SahteEtiket:
    """Metin/stil cagrilarini yutan sahte QLabel."""

    def setText(self, *a):
        pass

    def setStyleSheet(self, *a):
        pass


class SahteButon(SahteEtiket):
    """Yalnizca isaretli durumunu tutan sahte QPushButton."""

    def __init__(self):
        self._c = False

    def isChecked(self):
        return self._c

    def setChecked(self, v):
        self._c = v


class SahtePencere:
    """MainWindow'un hareket/ates kapilari icin ihtiyac duydugu asgari yuzey."""
    _aci_hareket = A.MainWindow._aci_hareket
    _ates_kes = A.MainWindow._ates_kes

    def _esp_goster(self, d):
        pass

    def __init__(self):
        self.mod = "Manuel"
        self.thread = None                # isinstance(AlgiThread) -> False
        self.pan_aci = 0.0
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
        self.kontrol = kontrol_mod.Kontrol("mock")


def test_uygulanan_delta():
    """Tilt limitinde ekrandaki aci ile cihazin hedefi KOPMAMALI.

    ESP32'ye ham delta degil, gercekten uygulanan delta gider (protokol.py EKSEN
    TANIMI). Aksi halde limitte ekran 60° kalirken cihaz hedefi buyumeye devam eder."""
    w = SahtePencere()
    for _ in range(12):                       # 12 x 5 = 60 -> tam limit
        w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == 60.0, w.tilt_aci
    assert w.kontrol.mock.hedef_pitch == 60.0, w.kontrol.mock.hedef_pitch

    # Limitte fazladan komut: gonderilecek bir sey yok, bos paket de atilmamali.
    paket = len(w.kontrol.mock.kayit)
    w._aci_hareket(0.0, 5.0)
    assert w.tilt_aci == 60.0
    assert len(w.kontrol.mock.kayit) == paket, w.kontrol.mock.kayit[-1]

    w._aci_hareket(0.0, -5.0)                 # asagi normal calisir
    assert w.tilt_aci == 55.0 and w.kontrol.mock.hedef_pitch == 55.0

    # ASIL VAKA — kismi kirpma: 55°'de +8 istenir, ancak +5 uygulanabilir.
    # Pakete 8 yazilirsa ekran 60 derken cihazin hedefi 63 olur (sessiz kopma).
    w._aci_hareket(0.0, 8.0)
    assert w.tilt_aci == 60.0, w.tilt_aci
    assert w.kontrol.mock.kayit[-1]["dy"] == 5.0, \
        f"ham delta gonderildi: {w.kontrol.mock.kayit[-1]['dy']} (uygulanan 5.0 olmaliydi)"
    assert w.kontrol.mock.hedef_pitch == 60.0, w.kontrol.mock.hedef_pitch


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
    w.thread = A.AlgiThread()
    w.thread.estop = True
    assert w._aci_hareket(0.0, 5.0) is False
    assert w.tilt_aci == 0.0 and w.kontrol.mock.hedef_pitch == 0.0

    w.thread.estop = False                    # DEVAM -> hareket yeniden serbest
    assert w._aci_hareket(0.0, 5.0) is True
    assert w.tilt_aci == 5.0 and w.kontrol.mock.hedef_pitch == 5.0


if __name__ == "__main__":
    test_uygulanan_delta()
    test_ates_sirasinda_yasak_alan()
    test_harekete_yasak_alan()
    test_estop_hareketi_keser()
    print("kapi testleri OK — uygulanan delta, ates sirasinda yasak alan, "
          "harekete yasak alan, E-Stop")
