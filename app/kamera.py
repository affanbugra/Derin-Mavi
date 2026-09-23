"""Kamera — YALNIZ takılı HARİCİ kamera (USB-C). Takımın kuralı (22.09.2026):

  * Laptopun kendi kamerası (Mac FaceTime / Windows "Integrated") KULLANILMAZ.
  * Telefon (iPhone Süreklilik Kamerası, DroidCam…) ve sanal kameralar KULLANILMAZ.
  * Harici kamera takılıysa onu aç; yoksa "Kamera bulunamadı" de. Sonradan
    takılırsa kendiliğinden bağlanır, çıkarılırsa "bulunamadı"ya döner.

NEDEN Qt, NEDEN OpenCV DEĞİL: eski kod kameraları Qt ile İSİMLERİYLE listeleyip
(iPhone'u orada eliyordu) ama OpenCV ile SIRA NUMARASIYLA açıyordu. İki
kütüphanenin sırası macOS'ta aynı değil — "iPhone hariç" seçilen numara OpenCV'de
iPhone'a denk gelebiliyor, her açılışta telefona bağlantı isteği gidiyordu. Burada
kamera, seçilen cihazın KENDİSİYLE açılır: elenen cihaza hiç dokunulmaz.

Kareler numpy BGR olarak verilir (algı zinciri değişmedi); arayüz tarafı
`oku(son_sira)` ile eskisiyle aynı arayüzü kullanır.
"""
import os
import threading
import time

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (QCamera, QCameraDevice, QMediaCaptureSession,
                                  QMediaDevices, QVideoSink)

# Harici OLMAYAN kameralar isimden elenir. macOS adları sistem diline göre gelir
# ("MacBook Air Kamerası", "iPhone Kamerası") — Türkçe/İngilizce ikisi de burada.
# ⚠ Windows'ta bazı dahili kameralar harici USB kamerayla AYNI tip adla görünür
#   ("USB2.0 HD UVC WebCam"). Böyle biri seçilirse adını buraya TEK satır eklemek yeter.
HARICI_DEGIL = (
    "macbook", "facetime", "imac", "built-in", "yerleşik",                 # Mac dahili
    "iphone", "ipad", "continuity", "süreklilik", "desk view", "masaüstü görünümü",
    "integrated", "internal", "dahili", "truevision", "easycamera",        # PC dahili
    "ir camera", "kızılötesi",
    "droidcam", "ivcam", "iriun", "camo", "epoccam",                       # telefon uyg.
    "virtual", "sanal", "obs virtual", "manycam", "snap camera", "broadcast",  # sanal
    # ⚠ Yalniz "obs" YAZILMAZ: gercek harici OBSBOT kamerayi da eler (test yakaladi).
)

# Test/tekrar için: DERINMAVI_CAM=dosya.mp4 veya rtsp://... (cihaz taramaz).
DOSYA_KAYNAGI = os.environ.get("DERINMAVI_CAM", "").strip()


# ⚠ Yarisma gunu kacis kapisi: harici kamera bozulursa/ariza yaparsa operator
# ⚙ → SINIRLAR bolumunden "Tum kameralari goster"i acar ve dahili kamerayla
# devam eder. Varsayilan yine YALNIZ HARICI (telefonlara istek gitmesin).
TUM_KAMERALAR = False


def tum_kameralar_ayarla(acik):
    global TUM_KAMERALAR
    TUM_KAMERALAR = bool(acik)
    return TUM_KAMERALAR


def harici_mi(cihaz):
    if TUM_KAMERALAR:
        return True
    if cihaz.position() in (QCameraDevice.FrontFace, QCameraDevice.BackFace):
        return False                    # telefon/tablet/laptop kasası kamerası
    ad = cihaz.description().lower()
    return not any(k in ad for k in HARICI_DEGIL)


def harici_kameralar():
    return [c for c in QMediaDevices.videoInputs() if harici_mi(c)]


