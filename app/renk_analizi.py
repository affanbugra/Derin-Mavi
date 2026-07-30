# -*- coding: utf-8 -*-
"""Dost/Dusman ayrimi — sartname kurali: ayrim RENK ile yapilir.

  Dusman = Kirmizi  #F50A0A      Dost = Camgobegi #00A3E0

Binary karar: kutu icinde cyan mi kirmizi mi baskin? Arasi yok. Tip (model) ile
taraf (renk) AYRI adimlardir — tipe bakan hicbir kural yoktur.
Yalniz Asama 3'te calisir; Asama 1-2'de tum maketler kirmizi, dost yok.

Kullanim (algi.py):
    kirmizi_orani, cyan_orani = renk_oranlari(frame_bgr, (x1, y1, x2, y2))
"""
import cv2
import numpy as np

# --- HSV esikleri (OpenCV: H 0-180, S/V 0-255) ---
# Kirmizi #F50A0A -> H~0; kirmizi HSV'de iki banda bolunur (0 civari ve 180 civari)
KIRMIZI_ALT_1 = np.array([0, 110, 60])
KIRMIZI_UST_1 = np.array([12, 255, 255])
KIRMIZI_ALT_2 = np.array([168, 110, 60])
KIRMIZI_UST_2 = np.array([180, 255, 255])
# Camgobegi #00A3E0 -> H = 196.5/2 ≈ 98
CYAN_ALT = np.array([85, 90, 70])
CYAN_UST = np.array([112, 255, 255])

KENAR_PAY = 0.12  # kutunun kenarindan icve dogru kirpma orani (arka plan sizmasini azaltir)


def _ic_bolge(frame, box):
    x1, y1, x2, y2 = box
    h, w = frame.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * KENAR_PAY), int(bh * KENAR_PAY)
    ax1, ay1 = max(0, x1 + px), max(0, y1 + py)
    ax2, ay2 = min(w, x2 - px), min(h, y2 - py)
    if ax2 - ax1 < 4 or ay2 - ay1 < 4:
        ax1, ay1 = max(0, x1), max(0, y1)
        ax2, ay2 = min(w, x2), min(h, y2)
    return frame[ay1:ay2, ax1:ax2]


def renk_oranlari(frame_bgr, box):
    """Kutu ic bolgesindeki kirmizi ve cyan piksel oranlarini dondurur (0..1)."""
    roi = _ic_bolge(frame_bgr, box)
    if roi.size == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m_kirmizi = cv2.inRange(hsv, KIRMIZI_ALT_1, KIRMIZI_UST_1) | \
                cv2.inRange(hsv, KIRMIZI_ALT_2, KIRMIZI_UST_2)
    m_cyan = cv2.inRange(hsv, CYAN_ALT, CYAN_UST)
    n = roi.shape[0] * roi.shape[1]
    return float(np.count_nonzero(m_kirmizi)) / n, float(np.count_nonzero(m_cyan)) / n


if __name__ == "__main__":
    # Kendi kendine test: sentetik kirmizi/cyan kareler dogru oranlari vermeli.
    # (Taraf karari algi._taraf_belirle icinde verilir; burada olculen oranlardir.)
    kirmizi_img = np.full((100, 100, 3), (10, 10, 245), np.uint8)     # BGR kirmizi
    cyan_img = np.full((100, 100, 3), (224, 163, 0), np.uint8)        # BGR cyan
    kutu = (0, 0, 100, 100)

    k, c = renk_oranlari(kirmizi_img, kutu)
    assert k > 0.9 and c < 0.01, (k, c)
    k, c = renk_oranlari(cyan_img, kutu)
    assert c > 0.9 and k < 0.01, (k, c)

    print("renk_analizi testleri OK — kirmizi ve cyan oranlari dogru olculuyor")
