# -*- coding: utf-8 -*-
"""Dost/Dusman ayrimi — sartname kurali: ayrim RENK ile yapilir.

  Dusman = Kirmizi  #F50A0A      Dost = Camgobegi #00A3E0

Binary karar: kutu icinde cyan mi kirmizi mi baskin? Arasi yok. Tip (model) ile
taraf (renk) AYRI adimlardir — tipe bakan hicbir kural yoktur.
Yalniz Asama 3'te calisir; Asama 1-2'de tum maketler kirmizi, dost yok.

⚠ BALON TUZAGI (sartname V1.4 §5.4, 23.06.2026): **TUM** maketlerin ALTINA
**KIRMIZI** balon baglanir — dost maketin altindaki balon da kirmizidir. Renk
kutunun TAMAMINDAN olculseydi, dost (mavi) bir maketin kutusuna sizan balon
pikselleri tarafi "Dusman" gosterebilir ve sistem DOST HEDEFE ATES ederdi
(Asama-3'te -10 puan). Bu yuzden renk yalnizca kutunun UST kismindan
(GOVDE_ORANI) okunur: balon her zaman govdenin ALTINDADIR.

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
# Kutunun UST'ten ne kadari "govde" sayilir. Kalan alt kisim balona ait olabilir
# (bkz. modul basligindaki BALON TUZAGI). 0.70 = ust %70. Modelin kutusu balonu
# hic icermiyorsa bu deger zararsizdir: olculen yine govdedir.
GOVDE_ORANI = 0.70


def _ic_bolge(frame, box, govde_orani=GOVDE_ORANI):
    x1, y1, x2, y2 = box
    h, w = frame.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * KENAR_PAY), int(bh * KENAR_PAY)
    ax1, ay1 = max(0, x1 + px), max(0, y1 + py)
    ax2, ay2 = min(w, x2 - px), min(h, y2 - py)
    # Alt siniri govde oranina cek (balon disarida kalsin)
    ay2 = min(ay2, max(0, y1 + int(bh * float(govde_orani))))
    if ax2 - ax1 < 4 or ay2 - ay1 < 4:      # kutu cok kucuk: kirpmadan olc
        ax1, ay1 = max(0, x1), max(0, y1)
        ax2, ay2 = min(w, x2), min(h, y2)
    return frame[ay1:ay2, ax1:ax2]


def renk_oranlari(frame_bgr, box, govde_orani=GOVDE_ORANI):
    """Kutunun GOVDE bolgesindeki kirmizi ve cyan piksel oranlari (0..1).

    `govde_orani=1.0` kutunun tamamini olcer — yalnizca teshis/karsilastirma icin;
    canli yolda kullanilmaz (balon tuzagi)."""
    roi = _ic_bolge(frame_bgr, box, govde_orani)
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
    KIRMIZI_BGR, CYAN_BGR = (10, 10, 245), (224, 163, 0)
    kirmizi_img = np.full((100, 100, 3), KIRMIZI_BGR, np.uint8)
    cyan_img = np.full((100, 100, 3), CYAN_BGR, np.uint8)
    kutu = (0, 0, 100, 100)

    k, c = renk_oranlari(kirmizi_img, kutu)
    assert k > 0.9 and c < 0.01, (k, c)
    k, c = renk_oranlari(cyan_img, kutu)
    assert c > 0.9 and k < 0.01, (k, c)

    # ⚠ BALON TUZAGI: DOST (mavi) maket + ALTINDA kirmizi balon. Kucuk bir maketin
    # (or. 30 cm İHA) altindaki balon kutunun yarisindan fazlasini kaplayabilir —
    # en zorlayici ve gercekci hal budur: ust %45 govde, alt %55 balon.
    dost = np.zeros((100, 100, 3), np.uint8)
    dost[:45] = CYAN_BGR
    dost[45:] = KIRMIZI_BGR
    k, c = renk_oranlari(dost, kutu)
    assert c > k, f"dost maket kirmizi balon yuzunden dusman goruldu: kirmizi={k:.2f} cyan={c:.2f}"

    # Ayni kare kutunun TAMAMINDAN olculseydi karar TERSINE donerdi — duzeltmenin
    # gercekten is gordugunu bu satir kanitlar (govde_orani=1.0 eski davranistir).
    k_eski, c_eski = renk_oranlari(dost, kutu, govde_orani=1.0)
    assert k_eski > c_eski, "eski davranis artik hatayi uretmiyor (test degerini yitirdi)"

    # DUSMAN (kirmizi) maket + kirmizi balon: karar degismemeli
    dusman = np.zeros((100, 100, 3), np.uint8)
    dusman[:] = KIRMIZI_BGR
    k, c = renk_oranlari(dusman, kutu)
    assert k > 0.9 and c < 0.01, (k, c)

    # Cok kucuk kutu: kirpma sonrasi bolge bosalmamali (uzak hedef)
    k, c = renk_oranlari(cyan_img, (10, 10, 18, 16))
    assert c > 0.5, (k, c)

    print("renk_analizi testleri OK — oranlar, BALON TUZAGI (dost+kirmizi balon), "
          "kucuk kutu")
