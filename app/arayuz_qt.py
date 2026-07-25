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
    QSlider, QDialog, QCheckBox, QSpinBox,
)

import algi
import kontrol as kontrol_mod

HERE = os.path.dirname(os.path.abspath(__file__))
# Model klasoru: repo kokunde "models/". Ekip arkadaslari kendi egittikleri agirligi
# (best.pt / .onnx / herhangi .pt) BURAYA atinca uygulama otomatik bulur — kod degismez.
MODELS_DIR = os.path.abspath(os.path.join(HERE, "..", "models"))


def _model_bul():
    """Kullanilacak model dosyasini DINAMIK bulur. Doner: yol (str) veya None.

    Oncelik:
      1. DERINMAVI_MODEL=<dosya yolu>  -> tam o dosya
      2. DERINMAVI_MODEL=onnx          -> models/best.onnx
      3. (tanimsiz) models/ icinde: best.pt -> best.onnx -> ilk *.pt -> ilk *.onnx
    Hicbiri yoksa None (uygulama modelsiz calisir: kamera + OpenCV akar, tespit yapmaz).
    """
    import glob
    sec = os.environ.get("DERINMAVI_MODEL", "").strip()
    if sec and sec.lower() != "onnx":
        return sec if os.path.isfile(sec) else None
    if sec.lower() == "onnx":
        p = os.path.join(MODELS_DIR, "best.onnx")
        return p if os.path.isfile(p) else None
    for aday in ("best.pt", "best.onnx"):
        p = os.path.join(MODELS_DIR, aday)
        if os.path.isfile(p):
            return p
    for kalip in ("*.pt", "*.onnx"):
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
COZUNURLUK_SECENEK = [416, 512, 640, 960]

# (key, baslik, tip, min, max, oneri, aciklama)
#   tip "yuzde": slider degeri /100 (0.xx) · "kare": tam sayi · "secim": COZUNURLUK_SECENEK indeksi
AYAR_TANIM = [
    ("hassasiyet", "Hassasiyet", "yuzde", 15, 60, 25,
     "Model bir nesneyi 'gördü' saymak için ne kadar emin olmalı.\n\n"
     "↑ ARTTIRIRSAN: sadece net nesneler yakalanır, boşa/yanlış kutu azalır — ama zayıf ya da "
     "uzaktaki nesneleri kaçırabilir.\n"
     "↓ AZALTIRSAN: zayıf/uzak nesneleri de yakalar — ama arka plana yanlış kutu atma riski artar."),
    ("gosterim", "Gösterim eşiği", "yuzde", 20, 60, 35,
     "Yeni bir kutunun ekranda BELİRMESİ için gereken güven. (Bir kez takibe giren nesne, bunun "
     "altına düşse bile gösterilmeye devam eder — titremesin diye.)\n\n"
     "↑ ARTTIRIRSAN: sadece emin olunan nesneler belirir, ekran daha temiz olur.\n"
     "↓ AZALTIRSAN: nesneler daha çabuk belirir — ama yanıp sönen/hayalet kutu görülebilir."),
    ("kararlilik", "Kutu kararlılığı", "kare", 10, 90, 30,
     "Bir nesne bir an görünmez olursa kutusu kaç kare boyunca hafızada tutulsun (hemen kaybolmasın diye).\n\n"
     "↑ ARTTIRIRSAN: kısa kayıplarda kutu kaybolmaz, takip daha kararlı olur — ama gerçekten kadraj "
     "dışına çıkan nesne biraz geç silinir.\n"
     "↓ AZALTIRSAN: giden nesne hızlı silinir — ama kutu daha çok titreyip kopabilir."),
    ("cozunurluk", "Çözünürlük", "secim", 0, len(COZUNURLUK_SECENEK) - 1, 640,
     "Modele verilen görüntü çözünürlüğü — HIZ ile UZAK NESNE görme arasındaki denge.\n\n"
     "↑ BÜYÜTÜRSEN (960): uzak/küçük nesneleri (15 m) daha iyi görür — ama FPS düşer, sistem yavaşlar.\n"
     "↓ KÜÇÜLTÜRSEN (416): daha akıcı ve hızlı olur — ama uzaktaki nesnede zayıflar."),
]


