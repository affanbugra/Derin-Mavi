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
    # Cakisan kutu temizligi: iki kutunun kucugunun bu kadari otekinin icindeyse AYNI
    # nesnedir, biri elenir. NMS'in yapamadigi is (o sinif ici calisir) — gorevde ayni
    # alanda iki hedef bulunmaz. 0.99 = pratikte kapali.
    "ortusme": 0.60,
    "maks_tespit": 300,     # kare basina en fazla kutu (max_det)
    "ayna": 0,              # goruntuyu yatay cevir. 0 = ham YOLO ile birebir ayni
    # --- nisan.py (Otonom takip geometrisi) ---
    "fov": 60.0,            # kameranin yatay gorus acisi (derece)
    "kp": 0.50,             # takip gucu: hatanin ne kadari tek adimda kapatilsin
    "kd": 0.06,             # ongoru suresi (sn) — gecikme telafisi
    "olu_bolge": 0.02,      # merkeze bu kadar yakinsa komut yok (dwell icin sart)
    "onay_esigi": 0.70,     # kesin tanima icin gereken min. guven
    "onay_tekrari": 3,      # kesin tanima icin gereken ardisik yuksek-guven kare sayisi
    "kamera_fps": 30,       # kameradan istenen saniyelik kare hizi
}
AYAR = dict(VARSAYILAN_AYAR)

# Bozuk/eski ayarlar.json degerleri sisteme sizmasin diye gecerli araliklar.
AYAR_SINIR = {
    "hassasiyet": (0.05, 0.95), "gosterim": (0.05, 0.95),
    "kararlilik": (5, 300), "cozunurluk": (320, 1280),
    "iou": (0.10, 0.95), "ortusme": (0.30, 0.99), "maks_tespit": (1, 1000),
    "ayna": (0, 1), "fov": (20.0, 140.0),
    "kp": (0.05, 1.50), "kd": (0.0, 0.50), "olu_bolge": (0.0, 0.10),
    "onay_esigi": (0.10, 0.99), "onay_tekrari": (1, 10),
    "kamera_fps": (5, 120),
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
BLUE = (168, 88, 18)     # dost (yalniz A3) / belirsiz
HEDEF = (0, 170, 255)    # A1/A2: taraf ayrimi yok, hepsi hedef
YELLOW = (60, 200, 235)  # balon (nisan noktasi) / orta guven
ORANGE = (0, 165, 255)   # belirsiz / onay bekliyor
GREEN = (40, 200, 40)    # yuksek guven

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
                        (cv2.CAP_PROP_FPS, int(AYAR.get("kamera_fps", ISTENEN_FPS)))):
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


# Telefonu webcam yapan uygulamalar (kamera darbogazinda pratik bir yedek — bkz. CLAUDE.md §12).
TELEFON_UYG = {"droidcam": "DroidCam", "ivcam": "iVCam", "iriun": "Iriun"}
# Dahili kamera ipuclari: "Integrated Camera" gibi acik adlar + laptop sensor kod adlari.
DAHILI_IPUCU = ("integrated", "built-in", "facetime", "techfront", "ov97", "ov56", "ov27")


def _guzel_kamera_adi(raw: str) -> str:
    """Ham aygit adini secim listesinde okunakli hale getirir. Amac tek: operator
    "hangisi laptopun kamerasi, hangisi taktigim kamera" ayrimini gorsun.

        'ov9734_techfront_camera'      -> 'PC Kamerası'
        'OBSBOT Meet SE StreamCamera'  -> 'USB Kamera · OBSBOT Meet SE'
        'USB2.0 HD UVC WebCam'         -> 'USB Kamera'

    Tanimadigi cihaz HAM adiyla gecer — hicbir kamera listede kaybolmaz.
    (Bu ad yalnizca gorunustur; kamera secimi/karar mantigi index ile calisir.)"""
    low = raw.lower().replace("_", " ")
    for anahtar, ad in TELEFON_UYG.items():
        if anahtar in low:
            return f"Telefon Kamerası · {ad}"
    if "virtual" in low:
        return "Sanal Kamera"
    if any(k in low for k in DAHILI_IPUCU):
        return "PC Kamerası"

    # Harici/USB: teknik son ekleri atip marka adini birak.
    temizle = raw
    for suf in ("StreamCamera", "Stream Camera", "WebCam", "Webcam", "UVC",
                "USB2.0", "USB 2.0", "USB3.0", "USB 3.0", "Camera", "Cam", "HD"):
        temizle = temizle.replace(suf, "").replace(suf.lower(), "")
    marka = " ".join(temizle.split()).strip(" -·.,")
    return f"USB Kamera · {marka}" if marka else "USB Kamera"


