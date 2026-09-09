# -*- coding: utf-8 -*-
"""SAHI Test Scripti — Normal YOLO vs SAHI yan yana karsilastirma.

Kullanim:
    python app/sahi_test.py

Canli kameradan kare alip sol tarafta normal YOLO, sag tarafta SAHI
tespitlerini gosterir. FPS farki ekranda gorulur.

Dilim boyutu ve ortusme orani arguman olarak verilebilir:
    python app/sahi_test.py --dilim 640 --ortusme 0.2
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

# Proje kok dizinini ekle (algi modulu icin)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MODELS_DIR = os.path.abspath(os.path.join(HERE, "..", "models"))

from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction, get_prediction
from ultralytics import YOLO

import algi


def model_yolu_bul():
    """Mevcut en iyi modeli bulur (algi.py mantigiyla uyumlu)."""
    for aday in ("best.pt",):
        p = os.path.join(MODELS_DIR, aday)
        if os.path.isfile(p):
            return p
    return None


def kutu_ciz(frame, kutular, renk, etiket_prefix=""):
    """Tespit kutularini cizer."""
    for k in kutular:
        x1, y1, x2, y2 = k["box"]
        conf = k["conf"]
        ad = k.get("ad", "?")
        cv2.rectangle(frame, (x1, y1), (x2, y2), renk, 2, cv2.LINE_AA)
        txt = f"{etiket_prefix}{ad} %{conf}"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        ly = max(y1 - 5, th + 10)
        cv2.rectangle(frame, (x1, ly - th - 8), (x1 + tw + 6, ly + 4), renk, -1)
        cv2.putText(frame, txt, (x1 + 3, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (255, 255, 255), 1, cv2.LINE_AA)


def normal_tespit(model, frame, conf_esik=0.25, imgsz=640):
    """Normal YOLO tespiti (model.predict)."""
    results = model.predict(frame, conf=conf_esik, imgsz=imgsz, verbose=False)
    dets = []
    r = results[0]
    if r.boxes is not None:
        for b in r.boxes:
            ham_ad = r.names[int(b.cls)]
            cls = algi.kanonik(ham_ad)
            conf = float(b.conf)
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            dets.append({
                "cls": cls,
                "ad": algi.goster_ad_cv(cls, ham_ad),
                "conf": int(round(conf * 100)),
                "box": (x1, y1, x2, y2),
            })
    return dets


def sahi_tespit(sahi_model, frame, dilim=640, ortusme=0.2, conf_esik=0.25):
    """SAHI dilimli tespit."""
    result = get_sliced_prediction(
        image=frame,
        detection_model=sahi_model,
        slice_height=dilim,
        slice_width=dilim,
        overlap_height_ratio=ortusme,
        overlap_width_ratio=ortusme,
        verbose=0,
    )
    dets = []
    for pred in result.object_prediction_list:
        bbox = pred.bbox
        x1, y1, x2, y2 = int(bbox.minx), int(bbox.miny), int(bbox.maxx), int(bbox.maxy)
        conf = pred.score.value
        ham_ad = pred.category.name
        cls = algi.kanonik(ham_ad)
        dets.append({
            "cls": cls,
            "ad": algi.goster_ad_cv(cls, ham_ad),
            "conf": int(round(conf * 100)),
            "box": (x1, y1, x2, y2),
        })
    return dets


def main():
    parser = argparse.ArgumentParser(description="SAHI vs Normal YOLO karsilastirma")
    parser.add_argument("--dilim", type=int, default=640, help="SAHI dilim boyutu (px)")
    parser.add_argument("--ortusme", type=float, default=0.2, help="Dilim ortusme orani (0-1)")
    parser.add_argument("--conf", type=float, default=0.25, help="Guven esigi")
    parser.add_argument("--imgsz", type=int, default=640, help="Normal YOLO imgsz")
    args = parser.parse_args()

    # Model bul
    model_path = model_yolu_bul()
    if model_path is None:
        print("HATA: models/ klasorunde best.pt bulunamadi!")
        sys.exit(1)
    print(f"Model: {model_path}")

    # Normal YOLO modeli
    yolo_model = YOLO(model_path)

    # SAHI modeli
    sahi_model = AutoDetectionModel.from_pretrained(
        model_type="yolov8",
        model_path=model_path,
        confidence_threshold=args.conf,
        device="cpu",
    )
    print(f"SAHI modeli yuklendi. Dilim: {args.dilim}x{args.dilim}, Ortusme: {args.ortusme}")

    # Kamera ac
    cap = algi.open_camera()
    if cap is None:
        print("HATA: Kamera acilamadi!")
        sys.exit(1)

    print("\nKontroller:")
    print("  Q / ESC  : Cikis")
    print("  D        : Dilim boyutunu degistir (480/640/800)")
    print("  O        : Ortusme oranini degistir (0.1/0.2/0.3)")
    print()

    dilim_secenekleri = [480, 640, 800]
    ortusme_secenekleri = [0.1, 0.2, 0.3]
    dilim_idx = dilim_secenekleri.index(args.dilim) if args.dilim in dilim_secenekleri else 1
    ortusme_idx = ortusme_secenekleri.index(args.ortusme) if args.ortusme in ortusme_secenekleri else 1

    fps_normal = 0.0
    fps_sahi = 0.0

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.01)
            continue

        h, w = frame.shape[:2]
        dilim = dilim_secenekleri[dilim_idx]
        ortusme = ortusme_secenekleri[ortusme_idx]

        # --- Normal YOLO ---
        t0 = time.perf_counter()
        dets_normal = normal_tespit(yolo_model, frame, args.conf, args.imgsz)
        t_normal = time.perf_counter() - t0
        fps_normal = 0.8 * fps_normal + 0.2 * (1.0 / max(t_normal, 1e-6))

        # --- SAHI ---
        t0 = time.perf_counter()
        dets_sahi = sahi_tespit(sahi_model, frame, dilim, ortusme, args.conf)
        t_sahi = time.perf_counter() - t0
        fps_sahi = 0.8 * fps_sahi + 0.2 * (1.0 / max(t_sahi, 1e-6))

        # Yan yana gosterim
        sol = frame.copy()
        sag = frame.copy()

        kutu_ciz(sol, dets_normal, (0, 200, 80))    # yesil
        kutu_ciz(sag, dets_sahi, (0, 170, 255))      # turuncu

        # Bilgi paneli
        cv2.putText(sol, f"NORMAL YOLO | {len(dets_normal)} tespit | {fps_normal:.1f} FPS",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(sol, f"NORMAL YOLO | {len(dets_normal)} tespit | {fps_normal:.1f} FPS",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 80), 1, cv2.LINE_AA)

        cv2.putText(sag, f"SAHI | {len(dets_sahi)} tespit | {fps_sahi:.1f} FPS | Dilim:{dilim} Ort:{ortusme}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(sag, f"SAHI | {len(dets_sahi)} tespit | {fps_sahi:.1f} FPS | Dilim:{dilim} Ort:{ortusme}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 170, 255), 1, cv2.LINE_AA)

        # Ayirici cizgi
        birlesik = np.hstack([sol, sag])
        cv2.line(birlesik, (w, 0), (w, h), (255, 255, 255), 2)

        # Pencereyi goster
        cv2.imshow("SAHI Karsilastirma (Q: Cikis | D: Dilim | O: Ortusme)", birlesik)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), ord('Q'), 27):  # Q veya ESC
            break
        elif key in (ord('d'), ord('D')):
            dilim_idx = (dilim_idx + 1) % len(dilim_secenekleri)
            print(f"Dilim boyutu: {dilim_secenekleri[dilim_idx]}")
        elif key in (ord('o'), ord('O')):
            ortusme_idx = (ortusme_idx + 1) % len(ortusme_secenekleri)
            print(f"Ortusme orani: {ortusme_secenekleri[ortusme_idx]}")

    cap.release()
    cv2.destroyAllWindows()
    print("Test bitti.")


if __name__ == "__main__":
    main()