# =====================================================================
#  Algilama is parcacigi
# =====================================================================
class AlgiThread(QThread):
    kare_hazir = Signal(QImage, dict)
    durum = Signal(str, bool)               # mesaj, hata_mi
    kameralar_bulundu = Signal(list)        # [{"index": int, "name": str, "is_default": bool}, ...]

    def __init__(self):
        super().__init__()
        self._calis = True
        self.estop = False
        self.model_yok = False              # models/ klasorunde model bulunamadi mi
        self.asama = 3                      # 1/2/3/0 — SARTNAME davranisi (renk yalniz A3)
        self.kaynak_istegi = None           # None | "auto" | int

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
                self.durum.emit("Sistem hazır", False)
            except Exception as e:
                self.durum.emit(f"Model yüklenemedi: {e}", True)  # ham goruntu akmaya devam

        t_son, fps = time.time(), 0.0
        hata = 0
        while self._calis:
            # kamera degisim istegi (arayuzden secim)
            if self.kaynak_istegi is not None:
                istek = self.kaynak_istegi
                self.kaynak_istegi = None
                algi.takip_sifirla()   # kamera degisiyor: eski takip kutulari kalmasin
                if cap is not None:
                    cap.release()
                self.durum.emit("Kamera değiştiriliyor…", False)
                cap = algi.open_camera() if istek == "auto" else algi.ac_kaynak(istek)
                if cap is None:
                    self.durum.emit("Seçilen kamera açılamadı — otomatik aranıyor…", True)
                    cap = algi.open_camera()
                    if cap is None:
                        self.durum.emit("Hiçbir kamera açılamadı", True)
                        self.msleep(1000)
                        continue
                self.durum.emit("Sistem hazır" if model else "Model yükleniyor… (kamera aktif)", False)

            ok, frame = cap.read()
            if ok and frame is not None:
                frame = cv2.flip(frame, 1)   # yatay aynalama: goruntu ters dusmesin
            if not ok or frame is None:
                hata += 1
                if hata > 30:
                    cap.release()
                    cap = algi.open_camera()
                    hata = 0
                    if cap is None:
                        self.durum.emit("Kamera koptu — yeniden deneniyor…", True)
                        self.msleep(500)
                        continue
                self.msleep(20)
                continue
            hata = 0

            # Model hazirsa: algilama yap. Degilse: ham goruntu gonder
            if model is not None:
                dets, balonlar, active_idx = algi.analiz_et(model, frame, self.estop, self.asama)
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
            self.kare_hazir.emit(qimg, data)

        if cap is not None:
            cap.release()

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
        self.mod = "Otonom"
        self.asama = "Aşama 3"
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
        self.thread.kare_hazir.connect(self._kare_geldi)
        self.thread.durum.connect(self._durum_geldi)
        self.thread.kameralar_bulundu.connect(self._kameralar_geldi)
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

    def _asama1_panel(self):
        """Asama 1: zarf sirasina gore dizilen 4 hedef karti."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(8)
        ipucu = QLabel("Zarftan gelen imha sırasına göre kartları sürükleyip dizin:")
        ipucu.setObjectName("ipucu")
        v.addWidget(ipucu)
        self.kartlar = SiraliKartlar(self.KART_TANIM, os.path.join(HERE, "Grafik"))
        ksar = QHBoxLayout()
        ksar.addStretch(1)
        ksar.addWidget(self.kartlar)
        ksar.addStretch(1)
        v.addLayout(ksar)
        return w

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

        for tanim in AYAR_TANIM:
            self._ayar_satiri(pv, tanim)

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
        if tip == "secim":
            sl.setMinimum(0)
            sl.setMaximum(len(COZUNURLUK_SECENEK) - 1)
            sl.setValue(COZUNURLUK_SECENEK.index(int(algi.AYAR[key])))
            sl.oneri_val = COZUNURLUK_SECENEK.index(oneri)
        else:
            sl.setMinimum(mn)
            sl.setMaximum(mx)
            sl.setValue(int(round(algi.AYAR[key] * 100)) if tip == "yuzde" else int(algi.AYAR[key]))
            sl.oneri_val = oneri
        sl.setObjectName("ayarsl")
        sl.valueChanged.connect(lambda val, k=key, t=tip, d=deger, s=sl: self._ayar_degisti(k, t, val, d, s))
        kutu.addWidget(sl)

        layout.addLayout(kutu)
        self.ayar_sliderlar[key] = (sl, tip)
        self._ayar_degisti(key, tip, sl.value(), deger, sl)

    def _ayar_deger_yaz(self, tip, val, lbl):
        if tip == "yuzde":
            lbl.setText(f"{val / 100:.2f}")
        elif tip == "secim":
            lbl.setText(f"{COZUNURLUK_SECENEK[val]} px")
        else:
            lbl.setText(f"{val} kare")

    def _ayar_degisti(self, key, tip, val, deger_lbl, slider):
        if tip == "yuzde":
            algi.ayar_guncelle(**{key: val / 100.0})
        elif tip == "secim":
            algi.ayar_guncelle(**{key: COZUNURLUK_SECENEK[val]})
        else:
            algi.ayar_guncelle(**{key: int(val)})
        self._ayar_deger_yaz(tip, val, deger_lbl)
        self._slider_stil_guncelle(slider, val, deger_lbl)

    def _slider_stil_guncelle(self, sl, val, deger_lbl=None):
        is_default = (val == getattr(sl, "oneri_val", None))
        if is_default:
            sl.setStyleSheet(f"""
                QSlider#ayarsl {{ height: 22px; }}
                QSlider#ayarsl::groove:horizontal {{ height: 5px; border-radius: 2px; background: #dbe3ec; margin: 0 2px; }}
                QSlider#ayarsl::sub-page:horizontal {{ height: 5px; border-radius: 2px; background: {BLUE}; margin: 0 2px; }}
                QSlider#ayarsl::add-page:horizontal {{ height: 5px; border-radius: 2px; background: #dbe3ec; margin: 0 2px; }}
                QSlider#ayarsl::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                    background: {GRN}; border: 2px solid {GRN}; }}
                QSlider#ayarsl::handle:horizontal:hover {{ background: #189a5c; border: 2px solid #189a5c; }}
                QSlider#ayarsl::handle:horizontal:pressed {{ background: #0f6c3f; border: 2px solid #0f6c3f; }}
            """)
            if deger_lbl:
                deger_lbl.setStyleSheet(f"color:{GRN}; background:rgba(21,135,80,0.14); border-radius:9px; padding:2px 10px; font-family:{FM}; border: 1px solid rgba(21,135,80,0.35); font-size:12px; font-weight:700;")
        else:
            sl.setStyleSheet(f"""
                QSlider#ayarsl {{ height: 22px; }}
                QSlider#ayarsl::groove:horizontal {{ height: 5px; border-radius: 2px; background: #dbe3ec; margin: 0 2px; }}
                QSlider#ayarsl::sub-page:horizontal {{ height: 5px; border-radius: 2px; background: {BLUE}; margin: 0 2px; }}
                QSlider#ayarsl::add-page:horizontal {{ height: 5px; border-radius: 2px; background: #dbe3ec; margin: 0 2px; }}
                QSlider#ayarsl::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                    background: #ffffff; border: 2px solid {BLUE}; }}
                QSlider#ayarsl::handle:horizontal:hover {{ border: 2px solid #0e4a90; background: #f3f8ff; }}
                QSlider#ayarsl::handle:horizontal:pressed {{ background: #dbe9fb; }}
            """)
            if deger_lbl:
                deger_lbl.setStyleSheet(f"color:{BLUE}; background:rgba(18,88,168,0.10); border-radius:9px; padding:2px 10px; font-family:{FM}; border: 1px solid rgba(18,88,168,0.18); font-size:12px; font-weight:700;")

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
            v = algi.VARSAYILAN_AYAR[key]
            if tip == "yuzde":
                sl.setValue(int(round(v * 100)))
            elif tip == "secim":
                sl.setValue(COZUNURLUK_SECENEK.index(int(v)))
            else:
                sl.setValue(int(v))

    def _ayar_dosya(self):
        return os.path.join(HERE, "ayarlar.json")

    def _ayar_yukle(self):
        import json
        p = os.path.join(HERE, "ayarlar.json")
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
        mk = QFrame()
        mk.setObjectName("panelk")
        mv = QVBoxLayout(mk)
        mv.setContentsMargins(16, 12, 16, 12)
        mv.setSpacing(8)

        # 1. Baslik + Aci Ayarlari butonu
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

        # Aci takip degiskenleri
        self.pan_aci = 0.0          # Azimut (0 - 360)
        self.tilt_aci = 0.0         # Yukselis (0 - max_tilt_limit)
        self.max_tilt_limit = 60.0  # Yukselis max siniri

        # 1. Harekete Yasak Alan Sinirlari
        self.pan_yasak_aktif = False
        self.pan_yasak_min = 120.0
        self.pan_yasak_max = 160.0
        self.tilt_yasak_aktif = False
        self.tilt_yasak_min = 45.0
        self.tilt_yasak_max = 60.0

        # 2. Atisa Yasak Alan Sinirlari
        self.atis_yasak_aktif = False
        self.atis_pan_min = 45.0
        self.atis_pan_max = 75.0

        self.aci_adim = 5.0          # Adim hassasiyeti (derece)

        # Ic Stack (0: D-Pad Kontrolleri, 1: Aci Ayarlari Paneli)
        self.manuel_inner_stack = QStackedWidget()

        # PAGE 0: D-PAD VE MANUEL KONTROLLER
        dpad_view = QWidget()
        dv = QVBoxLayout(dpad_view)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(8)

        # Dijital Aci Gostergesi
        gost_box = QFrame()
        gost_box.setObjectName("angtgl")
        gh = QHBoxLayout(gost_box)
        gh.setContentsMargins(12, 6, 12, 6)
        gh.setSpacing(12)

        # Pan
        pv = QVBoxLayout()
        pv.setSpacing(1)
        plbl = QLabel("AZİMUT (PAN)")
        plbl.setObjectName("engsub")
        self.pan_val_lbl = QLabel("0.0°")
        self.pan_val_lbl.setObjectName("turn")
        self.pan_val_lbl.setStyleSheet(f"font-size:18px; color:{TXT}; font-weight:700;")
        pv.addWidget(plbl)
        pv.addWidget(self.pan_val_lbl)
        gh.addLayout(pv, 1)

        # Div
        d1 = QFrame()
        d1.setObjectName("vdiv")
        d1.setFixedWidth(1)
        gh.addWidget(d1)

        # Tilt
        tv_box = QVBoxLayout()
        tv_box.setSpacing(1)
        self.tilt_lbl_ref = QLabel(f"YÜKSELİŞ (TİLT max {int(self.max_tilt_limit)}°)")
        self.tilt_lbl_ref.setObjectName("engsub")
        self.tilt_val_lbl = QLabel("0.0°")
        self.tilt_val_lbl.setObjectName("turn")
        self.tilt_val_lbl.setStyleSheet(f"font-size:18px; color:{BLUE}; font-weight:700;")
        tv_box.addWidget(self.tilt_lbl_ref)
        tv_box.addWidget(self.tilt_val_lbl)
        gh.addLayout(tv_box, 1)
        dv.addWidget(gost_box)

        # Bolge Durumu
        self.bolge_status = QLabel("● BÖLGE GÜVENLİ")
        self.bolge_status.setObjectName("firest")
        self.bolge_status.setAlignment(Qt.AlignCenter)
        self.bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
        dv.addWidget(self.bolge_status)

        # Yon Tus Takimi (D-Pad Grid)
        dpad = QWidget()
        gl = QGridLayout(dpad)
        gl.setContentsMargins(0, 2, 0, 2)
        gl.setSpacing(6)

        self._key_normal_style = (
            "QPushButton { "
            "  background: #f7f9fb; "
            "  border: 1px solid #dfe4ea; "
            "  border-radius: 8px; "
            "  color: #2b3540; "
            "  font-size: 13px; "
            "  font-weight: 700; "
            "  min-width: 68px; max-width: 68px; "
            "  min-height: 54px; max-height: 54px; "
            "} "
            "QPushButton:hover { "
            "  background: #eef3f8; "
            "  border-color: #c3d3e2; "
            "}"
        )

        self._key_active_style = (
            "QPushButton { "
            "  background: #dbe6f1; "
            "  border: 1.5px solid #1e4b7a; "
            "  border-radius: 8px; "
            "  color: #1e4b7a; "
            "  font-size: 13px; "
            "  font-weight: 700; "
            "  min-width: 68px; max-width: 68px; "
            "  min-height: 54px; max-height: 54px; "
            "}"
        )

        self._key_center_normal_style = (
            "QPushButton { "
            "  background: #1e4b7a; "
            "  border: 1px solid #1e4b7a; "
            "  border-radius: 8px; "
            "  color: #ffffff; "
            "  font-size: 11px; "
            "  font-weight: 700; "
            "  min-width: 68px; max-width: 68px; "
            "  min-height: 54px; max-height: 54px; "
            "} "
            "QPushButton:hover { "
            "  background: #265a8f; "
            "  border-color: #265a8f; "
            "}"
        )

        self._key_center_active_style = (
            "QPushButton { "
            "  background: #17395d; "
            "  border: 1.5px solid #17395d; "
            "  border-radius: 8px; "
            "  color: #ffffff; "
            "  font-size: 11px; "
            "  font-weight: 700; "
            "  min-width: 68px; max-width: 68px; "
            "  min-height: 54px; max-height: 54px; "
            "}"
        )

        self.btn_up = QPushButton("▲\nW")
        self.btn_up.setStyleSheet(self._key_normal_style)
        self.btn_up.setToolTip("[W] veya [▲] — YUKARI (TİLT +)")
        self.btn_up.setCursor(Qt.PointingHandCursor)
        self.btn_up.pressed.connect(lambda: self._dpad_press("up"))
        self.btn_up.released.connect(lambda: self._dpad_release("up"))
        gl.addWidget(self.btn_up, 0, 1)

        self.btn_left = QPushButton("◀\nA")
        self.btn_left.setStyleSheet(self._key_normal_style)
        self.btn_left.setToolTip("[A] veya [◄] — SOL (PAN -)")
        self.btn_left.setCursor(Qt.PointingHandCursor)
        self.btn_left.pressed.connect(lambda: self._dpad_press("left"))
        self.btn_left.released.connect(lambda: self._dpad_release("left"))
        gl.addWidget(self.btn_left, 1, 0)

        self.btn_center = QPushButton("✛\nMERKEZ")
        self.btn_center.setStyleSheet(self._key_center_normal_style)
        self.btn_center.setToolTip("[R] veya [Space] — SIFIRLA / MERKEZ (0°, 0°)")
        self.btn_center.setCursor(Qt.PointingHandCursor)
        self.btn_center.pressed.connect(lambda: self._dpad_press("home"))
        self.btn_center.released.connect(lambda: self._dpad_release("home"))
        gl.addWidget(self.btn_center, 1, 1)

        self.btn_right = QPushButton("►\nD")
        self.btn_right.setStyleSheet(self._key_normal_style)
        self.btn_right.setToolTip("[D] veya [►] — SAĞ (PAN +)")
        self.btn_right.setCursor(Qt.PointingHandCursor)
        self.btn_right.pressed.connect(lambda: self._dpad_press("right"))
        self.btn_right.released.connect(lambda: self._dpad_release("right"))
        gl.addWidget(self.btn_right, 1, 2)

        self.btn_down = QPushButton("▼\nS")
        self.btn_down.setStyleSheet(self._key_normal_style)
        self.btn_down.setToolTip("[S] veya [▼] — AŞAĞI (TİLT -)")
        self.btn_down.setCursor(Qt.PointingHandCursor)
        self.btn_down.pressed.connect(lambda: self._dpad_press("down"))
        self.btn_down.released.connect(lambda: self._dpad_release("down"))
        gl.addWidget(self.btn_down, 2, 1)

        dv.addWidget(dpad, 0, Qt.AlignCenter)

        # Adim Hassasiyet Butonlari
        step_row = QHBoxLayout()
        step_row.setSpacing(6)

        self.step_btns = {}
        for val, label in [(1.0, "1° Hassas"), (5.0, "5° Normal"), (10.0, "10° Hızlı")]:
            sb = QPushButton(label)
            sb.setCheckable(True)
            sb.setChecked(val == self.aci_adim)
            sb.setFixedHeight(30)
            sb.setCursor(Qt.PointingHandCursor)
            sb.clicked.connect(lambda _, v=val: self._aci_adim_sec(v))
            step_row.addWidget(sb, 1)
            self.step_btns[val] = sb
            self._step_btn_stil_guncelle(sb, val == self.aci_adim)

        dv.addLayout(step_row)
        self.manuel_inner_stack.addWidget(dpad_view)

        # PAGE 1: AÇI VE YASAK ALAN AYARLARI PANENELİ
        self.aci_ayar_panel = QFrame()
        self.aci_ayar_panel.setObjectName("ayarpanel")
        apv = QVBoxLayout(self.aci_ayar_panel)
        apv.setContentsMargins(14, 10, 14, 10)
        apv.setSpacing(8)

        # Baslik satiri
        ap_head = QHBoxLayout()
        ap_title = QLabel("Açı & Yasak Alan Ayarları")
        ap_title.setObjectName("ayartitle")
        ap_head.addWidget(ap_title, 1)

        ap_close = QPushButton("✕")
        ap_close.setObjectName("ayarclose")
        ap_close.setFixedSize(20, 20)
        ap_close.setCursor(Qt.PointingHandCursor)
        ap_close.clicked.connect(self._aci_ayarlar_kapat)
        ap_head.addWidget(ap_close, 0)
        apv.addLayout(ap_head)

        # 1. Max Tilt Limit
        s1_box = QVBoxLayout()
        s1_box.setSpacing(3)
        s1_head = QHBoxLayout()
        s1_lbl = QLabel("Maksimum Yükseliş (Tilt) Sınırı")
        s1_lbl.setObjectName("ayarlbl")
        self.ap_tilt_deg = QLabel(f"{int(self.max_tilt_limit)}°")
        self.ap_tilt_deg.setObjectName("ayardeg")
        self.ap_tilt_deg.setFixedSize(42, 22)
        self.ap_tilt_deg.setAlignment(Qt.AlignCenter)
        s1_head.addWidget(s1_lbl, 0, Qt.AlignVCenter)
        s1_head.addStretch(1)
        s1_head.addWidget(self.ap_tilt_deg, 0, Qt.AlignVCenter)
        s1_box.addLayout(s1_head)

        self.ap_tilt_sl = QSlider(Qt.Horizontal)
        self.ap_tilt_sl.setObjectName("ayarsl")
        self.ap_tilt_sl.setMinimum(10)
        self.ap_tilt_sl.setMaximum(90)
        self.ap_tilt_sl.setValue(int(self.max_tilt_limit))
        self.ap_tilt_sl.valueChanged.connect(self._ap_tilt_degisti)
        s1_box.addWidget(self.ap_tilt_sl)
        apv.addLayout(s1_box)

        # 2. Pan Harekete Yasak Aci Araligi
        s2_box = QVBoxLayout()
        s2_box.setSpacing(3)
        self.ap_pan_cb = QCheckBox("Pan (Azimut) Harekete Yasak Açı Aralığı")
        self.ap_pan_cb.setStyleSheet(f"color:{TXT2}; font-size:11px; font-weight:600;")
        self.ap_pan_cb.setChecked(self.pan_yasak_aktif)
        self.ap_pan_cb.stateChanged.connect(self._ap_yasak_degisti)
        s2_box.addWidget(self.ap_pan_cb)

        py_row = QHBoxLayout()
        py_row.setSpacing(6)
        l_pmin = QLabel("Min (°):")
        l_pmin.setObjectName("engsub")
        self.ap_pmin_spin = QSpinBox()
        self.ap_pmin_spin.setRange(0, 360)
        self.ap_pmin_spin.setValue(int(self.pan_yasak_min))
        self.ap_pmin_spin.valueChanged.connect(self._ap_yasak_degisti)
        l_pmax = QLabel("Max (°):")
        l_pmax.setObjectName("engsub")
        self.ap_pmax_spin = QSpinBox()
        self.ap_pmax_spin.setRange(0, 360)
        self.ap_pmax_spin.setValue(int(self.pan_yasak_max))
        self.ap_pmax_spin.valueChanged.connect(self._ap_yasak_degisti)
        py_row.addWidget(l_pmin, 0, Qt.AlignVCenter)
        py_row.addWidget(self.ap_pmin_spin, 1, Qt.AlignVCenter)
        py_row.addWidget(l_pmax, 0, Qt.AlignVCenter)
        py_row.addWidget(self.ap_pmax_spin, 1, Qt.AlignVCenter)
        s2_box.addLayout(py_row)
        apv.addLayout(s2_box)

        # 3. Tilt Harekete Yasak Aci Araligi
        s3_box = QVBoxLayout()
        s3_box.setSpacing(3)
        self.ap_tilt_cb = QCheckBox("Tilt (Yükseliş) Harekete Yasak Açı Aralığı")
        self.ap_tilt_cb.setStyleSheet(f"color:{TXT2}; font-size:11px; font-weight:600;")
        self.ap_tilt_cb.setChecked(self.tilt_yasak_aktif)
        self.ap_tilt_cb.stateChanged.connect(self._ap_yasak_degisti)
        s3_box.addWidget(self.ap_tilt_cb)

        ty_row = QHBoxLayout()
        ty_row.setSpacing(6)
        l_tmin = QLabel("Min (°):")
        l_tmin.setObjectName("engsub")
        self.ap_tmin_spin = QSpinBox()
        self.ap_tmin_spin.setRange(0, 90)
        self.ap_tmin_spin.setValue(int(self.tilt_yasak_min))
        self.ap_tmin_spin.valueChanged.connect(self._ap_yasak_degisti)
        l_tmax = QLabel("Max (°):")
        l_tmax.setObjectName("engsub")
        self.ap_tmax_spin = QSpinBox()
        self.ap_tmax_spin.setRange(0, 90)
        self.ap_tmax_spin.setValue(int(self.tilt_yasak_max))
        self.ap_tmax_spin.valueChanged.connect(self._ap_yasak_degisti)
        ty_row.addWidget(l_tmin, 0, Qt.AlignVCenter)
        ty_row.addWidget(self.ap_tmin_spin, 1, Qt.AlignVCenter)
        ty_row.addWidget(l_tmax, 0, Qt.AlignVCenter)
        ty_row.addWidget(self.ap_tmax_spin, 1, Qt.AlignVCenter)
        s3_box.addLayout(ty_row)
        apv.addLayout(s3_box)

        # 4. Pan Atisa Yasak Aci Araligi
        s4_box = QVBoxLayout()
        s4_box.setSpacing(3)
        self.ap_atis_cb = QCheckBox("Pan (Azimut) Atışa Yasak Açı Aralığı")
        self.ap_atis_cb.setStyleSheet(f"color:{TXT2}; font-size:11px; font-weight:600;")
        self.ap_atis_cb.setChecked(self.atis_yasak_aktif)
        self.ap_atis_cb.stateChanged.connect(self._ap_yasak_degisti)
        s4_box.addWidget(self.ap_atis_cb)

        ay_row = QHBoxLayout()
        ay_row.setSpacing(6)
        l_amin = QLabel("Min (°):")
        l_amin.setObjectName("engsub")
        self.ap_amin_spin = QSpinBox()
        self.ap_amin_spin.setRange(0, 360)
        self.ap_amin_spin.setValue(int(self.atis_pan_min))
        self.ap_amin_spin.valueChanged.connect(self._ap_yasak_degisti)
        l_amax = QLabel("Max (°):")
        l_amax.setObjectName("engsub")
        self.ap_amax_spin = QSpinBox()
        self.ap_amax_spin.setRange(0, 360)
        self.ap_amax_spin.setValue(int(self.atis_pan_max))
        self.ap_amax_spin.valueChanged.connect(self._ap_yasak_degisti)
        ay_row.addWidget(l_amin, 0, Qt.AlignVCenter)
        ay_row.addWidget(self.ap_amin_spin, 1, Qt.AlignVCenter)
        ay_row.addWidget(l_amax, 0, Qt.AlignVCenter)
        ay_row.addWidget(self.ap_amax_spin, 1, Qt.AlignVCenter)
        s4_box.addLayout(ay_row)
        apv.addLayout(s4_box)

        apv.addStretch(1)

        # Alt aksiyon butonlari
        ap_alt = QHBoxLayout()
        self.ap_rst_btn = QPushButton("Varsayılan")
        self.ap_rst_btn.setObjectName("ayaralt")
        self.ap_rst_btn.setCursor(Qt.PointingHandCursor)
        self.ap_rst_btn.clicked.connect(self._ap_varsayilana_don)

        self.ap_ok_btn = QPushButton("Tamam")
        self.ap_ok_btn.setObjectName("ayarkaydet")
        self.ap_ok_btn.setCursor(Qt.PointingHandCursor)
        self.ap_ok_btn.clicked.connect(self._aci_ayarlar_kapat)

        ap_alt.addWidget(self.ap_rst_btn)
        ap_alt.addStretch(1)
        ap_alt.addWidget(self.ap_ok_btn)
        apv.addLayout(ap_alt)

        self.manuel_inner_stack.addWidget(self.aci_ayar_panel)

        mv.addWidget(self.manuel_inner_stack, 1)
        return mk

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

    def _fire_bas(self):
        if self.atis_yasak_aktif and (self.atis_pan_min <= self.pan_aci <= self.atis_pan_max):
            self.bolge_status.setText("🚫 ATIŞA YASAK AÇI BÖLGESİ — ATEŞ ENGELLENDİ")
            self.bolge_status.setStyleSheet(f"color:{RED}; font-size:11px; font-weight:700; padding:2px 0;")
            return

        self.bolge_status.setText("🔥 ATEŞ EDİLDİ — LAZER/SİSTEM AKTİF")
        self.bolge_status.setStyleSheet("color:#b8342a; font-size:11px; font-weight:700; padding:2px 0;")
        if hasattr(self, "kontrol") and self.kontrol and self.kontrol.bagli:
            self.kontrol.ates()

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
        """Pan/Tilt acisini degistirir, yasak bolgeleri kontrol eder ve ESP32 komutunu gonderir."""
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
            return

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

        # ESP32 komutu gonder
        if hasattr(self, "kontrol") and self.kontrol and self.kontrol.bagli:
            self.kontrol.nisan(1, d_pan, d_tilt)

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
        aktif = self.estop_btn.isChecked()
        self.thread.estop = aktif
        self.estop_btn.setText("▶ DEVAM ET" if aktif else "⏻ ACİL DURDUR")
        # E-Stop aktifken ATES butonu tamamen kilitlenir (Yetenek 3-4'un temeli)
        self.fire_btn.setEnabled(not aktif)
        if aktif and self.fire_btn.isChecked():
            self.fire_btn.setChecked(False)
            self.fire_btn.setText("A T E Ş")
        if self.kontrol.bagli:
            d = self.kontrol.estop(aktif)
            self._esp_goster(d)

    def _ates_bas(self):
        if not self.kontrol.bagli:
            self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;ATEŞ — kontrol katmanı kapalı (DERINMAVI_ESP)')
            self.fire_btn.setChecked(False)
            return
        if self.thread.estop:            # E-Stop'tayken ates verilmez
            self.fire_btn.setChecked(False)
            self.sb_msg.setText(f'<span style="color:{RED}">●</span>&nbsp;ATEŞ reddedildi — E-STOP aktif')
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
        pix = QPixmap.fromImage(qimg).scaled(
            self.video.width(), self.video.height(),
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.video.setPixmap(pix)

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