def kameralari_listele_qt():
    """QMediaDevices ile sistemdeki TUM kameralari gercek isimleriyle listeler.

    Doner: [{"index": int, "name": str, "is_default": bool, "resolutions": [(w, h), ...]}, ...]
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
            res_set = set()
            for fmt in cam.videoFormats():
                r = fmt.resolution()
                res_set.add((r.width(), r.height()))
            res_list = sorted(list(res_set), key=lambda x: x[0]*x[1], reverse=True)
            sonuc.append({
                "index": i,
                "name": _guzel_kamera_adi(cam.description()),
                "is_default": cam.isDefault(),
                "resolutions": res_list
            })
        return sonuc
    except Exception:
        return []


def kameralari_listele(max_idx=5):
    """Eski OpenCV index taramasi (fallback). Yeni kod kameralari_listele_qt() kullanir."""
    bulunan = []
    for i in range(max_idx):
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
# ID'li kutuya gosterim esiginde kucuk bir tolerans taninir: takibe girmis nesne bir
# kare zayiflayinca titremesin. Ama esik yine UYGULANIR — eski kod "ID varsa guven
# ne olursa olsun goster" diyordu ve olu tespitler track_buffer boyunca hayalet
# kutu olarak ekranda kaliyordu.
ID_TOLERANS = 0.80   # ID'li kutu icin esik bu oranla yumusatilir (0.25 -> 0.20)

# ONAYLANMIS hedef pratikte hic elenmez. Amac operatorun kuralidir: "bir hedef bir kez
# %70 uzerinde dogrulandiysa artik onu TAKIP ET." Onaylanmis bir kutunun guveni bir kac
# kare dususte diye kaybolursa takip/dwell kopar; onay zaten yalnizca uzun sureli
# zayiflikta (ONAY_BOZULMA) dusurulur, tek karelik dususle degil.
ONAYLI_ESIK = 0.02

# Onayli bir track bu kadar kare UST USTE onay esiginin altinda kalirsa onay DUSER.
# Olmasaydi bir kez yanlis onaylanan sinif ID yasadigi surece duzelmezdi.
ONAY_BOZULMA = 15

# Taraf hafizasi: yalniz A3 renk karari icin, kutu konumuna DOKUNMAZ. Renk bir an
# okunamazsa son bilinen taraf korunur -> dost/dusman etiketi yanip sonmez.
_taraf_hafiza = {}   # takip id -> "Düşman" | "Dost"
_takip_durumlari = {} # takip id -> aday/onayli sinif bilgisi
_kayip_sayaclari = {}  # takip id -> kac karedir gorulmedi
_budama_sayaci = 0

RENK_ESIK = 0.02      # bu oranin altinda renk "okunamadi" sayilir
BUDAMA_PERIYOT = 300  # kac karede bir olu ID'ler temizlenir


def takip_sifirla():
    """Taraf hafizasini ve takip durumlarini temizler (kamera degisince cagirilir)."""
    _taraf_hafiza.clear()
    _takip_durumlari.clear()
    _kayip_sayaclari.clear()


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


def _karar_ver(tid, sinif_adi, conf, onay_esigi, onay_tekrari):
    """Tek bir takip ID'si icin kesin-tanima karari. Doner: onayli sinif veya None.

    ⚠ SIFIRLAMA DEGIL, HISTEREZIS. Eski kural "onay_tekrari kadar ARDISIK yuksek-guven
      kare" idi: esigin altinda kalan tek bir kare sayaci sifirliyordu. Gercek videoda
      guven kare kare dalgalanir (%75, %68, %72, %71...), dolayisiyla onay ya hic
      gerceklesmiyor ya cok geciyordu — kutu "?" olarak kaliyordu. Artik zayif kare
      sayaci yalnizca BIR AZALTIR; guclu kareler cogunluktaysa onay gelir.

    Sinif yarisi da ayni mantikla cozulur (cogunluk oylamasi): baska bir sinif yuksek
    guvenle gelirse mevcut adayin puani duser, ancak puan tukendiginde aday degisir.
    Boylece tek karelik bir yanlis sinif tahmini adayi devirmez.

    ⚠ SINIF TEKILLIGI KALDIRILDI. Eskiden bir sinifi tek bir track "sahiplenirdi"
      (_kilitli_siniflar); ayni siniftan ikinci hedef ASLA onaylanamaz, sonsuza dek
      "belirsiz" kalirdi. Oysa sartname coklu hedef gerektiriyor: Asama 2'de 3 koldan
      ayni anda Fuze + Mini/Micro IHA geliyor, Asama 3'te dusman F16 ile dost F16 ayni
      karede olabiliyor. Ayirt etme isi zaten takip ID'sinin (ve A3'te rengin) isidir.
    """
    durum = _takip_durumlari.setdefault(
        tid, {"aday_sinif": None, "aday_sayac": 0, "onayli_sinif": None, "zayif": 0}
    )
    yuksek = conf >= onay_esigi

    # --- ONAYLI: sinif SABIT kalir; yalnizca uzun sureli zayiflik onayi dusurur ---
    if durum["onayli_sinif"] is not None:
        durum["zayif"] = 0 if yuksek else durum["zayif"] + 1
        if durum["zayif"] >= ONAY_BOZULMA:
            durum.update({"onayli_sinif": None, "aday_sinif": None,
                          "aday_sayac": 0, "zayif": 0})
            return None
        return durum["onayli_sinif"]

    # --- HENUZ ONAYSIZ: cogunluk oylamasi ---
    if not yuksek:
        durum["aday_sayac"] = max(0, durum["aday_sayac"] - 1)     # sifirlama YOK
    elif durum["aday_sinif"] == sinif_adi:
        durum["aday_sayac"] += 1
    else:
        durum["aday_sayac"] -= 1                                  # rakip sinif puan dusurur
        if durum["aday_sayac"] <= 0:
            durum["aday_sinif"] = sinif_adi
            durum["aday_sayac"] = 1

    if durum["aday_sayac"] >= onay_tekrari:
        durum["onayli_sinif"] = durum["aday_sinif"]
        durum["zayif"] = 0
        return durum["onayli_sinif"]
    return None


def _onayli_mi(tid):
    """Bu takip ID'si kesin tanindi mi? (cizim esigini secmek icin)"""
    return (tid is not None
            and _takip_durumlari.get(tid, {}).get("onayli_sinif") is not None)


