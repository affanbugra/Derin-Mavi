# -*- coding: utf-8 -*-
"""DERIN MAVI - Algi cekirdegi (perception core).

Kamera + YOLO tespit + RENK ile dost/dusman mantiginin TEK KAYNAGI. Arayuz
(arayuz_qt.py) bunu kullanir. Donanim-bagimsizdir (bkz. CLAUDE.md ilke 7).

Kamera kaynagi: DERINMAVI_CAM env (index / dosya / RTSP-URL); tanimsizsa otomatik tarama.
"""
import os
import time
import tempfile
import threading
import cv2

from renk_analizi import renk_oranlari

_qmedia_ready = False


def _ensure_qmedia():
    """QMediaDevices kullanilabilir mi? (PySide6.QtMultimedia lazy import)"""
    global _qmedia_ready
    if _qmedia_ready:
        return True
    try:
        from PySide6.QtMultimedia import QMediaDevices  # noqa: F401
        _qmedia_ready = True
        return True
    except ImportError:
        return False


# ---------------- Sinif adlari ----------------
# Model hangi sinifi uretirse uretsin kutu ASLA sessizce atilmaz; DISPLAY yalnizca
# "guzel Turkce ad" tablosudur, bilinmeyen sinif modelin HAM adiyla gosterilir.
# (Eski kod `if cls not in DISPLAY: continue` diyordu; model 'F16'/'iha' gibi ufak
#  bir ad farkiyla egitilmisse TUM tespitler uyarisiz yok oluyordu.)
# Anahtarlar _sadelestir()'den gecmis halleriyle yazilir. Yeni bir model farkli ad
# kullaniyorsa buraya tek satir eklemek yeterli.
DISPLAY = {"f16": "F-16", "helikopter": "Helikopter", "drone": "İHA", "fuze": "Füze"}
DISPLAY_CV = {"f16": "F-16", "helikopter": "Helikopter", "drone": "IHA", "fuze": "Fuze"}

BALON = "balon"      # nisan noktasi sinifi (CLAUDE.md §7: balon maketin ALTINDA)


def kanonik(ad):
    """Sinif adini karsilastirilabilir hale getirir: kucuk harf, ayirici yok.
    'F-16' -> 'f16' · 'Mini_Drone' -> 'minidrone'. Eslesme aranmaz, kutu atilmaz."""
    s = str(ad).strip().lower()
    for ch in ("-", "_", ".", " "):
        s = s.replace(ch, "")
    return s


def goster_ad(kanon, ham):
    """Arayuz adi: bilineni Turkce'ye cevir, bilinmeyeni HAM haliyle goster."""
    return DISPLAY.get(kanon, str(ham))


def goster_ad_cv(kanon, ham):
    """OpenCV cizimi icin ASCII ad (cv2.putText Turkce karakter basamaz)."""
    if kanon in DISPLAY_CV:
        return DISPLAY_CV[kanon]
    return str(ham).encode("ascii", "replace").decode("ascii")


def model_sinif_ozeti(model):
    """Alt cubuk teshisi: '2 sınıf · fuze, helikopter'. Arayuz 4 tip + balon vaat
    ederken model 2 sinifliysa bu gercek gizli kalmasin."""
    adlar = list(getattr(model, "names", {}).values())
    if not adlar:
        return "model sınıfları okunamadı"
    kisa = ", ".join(adlar[:6]) + ("…" if len(adlar) > 6 else "")
    return f"{len(adlar)} sınıf · {kisa}"


def eksik_siniflar(model):
    """Sartnamenin gerektirdigi ama modelde OLMAYAN siniflar (uyari icin)."""
    var = {kanonik(a) for a in getattr(model, "names", {}).values()}
    return [g for g in ("f16", "helikopter", "drone", "fuze", BALON) if g not in var]

# ---------------- Canli ayarlar (arayuzdeki "⚙" panelinden) ----------------
# Varsayilanlar ULTRALYTICS'IN KENDI VARSAYILANLARIDIR: ayarlara dokunmayan biri ham
# `yolo track source=0` ile ayni davranisi gorur. Sapmak isteyen panelden sapar.
#
# model.track()'e verilen conf KASITLI olarak dusuktur (BESLEME_CONF): ByteTrack'in
# fikri dusuk skorlu kutulari da alip ikinci asamada eslestirmektir, modele yuksek
# conf verilirse o kutular NMS'te olur. Filtreleme tracker (hassasiyet) + cizim
# (gosterim) katmanlarinda yapilir.
BESLEME_CONF = 0.10

