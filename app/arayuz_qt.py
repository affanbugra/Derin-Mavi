# -*- coding: utf-8 -*-
"""DERIN MAVI - Native Kontrol Istasyonu (PySide6).

Tasarim: gorev_kontrol_yedek.html'in BIREBIR native kopyasi (acik tema).
Algi cekirdegi algi.py'den gelir. Donanim-bagimsizdir (CLAUDE.md ilke 7):
kamera secimi arayuzden yapilir, DERINMAVI_CAM env override desteklenir.

Calistir:  python app/arayuz_qt.py   (veya kokteki Baslat.bat)
"""
import os
import sys
import time
import cv2

# ONEMLI: ultralytics/torch ANA THREAD'de (modul yuklenirken) import edilir.
# torch'un op-registration'i thread-safe DEGILDIR; arka plan thread'inde import
# edilirse ana thread'in Qt cizimiyle carpisip COKME (segfault) olur. Burada
# import edilince registration bir kez ana thread'de olur; sonra QThread yalnizca
# hazir modulu kullanir (agirlik yukleme + tensor islemleri thread-guvenli).
from ultralytics import YOLO

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF, QEvent, QPoint, QRect
from PySide6.QtGui import QImage, QPixmap, QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy, QButtonGroup,
    QGraphicsView, QGraphicsScene, QStackedWidget,
    QSlider, QCheckBox, QSpinBox, QScrollArea,
)

import algi
import nisan
import kontrol as kontrol_mod

HERE = os.path.dirname(os.path.abspath(__file__))
# Model klasoru: repo kokunde "models/". Ekip arkadaslari kendi egittikleri agirligi
# (best.pt / .onnx / herhangi .pt) BURAYA atinca uygulama otomatik bulur — kod degismez.
MODELS_DIR = os.path.abspath(os.path.join(HERE, "..", "models"))


def _model_bul():
    """Kullanilacak modeli DINAMIK bulur. Doner: yol (str) veya None.

    Oncelik:
      1. DERINMAVI_MODEL=<dosya/klasor yolu>  -> tam o model
      2. DERINMAVI_MODEL=onnx | openvino      -> models/best.onnx | best_openvino_model
      3. (tanimsiz) HIZ SIRASI: OpenVINO klasoru -> ONNX -> .pt -> ilk bulunan

    HIZ NOTU (C1): bu proje GPU'suz laptopta calisiyor (CLAUDE.md §8) ve tek gercek
    darbogaz CPU inference'i. Ultralytics ayni agirligi OpenVINO'ya cevirebilir ve
    Intel CPU'da tipik 2-3x hizlanma verir — KOD DEGISMEDEN. Donusturmek icin:
        yolo export model=models/best.pt format=openvino
    Ciktiyi (models/best_openvino_model/) models/ icine birakmak yeterli; burasi
    onu otomatik tercih eder. Yoksa .pt ile calismaya devam eder.

    Hicbiri yoksa None (uygulama modelsiz calisir: kamera akar, tespit yapmaz).
    """
    import glob
    sec = os.environ.get("DERINMAVI_MODEL", "").strip()
    if sec:
        dusuk = sec.lower()
        if dusuk == "onnx":
            p = os.path.join(MODELS_DIR, "best.onnx")
            return p if os.path.isfile(p) else None
        if dusuk == "openvino":
            p = os.path.join(MODELS_DIR, "best_openvino_model")
            return p if os.path.isdir(p) else None
        if dusuk in ("pt", "torch"):
            p = os.path.join(MODELS_DIR, "best.pt")
            return p if os.path.isfile(p) else None
        return sec if (os.path.isfile(sec) or os.path.isdir(sec)) else None

    ov = os.path.join(MODELS_DIR, "best_openvino_model")
    if os.path.isdir(ov):
        return ov
    for aday in ("best.onnx", "best.pt"):
        p = os.path.join(MODELS_DIR, aday)
        if os.path.isfile(p):
            return p
    for kalip in ("*_openvino_model", "*.onnx", "*.pt"):
        bulunan = sorted(glob.glob(os.path.join(MODELS_DIR, kalip)))
        if bulunan:
            return bulunan[0]
    return None

# ---- HTML tasarim tokenlari (gorev_kontrol_yedek.html :root) ----
BG = "#dde3ea"; PANEL = "#ffffff"; CARD = "#edf1f6"; BD = "#bbc8d6"; BD2 = "#96aabb"
TXT = "#0b1620"; TXT2 = "#2c4560"; TXT3 = "#527088"
BLUE = "#1258a8"; RED = "#bf2020"; GRN = "#158750"; AMB = "#8e5c08"
F = "'Public Sans','Segoe UI',sans-serif"
FM = "Consolas,'Courier New',monospace"


# =====================================================================
#  Ayar paneli — kaydiricilar + "oneri" isaretli
# =====================================================================
COZUNURLUK_SECENEK = [416, 512, 640, 960, 1280]

# Kaydirici gorunumu: onerilen degerde YESIL tutamac, degistirilmisse MAVI.
# Tek sablon + iki renk takimi (eskiden ayni CSS iki kez kopyalanmisti).
SLIDER_TASLAK = """
    QSlider#ayarsl {{ height: 22px; }}
    QSlider#ayarsl::groove:horizontal {{ height: 5px; border-radius: 2px; background: #dbe3ec; margin: 0 2px; }}
    QSlider#ayarsl::sub-page:horizontal {{ height: 5px; border-radius: 2px; background: %s; margin: 0 2px; }}
    QSlider#ayarsl::add-page:horizontal {{ height: 5px; border-radius: 2px; background: #dbe3ec; margin: 0 2px; }}
    QSlider#ayarsl::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
        background: {tutamac}; border: 2px solid {kenar}; }}
    QSlider#ayarsl::handle:horizontal:hover {{ background: {ust_tutamac}; border: 2px solid {ust_kenar}; }}
    QSlider#ayarsl::handle:horizontal:pressed {{ background: {bas_tutamac}; border: 2px solid {bas_kenar}; }}
""" % BLUE
SLIDER_ONERI = {"tutamac": GRN, "kenar": GRN,
                "ust_tutamac": "#189a5c", "ust_kenar": "#189a5c",
                "bas_tutamac": "#0f6c3f", "bas_kenar": "#0f6c3f"}
SLIDER_DEGISIK = {"tutamac": "#ffffff", "kenar": BLUE,
                  "ust_tutamac": "#f3f8ff", "ust_kenar": "#0e4a90",
                  "bas_tutamac": "#dbe9fb", "bas_kenar": BLUE}

_ETIKET = ("color:%s; background:rgba(%s,%s); border-radius:9px; padding:2px 10px; "
           "font-family:" + FM + "; border: 1px solid rgba(%s,%s); font-size:12px; font-weight:700;")
ETIKET_ONERI = _ETIKET % (GRN, "21,135,80", "0.14", "21,135,80", "0.35")
ETIKET_DEGISIK = _ETIKET % (BLUE, "18,88,168", "0.10", "18,88,168", "0.18")

# D-pad tuslari: 68x54 sabit kutu; yalnizca renk/kalinlik/yazi boyu degisir.
# Dort varyant (kenar/merkez x normal/basili) ayni iki sablondan uretilir.
_DPAD_GOVDE = ("QPushButton {{ "
               "  background: {arka}; "
               "  border: {kalinlik} solid {kenar}; "
               "  border-radius: 8px; "
               "  color: {yazi}; "
               "  font-size: {punto}; "
               "  font-weight: 700; "
               "  min-width: 68px; max-width: 68px; "
               "  min-height: 54px; max-height: 54px; "
               "}} ")
DPAD_STIL = _DPAD_GOVDE + ("QPushButton:hover {{ "
                           "  background: {ust_arka}; "
                           "  border-color: {ust_kenar}; "
                           "}}")
DPAD_STIL_BASILI = _DPAD_GOVDE          # basili halde :hover kurali yok

DPAD_KENAR = {"arka": "#f7f9fb", "kenar": "#dfe4ea", "kalinlik": "1px",
              "yazi": "#2b3540", "punto": "13px",
              "ust_arka": "#eef3f8", "ust_kenar": "#c3d3e2"}
DPAD_KENAR_BASILI = {"arka": "#dbe6f1", "kenar": "#1e4b7a", "kalinlik": "1.5px",
                     "yazi": "#1e4b7a", "punto": "13px"}
DPAD_MERKEZ = {"arka": "#1e4b7a", "kenar": "#1e4b7a", "kalinlik": "1px",
               "yazi": "#ffffff", "punto": "11px",
               "ust_arka": "#265a8f", "ust_kenar": "#265a8f"}
DPAD_MERKEZ_BASILI = {"arka": "#17395d", "kenar": "#17395d", "kalinlik": "1.5px",
                      "yazi": "#ffffff", "punto": "11px"}

# Ayar paneli sekmeleri: kalabalik tek liste yerine iki grup.
#   "Tespit"  — YOLO/ByteTrack davranisi
#   "Nişan"   — gimbal/kamera geometrisi (Otonom takip)
#
# (key, baslik, tip, min, max, oneri, aciklama)
#   tip "yuzde": slider /100 · "kare"/"sayi": tam sayi · "secim": COZUNURLUK_SECENEK
#   "onda": slider /10 (ondalikli) · "anahtar": ac/kapa (0/1)
#
# ONEMLI: her ayarin "oneri" degeri ULTRALYTICS VARSAYILANIDIR. Yani hicbir kaydiriciya
# dokunmayan biri, ham `yolo track source=0` ile AYNI sonucu alir. Sapmak isteyen buradan sapar.
AYAR_TANIM_TESPIT = [
    ("hassasiyet", "Hassasiyet", "yuzde", 5, 90, 25,
     "Bir nesnenin YENİ HEDEF olarak takibe alınması için gereken güven.\n"
     "(Teknik: ByteTrack new_track_thresh / track_high_thresh — Ultralytics varsayılanı 0.25)\n\n"
     "↑ ARTTIRIRSAN: sadece net nesneler takibe girer, yanlış hedef azalır — ama zayıf/uzak "
     "nesneyi kaçırabilir.\n"
     "↓ AZALTIRSAN: zayıf/uzak nesneleri de yakalar — ama arka plana yanlış kutu atma riski artar."),
    ("gosterim", "Gösterim eşiği", "yuzde", 5, 90, 25,
     "Bir kutunun EKRANDA ÇİZİLMESİ için gereken güven. Bunun altındaki kutu çizilmez.\n"
     "(Takibe girmiş nesneye küçük bir tolerans tanınır — tek karelik zayıflamada titremesin diye.)\n\n"
     "↑ ARTTIRIRSAN: ekran temizlenir, sadece emin olunanlar görünür.\n"
     "↓ AZALTIRSAN: nesneler daha çabuk belirir — ama zayıf/hayalet kutu görülebilir."),
    ("kararlilik", "Kutu kararlılığı", "kare", 5, 120, 30,
     "Bir nesne bir an görünmez olursa takibi kaç kare hafızada tutulsun.\n"
     "(Teknik: ByteTrack track_buffer — Ultralytics varsayılanı 30)\n\n"
     "↑ ARTTIRIRSAN: kısa kayıplarda (önünden bir şey geçmesi) takip kopmaz — ama gerçekten "
     "kadraj dışına çıkan nesne geç silinir.\n"
     "↓ AZALTIRSAN: giden nesne hızlı silinir — ama takip daha çok kopar, ID değişir."),
    ("cozunurluk", "Çözünürlük", "secim", 0, len(COZUNURLUK_SECENEK) - 1, 640,
     "Modele verilen görüntü çözünürlüğü — HIZ ile UZAK NESNE görme arasındaki denge.\n"
     "(Ultralytics varsayılanı 640)\n\n"
     "↑ BÜYÜTÜRSEN (960/1280): 15 m'deki küçük hedefi daha iyi görür — ama FPS düşer.\n"
     "↓ KÜÇÜLTÜRSEN (416): akıcı olur, takip gecikmesi azalır — ama uzakta zayıflar.\n\n"
     "NOT: FPS düşerse hareketli hedefte nişan gecikmesi artar — ikisini birlikte düşün."),
    ("iou", "Kutu ayrıştırma (IoU)", "yuzde", 10, 95, 70,
     "Üst üste binen iki kutunun AYNI nesne mi sayılacağı (NMS eşiği).\n"
     "(Ultralytics varsayılanı 0.70)\n\n"
     "↑ ARTTIRIRSAN: yan yana duran hedefler ayrı ayrı kalır — ama aynı nesneye çift kutu riski.\n"
     "↓ AZALTIRSAN: çift kutu temizlenir — ama sürüde (Aşama 2) bitişik hedefler birleşebilir."),
    ("maks_tespit", "En fazla hedef", "sayi", 5, 300, 300,
     "Bir karede en fazla kaç kutu işlensin.\n(Ultralytics varsayılanı 300)\n\n"
     "Düşürmek çok kalabalık sahnede işi hafifletir; yarışma senaryosunda (en fazla 3-4 hedef) "
     "varsayılan zaten fazlasıyla yeterli."),
    ("ayna", "Aynala (yatay çevir)", "anahtar", 0, 1, 0,
     "Görüntüyü yatay çevirir (selfie görünümü).\n\n"
     "VARSAYILAN KAPALI — ham YOLO çıktısıyla birebir aynı görüntü.\n\n"
     "⚠ Webcam ile demo yaparken hareket yönü ters geldiği için açmak isteyebilirsiniz. "
     "Açıldığında nişan matematiğindeki yaw işareti OTOMATİK düzeltilir (yoksa gimbal hedeften "
     "kaçardı). Yarışma kamerasında KAPALI kalmalı."),
]

