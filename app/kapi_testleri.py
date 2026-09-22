# -*- coding: utf-8 -*-
"""Birlesik Affan arayuzu + v1 kontrol katmani regresyon testleri.

Kamera, model ve gercek motor baslatilmaz. Calistir: python app/kapi_testleri.py
Eski arayuzun testleri kapi_testleri_eski_arayuz.py dosyasinda korunur.
"""
import os
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DERINMAVI_ESP"] = "off"
os.environ["DERINMAVI_TILT"] = "off"
os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "derinmavi-yolo-test"))

import algi
import arayuz_qt as A
import bolge as B


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

    def kapat(self):
        pass


def pencere():
    A.InferenceThread.start = lambda self: None
    A.VideoThread.start = lambda self: None
    A.kamera_mod.Kamera.baslat = lambda self: None
    w = A.MainWindow()
    w.kontrol = SahteKontrol()
    return w


def test_hareket_ve_ates(w):
    assert w.max_tilt_limit == 25.0
    assert (w.bolge.hareket_pan.alt, w.bolge.hareket_pan.ust) == (-60.0, 60.0)
    assert (w.bolge.hareket_tilt.alt, w.bolge.hareket_tilt.ust) == (-25.0, 25.0)
    assert all((spin.minimum(), spin.maximum()) == (-60, 60)
               for spin in w.bolge_spin[("hareket", "pan")])
    assert all((spin.minimum(), spin.maximum()) == (-25, 25)
               for spin in w.bolge_spin[("hareket", "tilt")])
    assert w._aci_hareket(15, -30)
    assert (w.pan_ham, w.tilt_aci) == (15.0, -25.0)
    assert (w.kontrol.pan_hedef, w.kontrol.tilt_hedef) == (15.0, -25.0)
    assert w._aci_hareket(100, -10)
    assert (w.pan_ham, w.tilt_aci) == (60.0, -25.0)
    assert w._aci_hareket(-60, 60)
    assert (w.pan_ham, w.tilt_aci) == (0.0, 25.0)

    w.bolge.hareket_tilt = B.Pencere(True, -10, 10)
    assert w._aci_hareket(0, -25)
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


if __name__ == "__main__":
    app = A.QApplication([])
    win = pencere()
    try:
        test_hareket_ve_ates(win)
        test_kart_kilidi_ve_hizalama(win)
        test_acilis_yukselisi_kart_hazir_olana_kadar_bekler(win)
        test_tip_secimi(win)
        test_kare_arayuze_ulasir(win)
        print("Birlesik arayuz kapi testleri OK")
    finally:
        win.close()
