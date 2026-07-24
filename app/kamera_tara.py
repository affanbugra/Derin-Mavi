# -*- coding: utf-8 -*-
"""Hangi kamera index+backend'inin gercek goruntu verdigini tarar."""
import cv2

backends = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF), ("ANY", cv2.CAP_ANY)]
print("Kamera taraniyor...\n")
bulunan = []
for idx in range(4):
    for ad, be in backends:
        cap = cv2.VideoCapture(idx, be)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = False, None
        for _ in range(6):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        if ok and frame is not None:
            ort = float(frame.mean())
            durum = "OK (goruntu var)" if ort > 1 else "SIYAH (ort=0)"
            print(f"  index {idx} / {ad:6} -> {frame.shape}  {durum}  parlaklik={ort:.1f}")
            if ort > 1:
                bulunan.append((idx, ad))
        else:
            print(f"  index {idx} / {ad:6} -> acildi ama KARE OKUNAMADI")
        cap.release()

print()
if bulunan:
    idx, ad = bulunan[0]
    print(f"KULLAN: index {idx} ({ad}).  DERINMAVI_CAM={idx} env ile sabitleyebilirsin.")
else:
    print("HIC CALISAN KAMERA YOK. Olasi sebepler:")
    print(" - Baska bir uygulama kamerayi kullaniyor (Zoom/Teams/Kamera app) -> kapat")
    print(" - Windows gizlilik: Ayarlar > Gizlilik > Kamera > 'Masaustu uygulamalari' ACIK olmali")
    print(" - Harici kamera takiliysa kablosunu kontrol et")