AYAR_TANIM_NISAN = [
    ("fov", "Kamera görüş açısı", "onda", 200, 1200, 600,
     "Kameranın YATAY görüş açısı (derece). Piksel hatasını açıya çevirmek için kullanılır — "
     "otonom takibin doğruluğu buna bağlıdır.\n\n"
     "Bilmiyorsanız: kameradan bilinen uzaklığa (ör. 2 m) bir cetvel koyup kadraja tam sığan "
     "genişliği (G) ölçün → FOV = 2 × atan(G / (2×2 m)).\n\n"
     "Yanlış girilirse gimbal ya hedefi aşar ya da yavaş yaklaşır."),
    ("kp", "Takip gücü (Kp)", "yuzde", 10, 150, 50,
     "Hedef merkezden kaçtığında hatanın ne kadarını TEK adımda kapatmaya çalışsın.\n\n"
     "↑ ARTTIRIRSAN: hedefe daha hızlı kilitlenir, hareketli hedefte geride kalma azalır — "
     "ama aşma (overshoot) ve salınım riski artar.\n"
     "↓ AZALTIRSAN: yumuşak ve kararlı — ama hareketli hedefin arkasında kalır.\n\n"
     "Hareketli hedefte kalıcı gecikme ≈ (hedef hızı × kare süresi) / Kp."),
    ("kd", "Öngörü süresi (Kd)", "onda", 0, 30, 6,
     "Hedefin KAÇ SANİYE SONRAKİ yerine nişan alınsın (ileri görüş).\n\n"
     "Kamera + işlem gecikmesini telafi eder; tipik olarak bir kare süresi kadar (0.06 sn).\n\n"
     "↑ ARTTIRIRSAN: hızlanan hedefte önünü keser — ama gürültüde zıplama yapar.\n"
     "↓ 0 YAPARSAN: saf oransal kontrol, en sakin ama en geç tepki."),
    ("olu_bolge", "Ölü bölge", "yuzde", 0, 10, 2,
     "Hedef merkeze bu kadar yakınsa (kare genişliğinin yüzdesi) motora komut GÖNDERİLMEZ.\n\n"
     "Amaç: lazer balonun üstünde SABİT dursun (dwell). Sıfırlanırsa sistem her karede "
     "titrer ve balonu patlatacak süre boyunca noktada kalamaz.\n\n"
     "↑ ARTTIRIRSAN: çok sakin durur — ama nişan kabaca ortalanır.\n"
     "↓ AZALTIRSAN: daha hassas ortalar — ama titreme başlar."),
]



# =====================================================================
#  Algilama is parcacigi
# =====================================================================
class AlgiThread(QThread):
    kare_hazir = Signal(QImage, dict)
    durum = Signal(str, bool)               # mesaj, hata_mi
    kameralar_bulundu = Signal(list)        # [{"index": int, "name": str, "is_default": bool}, ...]
    model_bilgi = Signal(str, list)         # ozet metni, eksik siniflar (C7)
    nisan_komut = Signal(float, float)      # d_yaw, d_pitch — Otonom takip (B3)

    def __init__(self):
        super().__init__()
        self._calis = True
        self.estop = False
        self.model_yok = False              # models/ klasorunde model bulunamadi mi
        self.asama = 3                      # 1/2/3/0 — SARTNAME davranisi (renk yalniz A3)
        self.kaynak_istegi = None           # None | "auto" | int
        self.otonom = False                 # Otonom modda mi (nisan dongusu yalniz o zaman)
        self.nisanci = nisan.PDNisanci()    # ayarlari algi.AYAR'dan canli okur
        # A4: "son kare kazanir". GUI yavassa Qt sinyal kuyrugu BIRIKIR (olaylar
        # dusmez!) ve gecikme kartopu gibi buyur. Bu bayrak sayesinde onceki kare
        # ekrana cizilmeden yenisi gonderilmez; ara kareler islenmeden atlanir.
        self._gui_mesgul = False

    def kare_islendi(self):
        """GUI bir kareyi cizdiginde cagirir -> yeni kare gonderilebilir (A4)."""
        self._gui_mesgul = False

    def run(self):
        # --- 1. Kamerayi hemen ac (hizli ~0.2s) ---
        self.durum.emit("Kamera aranıyor…", False)
        cap = algi.open_camera()
        if cap is None:
            self.durum.emit("Kamera bulunamadı — bağlı mı / başka uygulama kullanıyor mu?", True)
            return

        # Kamera listesini hemen bildir
        if algi.AKTIF_INDEX is not None:
            qt_cams = algi.kameralari_listele_qt()
            if qt_cams:
                self.kameralar_bulundu.emit(qt_cams)
            else:
                self.kameralar_bulundu.emit([{"index": algi.AKTIF_INDEX,
                                              "name": f"Kamera {algi.AKTIF_INDEX}",
                                              "is_default": True}])

        # --- 2. Modeli yukle (torch ANA THREAD'de import edildi -> burada guvenli) ---
        model = None
        model_yolu = _model_bul()
        if model_yolu is None:
            # Repo modelsiz gelir. Kamera + OpenCV calisir; tespit icin models/ klasorune
            # bir best.pt eklenmelidir (bkz. models/README.md).
            self.model_yok = True
            self.durum.emit("Model yok — kamera aktif · models/ klasörüne best.pt ekleyin", True)
        else:
            self.durum.emit("Model yükleniyor…", False)
            try:
                model = YOLO(os.path.abspath(model_yolu))
                # C7: modelin GERCEKTEN kac sinif tanidigini ekibe goster. Arayuz 4 tip +
                # balon vaat ederken model 2 sinifliysa bu gercek gizli kalmamali.
                self.model_bilgi.emit(algi.model_sinif_ozeti(model), algi.eksik_siniflar(model))
                self.durum.emit("Sistem hazır", False)
            except Exception as e:
                self.durum.emit(f"Model yüklenemedi: {e}", True)  # ham goruntu akmaya devam

        # A3: kamerayi kendi thread'inde okuyup HEP EN TAZE kareyi tut.
        okuyucu = algi.KameraOkuyucu(cap)
        son_sira = None
        t_son, fps = time.time(), 0.0
        try:
            while self._calis:
                # kamera degisim istegi (arayuzden secim)
                if self.kaynak_istegi is not None:
                    istek = self.kaynak_istegi
                    self.kaynak_istegi = None
                    algi.takip_sifirla()   # kamera degisiyor: eski takip kutulari kalmasin
                    self.nisanci.sifirla()
                    eski = okuyucu.cap
                    okuyucu.cap_degistir(None)
                    if eski is not None:
                        eski.release()
                    self.durum.emit("Kamera değiştiriliyor…", False)
                    yeni = algi.open_camera() if istek == "auto" else algi.ac_kaynak(istek)
                    if yeni is None:
                        self.durum.emit("Seçilen kamera açılamadı — otomatik aranıyor…", True)
                        yeni = algi.open_camera()
                        if yeni is None:
                            self.durum.emit("Hiçbir kamera açılamadı", True)
                            self.msleep(1000)
                            continue
                    okuyucu.cap_degistir(yeni)
                    son_sira = None
                    self.durum.emit("Sistem hazır" if model else "Model yükleniyor… (kamera aktif)",
                                    False)

                # Kamera koptu mu? (okuyucu thread'i ust uste hata aliyorsa)
                if okuyucu.hata_sayaci > 60:
                    self.durum.emit("Kamera koptu — yeniden deneniyor…", True)
                    eski = okuyucu.cap
                    okuyucu.cap_degistir(None)
                    if eski is not None:
                        eski.release()
                    okuyucu.cap_degistir(algi.open_camera())
                    son_sira = None
                    self.msleep(500)
                    continue

                # A4: onceki kare henuz ekrana cizilmediyse yeni kare GONDERME.
                # (Qt kuyrugu birikmesin; gecikme sabit kalsin.)
                if self._gui_mesgul:
                    self.msleep(3)
                    continue

                frame, sira = okuyucu.oku(son_sira)
                if frame is None:              # henuz yeni kare yok
                    self.msleep(3)
                    continue
                son_sira = sira
                frame = frame.copy()           # okuyucu thread'i uzerine yazmasin

                # A6: AYNA artik varsayilan KAPALI ve ayardan yonetiliyor.
                # (Eski kod her kareyi kosulsuz cevirirdi: ham YOLO'dan farkli goruntu
                #  + nisan matematiginde isaret hatasi -> gimbal hedeften kacar.)
                if int(algi.AYAR.get("ayna", 0)):
                    frame = cv2.flip(frame, 1)

                # Model hazirsa: algilama yap. Degilse: ham goruntu gonder
                if model is not None:
                    dets, balonlar, active_idx = algi.analiz_et(model, frame,
                                                                self.estop, self.asama)
                    self._nisan_al(frame, dets, balonlar, active_idx)
                    frame = algi.draw_overlay(frame, dets, active_idx, balonlar, self.estop)
                    data = self._panel_verisi(dets, active_idx, fps)
                else:
                    mesaj = ("Model yok — models/ klasörüne best.pt ekleyin"
                             if self.model_yok else "Model yükleniyor…")
                    data = {"active": None, "hedefler": [], "mesaj": mesaj, "fps": fps,
                            "a3": self.asama == 3}

                now = time.time()
                dt = now - t_son
                t_son = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt)
                data["fps"] = fps

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
                self._gui_mesgul = True
                self.kare_hazir.emit(qimg, data)
        finally:
            okuyucu.kapat()

    def _nisan_al(self, frame, dets, balonlar, active_idx):
        """B3 — OTONOM TAKIP: aktif hedefin piksel hatasindan gimbal komutu uretir.

        Bu katman eskiden HIC YOKTU: sistem hedefi goruyor ama gimbal'a tek komut
        gondermiyordu, yani Otonom modda takip fiilen calismiyordu (Yetenek 5).

        Guvenlik kapilari (sirayla):
          * E-Stop aktifse komut YOK (sartname: E-Stop hareketi keser)
          * Manuel moddaysa komut YOK (operator suruyor)
          * Kilitli hedef yoksa komut YOK + kontrolcu sifirlanir (yeni hedefte sicrama olmasin)
          * Olu bolge icindeysek nisanci zaten (None, None) doner -> komut YOK (dwell)
        Yasak alan kontrolu arayuz tarafinda (_nisan_geldi) yapilir — tek kapi.
        """
        if self.estop or not self.otonom or active_idx < 0 or active_idx >= len(dets):
            self.nisanci.sifirla()
            return
        h, w = frame.shape[:2]
        hedef_xy = nisan.nisan_noktasi(dets[active_idx]["box"], balonlar)
        d_yaw, d_pitch = self.nisanci.adim(hedef_xy, (w, h))
        if d_yaw is not None:
            self.nisan_komut.emit(d_yaw, d_pitch)

    def _panel_verisi(self, dets, active_idx, fps):
        # SARTNAME: A1-A2'de dost yok (hepsi hedef); A3'te dost/dusman (renk). Panel buna gore.
        a3 = (self.asama == 3)
        hedefler = []
        for i, d in enumerate(dets):
            aktif = (i == active_idx)
            if aktif and not self.estop:
                durum = "◉ Kilitli"
            elif a3 and d["tip"] == "Dost":
                durum = "Dost — geç"
            else:
                durum = "Bekliyor"
            hedefler.append({"ad": d["ad"], "tip": d["tip"], "durum": durum, "aktif": aktif})
        active = None
        if active_idx >= 0 and not self.estop:
            d = dets[active_idx]
            active = {"ad": d["ad"], "tip": d["tip"], "conf": d["conf"], "box": d["box"]}
        if self.estop:
            mesaj = "ACİL DURDURULDU — ateş ve kilit kesildi"
        elif active:
            mesaj = f"{active['ad']} kilitlendi — %{active['conf']} güven"
        else:
            mesaj = "Hedef aranıyor…"
        return {"active": active, "hedefler": hedefler, "mesaj": mesaj, "fps": fps, "a3": a3}

    def durdur(self):
        self._calis = False


class TaramaThread(QThread):
    """QMediaDevices ile tum kameralari arka planda bulur (gereksizse eski index taramasi yapar)."""
    bulundu = Signal(list)   # [{"index": int, "name": str, "is_default": bool}, ...]

    def run(self):
        try:
            sonuc = algi.kameralari_listele_qt()
            if not sonuc:
                # fallback: eski index taramasi
                idx_list = algi.kameralari_listele()
                sonuc = [{"index": i, "name": f"Kamera {i}", "is_default": False}
                         for i in idx_list]
            self.bulundu.emit(sonuc)
        except Exception:
            self.bulundu.emit([])


