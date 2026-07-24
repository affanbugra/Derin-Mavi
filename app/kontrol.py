# -*- coding: utf-8 -*-
"""Kontrol katmani — arayuzun ESP32 ile konusma API'si (mock/gercek TEK arayuz).

Kaynak secimi (donanim-bagimsiz, CLAUDE.md ilke 7):
    DERINMAVI_ESP=mock   -> MockESP32 (varsayilan; donanimsiz gelistirme)
    DERINMAVI_ESP=COM5   -> gercek seri port (pyserial; donanim gelince)
    DERINMAVI_ESP=off    -> kontrol kapali (yalniz goruntu isleme)

Kullanim (arayuz):
    k = Kontrol()
    k.nisan(mod, dx_der, dy_der)   # piksel hatasindan gelen aci duzeltmesi
    k.ates(True/False)             # lazer ac/kes
    k.estop(True/False)            # yazilimsal acil durdur / devam
    k.durum                       # son durum dict'i (yaw, pitch, durum_ad, lazer, ...)
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
        self.durum = None          # son cozulmus durum paketi (dict) veya None
        self.hata = None
        if self.kaynak == "off":
            return
        if self.kaynak == "mock":
            self.mock = MockESP32()
        else:                       # gercek seri port (or. COM5, /dev/ttyUSB0)
            try:
                import serial       # pyserial — yalniz gercek portta gerekir
                self.seri = serial.Serial(self.kaynak.upper(), 115200, timeout=0.05)
            except Exception as e:
                self.hata = f"Seri port açılamadı ({self.kaynak}): {e}"

    @property
    def bagli(self):
        return self.mock is not None or self.seri is not None

    @property
    def mock_mu(self):
        return self.mock is not None

    # ---- alt seviye: paket gonder, durum al ----
    def _gonder(self, paket):
        if self.mock is not None:
            self.durum = P.durum_coz(self.mock.islet(paket))
            return self.durum
        if self.seri is not None:
            try:
                self.seri.write(paket)
                yanit = self.seri.read(P.PAKET_BOY)
                if len(yanit) == P.PAKET_BOY:
                    self.durum = P.durum_coz(yanit)
                return self.durum
            except Exception as e:
                self.hata = f"Seri iletişim hatası: {e}"
        return None

    # ---- yuksek seviye API ----
    def nisan(self, mod, dx_der, dy_der):
        """Hedefe yonelme duzeltmesi (derece delta). Ates durumunu DEGISTIRMEZ."""
        return self._gonder(P.komut_paketle(mod, dx_der, dy_der, P.K_BEKLE))

    def ates(self, ac: bool, mod=0):
        return self._gonder(P.komut_paketle(mod, 0, 0, P.K_ATES if ac else P.K_ATES_KES))

    def estop(self, aktif: bool):
        return self._gonder(P.komut_paketle(0, 0, 0, P.K_ESTOP if aktif else P.K_DEVAM))

    def home(self):
        return self._gonder(P.komut_paketle(0, 0, 0, P.K_HOME))

    def kapat(self):
        if self.seri is not None:
            try:
                self.seri.close()
            except Exception:
                pass


if __name__ == "__main__":
    k = Kontrol("mock")
    assert k.bagli and k.mock_mu
    d = k.nisan(1, 4.2, -1.5)
    print("nisan ->", d)
    d = k.ates(True)
    assert d["lazer"], d
    d = k.estop(True)
    assert d["durum_ad"] == "E-STOP" and not d["lazer"], d
    k.estop(False)
    print("kontrol testleri OK")
