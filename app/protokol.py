# -*- coding: utf-8 -*-
"""DERIN MAVI - Laptop <-> ESP32 UART protokolu (TEK KAYNAK).

KTR temeli: 115200 baud, sabit uzunluklu paket, XOR checksum, 0.1 derece cozunurluk.
Ayni format hem MOCK hem GERCEK ESP32'de kullanilir -> donanim gelince kod DEGISMEZ,
yalnizca port adi degisir. (ESP32 tarafindaki C kodu da bu dosyadaki tabloya gore yazilacak.)

KOMUT PAKETI (laptop -> ESP32, 8 bayt):
    [0] 0xAA  baslik
    [1] mod   0=Manuel 1=Otonom
    [2:4] dx  int16 LE, 0.1 der. birimi — YAW duzeltme delta'si (+ = saga)
    [4:6] dy  int16 LE, 0.1 der. birimi — PITCH duzeltme delta'si (+ = yukari)
    [6] komut 0=BEKLE 1=ATES 2=ATES_KES 3=ESTOP 4=DEVAM(estop kaldir) 5=HOME
    [7] xor   [0..6] baytlarinin XOR'u

    ⚠ DELTA SEMANTIGI (ESP32 C kodunu yazan arkadas MUTLAKA okusun):
      dx/dy DELTA'dir ve **dx=dy=0 "hareket etme" DEGIL, "hedefi DEGISTIRME" demektir.**
      Yani sifir delta gelince ESP32 mevcut hareket hedefini KORUMALI, sifirlamamalidir.
      Aksi halde hedefe donerken gelen bir ATES paketi (dx=dy=0) sureg elen hareketi
      iptal eder ve namlu hedefin yarisinda kalir — takip + ates ayni anda calismaz.
      Kural: yeni hedef = mevcut_hedef + delta   (mevcut_konum + delta DEGIL).

    ⚠ EKSEN TANIMI (arayuz, mock ve gercek ESP32 AYNI tanimi kullanmali):
      YAW  (dx) : azimut, 0-360 sarmali, + = saga.
      PITCH(dy) : yukselis, **0° = ufuk, + = yukari, tavan arayuzdeki tilt limiti (varsayilan 60°).**
      Negatif pitch YOKTUR (sistem ufkun altina bakmaz). Arayuz de bu araligi uygular ve
      ESP32'ye yalnizca GERCEKTEN UYGULANAN delta'yi gonderir; boylece ekrandaki aci ile
      cihazin hedefi asla birbirinden kopmaz.

DURUM PAKETI (ESP32 -> laptop, 8 bayt):
    [0] 0xAA  baslik
    [1] durum 0=HAZIR 1=HAREKET 2=ATES 3=ESTOP 4=HATA
    [2:4] yaw   int16 LE, 0.1 der. — mutlak konum
    [4:6] pitch int16 LE, 0.1 der. — mutlak konum
    [6] bayrak bit0=homing tamam, bit1=lazer acik
    [7] xor
"""
import struct

BASLIK = 0xAA
PAKET_BOY = 8

# komut kodlari
K_BEKLE, K_ATES, K_ATES_KES, K_ESTOP, K_DEVAM, K_HOME = 0, 1, 2, 3, 4, 5
# durum kodlari
D_HAZIR, D_HAREKET, D_ATES, D_ESTOP, D_HATA = 0, 1, 2, 3, 4
DURUM_AD = {0: "Hazır", 1: "Hareket", 2: "ATEŞ", 3: "E-STOP", 4: "HATA"}


def _xor(b):
    x = 0
    for v in b:
        x ^= v
    return x


def komut_paketle(mod, dx_der, dy_der, komut=K_BEKLE):
    """Komut paketini uretir. dx/dy derece (float) -> 0.1 der int16'ya kirpilir."""
    dx = max(-3200, min(3200, int(round(dx_der * 10))))
    dy = max(-3200, min(3200, int(round(dy_der * 10))))
    govde = struct.pack("<BBhhB", BASLIK, mod & 1, dx, dy, komut & 0xFF)
    return govde + bytes([_xor(govde)])


def komut_coz(paket):
    """Komut paketini cozer. Gecersizse None."""
    if len(paket) != PAKET_BOY or paket[0] != BASLIK or _xor(paket[:7]) != paket[7]:
        return None
    _, mod, dx, dy, komut = struct.unpack("<BBhhB", paket[:7])
    return {"mod": mod, "dx": dx / 10.0, "dy": dy / 10.0, "komut": komut}


def durum_paketle(durum, yaw_der, pitch_der, homed=True, lazer=False):
    yaw = max(-3200, min(3200, int(round(yaw_der * 10))))
    pitch = max(-3200, min(3200, int(round(pitch_der * 10))))
    bayrak = (1 if homed else 0) | (2 if lazer else 0)
    govde = struct.pack("<BBhhB", BASLIK, durum & 0xFF, yaw, pitch, bayrak)
    return govde + bytes([_xor(govde)])


def durum_coz(paket):
    """Durum paketini cozer. Gecersizse None."""
    if len(paket) != PAKET_BOY or paket[0] != BASLIK or _xor(paket[:7]) != paket[7]:
        return None
    _, durum, yaw, pitch, bayrak = struct.unpack("<BBhhB", paket[:7])
    return {"durum": durum, "durum_ad": DURUM_AD.get(durum, "?"),
            "yaw": yaw / 10.0, "pitch": pitch / 10.0,
            "homed": bool(bayrak & 1), "lazer": bool(bayrak & 2)}


if __name__ == "__main__":
    # hizli kendi kendine test
    p = komut_paketle(1, -12.34, 5.6, K_ATES)
    assert len(p) == PAKET_BOY
    c = komut_coz(p)
    assert c == {"mod": 1, "dx": -12.3, "dy": 5.6, "komut": K_ATES}, c
    bozuk = p[:-1] + bytes([p[-1] ^ 1])
    assert komut_coz(bozuk) is None            # checksum yakalama
    d = durum_paketle(D_ATES, 123.4, -15.0, homed=True, lazer=True)
    dc = durum_coz(d)
    assert dc["durum_ad"] == "ATEŞ" and dc["yaw"] == 123.4 and dc["lazer"]
    print("protokol testleri OK")
