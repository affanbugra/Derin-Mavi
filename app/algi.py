# -*- coding: utf-8 -*-
"""DERIN MAVI - Algi cekirdegi (perception core).

Kamera + YOLO tespit + RENK ile dost/dusman + bilinen-boyut mesafe mantiginin
TEK KAYNAGI. Hem native arayuz (arayuz_qt.py) hem baska moduller bunu kullanir;
kod tekrari olmaz. Donanim-bagimsizdir (bkz. CLAUDE.md ilke 7).

Kamera kaynagi: DERINMAVI_CAM env (index / dosya / RTSP-URL); tanimsizsa otomatik tarama.
"""
import os
import time
import threading
import cv2
import numpy as np

# QMediaDevices icin lazy import (PySide6.QtMultimedia)
_qmedia_ready = False

def _ensure_qmedia():
    """QMediaDevices'i kullanmak icin QApplication gerekir; arayuz varsa zaten olusturulmustur."""
    global _qmedia_ready
    if _qmedia_ready:
        return True
    try:
        from PySide6.QtMultimedia import QMediaDevices  # noqa: F401
        _qmedia_ready = True
        return True
    except ImportError:
        return False

from renk_analizi import taraf_tespit

# ---------------- Sabitler (sartname) ----------------
# Ekran adlari. TARAF tipe DEGIL renge baglidir (kirmizi=dusman, cyan=dost).
DISPLAY = {"f16": "F-16", "helikopter": "Helikopter", "drone": "İHA", "fuze": "Füze"}
DISPLAY_CV = {"f16": "F-16", "helikopter": "Helikopter", "drone": "IHA", "fuze": "Fuze"}

# Asama-3 imha menzilleri (m), tipe gore. 10-15 m bandi TUM tipler icin ortak gecerli.
MENZIL = {"f16": (10.0, 15.0), "helikopter": (5.0, 15.0),
          "fuze": (5.0, 15.0), "drone": (0.0, 15.0)}

# Hedeflerin gercek boyutlari (m) — sartname tablosu. Monokuler mesafe icin.
GERCEK_BOYUT = {"f16": 0.50, "helikopter": 0.50, "drone": 0.30, "fuze": 0.40}

# Kamera odak uzakligi (piksel). mesafe_kalibrasyon.py ile olculur.
# DIKKAT: kalibre edilmeden mesafeler YAKLASIKTIR. Env ile makineye ozel gecilebilir.
FOCAL_PX = float(os.environ.get("DERINMAVI_FOCAL", "900"))

FLOOR = 0.35   # YENI takip baslatmak icin esik. Zaten takipteki (ID'li) kutular bunun
               # altinda da gosterilir (ByteTrack onayladi) -> titremeyi bu onler, esik degil.
INFER_IMGSZ = 640   # cikarim cozunurlugu (kucuk/uzak nesne icin 512->640; 15 m dayanikliligi)

# BGR renkler (arayuz cizimleri)
RED = (32, 32, 191)      # dusman
BLUE = (168, 88, 18)     # dost
GRAY = (140, 140, 140)   # bilinmeyen taraf
YELLOW = (60, 200, 235)  # balon (nisan noktasi)

CAM_SOURCE = os.environ.get("DERINMAVI_CAM", "").strip()