def en_yakin_format(cihaz, genislik, yukseklik, fps):
    """Cihazın desteklediği formatlardan istenen çözünürlüğe en yakın olanı
    (eşitlikte istenen FPS'i karşılayanı) seçer. Desteklenmeyen format ASLA
    zorlanmaz — kamera kendi listesinden seçilir."""
    formatlar = cihaz.videoFormats()
    if not formatlar:
        return None

    def puan(f):
        r = f.resolution()
        min_fps, max_fps = float(f.minFrameRate()), float(f.maxFrameRate())
        # Ayni cozunurlukte 60 FPS istenirken 150 FPS profilini secmek kameranin
        # gercekte 30'a dusmesine yol acabiliyor. Once istenen FPS'i kapsayan araligi,
        # sonra da tavani istenene en yakin profili sec.
        fps_uzaklik = (min_fps - fps if fps < min_fps else
                       fps - max_fps if fps > max_fps else 0.0)
        return (abs(r.width() * r.height() - genislik * yukseklik),
                fps_uzaklik,
                abs(max_fps - fps),
                abs(min_fps - fps))
    return min(formatlar, key=puan)


class Kamera(QObject):
    """Tek kamera kaynağı. ANA (GUI) thread'de yaşar; kareyi `oku()` ile her
    thread güvenle alır."""
    durum = Signal(str, bool)            # mesaj, hata_mi
    liste_degisti = Signal(list)         # [QCameraDevice] — yalnız harici olanlar

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kilit = threading.Lock()
        self._kare, self._sira, self._kare_t = None, 0, 0.0
        self._kamera = None
        self._acilis_nesli = 0          # gecikmeli acilis/eski hata sinyallerini gecersizlestirir
        self.secili_id = None
        self.kapali = False              # operatör "Kapalı" seçti
        self.istenen = (1280, 720, 30)   # (genişlik, yükseklik, fps)
        self._dosya = None               # DERINMAVI_CAM dosya/URL okuyucusu

        self._cihazlar = QMediaDevices(self)
        self._cihazlar.videoInputsChanged.connect(self._liste_guncelle)
        self._oturum = QMediaCaptureSession(self)
        self._sink = QVideoSink(self)
        self._oturum.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._kare_geldi)

    # ---- yaşam döngüsü ----
    def baslat(self):
        if DOSYA_KAYNAGI:
            self._dosya = _DosyaOkuyucu(DOSYA_KAYNAGI, self._kare_koy)
            self.durum.emit(f"Kaynak: {DOSYA_KAYNAGI}", False)
            self.liste_degisti.emit([])          # secici "dosya" modunu gostersin
            return
        self._liste_guncelle()

    @property
    def dosya_adi(self):
        return os.path.basename(DOSYA_KAYNAGI) if self._dosya is not None else None

    @property
    def aktif(self):
        return self._kamera is not None or self._dosya is not None

    def _liste_guncelle(self):
        """Kamera takıldı/çıkarıldı. Açık kamera hâlâ varsa dokunma; yoksa ilk
        harici kamerayı aç; hiç yoksa 'bulunamadı' de."""
        liste = harici_kameralar()
        self.liste_degisti.emit(liste)
        if self._dosya is not None or self.kapali:
            return
        if self._kamera is not None and self.secili_id in [bytes(c.id()) for c in liste]:
            return
        if liste:
            self.ac(liste[0])
        else:
            self._durdur()
            self.durum.emit("Kamera bulunamadı — harici kamera takılı değil", True)

    def ac(self, cihaz):
        """Cihazi ac. Eski kamera varsa Windows surucusune USB kaynagini birakmasi
        icin kisa sure taninir; ayni anda kapat/ac yapmak Media Foundation'da
        ERROR_OPERATION_ABORTED ("G/C islemi iptal edildi") uretebiliyor."""
        self._acilis_nesli += 1
        nesil = self._acilis_nesli
        eski_vardi = self._durdur()
        self.kapali = False
        self.secili_id = bytes(cihaz.id())
        if eski_vardi:
            QTimer.singleShot(180, lambda c=cihaz, n=nesil: self._ac_devam(c, n))
        else:
            self._ac_devam(cihaz, nesil)

    def _ac_devam(self, cihaz, nesil):
        """`ac` isleminin, eski kamera gercekten birakildiktan sonraki adimi."""
        if nesil != self._acilis_nesli or self.kapali:
            return
        # Gecikme sirasinda kablo ciktiysa hayalet QCamera olusturma.
        if bytes(cihaz.id()) not in [bytes(c.id()) for c in harici_kameralar()]:
            self.durum.emit("Kamera bağlantısı kesildi", True)
            return
        kamera = QCamera(cihaz, self)
        fmt = en_yakin_format(cihaz, *self.istenen)
        if fmt is not None:
            kamera.setCameraFormat(fmt)
        kamera.errorOccurred.connect(
            lambda _hata, metin, k=kamera: self._kamera_hatasi(k, metin))
        # start() sirasinda hata gelirse sinyalin hangi acilisa ait oldugu bilinsin.
        self._kamera = kamera
        self._oturum.setCamera(kamera)
        kamera.start()
        # Ilk liste sinyali kamera acilmadan once gelir. Secili cihaz/cozunurluk
        # kutularini gercek acilan formatla bir kez daha esitle.
        self.liste_degisti.emit(harici_kameralar())
        r = fmt.resolution() if fmt is not None else None
        ek = (f" · {r.width()}×{r.height()} @{fmt.maxFrameRate():.0f} FPS"
              if r is not None else "")
        self.durum.emit(f"Kamera açıldı: {cihaz.description()}{ek}", False)

    def _kamera_hatasi(self, kamera, metin):
        """Yalniz AKTIF kameranin hatasini goster.

        QCamera.stop() Windows'ta hata sinyalini kuyruga birakabilir. Eski kod bu
        gec sinyali yeni acilan kameranin hatasi sanip goruntuyu karartiyordu.
        """
        if kamera is not self._kamera:
            return
        dusuk = (metin or "").lower()
        if "iptal edildi" in dusuk or "operation aborted" in dusuk:
            metin = ("Kamera başlatılamadı — başka bir uygulama kamerayı kullanıyor "
                     "olabilir. Kamerayı yeniden seçin.")
        self.durum.emit(f"Kamera hatası: {metin}", True)

    def kapat(self):
        self._acilis_nesli += 1
        self.kapali = True
        self._durdur()
        self.durum.emit("Kamera kapatıldı", False)

    def yeniden_ac(self):
        """Çözünürlük/FPS değişince seçili kamerayı yeni formatla açar."""
        for c in harici_kameralar():
            if bytes(c.id()) == self.secili_id:
                self.ac(c)
                return

    def secili_cihaz(self):
        for c in harici_kameralar():
            if bytes(c.id()) == self.secili_id:
                return c
        return None

    def _durdur(self):
        kamera = self._kamera
        self._kamera = None              # stop()tan gelebilecek gec hata artik bayat
        if kamera is not None:
            kamera.stop()
            self._oturum.setCamera(None)
            kamera.deleteLater()
        with self._kilit:
            self._kare = None
            self._kare_t = 0.0
        return kamera is not None

    def durdur(self):
        """Uygulama kapanırken."""
        self._acilis_nesli += 1
        self._durdur()
        if self._dosya is not None:
            self._dosya.kapat()

    # ---- kareler ----
    def _kare_geldi(self, kare):
        # Zaman damgasini donusum/kopyalama ve GUI kuyrugundan ONCE al. Takip,
        # karede gorulen hedefi motorun ayni andaki acisiyla eslestirir; tuketicinin
        # kareyi daha sonra aldigi zamani kullanmak yuk altinda faz hatasi ve salinim
        # uretir. QVideoFrame.startTime akisa goreli oldugu icin duvar saatiyle
        # motor gecmisine dogrudan karistirilamaz; callback zamani ortak saat alanidir.
        kare_t = time.time()
        img = kare.toImage()
        if img.isNull():
            return
        img = img.convertToFormat(QImage.Format_BGR888)
        w, h, satir = img.width(), img.height(), img.bytesPerLine()
        dizi = np.frombuffer(img.constBits(), np.uint8, count=satir * h)
        self._kare_koy(dizi.reshape(h, satir)[:, :w * 3].reshape(h, w, 3).copy(), kare_t)

    def _kare_koy(self, bgr, kare_t=None):
        with self._kilit:
            self._kare = bgr
            self._kare_t = time.time() if kare_t is None else float(kare_t)
            self._sira += 1

    def oku(self, son_sira=None):
        """En taze kare: (kare, sira). Yeni kare yoksa (None, sira)."""
        with self._kilit:
            if self._kare is None or (son_sira is not None and self._sira == son_sira):
                return None, self._sira
            return self._kare, self._sira

    def oku_zamanli(self, son_sira=None):
        """En taze kareyi atomik olarak ``(kare, sira, okuma_zamani)`` verir.

        ``oku`` geriye uyumluluk icin iki deger dondurmeye devam eder. Takip yolu bu
        metodu kullanir; boylece kare ile ona ait zaman damgasi arasina yeni bir
        kamera callback'i girip ikisini farkli karelerden yapamaz.
        """
        with self._kilit:
            if self._kare is None or (son_sira is not None and self._sira == son_sira):
                return None, self._sira, self._kare_t
            return self._kare, self._sira, self._kare_t


