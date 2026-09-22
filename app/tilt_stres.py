# -*- coding: utf-8 -*-
"""DERIN MAVI — TILT KARTI STRES / KILITLENME AYIRT TESTI.

Sahada: otonom takip bir sure calisti, sonra ESP32 TAMAMEN sustu (STATE3 yok,
komutlara cevap yok, USB reset'e bile cevap yok); yalnizca USB cekilip
takilinca duzeldi. Manuel modda hic olmadi.

Iki hipotezi AYIRMAK icin:
  yazilim   : otonomun KOMUT DESENI (siki G yagmuru, nabiz bosluklari yuzunden
              kilitle-ac dongusu, taninmayan komut) firmware'i takiyor mu?
              -> kol HIC HAREKET ETTIRILMEDEN denenir (hedef = kolun durdugu aci)
  hareket   : ayni desen + GERCEK kucuk hareketler ve sik YON DEGISIMI.
              Yalniz bunda kilitleniyorsa sebep motor/surucu tarafindan gelen
              elektriksel gurultudur (GND, besleme, kablo).

Her satir zaman damgasiyla `tilt_stres_<zaman>.log` dosyasina yazilir: kilitlenme
olursa ondan hemen once karta ne gittigi ve karttan ne geldigi gorulur.

Kullanim:
    python app/tilt_stres.py yazilim 120            # 120 sn, kol KIPIRDAMAZ
    python app/tilt_stres.py hareket 120 -10 5      # operator -10..+5 (kol 20-35), DONER
"""
import os
import random
import sys
import time

import serial
import tilt_surucu as T

SESSIZLIK_ESIGI = 1.0   # sn — bu kadar STATE3 gelmezse kart KILITLENDI sayilir


def calistir(mod, sure, alt=-10.0, ust=5.0, port="auto"):
    if port == "auto":
        port = T.otomatik_port_bul()
        if port is None:
            print("[HATA] STATE3 yayinlayan port bulunamadi — kart zaten sessiz olabilir.")
            return 2
    s = serial.Serial(port=None, baudrate=T.BAUD, timeout=0, write_timeout=0.2)
    s.dtr = False
    s.rts = False
    s.port = port
    s.open()

    dosya = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         f"tilt_stres_{time.strftime('%Y%m%d_%H%M%S')}.log")
    log = open(dosya, "w", encoding="utf-8")
    t0 = time.time()

    def yaz_log(yon, metin):
        log.write(f"{time.time() - t0:9.3f} {yon} {metin}\n")

    def gonder(satir):
        yaz_log(">>", satir.strip())
        s.write(satir.encode("ascii"))

    rx, durum, son_state = "", None, time.time()
    sayac = {"G": 0, "H": 0, "E": 0, "X": 0, "Z": 0, "OK": 0, "ERR": 0, "STATE3": 0}
    rng = random.Random(1)
    hedef_yon = 1
    sonraki_g = sonraki_h = sonraki_bosluk = time.time()
    kilitlendi = False

    gonder("E\n")
    while time.time() - t0 < sure:
        # --- oku ---
        n = s.in_waiting
        if n:
            rx += s.read(n).decode("ascii", "replace")
        while "\n" in rx:
            satir, rx = rx.split("\n", 1)
            satir = satir.strip()
            if not satir:
                continue
            d = T.durum_coz(satir)
            if d is not None:
                durum, son_state = d, time.time()
                sayac["STATE3"] += 1
                if sayac["STATE3"] % 10 == 0:       # log sismesin: her 10'da bir
                    yaz_log("<<", satir)
            else:
                yaz_log("<<", satir)
                if satir.startswith("OK"):
                    sayac["OK"] += 1
                elif satir.startswith("ERR"):
                    sayac["ERR"] += 1

        simdi = time.time()
        if simdi - son_state > SESSIZLIK_ESIGI:
            kilitlendi = True
            yaz_log("!!", f"KART SUSTU — {simdi - son_state:.2f} sn STATE3 yok")
            break
        if durum is None:
            time.sleep(0.01)
            continue

        # --- otonom komut deseni ---
        # Nabiz bosluklari: YOLO/arayuz takilmasini taklit eder. 350 ms ustu
        # sessizlik karti kilitler, surucu E ile yeniden acar — otonomda sik olur.
        if simdi >= sonraki_bosluk:
            sonraki_bosluk = simdi + rng.uniform(3.0, 6.0)
            time.sleep(0.42)
            sonraki_h = time.time()
            if durum is not None:
                gonder("E\n"); sayac["E"] += 1
            continue
        if simdi >= sonraki_h:
            sonraki_h = simdi + 0.12
            gonder("H\n"); sayac["H"] += 1
            if not durum["acik"]:
                gonder("E\n"); sayac["E"] += 1
        if simdi >= sonraki_g and durum["acik"] and durum["kalibre"]:
            sonraki_g = simdi + rng.uniform(0.05, 0.15)       # ~7-20 komut/sn
            if mod == "yazilim":
                a = durum["aci"]                               # kol KIPIRDAMAZ
            else:
                # Kucuk adimlar + sik yon degisimi: otonom nisan duzeltmesi gibi.
                if rng.random() < 0.3:
                    hedef_yon = -hedef_yon
                a = durum["aci"] + hedef_yon * rng.uniform(0.5, 4.0)
                a = max(alt, min(ust, a))
            gonder(T.git(a)); sayac["G"] += 1
            if rng.random() < 0.05:
                gonder("X\n"); sayac["X"] += 1
            if rng.random() < 0.02:
                gonder("Z2006.2,17833.3\n"); sayac["Z"] += 1   # eski firmware'de ERR
        time.sleep(0.005)

    if not kilitlendi:
        gonder("D\n")
    log.close()
    s.close()

    gecen = time.time() - t0
    print(f"\n=== {mod.upper()} testi — {gecen:.0f} sn, port {port} ===")
    print("gonderilen:", {k: v for k, v in sayac.items() if k in "GHEXZ"})
    print(f"alinan    : STATE3 {sayac['STATE3']}  OK {sayac['OK']}  ERR {sayac['ERR']}")
    print("log       :", dosya)
    if kilitlendi:
        print("\n[!!] KART KILITLENDI. USB kablosunu cekip tak; log'un SON satirlarina bak.")
        return 1
    print("\n[ OK ] Kart butun test boyunca konustu, kilitlenmedi.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("yazilim", "hareket"):
        print(__doc__)
        raise SystemExit(0)
    mod = sys.argv[1]
    sure = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
    alt = float(sys.argv[3]) if len(sys.argv) > 3 else -10.0
    ust = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0
    raise SystemExit(calistir(mod, sure, alt, ust))
