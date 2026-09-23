# -*- coding: utf-8 -*-
"""Birlesik arayuzun Qt kamera yolunu motor/model olmadan olcer.

Kullanim:
    python app/kamera_pasif_test.py --sure 5
    python app/kamera_pasif_test.py --sure 5 --kare C:/.../kare.jpg

ESP/seri portu, model ve lazer acilmaz. Uygulamanin kullandigi ``kamera.Kamera``
sinifini birebir kullanir; format secimi ve kare zaman damgasi bu yolla dogrulanir.
"""
import argparse
from pathlib import Path
import statistics
import sys
import time

import cv2
from PySide6.QtCore import QCoreApplication, QTimer

from kamera import Kamera


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sure", type=float, default=5.0)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--kare", type=Path, default=None)
    args = ap.parse_args()

    app = QCoreApplication(sys.argv[:1])
    kaynak = Kamera()
    kaynak.istenen = (1280, 720, max(1, args.fps))
    durumlar = []
    kaynak.durum.connect(lambda mesaj, hata: durumlar.append((mesaj, hata)))

    son_sira = None
    zamanlar, yaslar, parlakliklar = [], [], []
    son_kare = [None]
    bas = time.monotonic()

    def yokla():
        nonlocal son_sira
        kare, sira, kare_t = kaynak.oku_zamanli(son_sira)
        if kare is not None:
            son_sira = sira
            simdi = time.time()
            zamanlar.append(kare_t)
            yaslar.append(max(0.0, (simdi - kare_t) * 1000.0))
            parlakliklar.append(float(kare.mean()))
            son_kare[0] = kare.copy()
        if time.monotonic() - bas >= max(1.0, args.sure):
            kaynak.durdur()
            app.quit()

    timer = QTimer()
    timer.timeout.connect(yokla)
    timer.start(2)
    kaynak.baslat()
    app.exec()

    for mesaj, hata in durumlar:
        print(("HATA: " if hata else "") + mesaj)
    if not zamanlar or son_kare[0] is None:
        raise SystemExit("Kare alinamadi.")
    sure = max(1e-6, zamanlar[-1] - zamanlar[0])
    fps = (len(zamanlar) - 1) / sure if len(zamanlar) > 1 else 0.0
    h, w = son_kare[0].shape[:2]
    print(f"Gercek kare: {w}x{h} | callback {fps:.1f} FPS | adet {len(zamanlar)}")
    print(f"Kare yasi medyan {statistics.median(yaslar):.2f} ms | "
          f"P95 {sorted(yaslar)[int(0.95 * (len(yaslar) - 1))]:.2f} ms | "
          f"parlaklik medyan {statistics.median(parlakliklar):.1f}")
    if args.kare is not None:
        args.kare.parent.mkdir(parents=True, exist_ok=True)
        # OpenCV'nin Windows `imwrite` yolu ASCII disi karakterlerde (Masaustu gibi)
        # basarisiz olabiliyor. Encode edip pathlib ile yazmak Unicode yolu korur.
        uzanti = args.kare.suffix or ".jpg"
        ok, kodlu = cv2.imencode(uzanti, son_kare[0])
        if not ok:
            raise SystemExit(f"Kare yazilamadi: {args.kare}")
        args.kare.write_bytes(kodlu.tobytes())
        print(f"Kare kaydedildi: {args.kare}")


if __name__ == "__main__":
    main()