class _DosyaOkuyucu:
    """DERINMAVI_CAM ile verilen video dosyası / akış (kamera taramasına dokunmaz).
    Dosya bitince başa sarar — kamerasız test için."""

    def __init__(self, kaynak, koy):
        self._cap = cv2.VideoCapture(kaynak)
        self._koy = koy
        self._calis = True
        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self):
        import time
        while self._calis:
            ok, kare = self._cap.read()
            if not ok:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.05)
                continue
            self._koy(kare)
            time.sleep(1.0 / self._fps)

    def kapat(self):
        self._calis = False


# =====================================================================
#  Kendi kendini test (kamera AÇMAZ — yalnız eleme kuralı)
# =====================================================================
if __name__ == "__main__":
    class _Sahte:
        def __init__(self, ad, konum=QCameraDevice.UnspecifiedPosition):
            self._ad, self._konum = ad, konum
        def description(self): return self._ad
        def position(self): return self._konum

    elenmeli = ["MacBook Air Kamerası", "FaceTime HD Camera", "iPhone Kamerası",
                "Affan's iPhone Camera", "Masaüstü Görünümü Kamerası", "Integrated Camera",
                "HP TrueVision HD Camera", "OBS Virtual Camera", "DroidCam Source 3",
                "Integrated IR Camera"]
    kalmali = ["OBSBOT Meet SE StreamCamera", "Logitech BRIO", "HD Pro Webcam C920",
               "USB2.0 HD UVC WebCam", "Arducam OV9281 USB Camera"]
    for ad in elenmeli:
        assert not harici_mi(_Sahte(ad)), f"elenmeliydi: {ad}"
    for ad in kalmali:
        assert harici_mi(_Sahte(ad)), f"harici sayılmalıydı: {ad}"
    assert not harici_mi(_Sahte("Camera", QCameraDevice.FrontFace))

    class _Boyut:
        def __init__(self, w, h): self._w, self._h = w, h
        def width(self): return self._w
        def height(self): return self._h
    class _Format:
        def __init__(self, w, h, mn, mx): self._r, self._mn, self._mx = _Boyut(w, h), mn, mx
        def resolution(self): return self._r
        def minFrameRate(self): return self._mn
        def maxFrameRate(self): return self._mx
    class _Cihaz:
        def __init__(self, fs): self._fs = fs
        def videoFormats(self): return self._fs

    f30, f60, f150 = (_Format(1280, 720, 30, 30), _Format(1280, 720, 30, 60),
                       _Format(1280, 720, 30, 150))
    assert en_yakin_format(_Cihaz([f150, f30, f60]), 1280, 720, 60) is f60

    # Zaman damgasi kareyle ayni kilit altinda saklanmali; iki asamali okuma yeni
    # callback araya girdiginde baska karenin zamanini verebilirdi.
    k = Kamera.__new__(Kamera)
    k._kilit, k._kare, k._sira, k._kare_t = threading.Lock(), None, 0, 0.0
    k._kare_koy(np.zeros((1, 1, 3), dtype=np.uint8), 123.5)
    _im, _sira, _t = k.oku_zamanli()
    assert _sira == 1 and _t == 123.5
    print("kamera testleri OK — cihaz eleme, format secimi, atomik kare zamani")
