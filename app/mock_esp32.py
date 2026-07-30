# -*- coding: utf-8 -*-
"""MOCK ESP32 — gercek kartin yazilimsal taklidi (donanim gelmeden zincir testi).

Gercek ESP32 gibi davranir:
  - Komut paketini alir (protokol.py formati), gecersiz paketi REDDeder.
  - Yaw/pitch motorlarini SINIRLI HIZLA (slew) hedefe dogru surer (aninda isinlanmaz;
    gercek step motor davranisini taklit eder -> takip/dwell mantigi gercekci test edilir).
  - ATES komutuyla lazeri "acar", ATES_KES ile kapatir.
  - ESTOP'ta hareketi VE lazeri aninda keser, DEVAM gelene kadar komut kabul etmez.
  - Her komuta durum paketiyle cevap verir.

Gercek donanima gecis: kontrol.py'de port="mock" yerine "COM5" yazmak yeterli;
ESP32'deki C kodu ayni protokolu konusacak.
"""
import time

import protokol as P

# mekanik sinirlar / hizlar (KTR: yaw 360, pitch min 60; NEMA23 makul hizlar)
YAW_HIZ = 120.0    # derece/sn
PITCH_HIZ = 60.0
PITCH_MIN, PITCH_MAX = -30.0, 30.0


class MockESP32:
    def __init__(self):
        self.yaw = 0.0          # mutlak konum (der)
        self.pitch = 0.0
        self.hedef_yaw = 0.0    # komutla istenen konum
        self.hedef_pitch = 0.0
        self.lazer = False
        self.estop = False
        self.homed = True       # mock acilista homing tamam sayilir
        self._son_t = time.time()
        self.kayit = []         # test/teshis icin komut gecmisi

    # ---- fizik adimi: motorlari sinirli hizla hedefe yurut ----
    def _adim(self):
        t = time.time()
        dt = min(0.25, t - self._son_t)
        self._son_t = t
        if self.estop:
            return
        for isim, hiz in (("yaw", YAW_HIZ), ("pitch", PITCH_HIZ)):
            simdiki = getattr(self, isim)
            hedef = getattr(self, "hedef_" + isim)
            fark = hedef - simdiki
            adim = hiz * dt
            if abs(fark) <= adim:
                setattr(self, isim, hedef)
            else:
                setattr(self, isim, simdiki + (adim if fark > 0 else -adim))

    def _durum_kodu(self):
        if self.estop:
            return P.D_ESTOP
        if self.lazer:
            return P.D_ATES
        if abs(self.yaw - self.hedef_yaw) > 0.05 or abs(self.pitch - self.hedef_pitch) > 0.05:
            return P.D_HAREKET
        return P.D_HAZIR

    def islet(self, paket: bytes) -> bytes:
        """Bir komut paketini isler, durum paketi dondurur (gercek kartin dongusu)."""
        self._adim()
        k = P.komut_coz(paket)
        if k is None:                      # bozuk paket -> HATA durumu bildir
            return P.durum_paketle(P.D_HATA, self.yaw, self.pitch, self.homed, self.lazer)
        self.kayit.append(k)

        if k["komut"] == P.K_ESTOP:
            self.estop = True
            self.lazer = False             # sartname: E-Stop ateşi keser
            self.hedef_yaw, self.hedef_pitch = self.yaw, self.pitch   # hareketi durdur
        elif k["komut"] == P.K_DEVAM:
            self.estop = False
        elif not self.estop:               # ESTOP'tayken diger komutlar YOK SAYILIR
            if k["komut"] == P.K_HOME:
                self.hedef_yaw = self.hedef_pitch = 0.0
                self.homed = True
            else:
                # dx/dy = DELTA duzeltme (piksel hatasindan gelen aci).
                # Delta MEVCUT HEDEFE eklenir, mevcut KONUMA degil (bkz. protokol.py):
                #   * hedefe dogru yurunurken gelen yeni duzeltme birikerek dogru yerde toplanir
                #   * dx=dy=0 (or. ATES paketi) sureg elen hareketi IPTAL ETMEZ
                # Eski kod `self.yaw + dx` yaziyordu; ates komutu her seferinde hedefi
                # o anki konuma cekip hareketi kesiyordu (takip + ates ayni anda calismiyordu).
                if k["dx"] or k["dy"]:
                    self.hedef_yaw = self.hedef_yaw + k["dx"]
                    self.hedef_pitch = max(PITCH_MIN, min(PITCH_MAX,
                                                          self.hedef_pitch + k["dy"]))
                if k["komut"] == P.K_ATES:
                    self.lazer = True
                elif k["komut"] == P.K_ATES_KES:
                    self.lazer = False

        return P.durum_paketle(self._durum_kodu(), self.yaw, self.pitch,
                               self.homed, self.lazer)


if __name__ == "__main__":
    # kendi kendine test: hareket + ates + ESTOP zinciri
    m = MockESP32()
    d = P.durum_coz(m.islet(P.komut_paketle(1, 10.0, 5.0, P.K_BEKLE)))
    assert d["durum_ad"] == "Hareket", d
    time.sleep(0.15)                                   # motorlar yurusun
    d = P.durum_coz(m.islet(P.komut_paketle(1, 0, 0, P.K_ATES)))
    assert d["lazer"] is True, d
    d = P.durum_coz(m.islet(P.komut_paketle(1, 0, 0, P.K_ESTOP)))
    assert d["durum_ad"] == "E-STOP" and d["lazer"] is False, d       # ates KESILDI
    d = P.durum_coz(m.islet(P.komut_paketle(1, 5, 5, P.K_ATES)))      # estop'ta ates DENEMESI
    assert d["lazer"] is False and d["durum_ad"] == "E-STOP", d       # reddedildi
    d = P.durum_coz(m.islet(P.komut_paketle(1, 0, 0, P.K_DEVAM)))
    assert d["durum_ad"] != "E-STOP", d
    bozuk = bytearray(P.komut_paketle(0, 0, 0)); bozuk[3] ^= 0xFF
    assert P.durum_coz(m.islet(bytes(bozuk)))["durum_ad"] == "HATA"   # checksum reddi

    # B4 REGRESYONU: ATES paketi (dx=dy=0) sureg elen hareketi IPTAL ETMEMELI.
    m2 = MockESP32()
    P.durum_coz(m2.islet(P.komut_paketle(1, 90.0, 0, P.K_BEKLE)))     # 90 dereceye don
    assert m2.hedef_yaw == 90.0
    time.sleep(0.05)                                                  # yolun bir kismi
    P.durum_coz(m2.islet(P.komut_paketle(1, 0, 0, P.K_ATES)))         # yoldayken ATES
    assert m2.hedef_yaw == 90.0, f"ates hedefi bozdu: {m2.hedef_yaw}"
    assert m2.yaw < 90.0 and m2.lazer                                 # hala yolda + lazer acik
    # Delta MEVCUT HEDEFE eklenir (konuma degil) -> duzeltmeler birikir
    P.durum_coz(m2.islet(P.komut_paketle(1, 10.0, 0, P.K_BEKLE)))
    assert m2.hedef_yaw == 100.0, m2.hedef_yaw

    print("mock_esp32 testleri OK — hareket/ates/ESTOP/checksum + ates-hareket bagimsizligi")
