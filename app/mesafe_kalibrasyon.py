# -*- coding: utf-8 -*-
"""Kamera odak uzakligi (FOCAL_PX) kalibrasyonu.

Mesafe formulu:  mesafe = gercek_boyut * FOCAL_PX / piksel_boyut
Dolayisiyla:     FOCAL_PX = piksel_boyut * bilinen_mesafe / gercek_boyut

NASIL KULLANILIR:
 1. Boyutunu bildigin bir nesneyi (orn. 50 cm'lik F16 maketi, ya da 30 cm cetvel)
    kameradan BILINEN bir mesafeye koy (orn. tam 5.00 m — serit metreyle olc).
 2. python mesafe_kalibrasyon.py --boyut 0.50 --mesafe 5.0
 3. Acilan pencerede nesnenin IKI UCUNA tikla (genisligi/boyu neyse o iki uc).
 4. Program FOCAL_PX degerini hesaplar ve ekrana yazar.
 5. Bu degeri algi.py FOCAL_PX sabitine yaz (veya DERINMAVI_FOCAL env ile gec).

IPUCU: 3-4 farkli mesafede tekrarla (5m, 10m, 15m) ve ortalamasini al.
Zoom/cozunurluk degisirse kalibrasyon tekrarlanmalidir!
"""
import argparse
import cv2
import numpy as np

noktalar = []


def tikla(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN and len(noktalar) < 2:
        noktalar.append((x, y))


def kamera_ac(index=1):
    for idx, backend in ((index, cv2.CAP_DSHOW), (0, cv2.CAP_DSHOW), (index, cv2.CAP_ANY)):
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened():
            ok, fr = cap.read()
            if ok and fr is not None and fr.mean() > 1:
                print(f"Kamera acildi: index {idx}")
                return cap
        cap.release()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boyut", type=float, required=True,
                    help="Nesnenin gercek boyutu (metre), orn. 0.50")
    ap.add_argument("--mesafe", type=float, required=True,
                    help="Nesnenin kameraya uzakligi (metre), orn. 5.0")
    ap.add_argument("--kamera", type=int, default=1, help="Kamera index (vars. 1)")
    args = ap.parse_args()

    cap = kamera_ac(args.kamera)
    if cap is None:
        print("HATA: Kamera acilamadi.")
        return

    cv2.namedWindow("kalibrasyon")
    cv2.setMouseCallback("kalibrasyon", tikla)
    print("Nesnenin iki ucuna tikla. R = sifirla, S = kareyi dondur, Q = cik.")

    donmus = frozen = None
    while True:
        if frozen is None:
            ok, frame = cap.read()
            if not ok:
                continue
        else:
            frame = frozen.copy()

        for p in noktalar:
            cv2.circle(frame, p, 5, (0, 255, 0), -1)
        if len(noktalar) == 2:
            cv2.line(frame, noktalar[0], noktalar[1], (0, 255, 0), 2)
            px = float(np.hypot(noktalar[1][0] - noktalar[0][0],
                                noktalar[1][1] - noktalar[0][1]))
            focal = px * args.mesafe / args.boyut
            txt = f"piksel={px:.1f}  ->  FOCAL_PX = {focal:.1f}"
            cv2.putText(frame, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0), 2)
            print(f"\nSONUC: {txt}")
            print("Bu degeri algi.py -> FOCAL_PX'e yaz (veya DERINMAVI_FOCAL env).")

        cv2.imshow("kalibrasyon", frame)
        k = cv2.waitKey(30) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("r"):
            noktalar.clear()
            frozen = None
        if k == ord("s"):     # kareyi dondur (titremeden tiklamak icin)
            frozen = frame.copy() if frozen is None else None

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