# Windows'ta DSHOW ONCE denenir: acilisi MSMF'ten cok daha hizlidir (~0.2s vs ~2-5s).
# Kamera DSHOW'da siyah verirse (bazi dahili kameralar) MSMF'e otomatik dusulur.
if os.name == "nt":
    _BACKENDS = [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF")]
else:
    _BACKENDS = [(cv2.CAP_ANY, "ANY")]

_cached_open = None
AKTIF_INDEX = None   # su an acik olan kamera index'i (arayuz secim listesi icin)


# ---------------- Kamera (donanim-bagimsiz) ----------------
AC_TIMEOUT = 4.0   # tek bir VideoCapture acilisi icin ust sinir (sn) — asla asili kalma


def _grab_gercek(cap):
    """Kameradan gercek (siyah olmayan) kare gelip gelmedigini hizlica test eder."""
    for _ in range(5):
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 3:
            return True
    return False


def _ac_timeout(idx, backend, timeout=AC_TIMEOUT):
    """VideoCapture'i zaman asimiyla acar. Acilis takilirsa (or. MSMF+OBSBOT 21s)
    None doner; takilan cap arka planda serbest birakilir. Boylece UI asla donmaz."""
    kutu = {}

    def _worker():
        cap = cv2.VideoCapture(idx, backend)
        if kutu.get("iptal"):
            cap.release()
        else:
            kutu["cap"] = cap

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():          # sure asildi
        kutu["iptal"] = True
        return None
    return kutu.get("cap")


def _dene(idx, backend, ad):
    """idx+backend'i zaman asimiyla acar; gercek kare verirse cap, yoksa None."""
    global AKTIF_INDEX
    cap = _ac_timeout(idx, backend)
    if cap is not None and cap.isOpened() and _grab_gercek(cap):
        print(f"Kamera acildi: index {idx}, backend {ad}")
        AKTIF_INDEX = idx
        return cap
    if cap is not None:
        cap.release()
    return None


def _ac_index(idx):
    """Belirli index'i acar: once DSHOW (hizli), sonra MSMF (yavas, son care)."""
    for backend, ad in _BACKENDS:
        cap = _dene(idx, backend, ad)
        if cap is not None:
            return cap
    return None


def _guzel_kamera_adi(raw: str) -> str:
    """Ham aygit adini kullanici dostu Turkce isme cevirir.

    Ornekler:
        'ov9734_techfront_camera'          -> 'PC Kamerası'
        'Integrated Camera'                -> 'PC Kamerası'
        'OBSBOT Meet SE StreamCamera'      -> 'USB Kamera · OBSBOT Meet SE'
        'USB2.0 HD UVC WebCam'             -> 'USB Kamera'
        'DroidCam Source 3'                -> 'Telefon Kamerası · DroidCam'
        'e2eSoft iVCam'                    -> 'Telefon Kamerası · iVCam'
        'OBS Virtual Camera'               -> 'Sanal Kamera · OBS'
    """
    low = raw.lower().replace("_", " ")

    # --- Telefon kamera uygulamalari ---
    if "droidcam" in low:
        return "Telefon Kamerası · DroidCam"
    if "ivcam" in low:
        return "Telefon Kamerası · iVCam"
    if "iriun" in low:
        return "Telefon Kamerası · Iriun"
    if "epoccam" in low:
        return "Telefon Kamerası · EpocCam"
    if "camo" in low and "virtual" not in low:
        return "Telefon Kamerası · Camo"

    # --- Sanal kameralar ---
    if "obs virtual" in low or "obs-virtual" in low:
        return "Sanal Kamera · OBS"
    if "virtual" in low:
        return "Sanal Kamera"

    # --- Dahili / entegre kameralar ---
    dahili_ipuclari = ("integrated", "built-in", "facetime", "techfront",
                       "ov9734", "ov5693", "ov2740", "front camera",
                       "ir camera", "laptop", "notebook")
    if any(k in low for k in dahili_ipuclari):
        if "ir " in low or "infrared" in low:
            return "PC Kamerası · IR"
        return "PC Kamerası"

    # --- USB / harici kameralar ---
    # Marka adini cikar: bilinen teknik son ekleri kaldir
    temizle = raw
    for suf in ("StreamCamera", "Stream Camera", "WebCam", "Webcam",
                "webcam", "HD UVC", "UVC", "USB2.0", "USB 2.0",
                "USB3.0", "USB 3.0", "Video", "Camera", "camera",
                "Cam", "cam", "Source", "Pro", "HD"):
        temizle = temizle.replace(suf, "")
    marka = " ".join(temizle.split()).strip(" -·.,")

    if marka:
        return f"USB Kamera · {marka}"
    return "USB Kamera"


def kameralari_listele_qt():
    """QMediaDevices ile sistemdeki TUM kameralari gercek isimleriyle listeler.

    Doner: [{"index": int, "name": str, "is_default": bool}, ...]
    Her kamera icin OpenCV index'i eslestirilir (Windows'ta QMediaDevices sirasi
    genellikle OpenCV MSMF backend sirasi ile aynidir).
    """
    if not _ensure_qmedia():
        return []
    try:
        from PySide6.QtMultimedia import QMediaDevices
        cams = QMediaDevices.videoInputs()
        sonuc = []
        for i, cam in enumerate(cams):
            sonuc.append({
                "index": i,
                "name": _guzel_kamera_adi(cam.description()),
                "is_default": cam.isDefault(),
            })
        return sonuc
    except Exception:
        return []


def kameralari_listele(max_idx=5, haric=()):
    """Eski OpenCV index taramasi (fallback). Yeni kod kameralari_listele_qt() kullanir."""
    bulunan = []
    for i in range(max_idx):
        if i in haric:
            continue
        for backend, _ in _BACKENDS:
            cap = cv2.VideoCapture(i, backend)
            ok = cap.isOpened()
            cap.release()
            if ok:
                bulunan.append(i)
                break
    return bulunan


def ac_kaynak(idx):
    """Belirli bir kamera index'ini acar (arayuzden secim icin) ve hatirlar."""
    global _cached_open
    cap = _ac_index(idx)
    if cap is not None:
        _cached_open = idx
    return cap


def _aday_indexler():
    """Denenecek kamera index'lerini oncelik sirasiyla: USB/harici once, PC sona."""
    idxs = []
    qt_cams = kameralari_listele_qt()
    if qt_cams:
        sirali = sorted(qt_cams, key=lambda c: 1 if "PC Kamerası" in c["name"] else 0)
        idxs = [c["index"] for c in sirali]
    for i in range(4):   # QMediaDevices eksikse/bulamazsa tamamla
        if i not in idxs:
            idxs.append(i)
    return idxs


def open_camera():
    """Kamera kaynagini DINAMIK ve HIZLI cozer.

    Oncelik: env override -> onceki calisan -> IKI FAZLI tarama.
    Iki fazli tarama: once TUM indexler DSHOW ile (her biri ~0.5s), calisan
    ilkini al; hicbiri olmazsa MSMF ile (yavas ama zaman-asimli, son care).
    Boylece kotu/siyah veren bir kamera (or. MSMF'te 21s asilan OBSBOT) tum
    acilisi kilitlemez.
    """
    global _cached_open
    # 1. env override (index / dosya / URL)
    if CAM_SOURCE:
        if CAM_SOURCE.isdigit():
            cap = _ac_index(int(CAM_SOURCE))
            if cap is not None:
                _cached_open = int(CAM_SOURCE)
                return cap
        else:
            cap = cv2.VideoCapture(CAM_SOURCE)
            if cap.isOpened() and _grab_gercek(cap):
                print(f"Kamera acildi: kaynak {CAM_SOURCE}")
                return cap
            cap.release()
    # 2. onceki calisan index (hizli yeniden baglanma)
    if _cached_open is not None:
        cap = _ac_index(_cached_open)
        if cap is not None:
            return cap
    # 3. iki fazli tarama: faz1 = tum indexler DSHOW, faz2 = tum indexler MSMF
    adaylar = _aday_indexler()
    for backend, ad in _BACKENDS:          # _BACKENDS = [DSHOW(hizli), MSMF(yavas)]
        for idx in adaylar:
            cap = _dene(idx, backend, ad)
            if cap is not None:
                _cached_open = idx
                return cap
    return None


# ---------------- Mesafe ----------------
# DIKKAT: MESAFE OZELLIGI GECICI OLARAK DEVRE DISI (18.07.2026, kullanici karari).
# FOCAL_PX kalibre edilmeden uretilen sayilar YANILTICI oldugu icin (or. "12.4 m" gercekte
# olcum degil, kaba tahmin) UI'dan ve karar zincirinden CIKARILDI. Asagidaki fonksiyon ve
# MENZIL/GERCEK_BOYUT/FOCAL_PX sabitleri, gercek mesafe olcum ozelligi (kalibrasyon + belki
# stereo/derinlik) eklenene kadar KULLANILMIYOR; sartname kurallarini (imha menzil tablosu)
# ve gelecekteki entegrasyonu belgelemek icin korunuyor. Yeniden aktif etmek icin analiz_et
# icinde est_distance()/MENZIL cagrisini geri ekleyin.
def est_distance(cls, box_px):
    """Bilinen gercek boyuttan monokuler mesafe: d = boyut * odak / piksel_boyut.
    NOT: su an analiz_et() tarafindan CAGRILMIYOR (yukaridaki notu okuyun)."""
    x1, y1, x2, y2 = box_px
    boyut_px = max(x2 - x1, y2 - y1)
    if boyut_px <= 0:
        return 25.0
    d = GERCEK_BOYUT.get(cls, 0.5) * FOCAL_PX / boyut_px
    return float(np.clip(round(d, 1), 0.5, 30.0))


# ---------------- Takip (ByteTrack tabanli, KARARLI) ----------------
# model.track(persist=True) ByteTrack ile her nesneye kalici bir ID verir ve kisa
# kayiplarda takibi surdurur. KENDI coasting/EMA katmanimizi TUTMUYORUZ (o yol
# hayalet + cift kutu + gecikme yaratiyordu). Bunun yerine dogrudan ByteTrack'in
# O KAREDEKI kutusunu cizeriz -> kutu her zaman nesnenin GERCEK/ANLIK yerinde,
# gecikme yok, hayalet yok, cift kutu yok.
#
# Titremeyi onleyen kilit fikir: bir kutunun takip ID'si varsa ByteTrack onu
# ONAYLAMISTIR; guveni FLOOR altinda olsa bile GOSTERIRIZ (eski kod bunlari
# gizleyip titretiyordu). ID yoksa (ilk kare/zayif) FLOOR ile gurultu elenir.
#
# Taraf hafizasi: yalniz RENK karari icin (kutu konumuna DOKUNMAZ). Her ID'nin son
# "kesin" tarafini hatirlariz ki renk bir an okunamayinca dost/dusman yanip sonmesin.
_taraf_hafiza = {}   # id -> son bilinen kesin taraf ("Düşman"/"Dost")


def takip_sifirla():
    """Takip yardimci hafizasini temizler (or. kamera degisince cagirilir)."""
    _taraf_hafiza.clear()


# ---------------- Tespit + karar ----------------
def analiz_et(model, frame, estop=False):
    """Bir kareyi analiz eder. Doner: (dets, balonlar, active_idx).

    dets: her biri {cls, ad, tip, conf, box, id}  (id = ByteTrack takip kimligi veya None)
    balonlar: [(x1,y1,x2,y2), ...]  (nisan noktalari)
    active_idx: kilitlenen dusman index'i; estop veya hedef yoksa -1.

    Kutular ByteTrack'in ANLIK ciktisidir: nesnenin gercek yerinde, gecikmesiz.
    Takip ID'li kutular dusuk guvende de gosterilir -> titremez, hayalet/cift kutu olmaz.
    """
    results = model.track(frame, persist=True, conf=0.25, imgsz=INFER_IMGSZ,
                          tracker="bytetrack.yaml", verbose=False)
    r = results[0]
    balonlar = []
    dets = []
    if r.boxes is not None:
        for b in r.boxes:
            cls = r.names[int(b.cls)]
            conf = float(b.conf)
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            tid = int(b.id.item()) if b.id is not None else None
            if cls == "balon":
                if conf >= FLOOR or tid is not None:
                    balonlar.append((x1, y1, x2, y2))
                continue
            if cls not in DISPLAY:
                continue
            # Takip ID'si varsa ByteTrack onaylamis -> dusuk conf'ta da goster (titremez).
            # ID yoksa (ilk kare / zayif tespit) FLOOR ile gurultuyu ele.
            if tid is None and conf < FLOOR:
                continue
            taraf, _ = taraf_tespit(frame, (x1, y1, x2, y2), cls)   # SARTNAME: taraf = renk
            # Taraf yumusatma (yalniz renk karari; kutu konumuna dokunmaz):
            if tid is not None:
                if taraf == "Bilinmeyen" and tid in _taraf_hafiza:
                    taraf = _taraf_hafiza[tid]
                elif taraf in ("Düşman", "Dost"):
                    _taraf_hafiza[tid] = taraf
            dets.append({"cls": cls, "ad": DISPLAY[cls], "tip": taraf,
                         "conf": int(round(conf * 100)), "box": (x1, y1, x2, y2), "id": tid})

    # aktif hedef: yalnizca DUSMAN kilitlenir. E-Stop'ta kilit YOK.
    active_idx = -1
    if not estop and dets:
        dusmanlar = [i for i, d in enumerate(dets) if d["tip"] == "Düşman"]
        if dusmanlar:
            active_idx = max(dusmanlar, key=lambda i: dets[i]["conf"])
    return dets, balonlar, active_idx


def draw_overlay(frame, dets, active_idx, balonlar=(), estop=False):
    """BGR kareye kutu + etiket + nisan cizer."""
    for bx in balonlar:
        x1, y1, x2, y2 = bx
        cv2.rectangle(frame, (x1, y1), (x2, y2), YELLOW, 1, cv2.LINE_AA)
        cv2.putText(frame, "BALON", (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, YELLOW, 1, cv2.LINE_AA)
    for i, d in enumerate(dets):
        enemy = d["tip"] == "Düşman"
        color = RED if enemy else (BLUE if d["tip"] == "Dost" else GRAY)
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        # Kutu etiketi: taraf BILINIYORSA "Dusman/Dost - Tip - %..", bilinmiyorsa
        # kalabalik yapmamak icin SADECE tip adi ("Helikopter - %..") yazilir.
        # Dost/dusman/bilinmiyor bilgisi yan paneldeki tespit tablosunda (TIP kolonu) gorunur.
        tip_cv = {"Düşman": "Dusman", "Dost": "Dost"}.get(d["tip"])
        ad_cv = DISPLAY_CV.get(d['cls'], d['cls'])
        txt = f"{tip_cv} - {ad_cv} - %{d['conf']}" if tip_cv else f"{ad_cv} - %{d['conf']}"
        f, fs, ft = cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        (tw, th), _ = cv2.getTextSize(txt, f, fs, ft)
        ly = max(y1, th + 10)
        cv2.rectangle(frame, (x1, ly - th - 8), (x1 + tw + 12, ly), color, -1, cv2.LINE_AA)
        cv2.putText(frame, txt, (x1 + 6, ly - 4), f, fs, (255, 255, 255), ft, cv2.LINE_AA)
        # aktif dusman icin nisan reticle (E-Stop'ta cizilmez)
        if i == active_idx and enemy and not estop:
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.circle(frame, (cx, cy), 16, color, 2, cv2.LINE_AA)
            cv2.line(frame, (cx - 22, cy), (cx + 22, cy), color, 1, cv2.LINE_AA)
            cv2.line(frame, (cx, cy - 22), (cx, cy + 22), color, 1, cv2.LINE_AA)
    return frame