VARSAYILAN_AYAR = {
    "hassasiyet": 0.25,     # ByteTrack new_track_thresh + track_high_thresh
    "gosterim": 0.25,       # bu guvenin altindaki kutu CIZILMEZ
    "kararlilik": 30,       # ByteTrack track_buffer: kayip kutu kac kare yasar
    "cozunurluk": 640,      # model.track(imgsz=)
    "iou": 0.70,            # NMS IoU esigi
    "maks_tespit": 300,     # kare basina en fazla kutu (max_det)
    "ayna": 0,              # goruntuyu yatay cevir. 0 = ham YOLO ile birebir ayni
    # --- nisan.py (Otonom takip geometrisi) ---
    "fov": 60.0,            # kameranin yatay gorus acisi (derece)
    "kp": 0.50,             # takip gucu: hatanin ne kadari tek adimda kapatilsin
    "kd": 0.06,             # ongoru suresi (sn) — gecikme telafisi
    "olu_bolge": 0.02,      # merkeze bu kadar yakinsa komut yok (dwell icin sart)
}
AYAR = dict(VARSAYILAN_AYAR)

# Bozuk/eski ayarlar.json degerleri sisteme sizmasin diye gecerli araliklar.
AYAR_SINIR = {
    "hassasiyet": (0.05, 0.95), "gosterim": (0.05, 0.95),
    "kararlilik": (5, 300), "cozunurluk": (320, 1280),
    "iou": (0.10, 0.95), "maks_tespit": (1, 1000),
    "ayna": (0, 1), "fov": (20.0, 140.0),
    "kp": (0.05, 1.50), "kd": (0.0, 0.50), "olu_bolge": (0.0, 0.10),
}

_ayar_kilit = threading.Lock()   # AYAR: GUI thread yazar, algi thread okur
_tracker_yeniden_kur = True      # hassasiyet/kararlilik degisince tracker yeniden kurulur

# ByteTrack ayarlarini canli degistirebilmek icin kendi yaml'imizi yazariz.
_TRACKER_YAML = os.path.join(tempfile.gettempdir(), "derinmavi_bytetrack.yaml")


def _tracker_yaml_yaz(a):
    """Guncel ayarlarla ByteTrack config'i yazar. Ultralytics varsayilan sablonu;
    yalnizca hassasiyet ve kararlilik kullanicidan gelir."""
    hass = float(a["hassasiyet"])
    with open(_TRACKER_YAML, "w", encoding="utf-8") as f:
        f.write(
            "tracker_type: bytetrack\n"
            f"track_high_thresh: {hass:.3f}\n"
            "track_low_thresh: 0.1\n"
            f"new_track_thresh: {hass:.3f}\n"
            f"track_buffer: {int(a['kararlilik'])}\n"
            "match_thresh: 0.8\n"
            "fuse_score: True\n"
        )


def ayar_al():
    """Ayarlarin o anki kopyasi. analiz_et kare basina TEK kez cagirir ki kare
    ortasinda ayar degisince yari-eski/yari-yeni karisim olusmasin."""
    with _ayar_kilit:
        return dict(AYAR)


def _kirp(k, v):
    """Bir ayar degerini gecerli araliga kirpar; cevrilemezse varsayilana doner."""
    alt, ust = AYAR_SINIR.get(k, (None, None))
    try:
        v = float(v)
    except (TypeError, ValueError):
        return VARSAYILAN_AYAR[k]
    if alt is not None:
        v = max(alt, min(ust, v))
    return int(round(v)) if isinstance(VARSAYILAN_AYAR[k], int) else v


def ayar_guncelle(**kw):
    """Arayuzden gelen ayar degisikligini uygular (canli). Bilinmeyen anahtar yok
    sayilir, bozuk deger araliga kirpilir. Tracker'i etkileyen ayar degisirse
    tracker bir sonraki karede yeniden kurulur."""
    global _tracker_yeniden_kur
    with _ayar_kilit:
        for k, v in kw.items():
            if k not in AYAR:
                continue
            yeni = _kirp(k, v)
            if k in ("kararlilik", "hassasiyet") and yeni != AYAR[k]:
                _tracker_yeniden_kur = True
            AYAR[k] = yeni

# BGR renkler (kutu cizimleri)
RED = (32, 32, 191)      # dusman (yalniz A3)
BLUE = (168, 88, 18)     # dost (yalniz A3)
HEDEF = (0, 170, 255)    # A1/A2: taraf ayrimi yok, hepsi hedef
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

