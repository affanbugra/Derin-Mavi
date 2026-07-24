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

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF
from PySide6.QtGui import QImage, QPixmap, QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy, QButtonGroup,
    QGraphicsView, QGraphicsScene, QStackedWidget,
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
                dets, balonlar, active_idx = algi.analiz_et(model, frame, self.estop)
                frame = algi.draw_overlay(frame, dets, active_idx, balonlar, self.estop)
                data = self._panel_verisi(dets, active_idx, fps)
            else:
                mesaj = ("Model yok — models/ klasörüne best.pt ekleyin"
                         if self.model_yok else "Model yükleniyor…")
                data = {"active": None, "hedefler": [], "mesaj": mesaj, "fps": fps}

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
        # NOT: mesafe/menzil alanlari GECICI OLARAK YOK (bkz. algi.py "MESAFE OZELLIGI
        # DEVRE DISI" notu) — gercek olcum eklenene kadar tip/renk/guven ile karar verilir.
        hedefler = []
        for i, d in enumerate(dets):
            enemy = d["tip"] == "Düşman"
            aktif = (i == active_idx)
            durum = "◉ Kilitli" if (enemy and aktif and not self.estop) else "Pas geç"
            hedefler.append({"ad": d["ad"], "tip": d["tip"],
                             "durum": durum, "enemy": enemy, "aktif": aktif})
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
        return {"active": active, "hedefler": hedefler, "mesaj": mesaj, "fps": fps}

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
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(3)
        self.rozet = QLabel("1")
        self.rozet.setObjectName("kartno")
        self.rozet.setFixedSize(19, 19)
        self.rozet.setAlignment(Qt.AlignCenter)
        v.addWidget(self.rozet, 0, Qt.AlignLeft)
        img = QLabel()
        img.setAlignment(Qt.AlignCenter)
        if not pixmap.isNull():
            img.setPixmap(pixmap.scaled(ust.KART_W - 26, 74,
                          Qt.KeepAspectRatio, Qt.SmoothTransformation))
        v.addWidget(img, 1)
        adl = QLabel(ad)
        adl.setObjectName("kartad")
        adl.setAlignment(Qt.AlignCenter)
        adl.setWordWrap(True)
        v.addWidget(adl)
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
    KART_W, KART_H, GAP = 158, 150, 10

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
        mh = QHBoxLayout(main)
        mh.setContentsMargins(12, 12, 12, 12)
        mh.setSpacing(12)
        kok.addWidget(main, 1)

        mh.addWidget(self._sol_kolon())
        mh.addWidget(self._sag_kolon(), 1)

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
        self.thread.kare_hazir.connect(self._kare_geldi)
        self.thread.durum.connect(self._durum_geldi)
        self.thread.kameralar_bulundu.connect(self._kameralar_geldi)
        self.thread.start()

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

    # ================= SOL KOLON =================
    def _sol_kolon(self):
        kol = QWidget()
        kol.setFixedWidth(716)
        v = QVBoxLayout(kol)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # --- kamera ---
        self.cam = QFrame()
        self.cam.setObjectName("cam")
        self.cam.setFixedHeight(464)
        cl = QVBoxLayout(self.cam)
        cl.setContentsMargins(0, 0, 0, 0)
        self.video = QLabel("Kamera başlatılıyor…")
        self.video.setObjectName("video")
        self.video.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.video)

        v.addWidget(self.cam)

        # --- sistem durumu (ASAMAYA DUYARLI) ---
        sysk = QFrame()
        sysk.setObjectName("panelk")
        sv = QVBoxLayout(sysk)
        sv.setContentsMargins(17, 13, 17, 13)
        sv.setSpacing(9)

        # baslik + asama pill
        brow = QHBoxLayout()
        ph = QLabel("SİSTEM DURUMU")
        ph.setObjectName("ph")
        brow.addWidget(ph)
        brow.addStretch(1)
        self.asama_pill = QLabel(self.asama or "—")
        self.asama_pill.setObjectName("asamap")
        brow.addWidget(self.asama_pill)
        sv.addLayout(brow)

        # asamaya gore degisen govde
        self.stack = QStackedWidget()
        yok = QLabel("Aşama seçiniz")
        yok.setObjectName("bosmsg")
        yok.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(yok)                     # 0: secim yok
        self.stack.addWidget(self._asama1_panel())    # 1: Asama 1 (kartlar)
        self.stack.addWidget(self._tur_panel(4))      # 2: Asama 2 (tur/4)
        self.stack.addWidget(self._tur_panel(8))      # 3: Asama 3 (tur/8)
        sv.addWidget(self.stack)

        # kural kutusu (asamaya gore)
        self.kural = QLabel()
        self.kural.setObjectName("kural")
        self.kural.setWordWrap(True)
        sv.addWidget(self.kural)

        v.addWidget(sysk)
        v.addStretch(1)
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
        kv.setContentsMargins(19, 15, 19, 15)
        kv.setSpacing(10)
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

        # NOT: mesafe/menzil gostergesi GECICI OLARAK KALDIRILDI (18.07.2026) — gercek
        # olcum/kalibrasyon eklenene kadar yaniltici sayi gosterilmeyecek. bkz. algi.py notu.

        self.fire_btn = QPushButton("A T E Ş")
        self.fire_btn.setObjectName("fire")
        self.fire_btn.setFixedHeight(48)
        self.fire_btn.setCheckable(True)
        self.fire_btn.clicked.connect(self._ates_bas)
        kv.addWidget(self.fire_btn)

        self.fire_status = QLabel("Hedef aranıyor…")
        self.fire_status.setObjectName("firest")
        self.fire_status.setAlignment(Qt.AlignCenter)
        kv.addWidget(self.fire_status)
        v.addWidget(kart)

        # --- tespit tablosu ---
        tk = QFrame()
        tk.setObjectName("panelk")
        tv = QVBoxLayout(tk)
        tv.setContentsMargins(19, 15, 19, 15)
        tv.setSpacing(10)
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
        v.addWidget(tk, 1)

        # --- angajman ---
        ak = QFrame()
        ak.setObjectName("panelk")
        av = QVBoxLayout(ak)
        av.setContentsMargins(19, 15, 19, 15)
        av.setSpacing(10)
        at = QLabel("ANGAJMAN DURUMU")
        at.setObjectName("ph")
        av.addWidget(at)
        arow = QHBoxLayout()
        arow.setSpacing(12)

        self.eng = QFrame()
        self.eng.setObjectName("engok")
        eh = QHBoxLayout(self.eng)
        eh.setContentsMargins(13, 10, 13, 10)
        eh.setSpacing(9)
        self.eng_dot = QLabel()
        self.eng_dot.setFixedSize(8, 8)
        self.eng_dot.setStyleSheet(f"background:{GRN};border-radius:4px;")
        ev = QVBoxLayout()
        ev.setSpacing(1)
        self.eng_name = QLabel("Angajman bekleniyor")
        self.eng_name.setObjectName("engname")
        self.eng_sub = QLabel("—")
        self.eng_sub.setObjectName("engsub")
        ev.addWidget(self.eng_name)
        ev.addWidget(self.eng_sub)
        eh.addWidget(self.eng_dot)
        eh.addLayout(ev)
        arow.addWidget(self.eng, 1)

        for baslik, alt in (("Atışa Yasak Alan", "Tanımsız — Kapalı"),
                            ("Harekete Yasak Alan", "Tanımsız — Kapalı")):
            tgl = QFrame()
            tgl.setObjectName("angtgl")
            th2 = QHBoxLayout(tgl)
            th2.setContentsMargins(20, 14, 20, 14)
            th2.setSpacing(20)
            l = QLabel(f'{baslik}<br><small style="color:{TXT3}">{alt}</small>')
            l.setObjectName("tgll")
            sw = QLabel()
            sw.setFixedSize(32, 16)
            sw.setStyleSheet(f"background:{BD2};border-radius:8px;")
            th2.addWidget(l, 1)
            th2.addWidget(sw)
            arow.addWidget(tgl, 1)
        av.addLayout(arow)
        v.addWidget(ak)
        return kol

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
        self._asama_uygula()

    def _asama_sec(self, ad):
        if not self.asama_btns[ad].isEnabled():
            return
        self.asama = None if self.asama == ad else ad   # tekrar tikla -> kaldir
        for a, b in self.asama_btns.items():
            b.setChecked(a == self.asama)
        self._asama_uygula()

    def _asama_uygula(self):
        """Secili asamaya gore stack + pill + kural gunceller."""
        self.stack.setCurrentIndex(self.ASAMA_IDX[self.asama])
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

        a = data["active"]
        if a:
            self.h_ad.setText(a["ad"])
            self.h_badge.setText(a["tip"])
            self._badge_stil(self.h_badge, a["tip"])
            self.h_conf.setText(f"%{a['conf']} güven")
            enemy = a["tip"] == "Düşman"
            if enemy:
                self.fire_status.setText("Hedef kilitli · Atışa hazır")
                self.fire_status.setStyleSheet(f"color:{GRN};font-size:13px;font-weight:500;")
                self.eng_name.setText("Angajman kabul edildi")
                self.eng_sub.setText(f"{a['ad']} · %{a['conf']} güven")
            else:
                self.fire_status.setText("Dost/bilinmeyen hedef · Pas geç")
                self.fire_status.setStyleSheet(f"color:{TXT3};font-size:13px;font-weight:500;")
                self.eng_name.setText("Angajman reddedildi")
                self.eng_sub.setText(f"{a['ad']} · dost/bilinmeyen")
        else:
            self.h_ad.setText("—")
            self.h_badge.setText("—")
            self._badge_stil(self.h_badge, None)
            self.h_conf.setText("")
            estop = "DURDUR" in data["mesaj"]
            self.fire_status.setText(data["mesaj"] if estop else "Hedef aranıyor…")
            self.fire_status.setStyleSheet(f"color:{RED if estop else TXT3};font-size:13px;font-weight:500;")
            self.eng_name.setText("Angajman bekleniyor")
            self.eng_sub.setText("—")

        # tablo
        hedefler = data["hedefler"]
        self.tablo.setRowCount(len(hedefler))
        for r, hh in enumerate(hedefler):
            kilitli = hh["aktif"] and hh["enemy"]
            it_ad = QTableWidgetItem(hh["ad"])
            it_ad.setForeground(QColor(TXT if kilitli else TXT2))
            it_tip = QTableWidgetItem(hh["tip"])
            it_tip.setForeground(QColor(RED if hh["enemy"] else (BLUE if hh["tip"] == "Dost" else TXT3)))
            it_dur = QTableWidgetItem(hh["durum"])
            it_dur.setForeground(QColor(RED if kilitli else TXT3))
            if kilitli:
                f = it_dur.font()
                f.setBold(True)
                it_dur.setFont(f)
            for c, it in enumerate((it_ad, it_tip, it_dur)):
                if kilitli:
                    it.setBackground(QColor(191, 32, 32, 18))
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
