# -*- coding: utf-8 -*-
"""Dost/Dusman ayrimi — SARTNAME kurali: ayrim RENK ile yapilir.

  Dusman = Kirmizi  #F50A0A
  Dost   = Camgobegi #00A3E0

Aynı F16/Helikopter hem dost hem dusman olabilir -> tip tek basina taraf soylemez.
Balon rengi iki tarafta da AYNIDIR -> analiz maket GOVDE renginden yapilir.

YOLO kutusunun ic bolgesinde HSV maskeleriyle kirmizi/cyan piksel orani olculur.
Deterministik ve aciklanabilir: modelin renk ogrenmesine guvenmek yerine kesin kural.

Kullanim:
    from renk_analizi import taraf_tespit
    taraf, guven = taraf_tespit(frame_bgr, (x1, y1, x2, y2))
    # taraf: "Düşman" | "Dost" | "Bilinmeyen"   guven: 0..1 arasi baskin renk orani
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

MIN_ORAN = 0.06   # kutu icinde bu orandan az renk varsa "Bilinmeyen" (arka plan gurultusu)
KENAR_PAY = 0.12  # kutunun kenarindan icve dogru kirpma orani (arka plan sizmasini azaltir)

# Sartname: IHA (drone) ve Fuze YALNIZCA dusman olarak tanimli.
# Renk okunamazsa bu tipler icin guvenli varsayilan dusmandir.
HEP_DUSMAN = {"drone", "fuze"}


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


def taraf_tespit(frame_bgr, box, cls=None):
    """Taraf karari.

    Args:
        frame_bgr: BGR kare
        box: (x1, y1, x2, y2) piksel
        cls: YOLO sinif adi (opsiyonel; drone/fuze icin guvenli varsayilan)

    Returns:
        (taraf, guven): taraf "Düşman"/"Dost"/"Bilinmeyen"; guven = baskin renk orani
    """
    kirmizi, cyan = renk_oranlari(frame_bgr, box)

    if kirmizi >= MIN_ORAN and kirmizi > cyan * 1.3:
        return "Düşman", kirmizi
    if cyan >= MIN_ORAN and cyan > kirmizi * 1.3:
        return "Dost", cyan

    # Renk belirsiz: IHA/Fuze sartname geregi hep dusman; digerleri bilinmeyen.
    # Bilinmeyen'e ATES EDILMEZ (dost vurma cezasi -10'dan kacinmak icin guvenli taraf).
    if cls in HEP_DUSMAN:
        return "Düşman", max(kirmizi, cyan)
    return "Bilinmeyen", max(kirmizi, cyan)


if __name__ == "__main__":
    # hizli kendi kendine test: sentetik kirmizi/cyan kutularla dogrula
    for ad, bgr in (("kirmizi", (10, 10, 245)), ("cyan", (224, 163, 0))):
        img = np.full((100, 100, 3), bgr, np.uint8)
        taraf, g = taraf_tespit(img, (0, 0, 100, 100))
        print(f"{ad}: {taraf} (guven {g:.2f})")