# Istenen kamera formati (kamera desteklemezse OpenCV en yakinina duser).
# 640x480'de 15 m'deki 30 cm'lik IHA ~8 piksel olur, model goremez.
ISTENEN_W = int(os.environ.get("DERINMAVI_CAM_W", "1280"))
ISTENEN_H = int(os.environ.get("DERINMAVI_CAM_H", "720"))
ISTENEN_FPS = int(os.environ.get("DERINMAVI_CAM_FPS", "30"))


def _cap_ayarla(cap):
    """Acilan kameraya format + tampon ayarlarini uygular.

    BUFFERSIZE=1: OpenCV birkac kare tamponlar ve cap.read() tamponun EN ESKI
    karesini verir. Inference kameradan yavas olunca tampon dolu kalir ve goruntu
    ~200-350 ms geride gider (kutu nesnenin arkasinda kalir).
    MJPG: cogu webcam 720p'yi sikistirilmamis YUY2 ile ~10 FPS, MJPG ile 30 FPS
    verir; MJPG istenmezse cozunurluk yukseltmek kare hizini sessizce dusurur.
    SIRA: FOURCC once, cozunurluk sonra (tersi bazi surucularde yok sayilir)."""
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    except Exception:
        pass
    for prop, deger in ((cv2.CAP_PROP_BUFFERSIZE, 1),
                        (cv2.CAP_PROP_FRAME_WIDTH, ISTENEN_W),
                        (cv2.CAP_PROP_FRAME_HEIGHT, ISTENEN_H),
                        (cv2.CAP_PROP_FPS, ISTENEN_FPS)):
        try:
            cap.set(prop, deger)
        except Exception:
            pass   # her backend her prop'u desteklemez
    return cap


