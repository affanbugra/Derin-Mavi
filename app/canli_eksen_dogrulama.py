# -*- coding: utf-8 -*-
"""ESP32-S3 iki eksen için sınırlı, düşük hızlı geri-bildirim testi.

Lazer koduna erişmez. Her ekseni başlangıç konumundan en fazla 3° ayırır ve geri
getirir; beklenmedik durumda X/D ile durdurur. Fiziksel lazer beslemesi kapalı,
hareket alanı boş ve kartın sıfır referansı doğrulanmış olmalıdır.
"""
import argparse
import threading
import time

import tilt_surucu as T


def kare_al(cap):
    """Kamera tamponundan eski kare kalmasın; en son okunanı kullan."""
    kare = None
    for _ in range(5):
        ok, yeni = cap.read()
        if ok and yeni is not None:
            kare = yeni
    if kare is None:
        raise RuntimeError("Kamera karesi okunamadı")
    return kare


def sahne_kaymasi(once, sonra):
    """Sabit arka planın iki duruş arasındaki (dx,dy) piksel kayması."""
    import cv2
    import numpy as np

    def hazirla(kare):
        h, w = kare.shape[:2]
        kirpik = kare[:int(h * 0.62), int(w * 0.08):int(w * 0.92)]
        return cv2.cvtColor(kirpik, cv2.COLOR_BGR2GRAY).astype(np.float32)

    a, b = hazirla(once), hazirla(sonra)
    pencere = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), kalite = cv2.phaseCorrelate(a * pencere, b * pencere)
    return dx, dy, kalite


def bekle(s, kilit, oku, hedef, sure=4.0):
    bitis = time.monotonic() + sure
    ornekler = []
    while time.monotonic() < bitis:
        with kilit:
            deger = oku()
            hata = s.hata
            taze = s.taze
        if deger is not None:
            ornekler.append(deger)
            if abs(deger - hedef) <= 0.12 and len(ornekler) >= 3:
                return ornekler
        if hata or not taze:
            raise RuntimeError(f"Kart geri bildirimi kesildi: {hata}")
        time.sleep(0.02)
    raise TimeoutError(f"Hedef {hedef:.3f}° ulaşılmadı; son {ornekler[-1] if ornekler else None}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--adim", type=float, default=1.0,
                    help="eksen basamağı, güvenlik için 1–3°")
    ap.add_argument("--kamera", action="store_true",
                    help="kameradaki fiziksel sahne kaymasını da ölç")
    args = ap.parse_args()
    if not 1.0 <= args.adim <= 3.0:
        raise SystemExit("Adım güvenlik sınırı dışında: yalnız 1–3°")
    cap = None
    if args.kamera:
        import algi
        cap = algi.open_camera()
        if cap is None:
            raise SystemExit("Kamera açılamadı; motor testine başlanmadı")
    s = T.TiltSurucu(args.port)
    if not s.bagli:
        if cap is not None:
            cap.release()
        raise SystemExit(f"Kart açılamadı: {s.hata}")
    kilit = threading.RLock()
    dur = threading.Event()

    def nabiz():
        # Kamera okuma/phaseCorrelate 350 ms watchdog'u durdurmamalı.
        while not dur.is_set():
            with kilit:
                s.yokla()
            dur.wait(0.02)

    th = threading.Thread(target=nabiz, daemon=True)
    th.start()
    try:
        for _ in range(100):
            with kilit:
                if s.hazir and s.pan_destekli:
                    break
            time.sleep(0.02)
        with kilit:
            if not (s.hazir and s.pan_destekli and s.pan_aci is not None):
                raise RuntimeError(f"Kalibre/hazır/PAN1 değil: {s.ozet()}")
            if s.hareket or s.pan_durum["hareket"] or s.kart_resetlendi:
                raise RuntimeError("Kart hareket ediyor veya reset gördü; test iptal")
            tilt0, pan0 = s.aci, s.pan_aci
        # Operator acisi -30..+30'dur. Test boyunca olculmus fiziksel 48°
        # (= operator +18°) takip tavanindan en az 3° pay kalsin.
        if not (T.ACI_MIN <= tilt0 and tilt0 + args.adim <= 15.0
                and abs(pan0) <= 45.0 and abs(pan0 + args.adim) <= 45.0):
            raise RuntimeError(f"Güvenli başlangıç penceresi dışında: tilt={tilt0}, pan={pan0}")
        with kilit:
            s.hiz_ayarla(T.H_YAVAS)
        time.sleep(0.4)
        print(f"Başlangıç: tilt {tilt0:.3f}°, pan {pan0:.3f}°, "
              f"kalibrasyon {s.durum['upper']} darbe, pan EN={s.pan_durum['en']}")
        kare0 = kare_al(cap) if cap is not None else None

        # Önce tek eksen; öteki eksen sabit kalmalı.
        tilt1 = tilt0 + args.adim
        with kilit:
            s.git(tilt1)
        t_artis = bekle(s, kilit, lambda: s.aci, tilt1)
        if cap is not None:
            time.sleep(0.15)
            tilt_kayma = sahne_kaymasi(kare0, kare_al(cap))
        with kilit:
            pan_sapma = abs(s.pan_aci - pan0)
            s.git(tilt0)
        t_donus = bekle(s, kilit, lambda: s.aci, tilt0)
        print(f"Tilt +{args.adim:g}° / geri: {t_artis[-1]:.3f}° / {t_donus[-1]:.3f}°; "
              f"pan çapraz sapma {pan_sapma:.3f}°")
        if cap is not None:
            print(f"Tilt fiziksel görüntü kayması: dx={tilt_kayma[0]:+.1f}, "
                  f"dy={tilt_kayma[1]:+.1f} px, kalite={tilt_kayma[2]:.2f}")
            kare0 = kare_al(cap)

        pan1 = pan0 + args.adim
        with kilit:
            s.pan_git(pan1)
        p_artis = bekle(s, kilit, lambda: s.pan_aci, pan1)
        if cap is not None:
            time.sleep(0.15)
            pan_kayma = sahne_kaymasi(kare0, kare_al(cap))
        with kilit:
            tilt_sapma = abs(s.aci - tilt0)
            s.pan_git(pan0)
        p_donus = bekle(s, kilit, lambda: s.pan_aci, pan0)
        print(f"Pan +{args.adim:g}° / geri: {p_artis[-1]:.3f}° / {p_donus[-1]:.3f}°; "
              f"tilt çapraz sapma {tilt_sapma:.3f}°")
        if cap is not None:
            print(f"Pan fiziksel görüntü kayması: dx={pan_kayma[0]:+.1f}, "
                  f"dy={pan_kayma[1]:+.1f} px, kalite={pan_kayma[2]:.2f}")
        if pan_sapma > 0.15 or tilt_sapma > 0.15:
            raise RuntimeError("Eksenler arası beklenmedik hareket")
        print("İki eksen geri bildirimi ve bağımsızlığı OK")
    finally:
        dur.set()
        th.join(timeout=1.0)
        with kilit:
            s.dur()
            s.kapat(kalici=True)
        if cap is not None:
            cap.release()


if __name__ == "__main__":
    main()
