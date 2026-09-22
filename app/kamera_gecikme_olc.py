# -*- coding: utf-8 -*-
"""Kucuk tilt basamagindan kamera/enkoder gecikmesini olc; lazer/model kullanmaz.

Sabit arka plan dokusunun faz kaymasini izler. Sonuc, kare okuma zamani ile
kartin aci bildirimini eslemek icin kullanilir; fiziksel sensor zamani bilinmez.
"""
import argparse
import csv
import os
import statistics
import threading
import time

import cv2

import algi
import tilt_surucu as T


def arka_plan(frame):
    """Maket ve gimbal disinda kalan duvar/perde bolgesi, yari cozunurluk."""
    roi = frame[:460, :950]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (475, 230)).astype("float32")


def ara(iz, t):
    if not iz or t < iz[0][0] or t > iz[-1][0]:
        return None
    lo, hi = 0, len(iz) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if iz[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, a0 = iz[lo]
    t1, a1 = iz[hi]
    return a0 + (a1 - a0) * (t - t0) / max(1e-9, t1 - t0)


def degerlendir(kareler, acilar, bas):
    sonuclar = []
    for ms in range(0, 401, 10):
        lag = ms / 1000.0
        xy = [(T.kamera_acisi(a), y) for t, y in kareler
              if 0.5 <= t - bas <= 6.0
              for a in [ara(acilar, t - lag)] if a is not None]
        if len(xy) < 30:
            continue
        x, y = zip(*xy)
        xm, ym = statistics.mean(x), statistics.mean(y)
        var = sum((v - xm) ** 2 for v in x)
        if var < 0.1:
            continue
        ppd = sum((u - xm) * (v - ym) for u, v in xy) / var
        rmse = (sum((v - ym - ppd * (u - xm)) ** 2 for u, v in xy) / len(xy)) ** 0.5
        sonuclar.append((rmse, ms, ppd, len(xy)))
    for rmse, ms, ppd, n in sorted(sonuclar)[:5]:
        print(f"gecikme {ms:3d} ms | RMSE {rmse:5.2f} px | "
              f"kamera olcegi {ppd:5.2f} px/kamera° | {n} kare")
    if not sonuclar:
        print("Gecikme hesaplanamadi: hedef veya kart olcumu eksik")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--adim", type=float, default=3.0)
    ap.add_argument("--fps", type=int, default=60,
                    help="uygulamayla ayni kamera FPS istegi")
    args = ap.parse_args()
    if not 1.0 <= args.adim <= 3.0:
        raise SystemExit("Adim 1-3 derece olmali")
    algi.ayar_guncelle(kamera_fps=args.fps)
    cap = algi.open_camera()
    if cap is None:
        raise SystemExit("Kamera acilamadi")
    s = T.TiltSurucu(args.port)
    if not s.bagli:
        cap.release()
        raise SystemExit(f"Kart acilamadi: {s.hata}")
    kilit, dur = threading.RLock(), threading.Event()
    acilar, kareler = [], []

    def nabiz():
        while not dur.is_set():
            with kilit:
                s.yokla()
                if s.aci is not None:
                    acilar.append((time.time(), s.aci))
            dur.wait(0.02)

    th = threading.Thread(target=nabiz, daemon=True)
    th.start()
    try:
        for _ in range(100):
            with kilit:
                if s.hazir and s.aci is not None and not s.hareket:
                    break
            time.sleep(0.02)
        with kilit:
            if not s.hazir or s.aci is None or s.hareket:
                raise RuntimeError("Kart hazir veya duragan degil")
            ilk = s.aci
            if not 5.0 <= ilk <= 42.0:
                raise RuntimeError(f"Guvenli baslangic acisi disinda: {ilk:.2f}°")
            s.hiz_ayarla(T.H_YAVAS)
        hedef = ilk - args.adim
        print(f"Kamera {cap.get(cv2.CAP_PROP_FPS):.1f} FPS | "
              f"Tilt {ilk:.3f} -> {hedef:.3f} -> {ilk:.3f}°; 7 sn veri", flush=True)
        bas = time.time()
        gitti = dondu = False
        referans = pencere = None
        while time.time() - bas < 7.0:
            t = time.time() - bas
            if t >= 1.0 and not gitti:
                with kilit:
                    s.git(hedef)
                gitti = True
            if t >= 4.0 and not dondu:
                with kilit:
                    s.git(ilk)
                dondu = True
            ok, frame = cap.read()
            if ok:
                goruntu = arka_plan(frame)
                if referans is None:
                    referans = goruntu
                    pencere = cv2.createHanningWindow((475, 230), cv2.CV_32F)
                (_, dy), kalite = cv2.phaseCorrelate(referans, goruntu, pencere)
                if kalite >= 0.15:
                    kareler.append((time.time(), 2.0 * dy))
        with kilit:
            son = s.aci
        print(f"Son okunan aci {son:.3f}°; {len(kareler)} arka-plan karesi, "
              f"{len(acilar)} aci ornegi")
        degerlendir(kareler, acilar, bas)
        yol = os.path.join(os.path.dirname(__file__), "loglar",
                           f"gecikme_olc_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", newline="", encoding="utf-8") as f:
            yz = csv.writer(f)
            yz.writerow(("tur", "zaman", "deger"))
            yz.writerows(("aci", t, v) for t, v in acilar)
            yz.writerows(("kayma_y", t, v) for t, v in kareler)
        print(f"Kayit: {yol}")
    finally:
        dur.set()
        th.join(timeout=1.0)
        with kilit:
            s.dur()
            s.kapat(kalici=True)
        cap.release()


if __name__ == "__main__":
    main()