def kamera_bilgi(cap):
    """Kameranin GERCEKTEN verdigi format (istenen degil) — alt cubuk/teshis icin."""
    if cap is None:
        return None
    try:
        return {"w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0)}
    except Exception:
        return None


class KameraOkuyucu:
    """Kamerayi kendi thread'inde surekli okur, yalnizca EN SON kareyi tutar.

    cap.read() ana dongude cagrilirsa, inference kameradan yavas oldugu anda surucu
    tamponu dolar ve read() hep eski kareyi verir -> goruntu gecikir.
    Tampon drenaji cozum degil: grab() bloklayici oldugu icin "n kare at" yapmak
    FPS'i kamera_fps/n'e bolerdi. Ayri thread kamera hiziyla doner; oku() her zaman
    en taze kareyi verir, islenemeyen kareler atlanir."""

    def __init__(self, cap):
        self.cap = cap
        self._kare = None
        self._sira = 0            # kac kare uretildi (ayni kareyi iki kez islememek icin)
        self._kilit = threading.Lock()
        self._calis = True
        self.hata_sayaci = 0
        self._th = threading.Thread(target=self._dongu, daemon=True)
        self._th.start()

    def _dongu(self):
        while self._calis:
            cap = self.cap
            if cap is None:
                time.sleep(0.01)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                self.hata_sayaci += 1
                time.sleep(0.01)
                continue
            self.hata_sayaci = 0
            with self._kilit:
                self._kare = frame
                self._sira += 1

    def oku(self, son_sira=None):
        """En taze kareyi dondurur: (kare, sira). Yeni kare yoksa (None, sira).
        `son_sira` verilirse ayni kare tekrar islenmez."""
        with self._kilit:
            if self._kare is None or (son_sira is not None and self._sira == son_sira):
                return None, self._sira
            return self._kare, self._sira

    def cap_degistir(self, yeni_cap):
        """Kamera degisiminde (arayuzden secim) okuyucuyu yeni cap'e baglar."""
        with self._kilit:
            self._kare = None
        self.cap = yeni_cap
        self.hata_sayaci = 0

    def kapat(self):
        self._calis = False
        self._th.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()
            self.cap = None


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
    if cap is not None and cap.isOpened():
        _cap_ayarla(cap)                      # format + BUFFERSIZE=1 (A3) — test KARESINDEN ONCE
        if _grab_gercek(cap):
            bilgi = kamera_bilgi(cap) or {}
            print(f"Kamera acildi: index {idx}, backend {ad}, "
                  f"format {bilgi.get('w')}x{bilgi.get('h')} @{bilgi.get('fps')}")
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


# ---------------- Takip (ByteTrack) ----------------
# model.track(persist=True) her nesneye kalici ID verir ve kisa kayiplarda takibi
# surdurur. Kendi coasting/EMA katmanimiz YOK (hayalet + cift kutu yaratiyordu);
# dogrudan ByteTrack'in o karedeki kutusu cizilir.
#
# ID'li kutuya gosterim esiginde kucuk bir tolerans taninir: onaylanmis nesne bir
# kare zayiflayinca titremesin. Ama esik yine UYGULANIR — eski kod "ID varsa guven
# ne olursa olsun goster" diyordu ve olu tespitler track_buffer boyunca hayalet
# kutu olarak ekranda kaliyordu.
ID_TOLERANS = 0.80   # ID'li kutu icin esik bu oranla yumusatilir (0.25 -> 0.20)

# Taraf hafizasi: yalniz A3 renk karari icin, kutu konumuna DOKUNMAZ. Renk bir an
# okunamazsa son bilinen taraf korunur -> dost/dusman etiketi yanip sonmez.
_taraf_hafiza = {}   # takip id -> "Düşman" | "Dost"
_budama_sayaci = 0

RENK_ESIK = 0.02      # bu oranin altinda renk "okunamadi" sayilir
BUDAMA_PERIYOT = 300  # kac karede bir olu ID'ler temizlenir


def takip_sifirla():
    """Taraf hafizasini temizler (kamera degisince cagirilir)."""
    _taraf_hafiza.clear()


def _hafiza_buda(canli_idler):
    """Goruntude olmayan ID'leri taraf hafizasindan siler; sozluk sinirsiz buyumesin."""
    global _budama_sayaci
    _budama_sayaci += 1
    if _budama_sayaci < BUDAMA_PERIYOT:
        return
    _budama_sayaci = 0
    for tid in [k for k in _taraf_hafiza if k not in canli_idler]:
        del _taraf_hafiza[tid]


def _taraf_belirle(frame, box, tid):
    """A3 taraf karari — binary: cyan baskin=Dost, degilse Düşman (arasi yok).
    Renk hic okunamazsa son bilinen tarafa duseriz."""
    kirmizi, cyan = renk_oranlari(frame, box)
    if max(kirmizi, cyan) < RENK_ESIK and tid in _taraf_hafiza:
        return _taraf_hafiza[tid]
    taraf = "Dost" if cyan > kirmizi else "Düşman"
    if tid is not None:
        _taraf_hafiza[tid] = taraf
    return taraf


# ---------------- Tespit + karar ----------------
def analiz_et(model, frame, estop=False, asama=None):
    """Bir kareyi analiz eder. Doner: (dets, balonlar, active_idx).

    asama (sartname davranisi):
      1-2 : tum maketler kirmizi, dost YOK -> renk isi hic yapilmaz, her tespit "Hedef"
      3   : taraf RENKTEN belirlenir; yalnizca "Düşman" kilitlenir (dost vurmak -10)

    dets        : [{cls, ham, ad, tip, conf, box, id}, ...]
    balonlar    : [(x1,y1,x2,y2), ...] — nisan noktalari
    active_idx  : kilitli hedefin index'i; estop veya hedef yoksa -1
    """
    a = ayar_al()
    gosterim = float(a["gosterim"])

    global _tracker_yeniden_kur
    if _tracker_yeniden_kur:
        _tracker_yaml_yaz(a)
        try:   # mevcut tracker'i dusur ki yeni ayarlarla yeniden kurulsun
            if getattr(model, "predictor", None) is not None and hasattr(model.predictor, "trackers"):
                del model.predictor.trackers
        except Exception:
            pass
        _tracker_yeniden_kur = False

    # conf=BESLEME_CONF kasitli dusuk (bkz. dosya basi): filtrelemeyi tracker
    # (hassasiyet) ve cizim (gosterim) yapar, NMS degil.
    results = model.track(frame, persist=True,
                          conf=BESLEME_CONF,
                          iou=float(a["iou"]),
                          max_det=int(a["maks_tespit"]),
                          imgsz=int(a["cozunurluk"]),
                          tracker=_TRACKER_YAML, verbose=False)
    r = results[0]
    balonlar = []
    dets = []
    canli_idler = set()
    if r.boxes is not None:
        for b in r.boxes:
            ham_ad = r.names[int(b.cls)]     # modelin kendi sinif adi
            cls = kanonik(ham_ad)
            conf = float(b.conf)
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            tid = int(b.id.item()) if b.id is not None else None
            if tid is not None:
                canli_idler.add(tid)

            esik = gosterim * ID_TOLERANS if tid is not None else gosterim
            if conf < esik:
                continue

            if cls == BALON:                 # nisan noktasi, hedef listesine girmez
                balonlar.append((x1, y1, x2, y2))
                continue

            taraf = _taraf_belirle(frame, (x1, y1, x2, y2), tid) if asama == 3 else "Hedef"
            dets.append({"cls": cls, "ham": ham_ad, "ad": goster_ad(cls, ham_ad),
                         "tip": taraf, "conf": int(round(conf * 100)),
                         "box": (x1, y1, x2, y2), "id": tid})

    _hafiza_buda(canli_idler)

    # Kilit: A3'te yalniz Düşman (dosta ates yok), A1/A2'de her tespit hedeftir.
    active_idx = -1
    if not estop and dets:
        if asama == 3:
            aday = [i for i, d in enumerate(dets) if d["tip"] == "Düşman"]
        else:
            aday = list(range(len(dets)))
        if aday:
            active_idx = max(aday, key=lambda i: dets[i]["conf"])
    return dets, balonlar, active_idx


def draw_overlay(frame, dets, active_idx, balonlar=(), estop=False):
    """BGR kareye kutu + etiket + nisan cizer."""
    for bx in balonlar:
        x1, y1, x2, y2 = bx
        cv2.rectangle(frame, (x1, y1), (x2, y2), YELLOW, 1, cv2.LINE_AA)
        cv2.putText(frame, "BALON", (x1, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, YELLOW, 1, cv2.LINE_AA)
    for i, d in enumerate(dets):
        tip = d["tip"]
        color = RED if tip == "Düşman" else (BLUE if tip == "Dost" else HEDEF)
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        # Etiket: A3'te "Dusman/Dost - Tip - %.."; A1-A2'de yalniz "Tip - %.."
        tip_cv = {"Düşman": "Dusman", "Dost": "Dost"}.get(tip)
        ad_cv = goster_ad_cv(d["cls"], d.get("ham", d["cls"]))
        txt = f"{tip_cv} - {ad_cv} - %{d['conf']}" if tip_cv else f"{ad_cv} - %{d['conf']}"
        f, fs, ft = cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        (tw, th), _ = cv2.getTextSize(txt, f, fs, ft)
        ly = max(y1, th + 10)
        cv2.rectangle(frame, (x1, ly - th - 8), (x1 + tw + 12, ly), color, -1, cv2.LINE_AA)
        cv2.putText(frame, txt, (x1 + 6, ly - 4), f, fs, (255, 255, 255), ft, cv2.LINE_AA)
        # Nisan isareti yalniz kilitli hedefe (active_idx asamaya gore secildi, dosta cizilmez)
        if i == active_idx and not estop:
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.circle(frame, (cx, cy), 16, color, 2, cv2.LINE_AA)
            cv2.line(frame, (cx - 22, cy), (cx + 22, cy), color, 1, cv2.LINE_AA)
            cv2.line(frame, (cx, cy - 22), (cx, cy + 22), color, 1, cv2.LINE_AA)
    return frame


if __name__ == "__main__":
    # Kendi kendine test — kamera/model gerektirmez.

    # Sinif adi sadelestirme; bilinmeyen sinif ATILMAZ, ham adiyla gosterilir.
    assert kanonik("F-16") == "f16"
    assert kanonik("Mini_Drone") == "minidrone"
    assert kanonik("kus") == "kus"
    assert goster_ad("f16", "F-16") == "F-16"           # bilinen -> Turkce ad
    assert goster_ad("kus", "kus") == "kus"             # bilinmeyen -> ham ad
    assert goster_ad_cv("drone", "drone") == "IHA"      # cizim icin ASCII

    # Bozuk/asiri ayar degerleri araliga kirpilir, bilinmeyen anahtar yok sayilir.
    ayar_guncelle(hassasiyet=9.9, kararlilik=-5, cozunurluk="abc", bilinmeyen=1)
    assert AYAR["hassasiyet"] == 0.95 and AYAR["kararlilik"] == 5
    assert AYAR["cozunurluk"] == VARSAYILAN_AYAR["cozunurluk"]   # cevrilemedi -> varsayilan
    assert "bilinmeyen" not in AYAR
    ayar_guncelle(**VARSAYILAN_AYAR)
    assert ayar_al() == VARSAYILAN_AYAR

    # Tracker yaml ultralytics varsayilanlariyla yazilmali.
    _tracker_yaml_yaz(ayar_al())
    ic = open(_TRACKER_YAML, encoding="utf-8").read()
    assert "new_track_thresh: 0.250" in ic and "track_buffer: 30" in ic, ic

    # Taraf hafizasi budanmali (sinirsiz buyumemeli).
    _taraf_hafiza.update({i: "Düşman" for i in range(50)})
    for _ in range(BUDAMA_PERIYOT):
        _hafiza_buda({1, 2, 3})
    assert set(_taraf_hafiza) == {1, 2, 3}, _taraf_hafiza
    takip_sifirla()

    print("algi testleri OK — sinif adi, ayar kirpma, tracker yaml, hafiza budama")