def _ortusme(a, b):
    """Iki kutunun ortusme orani: kesisim / KUCUK kutunun alani (IoS).

    Neden IoU degil: IoU kesisimi BIRLESIME boler, dolayisiyla ic ice gecmis kutularda
    (kucuk kutu buyugun icinde) dusuk cikar — oysa bunlar en tipik cift-kutu halidir.
    Kucuk alana bolmek "bu kutunun ne kadari otekinin icinde" sorusunu sorar."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    kx = max(0, min(ax2, bx2) - max(ax1, bx1))
    ky = max(0, min(ay2, by2) - max(ay1, by1))
    kesisim = kx * ky
    if kesisim <= 0:
        return 0.0
    kucuk = min(max(1, (ax2 - ax1) * (ay2 - ay1)), max(1, (bx2 - bx1) * (by2 - by1)))
    return kesisim / kucuk


def _cift_kutulari_ele(dets, esik):
    """Ayni nesneye atilmis IKINCI kutuyu eler.

    GOREV GERCEGI (takim bilgisi): hedefler raya asili gelir, birbirinden ayridir —
    ayni alanda iki hedef ASLA bulunmaz. O halde yuksek ortusme her zaman modelin
    ayni nesneye iki kutu atmasidir.

    Bunu NMS yapamaz: Ultralytics NMS'i SINIF ICI calisir (agnostic degil). Model ayni
    maketi hem 'fuze' hem 'helikopter' sanarsa kutular %90 ortusse bile ikisi de hayatta
    kalir — "iou" ayarini kismak bu duruma hic dokunmaz.

    Hangisi kalir: once KESIN TANINMIS olan (onaylanmis tip, "belirsiz" degil), esitlikte
    guveni yuksek olan. Yalnizca guvene bakilsaydi, onaylanmis bir hedef o karede sansli
    cikan gecici bir kutu yuzunden elenebilirdi.

    ⚠ BALON bu temizlige HIC girmez: `dets`e degil ayri `balonlar` listesine yazilir.
      Balon maketin ALTINDA oldugu icin govdeyle ortusur; buraya dahil edilseydi nisan
      noktasi elenirdi (bkz. CLAUDE.md §7)."""
    if len(dets) < 2:
        return dets
    sira = sorted(range(len(dets)),
                  key=lambda i: (dets[i]["cls"] != "belirsiz", dets[i]["conf"]),
                  reverse=True)
    tutulan = []
    for i in sira:
        if all(_ortusme(dets[i]["box"], dets[j]["box"]) < esik for j in tutulan):
            tutulan.append(i)
    return [dets[i] for i in sorted(tutulan)]   # kutu sirasi korunur


def _kayiplari_temizle(gorulen_id_seti, kayip_esigi):
    """Gorulmeyen ID'lerin kayip sayacini artirir ve esigi asinca hafizadan siler.

    Esik ByteTrack'in track_buffer'indan ("kararlilik" ayari) turer. Sabit 60 karedeydi:
    tracker ID'yi 30 karede dusurup nesneye YENI ID verdigi icin bizim hafizamiz olu bir
    ID'yi tutmaya devam ediyor, geri gelen nesne ise sifirdan onay bekliyordu."""
    for tid in list(_takip_durumlari.keys()):
        if tid in gorulen_id_seti:
            _kayip_sayaclari[tid] = 0
            continue
        _kayip_sayaclari[tid] = _kayip_sayaclari.get(tid, 0) + 1
        if _kayip_sayaclari[tid] >= kayip_esigi:
            _takip_durumlari.pop(tid, None)
            _kayip_sayaclari.pop(tid, None)


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
    #
    # TensorRT / ONNX sabit-boyutlu modeller: imgsz ayardan degil modelin kendi
    # boyutundan okunur. _fixed_imgsz ilk AssertionError'dan parse edilip saklanir.
    fixed_sz = getattr(model, "_fixed_imgsz", None)
    track_kwargs = {
        "persist": True,
        "conf": BESLEME_CONF,
        "iou": float(a["iou"]),
        "max_det": int(a["maks_tespit"]),
        "tracker": _TRACKER_YAML,
        "verbose": False,
        "imgsz": fixed_sz if fixed_sz is not None else int(a["cozunurluk"]),
    }

    try:
        results = model.track(frame, **track_kwargs)
    except AssertionError as e:
        msg = str(e)
        if "max model size" in msg:
            # Hata metninden modelin gercek boyutunu parse et: "(1, 3, 640, 640)"
            import re
            m = re.search(r"max model size[^\d]*(\d+),\s*(\d+)\)", msg)
            native_h = int(m.group(1)) if m else 640
            native_w = int(m.group(2)) if m else 640
            native_sz = max(native_h, native_w)
            model._fixed_imgsz = native_sz
            print(f"\n[UYARI] Model sabit boyutlu ({native_sz}px). "
                  f"Arayuzdeki cozunurluk yoksayiliyor.\n")
            # Predictor'i sifirla ki eski imgsz onbellekte kalmasin
            if getattr(model, "predictor", None) is not None:
                model.predictor = None
            track_kwargs["imgsz"] = native_sz
            results = model.track(frame, **track_kwargs)
        else:
            raise
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

            if cls == BALON:                 # nisan noktasi, hedef listesine girmez
                if conf >= gosterim:
                    balonlar.append((x1, y1, x2, y2))
                continue

            # KARAR ONCE, CIZIM ESIGI SONRA. Sira onemli: esik altinda kalan kare de
            # onay durumunu beslemelidir, yoksa onayli bir track zayifladiginda
            # `zayif` sayaci hic artmaz ve yanlis bir onay sonsuza dek yasardi.
            if tid is not None:
                kesin_cls = _karar_ver(tid, cls, conf, float(a["onay_esigi"]),
                                       int(a["onay_tekrari"]))
                if kesin_cls is None:
                    cls = "belirsiz"
                    ham_ad = "?"
                else:
                    cls = kesin_cls
                    ham_ad = kesin_cls

            # ONAYLANMIS hedef pratikte elenmez ("bir kez dogrulandiysa TAKIP ET"),
            # takibe girmis ama onaysiz kutuya kucuk tolerans, ID'siz kutuya tam esik.
            if _onayli_mi(tid):
                esik = ONAYLI_ESIK
            elif tid is not None:
                esik = gosterim * ID_TOLERANS
            else:
                esik = gosterim
            if conf < esik:
                continue

            if cls == "belirsiz":
                taraf = "Belirsiz"
            else:
                taraf = _taraf_belirle(frame, (x1, y1, x2, y2), tid) if asama == 3 else "Hedef"
            
            dets.append({"cls": cls, "ham": ham_ad, "ad": "?" if cls == "belirsiz" else goster_ad(cls, ham_ad),
                         "tip": taraf, "conf": int(round(conf * 100)),
                         "box": (x1, y1, x2, y2), "id": tid})

    # Ayni nesneye atilmis cift kutulari ele (NMS sinif ici calistigi icin farkli
    # sinif etiketli ciftleri temizleyemez — bkz. _cift_kutulari_ele).
    dets = _cift_kutulari_ele(dets, float(a["ortusme"]))

    _hafiza_buda(canli_idler)
    _kayiplari_temizle(canli_idler, int(a["kararlilik"]))

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
        if tip == "Belirsiz":
            color = BLUE
        else:
            c = d["conf"]
            if c >= 75:
                color = GREEN
            elif c >= 50:
                color = YELLOW
            else:
                color = RED
        
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        
        # Etiket: A3'te "Dusman/Dost - Tip - %.."; A1-A2'de yalniz "Tip - %.."
        tip_cv = {"Düşman": "Dusman", "Dost": "Dost"}.get(tip)
        ad_cv = "?" if d["cls"] == "belirsiz" else goster_ad_cv(d["cls"], d.get("ham", d["cls"]))
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

    # ---- KESIN TANIMA (_karar_ver) ----
    ESIK, TEKRAR = 0.70, 3

    def besle(tid, kareler):
        """kareler: [(sinif, conf), ...] -> son karedeki karar."""
        son = None
        for sinif, conf in kareler:
            son = _karar_ver(tid, sinif, conf, ESIK, TEKRAR)
        return son

    # 3 guclu kare -> onay
    assert besle(1, [("f16", 0.9)] * 3) == "f16"
    takip_sifirla()

    # DALGALI GUVEN: aradaki zayif kare onayi ENGELLEMEMELI (eski kod sifirlardi).
    # (+1 +1 -1 +1 +1 = 3) -> onay
    assert besle(1, [("f16", 0.9), ("f16", 0.8), ("f16", 0.5),
                     ("f16", 0.85), ("f16", 0.9)]) == "f16"
    takip_sifirla()

    # Surekli zayif kalan hedef onaylanmamali.
    assert besle(1, [("f16", 0.5)] * 20) is None
    takip_sifirla()

    # Tek karelik yanlis sinif tahmini adayi DEVIRMEMELI — yalnizca onayi geciktirir.
    # (+1 +1 -1(fuze) +1 = 2 -> heniz onay yok, ama aday hala f16)
    assert besle(1, [("f16", 0.9), ("f16", 0.9), ("fuze", 0.9), ("f16", 0.9)]) is None
    assert _takip_durumlari[1]["aday_sinif"] == "f16", "rakip sinif adayi devirdi"
    assert _karar_ver(1, "f16", 0.9, ESIK, TEKRAR) == "f16"   # bir kare daha -> onay
    takip_sifirla()

    # ISRARLI yanlis sinif adayi devirebilmeli (model gercekten fikir degistirdiyse).
    assert besle(1, [("f16", 0.9), ("f16", 0.9)]) is None
    assert besle(1, [("fuze", 0.9)] * 5) == "fuze", "israrli dogru sinif adayi deviremedi"
    takip_sifirla()

    # AYNI SINIFTAN IKI HEDEF: ikisi de onaylanmali (sartname: Asama 2'de 3 hedef,
    # Asama 3'te dusman F16 + dost F16 ayni karede olabilir).
    assert besle(1, [("f16", 0.9)] * 3) == "f16"
    assert besle(2, [("f16", 0.9)] * 3) == "f16", "ayni siniftan ikinci hedef onaylanmadi"
    takip_sifirla()

    # Onaydan sonra sinif SABIT: zayif kareler kutuyu kaybettirmez...
    besle(1, [("f16", 0.9)] * 3)
    assert besle(1, [("f16", 0.3)] * (ONAY_BOZULMA - 1)) == "f16"
    assert _onayli_mi(1)
    # ...ama UZUN sureli zayiflik onayi dusurur (yanlis onay sonsuza dek yasamasin).
    assert besle(1, [("f16", 0.3)] * 2) is None
    assert not _onayli_mi(1)
    takip_sifirla()

    # Onayli track baska sinif gorse bile tipini degistirmez (etiket titremesin).
    besle(1, [("f16", 0.9)] * 3)
    assert besle(1, [("fuze", 0.95)]) == "f16"
    takip_sifirla()

    # ---- CAKISAN KUTU TEMIZLIGI (_ortusme / _cift_kutulari_ele) ----
    # Ortusme orani kucuk kutuya gore olculur: ic ice kutu IoU ile yakalanmaz.
    assert _ortusme((0, 0, 100, 100), (0, 0, 100, 100)) == 1.0        # birebir ayni
    assert _ortusme((0, 0, 100, 100), (200, 200, 300, 300)) == 0.0    # hic degmiyor
    assert _ortusme((0, 0, 100, 100), (25, 25, 75, 75)) == 1.0        # kucuk TAMAMEN icinde
    assert abs(_ortusme((0, 0, 100, 100), (50, 0, 150, 100)) - 0.5) < 1e-6   # yarim

    def kutu(cls, conf, box, tid=1):
        return {"cls": cls, "ham": cls, "ad": cls, "tip": "Hedef",
                "conf": conf, "box": box, "id": tid}

    # Ayni nesneye iki FARKLI SINIF etiketi -> biri elenmeli (NMS'in yapamadigi is).
    d = _cift_kutulari_ele([kutu("fuze", 60, (10, 10, 110, 110)),
                            kutu("helikopter", 85, (12, 12, 112, 112))], 0.60)
    assert len(d) == 1 and d[0]["cls"] == "helikopter", d      # guveni yuksek olan kalir

    # KESIN TANINMIS hedef, o karede daha guvenli cikan "belirsiz" kutuya yenilmez.
    d = _cift_kutulari_ele([kutu("belirsiz", 95, (10, 10, 110, 110)),
                            kutu("f16", 55, (12, 12, 112, 112))], 0.60)
    assert len(d) == 1 and d[0]["cls"] == "f16", d

    # AYRI hedefler (Asama 2 surusu) korunmali — az ortusme eleme sebebi degil.
    ayri = [kutu("fuze", 80, (0, 0, 100, 100), 1),
            kutu("drone", 80, (90, 0, 190, 100), 2),
            kutu("fuze", 80, (300, 0, 400, 100), 3)]
    assert len(_cift_kutulari_ele(ayri, 0.60)) == 3, "ayri hedefler elendi"

    # Esik 0.99'da temizlik pratikte KAPALI olmali (operator kapatabilmeli).
    ikiz = [kutu("fuze", 60, (10, 10, 110, 110)), kutu("helikopter", 85, (12, 12, 112, 112))]
    assert len(_cift_kutulari_ele(ikiz, 0.99)) == 2

    # Kutu sirasi korunmali (active_idx bu listeye gore secilir).
    sirali = _cift_kutulari_ele([kutu("f16", 90, (0, 0, 50, 50), 1),
                                 kutu("drone", 70, (300, 300, 350, 350), 2)], 0.60)
    assert [x["cls"] for x in sirali] == ["f16", "drone"], sirali

    # Kayip ID hafizadan silinmeli; esik "kararlilik" ayarindan gelir.
    besle(7, [("f16", 0.9)] * 3)
    for _ in range(5):
        _kayiplari_temizle(set(), 5)
    assert 7 not in _takip_durumlari, "kayip ID hafizada kaldi"
    takip_sifirla()

    print("algi testleri OK — sinif adi, ayar kirpma, tracker yaml, hafiza budama, "
          "kesin tanima (histerezis/coklu hedef/onay bozulma), cakisan kutu temizligi")