# =====================================================================
#  Asama-1: Surukle-sirala hedef kartlari (Sartname Gorev-1 zarf sirasi)
#  Qt DnD DEGIL, fare tabanli -> QGraphicsProxyWidget icinde sorunsuz calisir.
# =====================================================================
class Kart(QFrame):
    def __init__(self, ust, cls, ad, pixmap):
        super().__init__(ust)
        self.cls = cls
        self.ust = ust
        self.setObjectName("kart")
        self.setFixedSize(ust.KART_W, ust.KART_H)
        v = QVBoxLayout(self)
        v.setContentsMargins(5, 4, 5, 4)
        v.setSpacing(2)

        # Ust satir: rozet + ad
        ust_row = QHBoxLayout()
        ust_row.setContentsMargins(0, 0, 0, 0)
        ust_row.setSpacing(4)

        self.rozet = QLabel("1")
        self.rozet.setObjectName("kartno")
        self.rozet.setFixedSize(16, 16)
        self.rozet.setAlignment(Qt.AlignCenter)
        ust_row.addWidget(self.rozet, 0, Qt.AlignVCenter)

        adl = QLabel(ad)
        adl.setObjectName("kartad")
        adl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        ust_row.addWidget(adl, 1, Qt.AlignVCenter)
        v.addLayout(ust_row)

        # Alt: gorsel
        img = QLabel()
        img.setAlignment(Qt.AlignCenter)
        if not pixmap.isNull():
            img.setPixmap(pixmap.scaled(ust.KART_W - 12, 30,
                          Qt.KeepAspectRatio, Qt.SmoothTransformation))
        v.addWidget(img, 1)
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, e):
        self.setCursor(Qt.ClosedHandCursor)
        self.ust._bas(self, e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        self.ust._surukle(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.OpenHandCursor)
        self.ust._birak()


class SiraliKartlar(QWidget):
    KART_W, KART_H, GAP = 120, 65, 8

    def __init__(self, tanimlar, grafik_dir):
        super().__init__()
        self.kartlar = []
        for cls, ad in tanimlar:
            pm = QPixmap(os.path.join(grafik_dir, f"kart_{cls}.png"))
            self.kartlar.append(Kart(self, cls, ad, pm))
        n = len(self.kartlar)
        self.sira = list(range(n))     # gosterim sirasi -> kart index
        self._dragging = None
        self._offset = 0
        W = n * self.KART_W + (n - 1) * self.GAP
        self.setFixedSize(W, self.KART_H + 4)
        self._dizil()

    def _slot_x(self, pos):
        return pos * (self.KART_W + self.GAP)

    def _dizil(self):
        for pos, ki in enumerate(self.sira):
            k = self.kartlar[ki]
            k.rozet.setText(str(pos + 1))
            if k is not self._dragging:
                k.move(self._slot_x(pos), 2)

    def _bas(self, kart, gpos):
        self._dragging = kart
        kart.raise_()
        self._offset = self.mapFromGlobal(gpos).x() - kart.x()

    def _surukle(self, gpos):
        if not self._dragging:
            return
        x = self.mapFromGlobal(gpos).x() - self._offset
        x = max(0, min(self.width() - self.KART_W, x))
        self._dragging.move(x, 2)
        hedef = int((x + self.KART_W / 2) // (self.KART_W + self.GAP))
        hedef = max(0, min(len(self.sira) - 1, hedef))
        simdi = self.sira.index(self.kartlar.index(self._dragging))
        if hedef != simdi:
            ki = self.sira.pop(simdi)
            self.sira.insert(hedef, ki)
            self._dizil()

    def _birak(self):
        if self._dragging:
            self._dragging = None
            self._dizil()

    def sirali_tipler(self):
        """Kullanicinin dizdigi imha sirasini tip listesi olarak dondurur."""
        return [self.kartlar[ki].cls for ki in self.sira]


# =====================================================================
#  Ana pencere — HTML yerlesiminin birebir kopyasi
# =====================================================================
class MainWindow(QMainWindow):
    KART_TANIM = [("fuze", "Balistik Füze"), ("helikopter", "Helikopter"),
                  ("f16", "Savaş Uçağı"), ("drone", "Mini/Micro İHA")]
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DERİN MAVİ — Görev Kontrol İstasyonu")
        self.mod = "Manuel"
        self.asama = "Aşama 1"
        self._ayar_yukle()   # kayitli ayarlar varsa algi.AYAR'a yukle (sliderlar bunu okur)

        # Icerik tuvali: yuksekligi sabit 900, GENISLIGI EKRANIN ORANINA gore ayarlanir.
        # Boylece her ekranda (16:9, 16:10, ultrawide...) yan bosluk (letterbox) KALMAZ.
        # Pencere kucultulunce QGraphicsView orantili olcekler (tarayici zoom gibi).
        scr = QApplication.primaryScreen().availableGeometry()
        self.CH = 900
        self.CW = int(round(self.CH * scr.width() / max(1, scr.height())))
        self.CW = max(1360, min(2100, self.CW))   # makul sinirlar

        merkez = QWidget()
        merkez.setObjectName("content")
        merkez.setFixedSize(self.CW, self.CH)
        self.content = merkez
        kok = QVBoxLayout(merkez)
        kok.setContentsMargins(0, 0, 0, 0)
        kok.setSpacing(0)

        # --- topbar ---
        ust_sar = QWidget()
        usv = QVBoxLayout(ust_sar)
        usv.setContentsMargins(12, 8, 12, 0)
        usv.addWidget(self._topbar())
        kok.addWidget(ust_sar)

        # --- main ---
        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(12, 12, 12, 12)
        mv.setSpacing(12)
        kok.addWidget(main, 1)

        # 1. Ust Alan (Kamera sol, Aktif Hedef + Tespit Tablosu sag)
        ust_alan = QWidget()
        uh = QHBoxLayout(ust_alan)
        uh.setContentsMargins(0, 0, 0, 0)
        uh.setSpacing(12)

        uh.addWidget(self._sol_kolon(), 5)
        uh.addWidget(self._sag_kolon(), 4)
        mv.addWidget(ust_alan, 1)

        # 2. Alt Panel (Sistem Durumu + Hedef Durumu + Yasak Alanlar)
        mv.addWidget(self._alt_panel(), 0)

        # --- status bar ---
        kok.addWidget(self._sbar())

        self._stil()

        # --- Orantili olcekleme sarmalayicisi (tarayici zoom mantigi) ---
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, self.CW, self.CH)
        self.proxy = self.scene.addWidget(merkez)
        self.view = QGraphicsView(self.scene, self)
        self.view.setObjectName("view")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setBackgroundBrush(QColor(BG))
        self.view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setCentralWidget(self.view)
        self.setMinimumSize(760, 500)
        self.resize(1280, 800)

        # mod-asama kilidini ilk durum icin uygula (stack + pill + kural senkron)
        self._mod_sec(self.mod)

        # saat
        self.saat_timer = QTimer(self)
        self.saat_timer.timeout.connect(self._saat_guncelle)
        self.saat_timer.start(1000)
        self._saat_guncelle()
        # CANLI gostergesi baslangicta gizli (kamera henuz baslamadi)
        self.live_dot.setVisible(False)

        # Kontrol katmani (mock-ESP32 varsayilan; DERINMAVI_ESP env ile gercek porta gecilir)
        self.kontrol = kontrol_mod.Kontrol()
        if self.kontrol.bagli:
            etiket = "· mock (simülasyon)" if self.kontrol.mock_mu else f"· {self.kontrol.kaynak}"
            self._ci("ESP32", AMB if self.kontrol.mock_mu else GRN, etiket)
            self._ci("Seri Port", AMB if self.kontrol.mock_mu else GRN, "· 115200 baud")
        elif self.kontrol.hata:
            self._ci("ESP32", BD2, "· hata")

        # Kamera secici listesini HEMEN doldur (kamera acilisini bekleme)
        try:
            self._kameralar_geldi(algi.kameralari_listele_qt())
        except Exception:
            pass

        # algi thread
        self.thread = AlgiThread()
        self.thread.asama = self.ASAMA_IDX[self.asama]   # ilk asamayi ilet (renk yalniz A3)
        self.thread.otonom = (self.mod == "Otonom")      # nisan dongusu yalniz Otonom'da
        self.thread.kare_hazir.connect(self._kare_geldi)
        self.thread.durum.connect(self._durum_geldi)
        self.thread.kameralar_bulundu.connect(self._kameralar_geldi)
        self.thread.model_bilgi.connect(self._model_bilgi_geldi)   # C7
        self.thread.nisan_komut.connect(self._nisan_geldi)         # B3 otonom takip
        self.thread.start()

        # Ayar paneli acikken panel disina tiklaninca kapansin (uygulama geneli olay filtresi)
        QApplication.instance().installEventFilter(self)

    # ================= TOPBAR =================
    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("top")
        bar.setFixedHeight(76)
        h = QHBoxLayout(bar)
        # DIKKAT: dikey (ust/alt) marj MUTLAKA > 0 olmali. Sifir birakilirsa QHBoxLayout
        # icindeki gruplar (varsayilan davranisla) barin TUM yuksekligine gerilir
        # ve pilli kutular hicbir bosluk birakmadan barin ust/alt kenarina yapisir — daha
        # once yasanan tam olarak buydu. 12px dikey marj + her ekleme AlignVCenter ile
        # kutular kompakt kalir ve barin ortasinda rahat bir sekilde durur.
        h.setContentsMargins(24, 12, 24, 12)
        h.setSpacing(20)

        def ekle(widget, stretch=0):
            h.addWidget(widget, stretch, Qt.AlignVCenter)

        # Logo + "Hava Savunma Sistemi" yazisi
        brand_w = QWidget()
        bh = QHBoxLayout(brand_w)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(11)
        logo = QLabel()
        logo_path = os.path.join(HERE, "Grafik", "logo-mKXFEkR2.png")
        pm = QPixmap(logo_path)
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(40, Qt.SmoothTransformation))
        else:
            logo.setText("DERİN MAVİ")
            logo.setObjectName("brand")
        bh.addWidget(logo, 0, Qt.AlignVCenter)
        brand_txt = QLabel("Hava Savunma Sistemi")
        brand_txt.setObjectName("brandtxt")
        bh.addWidget(brand_txt, 0, Qt.AlignVCenter)
        ekle(brand_w)
        ekle(self._div())

        # Calisma Modu
        self.mod_btns = {}
        ekle(self._tab_grubu("ÇALIŞMA MODU", ("Manuel", "Otonom"),
                             self.mod, self._mod_sec, self.mod_btns))
        ekle(self._div())
        # Aktif Gorev (opsiyonel: hicbiri secili olmayabilir; moda gore kilitli)
        self.asama_btns = {}
        ekle(self._tab_grubu("AKTİF GÖREV", ("Aşama 1", "Aşama 2", "Aşama 3"),
                             self.asama, self._asama_sec, self.asama_btns,
                             optional=True))
        ekle(self._div())

        # KAMERA secici + CANLI göstergesi. Diger iki grupla (ÇALIŞMA MODU / AKTİF GÖREV)
        # AYNI dikey yerlesim (baslik + control satiri) kullanilir ki uc grup da ortak bir
        # taban cizgisinde hizalansin (simetri). Kutulu ("tabs") sarmalama YAPILMAZ —
        # #camsel zaten kendi kutu stiline sahip; ust uste iki kutu (cift cerceve) olurdu.
        kam_g = QWidget()
        kv = QVBoxLayout(kam_g)
        kv.setContentsMargins(0, 0, 0, 0)
        kv.setSpacing(4)
        cap = QLabel("KAMERA")
        cap.setObjectName("tgcap")
        kv.addWidget(cap)
        kam_row = QWidget()
        krh = QHBoxLayout(kam_row)
        krh.setContentsMargins(0, 0, 0, 0)
        krh.setSpacing(8)
        self.kam_sec = QComboBox()
        self.kam_sec.setObjectName("camsel")
        self.kam_sec.addItem("Otomatik", "auto")
        self.kam_sec.currentIndexChanged.connect(self._kamera_sec)
        krh.addWidget(self.kam_sec, 0, Qt.AlignVCenter)
        # CANLI rozeti (kamera seçicinin sağında)
        self.live_dot = QLabel()
        self.live_dot.setFixedSize(7, 7)
        self.live_dot.setStyleSheet(f"background:{RED};border-radius:3px;")
        live_lbl = QLabel("CANLI")
        live_lbl.setObjectName("livet")
        krh.addWidget(self.live_dot, 0, Qt.AlignVCenter)
        krh.addWidget(live_lbl, 0, Qt.AlignVCenter)
        krh.addStretch(1)
        kv.addWidget(kam_row)
        ekle(kam_g)

        h.addStretch(1)

        # NOT: cihaz durum gostergeleri (Kamera/Lazer/ESP32/Seri Port) alt cubuga tasindi.
        ekle(self._div())
        self.estop_btn = QPushButton("⏻ ACİL DURDUR")
        self.estop_btn.setObjectName("estop")
        self.estop_btn.setCheckable(True)
        self.estop_btn.clicked.connect(self._estop_bas)
        ekle(self.estop_btn)
        return bar

    def _tab_grubu(self, baslik, isimler, aktif, cb, kayit, optional=False):
        g = QWidget()
        v = QVBoxLayout(g)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        cap = QLabel(baslik)
        cap.setObjectName("tgcap")
        v.addWidget(cap)
        tabs = QFrame()
        tabs.setObjectName("tabs")
        th = QHBoxLayout(tabs)
        th.setContentsMargins(3, 3, 3, 3)
        th.setSpacing(2)
        grp = QButtonGroup(self)
        grp.setExclusive(not optional)   # asama grubu opsiyonel (hicbiri secili olmayabilir)
        for ad in isimler:
            b = QPushButton(ad)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setChecked(ad == aktif)
            b.clicked.connect(lambda _, a=ad: cb(a))
            grp.addButton(b)
            th.addWidget(b)
            kayit[ad] = b
        v.addWidget(tabs)
        return g

    def _div(self):
        f = QFrame()
        f.setObjectName("vdiv")
        f.setFixedSize(1, 22)
        return f

    # ================= SOL KOLON (KAMERA) =================
    def _sol_kolon(self):
        kol = QWidget()
        v = QVBoxLayout(kol)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # --- kamera ---
        self.cam = QFrame()
        self.cam.setObjectName("cam")
        cl = QVBoxLayout(self.cam)
        cl.setContentsMargins(0, 0, 0, 0)
        self.video = QLabel("Kamera başlatılıyor…")
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.video)

        # kamera sol ustune ⚙ Ayarlar butonu + acilir panel (video uzerinde)
        self._ayar_overlay_kur(self.cam)

        v.addWidget(self.cam, 1)
        return kol

    def _tur_panel(self, n):
        """Asama 2/3: Tur X/n sayaci + n nokta + bu-tur bilgisi."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(12)
        tl = QLabel('Tur <b>0</b><span style="color:%s;font-size:15px;font-weight:400"> / %d</span>' % (TXT3, n))
        tl.setObjectName("turn")
        row.addWidget(tl)
        td = QWidget()
        tdh = QHBoxLayout(td)
        tdh.setContentsMargins(0, 0, 0, 0)
        tdh.setSpacing(5)
        for _ in range(n):
            d = QLabel()
            d.setFixedSize(20, 5)
            d.setStyleSheet(f"background:{BD2};border-radius:3px;")
            tdh.addWidget(d)
        row.addWidget(td)
        row.addStretch(1)
        v.addLayout(row)
        if n == 4:
            bilgi = QLabel(f'Bu tur: 3 koldan <b style="color:{RED}">3 hedef</b> '
                           f'(Balistik Füze + Mini/Micro İHA) · tümü düşman, sınıflandırma yok')
        else:
            bilgi = QLabel(f'Bu tur: <b style="color:{RED}">1 Düşman</b> + '
                           f'<i style="color:{BLUE}">2 Dost</i> · düşmanı tipine göre uygun menzilde imha')
        bilgi.setObjectName("turbilgi")
        bilgi.setWordWrap(True)
        v.addWidget(bilgi)
        v.addStretch(1)
        return w

    # ================= AYAR PANELI (canli goruntu isleme ayarlari) =================
    def _ayar_overlay_kur(self, parent):
        """Kamera sol ustune ⚙ butonu + acilir ayar paneli koyar (video uzerinde overlay)."""
        self.ayar_sliderlar = {}   # key -> (slider, tip)

        self.ayar_btn = QPushButton("⚙", parent)
        self.ayar_btn.setObjectName("ayarbtn")
        self.ayar_btn.setFixedSize(34, 34)
        self.ayar_btn.setCursor(Qt.PointingHandCursor)
        self.ayar_btn.setToolTip("Görüntü işleme ayarları")
        self.ayar_btn.move(10, 10)
        self.ayar_btn.clicked.connect(self._ayar_toggle)

        self.ayar_panel = QFrame(parent)
        self.ayar_panel.setObjectName("ayarpanel")
        self.ayar_panel.setFixedWidth(336)
        self.ayar_panel.move(12, 54)
        # NOT: QGraphicsDropShadowEffect KULLANMA — tum arayuz bir QGraphicsView (proxy) icinde
        # cizildigi icin efekt render'i bozup siyah kutu artefakti birakiyor. Derinlik hissi
        # kenarlik + yuvarlak kose + koyu video ustunde durmasiyla zaten var.

        pv = QVBoxLayout(self.ayar_panel)
        pv.setContentsMargins(18, 15, 18, 16)
        pv.setSpacing(16)

        # --- baslik satiri: baslik + kapat (x) ---
        brow = QHBoxLayout()
        brow.setSpacing(8)
        bas = QLabel("Görüntü İşleme")
        bas.setObjectName("ayarbaslik")
        brow.addWidget(bas)
        brow.addStretch(1)
        self.ayar_kapat_btn = QPushButton("✕")
        self.ayar_kapat_btn.setObjectName("ayarkapat")
        self.ayar_kapat_btn.setFixedSize(24, 24)
        self.ayar_kapat_btn.setCursor(Qt.PointingHandCursor)
        self.ayar_kapat_btn.clicked.connect(lambda: self.ayar_panel.setVisible(False))
        brow.addWidget(self.ayar_kapat_btn)
        pv.addLayout(brow)

        # Ayarlar KAYDIRILABILIR bir alanda: 11 ayar sabit yukseklikte panele sigmaz
        # ve video alanini tasardi. Baslik ile Sifirla/Kaydet butonlari sabit kalir,
        # yalnizca ayar listesi kayar.
        ic = QWidget()
        ic.setObjectName("ayaric")
        iv = QVBoxLayout(ic)
        iv.setContentsMargins(0, 0, 8, 0)     # sagda kaydirma cubugu payi
        iv.setSpacing(15)

        # Iki grup: TESPIT (YOLO/ByteTrack) ve NISAN (gimbal geometrisi).
        # Gruplar hangi ayarin neyi etkiledigini bir bakista gosterir.
        for baslik, tanimlar in (("TESPİT", AYAR_TANIM_TESPIT),
                                 ("NİŞAN (Otonom takip)", AYAR_TANIM_NISAN)):
            gb = QLabel(baslik)
            gb.setObjectName("ayargrup")
            iv.addWidget(gb)
            for tanim in tanimlar:
                self._ayar_satiri(iv, tanim)

        kaydir = QScrollArea()
        kaydir.setObjectName("ayarkaydir")
        kaydir.setWidget(ic)
        kaydir.setWidgetResizable(True)
        kaydir.setFrameShape(QFrame.NoFrame)
        kaydir.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        kaydir.setMaximumHeight(430)
        pv.addWidget(kaydir, 1)

        alt = QHBoxLayout()
        self.ayar_sifirla_btn = QPushButton("Sıfırla")
        self.ayar_sifirla_btn.setObjectName("ayaralt")
        self.ayar_sifirla_btn.setCursor(Qt.PointingHandCursor)
        self.ayar_sifirla_btn.setMinimumHeight(32)
        self.ayar_sifirla_btn.clicked.connect(self._ayar_sifirla)
        self.ayar_kaydet_btn = QPushButton("Kaydet")
        self.ayar_kaydet_btn.setObjectName("ayarkaydet")
        self.ayar_kaydet_btn.setCursor(Qt.PointingHandCursor)
        self.ayar_kaydet_btn.setMinimumHeight(32)
        self.ayar_kaydet_btn.clicked.connect(self._ayar_kaydet)
        alt.addWidget(self.ayar_sifirla_btn)
        alt.addStretch(1)
        alt.addWidget(self.ayar_kaydet_btn)
        pv.addLayout(alt)

        self.ayar_panel.setVisible(False)
        self.ayar_panel.adjustSize()
        self.ayar_btn.raise_()

    def _ayar_satiri(self, layout, tanim):
        key, baslik, tip, mn, mx, oneri, aciklama = tanim
        kutu = QVBoxLayout()          # her ayar kendi grubunda (ic bosluk dar, gruplar arasi genis)
        kutu.setSpacing(6)
        ust = QHBoxLayout()
        ust.setSpacing(7)
        lab = QLabel(baslik)
        lab.setObjectName("ayarlbl")
        info = QLabel("i")
        info.setObjectName("ayarinfo")
        info.setFixedSize(16, 16)
        info.setAlignment(Qt.AlignCenter)
        info.setCursor(Qt.WhatsThisCursor)
        # Uzerine gelince aciklama (tooltip) — ekstra popup yok. Satirlar <br> ile sarilir.
        ipucu = f"<div style='max-width:300px; white-space:normal'>{aciklama.replace(chr(10), '<br>')}</div>"
        info.setToolTip(ipucu)
        lab.setToolTip(ipucu)
        deger = QLabel()
        deger.setObjectName("ayardeg")
        ust.addWidget(lab)
        ust.addWidget(info)
        ust.addStretch(1)
        ust.addWidget(deger)
        kutu.addLayout(ust)

        sl = QSlider(Qt.Horizontal)
        sl.setMinimum(0 if tip == "secim" else mn)
        sl.setMaximum(len(COZUNURLUK_SECENEK) - 1 if tip == "secim" else mx)
        sl.setValue(self._ayar_slider_deger(key, tip))
        sl.oneri_val = (COZUNURLUK_SECENEK.index(oneri) if tip == "secim" else oneri)
        sl.setObjectName("ayarsl")
        sl.valueChanged.connect(lambda val, k=key, t=tip, d=deger, s=sl: self._ayar_degisti(k, t, val, d, s))
        kutu.addWidget(sl)

        layout.addLayout(kutu)
        self.ayar_sliderlar[key] = (sl, tip)
        self._ayar_degisti(key, tip, sl.value(), deger, sl)

    # --- ayar deger donusumleri: slider tam sayidir, ayar degeri olcekli olabilir ---
    def _ayar_slider_deger(self, key, tip):
        """algi.AYAR'daki degeri slider tam sayisina cevirir."""
        v = algi.AYAR[key]
        if tip == "secim":
            # Kayitli cozunurluk listede yoksa en yakinina yuvarla (bozuk ayarlar.json)
            if int(v) in COZUNURLUK_SECENEK:
                return COZUNURLUK_SECENEK.index(int(v))
            return min(range(len(COZUNURLUK_SECENEK)),
                       key=lambda i: abs(COZUNURLUK_SECENEK[i] - int(v)))
        if tip == "yuzde":
            return int(round(float(v) * 100))
        if tip == "onda":
            return int(round(float(v) * 10))
        return int(v)                                  # "kare", "sayi", "anahtar"

    def _ayar_gercek_deger(self, tip, val):
        """Slider tam sayisini algi.AYAR degerine cevirir."""
        if tip == "secim":
            return COZUNURLUK_SECENEK[val]
        if tip == "yuzde":
            return val / 100.0
        if tip == "onda":
            return val / 10.0
        return int(val)                                # "kare", "sayi", "anahtar"

    def _ayar_deger_yaz(self, tip, val, lbl, key=None):
        if tip == "yuzde":
            lbl.setText(f"{val / 100:.2f}")
        elif tip == "secim":
            lbl.setText(f"{COZUNURLUK_SECENEK[val]} px")
        elif tip == "onda":
            birim = "°" if key == "fov" else " sn"
            lbl.setText(f"{val / 10:.1f}{birim}")
        elif tip == "anahtar":
            lbl.setText("Açık" if val else "Kapalı")
        elif tip == "sayi":
            lbl.setText(str(val))
        else:
            lbl.setText(f"{val} kare")

    def _ayar_degisti(self, key, tip, val, deger_lbl, slider):
        algi.ayar_guncelle(**{key: self._ayar_gercek_deger(tip, val)})
        self._ayar_deger_yaz(tip, val, deger_lbl, key)
        self._slider_stil_guncelle(slider, val, deger_lbl)

    def _slider_stil_guncelle(self, sl, val, deger_lbl=None):
        """Kaydirici onerilen degerdeyse YESIL, degistirilmisse MAVI gorunur.
        Iki durum yalnizca tutamac/etiket renklerinde ayrisir (bkz. SLIDER_* sabitleri)."""
        onerilen = (val == getattr(sl, "oneri_val", None))
        sl.setStyleSheet(SLIDER_TASLAK.format(**(SLIDER_ONERI if onerilen else SLIDER_DEGISIK)))
        if deger_lbl:
            deger_lbl.setStyleSheet(
                ETIKET_ONERI if onerilen else ETIKET_DEGISIK)

    def _ayar_toggle(self):
        gorunur = not self.ayar_panel.isVisible()
        self.ayar_panel.setVisible(gorunur)
        if gorunur:
            self.ayar_panel.raise_()

    def eventFilter(self, obj, event):
        """Ayar paneli acikken panelin/butonun DISINA tiklaninca paneli kapat.

        DIKKAT: QGraphicsView icinde gercek olay hedefi cogu zaman viewport'tur (parent
        zinciri panele ulasmaz). Bu yuzden parent-zinciri DEGIL, GEOMETRI ile bakariz:
        tiklama noktasini sahne(content) koordinatina cevirip panelin/butonun dikdortgeni
        icinde mi diye kontrol ederiz.
        """
        if (event.type() == QEvent.MouseButtonPress
                and getattr(self, "ayar_panel", None) is not None
                and self.ayar_panel.isVisible()):
            try:
                gp = event.globalPosition().toPoint()
                vp = self.view.viewport().mapFromGlobal(gp)
                sahne = self.view.mapToScene(vp).toPoint()   # sahne = content koordinati

                def _icinde(w):
                    tl = w.mapTo(self.content, QPoint(0, 0))
                    return QRect(tl, w.size()).contains(sahne)

                if not (_icinde(self.ayar_panel) or _icinde(self.ayar_btn)):
                    self.ayar_panel.setVisible(False)
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _ayar_sifirla(self):
        algi.ayar_guncelle(**algi.VARSAYILAN_AYAR)
        for key, (sl, tip) in self.ayar_sliderlar.items():
            sl.setValue(self._ayar_slider_deger(key, tip))

    def _ayar_dosya(self):
        return os.path.join(HERE, "ayarlar.json")

    def _ayar_yukle(self):
        import json
        p = self._ayar_dosya()
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                algi.ayar_guncelle(**{k: v for k, v in d.items() if k in algi.AYAR})
            except Exception:
                pass

    def _ayar_kaydet(self):
        import json
        try:
            with open(self._ayar_dosya(), "w", encoding="utf-8") as f:
                json.dump(algi.AYAR, f, ensure_ascii=False, indent=2)
            self.ayar_kaydet_btn.setText("✓ Kaydedildi")
            QTimer.singleShot(1500, lambda: self.ayar_kaydet_btn.setText("Kaydet"))
        except Exception:
            self.ayar_kaydet_btn.setText("✗ Hata")
            QTimer.singleShot(1500, lambda: self.ayar_kaydet_btn.setText("Kaydet"))

    # ================= SAG KOLON =================
    def _sag_kolon(self):
        kol = QWidget()
        v = QVBoxLayout(kol)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # --- aktif hedef ---
        kart = QFrame()
        kart.setObjectName("panelk")
        kv = QVBoxLayout(kart)
        kv.setContentsMargins(19, 13, 19, 13)
        kv.setSpacing(8)
        t = QLabel("AKTİF HEDEF")
        t.setObjectName("ph")
        kv.addWidget(t)

        hrow = QHBoxLayout()
        hrow.setSpacing(10)
        self.h_ad = QLabel("—")
        self.h_ad.setObjectName("hname")
        hrow.addWidget(self.h_ad)
        self.h_badge = QLabel("—")
        self.h_badge.setObjectName("badge")
        self._badge_stil(self.h_badge, None)
        hrow.addWidget(self.h_badge)
        hrow.addStretch(1)
        self.h_conf = QLabel("")
        self.h_conf.setObjectName("hconf")
        hrow.addWidget(self.h_conf)
        kv.addLayout(hrow)

        self.fire_btn = QPushButton("A T E Ş")
        self.fire_btn.setObjectName("fire")
        self.fire_btn.setFixedHeight(44)
        self.fire_btn.setCheckable(True)
        self.fire_btn.clicked.connect(self._ates_bas)
        kv.addWidget(self.fire_btn)

        self.fire_status = QLabel("Hedef aranıyor…")
        self.fire_status.setObjectName("firest")
        self.fire_status.setAlignment(Qt.AlignCenter)
        kv.addWidget(self.fire_status)
        v.addWidget(kart)

        # --- tespit tablosu ---
        self.tk = QFrame()
        self.tk.setObjectName("panelk")
        tv = QVBoxLayout(self.tk)
        tv.setContentsMargins(19, 13, 19, 13)
        tv.setSpacing(8)
        tt = QLabel("TESPİT EDİLEN HEDEFLER")
        tt.setObjectName("ph")
        tv.addWidget(tt)
        self.tablo = QTableWidget(0, 3)
        self.tablo.setHorizontalHeaderLabels(["SINIF", "TİP", "DURUM"])
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tablo.setSelectionMode(QTableWidget.NoSelection)
        self.tablo.setFocusPolicy(Qt.NoFocus)
        self.tablo.setShowGrid(False)
        hh = self.tablo.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        tv.addWidget(self.tablo)

        # Sag kolon stacked widget (Otonom = Tablo, Manuel = Yon kontrolleri)
        self.sag_stack = QStackedWidget()
        self.sag_stack.addWidget(self.tk)                       # 0: Otonom
        self.manuel_panel = self._manuel_kontrol_panel()
        self.sag_stack.addWidget(self.manuel_panel)             # 1: Manuel
        v.addWidget(self.sag_stack, 1)

        return kol

    # ================= MANUEL YÖN VE NİŞAN KONTROLÜ =================
    def _manuel_kontrol_panel(self):
        """Manuel mod paneli. Ic stack: 0 = D-pad kontrolleri, 1 = aci/yasak alan ayarlari."""
        mk = QFrame()
        mk.setObjectName("panelk")
        mv = QVBoxLayout(mk)
        mv.setContentsMargins(16, 12, 16, 12)
        mv.setSpacing(8)

        # Baslik + "Aci Ayarlari" butonu
        brow = QHBoxLayout()
        mt = QLabel("MANUEL NİŞAN & YÖN KONTROLÜ")
        mt.setObjectName("ph")
        brow.addWidget(mt, 1)
        self.aci_ayar_btn = QPushButton("⚙ Açı Ayarları")
        self.aci_ayar_btn.setObjectName("ayaralt")
        self.aci_ayar_btn.setCursor(Qt.PointingHandCursor)
        self.aci_ayar_btn.setFixedHeight(24)
        self.aci_ayar_btn.clicked.connect(self._aci_ayarlar_toggle)
        brow.addWidget(self.aci_ayar_btn, 0)
        mv.addLayout(brow)

        self._aci_durum_baslat()

        self.manuel_inner_stack = QStackedWidget()
        self.manuel_inner_stack.addWidget(self._dpad_sayfasi())        # 0
        self.manuel_inner_stack.addWidget(self._aci_ayar_sayfasi())    # 1
        mv.addWidget(self.manuel_inner_stack, 1)
        return mk

    def _aci_durum_baslat(self):
        """Gimbal aci durumu ve yasak alan sinirlari (arayuz tarafindaki tek kaynak)."""
        self.pan_aci = 0.0            # azimut, 0-360
        self.tilt_aci = 0.0           # yukselis, 0 - max_tilt_limit
        self.max_tilt_limit = 60.0
        self.aci_adim = 5.0           # D-pad adim hassasiyeti (derece)

        self.pan_yasak_aktif = False  # harekete yasak alan (azimut)
        self.pan_yasak_min = 120.0
        self.pan_yasak_max = 160.0
        self.tilt_yasak_aktif = False # harekete yasak alan (yukselis)
        self.tilt_yasak_min = 45.0
        self.tilt_yasak_max = 60.0
        self.atis_yasak_aktif = False # atisa yasak alan (azimut)
        self.atis_pan_min = 45.0
        self.atis_pan_max = 75.0

    # ---- Ic sayfa 0: D-pad ----
    def _dpad_sayfasi(self):
        sayfa = QWidget()
        dv = QVBoxLayout(sayfa)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(8)
        dv.addWidget(self._aci_gostergesi())

        self.bolge_status = QLabel("● BÖLGE GÜVENLİ")
        self.bolge_status.setObjectName("firest")
        self.bolge_status.setAlignment(Qt.AlignCenter)
        self.bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
        dv.addWidget(self.bolge_status)

        dv.addWidget(self._dpad_izgarasi(), 0, Qt.AlignCenter)
        dv.addLayout(self._adim_butonlari())
        return sayfa

    def _aci_gostergesi(self):
        """Canli azimut/yukselis sayi gostergesi."""
        kutu = QFrame()
        kutu.setObjectName("angtgl")
        gh = QHBoxLayout(kutu)
        gh.setContentsMargins(12, 6, 12, 6)
        gh.setSpacing(12)

        def sutun(baslik, renk):
            v = QVBoxLayout()
            v.setSpacing(1)
            bl = QLabel(baslik)
            bl.setObjectName("engsub")
            deger = QLabel("0.0°")
            deger.setObjectName("turn")
            deger.setStyleSheet(f"font-size:18px; color:{renk}; font-weight:700;")
            v.addWidget(bl)
            v.addWidget(deger)
            return v, bl, deger

        pan_kol, _, self.pan_val_lbl = sutun("AZİMUT (PAN)", TXT)
        gh.addLayout(pan_kol, 1)

        ayirac = QFrame()
        ayirac.setObjectName("vdiv")
        ayirac.setFixedWidth(1)
        gh.addWidget(ayirac)

        tilt_kol, self.tilt_lbl_ref, self.tilt_val_lbl = sutun(
            f"YÜKSELİŞ (TİLT max {int(self.max_tilt_limit)}°)", BLUE)
        gh.addLayout(tilt_kol, 1)
        return kutu

    def _dpad_izgarasi(self):
        """Yon tus takimi. 4 stil (normal/basili x kenar/merkez) tek sablondan uretilir."""
        self._key_normal_style = DPAD_STIL.format(**DPAD_KENAR)
        self._key_active_style = DPAD_STIL_BASILI.format(**DPAD_KENAR_BASILI)
        self._key_center_normal_style = DPAD_STIL.format(**DPAD_MERKEZ)
        self._key_center_active_style = DPAD_STIL_BASILI.format(**DPAD_MERKEZ_BASILI)

        dpad = QWidget()
        gl = QGridLayout(dpad)
        gl.setContentsMargins(0, 2, 0, 2)
        gl.setSpacing(6)

        # (isim, metin, satir, kolon, ipucu, yon, merkez_mi)
        tuslar = [
            ("btn_up", "▲\nW", 0, 1, "[W] veya [▲] — YUKARI (TİLT +)", "up", False),
            ("btn_left", "◀\nA", 1, 0, "[A] veya [◄] — SOL (PAN -)", "left", False),
            ("btn_center", "✛\nMERKEZ", 1, 1, "[R] veya [Space] — SIFIRLA / MERKEZ (0°, 0°)", "home", True),
            ("btn_right", "►\nD", 1, 2, "[D] veya [►] — SAĞ (PAN +)", "right", False),
            ("btn_down", "▼\nS", 2, 1, "[S] veya [▼] — AŞAĞI (TİLT -)", "down", False),
        ]
        for isim, metin, satir, kolon, ipucu, yon, merkez in tuslar:
            b = QPushButton(metin)
            b.setStyleSheet(self._key_center_normal_style if merkez else self._key_normal_style)
            b.setToolTip(ipucu)
            b.setCursor(Qt.PointingHandCursor)
            b.pressed.connect(lambda y=yon: self._dpad_press(y))
            b.released.connect(lambda y=yon: self._dpad_release(y))
            gl.addWidget(b, satir, kolon)
            setattr(self, isim, b)
        return dpad

    def _adim_butonlari(self):
        """Adim hassasiyeti secimi (1° / 5° / 10°)."""
        satir = QHBoxLayout()
        satir.setSpacing(6)
        self.step_btns = {}
        for val, etiket in ((1.0, "1° Hassas"), (5.0, "5° Normal"), (10.0, "10° Hızlı")):
            sb = QPushButton(etiket)
            sb.setCheckable(True)
            sb.setChecked(val == self.aci_adim)
            sb.setFixedHeight(30)
            sb.setCursor(Qt.PointingHandCursor)
            sb.clicked.connect(lambda _, v=val: self._aci_adim_sec(v))
            satir.addWidget(sb, 1)
            self.step_btns[val] = sb
            self._step_btn_stil_guncelle(sb, val == self.aci_adim)
        return satir

    # ---- Ic sayfa 1: Aci ve yasak alan ayarlari ----
    def _aci_ayar_sayfasi(self):
        self.aci_ayar_panel = QFrame()
        self.aci_ayar_panel.setObjectName("ayarpanel")
        apv = QVBoxLayout(self.aci_ayar_panel)
        apv.setContentsMargins(14, 10, 14, 10)
        apv.setSpacing(8)

        # Baslik + kapat
        bas = QHBoxLayout()
        baslik = QLabel("Açı & Yasak Alan Ayarları")
        baslik.setObjectName("ayartitle")
        bas.addWidget(baslik, 1)
        kapat = QPushButton("✕")
        kapat.setObjectName("ayarclose")
        kapat.setFixedSize(20, 20)
        kapat.setCursor(Qt.PointingHandCursor)
        kapat.clicked.connect(self._aci_ayarlar_kapat)
        bas.addWidget(kapat, 0)
        apv.addLayout(bas)

        # Maksimum yukselis siniri
        ust = QVBoxLayout()
        ust.setSpacing(3)
        ust_bas = QHBoxLayout()
        ust_lbl = QLabel("Maksimum Yükseliş (Tilt) Sınırı")
        ust_lbl.setObjectName("ayarlbl")
        self.ap_tilt_deg = QLabel(f"{int(self.max_tilt_limit)}°")
        self.ap_tilt_deg.setObjectName("ayardeg")
        self.ap_tilt_deg.setFixedSize(42, 22)
        self.ap_tilt_deg.setAlignment(Qt.AlignCenter)
        ust_bas.addWidget(ust_lbl, 0, Qt.AlignVCenter)
        ust_bas.addStretch(1)
        ust_bas.addWidget(self.ap_tilt_deg, 0, Qt.AlignVCenter)
        ust.addLayout(ust_bas)
        self.ap_tilt_sl = QSlider(Qt.Horizontal)
        self.ap_tilt_sl.setObjectName("ayarsl")
        self.ap_tilt_sl.setMinimum(10)
        self.ap_tilt_sl.setMaximum(90)
        self.ap_tilt_sl.setValue(int(self.max_tilt_limit))
        self.ap_tilt_sl.valueChanged.connect(self._ap_tilt_degisti)
        ust.addWidget(self.ap_tilt_sl)
        apv.addLayout(ust)

        # Uc yasak alan bolumu ayni kaliptan uretilir (onay kutusu + min/max)
        self.ap_pan_cb, self.ap_pmin_spin, self.ap_pmax_spin = self._yasak_alan_bolumu(
            apv, "Pan (Azimut) Harekete Yasak Açı Aralığı",
            self.pan_yasak_aktif, self.pan_yasak_min, self.pan_yasak_max, 360)
        self.ap_tilt_cb, self.ap_tmin_spin, self.ap_tmax_spin = self._yasak_alan_bolumu(
            apv, "Tilt (Yükseliş) Harekete Yasak Açı Aralığı",
            self.tilt_yasak_aktif, self.tilt_yasak_min, self.tilt_yasak_max, 90)
        self.ap_atis_cb, self.ap_amin_spin, self.ap_amax_spin = self._yasak_alan_bolumu(
            apv, "Pan (Azimut) Atışa Yasak Açı Aralığı",
            self.atis_yasak_aktif, self.atis_pan_min, self.atis_pan_max, 360)

        apv.addStretch(1)

        alt = QHBoxLayout()
        self.ap_rst_btn = QPushButton("Varsayılan")
        self.ap_rst_btn.setObjectName("ayaralt")
        self.ap_rst_btn.setCursor(Qt.PointingHandCursor)
        self.ap_rst_btn.clicked.connect(self._ap_varsayilana_don)
        self.ap_ok_btn = QPushButton("Tamam")
        self.ap_ok_btn.setObjectName("ayarkaydet")
        self.ap_ok_btn.setCursor(Qt.PointingHandCursor)
        self.ap_ok_btn.clicked.connect(self._aci_ayarlar_kapat)
        alt.addWidget(self.ap_rst_btn)
        alt.addStretch(1)
        alt.addWidget(self.ap_ok_btn)
        apv.addLayout(alt)
        return self.aci_ayar_panel

    def _yasak_alan_bolumu(self, layout, baslik, acik, alt_deg, ust_deg, maks):
        """Bir yasak alan bolumu: onay kutusu + Min/Max derece kutulari.
        Uc yasak alan (pan hareket, tilt hareket, pan atis) ayni kaliptadir.
        Doner: (onay_kutusu, min_spin, max_spin)"""
        kutu = QVBoxLayout()
        kutu.setSpacing(3)
        cb = QCheckBox(baslik)
        cb.setStyleSheet(f"color:{TXT2}; font-size:11px; font-weight:600;")
        cb.setChecked(acik)
        cb.stateChanged.connect(self._ap_yasak_degisti)
        kutu.addWidget(cb)

        satir = QHBoxLayout()
        satir.setSpacing(6)
        spinler = []
        for etiket, deger in (("Min (°):", alt_deg), ("Max (°):", ust_deg)):
            lbl = QLabel(etiket)
            lbl.setObjectName("engsub")
            spin = QSpinBox()
            spin.setRange(0, maks)
            spin.setValue(int(deger))
            spin.valueChanged.connect(self._ap_yasak_degisti)
            satir.addWidget(lbl, 0, Qt.AlignVCenter)
            satir.addWidget(spin, 1, Qt.AlignVCenter)
            spinler.append(spin)
        kutu.addLayout(satir)
        layout.addLayout(kutu)
        return (cb, *spinler)

    def _dpad_press(self, direction):
        if direction == "up":
            self.btn_up.setStyleSheet(self._key_active_style)
            self._aci_hareket(0.0, self.aci_adim)
        elif direction == "down":
            self.btn_down.setStyleSheet(self._key_active_style)
            self._aci_hareket(0.0, -self.aci_adim)
        elif direction == "left":
            self.btn_left.setStyleSheet(self._key_active_style)
            self._aci_hareket(-self.aci_adim, 0.0)
        elif direction == "right":
            self.btn_right.setStyleSheet(self._key_active_style)
            self._aci_hareket(self.aci_adim, 0.0)
        elif direction in ("home", "center"):
            self.btn_center.setStyleSheet(self._key_center_active_style)
            self._aci_reset()

    def _dpad_release(self, direction):
        if direction == "up":
            self.btn_up.setStyleSheet(self._key_normal_style)
        elif direction == "down":
            self.btn_down.setStyleSheet(self._key_normal_style)
        elif direction == "left":
            self.btn_left.setStyleSheet(self._key_normal_style)
        elif direction == "right":
            self.btn_right.setStyleSheet(self._key_normal_style)
        elif direction in ("home", "center"):
            self.btn_center.setStyleSheet(self._key_center_normal_style)

    # NOT (B1): burada eskiden ikinci bir ates yolu vardi (`_fire_bas`). Iki sorunu vardi:
    #   1. `self.kontrol.ates()` zorunlu `ac` argumani olmadan cagriliyordu -> TypeError
    #      (hicbir yere bagli olmadigi icin patlamamisti; baglandigi an uygulama coker).
    #   2. E-STOP KONTROLU YOKTU -> E-Stop'ta ates edebilirdi (sartname Yetenek 4 ihlali).
    # Cozum: ates icin TEK KAPI var, `_ates_bas`. Yeni bir ates butonu eklenecekse
    # o da `_ates_bas`'a baglanmalidir; guvenlik kontrolleri orada toplanmistir.

    def atis_yasak_mi(self):
        """Su anki pan acisi ATISA YASAK bolgede mi? (sartname: atisa-yasak alan)"""
        return bool(getattr(self, "atis_yasak_aktif", False)
                    and self.atis_pan_min <= self.pan_aci <= self.atis_pan_max)

    def _ap_tilt_degisti(self, val):
        self.max_tilt_limit = float(val)
        self.ap_tilt_deg.setText(f"{val}°")
        if hasattr(self, "tilt_lbl_ref"):
            self.tilt_lbl_ref.setText(f"YÜKSELİŞ (TİLT max {int(val)}°)")

    def _ap_yasak_degisti(self):
        # 1. Harekete Yasak Alan
        self.pan_yasak_aktif = self.ap_pan_cb.isChecked()
        self.pan_yasak_min = float(self.ap_pmin_spin.value())
        self.pan_yasak_max = float(self.ap_pmax_spin.value())
        self.tilt_yasak_aktif = self.ap_tilt_cb.isChecked()
        self.tilt_yasak_min = float(self.ap_tmin_spin.value())
        self.tilt_yasak_max = float(self.ap_tmax_spin.value())

        # 2. Atisa Yasak Alan
        self.atis_yasak_aktif = self.ap_atis_cb.isChecked()
        self.atis_pan_min = float(self.ap_amin_spin.value())
        self.atis_pan_max = float(self.ap_amax_spin.value())

        # Sag alt kartlari guncelle
        self._yasak_kartlari_guncelle()

    def _yasak_kartlari_guncelle(self):
        if not hasattr(self, "hareket_yasak_lbl"):
            return

        # Harekete Yasak Alan Kartı
        if self.pan_yasak_aktif or self.tilt_yasak_aktif:
            txts = []
            if self.pan_yasak_aktif:
                txts.append(f"P:{int(self.pan_yasak_min)}°-{int(self.pan_yasak_max)}°")
            if self.tilt_yasak_aktif:
                txts.append(f"T:{int(self.tilt_yasak_min)}°-{int(self.tilt_yasak_max)}°")
            self.hareket_yasak_lbl.setText(f'<span style="color:{AMB};font-weight:700;">Aktif</span> '
                                           f'<small style="color:{TXT2}">({", ".join(txts)})</small>')
            self.hareket_yasak_sw.setStyleSheet(f"background:{AMB};border-radius:8px;")
        else:
            self.hareket_yasak_lbl.setText(f'<small style="color:{TXT3}">Devre Dışı — Serbest</small>')
            self.hareket_yasak_sw.setStyleSheet(f"background:{BD2};border-radius:8px;")

        # Atışa Yasak Alan Kartı
        if self.atis_yasak_aktif:
            self.atis_yasak_lbl.setText(f'<span style="color:{RED};font-weight:700;">Aktif</span> '
                                        f'<small style="color:{TXT2}">({int(self.atis_pan_min)}°-{int(self.atis_pan_max)}°)</small>')
            self.atis_yasak_sw.setStyleSheet(f"background:{RED};border-radius:8px;")
        else:
            self.atis_yasak_lbl.setText(f'<small style="color:{TXT3}">Devre Dışı — Serbest</small>')
            self.atis_yasak_sw.setStyleSheet(f"background:{BD2};border-radius:8px;")

    def _ap_varsayilana_don(self):
        self.ap_tilt_sl.setValue(60)
        self.ap_pan_cb.setChecked(False)
        self.ap_pmin_spin.setValue(120)
        self.ap_pmax_spin.setValue(160)
        self.ap_tilt_cb.setChecked(False)
        self.ap_tmin_spin.setValue(45)
        self.ap_tmax_spin.setValue(60)
        self.ap_atis_cb.setChecked(False)
        self.ap_amin_spin.setValue(45)
        self.ap_amax_spin.setValue(75)
        self._ap_tilt_degisti(60)
        self._ap_yasak_degisti()

    def _aci_hareket(self, d_pan, d_tilt):
        """Pan/Tilt acisini degistirir, yasak bolgeleri kontrol eder ve ESP32 komutunu gonderir.

        HAREKETIN TEK KAPISI. E-Stop, yasak alan ve tilt limiti burada uygulanir;
        hem manuel (D-pad/WASD) hem otonom (_nisan_geldi) bu kapidan gecer.
        """
        # B2 — E-Stop: hicbir hareket komutu gecmez, aci etiketleri de DEGISMEZ.
        if getattr(self, "thread", None) is not None and getattr(self.thread, "estop", False):
            return False

        yeni_pan = (self.pan_aci + d_pan) % 360.0
        yeni_tilt = max(0.0, min(self.max_tilt_limit, self.tilt_aci + d_tilt))

        # Harekete yasak aci kontrolu
        yasak_mi = False
        if self.pan_yasak_aktif and (self.pan_yasak_min <= yeni_pan <= self.pan_yasak_max):
            yasak_mi = True
        if self.tilt_yasak_aktif and (self.tilt_yasak_min <= yeni_tilt <= self.tilt_yasak_max):
            yasak_mi = True

        if yasak_mi:
            self.bolge_status.setText("▲ HAREKETE YASAK LİMİTİ — ENGELLENDİ")
            self.bolge_status.setStyleSheet(f"color:{RED}; font-size:11px; font-weight:700; padding:2px 0;")
            return False

        self.pan_aci = yeni_pan
        self.tilt_aci = yeni_tilt
        self.pan_val_lbl.setText(f"{self.pan_aci:.1f}°")
        self.tilt_val_lbl.setText(f"{self.tilt_aci:.1f}°")

        # Atisa yasak bolgede miyiz ikazi
        if self.atis_yasak_aktif and (self.atis_pan_min <= self.pan_aci <= self.atis_pan_max):
            self.bolge_status.setText("⚠️ ATIŞA YASAK BÖLGEDESİNİZ — ATEŞ KİLİTLİ")
            self.bolge_status.setStyleSheet(f"color:{AMB}; font-size:11px; font-weight:700; padding:2px 0;")
        else:
            self.bolge_status.setText("● BÖLGE GÜVENLİ")
            self.bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")

        # ESP32 komutu gonder. mod: 0=Manuel 1=Otonom (protokol.py) — eskiden hep 1
        # gonderiliyordu; ESP32 tarafi moda gore davranacagi icin dogru mod sart.
        if hasattr(self, "kontrol") and self.kontrol and self.kontrol.bagli:
            d = self.kontrol.nisan(1 if self.mod == "Otonom" else 0, d_pan, d_tilt)
            self._esp_goster(d)
        return True

    def _nisan_geldi(self, d_yaw, d_pitch):
        """B3 — Otonom nisan dongusunden gelen aci duzeltmesi (AlgiThread.nisan_komut).

        Manuel hareketle AYNI kapidan (_aci_hareket) gecer: E-Stop, yasak alan ve
        tilt limiti otonom modda da aynen uygulanir — guvenlik icin tek yol olmali.
        """
        if self.mod != "Otonom":
            return
        self._aci_hareket(d_yaw, d_pitch)

    def _aci_reset(self):
        self.pan_aci = 0.0
        self.tilt_aci = 0.0
        self.pan_val_lbl.setText("0.0°")
        self.tilt_val_lbl.setText("0.0°")
        self.bolge_status.setText("● MERKEZE ALINDI")
        self.bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
        if hasattr(self, "kontrol") and self.kontrol and self.kontrol.bagli:
            self.kontrol.home()

    def _aci_ayarlar_toggle(self):
        if hasattr(self, "manuel_inner_stack"):
            if self.manuel_inner_stack.currentWidget() == self.aci_ayar_panel:
                self._aci_ayarlar_kapat()
            else:
                self.manuel_inner_stack.setCurrentWidget(self.aci_ayar_panel)
                self.aci_ayar_btn.setText("◄ Kontrollere Dön")

    def _aci_ayarlar_kapat(self):
        if hasattr(self, "manuel_inner_stack"):
            self.manuel_inner_stack.setCurrentIndex(0)
            self.aci_ayar_btn.setText("⚙ Açı Ayarları")

    def _step_btn_stil_guncelle(self, btn, secili):
        if secili:
            btn.setStyleSheet(
                "QPushButton { "
                "  background: #eaf1f8; "
                "  border: 1.5px solid #1e4b7a; "
                "  border-radius: 8px; "
                "  color: #1e4b7a; "
                "  font-size: 12px; "
                "  font-weight: 700; "
                "}"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { "
                "  background: #ffffff; "
                "  border: 1px solid #dfe4ea; "
                "  border-radius: 8px; "
                "  color: #5f6b78; "
                "  font-size: 12px; "
                "} "
                "QPushButton:hover { "
                "  border-color: #c3d3e2; "
                "  color: #2b3540; "
                "}"
            )

    def _aci_adim_sec(self, val):
        self.aci_adim = val
        for v, b in self.step_btns.items():
            b.setChecked(v == val)
            self._step_btn_stil_guncelle(b, v == val)

    def _asama1_panel(self):
        """Asama 1: zarf sirasina gore dizilen 4 hedef karti."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        ipucu = QLabel("Zarftan gelen imha sırasına göre kartları sürükleyip dizin:")
        ipucu.setObjectName("ipucu")
        v.addWidget(ipucu)
        self.kartlar = SiraliKartlar(self.KART_TANIM, os.path.join(HERE, "Grafik"))
        ksar = QHBoxLayout()
        ksar.setContentsMargins(0, 0, 0, 0)
        ksar.addWidget(self.kartlar)
        ksar.addStretch(1)
        v.addLayout(ksar)
        return w

    # ================= ALT PANEL (Sistem durumu + Hedef durumu + Yasak alanlar) =================
    def _alt_panel(self):
        alt = QWidget()
        alt.setFixedHeight(126)
        h = QHBoxLayout(alt)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        # --- sistem durumu (baslik kaldirildi) ---
        sysk = QFrame()
        sysk.setObjectName("panelk")
        sv = QVBoxLayout(sysk)
        sv.setContentsMargins(15, 10, 15, 10)
        sv.setSpacing(4)

        ic = QHBoxLayout()
        ic.setSpacing(12)

        self.stack = QStackedWidget()
        yok = QLabel("Aşama seçiniz")
        yok.setObjectName("bosmsg")
        yok.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(yok)                     # 0: secim yok
        self.stack.addWidget(self._asama1_panel())    # 1: Asama 1 (kartlar)
        self.stack.addWidget(self._tur_panel(4))      # 2: Asama 2 (tur/4)
        self.stack.addWidget(self._tur_panel(8))      # 3: Asama 3 (tur/8)
        ic.addWidget(self.stack, 1)

        # dikey ayirici
        div = QFrame()
        div.setObjectName("vdiv")
        div.setFixedWidth(1)
        ic.addWidget(div)

        self.kural = QLabel()
        self.kural.setObjectName("kural")
        self.kural.setWordWrap(True)
        ic.addWidget(self.kural, 1)

        self.asama_pill = QLabel(self.asama or "—")
        self.asama_pill.setObjectName("asamap")
        ic.addWidget(self.asama_pill, 0, Qt.AlignTop)

        sv.addLayout(ic)
        h.addWidget(sysk, 8)

        # --- hedef durumu ---
        eng_card = QFrame()
        eng_card.setObjectName("panelk")
        ev = QVBoxLayout(eng_card)
        ev.setContentsMargins(15, 10, 15, 10)
        ev.setSpacing(6)
        at = QLabel("HEDEF DURUMU")
        at.setObjectName("ph")
        ev.addWidget(at)

        self.eng = QFrame()
        self.eng.setObjectName("engok")
        eh = QHBoxLayout(self.eng)
        eh.setContentsMargins(11, 7, 11, 7)
        eh.setSpacing(8)
        self.eng_dot = QLabel()
        self.eng_dot.setFixedSize(8, 8)
        self.eng_dot.setStyleSheet(f"background:{GRN};border-radius:4px;")
        ev_sub = QVBoxLayout()
        ev_sub.setSpacing(1)
        self.eng_name = QLabel("Hedef bekleniyor")
        self.eng_name.setObjectName("engname")
        self.eng_sub = QLabel("—")
        self.eng_sub.setObjectName("engsub")
        ev_sub.addWidget(self.eng_name)
        ev_sub.addWidget(self.eng_sub)
        eh.addWidget(self.eng_dot)
        eh.addLayout(ev_sub)
        ev.addWidget(self.eng)
        h.addWidget(eng_card, 2)

        # --- yasak alan kartlari ---
        # 1. Atisa Yasak Alan Kart
        atis_card = QFrame()
        atis_card.setObjectName("panelk")
        atv = QVBoxLayout(atis_card)
        atv.setContentsMargins(15, 10, 15, 10)
        atv.setSpacing(6)
        ph_atis = QLabel("ATIŞA YASAK ALAN")
        ph_atis.setObjectName("ph")
        atv.addWidget(ph_atis)

        tgl_atis = QFrame()
        tgl_atis.setObjectName("angtgl")
        th_atis = QHBoxLayout(tgl_atis)
        th_atis.setContentsMargins(12, 9, 12, 9)
        th_atis.setSpacing(10)
        self.atis_yasak_lbl = QLabel('<small style="color:#8094a8">Devre Dışı — Serbest</small>')
        self.atis_yasak_lbl.setObjectName("tgll")
        self.atis_yasak_sw = QLabel()
        self.atis_yasak_sw.setFixedSize(32, 16)
        self.atis_yasak_sw.setStyleSheet("background:#c3d3e2;border-radius:8px;")
        th_atis.addWidget(self.atis_yasak_lbl, 1)
        th_atis.addWidget(self.atis_yasak_sw)
        atv.addWidget(tgl_atis)
        h.addWidget(atis_card, 2)

        # 2. Harekete Yasak Alan Kart
        hareket_card = QFrame()
        hareket_card.setObjectName("panelk")
        hrv = QVBoxLayout(hareket_card)
        hrv.setContentsMargins(15, 10, 15, 10)
        hrv.setSpacing(6)
        ph_hrk = QLabel("HAREKETE YASAK ALAN")
        ph_hrk.setObjectName("ph")
        hrv.addWidget(ph_hrk)

        tgl_hrk = QFrame()
        tgl_hrk.setObjectName("angtgl")
        th_hrk = QHBoxLayout(tgl_hrk)
        th_hrk.setContentsMargins(12, 9, 12, 9)
        th_hrk.setSpacing(10)
        self.hareket_yasak_lbl = QLabel('<small style="color:#8094a8">Devre Dışı — Serbest</small>')
        self.hareket_yasak_lbl.setObjectName("tgll")
        self.hareket_yasak_sw = QLabel()
        self.hareket_yasak_sw.setFixedSize(32, 16)
        self.hareket_yasak_sw.setStyleSheet("background:#c3d3e2;border-radius:8px;")
        th_hrk.addWidget(self.hareket_yasak_lbl, 1)
        th_hrk.addWidget(self.hareket_yasak_sw)
        hrv.addWidget(tgl_hrk)
        h.addWidget(hareket_card, 2)

        # Ilk durum yansitmasi
        self._yasak_kartlari_guncelle()

        return alt

    # ================= STATUS BAR =================
    def _sbar(self):
        bar = QFrame()
        bar.setObjectName("sbar")
        bar.setFixedHeight(30)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(0)

        # TUM segmentler AYNI kalipla (_sb_seg) kurulur ve aralarina BAGIMSIZ, kisa/
        # ortalanmis bir ayrac (_sb_divider) konur. Onceki surumde ayrac her segmentin
        # KENDI kutusunun border-right'iydi -> kutu metne gore daralip genisledigi icin
        # cizgi hep "yazinin bittigi yerde" duruyordu, kasitli bir ayrac gibi degil. Simdi
        # ayrac, iki segment arasinda esit bosluklu, bagimsiz bir eleman.
        self.ci = {}
        segmentler = []
        for ad, alt in (("Kamera", "· aranıyor"), ("Lazer", "· bağlı değil"),
                        ("ESP32", "· bağlı değil"), ("Seri Port", "· bekleniyor")):
            cont, dot, lbl = self._sb_seg(f'{ad}<small style="color:{TXT3}">&nbsp;{alt}</small>',
                                          dot_renk=BD2)
            segmentler.append(cont)
            self.ci[ad] = (dot, lbl)

        cont, _, self.sb_mod = self._sb_seg(
            f'<span style="color:{BLUE}">Sistem:</span>&nbsp;{self.mod}')
        segmentler.append(cont)
        # Model segmenti: models/ klasorunde agirlik varsa dosya adi, yoksa uyari.
        _mp = _model_bul()
        if _mp:
            _model_txt = f'<span style="color:{BLUE}">{os.path.basename(_mp)}</span>&nbsp;yüklü'
        else:
            _model_txt = f'<span style="color:{RED}">Model yok</span>&nbsp;· models/'
        cont, _, self.sb_model = self._sb_seg(_model_txt)
        segmentler.append(cont)
        cont, _, self.sb_fps = self._sb_seg("FPS —")
        segmentler.append(cont)

        for i, seg in enumerate(segmentler):
            if i > 0:
                h.addWidget(self._sb_divider(), 0, Qt.AlignVCenter)
            h.addWidget(seg, 0, Qt.AlignVCenter)

        h.addWidget(self._sb_divider(), 0, Qt.AlignVCenter)
        cont, _, self.sb_msg = self._sb_seg(
            f'<span style="color:{GRN}">●</span>&nbsp;Başlatılıyor…')
        h.addWidget(cont, 1, Qt.AlignVCenter)

        self.clk = QLabel("--:--:--")
        self.clk.setObjectName("clk")
        h.addWidget(self.clk, 0, Qt.AlignVCenter)
        return bar

    def _sb_divider(self):
        """Alt cubuk ayraci: kisa, dikey ortalanmis, bagimsiz cizgi (metne yapisik degil)."""
        f = QFrame()
        f.setObjectName("sbdiv")
        f.setFixedSize(1, 13)
        return f

    def _sb_seg(self, html, dot_renk=None):
        """Alt cubuk TEK segment kurucusu: (istege bagli) durum noktasi + metin.
        Doner: (kapsayici_widget, nokta_veya_None, metin_label) — hepsi ayni dolgu ile,
        cihaz durumu ve bilgi segmentleri gorsel olarak esitlenir."""
        seg = QWidget()
        hl = QHBoxLayout(seg)
        hl.setContentsMargins(13, 0, 13, 0)
        hl.setSpacing(6)
        dot = None
        if dot_renk is not None:
            dot = QLabel()
            dot.setFixedSize(7, 7)
            dot.setStyleSheet(f"background:{dot_renk};border-radius:3px;")
            hl.addWidget(dot, 0, Qt.AlignVCenter)
        lbl = QLabel(html)
        lbl.setObjectName("sbseg")
        hl.addWidget(lbl, 0, Qt.AlignVCenter)
        return seg, dot, lbl

    # ================= OLAYLAR =================
    # Mod-Asama kilidi: Manuel=yalniz Asama1, Otonom=yalniz Asama2/3 (sartname).
    IZIN = {"Manuel": {"Aşama 1"}, "Otonom": {"Aşama 2", "Aşama 3"}}
    ASAMA_IDX = {None: 0, "Aşama 1": 1, "Aşama 2": 2, "Aşama 3": 3}

    def _mod_sec(self, ad):
        self.mod = ad
        for m, b in self.mod_btns.items():
            b.setChecked(m == ad)
        izin = self.IZIN[ad]
        for a, b in self.asama_btns.items():
            b.setEnabled(a in izin)
        if self.asama not in izin:          # gecersiz asama -> secimi kaldir
            self.asama = None
            for b in self.asama_btns.values():
                b.setChecked(False)
        self.sb_mod.setText(f'<span style="color:{BLUE}">Sistem:</span>&nbsp;{ad}')
        # B3: otonom nisan dongusu yalniz Otonom modda calisir. Mod degisince
        # kontrolcunun turev gecmisi sifirlanir (yeni moda gecince sicrama olmasin).
        if isinstance(getattr(self, "thread", None), AlgiThread):
            self.thread.otonom = (ad == "Otonom")
            self.thread.nisanci.sifirla()
        if hasattr(self, "sag_stack"):
            if self.mod == "Manuel":
                self.sag_stack.setCurrentWidget(self.manuel_panel)
            else:
                self.sag_stack.setCurrentWidget(self.tk)
        self._asama_uygula()

    def keyPressEvent(self, event):
        if getattr(self, "mod", "") == "Manuel" and hasattr(self, "pan_aci"):
            if not event.isAutoRepeat():
                k = event.key()
                if k in (Qt.Key_W, Qt.Key_Up):
                    self._dpad_press("up")
                    return
                elif k in (Qt.Key_S, Qt.Key_Down):
                    self._dpad_press("down")
                    return
                elif k in (Qt.Key_A, Qt.Key_Left):
                    self._dpad_press("left")
                    return
                elif k in (Qt.Key_D, Qt.Key_Right):
                    self._dpad_press("right")
                    return
                elif k in (Qt.Key_R, Qt.Key_C, Qt.Key_Space):
                    self._dpad_press("center")
                    return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if getattr(self, "mod", "") == "Manuel" and hasattr(self, "pan_aci"):
            if not event.isAutoRepeat():
                k = event.key()
                if k in (Qt.Key_W, Qt.Key_Up):
                    self._dpad_release("up")
                    return
                elif k in (Qt.Key_S, Qt.Key_Down):
                    self._dpad_release("down")
                    return
                elif k in (Qt.Key_A, Qt.Key_Left):
                    self._dpad_release("left")
                    return
                elif k in (Qt.Key_D, Qt.Key_Right):
                    self._dpad_release("right")
                    return
                elif k in (Qt.Key_R, Qt.Key_C, Qt.Key_Space):
                    self._dpad_release("center")
                    return
        super().keyReleaseEvent(event)

    def _asama_sec(self, ad):
        if not self.asama_btns[ad].isEnabled():
            return
        self.asama = None if self.asama == ad else ad   # tekrar tikla -> kaldir
        for a, b in self.asama_btns.items():
            b.setChecked(a == self.asama)
        self._asama_uygula()

    def _asama_uygula(self):
        """Secili asamaya gore stack + pill + kural + algi davranisi + tablo gunceller."""
        self.stack.setCurrentIndex(self.ASAMA_IDX[self.asama])
        # Algi thread'ine aktif asamayi bildir (renk yalniz A3'te calisir). Thread heniz
        # olusmamis olabilir (ilk cagri __init__ sirasinda). DIKKAT: hasattr(self,"thread")
        # KULLANMA — QObject'in yerlesik thread() metodu yuzunden hep True doner; isinstance ile.
        if isinstance(getattr(self, "thread", None), AlgiThread):
            self.thread.asama = self.ASAMA_IDX[self.asama]
        # Tespit tablosu basligi: A3'te TARAF (dost/dusman) kolonu var; A1-A2'de yok.
        if hasattr(self, "tablo"):
            if self.asama == "Aşama 3":
                self.tablo.setHorizontalHeaderLabels(["SINIF", "TARAF", "DURUM"])
            else:
                self.tablo.setHorizontalHeaderLabels(["SINIF", "DURUM", ""])
        if self.asama:
            self.asama_pill.setText(self.asama)
            self.asama_pill.setVisible(True)
            self.kural.setVisible(True)
            self._kural_guncelle()
        else:
            self.asama_pill.setVisible(False)
            self.kural.setVisible(False)

    def _kural_guncelle(self):
        kurallar = {
            "Aşama 1": (f'Zarftaki <b style="color:{RED}">SIRAYLA</b> imha &middot; '
                        f'Yanlış sıra: <b style="color:{RED}">−5 puan</b><br>'
                        f'Süre: <i style="color:{BLUE}">5 dk</i> &middot; Baraj: min. 30 puan &middot; Mod: Manuel'),
            "Aşama 2": (f'3 kol &times; <b style="color:{RED}">3 hedef</b> &middot; tur bitmeden imha &middot; '
                        f'sınıflandırma yok<br>'
                        f'<b style="color:{RED}">3 tur üst üste 0 = elenme</b> &middot; Baraj: min. 20 puan'),
            "Aşama 3": (f'8 tur &middot; her tur <b style="color:{RED}">1 Düşman</b> + '
                        f'<i style="color:{BLUE}">2 Dost</i> &middot; tipe göre menzil '
                        f'(F-16: <b style="color:{RED}">10–15 m</b>)<br>'
                        f'Dost vurma −10 &middot; 3 ardışık ıskalama = elenme &middot; Baraj: min. 10 puan'),
        }
        if self.asama in kurallar:
            self.kural.setText(kurallar[self.asama])

    def _estop_bas(self):
        """ACIL DURDUR — sartname Yetenek 3 (hareket kesilir) VE 4 (ates kesilir).

        B2 duzeltmesi: eski kod yalnizca ATES butonunu kilitliyordu; D-pad/WASD ile
        hareket komutu gitmeye devam ediyordu. Mock/gercek ESP32 komutu reddettigi
        icin donanim durur ama ARAYUZDEKI aci etiketleri artmaya devam ederdi ->
        ekrandaki aci ile gercek konum birbirinden kopardi (videoda "E-Stop'ta hareket
        ediyor" gibi gorunur). Artik hareket kapisi da E-Stop'ta kapaniyor.
        """
        aktif = self.estop_btn.isChecked()
        self.thread.estop = aktif
        self.estop_btn.setText("▶ DEVAM ET" if aktif else "⏻ ACİL DURDUR")
        # 1. ATES kapisi (Yetenek 4)
        self.fire_btn.setEnabled(not aktif)
        if aktif and self.fire_btn.isChecked():
            self.fire_btn.setChecked(False)
            self.fire_btn.setText("A T E Ş")
        # 2. HAREKET kapisi (Yetenek 3): manuel yon kontrolleri kilitlenir.
        #    (Otonom nisan dongusu de AlgiThread._nisan_al icinde estop'ta durur.)
        for ad in ("btn_up", "btn_down", "btn_left", "btn_right", "btn_center"):
            b = getattr(self, ad, None)
            if b is not None:
                b.setEnabled(not aktif)
        if hasattr(self, "bolge_status"):
            if aktif:
                self.bolge_status.setText("⏻ ACİL DURDURULDU — hareket ve ateş kesildi")
                self.bolge_status.setStyleSheet(
                    f"color:{RED}; font-size:11px; font-weight:700; padding:2px 0;")
            else:
                self.bolge_status.setText("● BÖLGE GÜVENLİ")
                self.bolge_status.setStyleSheet(
                    f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
        if self.kontrol.bagli:
            d = self.kontrol.estop(aktif)
            self._esp_goster(d)

    def _ates_bas(self):
        """ATESIN TEK KAPISI. Tum guvenlik kontrolleri burada toplanir (B1).
        Yeni bir ates butonu/kisayolu eklenirse mutlaka buraya baglanmalidir."""
        if not self.kontrol.bagli:
            self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;ATEŞ — kontrol katmanı kapalı (DERINMAVI_ESP)')
            self.fire_btn.setChecked(False)
            return
        if self.thread.estop:            # E-Stop'tayken ates verilmez (Yetenek 4)
            self.fire_btn.setChecked(False)
            self.sb_msg.setText(f'<span style="color:{RED}">●</span>&nbsp;ATEŞ reddedildi — E-STOP aktif')
            return
        if self.fire_btn.isChecked() and self.atis_yasak_mi():   # sartname: atisa-yasak alan
            self.fire_btn.setChecked(False)
            self.sb_msg.setText(f'<span style="color:{RED}">●</span>&nbsp;'
                                f'ATEŞ reddedildi — ATIŞA YASAK AÇI BÖLGESİ')
            if hasattr(self, "bolge_status"):
                self.bolge_status.setText("🚫 ATIŞA YASAK AÇI BÖLGESİ — ATEŞ ENGELLENDİ")
                self.bolge_status.setStyleSheet(
                    f"color:{RED}; font-size:11px; font-weight:700; padding:2px 0;")
            return
        ac = self.fire_btn.isChecked()
        d = self.kontrol.ates(ac, mod=1 if self.mod == "Otonom" else 0)
        self.fire_btn.setText("ATEŞİ KES" if ac else "A T E Ş")
        renk = RED if ac else GRN
        kaynak = "mock" if self.kontrol.mock_mu else self.kontrol.kaynak
        self.sb_msg.setText(f'<span style="color:{renk}">●</span>&nbsp;'
                            f'{"LAZER AKTİF" if ac else "Ateş kesildi"} ({kaynak})')
        self._esp_goster(d)

    def _esp_goster(self, d):
        """ESP32 durum paketini alt cubuga yansitir."""
        if not d:
            return
        renk = {"Hazır": GRN, "Hareket": BLUE, "ATEŞ": RED,
                "E-STOP": RED, "HATA": AMB}.get(d["durum_ad"], BD2)
        ek = " · mock" if self.kontrol.mock_mu else ""
        self._ci("ESP32", renk,
                 f'· {d["durum_ad"]} · yaw {d["yaw"]:.1f}° pitch {d["pitch"]:.1f}°{ek}')

    def _kamera_sec(self, i):
        veri = self.kam_sec.itemData(i)
        if veri is None:
            return
        self.thread.kaynak_istegi = veri

    def _kameralar_geldi(self, liste):
        """liste: [{"index": int, "name": str, "is_default": bool}, ...]"""
        mevcut = {self.kam_sec.itemData(i) for i in range(self.kam_sec.count())}
        for cam in sorted(liste, key=lambda c: c["index"]):
            idx = cam["index"]
            if idx not in mevcut:
                # Gercek isim varsa kullan, yoksa generic
                isim = cam.get("name", f"Kamera {idx}")
                self.kam_sec.addItem(f"{isim}", idx)
        # arka plan taramasi bir kez calissin (Qt listesi zaten tum kameralari verir)
        if not getattr(self, "_tarama_basladi", False):
            self._tarama_basladi = True
            self.tarama = TaramaThread()
            self.tarama.bulundu.connect(self._kameralar_geldi)
            self.tarama.start()

    def _model_bilgi_geldi(self, ozet, eksikler):
        """C7 — Modelin GERCEKTEN kac sinif tanidigini alt cubukta goster.

        Arayuz 4 hedef tipi + balon vaat ediyor. Model bunlardan bazilarini
        icermiyorsa (or. su anki best.pt yalnizca fuze+helikopter tanıyor) bu
        gercek gizli kalmamali — yoksa "neden İHA'yı görmüyor?" diye saatler
        yanlis yerde aranir."""
        self._model_ozet = ozet
        dosya = os.path.basename(_model_bul() or "model")
        if eksikler:
            adlar = ", ".join(algi.DISPLAY.get(e, e) for e in eksikler)
            self.sb_model.setText(
                f'<span style="color:{BLUE}">{dosya}</span>&nbsp;'
                f'<small style="color:{AMB}">· {ozet} · eksik: {adlar}</small>')
            self.sb_model.setToolTip(
                f"Model: {ozet}\n\nBu tipler modelde YOK, tespit EDİLEMEZ:\n  {adlar}\n\n"
                "Şartname 4 hedef tipi + nişan için balon gerektiriyor. Eksik tipler "
                "eğitim setine eklenip model yeniden eğitilmeli.")
            self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;'
                                f'Model {ozet} — şu tipler tespit EDİLEMEZ: {adlar}')
        else:
            self.sb_model.setText(f'<span style="color:{BLUE}">{dosya}</span>&nbsp;'
                                  f'<small style="color:{TXT3}">· {ozet}</small>')
            self.sb_model.setToolTip(f"Model: {ozet}\nŞartnamenin gerektirdiği tüm tipler mevcut.")

    def _durum_geldi(self, mesaj, hata):
        renk = AMB if hata else GRN
        self.sb_msg.setText(f'<span style="color:{renk}">●</span>&nbsp;{mesaj}')
        if hata:
            self.video.setText(mesaj)
            self._ci("Kamera", BD2, "· yok")
            self.live_dot.setVisible(False)

    def _ci(self, ad, renk, alt):
        dot, lbl = self.ci[ad]
        dot.setStyleSheet(f"background:{renk};border-radius:3px;")
        base = ad
        lbl.setText(f'{base}<small style="color:{TXT3}">&nbsp;{alt}</small>')

    def _badge_stil(self, badge, tip):
        if tip == "Düşman":
            badge.setStyleSheet(f"background:rgba(191,32,32,0.14);color:{RED};"
                                f"border:1px solid rgba(191,32,32,0.38);border-radius:13px;"
                                f"padding:3px 11px 5px 11px;font-size:10px;font-weight:700;")
        elif tip == "Dost":
            badge.setStyleSheet(f"background:rgba(18,88,168,0.12);color:{BLUE};"
                                f"border:1px solid rgba(18,88,168,0.32);border-radius:13px;"
                                f"padding:3px 11px 5px 11px;font-size:10px;font-weight:700;")
        else:
            badge.setStyleSheet(f"background:rgba(82,112,136,0.12);color:{TXT3};"
                                f"border:1px solid rgba(82,112,136,0.32);border-radius:13px;"
                                f"padding:3px 11px 5px 11px;font-size:10px;font-weight:700;")

    def _saat_guncelle(self):
        self.clk.setText(time.strftime("%H:%M:%S"))



    # ================= KARE GELDI =================
    def _kare_geldi(self, qimg, data):
        # A5 — GORUNTU OLCEKLEME:
        #  * KeepAspectRatio (ByExpanding DEGIL): ByExpanding pixmap'i hedefi TASIRACAK
        #    kadar buyutur, QLabel de tasan kismi KIRPARDI -> kadrajin kenarindaki
        #    tespitleri operator hic goremiyordu. Artik tum kadraj gorunur.
        #  * FastTransformation: tum arayuz zaten bir QGraphicsView proxy'si icinde
        #    ikinci kez olceklendigi icin burada smooth kullanmak hem gereksiz bulaniklik
        #    hem de her karede bosa CPU demekti.
        pix = QPixmap.fromImage(qimg).scaled(
            self.video.width(), self.video.height(),
            Qt.KeepAspectRatio, Qt.FastTransformation)
        self.video.setPixmap(pix)
        # A4: kare cizildi -> algi thread'i yeni kare gonderebilir (kuyruk birikmesin).
        self.thread.kare_islendi()

        # CANLI gostergesi: kare geliyorsa aktif
        if not self.live_dot.isVisible():
            self.live_dot.setVisible(True)
        self._ci("Kamera", GRN, f"· {qimg.width()}×{qimg.height()}")

        # A3'te dost/dusman rozeti/kolonu var; A1-A2'de yok (hepsi hedef).
        a3 = data.get("a3", False)
        self.h_badge.setVisible(a3)

        a = data["active"]
        if a:
            self.h_ad.setText(a["ad"])
            if a3:
                self.h_badge.setText(a["tip"])           # Düşman (A3 aktif hep düşman)
                self._badge_stil(self.h_badge, a["tip"])
            self.h_conf.setText(f"%{a['conf']} güven")
            self.fire_status.setText("Hedef kilitli · Atışa hazır")
            self.fire_status.setStyleSheet(f"color:{GRN};font-size:13px;font-weight:500;")
            self.eng_name.setText("Hedef kilitli")
            self.eng_sub.setText(f"{a['ad']} · %{a['conf']} güven")
        else:
            self.h_ad.setText("—")
            if a3:
                self.h_badge.setText("—")
                self._badge_stil(self.h_badge, None)
            self.h_conf.setText("")
            estop = "DURDUR" in data["mesaj"]
            self.fire_status.setText(data["mesaj"] if estop else "Hedef aranıyor…")
            self.fire_status.setStyleSheet(f"color:{RED if estop else TXT3};font-size:13px;font-weight:500;")
            self.eng_name.setText("Hedef bekleniyor")
            self.eng_sub.setText("—")

        # tablo (A3: SINIF/TARAF/DURUM · A1-A2: SINIF/DURUM/-)
        hedefler = data["hedefler"]
        self.tablo.setRowCount(len(hedefler))
        lock_bg = QColor(191, 32, 32, 18) if a3 else QColor(0, 170, 255, 22)
        for r, hh in enumerate(hedefler):
            tip = hh["tip"]
            kilitli = hh["aktif"]
            ad_it = QTableWidgetItem(hh["ad"])
            ad_it.setForeground(QColor(TXT if kilitli else TXT2))
            dur_it = QTableWidgetItem(hh["durum"])
            dur_it.setForeground(QColor((RED if a3 else GRN) if kilitli else TXT3))
            if kilitli:
                f = dur_it.font(); f.setBold(True); dur_it.setFont(f)
            if a3:
                taraf_it = QTableWidgetItem(tip)
                taraf_it.setForeground(QColor(RED if tip == "Düşman" else (BLUE if tip == "Dost" else TXT3)))
                cells = (ad_it, taraf_it, dur_it)
            else:
                cells = (ad_it, dur_it, QTableWidgetItem(""))
            for c, it in enumerate(cells):
                if kilitli:
                    it.setBackground(lock_bg)
                self.tablo.setItem(r, c, it)
        self.tablo.setRowHeight(0, 36)

        self.sb_msg.setText(f'<span style="color:{GRN}">●</span>&nbsp;{data["mesaj"]}')
        self.sb_fps.setText(f"FPS&nbsp;<span style='color:{BLUE}'>{data['fps']:.1f}</span>")

    def _fit(self):
        """Icerigi pencereye orantili sigdir (en-boy oranini koru)."""
        if hasattr(self, "view"):
            self.view.fitInView(QRectF(0, 0, self.CW, self.CH), Qt.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def showEvent(self, e):
        super().showEvent(e)
        self._fit()

    def closeEvent(self, e):
        self.thread.durdur()
        self.thread.wait(2000)
        if self.kontrol.bagli:
            self.kontrol.estop(True)   # kapanista guvenli duruma al
            self.kontrol.kapat()
        e.accept()

    # ================= STIL (HTML CSS birebir) =================
    def _stil(self):
        self.content.setStyleSheet(f"""
        QWidget {{ background:transparent; color:{TXT};
            font-family:{F}; font-size:13px; }}
        #content {{ background:{BG}; }}
        #top {{ background:{PANEL}; border:1px solid {BD}; border-radius:8px; }}
        #brand {{ font-size:15px; font-weight:700; color:{TXT}; background:transparent; }}
        #brandtxt {{ font-size:15px; font-weight:700; color:{BLUE}; background:transparent; }}
        #vdiv {{ background:{BD}; }}
        #sbdiv {{ background:{BD}; }}
        #tgcap {{ font-size:11px; font-weight:700; letter-spacing:1px; color:{TXT};
            background:transparent; }}
        #tabs {{ background:{BG}; border:1px solid {BD}; border-radius:5px; }}
        #tab {{ padding:4px 13px 6px 13px; font-size:13px; font-weight:600; color:{TXT};
            background:transparent; border:none; border-radius:3px; }}
        #tab:checked {{ background:{BLUE}; color:#ffffff; font-weight:700; }}
        #tab:disabled {{ color:{TXT3}; background:transparent; }}
        #tab:disabled:checked {{ background:rgba(150,170,187,0.45); color:#ffffff; }}
        #camsel {{ background:{BG}; border:1px solid {BD}; border-radius:5px;
            padding:4px 10px; font-size:13px; font-weight:600; color:{TXT}; min-width:130px; }}
        #camsel QAbstractItemView {{ background:{PANEL}; color:{TXT};
            selection-background-color:{BLUE}; selection-color:#fff; border:1px solid {BD}; }}
        #stt {{ font-size:12px; color:{TXT2}; background:transparent; }}
        #estop {{ padding:6px 15px; border-radius:5px; border:2px solid {RED};
            color:{RED}; font-size:13px; font-weight:700; background:transparent; }}
        #estop:hover {{ background:{RED}; color:#ffffff; }}
        #estop:checked {{ background:{RED}; color:#ffffff; }}
        #cam {{ background:#c8d0d8; border:1px solid {BD}; border-radius:8px; }}
        #video {{ background:#c8d0d8; border-radius:8px; color:{TXT3}; font-size:15px; }}
        #livet {{ font-size:11px; font-weight:700; color:{RED}; background:transparent; }}
        /* --- Ayar paneli (kamera uzeri overlay) --- */
        #ayarbtn {{ background:rgba(15,22,32,0.70); color:#fff; border:1px solid rgba(255,255,255,0.22);
            border-radius:10px; font-size:17px; }}
        #ayarbtn:hover {{ background:{BLUE}; border:1px solid {BLUE}; }}
        #ayarpanel {{ background:#ffffff; border:1px solid rgba(15,22,32,0.06); border-radius:16px; }}
        #ayarbaslik {{ font-size:15px; font-weight:800; color:{TXT}; background:transparent; }}
        #ayarkapat {{ background:{CARD}; color:{TXT3}; border:none; border-radius:12px;
            font-size:12px; font-weight:700; }}
        #ayarkapat:hover {{ background:rgba(191,32,32,0.12); color:{RED}; }}
        #ayarlbl {{ font-size:13px; font-weight:600; color:{TXT}; background:transparent; }}
        #ayargrup {{ font-size:10px; font-weight:800; color:{TXT3}; background:transparent;
            letter-spacing:1.1px; padding-top:2px; }}
        #ayarkaydir, #ayaric {{ background:transparent; border:none; }}
        #ayarkaydir QScrollBar:vertical {{ background:transparent; width:7px; margin:0; }}
        #ayarkaydir QScrollBar::handle:vertical {{ background:{BD}; border-radius:3px; min-height:28px; }}
        #ayarkaydir QScrollBar::handle:vertical:hover {{ background:{BD2}; }}
        #ayarkaydir QScrollBar::add-line:vertical, #ayarkaydir QScrollBar::sub-line:vertical {{ height:0; }}
        #ayarkaydir QScrollBar::add-page:vertical, #ayarkaydir QScrollBar::sub-page:vertical {{ background:transparent; }}
        #ayardeg {{ font-size:12px; font-weight:700; color:{BLUE}; background:rgba(18,88,168,0.10);
            border-radius:9px; padding:2px 10px; font-family:{FM}; }}
        #ayarinfo {{ background:rgba(18,88,168,0.13); color:{BLUE}; border:none; border-radius:8px;
            font-size:11px; font-weight:800; font-style:italic; }}
        #ayarinfo:hover {{ background:{BLUE}; color:#fff; }}
        #ayaralt {{ background:transparent; color:{TXT2}; border:1px solid {BD}; border-radius:9px;
            padding:8px 18px; font-size:12px; font-weight:600; min-height:16px; }}
        #ayaralt:hover {{ background:{CARD}; border:1px solid {BD2}; }}
        #ayarkaydet {{ background:{BLUE}; color:#fff; border:none; border-radius:9px;
            padding:8px 22px; font-size:12px; font-weight:700; min-height:16px; }}
        #ayarkaydet:hover {{ background:#0e4a90; }}
        #panelk {{ background:{PANEL}; border:1px solid {BD}; border-radius:8px; }}
        #ph {{ font-size:11px; font-weight:600; letter-spacing:1px; color:{TXT3};
            padding-bottom:7px; border-bottom:1px solid {BD}; background:transparent; }}
        #turn {{ font-size:21px; font-weight:700; color:{TXT}; background:transparent; }}
        #asamap {{ font-size:10px; font-weight:700; letter-spacing:1px;
            padding:3px 10px 5px 10px; border-radius:12px; background:rgba(142,92,8,0.14);
            color:{AMB}; border:1px solid rgba(142,92,8,0.38); }}
        #cit {{ font-size:13px; color:{TXT2}; background:transparent; }}
        #kural {{ padding:9px 12px; background:{CARD}; border:1px solid {BD};
            border-radius:7px; font-size:13px; color:{TXT2}; line-height:1.8; }}
        #bosmsg {{ font-size:14px; color:{TXT3}; background:transparent; padding:28px 0; }}
        #ipucu {{ font-size:12.5px; color:{TXT3}; background:transparent; }}
        #turbilgi {{ font-size:13px; color:{TXT2}; background:transparent; line-height:1.6; }}
        #kart {{ background:{CARD}; border:1px solid {BD}; border-radius:8px; }}
        #kart:hover {{ border:1px solid {BD2}; }}
        #kartno {{ background:{BLUE}; color:#ffffff; border-radius:9px;
            font-size:11px; font-weight:700; }}
        #kartad {{ font-size:12px; font-weight:600; color:{TXT2}; background:transparent; }}
        #hname {{ font-size:28px; font-weight:700; color:{TXT}; background:transparent; }}
        #hconf {{ font-size:14px; color:{TXT3}; background:transparent; }}
        #fire {{ background:rgba(191,32,32,0.08); border:2px solid {RED}; border-radius:5px;
            color:{RED}; font-size:16px; font-weight:700; letter-spacing:6px; }}
        #fire:hover {{ background:{RED}; color:#ffffff; }}
        #fire:checked {{ background:{RED}; color:#ffffff; }}
        #fire:disabled {{ background:transparent; border:2px solid {BD2}; color:{BD2}; }}
        #firest {{ font-size:13px; color:{GRN}; font-weight:500; background:transparent; }}
        QTableWidget {{ background:{PANEL}; border:none; font-size:14px; }}
        QTableWidget::item {{ padding:8px 10px; border-bottom:1px solid rgba(226,231,238,0.9); }}
        QHeaderView::section {{ background:{PANEL}; color:{TXT3}; border:none;
            border-bottom:1px solid {BD}; padding:0 10px 6px; font-size:11px;
            font-weight:600; letter-spacing:1px; }}
        #engok {{ background:rgba(21,135,80,0.12); border:1px solid rgba(21,135,80,0.35);
            border-radius:7px; }}
        #engname {{ font-size:14px; font-weight:700; color:{GRN}; background:transparent; }}
        #engsub {{ font-size:12px; color:{TXT3}; background:transparent; }}
        #angtgl {{ background:{CARD}; border:1px solid {BD}; border-radius:5px; }}
        #tgll {{ font-size:13px; color:{TXT2}; background:transparent; }}
        #sbar {{ background:{PANEL}; border-top:1px solid {BD}; }}
        #sbseg {{ font-size:11px; color:{TXT3}; background:transparent; }}
        #clk {{ font-family:{FM}; font-size:13px; font-weight:600; color:{TXT2};
            background:transparent; margin-left:11px; }}
        """)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    w.showMaximized()   # acilista ekrani tam kapla (yan bosluk kalmasin)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
