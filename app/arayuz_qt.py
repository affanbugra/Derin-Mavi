# -*- coding: utf-8 -*-
"""DERIN MAVI - Native Kontrol Istasyonu (PySide6).

Tasarim: gorev_kontrol_yedek.html'in BIREBIR native kopyasi (acik tema).
Algi cekirdegi algi.py'den gelir. Donanim-bagimsizdir (CLAUDE.md ilke 7):
kamera secimi arayuzden yapilir, DERINMAVI_CAM env override desteklenir.

Calistir:  python app/arayuz_qt.py   (veya kokteki Baslat.bat)
"""
import glob
import json
import math
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

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF, QEvent, QPoint, QRect, QPointF
from PySide6.QtGui import (QImage, QPixmap, QFont, QColor, QPainter, QPen, QLinearGradient,
                           QRadialGradient, QPainterPath)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
    QSizePolicy, QButtonGroup,
    QGraphicsView, QGraphicsScene, QStackedWidget,
    QSlider, QCheckBox, QSpinBox, QScrollArea,
)

import algi
import kamera as kamera_mod   # YALNIZ harici (USB-C) kamera — bkz. kamera.py
import nisan
import tasarim as T          # Apple tasarim katmani — renk/olcu/stil TEK KAYNAK
import bolge as B
import kol_ikon as KI            # harekete/atisa izinli pencereler (sartname §4.2)
import gamepad as gamepad_mod
import kontrol as kontrol_mod
import protokol as P          # hiz duzeyi/durum sabitleri — TEK KAYNAK (bkz. protokol.py)
import hedef_kestirici as HK
import tilt_surucu as TS

HERE = os.path.dirname(os.path.abspath(__file__))
# Model klasoru: repo kokunde "models/". Ekip arkadaslari kendi egittikleri agirligi
# (best.pt / .onnx / herhangi .pt) BURAYA atinca uygulama otomatik bulur — kod degismez.
MODELS_DIR = os.path.abspath(os.path.join(HERE, "..", "models"))


def _modelleri_bul():
    """Kullanilacak modelleri DINAMIK bulur (oncelik sirasiyla). Doner: liste.

    HIZ NOTU (C1): bu proje GPU'suz laptopta calisiyor (CLAUDE.md §8) ve tek gercek
    darbogaz CPU inference'i. Ultralytics ayni agirligi OpenVINO'ya cevirebilir ve
    Intel CPU'da tipik 2-3x hizlanma verir — KOD DEGISMEDEN. Donusturmek icin:
        yolo export model=models/best.pt format=openvino
    Ciktiyi (models/best_openvino_model/) models/ icine birakmak yeterli; burasi
    onu otomatik tercih eder. Yoksa .pt ile calismaya devam eder.
    """
    modeller = []
    sec = os.environ.get("DERINMAVI_MODEL", "").strip()
    if sec:
        dusuk = sec.lower()
        if dusuk == "engine" or dusuk == "trt":
            p = os.path.join(MODELS_DIR, "best.engine")
            if os.path.isfile(p): modeller.append(p)
        elif dusuk == "onnx":
            p = os.path.join(MODELS_DIR, "best.onnx")
            if os.path.isfile(p): modeller.append(p)
        elif dusuk == "openvino":
            p = os.path.join(MODELS_DIR, "best_openvino_model")
            if os.path.isdir(p): modeller.append(p)
        elif dusuk in ("pt", "torch"):
            p = os.path.join(MODELS_DIR, "best.pt")
            if os.path.isfile(p): modeller.append(p)
        else:
            if os.path.isfile(sec) or os.path.isdir(sec): modeller.append(sec)

    for aday in ("best.engine", "best_openvino_model", "best.onnx", "best.pt"):
        p = os.path.join(MODELS_DIR, aday)
        if (os.path.isfile(p) or os.path.isdir(p)) and p not in modeller:
            modeller.append(p)
            
    for kalip in ("*.engine", "*_openvino_model", "*.onnx", "*.pt"):
        bulunan = sorted(glob.glob(os.path.join(MODELS_DIR, kalip)))
        for b in bulunan:
            if b not in modeller: modeller.append(b)
            
    return modeller

def _model_bul():
    """Tarihsel uyumluluk icin sadece ilk modeli veya None doner."""
    m = _modelleri_bul()
    return m[0] if m else None

# ---- Renk/olcu simgeleri: TEK KAYNAK app/tasarim.py (Apple macOS 27 UI Kit) ----
# Buradaki adlar TARIHSEL: kod tabaninda yuzlerce yerde geciyorlar, hepsi artik
# tasarim.py'deki Apple degerlerine isaret ediyor. Yeni kod dogrudan `T.` kullanir.
BG   = T.PENCERE      # pencere zemini (Window Backgrounds/Dark)
BD2  = T.AYRAC        # ince ayrac / pasif gosterge rengi
TXT  = T.L1           # Labels/Dark 1 Primary
TXT2 = T.L2           # 2 Secondary
TXT3 = T.L3           # 3 Tertiary
MAVI = MAVI_ACIK = BLUE = T.AKSAN                 # System Colors/Dark 8 Blue
RED  = T.KIRMIZI; GRN = T.YESIL; AMB = T.SARI     # 1 Red / 4 Green / 3 Yellow
F    = T.F


class SecimKutusu(QComboBox):
    """Acilir liste — ok isaretini KENDI cizer.

    Neden: QSS'te yaygin olan "::down-arrow'u kenarliklardan ucgen yap" numarasi
    (width/height 0 + border-left/right transparent) macOS'ta calismiyor; Qt alt
    bileseni kutunun tum genisligine gerdigi icin ok, kutunun ustune oturan DEV bir
    mavi kama olarak ciziliyordu (yaninda da native okun gri kalintisi). Ok artik
    QSS'te tamamen kapatilip (`image: none; border: none; width/height: 0`) burada
    QPainter ile ciziliyor: her platformda ayni, olceklenmeyen tek bir chevron.
    """

    def showPopup(self):
        # Acilir liste kutu genisligine sikismasin: uzun kamera adlari
        # ("MacBook Kamerası" gibi) kutuda kisalabilir ama LISTEDE tam okunmali.
        v = self.view()
        v.setMinimumWidth(max(self.width(), v.sizeHintForColumn(0) + 44))
        super().showPopup()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(TXT2 if self.isEnabled() else TXT3), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        cx, cy = self.width() - 15.0, self.height() / 2.0
        p.drawPolyline([QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2.5), QPointF(cx + 4, cy - 2)])
        p.end()


class _AciKarosu(QWidget):
    """Aci gostergesi karosu: arac resmi + namlu ucundan lazer isigi + BUYUK derece.

    Katman sirasi bilincli: (1) resim, (2) lazer isigi — ikisi de bu bileşenin
    paintEvent'inde, (3) derece yazisi AYRI bir cocuk QLabel. Qt cocuk bileşenleri
    ebeveynin ustune cizdigi icin isik yapisal olarak yazinin ALTINDA kalir;
    ebeveyn disina cizim de kirpildigindan isik karonun disina tasamaz.
    Yazi gercek QLabel oldugu icin `pan_val_lbl`/`tilt_val_lbl` eskisi gibi calisir.
    """

    YAZI_BOYU = 36                 # alt bant: derece yazisi
    ISIK_BOY = 0.42                # lazer uzunlugu = karo genisliginin orani

    def __init__(self, renk, parent=None):
        super().__init__(parent)
        self.aci = 0.0
        self.lazer_acik = False        # isik YALNIZ gercek lazer acikken cizilir
        self.hareket = None            # bu eksenin bolge.Pencere'leri (yasak alan dilimleri)
        self.atis = None
        self.deger = QLabel("0.0°", self)
        self.deger.setObjectName("turn")
        self.deger.setAlignment(Qt.AlignCenter)
        self.deger.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.deger.setStyleSheet(T.yazi((28, 700), renk,
                                        f"font-family:{T.FM}; background: transparent;"))
        self.deger.setFixedHeight(self.YAZI_BOYU)
        # Yazi LAYOUT ile alta yerlesir; resizeEvent'te elle setGeometry kullanilmaz:
        # arayuz bir QGraphicsView sahnesinde cizildigi icin elle konumlanan cocuk
        # pencerede yanlis yerde (karo disinda, kesik) gorunuyordu.
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(self.deger)

    def aci_ayarla(self, aci):
        aci = float(aci)
        if abs(aci - self.aci) > 0.05:
            self.aci = aci
            self.update()

    def lazer_ayarla(self, acik):
        acik = bool(acik)
        if acik != self.lazer_acik:
            self.lazer_acik = acik
            self.update()

    RESIM_ORANI = 0.80             # arac resmi alaninin %80'i (22.09: %20 kucultuldu)

    def resim_alani(self):
        """Resmin cizilecegi alan: yazi bandinin ustu, RESIM_ORANI kadar, ortali."""
        w, h = self.width(), self.height() - self.YAZI_BOYU - 2
        r = self.RESIM_ORANI
        return QRectF(w * (1 - r) / 2, 2 + h * (1 - r) / 2, w * r, h * r)

    @staticmethod
    def lazer_ciz(p, uc, yon, uzunluk):
        """Star Wars tarzi kisa lazer: genis soluk hale + parlak kirmizi govde +
        beyazimsi cekirdek; namludan uzaklastikca soner. Cagiran kirpmayi saglar."""
        if uc is None:
            return
        son = QPointF(uc.x() + yon.x() * uzunluk, uc.y() + yon.y() * uzunluk)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        for kalinlik, alfa, renk in ((14, 38, "#FF2D2D"), (8, 90, "#FF3B30"),
                                     (4, 230, "#FF4245"), (1.6, 255, "#FFE3E3")):
            g = QLinearGradient(uc, son)
            c0, c1 = QColor(renk), QColor(renk)
            c0.setAlpha(alfa)
            c1.setAlpha(0)
            g.setColorAt(0.0, c0)
            g.setColorAt(0.75, QColor(c0.red(), c0.green(), c0.blue(), int(alfa * 0.7)))
            g.setColorAt(1.0, c1)
            kalem = QPen(g, kalinlik)
            kalem.setCapStyle(Qt.RoundCap)
            p.setPen(kalem)
            p.drawLine(uc, son)
        # namlu agzinda kucuk parlama
        r = 7
        pr = QRadialGradient(uc, r)
        pr.setColorAt(0.0, QColor(255, 235, 235, 230))
        pr.setColorAt(0.4, QColor(255, 60, 50, 140))
        pr.setColorAt(1.0, QColor(255, 40, 40, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(pr)
        p.drawEllipse(uc, r, r)
        p.restore()

    def bolge_ayarla(self, hareket, atis):
        """Bu eksenin yasak alan pencereleri (bolge.Pencere; KOPYA saklanir ki
        kaydedilmemis duzenleme ekrana yansimasin)."""
        kopya = lambda w: (w.aktif, w.alt, w.ust)
        yeni = (kopya(hareket), kopya(atis))
        if yeni != (self.hareket, self.atis):
            self.hareket, self.atis = yeni
            self.update()

    # --- yasak alan dilimleri -------------------------------------------------
    # Operator acisi (yatayda on=0 saga +, dikeyde yere paralel=0 yukari +) -> Qt
    # acisi (3 yonu = 0, saat YONUNUN TERSI +). Alt siniflar tanimlar.
    ARALIK = (-180.0, 180.0)                 # eksenin tum araligi (operator acisi)

    DILIM_RENK = {"hareket": T.SARI, "atis": T.KIRMIZI, "izin": T.YESIL}
    DILIM_ALFA = {"hareket": 0.15, "atis": 0.15, "izin": 0.07}
    # Dolgunun yaricap boyunca alfa carpani. Iki karoda da renk ARACIN CEVRESINDE
    # belirip her iki uca dogru soner: ne merkezde araci boyar ne de disarida
    # kesik bir kenar birakir. Keskin kadran cizgisi denendi ve KALDIRILDI —
    # renkten cok cizgi one cikiyor, arayuze yapistirilmis gibi duruyordu
    # (kullanici iki karo icin de ayni seyi soyledi, 22.09).
    DILIM_DURAK = ((0.0, 0.0), (0.5, 0.0), (0.9, 1.0), (1.0, 0.0))

    def qt_aci(self, a):
        raise NotImplementedError

    def dilim_merkezi(self):
        """(merkez, yaricap) — karo koordinatinda. Alt siniflar tanimlar."""
        raise NotImplementedError

    def dilimler(self):
        """[(tur, alt, ust)] — cizilecek renkli dilimler (operator acisi).
        Harekete yasak = hareket penceresinin disi (sari); atisa yasak = hareket
        penceresinin ICINDE kalan ama atis penceresinin disi (kirmizi); atis izni =
        atis penceresi (soluk yesil). Atis penceresi hareket penceresinin disina
        tasamadigi (bolge.atis_uyumla) icin dilimler ust uste binmez."""
        if self.hareket is None:
            return []
        lo, hi = self.ARALIK
        h_aktif, h0, h1 = self.hareket
        a_aktif, a0, a1 = self.atis
        if not h_aktif:
            h0, h1 = lo, hi
        out = []
        if h_aktif:
            out += [("hareket", lo, h0), ("hareket", h1, hi)]
        if a_aktif:
            a0, a1 = max(a0, h0), min(a1, h1)
            out += [("atis", h0, a0), ("atis", a1, h1), ("izin", a0, a1)]
        return [(t, x, y) for t, x, y in out if y - x > 0.05]

    def bolge_ciz(self, p):
        dilimler = self.dilimler()
        if not dilimler:
            return
        merkez, r = self.dilim_merkezi()
        kutu = QRectF(merkez.x() - r, merkez.y() - r, 2 * r, 2 * r)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        for tur, x, y in dilimler:
            renk, alfa = QColor(self.DILIM_RENK[tur]), self.DILIM_ALFA[tur]
            yol = QPainterPath(merkez)
            yol.arcTo(kutu, self.qt_aci(y), y - x)      # qt_aci azalan: y'den x'e CCW
            yol.closeSubpath()
            # Merkeze dogru sonen dolgu: arac okunur kalir, renk disa dogru belirginlesir.
            g = QRadialGradient(merkez, r)
            for konum, carpan in self.DILIM_DURAK:
                c = QColor(renk)
                c.setAlphaF(alfa * carpan)
                g.setColorAt(konum, c)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawPath(yol)

        p.restore()

    def paintEvent(self, e):
        p = QPainter(self)
        self.bolge_ciz(p)                      # dilimler aracin ARKASINDA
        uc, yon = self.ciz(p, self.resim_alani(), self.aci)
        if self.lazer_acik:
            self.lazer_ciz(p, uc, yon, self.width() * self.ISIK_BOY)
        p.end()


class AracAciGostergesi(_AciKarosu):
    """YUKSELIS karosu — aracin yan gorunusu; namlu tilt acisi kadar kalkar.

    Resim iki katman (Grafik/arac_govde.png + arac_namlu.png). Namlu gercekte
    govdedeki egik kolonun ARKASINDAN gectigi icin once namlu (donmus), sonra
    govde cizilir: kolon namluyu dogal olarak ortter.

    Operator acisi dogrudan fiziksel -30°..+30° araligindadir; 0° yataydir.

    ⚠ [VARSAYIM] Donme ekseni namlu ekseninin kolonla kesistigi nokta; gercek muylu
    konumu mekanik ekipten teyit edilmeli. Aci ESP32'nin OLCUMU degil HEDEFTIR (§5.1)."""

    GOVDE_PIVOT = (377, 182)       # govde resmindeki donme ekseni (piksel)
    NAMLU_PIVOT = (449, 89)        # namlu resmindeki ayni nokta
    NAMLU_AGZI = (6, 91)           # namlu resminde V kesiginin ortasi (isigin cikisi)
    FIZIKSEL_ALT = -30.0           # sistem 0°'nin fiziksel karsiligi (yere gore)
    MEKANIK_ARALIK = 60.0          # toplam hareket kabiliyeti

    def __init__(self, parent=None):
        super().__init__(T.AKSAN, parent)
        yol = os.path.join(HERE, "Grafik")
        self._govde = QImage(os.path.join(yol, "arac_govde.png"))
        self._namlu = QImage(os.path.join(yol, "arac_namlu.png"))

    @classmethod
    def fiziksel(cls, sistem_aci):
        """Sistem acisi (0..60) -> namlunun yere gore acisi (-30..+30), kirpilmis:
        namlu fiziksel duraktan otesine GIDEMEZ, ekranda da gidiyormus gibi gosterilmez."""
        f = float(sistem_aci)
        return max(cls.FIZIKSEL_ALT, min(cls.FIZIKSEL_ALT + cls.MEKANIK_ARALIK, f))

    @classmethod
    def sahne_kutusu(cls, govde_boyut, namlu_boyut):
        """Tum mekanik aralikta cizimi kapsayan dikdortgen (govde koordinati). Sabit
        tutulur ki namlu kalkinca arac kuculup buyumesin."""
        from math import radians, cos, sin
        px, py = cls.GOVDE_PIVOT
        nx, ny = cls.NAMLU_PIVOT
        nw, nh = namlu_boyut
        kose = [(-nx, -ny), (nw - nx, -ny), (-nx, nh - ny), (nw - nx, nh - ny)]
        xs, ys = [0, govde_boyut[0]], [0, govde_boyut[1]]
        alt = int(cls.FIZIKSEL_ALT)
        for derece in range(alt, alt + int(cls.MEKANIK_ARALIK) + 1, 5):
            a = radians(derece)
            for kx, ky in kose:
                xs.append(px + kx * cos(a) - ky * sin(a))
                ys.append(py + kx * sin(a) + ky * cos(a))
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    ARALIK = (B.TILT_CALISMA_MIN, B.TILT_CALISMA_MAX)  # izinli çalışma alanı
    # Yelpaze dar oldugu icin renk namlunun hemen otesinde baslar (tabandaki
    # rampa daha erken acilsa govdenin arkasinda harcanirdi).
    DILIM_DURAK = ((0.0, 0.0), (0.45, 0.0), (0.88, 0.95), (1.0, 0.30))

    def ciz(self, p, hedef, aci):
        return self.ciz_saf(p, hedef, self._govde, self._namlu, aci)

    def qt_aci(self, a):
        return 180.0 - a                      # namlu SOLA bakar; + = yukari

    def dilim_merkezi(self):
        """Namlunun donme ekseni (ciz_saf ile ayni donusum) + namlu boyunca yaricap."""
        hedef = self.resim_alani()
        if self._govde.isNull() or self._namlu.isNull():
            return hedef.center(), min(hedef.width(), hedef.height()) / 2
        kutu = self.sahne_kutusu((self._govde.width(), self._govde.height()),
                                 (self._namlu.width(), self._namlu.height()))
        olcek = min(hedef.width() / kutu.width(), hedef.height() / kutu.height())
        ox = hedef.x() + (hedef.width() - kutu.width() * olcek) / 2
        oy = hedef.y() + (hedef.height() - kutu.height() * olcek) / 2
        merkez = QPointF(ox + (self.GOVDE_PIVOT[0] - kutu.x()) * olcek,
                         oy + (self.GOVDE_PIVOT[1] - kutu.y()) * olcek)
        # Yaricap namlu boyunun biraz otesi: dolgu (DILIM_DURAK) zaten namlunun
        # bittigi yerde belirdigi icin govdenin arkasinda kaybolmaz.
        namlu = (self.NAMLU_PIVOT[0] - self.NAMLU_AGZI[0]) * olcek
        return merkez, min(namlu * 1.32, merkez.x() - 4)

    @classmethod
    def ciz_saf(cls, p, hedef, govde, namlu, aci):
        """Saf cizim (pencere gerektirmez, test edilebilir). `aci` SISTEM acisidir.
        Doner: (namlu agzi noktasi, isik yonu) — karo koordinatinda."""
        if govde.isNull() or namlu.isNull():
            return None, None
        kutu = cls.sahne_kutusu((govde.width(), govde.height()), (namlu.width(), namlu.height()))
        olcek = min(hedef.width() / kutu.width(), hedef.height() / kutu.height())
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(hedef.x() + (hedef.width() - kutu.width() * olcek) / 2,
                    hedef.y() + (hedef.height() - kutu.height() * olcek) / 2)
        p.scale(olcek, olcek)
        p.translate(-kutu.x(), -kutu.y())
        p.save()
        p.translate(*cls.GOVDE_PIVOT)
        p.rotate(cls.fiziksel(aci))            # resim = fiziksel 0° (yere paralel)
        p.translate(-cls.NAMLU_PIVOT[0], -cls.NAMLU_PIVOT[1])
        p.drawImage(QPointF(0, 0), namlu)
        tr = p.transform()                     # namlu -> karo donusumu (isik icin)
        p.restore()
        p.drawImage(QPointF(0, 0), govde)      # govde ustte: kolon namlu kokunu ortter
        p.restore()
        uc = tr.map(QPointF(*cls.NAMLU_AGZI))
        ileri = tr.map(QPointF(cls.NAMLU_AGZI[0] - 100, cls.NAMLU_AGZI[1]))   # namlu sola bakar
        return uc, _birim(uc, ileri)


class AracYonGostergesi(_AciKarosu):
    """AZIMUT karosu — aracin ust gorunusu; pan acisi kadar SAAT YONUNDE doner.

    Resimdeki hal = 0° (namlu tam karsiya). Aci arttikca saga (saat yonunde)
    doner (kullanici tanimi, 21.09.2026); ekrandaki azimut 0..360 sarmalidir.

    ⚠ [VARSAYIM] Donme ekseni govdenin merkezi; gercek doner tabla merkezi mekanik
    ekipten teyit edilmeli. Aci ESP32'nin OLCUMU degil HEDEFTIR (§5.1)."""

    PIVOT = (330, 356)             # arac_ust.png icinde donme ekseni (piksel)
    NAMLU_AGZI = (330, 4)          # ustteki V kesiginin ortasi (isigin cikisi)

    def __init__(self, parent=None):
        super().__init__(T.L1, parent)
        self._resim = QImage(os.path.join(HERE, "Grafik", "arac_ust.png"))
        self._yaricap = self.donme_yaricapi(self._resim)

    def aci_ayarla(self, aci):
        super().aci_ayarla(float(aci) % 360.0)

    @classmethod
    def donme_yaricapi(cls, resim):
        """Pivottan EN UZAK opak piksele uzaklik. Kutunun koselerine gore degil
        gercek sekle gore hesaplanir: arac her acida sigar ama gereksiz kuculmez."""
        if resim.isNull():
            return 1.0
        from math import hypot
        px, py = cls.PIVOT
        en = 1.0
        for y in range(0, resim.height(), 2):
            for x in range(0, resim.width(), 2):
                if resim.pixelColor(x, y).alpha() > 0:
                    en = max(en, hypot(x - px, y - py))
        return en

    def ciz(self, p, hedef, aci):
        return self.ciz_saf(p, hedef, self._resim, aci, self._yaricap)

    # Tam daire: renk arac siluetinin cevresinde bir hale olarak durur; taban
    # rampasi biraz daha guclu, cunku alan genis ve renk her iki uca soner.
    DILIM_ALFA = {"hareket": 0.19, "atis": 0.19, "izin": 0.09}

    # Yalniz GIDILEBILEN yari boyanir: arka yari yapisal olarak erisilemez
    # (B.PAN_MAX), orayi sariya boyamak "yasak alan" degil "olmayan alan" gosterirdi.
    ARALIK = (-B.PAN_MAX, B.PAN_MAX)

    def qt_aci(self, a):
        return 90.0 - a                       # on = yukari, + = saat yonu

    def dilim_merkezi(self):
        """Arac merkezi (ciz_saf ile ayni); yaricap aracin biraz disi — resim alani
        tum karonun %80'i oldugu icin dilimler aracin cevresinde bir halka gibi durur."""
        merkez = self.resim_alani().center()
        w, h = self.width(), self.height() - self.YAZI_BOYU - 2
        return merkez, min(w, h) / 2 - 3

    @classmethod
    def ciz_saf(cls, p, hedef, resim, aci, yaricap):
        if resim.isNull():
            return None, None
        olcek = min(hedef.width(), hedef.height()) / (2 * yaricap)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(hedef.center())
        p.scale(olcek, olcek)
        p.rotate(aci)                          # Qt: + = saat yonu = saga donus
        p.translate(-cls.PIVOT[0], -cls.PIVOT[1])
        p.drawImage(QPointF(0, 0), resim)
        tr = p.transform()
        p.restore()
        uc = tr.map(QPointF(*cls.NAMLU_AGZI))
        ileri = tr.map(QPointF(cls.NAMLU_AGZI[0], cls.NAMLU_AGZI[1] - 100))   # namlu yukari bakar
        return uc, _birim(uc, ileri)


def _birim(a, b):
    """a'dan b'ye birim yon vektoru."""
    from math import hypot
    dx, dy = b.x() - a.x(), b.y() - a.y()
    n = hypot(dx, dy) or 1.0
    return QPointF(dx / n, dy / n)


class _TiklanirKapsul(QFrame):
    """Tiklaninca geri cagri yapan kapsul. Icindeki anahtar kendi tiklamasini alir
    (cocuk once alir), kapsulun geri kalanina tiklamak ayar sayfasini acar."""

    def __init__(self, geri_cagri, parent=None):
        super().__init__(parent)
        self._geri_cagri = geri_cagri

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._geri_cagri()
        super().mousePressEvent(e)


class AppleSwitch(QWidget):
    """macOS anahtarı (toggle switch) — Apple macOS 27 UI Kit ölçüleriyle.

    Kitten ölçülen "3 Rg" anahtarı: gövde 54×24, tutamaç 32×20 (daire DEĞİL,
    KAPSÜL — macOS 26 ile değişti), kapalı zemin beyaz %10, açık zemin sistem
    mavisi, tutamaç beyaz %85 + yumuşak gölge. Qt bu bileşeni stil sayfasıyla
    düzgün çizemediği için kendimiz çiziyoruz."""
    toggled = Signal(bool)

    EN, BOY = 54, 24
    TUT_EN, TUT_BOY, BOSLUK = 32, 20, 2

    def __init__(self, checked=False, parent=None, active_color=None, kucuk=False):
        super().__init__(parent)
        if kucuk:                        # "Small" (20 px): Regular'in 5/6'si, ayni oranlar
            self.EN, self.BOY, self.TUT_EN, self.TUT_BOY = 45, 20, 27, 16
        self.setFixedSize(self.EN, self.BOY)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = bool(checked)
        self._active_color = QColor(active_color or T.AKSAN)
        self.oneri_val = 0

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        checked = bool(checked)
        if self._checked != checked:
            self._checked = checked
            self.update()
            self.toggled.emit(self._checked)

    def value(self):
        return 1 if self._checked else 0

    def setValue(self, val):
        self.setChecked(bool(val))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(Qt.NoPen)
        p.setBrush(self._active_color if self._checked else QColor(255, 255, 255, 26))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2.0, h / 2.0)

        x = (w - self.TUT_EN - self.BOSLUK) if self._checked else self.BOSLUK
        tut = QRectF(x, self.BOSLUK, self.TUT_EN, self.TUT_BOY)
        p.setBrush(QColor(255, 255, 255, 217))          # kit: beyaz %85
        p.drawRoundedRect(tut, self.TUT_BOY / 2.0, self.TUT_BOY / 2.0)
        p.end()


# =====================================================================
#  Ayar paneli — kaydiricilar + "oneri" isaretli
# =====================================================================
COZUNURLUK_SECENEK = [416, 512, 640, 960, 1280]

# Kaydirici: onerilen degerde YESIL, degistirilmisse VURGU rengi dolu kisim.
# Govde olculeri (oluk 6px, tutamac 20px beyaz daire) Apple kitinden gelir.
SLIDER_ONERI   = T.slider_stil(vurgu=T.YESIL)
SLIDER_DEGISIK = T.slider_stil(vurgu=T.AKSAN)
SLIDER_LAZER   = T.slider_stil("lazersl", vurgu=T.AKSAN)

ETIKET_ONERI   = T.deger_etiketi(T.YESIL)
ETIKET_DEGISIK = T.deger_etiketi(T.AKSAN)

# D-pad tuslari: Apple'in XL kapsul butonu (Liquid Glass'in imzasi yuvarlak uctur).
DPAD_EN, DPAD_BOY   = 68, 34            # yon tuslari (22.09: 58x28'den buyutuldu)
DPAD_NORMAL         = T.dpad_stil(en=DPAD_EN, boy=DPAD_BOY)
DPAD_BASILI         = T.dpad_stil(basili=True, en=DPAD_EN, boy=DPAD_BOY)
DPAD_MERKEZ         = T.dpad_stil(merkez=True, en=DPAD_EN, boy=DPAD_BOY)
DPAD_MERKEZ_BASILI  = T.dpad_stil(basili=True, merkez=True, en=DPAD_EN, boy=DPAD_BOY)

# ATES butonu metinleri
ATES_METIN_KAPALI = "ATEŞ"
ATES_METIN_ACIK = "ATEŞİ KES"

# Klavye -> D-pad yonu (WASD + ok tuslari; yalniz R = merkeze al — takim karari 21.09:
# Space/C kazara basilip gimbal'i merkeze kosturmasin).
TUS_YON = {Qt.Key_W: "up", Qt.Key_Up: "up", Qt.Key_S: "down", Qt.Key_Down: "down",
           Qt.Key_A: "left", Qt.Key_Left: "left", Qt.Key_D: "right", Qt.Key_Right: "right",
           Qt.Key_R: "center"}

# Ayar paneli sekmeleri: kalabalik tek liste yerine iki grup.
#   "Tespit"  — YOLO/ByteTrack davranisi
#   "Nişan"   — gimbal/kamera geometrisi (Otonom takip)
#
# (key, baslik, tip, min, max, aciklama)  — tablo yalnizca GORUNUMU tarif eder.
#   tip "yuzde": slider /100 · "kare"/"sayi": tam sayi · "secim": COZUNURLUK_SECENEK
#   "onda": slider /10 (ondalikli) · "anahtar": ac/kapa (0/1)
#
# ONEMLI: "onerilen" (yesil) deger burada YAZILI DEGILDIR; algi.VARSAYILAN_AYAR'dan okunur
# ve o degerler ULTRALYTICS VARSAYILANIDIR. Yani hicbir kaydiriciya dokunmayan biri, ham
# `yolo track source=0` ile AYNI sonucu alir. Sapmak isteyen buradan sapar.
AYAR_TANIM_TESPIT = [
    ("hassasiyet", "Hassasiyet", "yuzde", 5, 90,
     "Bir nesnenin YENİ HEDEF olarak takibe alınması için gereken güven.\n"
     "(Teknik: ByteTrack new_track_thresh / track_high_thresh — Ultralytics varsayılanı 0.25)\n\n"
     "↑ ARTTIRIRSAN: sadece net nesneler takibe girer, yanlış hedef azalır — ama zayıf/uzak "
     "nesneyi kaçırabilir.\n"
     "↓ AZALTIRSAN: zayıf/uzak nesneleri de yakalar — ama arka plana yanlış kutu atma riski artar."),
    ("gosterim", "Gösterim eşiği", "yuzde", 5, 90,
     "Bir kutunun EKRANDA ÇİZİLMESİ için gereken güven. Bunun altındaki kutu çizilmez.\n"
     "(Takibe girmiş nesneye küçük bir tolerans tanınır — tek karelik zayıflamada titremesin diye.)\n\n"
     "↑ ARTTIRIRSAN: ekran temizlenir, sadece emin olunanlar görünür.\n"
     "↓ AZALTIRSAN: nesneler daha çabuk belirir — ama zayıf/hayalet kutu görülebilir."),
    ("onay_esigi", "Kesin tanıma eşiği", "yuzde", 10, 99,
     "Bir hedefin TİPİ (F-16 / İHA / Füze / Helikopter) kesin sayılması için gereken güven.\n\n"
     "Bu eşiğin üstünde yeterince kare gören hedef ONAYLANIR: tipi artık sabitlenir ve "
     "güveni düşse bile kutu kaybolmaz — takip kopmaz. Onaylanana kadar hedef '?' görünür.\n\n"
     "↑ ARTTIRIRSAN: yanlış tip etiketi azalır — ama onay geç gelir, hedef uzun süre '?' kalır.\n"
     "↓ AZALTIRSAN: hedef çabuk tanınır — ama zayıf/hatalı bir tahmin onaylanabilir."),
    ("onay_tekrari", "Onay için kare sayısı", "sayi", 1, 10,
     "Kesin tanıma eşiğini kaç kare geçerse hedef ONAYLANSIN.\n\n"
     "Ardışık olmak ZORUNDA DEĞİL: eşiği geçen kare puanı artırır, geçmeyen bir puan düşürür "
     "(çoğunluk oylaması). Böylece güven dalgalandığında onay yine de gerçekleşir.\n\n"
     "↑ ARTTIRIRSAN: onay daha güvenilir — ama geç gelir.\n"
     "↓ AZALTIRSAN: anında tanır — ama tek şanslı kare yanlış tipi onaylatabilir."),
    ("kararlilik", "Kutu kararlılığı", "kare", 5, 120,
     "Bir nesne bir an görünmez olursa takibi kaç kare hafızada tutulsun.\n"
     "(Teknik: ByteTrack track_buffer — Ultralytics varsayılanı 30)\n\n"
     "↑ ARTTIRIRSAN: kısa kayıplarda (önünden bir şey geçmesi) takip kopmaz — ama gerçekten "
     "kadraj dışına çıkan nesne geç silinir.\n"
     "↓ AZALTIRSAN: giden nesne hızlı silinir — ama takip daha çok kopar, ID değişir."),
    ("cozunurluk", "Çözünürlük", "secim", 0, len(COZUNURLUK_SECENEK) - 1,
     "Modele verilen görüntü çözünürlüğü — HIZ ile UZAK NESNE görme arasındaki denge.\n"
     "(Ultralytics varsayılanı 640)\n\n"
     "↑ BÜYÜTÜRSEN (960/1280): 15 m'deki küçük hedefi daha iyi görür — ama FPS düşer.\n"
     "↓ KÜÇÜLTÜRSEN (416): akıcı olur, takip gecikmesi azalır — ama uzakta zayıflar.\n\n"
     "NOT: FPS düşerse hareketli hedefte nişan gecikmesi artar — ikisini birlikte düşün."),
    ("iou", "Kutu ayrıştırma (IoU)", "yuzde", 10, 95,
     "Üst üste binen iki kutunun AYNI nesne mi sayılacağı (NMS eşiği).\n"
     "(Ultralytics varsayılanı 0.70)\n\n"
     "↑ ARTTIRIRSAN: yan yana duran hedefler ayrı ayrı kalır — ama aynı nesneye çift kutu riski.\n"
     "↓ AZALTIRSAN: çift kutu temizlenir — ama sürüde (Aşama 2) bitişik hedefler birleşebilir."),
    ("ortusme", "Çakışan kutu temizliği", "yuzde", 30, 99,
     "Üst üste binen iki kutudan birini eler: küçük kutunun bu kadarı diğerinin içinde "
     "kalıyorsa ikisi AYNI nesne sayılır.\n\n"
     "Neden gerekli: NMS (yukarıdaki 'Kutu ayrışması') yalnızca AYNI SINIF içinde çalışır. "
     "Model aynı maketi hem 'Füze' hem 'Helikopter' sanarsa kutular %90 örtüşse bile ikisi de "
     "ekranda kalır. Görevde aynı alanda iki hedef bulunmadığı için bu her zaman hatadır.\n\n"
     "Kesin tanınmış (onaylanmış) hedef önceliklidir; eşitlikte güveni yüksek olan kalır.\n"
     "Balon buna dahil değildir — maketin altında olduğu için gövdeyle örtüşür.\n\n"
     "↓ AZALTIRSAN: çift kutular daha agresif temizlenir — ama yan yana gelen iki gerçek "
     "hedeften biri elenebilir (Aşama 2 sürüsü).\n"
     "↑ ARTTIRIRSAN: temizlik gevşer; %99 pratikte kapalı demektir."),
    ("maks_tespit", "En fazla hedef", "sayi", 5, 300,
     "Bir karede en fazla kaç kutu işlensin.\n(Ultralytics varsayılanı 300)\n\n"
     "Düşürmek çok kalabalık sahnede işi hafifletir; yarışma senaryosunda (en fazla 3-4 hedef) "
     "varsayılan zaten fazlasıyla yeterli."),
    ("kamera_fps", "Kamera FPS", "sayi", 5, 120,
     "Kameradan alınması istenen kare hızı (FPS).\n\n"
     "NOT: Değişikliğin etkili olması için yukarıdan kamerayı tekrar seçmelisiniz."),
]

# SAHI (Slicing Aided Hyper Inference) — uzak/kucuk nesneleri tespit icin dilimli cikarim.
AYAR_TANIM_SAHI = [
    ("sahi", "SAHI Modu", "anahtar", 0, 1,
     "Uzak / küçük nesneleri algılamak için SAHI (Slicing Aided Hyper Inference) modunu açar.\n\n"
     "SAHI görüntüyü üst üste binen dilimlere böler ve her dilimde ayrı ayrı çıkarım yapar. "
     "Normal YOLO'nun kaçırdığı 15 m'deki küçük İHA gibi hedefleri yakalar.\n\n"
     "⚠ SAHI modunda ByteTrack takibi DEVRE DIŞI kalır — nesneler ID almaz. "
     "Gimbal kontrolü yokken (tek açıdan tespit) sorun değildir.\n\n"
     "AÇARSAN: küçük nesne tespiti dramatik artar — ama FPS düşer (her dilim ayrı çıkarım).\n"
     "KAPATIRSAN: normal YOLO hızında çalışır — ama uzak nesneleri kaçırabilir."),
    ("sahi_dilim", "Dilim boyutu", "secim_sahi", 0, 2,
     "Her dilimin kenar uzunluğu (piksel). Model eğitim boyutuyla (640) aynı olması önerilir.\n\n"
     "KÜÇÜLTÜRSEN (480): daha çok dilim = daha iyi küçük nesne — ama daha yavaş.\n"
     "BÜYÜTÜRSEN (800): daha az dilim = daha hızlı — ama küçük nesne avantajı azalır."),
    ("sahi_ortusme", "Dilim örtüşmesi", "yuzde", 5, 50,
     "Komşu dilimlerin ne kadar üst üste bineceği.\n\n"
     "Düşük örtüşme (%%10): hızlı ama dilim kenarlarındaki nesneyi kaçırabilir.\n"
     "Yüksek örtüşme (%%30-40): kenar nesnelerini yakalar — ama dilim sayısı artar, FPS düşer."),
]

# SAHI dilim boyutu secenekleri ("secim_sahi" tipi icin)
SAHI_DILIM_SECENEK = [480, 640, 800]

AYAR_TANIM_NISAN = [
    ("fov", "Kamera görüş açısı", "onda", 200, 1200,
     "Kameranın YATAY görüş açısı (derece). Piksel hatasını açıya çevirmek için kullanılır — "
     "otonom takibin doğruluğu buna bağlıdır.\n\n"
     "Bilmiyorsanız: kameradan bilinen uzaklığa (ör. 2 m) bir cetvel koyup kadraja tam sığan "
     "genişliği (G) ölçün → FOV = 2 × atan(G / (2×2 m)).\n\n"
     "Yanlış girilirse gimbal ya hedefi aşar ya da yavaş yaklaşır."),
    ("kp", "Takip gücü (Kp)", "yuzde", 10, 150,
     "Hedef merkezden kaçtığında hatanın ne kadarını TEK adımda kapatmaya çalışsın.\n\n"
     "↑ ARTTIRIRSAN: hedefe daha hızlı kilitlenir, hareketli hedefte geride kalma azalır — "
     "ama aşma (overshoot) ve salınım riski artar.\n"
     "↓ AZALTIRSAN: yumuşak ve kararlı — ama hareketli hedefin arkasında kalır.\n\n"
     "Hareketli hedefte kalıcı gecikme ≈ (hedef hızı × kare süresi) / Kp."),
    ("kd", "Öngörü süresi (Kd)", "onda", 0, 30,
     "Hedefin KAÇ SANİYE SONRAKİ yerine nişan alınsın (ileri görüş).\n\n"
     "Kamera + işlem gecikmesini telafi eder; tipik olarak bir kare süresi kadar (0.06 sn).\n\n"
     "↑ ARTTIRIRSAN: hızlanan hedefte önünü keser — ama gürültüde zıplama yapar.\n"
     "↓ 0 YAPARSAN: saf oransal kontrol, en sakin ama en geç tepki."),
    ("olu_bolge_kutu", "Ölü bölge (isabet payı)", "yuzde", 2, 60,
     "Lazer, nişan noktasına bu kadar yaklaşınca \"hedefteyim\" sayılır ve motora komut "
     "GÖNDERİLMEZ. Birim: HEDEF KUTUSUNUN YÜKSEKLİĞİ.\n\n"
     "Bu değer doğrudan İSABETİ belirler: ateş kapısı buna bakar, yani sistem bu yarıçapın "
     "içindeyken lazeri açar. Balondan geniş olursa sistem \"hedefteyim\" der ama lazer "
     "balonun yanına gider.\n\n"
     "Neden kutuya oranlı: şartname (s.19) balonu \"kesit alanına göre belli bir "
     "büyüklükte\" tanımlıyor — balon hedefle birlikte küçülür. Kareye oranlı sabit bir "
     "yüzde 5 m'de doğru olsa bile 15 m'de balondan geniş kalırdı.\n\n"
     "↑ ARTTIRIRSAN: çabuk yerleşir, sakin durur — ama ıskalama riski artar.\n"
     "↓ AZALTIRSAN: daha isabetli — ama titreme başlar ve dwell tamamlanamaz.\n\n"
     "KALİBRASYON: balonun ekrandaki yarıçapı, hedef kutusunun yüksekliğinin kaçta kaçı? "
     "Bu değeri onun ALTINDA tutun."),
    ("olu_bolge", "Ölü bölge (kutu yokken)", "yuzde", 0, 10,
     "Hedef kutusu bilinmediğinde kullanılan yedek ölü bölge (kare genişliğinin yüzdesi).\n\n"
     "Normal otonom takipte kullanılmaz — orada yukarıdaki kutuya oranlı değer geçerlidir. "
     "Bu yalnızca bir geri düşüş (fallback) değeridir."),
    ("lazer_ofset_x", "Lazer ofseti — Yatay", "yuzde", -15, 15,
     "Kamera ile lazer farklı noktalara monteli; ekran merkezi lazerin vurduğu "
     "nokta değildir (boresight/paralaks).\n\n"
     "KALİBRASYON: Manuel modda lazeri bir hedefe TAM İSABET ettirin (nokta hedefin "
     "üzerinde dururken durun). Ekrandaki yeşil nişangah hedeften SAĞDA duruyorsa "
     "bu değeri AZALTIN, SOLDA duruyorsa ARTIRIN — nişangah hedefe oturana kadar.\n\n"
     "Otonom takip artık bu kalibre noktaya kilitlenir, ekran merkezine değil."),
    ("lazer_ofset_y", "Lazer ofseti — Dikey", "yuzde", -15, 15,
     "Yatay ofsetle aynı kalibrasyon, dikey eksende.\n\n"
     "Nişangah hedefin ALTINDA duruyorsa bu değeri AZALTIN, ÜSTÜNDE duruyorsa "
     "ARTIRIN — nişangah hedefe oturana kadar."),
    ("balon_ofset", "Balon nişan ofseti", "yuzde", 0, 150,
     "Nişan noktası, hedef kutusunun ALT KENARINDAN ne kadar aşağıya konsun. "
     "Birim: hedef kutusunun YÜKSEKLİĞİ (%100 = bir maket boyu aşağı).\n\n"
     "İMHA KANITI BALONUN PATLAMASIDIR ve balon maketin ALTINDADIR — lazer gövdeye "
     "değil balona nişan almalı. Model şu an balonu göremediği için (best.pt 4 sınıf, "
     "balon yok) balonun yeri maketten geometrik olarak kestirilir.\n\n"
     "Oransal olması kasıtlı: balon maketin altında sabit bir FİZİKSEL mesafede durur, "
     "açısal karşılığı mesafeyle değişir. Kutu yüksekliği de aynı oranda küçüldüğü için "
     "bu ayar 5/10/15 m'de kendiliğinden doğru kalır.\n\n"
     "KALİBRASYON: Otonom modda hedefe kilitlenmesini bekleyin; nişangah balonun "
     "ÜSTÜNDE kalıyorsa ARTIRIN, ALTINA kaçıyorsa AZALTIN.\n\n"
     "Model bir gün balon sınıfını öğrenirse gerçek tespit bu kestirimi otomatik ezer."),
]

# Otonom Ateşleme Ayarları
OTONOM_DWELL_SURE = 0.5  # sn (Hedef bu kadar süre merkezde kalırsa lazer açılır)
OTONOM_ATES_SURE = 1.0   # sn (Lazer açıldıktan sonra en az bu kadar süre açık kalır)
OTONOM_BEKLEME_SURE = 10.0 # sn (Ateş bittikten sonra hedef aramadan beklenecek süre)
# =====================================================================
#  Ortak Veri (Kamera ve Algi threadleri arasi)
# =====================================================================
import threading

class OrtakVeri:
    def __init__(self):
        self.kilit = threading.Lock()
        self.kare = None
        self.kare_sira = -1
        self.kare_t = 0.0
        self.dets = []
        self.balonlar = []
        self.active_idx = -1
        self.fps = 0.0          # YOLO inference FPS
        self.kamera_fps = 0.0   # Kamera okuma FPS
        self.merkezde = False   # Hedef olu bolgede mi (dwell icin)
        self.nisan_hata_px = None   # teshis: (px, py) nisan noktasi - lazer referansi
        self.olu_bolge_px = None    # teshis: (olu_x, olu_y) o karedeki isabet yaricapi

# =====================================================================
#  Algilama (Inference) is parcacigi (Thread 2)
# =====================================================================
class InferenceThread(QThread):
    model_bilgi = Signal(str, list)         # ozet metni, eksik siniflar (C7)
    nisan_komut = Signal(float, float)      # d_yaw, d_pitch — Otonom takip (B3)
    takip_olcum = Signal(object)

    def __init__(self, veri):
        super().__init__()
        self.veri = veri
        self._calis = True
        self.model = None
        self.asama = 3                      # 1/2/3/0 — SARTNAME davranisi
        self.estop = False
        self.otonom = False                 # Otonom modda mi
        self.kamera_acisi_fn = None
        self._onceki_kamera_acisi = None
        self.nisanci = nisan.PDNisanci()

    def _kamera_kaymasi(self, kare_t, genislik):
        fn = self.kamera_acisi_fn
        if fn is None:
            return
        try:
            aci = fn(kare_t - float(algi.AYAR.get("kamera_gecikme", 0.03)))
        except Exception:
            aci = None
        if aci is None or None in aci:
            self._onceki_kamera_acisi = None
            return
        onceki, self._onceki_kamera_acisi = self._onceki_kamera_acisi, aci
        if onceki is not None:
            ppd = float(algi.AYAR.get("takip_ppd_pan", 18.7)) * genislik / 1280.0
            algi.kamera_kaymasi_bildir(-(aci[0] - onceki[0]) * ppd,
                                       (aci[1] - onceki[1]) * ppd)

    def run(self):
        # Mevcut modelleri sirasiyla dener, ilk yuklenenle devam eder
        for model_yolu in _modelleri_bul():
            try:
                self.model = YOLO(os.path.abspath(model_yolu))
                self.model_bilgi.emit(algi.model_sinif_ozeti(self.model), algi.eksik_siniflar(self.model))
                break # Basariyla yuklendi, denemeyi birak
            except Exception as e:
                print(f"Model yuklenemedi ({model_yolu}): {e}")
                self.model = None

        son_islenen_sira = -1
        t_son, fps = time.perf_counter(), 0.0

        while self._calis:
            try:
                with self.veri.kilit:
                    kare = self.veri.kare
                    sira = self.veri.kare_sira
                    kare_t = self.veri.kare_t

                if kare is None or sira == son_islenen_sira or self.model is None:
                    self.msleep(3)
                    continue

                son_islenen_sira = sira
                frame = kare.copy()

                self._kamera_kaymasi(kare_t, frame.shape[1])
                dets, balonlar, active_idx = algi.analiz_et(self.model, frame, self.estop, self.asama)

                merkezde = False
                aktif_det = dets[active_idx] if 0 <= active_idx < len(dets) else None
                kirmizi_kaniti = (aktif_det is not None and not aktif_det.get("hayalet")
                                  and algi.anlik_kirmizi_kaniti(frame, aktif_det["box"]))
                if self.otonom and not self.estop and aktif_det is not None and kirmizi_kaniti:
                    if aktif_det.get("hayalet"):
                        # ⚠ HAYALET HEDEFE NISAN ALINMAZ. Kutu KARE KOORDINATLARINDA
                        # DONMUS: gimbal ne yaparsa yapsin hata azalmaz, dolayisiyla
                        # PD ayni yone komut uretmeye devam eder ve namlu yazilimsal
                        # tavana tirmanir (16.08: tilt 180'e dayaniyordu — 30 kare x
                        # ~15 FPS = 2 sn, Normal hizda 80 dereceye kadar kacis).
                        # Sistem OLDUGU YERDE BEKLER.
                        #
                        # Ama `merkezde` SIFIRLANMAZ: hayaletin tum varlik sebebi
                        # kisa tespit kesintilerini yutmak. Her kesintide dwell
                        # sayacini sifirlasaydik ates hic tamamlanamazdi.
                        merkezde = False
                    else:
                        h, w = frame.shape[:2]
                        kutu = aktif_det["box"]
                        hedef_xy = nisan.nisan_noktasi(kutu, balonlar)
                        # Kutu yuksekligi olu bolgeyi olcekler: balon hedefle birlikte
                        # kuculdugu icin isabet olcutu de kutuya oranli olmali (sartname
                        # s.19 "kesit alanina gore belli bir buyuklukte balon").
                        d_yaw, d_pitch = self.nisanci.adim(
                            hedef_xy, (w, h), hedef_yukseklik=abs(kutu[3] - kutu[1]))
                        if d_yaw is not None:
                            self.nisan_komut.emit(d_yaw, d_pitch)
                        else:
                            merkezde = True
                        (ex, ey), (olu_x, olu_y) = self.nisanci.son_hata_px, self.nisanci.son_olu_px
                        self.takip_olcum.emit({"var": True, "t": kare_t, "ex": ex, "ey": ey,
                                               "olu_x": olu_x, "olu_y": olu_y, "w": w})
                else:
                    self.nisanci.sifirla()
                if self.otonom and not self.estop and not kirmizi_kaniti:
                    self.takip_olcum.emit({"var": False, "t": kare_t})

                now = time.perf_counter()
                dt = now - t_son
                t_son = now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt)

                with self.veri.kilit:
                    self.veri.dets = dets
                    self.veri.balonlar = balonlar
                    self.veri.active_idx = active_idx
                    self.veri.fps = fps
                    self.veri.merkezde = merkezde
                    # Teshis: ates kapisi "hata < olu bolge" olunca acilir. Ikisi de
                    # gorunmezse "neden ates etmiyor" sorusu cevapsiz kalir.
                    self.veri.nisan_hata_px = self.nisanci.son_hata_px
                    self.veri.olu_bolge_px = self.nisanci.son_olu_px
            except Exception as e:
                import traceback
                print("INFERENCE THREAD ERROR:")
                traceback.print_exc()
                self.msleep(100)

    def durdur(self):
        self._calis = False

# =====================================================================
#  Video Goruntu is parcacigi (Thread 3 / GUI feed)
# =====================================================================
# HEDEFLER karti daima bu sirayla listelenir (takim karari) — kac hedef, hangi
# sirayla tespit edilirse edilsin degismez. Bilinmeyen/onaysiz ("belirsiz") sinif
# listenin sonuna duser.
HEDEF_ONCELIK = {"fuze": 0, "helikopter": 1, "f16": 2, "drone": 3}

# Otonom nisan komutlari arasi ASGARI sure (saniye) — bkz. MainWindow._nisan_geldi
# "MESGUL KAPISI". Gonderilen her komuttan sonra, o komutun tahmini fiziksel
# tamamlanma suresinin bir kismi (NISAN_MESGUL_ORANI) kadar yeni komut kabul
# edilmez — bu sabit yalnizca cok KUCUK komutlar icin bir TABAN. Olmasaydi: motor
# bir komutu yerine getirirken kamera goruntusu henuz guncellenmez, o sure icindeki
# her kare AYNI bayat piksel hatasindan taze bir komut daha uretir — her biri hiz
# sinirinin icinde kalsa bile TOPLAMLARI gercek ihtiyacin katlarina cikar.
#
# 13.08 gece: ilk surum TAM tamamlanma suresini bekliyordu (`2*sqrt(mesafe/ivme)`,
# taban 0.10 sn) — sonuc: sicramaz oldu AMA "cok yavas, ortalamakta gec kaliyor"
# sikayeti geldi. NISAN_MESGUL_ORANI bu tam sureyi KISALTIR: hareketin TAMAMEN
# durmasini degil, GORULEBILIR olcude ilerlemesini bekler — daha az temkinli, daha
# akici. Salinim geri gelirse ilk yukseltilecek yer burasi (1.0'a dogru); "hala
# yavas" ise dusurulur. Taban da 0.10 -> 0.04 sn'ye indirildi (inference ~15 FPS'te
# zaten ~0.067 sn'de bir kare geliyor, bu tabanin pratikte etkisi kalmadi).
NISAN_MESGUL_ORANI = 0.4
NISAN_MIN_ARALIK = 0.04


class VideoThread(QThread):
    kare_hazir = Signal(QImage, dict)

    def __init__(self, inference_thread, veri, kaynak):
        super().__init__()
        self._calis = True
        self.estop = False
        self.asama = 3
        # Kare kaynagi (kamera.Kamera): ACMA/KAPAMA/SECME burada DEGIL, ana thread'de
        # Kamera nesnesinde. Bu thread yalniz en taze kareyi okur ve isler.
        self.kaynak = kaynak
        self.veri = veri
        self.inference_thread = inference_thread
        self._gui_mesgul = False
        self._hedef_son_gorulen = {}   # titresim onleme: {track_id: (son_gorulen_zaman, hedef_dict)}

    def kare_islendi(self):
        self._gui_mesgul = False

    def run(self):
        son_sira = None
        t_kamera, kamera_fps = time.perf_counter(), 0.0
        kare_vardi = False
        try:
            while self._calis:
                if not self.kaynak.aktif:
                    # Kamera yok / kapali: son karenin tespitleri ekranda asili kalmasin.
                    if kare_vardi:
                        kare_vardi = False
                        son_sira = None
                        algi.takip_sifirla()
                        self.inference_thread.nisanci.sifirla()
                        with self.veri.kilit:
                            self.veri.kare = None
                            self.veri.dets = []
                            self.veri.balonlar = []
                            self.veri.active_idx = -1
                    self.msleep(50)
                    continue

                if self._gui_mesgul:
                    self.msleep(3)
                    continue

                frame, sira = self.kaynak.oku(son_sira)
                if frame is None:
                    self.msleep(3)
                    continue
                son_sira = sira
                kare_vardi = True
                frame = frame.copy()           

                # Kamera FPS ölçümü
                now_k = time.perf_counter()
                dt_k = now_k - t_kamera
                t_kamera = now_k
                if dt_k > 0:
                    kamera_fps = 0.9 * kamera_fps + 0.1 * (1.0 / dt_k)

                # Fiziksel kameranin ayna efektini duzeltmek icin (sağ-sol tersligi)
                # frame = cv2.flip(frame, 1)  # KULLANICI ISTEGI UZERINE IPTAL EDILDI

                with self.veri.kilit:
                    self.veri.kare = frame
                    self.veri.kare_sira = sira
                    self.veri.kare_t = time.time()
                    self.veri.kamera_fps = kamera_fps
                    dets = list(self.veri.dets)
                    balonlar = list(self.veri.balonlar)
                    active_idx = self.veri.active_idx
                    fps = self.veri.fps
                    k_fps = self.veri.kamera_fps

                data = self._panel_verisi(dets, active_idx, fps, k_fps)
                data["dets"] = dets
                data["balonlar"] = balonlar
                data["active_idx"] = active_idx
                aktif = dets[active_idx] if 0 <= active_idx < len(dets) else None
                data["kirmizi_kaniti"] = bool(aktif and not aktif.get("hayalet")
                                               and aktif.get("anlik_kirmizi", False))
                data["estop"] = self.estop
                data["merkezde"] = getattr(self.veri, "merkezde", False)
                data["nisan_hata_px"] = getattr(self.veri, "nisan_hata_px", None)
                data["olu_bolge_px"] = getattr(self.veri, "olu_bolge_px", None)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
                self._gui_mesgul = True
                self.kare_hazir.emit(qimg, data)
        finally:
            pass

    def _panel_verisi(self, dets, active_idx, fps, kamera_fps=0.0):
        a3 = (self.asama == 3)
        hedefler = []
        simdi = time.time()
        goruldu = set()
        for i, d in enumerate(dets):
            aktif = (i == active_idx)
            if aktif and not self.estop:
                durum = "◉ Kilitli"
            elif a3 and d["tip"] == "Dost":
                durum = "Dost — geç"
            else:
                durum = "Bekliyor"
            h = {"ad": d["ad"], "tip": d["tip"], "durum": durum, "aktif": aktif,
                              "id": d.get("id"), "cls": d.get("cls")}
            hedefler.append(h)
            tid = d.get("id")
            if tid is not None:
                goruldu.add(tid)
                self._hedef_son_gorulen[tid] = (simdi, h)
        # Titresim onleme: Son 0.7 sn icinde gorulen ama bu karede olmayan hedefleri tut
        TOLERANS = 0.7
        for tid, (t, eski_h) in list(self._hedef_son_gorulen.items()):
            if tid not in goruldu:
                if simdi - t < TOLERANS:
                    hayalet = dict(eski_h)
                    hayalet["aktif"] = False
                    hedefler.append(hayalet)
                else:
                    del self._hedef_son_gorulen[tid]
        # Liste daima Fuze->Helikopter->F16->IHA sirasinda (HEDEF_ONCELIK); tespit sirasi
        # veya ekrandaki kutu sirasi bunu etkilemez. "aktif" (kilit) her ogeye kendi
        # sozlugunde bagli oldugu icin sondan sonraya tasinsa bile kilit bilgisi kaybolmaz.
        hedefler.sort(key=lambda hh: HEDEF_ONCELIK.get(hh["cls"], len(HEDEF_ONCELIK)))
        active = None
        if active_idx >= 0 and not self.estop:
            try:
                d = dets[active_idx]
                active = {"ad": d["ad"], "tip": d["tip"], "conf": d["conf"], "box": d["box"]}
            except IndexError:
                pass
        if self.estop:
            mesaj = "ACİL DURDURULDU — ateş ve kilit kesildi"
        elif time.time() < algi._kilitleme_yasagi_t:
            kalan = int(algi._kilitleme_yasagi_t - time.time())
            mesaj = f"İmha tamamlandı. Jüri onayı bekleniyor... ({kalan} sn)"
        elif active:
            mesaj = f"{active['ad']} kilitlendi — %{active['conf']} güven"
        else:
            mesaj = "Hedef aranıyor…"
        return {"active": active, "hedefler": hedefler, "mesaj": mesaj, "fps": fps, "kamera_fps": kamera_fps, "a3": a3}

    def durdur(self):
        self._calis = False


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
        # Motor hiz duzeyi (ESP32'deki iki step motorun tavan hizi). Her iki modda da
        # gecerli oldugu icin manuel panelde DEGIL, sag kolonun altinda durur.
        self.hiz_seviye = P.HIZ_VARSAYILAN
        self._nisan_son_t = None   # otonom PD komutlari icin hiz-siniri zamanlayicisi
        self._nisan_mesgul_ta = 0.0   # bu zamana kadar yeni otonom komutu KABUL EDILMEZ
        self._pan_takip = HK.EksenTakip(isaret=+1.0,
                                        bosluk=algi.AYAR.get("takip_bosluk", 0.8))
        self._tilt_takip = HK.EksenTakip(isaret=-1.0,
                                         bosluk=algi.AYAR.get("takip_bosluk", 0.8))
        self._acilis_yukselisi = False
        self._acilis_yukselisi_bekliyor = False
        self._otonom_ates_aktif = False
        self._otonom_hedef_merkezde_t = None
        self._otonom_ates_bitis_t = None
        # Lazer gucu (%). Her acilista GUVENLI VARSAYILANA doner — kalici olarak
        # kaydedilmez: "gecen sefer %100'de birakmisiz" diye baslamak istemeyiz.
        self.lazer_guc = P.LAZER_GUC_VARSAYILAN
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

        uh.addWidget(self._sol_kolon(), 6)
        uh.addWidget(self._sag_kolon(), 3)
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
        self.live_badge.setVisible(False)
        self.live_blink_state = True
        self.live_blink_timer = QTimer(self)
        self.live_blink_timer.setInterval(550)
        self.live_blink_timer.timeout.connect(self._live_blink_tick)

        # Kontrol katmani (mock-ESP32 varsayilan; DERINMAVI_ESP env ile gercek porta gecilir)
        self.kontrol = kontrol_mod.Kontrol()
        if self.kontrol.bagli:
            etiket = "· mock (simülasyon)" if self.kontrol.mock_mu else f"· {self.kontrol.kaynak}"
            self._ci("ESP32", AMB if self.kontrol.mock_mu else GRN, etiket)
            self._ci("Seri Port", AMB if self.kontrol.mock_mu else GRN, "· 115200 baud")
            # Motor hizi SABIT (arayuzde secim yok — takim karari 22.09); karta acilista
            # bir kez bildirilir. Basili tutma/gamepad/otonom hiz siniri da bundan turer.
            self._esp_goster(self.kontrol.hiz_ayarla(self.hiz_seviye))
            # ESP32 durum yoklamasi: motorlar hedefe YURURKEN konum, lazer ve (varsa)
            # DONANIMSAL E-Stop yalnizca boyle gorulur — komut gonderilmedigi surece
            # arayuz kartin durumunu ogrenemez. Bos komut hicbir seyi degistirmez.
            self.esp_timer = QTimer(self)
            self.esp_timer.timeout.connect(self._esp_yokla)
            # Periyot ATES TAZELEMESINI de belirler: bu dongu durursa kart lazeri keser.
            self.esp_timer.start(P.ATES_TAZELE_MS)
            if self.kontrol.tilt_ayri:
                self.tilt_timer = QTimer(self)
                self.tilt_timer.timeout.connect(self.kontrol.tilt.yokla)
                self.tilt_timer.start(100)
        elif self.kontrol.hata:
            self._ci("ESP32", BD2, "· hata")

        # USB GAMEPAD — manuel kontrolun ucuncu girdisi (sartname Yetenek 1: UI/joystick/
        # klavye). Cihaz yoksa timer yine calisir ve periyodik tarar: gamepad uygulama
        # acikken takilabilmeli (yarisma gunu kablo cikip takilir).
        self.gamepad = gamepad_mod.Gamepad()
        self._gp_son_t = time.time()
        self._gp_tarama = 0
        self._gamepad_durum_yaz()
        self.gp_timer = QTimer(self)
        self.gp_timer.timeout.connect(self._gamepad_tik)
        self.gp_timer.start(self.TEKRAR_PERIYOT_MS)   # D-pad tekrariyla ayni tempo

        # algi thread (3-thread architecture)
        self.veri = OrtakVeri()
        
        self.inference_thread = InferenceThread(self.veri)
        self.inference_thread.asama = self.ASAMA_IDX[self.asama]
        self.inference_thread.otonom = (self.mod == "Otonom")
        self.inference_thread.model_bilgi.connect(self._model_bilgi_geldi)
        self.inference_thread.nisan_komut.connect(self._nisan_geldi)
        self.inference_thread.takip_olcum.connect(self._takip_olcum_geldi)
        self.inference_thread.kamera_acisi_fn = self._kamera_acilari
        self.inference_thread.start()
        
        # Kamera: YALNIZ harici (USB-C). Ana thread'de yasar (Qt kamera nesneleri
        # burada olmali); VideoThread kareyi ondan okur. Takilinca/cikarilinca kendi
        # guncellenir (kamera.Kamera._liste_guncelle).
        self.kamera = kamera_mod.Kamera(self)
        self.kamera.istenen = (1280, 720, int(algi.AYAR.get("kamera_fps", 30)))
        self.kamera.durum.connect(self._durum_geldi)
        self.kamera.liste_degisti.connect(self._kameralar_geldi)

        self.thread = VideoThread(self.inference_thread, self.veri, self.kamera)
        self.thread.asama = self.ASAMA_IDX[self.asama]
        self.thread.kare_hazir.connect(self._kare_geldi)
        self.thread.start()
        self.kamera.baslat()

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

        # Logo + "DERİN MAVİ" + "Hava Savunma Sistemi"
        brand_w = QWidget()
        bh = QHBoxLayout(brand_w)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(10)
        logo = QLabel()
        logo_path = os.path.join(HERE, "Grafik", "logo-mKXFEkR2.png")
        pm = QPixmap(logo_path)
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(36, Qt.SmoothTransformation))
        bh.addWidget(logo, 0, Qt.AlignVCenter)

        brand_text_v = QVBoxLayout()
        brand_text_v.setSpacing(0)
        brand_title = QLabel("DERİN MAVİ")
        brand_title.setObjectName("brand")
        brand_sub = QLabel("Hava Savunma Sistemi")
        brand_sub.setObjectName("brandtxt")
        brand_text_v.addWidget(brand_title)
        brand_text_v.addWidget(brand_sub)
        bh.addLayout(brand_text_v)
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
        krh.setSpacing(6)
        self.kam_sec = SecimKutusu()
        self.kam_sec.setObjectName("camsel")
        self.kam_sec.setMinimumWidth(190)      # 'Kamera bulunamadı' / uzun adlar kesilmesin
        self.kam_sec.addItem("Kamera aranıyor…", None)
        self.kam_sec.currentIndexChanged.connect(self._kamera_sec)
        krh.addWidget(self.kam_sec, 0, Qt.AlignVCenter)

        self.res_sec = SecimKutusu()
        self.res_sec.setObjectName("camsel")
        self.res_sec.setMinimumWidth(112)      # "1280x720" + ok
        self.res_sec.addItem("Çözünürlük", None)
        self.res_sec.currentIndexChanged.connect(self._res_sec)
        krh.addWidget(self.res_sec, 0, Qt.AlignVCenter)

        # CANLI rozeti: nokta + yazi TEK bir kapsul icinde. Eskiden ikisi ayri
        # widget'ti ve yalnizca nokta gizleniyordu — kamera KAPALI iken bile
        # bos bir "CANLI" yazisi duruyordu (yaniltici). Artik rozet butun olarak
        # gorunur/gizlenir.
        self.live_badge = QFrame()
        self.live_badge.setObjectName("livebadge")
        lb = QHBoxLayout(self.live_badge)
        lb.setContentsMargins(8, 3, 9, 3)
        lb.setSpacing(5)
        self.live_dot = QLabel()
        self.live_dot.setFixedSize(7, 7)
        self.live_dot.setStyleSheet(T.nokta(T.KIRMIZI, 7))
        self.live_lbl = QLabel("CANLI")
        self.live_lbl.setObjectName("livet")
        lb.addWidget(self.live_dot, 0, Qt.AlignVCenter)
        lb.addWidget(self.live_lbl, 0, Qt.AlignVCenter)
        krh.addWidget(self.live_badge, 0, Qt.AlignVCenter)
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
            b.clicked.connect(lambda checked=False, a=ad: cb(a))
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
            d.setStyleSheet(T.nokta(T.L3, 6))
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
        self.ayar_kapat_btn.clicked.connect(self._ayar_kapat)
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

        # Uc grup: TESPIT (YOLO/ByteTrack), SAHI (dilimli cikarim) ve NISAN (gimbal).
        # Gruplar hangi ayarin neyi etkiledigini bir bakista gosterir.
        for baslik, tanimlar in (("TESPİT", AYAR_TANIM_TESPIT),
                                 ("SAHI (Uzak Nesne)", AYAR_TANIM_SAHI),
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
        kaydir.setMaximumHeight(520)   # satirlar Apple olculerinde buyudu, daha fazlasi sigsin
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
        key, baslik, tip, mn, mx, aciklama = tanim
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

        if tip == "anahtar":
            sw = AppleSwitch(checked=bool(algi.AYAR[key]))
            sw.oneri_val = self._slider_birimi(algi.VARSAYILAN_AYAR[key], tip)
            sw.toggled.connect(lambda chk, k=key, t=tip, d=deger, s=sw: self._ayar_degisti(k, t, 1 if chk else 0, d, s))
            ust.addWidget(deger)
            ust.addWidget(sw)
            kutu.addLayout(ust)
            layout.addLayout(kutu)
            self.ayar_sliderlar[key] = (sw, tip)
            self._ayar_degisti(key, tip, sw.value(), deger, sw)
            return

        ust.addWidget(deger)
        kutu.addLayout(ust)

        sl = QSlider(Qt.Horizontal)
        if tip == "secim":
            sl.setMinimum(0)
            sl.setMaximum(len(COZUNURLUK_SECENEK) - 1)
        elif tip == "secim_sahi":
            sl.setMinimum(0)
            sl.setMaximum(len(SAHI_DILIM_SECENEK) - 1)
        else:
            sl.setMinimum(mn)
            sl.setMaximum(mx)
        sl.setValue(self._slider_birimi(algi.AYAR[key], tip))
        # "Onerilen" (yesil) isaret = ALGI'NIN VARSAYILANI. Tek kaynak orasi; burada
        # ikinci bir kopya tutulsaydi varsayilan degisince yesil isaret sessizce yalan soylerdi.
        sl.oneri_val = self._slider_birimi(algi.VARSAYILAN_AYAR[key], tip)
        sl.setObjectName("ayarsl")
        sl.valueChanged.connect(lambda val, k=key, t=tip, d=deger, s=sl: self._ayar_degisti(k, t, val, d, s))
        if key == "kamera_fps":
            sl.sliderReleased.connect(self._fps_degistirildi)
        kutu.addWidget(sl)

        layout.addLayout(kutu)
        self.ayar_sliderlar[key] = (sl, tip)
        self._ayar_degisti(key, tip, sl.value(), deger, sl)

    def _fps_degistirildi(self):
        """FPS degistirildikten (slider birakildiktan) sonra kamerayi yeni ayarlarla yeniden baslatir."""
        w, h, _ = self.kamera.istenen
        self.kamera.istenen = (w, h, int(algi.AYAR.get("kamera_fps", 30)))
        self.kamera.yeniden_ac()

    # --- ayar deger donusumleri: slider tam sayidir, ayar degeri olcekli olabilir ---
    def _slider_birimi(self, v, tip):
        """Bir ayar degerini slider tam sayisina cevirir (algi.AYAR ve VARSAYILAN_AYAR icin)."""
        if tip == "secim":
            # Kayitli cozunurluk listede yoksa en yakinina yuvarla (bozuk ayarlar.json)
            if int(v) in COZUNURLUK_SECENEK:
                return COZUNURLUK_SECENEK.index(int(v))
            return min(range(len(COZUNURLUK_SECENEK)),
                       key=lambda i: abs(COZUNURLUK_SECENEK[i] - int(v)))
        if tip == "secim_sahi":
            if int(v) in SAHI_DILIM_SECENEK:
                return SAHI_DILIM_SECENEK.index(int(v))
            return min(range(len(SAHI_DILIM_SECENEK)),
                       key=lambda i: abs(SAHI_DILIM_SECENEK[i] - int(v)))
        if tip == "yuzde":
            return int(round(float(v) * 100))
        if tip == "onda":
            return int(round(float(v) * 10))
        return int(v)                                  # "kare", "sayi", "anahtar"

    def _ayar_gercek_deger(self, tip, val):
        """Slider tam sayisini algi.AYAR degerine cevirir."""
        if tip == "secim":
            return COZUNURLUK_SECENEK[val]
        if tip == "secim_sahi":
            return SAHI_DILIM_SECENEK[val]
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
        elif tip == "secim_sahi":
            lbl.setText(f"{SAHI_DILIM_SECENEK[val]} px")
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
        """Kaydirici onerilen degerdeyse YESIL, degistirilmisse MOR gorunur."""
        if sl is None:
            return
        if isinstance(sl, AppleSwitch):
            if deger_lbl:
                onerilen = (val == getattr(sl, "oneri_val", None))
                deger_lbl.setStyleSheet(ETIKET_ONERI if onerilen else ETIKET_DEGISIK)
            return
        onerilen = (val == getattr(sl, "oneri_val", None))
        sl.setStyleSheet(SLIDER_ONERI if onerilen else SLIDER_DEGISIK)
        if deger_lbl:
            deger_lbl.setStyleSheet(
                ETIKET_ONERI if onerilen else ETIKET_DEGISIK)

    def _ayar_kapat(self):
        self.ayar_panel.setVisible(False)
        self._odak_geri()                 # kaydirici odagi kalirsa klavye gimbal'a gitmez

    def _ayar_toggle(self):
        gorunur = not self.ayar_panel.isVisible()
        self.ayar_panel.setVisible(gorunur)
        if gorunur:
            self.ayar_panel.raise_()
        else:
            self._odak_geri()

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
                    self._ayar_kapat()
            except Exception:
                pass
        if (event.type() == QEvent.MouseButtonPress
                and getattr(self, "_acik_pencere", None) is not None):
            try:
                gp = event.globalPosition().toPoint()
                vp = self.view.viewport().mapFromGlobal(gp)
                sahne = self.view.mapToScene(vp).toPoint()
                ad = self._acik_pencere

                def _icinde2(w):
                    tl = w.mapTo(self.content, QPoint(0, 0))
                    return QRect(tl, w.size()).contains(sahne)

                # Tetik dugmesine tiklama kendi toggle'ina birakilir (cift islem olmasin).
                if not (_icinde2(self.pencereler[ad]) or _icinde2(self._pencere_tetik(ad))):
                    self._pencere_kapat()                 # disari tik = kaydetmeden kapat
            except Exception:
                pass
        # KLAVYE: arayuz bir QGraphicsView icinde cizildigi icin klavye odagi o
        # gorunumdedir ve gorunum OK TUSLARINI kendisi (kaydirma icin) yutar — ok
        # tuslari pencereye hic ulasmiyordu (W/A/S/D ulasiyordu cunku gorunum harfleri
        # kullanmaz). Bizim tuslarimizi gorunume gitmeden burada yakalariz.
        if (obj is getattr(self, "view", None)
                and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape):
            self._tus_bas(event)                       # ESC ates keser — odak nerede olursa olsun
            return True
        if (obj is getattr(self, "view", None)
                and event.type() in (QEvent.KeyPress, QEvent.KeyRelease)
                and not self._metin_girisi_odakta()):
            if event.type() == QEvent.KeyPress:
                if self._tus_bas(event):
                    return True
            elif self._tus_birak(event):
                return True
        return super().eventFilter(obj, event)

    def _odak_geri(self):
        """Odagi canli goruntuye geri verir.

        ⚠ GERCEK HATA (22.09): bir ayar kutucugundaki sayi kutusuna tiklayip kutucugu
        kapatinca odak GIZLENEN kutuda kaliyordu; Qt tus olaylarini odak bileşenine
        yolladigi icin W/A/S/D ve oklar gimbal'a hic ulasmiyordu — operatorun kontrolu
        sessizce oluyordu. Kapanan her panel/kutucuk odagi buradan geri verir."""
        gorunum = getattr(self, "view", None)
        if gorunum is not None:
            gorunum.setFocus(Qt.OtherFocusReason)

    def _metin_girisi_odakta(self):
        """Odak bir sayi/metin kutusundaysa (yasak alan Alt/Ust, lazer kaydiricisi)
        ok tuslari ONU ayarlamali, gimbal'i degil. GIZLI bir bileşen sayilmaz:
        kapanmis bir kutucugun kutusu klavyeyi rehin alamaz (yukaridaki nota bak)."""
        odak = self.content.focusWidget() if hasattr(self, "content") else None
        from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit
        if not isinstance(odak, (QAbstractSpinBox, QLineEdit, QSlider)):
            return False
        if not odak.isVisible():
            self._odak_geri()
            return False
        return True

    def _ayar_sifirla(self):
        algi.ayar_guncelle(**algi.VARSAYILAN_AYAR)
        for key, (sl, tip) in self.ayar_sliderlar.items():
            sl.setValue(self._slider_birimi(algi.AYAR[key], tip))

    def _ayar_dosya(self):
        return os.path.join(HERE, "ayarlar.json")

    def _ayar_yukle(self):
        p = self._ayar_dosya()
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                algi.ayar_guncelle(**{k: v for k, v in d.items() if k in algi.AYAR})
            except Exception:
                pass

    def _ayar_kaydet(self):
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
        v.setSpacing(8)

        # Aşama 2/3: hangi sınıflara otomatik kilit kurulacağını operatör belirler.
        # Tespit tablosu bütün sınıfları göstermeye devam eder.
        algi.hedef_tipleri_ayarla(None)
        tip_kart = QFrame()
        tip_kart.setObjectName("panelk")
        tip_lay = QHBoxLayout(tip_kart)
        tip_lay.setContentsMargins(10, 5, 10, 5)
        tip_lay.setSpacing(4)
        tip_lay.addWidget(QLabel("ARANAN"))
        self.tip_butonlari = {}
        for kanon, ad in (("fuze", "Füze"), ("helikopter", "Heli"),
                          ("f16", "F-16"), ("drone", "İHA")):
            btn = QPushButton(ad)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._tip_secimi_degisti)
            self.tip_butonlari[kanon] = btn
            tip_lay.addWidget(btn)
        self.tip_hepsi_lbl = QLabel("hepsi")
        tip_lay.addWidget(self.tip_hepsi_lbl)
        v.addWidget(tip_kart)

        hedef_kart = QFrame()
        hedef_kart.setObjectName("panelk")
        hedef_lay = QHBoxLayout(hedef_kart)
        hedef_lay.setContentsMargins(10, 3, 10, 3)
        hedef_lay.addWidget(QLabel("HEDEFLER"))
        self.hedef_scroll = QScrollArea()
        self.hedef_scroll.setWidgetResizable(True)
        self.hedef_scroll.setFrameShape(QFrame.NoFrame)
        self.hedef_scroll.setFixedHeight(34)
        self.hedef_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hedef_ic = QWidget()
        self.hedef_liste_lay = QHBoxLayout(hedef_ic)
        self.hedef_liste_lay.setContentsMargins(0, 0, 0, 0)
        self.hedef_liste_lay.setSpacing(4)
        self.hedef_scroll.setWidget(hedef_ic)
        hedef_lay.addWidget(self.hedef_scroll, 1)
        v.addWidget(hedef_kart)

        # Manuel ve Otonom modlar FARKLI paneller gosterir. QStackedWidget ile
        # gecis yapilir — setVisible() QGraphicsProxyWidget icinde guvenilir
        # degil (layout yeniden hesaplanmiyordu). Sayfa 0 = Manuel, Sayfa 1 = Otonom.
        self.sag_mod_stack = QStackedWidget()
        self.manuel_panel = self._manuel_kontrol_panel()
        self.otonom_panel = self._otonom_kontrol_panel()
        self.sag_mod_stack.addWidget(self.manuel_panel)   # 0 = Manuel
        self.sag_mod_stack.addWidget(self.otonom_panel)    # 1 = Otonom
        v.addWidget(self.sag_mod_stack, 1)


        return kol

    def _tip_secimi_degisti(self):
        secili = [tip for tip, btn in self.tip_butonlari.items() if btn.isChecked()]
        algi.hedef_tipleri_ayarla(secili)
        self.tip_hepsi_lbl.setText("hepsi" if not secili else f"{len(secili)} tip")

    def _hedef_liste_guncelle(self, hedefler, a3):
        lay = self.hedef_liste_lay
        while lay.count():
            oge = lay.takeAt(0).widget()
            if oge is not None:
                oge.deleteLater()
        for i, h in enumerate(hedefler):
            tid = h.get("id")
            etiket = f"{i + 1} · {h['ad']}"
            if a3:
                etiket = f"{i + 1} · {h['tip']} · {h['ad']}"
            btn = QPushButton(etiket)
            btn.setObjectName("hedefsatir")
            btn.setEnabled(tid is not None)
            btn.setToolTip("Hedefi elle kilitle / kilidi bırak")
            btn.setStyleSheet(T.yazi(T.CAGRI_VURGU,
                                    T.KIRMIZI if h["aktif"] else T.L2))
            btn.clicked.connect(lambda _=False, t=tid: self._hedef_secildi(t))
            lay.addWidget(btn)
        lay.addStretch(1)

    def _hedef_secildi(self, track_id):
        if track_id is None:
            return
        algi.hedef_sec(None if algi.kilitli_hedef() == track_id else track_id)

    def _otonom_kontrol_panel(self):
        """Otonom mod paneli — takip durumu, aktif hedef bilgisi ve nisan durumu."""
        mk = QFrame()
        mk.setObjectName("panelk")
        mv = QVBoxLayout(mk)
        mv.setContentsMargins(15, 8, 15, 8)
        mv.setSpacing(6)

        # Baslik
        mt = QLabel("OTONOM TAKİP DURUMU")
        mt.setObjectName("ph")
        mt.setStyleSheet(T.yazi(T.DIPNOT, T.L2, "padding-bottom: 4px;"))
        mv.addWidget(mt)

        # Takip durumu gostergesi (kilitli / araniyor / E-Stop)
        self.oto_durum_frame = QFrame()
        self.oto_durum_frame.setObjectName("engok")
        dh = QHBoxLayout(self.oto_durum_frame)
        dh.setContentsMargins(11, 7, 11, 7)
        dh.setSpacing(8)

        self.oto_durum_dot = QLabel()
        self.oto_durum_dot.setFixedSize(10, 10)
        self.oto_durum_dot.setStyleSheet(T.nokta(T.SARI, 10))
        dh.addWidget(self.oto_durum_dot)

        oto_sub = QVBoxLayout()
        oto_sub.setSpacing(1)
        self.oto_durum_baslik = QLabel("Hedef aranıyor…")
        self.oto_durum_baslik.setObjectName("engname")
        self.oto_durum_alt = QLabel("—")
        self.oto_durum_alt.setObjectName("engsub")
        oto_sub.addWidget(self.oto_durum_baslik)
        oto_sub.addWidget(self.oto_durum_alt)
        dh.addLayout(oto_sub, 1)
        mv.addWidget(self.oto_durum_frame)

        # Nisan (PD) durumu
        nisan_kart = QFrame()
        nisan_kart.setObjectName("altkart")
        nv = QVBoxLayout(nisan_kart)
        nv.setContentsMargins(12, 6, 12, 6)
        nv.setSpacing(3)
        nt = QLabel("NİŞAN KONTROLÜ")
        nt.setObjectName("ph")
        nv.addWidget(nt)

        self.oto_nisan_durum = QLabel("Bekleniyor")
        self.oto_nisan_durum.setStyleSheet(T.yazi(T.CAGRI, T.L3))
        nv.addWidget(self.oto_nisan_durum)

        self.oto_ates_kapi = QLabel("—")
        self.oto_ates_kapi.setStyleSheet(T.yazi(T.ALTBASLIK, T.L3))
        self.oto_ates_kapi.setWordWrap(True)
        nv.addWidget(self.oto_ates_kapi)

        # Aci bilgisi (pan/tilt)
        aci_row = QHBoxLayout()
        aci_row.setSpacing(16)
        self.oto_pan_lbl = QLabel("Azimut: 0.0°")
        self.oto_pan_lbl.setStyleSheet(T.yazi(T.CAGRI, T.L2, f"font-family:{T.FM};"))
        self.oto_tilt_lbl = QLabel("Yükseliş: 0.0°")
        self.oto_tilt_lbl.setStyleSheet(T.yazi(T.CAGRI, T.L2, f"font-family:{T.FM};"))
        aci_row.addWidget(self.oto_pan_lbl)
        aci_row.addWidget(self.oto_tilt_lbl)
        aci_row.addStretch(1)
        nv.addLayout(aci_row)

        mv.addWidget(nisan_kart)

        # Aktif gorev bilgisi
        gorev_kart = QFrame()
        gorev_kart.setObjectName("altkart")
        gv = QVBoxLayout(gorev_kart)
        gv.setContentsMargins(12, 6, 12, 6)
        gv.setSpacing(3)
        gt = QLabel("GÖREV BİLGİSİ")
        gt.setObjectName("ph")
        gv.addWidget(gt)

        self.oto_gorev_lbl = QLabel("Aşama seçilmedi")
        self.oto_gorev_lbl.setStyleSheet(T.yazi(T.CAGRI, T.L3))
        self.oto_gorev_lbl.setWordWrap(True)
        gv.addWidget(self.oto_gorev_lbl)

        mv.addWidget(gorev_kart)

        # Bolge durumu (otonom icin de)
        self.oto_bolge_status = QLabel("● BÖLGE GÜVENLİ")
        self.oto_bolge_status.setAlignment(Qt.AlignCenter)
        self.oto_bolge_status.setStyleSheet(T.durum_bandi(T.YESIL))
        mv.addWidget(self.oto_bolge_status)

        # Otonom ATES bilgisi — buton YOK ama lazer durumu gosterilir.
        # Bosluk (stretch) EN SONA konur: daha once lazer durumunun ustundeydi ve
        # panelin ortasinda hicbir sey anlatmayan genis bir bosluk biriktiriyordu.
        self.oto_lazer_durum = QLabel("○ Lazer kapalı")
        self.oto_lazer_durum.setAlignment(Qt.AlignCenter)
        self.oto_lazer_durum.setStyleSheet(T.yazi(T.GOVDE_VURGU, T.L3))
        mv.addWidget(self.oto_lazer_durum)
        mv.addStretch(1)

        return mk

    def _lazer_bilgi_yaz(self):
        """Lazer durumunun EKRANDAKI tek kapisi: LAZER kartinin basligi + aci
        karolarindaki kirmizi isik. Kaynak kontrol katmani (kartla eslenmis):
        E-Stop, kart resetleri ve ATES/KES hepsi `kontrol.lazer_acik`'e yansir.
        Sistem bagli degilse isik ASLA yanmaz — arayuz tahmin etmez."""
        acik = bool(getattr(self, "kontrol", None)
                    and self.kontrol.bagli and self.kontrol.lazer_acik)
        for karo in (getattr(self, "arac_ikon", None), getattr(self, "arac_yon_ikon", None)):
            if karo is not None:
                karo.lazer_ayarla(acik)

    def _lazer_guc_degisti(self, deger):
        """Guc degisiminin TEK UYGULAMA kapisi — yalniz ONAYDAN sonra cagrilir
        (lazer sayfasindaki kaydirici/kademeler sadece TASLAGI degistirir)."""
        deger = P.guc_kirp(deger)
        if deger == self.lazer_guc:
            return                              # ayni deger: hatta bos komut dolasmasin
        self.lazer_guc = deger
        self._lazer_taslak_ayarla(deger)        # sayfa da uygulanan degeri gostersin
        self._lazer_bilgi_yaz()
        if getattr(self, "kontrol", None) and self.kontrol.bagli:
            self._esp_goster(self.kontrol.guc_ayarla(deger))
            self.sb_msg.setText(f'<span style="color:{RED}">●</span>&nbsp;'
                                f'Lazer gücü: %{deger}')

    # ================= MANUEL YÖN VE NİŞAN KONTROLÜ =================
    def _manuel_kontrol_panel(self):
        """Manuel mod paneli. Ic stack: 0 = D-pad kontrolleri, 1 = aci/yasak alan ayarlari."""
        mk = QFrame()
        mk.setObjectName("panelk")
        mv = QVBoxLayout(mk)
        mv.setContentsMargins(16, 10, 16, 10)
        mv.setSpacing(6)

        # Baslik + "Aci Ayarlari" butonu
        brow = QHBoxLayout()
        mt = QLabel("MANUEL KONTROL")    # kisa: yaninda iki yasak alan kapsulu var
        mt.setObjectName("ph")
        mt.setStyleSheet(T.yazi(T.DIPNOT, T.L2, "padding-bottom: 4px;"))
        brow.addWidget(mt, 1)
        # Yasak alanlar (sartname §4.2): minimal kapsul = ad + anahtar. Anahtar alani
        # acar/kapar; kapsulun kendisine tiklamak o alanin Yatay/Dikey ayarini acar.
        self.yasak_dugme = {}
        for tur, ad in (("atis", "Atışa Yasak"), ("hareket", "Harekete Yasak")):
            self.yasak_dugme[tur] = self._yasak_kapsulu(tur, ad)
            brow.addWidget(self.yasak_dugme[tur][0], 0)
        mv.addLayout(brow)

        self._aci_durum_baslat()

        mv.addWidget(self._dpad_sayfasi(), 1)
        # Ayarlar AYRI SAYFA degil: tiklanan dugmenin yaninda acilan KUTUCUK (opak;
        # yari saydam denendi, arkadaki yazilar okunmayi bozuyordu).
        # Alttaki panel yerinde kalir (22.09 takim karari). Kutucuklar icerik
        # tuvalinin (self.content) cocugudur ki panelin ustune binebilsin.
        self.bolge_spin = {}
        self._acik_pencere = None
        self.pencereler = {"atis": self._bolge_sayfasi("atis"),
                           "hareket": self._bolge_sayfasi("hareket"),
                           "lazer": self._lazer_sayfasi()}
        for w in self.pencereler.values():
            w.setParent(self.content)
            w.setVisible(False)
        self._bolge_uygula()                                               # ilk yansitma
        return mk

    # ---- ayar kutucugu (popover) ----
    def _pencere_tetik(self, ad):
        """Kutucugu acan dugme — konum ve 'disari tiklama' denetimi icin."""
        if ad == "lazer":
            return self.lazer_ayar_btn
        return self.yasak_dugme[ad][0]

    def _pencere_ac(self, ad):
        """Kutucugu tetik dugmesine yaslayarak acar. Yasak alan kutucuklari
        kapsulun ALTINDA (sag kenari hizali), lazer kutucugu ATEŞ'in USTUNDE."""
        if self._acik_pencere and self._acik_pencere != ad:
            self._pencere_kapat()
        self._acik_pencere = ad
        self._pencere_yerlestir()

    def _pencere_yerlestir(self):
        """Acik kutucugu boyuna gore yeniden konumlar ve camini tazeler (lazer onay
        satiri acilinca kutu buyur — cam da, konum da ona uymali)."""
        ad = self._acik_pencere
        w, tetik = self.pencereler[ad], self._pencere_tetik(ad)
        w.adjustSize()
        tl = tetik.mapTo(self.content, QPoint(0, 0))
        if ad == "lazer":
            x, y = tl.x() - 6, tl.y() - w.height() - 10
        else:
            x, y = tl.x() + tetik.width() - w.width(), tl.y() + tetik.height() + 6
        x = max(8, min(x, self.content.width() - w.width() - 8))
        y = max(8, min(y, self.content.height() - w.height() - 8))
        w.move(x, y)
        w.setVisible(True)
        w.raise_()

    def _pencere_kapat(self):
        """Acik kutucugu KAYDETMEDEN kapatir: taslak/kutular kayitli degere doner."""
        ad, self._acik_pencere = self._acik_pencere, None
        if ad is None:
            return
        self.pencereler[ad].setVisible(False)
        self._odak_geri()
        if ad == "lazer":
            self._lazer_taslak_ayarla(self.lazer_guc)
            self._lazer_vazgec()
        else:
            self._bolge_kutulari_yenile()

    def _aci_durum_baslat(self):
        """Gimbal aci durumu ve yasak alan sinirlari (arayuz tarafindaki tek kaynak)."""
        self.pan_aci = 0.0            # azimut, 0-360 (EKRAN icin sarmali)
        self.pan_ham = 0.0
        self.tilt_aci = 0.0           # operator acisi, -30..+30; 0 yatay
        self.max_tilt_limit = (B.TILT_CALISMA_MAX if P.TILT_MAX >= B.TILT_CALISMA_MAX
                               else float(P.TILT_MAX))
        self.aci_adim = 1.0           # tek dokunus = 1° (sabit; arayuzde secim yok — 22.09)

        # Harekete / atisa IZINLI pencereler (disi yasak). Birimler ve kurallar:
        # app/bolge.py. Ayarlar ⚙ Aci Ayarlari panelinden gelir.
        self.bolge = B.Bolgeler()

        self._basili_yonler = set()
        self._son_tekrar_t = 0.0
        self._tekrar_gecikme = QTimer(self)
        self._tekrar_gecikme.setSingleShot(True)
        self._tekrar_gecikme.timeout.connect(self._tekrar_baslat)
        self._tekrar_timer = QTimer(self)
        self._tekrar_timer.setInterval(self.TEKRAR_PERIYOT_MS)
        self._tekrar_timer.timeout.connect(self._tekrar_tik)

        # Klavyeden ATES: [Space]+[B] birlikte ATES_KURMA_MS basili tutulmali. Kaza
        # ile tek tusa basmak lazeri acmasin diye kasitli olarak zor bir hareket.
        self._kol_ui, self._kol_gp = set(), set()   # kol gostergesindeki isik kaynaklari
        # Merkeze alma: kademeli yurutme + "basili tut" sayaci (MERKEZ butonu, L1/R1)
        self._merkez_calisiyor = False
        self._merkez_son_t = 0.0
        self._merkez_timer = QTimer(self)
        self._merkez_timer.setInterval(self.TEKRAR_PERIYOT_MS)
        self._merkez_timer.timeout.connect(self._merkez_tik)
        self._merkez_kurma_kim = None              # sayaci baslatan kaynak ("ui"/"kol")
        self._merkez_kurma = QTimer(self)
        self._merkez_kurma.setSingleShot(True)
        self._merkez_kurma.timeout.connect(self._merkez_kurma_bitti)
        self._ates_tuslari = set()
        self._ates_kurma_kaynak = None             # "klavye" | "kol"
        self._gp_ates_basili = False               # kolun iki tetigi su an basili mi
        self._ates_kurma = QTimer(self)
        self._ates_kurma.setSingleShot(True)
        self._ates_kurma.timeout.connect(self._ates_kurma_bitti)

    # ---- Ic sayfa 0: D-pad ----
    def _dpad_sayfasi(self):
        sayfa = QWidget()
        dv = QVBoxLayout(sayfa)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(4)
        dv.addWidget(self._aci_gostergesi())

        self.bolge_status = QLabel("● BÖLGE GÜVENLİ")
        self.bolge_status.setObjectName("bolgestatus")
        self.bolge_status.setAlignment(Qt.AlignCenter)
        self.bolge_status.setStyleSheet(T.durum_bandi(T.YESIL))
        dv.addWidget(self.bolge_status)

        self.kol_ikon = KI.KolGostergesi()
        self.kol_ikon.setFixedSize(150, 112)
        satir = QHBoxLayout()
        satir.setSpacing(14)
        satir.addStretch(1)
        satir.addWidget(self._dpad_izgarasi(), 0, Qt.AlignVCenter)
        satir.addWidget(self.kol_ikon, 0, Qt.AlignVCenter)
        satir.addStretch(1)
        dv.addLayout(satir)
        dv.addLayout(self._ates_satiri())
        dv.addStretch(1)                               # artan yer en altta kalir
        return sayfa

    def _ates_satiri(self):
        """ATEŞ butonu; lazer gucu ⚙'i butonun ICINDE, solda. ⚙ ayri bir cocuk
        butondur: tiklamasi onda kalir, ATESE GITMEZ (cocuk olayi once alir)."""
        satir = QHBoxLayout()
        fire = self._ates_butonu()
        ic = QHBoxLayout(fire)
        ic.setContentsMargins(4, 4, 4, 4)
        self.lazer_ayar_btn = QPushButton("⚙", fire)
        self.lazer_ayar_btn.setObjectName("lazerayar")
        self.lazer_ayar_btn.setFixedSize(T.ATES_BOY - 10, T.ATES_BOY - 10)
        self.lazer_ayar_btn.setCursor(Qt.PointingHandCursor)
        self.lazer_ayar_btn.setToolTip("Lazer gücü")
        self.lazer_ayar_btn.setFocusPolicy(Qt.NoFocus)
        self.lazer_ayar_btn.clicked.connect(self._lazer_sayfasi_ac)
        ic.addWidget(self.lazer_ayar_btn, 0, Qt.AlignVCenter)
        ic.addStretch(1)
        satir.addWidget(fire, 1)
        return satir

    def _lazer_sayfasi(self):
        """Lazer gucu: kaydirici + kademeler TASLAK uzerinde calisir; KAYDET onay
        ister, ancak 'Değiştir' ile karta gider. ✕ taslagi atar."""
        sayfa = QFrame()
        sayfa.setObjectName("ayarpanel")     # goruntu isleme paneliyle ayni opak zemin
        sayfa.setFixedWidth(self.CAM_KUTU_EN)
        v = QVBoxLayout(sayfa)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        bas = QHBoxLayout()
        baslik = QLabel("Lazer Gücü")
        baslik.setObjectName("ayartitle")
        self.lazer_taslak_lbl = QLabel()
        self.lazer_taslak_lbl.setObjectName("ayardeg")
        kapat = QPushButton("✕")
        kapat.setObjectName("ayarclose")
        kapat.setCursor(Qt.PointingHandCursor)
        kapat.clicked.connect(self._lazer_sayfasi_kapat)
        bas.addWidget(baslik, 1)
        bas.addWidget(self.lazer_taslak_lbl, 0)
        bas.addWidget(kapat, 0)
        v.addLayout(bas)

        self.lazer_sl = QSlider(Qt.Horizontal)
        self.lazer_sl.setObjectName("ayarsl")
        self.lazer_sl.setMinimum(P.LAZER_GUC_MIN)
        self.lazer_sl.setMaximum(P.LAZER_GUC_MAX)
        self.lazer_sl.setSingleStep(5)
        self.lazer_sl.setPageStep(10)
        self.lazer_sl.setStyleSheet(SLIDER_DEGISIK)
        self.lazer_sl.valueChanged.connect(self._lazer_taslak_ayarla)
        v.addWidget(self.lazer_sl)
        kapsul, self.lazer_btns = self._seviye_butonlari(
            [(20, "%20"), (40, "%40"), (70, "%70"), (100, "%100")],
            self.lazer_guc, self._lazer_taslak_ayarla)
        v.addWidget(kapsul)

        # onay satiri (Kaydet'e basinca gorunur)
        self.lazer_onay = QWidget()
        oh = QHBoxLayout(self.lazer_onay)
        oh.setContentsMargins(0, 0, 0, 0)
        oh.setSpacing(8)
        self.lazer_onay_lbl = QLabel()
        self.lazer_onay_lbl.setObjectName("ayarlbl")
        self.lazer_onay_lbl.setWordWrap(True)
        vazgec = QPushButton("Vazgeç")
        vazgec.setObjectName("ayaralt")
        vazgec.setCursor(Qt.PointingHandCursor)
        vazgec.clicked.connect(self._lazer_vazgec)
        degistir = QPushButton("Değiştir")
        degistir.setObjectName("ayarkaydet")
        degistir.setCursor(Qt.PointingHandCursor)
        degistir.clicked.connect(self._lazer_onayla)
        oh.addWidget(self.lazer_onay_lbl, 1)
        oh.addWidget(vazgec, 0)
        oh.addWidget(degistir, 0)
        self.lazer_onay.setVisible(False)
        v.addWidget(self.lazer_onay)

        self.lazer_kaydet_btn = QPushButton("Kaydet")
        self.lazer_kaydet_btn.setObjectName("ayarkaydet")
        self.lazer_kaydet_btn.setCursor(Qt.PointingHandCursor)
        self.lazer_kaydet_btn.clicked.connect(self._lazer_kaydet_iste)
        alt = QHBoxLayout()
        alt.addStretch(1)
        alt.addWidget(self.lazer_kaydet_btn)
        v.addLayout(alt)
        self._lazer_taslak_ayarla(self.lazer_guc)
        return sayfa

    def _lazer_taslak_ayarla(self, deger):
        """Sayfadaki TASLAK guc (karta gitmez). Kaydirici/kademe/etiket esitlenir."""
        self.lazer_taslak = P.guc_kirp(deger)
        sl = getattr(self, "lazer_sl", None)
        if sl is not None and sl.value() != self.lazer_taslak:
            sl.blockSignals(True)
            sl.setValue(self.lazer_taslak)
            sl.blockSignals(False)
        for v, b in getattr(self, "lazer_btns", {}).items():
            b.setChecked(v == self.lazer_taslak)
        if hasattr(self, "lazer_taslak_lbl"):
            self.lazer_taslak_lbl.setText(f"%{self.lazer_taslak}")

    def _lazer_sayfasi_ac(self):
        if self._acik_pencere == "lazer":
            self._lazer_sayfasi_kapat()
            return
        self._lazer_taslak_ayarla(self.lazer_guc)       # her acilis KAYITLI degerle
        self._lazer_vazgec()
        self._pencere_ac("lazer")

    def _lazer_sayfasi_kapat(self):
        """Onaysiz kapatma: taslak ATILIR."""
        if self._acik_pencere == "lazer":
            self._pencere_kapat()

    def _lazer_kaydet_iste(self):
        """KAYDET: deger degismediyse kapat; degistiyse ONAY iste (karta henuz gitmez)."""
        if self.lazer_taslak == self.lazer_guc:
            self._lazer_sayfasi_kapat()
            return False
        self.lazer_onay_lbl.setText(
            f"Lazer gücü %{self.lazer_guc} → %{self.lazer_taslak} olacak. Emin misiniz?")
        self.lazer_onay.setVisible(True)
        self.lazer_kaydet_btn.setVisible(False)
        if self._acik_pencere == "lazer":
            self._pencere_yerlestir()
        return True

    def _lazer_vazgec(self):
        if hasattr(self, "lazer_onay"):
            self.lazer_onay.setVisible(False)
            self.lazer_kaydet_btn.setVisible(True)
            if getattr(self, "_acik_pencere", None) == "lazer":
                self._pencere_yerlestir()

    def _lazer_onayla(self):
        """'Değiştir': taslak karta GIDER (tek uygulama kapisi) ve sayfa kapanir."""
        self._lazer_guc_degisti(self.lazer_taslak)
        self._lazer_sayfasi_kapat()

    def _ates_butonu(self):
        """ATES butonu — Apple Glass High-Impact Action Button."""
        self.fire_btn = QPushButton(ATES_METIN_KAPALI)
        self.fire_btn.setObjectName("fire")
        self.fire_btn.setFixedHeight(T.ATES_BOY)      # XL'den biraz buyuk kapsul (22.09)
        self.fire_btn.setCheckable(True)
        self.fire_btn.setCursor(Qt.PointingHandCursor)
        self.fire_btn.setToolTip("[L] — ateşi aç / kes")
        self.fire_btn.clicked.connect(self._ates_bas)
        return self.fire_btn

    def _aci_gostergesi(self):
        """Azimut + yukselis: iki ESIT karo (ust / yan gorunus), buyuk ortali derece.
        Baslik yazisi YOK (takim karari 21.09): resim neyi gosterdigini zaten anlatiyor."""
        kutu = QFrame()
        kutu.setObjectName("angtgl")
        gh = QHBoxLayout(kutu)
        gh.setContentsMargins(8, 6, 8, 4)
        gh.setSpacing(8)

        self.arac_yon_ikon = AracYonGostergesi()    # sol: azimut (ust gorunus)
        self.arac_ikon = AracAciGostergesi()        # sag: yukselis (yan gorunus)
        # 270 px sabit (takim karari 22.09: esneyen 390 px'lik hal ~%30 kucultuldu).
        for karo in (self.arac_yon_ikon, self.arac_ikon):
            karo.setFixedHeight(270)
            karo.setMinimumWidth(140)
        self.pan_val_lbl = self.arac_yon_ikon.deger
        self.tilt_val_lbl = self.arac_ikon.deger

        ayirac = QFrame()
        ayirac.setObjectName("vdiv")
        ayirac.setFixedWidth(1)
        gh.addWidget(self.arac_yon_ikon, 1)          # esit esneme -> esit karo
        gh.addWidget(ayirac)
        gh.addWidget(self.arac_ikon, 1)
        return kutu

    def _pan_goster(self):
        """Azimutun EKRANDAKI tek kapisi: sayi etiketi + ust gorunus ikonu birlikte."""
        self.pan_val_lbl.setText(f"{self.pan_aci:.1f}°")
        ikon = getattr(self, "arac_yon_ikon", None)
        if ikon is not None:
            ikon.aci_ayarla(self.pan_aci)

    def _tilt_goster(self):
        """Yukselis acisinin EKRANDAKI tek kapisi: sayi etiketi + arac ikonu birlikte.
        Ikisi ayri ayri guncellenseydi biri unutuldugunda namlu ile sayi ayrisirdi."""
        self.tilt_val_lbl.setText(f"{self.tilt_aci:.1f}°")
        ikon = getattr(self, "arac_ikon", None)
        if ikon is not None:
            ikon.aci_ayarla(self.tilt_aci)

    def _dpad_izgarasi(self):
        """Yon tus takimi. 4 stil (normal/basili x kenar/merkez) tek sablondan uretilir."""
        self._key_normal_style = DPAD_NORMAL
        self._key_active_style = DPAD_BASILI
        self._key_center_normal_style = DPAD_MERKEZ
        self._key_center_active_style = DPAD_MERKEZ_BASILI

        dpad = QWidget()
        # 3 satir x (28 px + QSS'teki 1 px ust/alt kenarlik) — kenarlik hesaba katilmayinca
        # ızgara 92 px kaliyor, 30 px'lik tuslar birbirine biniyordu (olculdu).
        dpad.setFixedSize(3 * DPAD_EN + 2 * 4, 3 * (DPAD_BOY + 2) + 2 * 4)
        gl = QGridLayout(dpad)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(4)

        # (isim, metin, satir, kolon, ipucu, yon, merkez_mi)
        tuslar = [
            ("btn_up", "▲", 0, 1, "[W] veya [▲] — YUKARI (TİLT +)", "up", False),
            ("btn_left", "◀", 1, 0, "[A] veya [◄] — SOL (PAN -)", "left", False),
            ("btn_center", "MERKEZ", 1, 1, "[R] — MERKEZE AL (0°, 0°)", "home", True),
            ("btn_right", "▶", 1, 2, "[D] veya [►] — SAĞ (PAN +)", "right", False),
            ("btn_down", "▼", 2, 1, "[S] veya [▼] — AŞAĞI (TİLT -)", "down", False),
        ]
        for isim, metin, satir, kolon, ipucu, yon, merkez in tuslar:
            b = QPushButton(metin)
            b.setFixedSize(DPAD_EN, DPAD_BOY)
            b.setStyleSheet(self._key_center_normal_style if merkez else self._key_normal_style)
            b.setToolTip(ipucu)
            b.setCursor(Qt.PointingHandCursor)
            b.pressed.connect(lambda y=yon: self._dpad_press(y))
            b.released.connect(lambda y=yon: self._dpad_release(y))
            gl.addWidget(b, satir, kolon, Qt.AlignCenter)
            setattr(self, isim, b)
        return dpad

    def _seviye_butonlari(self, secenekler, secili, geri_cagri):
        """Apple macOS birleşik kapsül segment kontrolü.
        secenekler: [(deger, etiket), ...]   Doner: (capsule_frame, {deger: buton})"""
        capsule = QFrame()
        capsule.setObjectName("tabs")
        capsule.setFixedHeight(T.BOY_NORMAL + 4)      # 24 px segment + 2px iç boşluk
        th = QHBoxLayout(capsule)
        th.setContentsMargins(2, 2, 2, 2)
        th.setSpacing(2)
        btns = {}
        for val, etiket in secenekler:
            b = QPushButton(etiket)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setChecked(val == secili)
            b.setFixedHeight(T.BOY_NORMAL)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda checked=False, v=val: geri_cagri(v))
            th.addWidget(b, 1)
            btns[val] = b
        return capsule, btns

    # ---- Ic sayfa 1: Aci ve yasak alan ayarlari ----
    # yon -> (buton adi, pan carpani, tilt carpani). "home"/"center" ayri ele alinir
    # (aci degisimi degil, sifirlama). Tek tablo: basma ve birakma ayni yerden okur.
    YON_TABLO = {"up": ("btn_up", 0.0, 1.0), "down": ("btn_down", 0.0, -1.0),
                 "left": ("btn_left", -1.0, 0.0), "right": ("btn_right", 1.0, 0.0)}

    # Basili tutma davranisi: ilk dokunus SECILI ADIM kadar hareket eder (hassas nisan
    # icin tek tik = 1°/5°/10°); tus TEKRAR_GECIKME_MS'den uzun basili kalirsa surekli
    # harekete gecilir.
    TEKRAR_GECIKME_MS = 300
    TEKRAR_PERIYOT_MS = 50
    CAM_KUTU_EN = 300           # yasak alan / lazer cam kutucuk genisligi

    # ---- kol gostergesi (hangi tusa basildi) -------------------------------
    # Isiklar IKI kaynaktan gelir: arayuzun kendi durumu (klavye, ekrandaki D-pad,
    # ates/E-Stop) ve gercek gamepad okumasi. Ikisi AYRI kumede tutulur, ekranda
    # birlesimleri yanar — yoksa 50 ms'de bir gelen gamepad yoklamasi klavyenin
    # yaktigi isigi hemen sondururdu.
    def _kol_isik(self, ad, acik=True):
        if not hasattr(self, "kol_ikon"):
            return
        (self._kol_ui.add if acik else self._kol_ui.discard)(ad)
        self._kol_yenile()

    def _kol_gamepad_isik(self, adlar):
        if not hasattr(self, "kol_ikon"):
            return
        self._kol_gp = set(adlar)
        self._kol_yenile()

    def _kol_yenile(self):
        self.kol_ikon.isiklari_ayarla(self._kol_ui | self._kol_gp)

    def _kol_parla(self, adlar, ms=220):
        """Anlik komutlar (merkeze al) icin kisa parlama."""
        if not hasattr(self, "kol_ikon"):
            return
        for ad in adlar:
            self._kol_isik(ad, True)
        QTimer.singleShot(ms, lambda: [self._kol_isik(ad, False) for ad in adlar])

    def _dpad_press(self, direction):
        if direction in ("home", "center"):
            if hasattr(self, "btn_center"):
                self.btn_center.setStyleSheet(self._key_center_active_style)
            self._merkez_kurma_baslat("MERKEZ", kim="ui")   # 2 sn basili tut (kaza ile
            return                                          # merkeze donus gimbal'i bastan alir)
        ad, kpan, ktilt = self.YON_TABLO[direction]
        getattr(self, ad).setStyleSheet(self._key_active_style)
        self._kol_isik(direction, True)
        self._aci_hareket(kpan * self.aci_adim, ktilt * self.aci_adim)   # tek dokunus
        self._basili_yonler.add(direction)
        if not self._tekrar_timer.isActive():
            self._tekrar_gecikme.start(self.TEKRAR_GECIKME_MS)

    def _dpad_release(self, direction):
        if direction in ("home", "center"):
            if hasattr(self, "btn_center"):
                self.btn_center.setStyleSheet(self._key_center_normal_style)
            self._merkez_kurma_iptal(erken=True, kim="ui")
            return
        getattr(self, self.YON_TABLO[direction][0]).setStyleSheet(self._key_normal_style)
        self._kol_isik(direction, False)
        self._basili_yonler.discard(direction)
        if not self._basili_yonler:
            self._tekrar_durdur()

    # ---- USB GAMEPAD ----
    GP_TARAMA_TIK = 40      # cihaz yokken kac tikta bir yeniden taransin (~2 sn)

    def _gamepad_durum_yaz(self):
        """Alt cubuk: kol BAGLI ise YESIL nokta + cihaz adi, degilse KIRMIZI nokta.
        Soluk gri kullanilmaz — "yok" ile "bakmadim" ayni gorunurdu; operator tek
        bakista kolun hazir olup olmadigini bilmeli (video cekiminde de oyle)."""
        if self.gamepad.bagli:
            self._ci("Gamepad", GRN, f"· {self.gamepad.ad[:26]}")
        else:
            self._ci("Gamepad", RED, "· bağlı değil")

    def _gamepad_tik(self):
        """Gamepad'i yoklar ve komutlari MEVCUT KAPILARDAN gecirir.

        ⚠ Burada yeni bir komut yolu YOK. Hareket `_aci_hareket`, ates `_ates_kisayolu`
          (yani `_ates_bas`), merkez `_aci_reset`, E-Stop `_estop_bas` uzerinden gider.
          Gamepad'e kendi yolu verilseydi guvenlik denetimleri (E-Stop, atisa-yasak alan)
          atlanirdi — gecmiste ikinci bir ates yolu tam bunu yapmisti (CLAUDE.md §12 B1).
        """
        if not self.gamepad.bagli:
            # Sicak takma: cihaz yokken de periyodik tara, ama her tikta degil (pahali).
            self._gp_tarama += 1
            if self._gp_tarama >= self.GP_TARAMA_TIK:
                self._gp_tarama = 0
                if self.gamepad.tara():
                    self._gamepad_durum_yaz()
                    self.sb_msg.setText(f'<span style="color:{GRN}">●</span>&nbsp;'
                                        f'Gamepad bağlandı: {self.gamepad.ad}')
            return

        d = self.gamepad.oku()
        if not self.gamepad.bagli:          # okuma sirasinda koptu
            self._gamepad_durum_yaz()
            self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;Gamepad bağlantısı koptu')
            return

        simdi = time.time()
        dt = min(0.2, simdi - self._gp_son_t)      # takilma sonrasi sicrama olmasin
        self._gp_son_t = simdi

        # E-STOP her kosulda islenir (digerlerinden ONCE): acil durdurma bir moda ya da
        # baska bir kosula bagli olamaz. Ayni buton DEVAM icin de kullanilir.
        # Koldaki gercek tuslar ekrandaki kol resminde yanar (durum gostergesi).
        # Cubuklar analogdur (dugme degil): sapinca kendi daireleri yanar — yoksa
        # sag cubukla yukari/asagi surerken ekranda hicbir sey degismiyordu.
        isiklar = set(d.basili)
        if d.pan:
            isiklar.add("sol_cubuk")
        if d.tilt:
            isiklar.add("sag_cubuk")
        self._kol_gamepad_isik(isiklar)
        self._gp_ates_basili = d.ates_basili

        if d.estop:
            self.estop_btn.setChecked(not self.estop_btn.isChecked())
            self._estop_bas()
            return                                  # ayni tikta baska komut isleme

        # ATES (takim karari 22.09): L2 + R2 BIRLIKTE. Kapali iken 2 sn basili tutmak
        # acar (klavyedeki Space+B ile ayni kural); ACIKKEN tek dokunus keser —
        # kesmek her zaman kolay olmalidir, beklemeye zorlanmaz.
        if d.ates_kenar:
            if self.fire_btn.isChecked():
                self._ates_kes("kol (L2+R2)")
                self._ates_kurma_iptal()
            elif not self._ates_kurma.isActive():
                self._ates_kurma_baslat("kol")
        elif not d.ates_basili and self._ates_kurma_kaynak == "kol":
            if self._ates_kurma.isActive():
                self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;'
                                    f'Ateş iptal — tetik erken bırakıldı')
            self._ates_kurma_iptal()

        # MERKEZ: L1/R1 **2 sn basili** (ates gibi). Tek dokunusla merkeze donmek
        # gimbal'i bastan alir; kazara dokunmak pahaliya mal olurdu.
        if d.merkez:
            self._merkez_kurma_baslat("L1/R1", kim="kol")
        elif not d.merkez_basili:
            self._merkez_kurma_iptal(erken=True, kim="kol")

        # HAREKET: adim = tavan hiz x gecen sure x cubugun sapmasi. Basili tutma
        # (`_tekrar_tik`) ile ayni matematik — tek farki analog carpan. Sabit adim
        # gonderilseydi hedef motorun onune gecer, cubuk birakildiginda gimbal
        # yetismek icin donmeye devam ederdi.
        if d.hareket_var:
            adim = P.HIZ_TABLO[self.hiz_seviye][0] * dt
            self._aci_hareket(d.pan * adim, d.tilt * adim)

    def _tekrar_baslat(self):
        if self._basili_yonler:
            self._son_tekrar_t = time.time()
            self._tekrar_timer.start()

    def _tekrar_tik(self):
        """Basili tutulan yon(ler) icin bir adim.

        Adim SECILI ADIM ACISI DEGIL, **motorun tavan hizi x gecen sure** kadardir.
        Sabit adimla gonderilseydi (or. 50 ms'de 5°  = 100°/s) hedef, motorun gidebilecegi
        hizin onune gecer; tus birakildiginda gimbal hedefe yetismek icin donmeye devam
        eder ve kullanici "durmuyor" diye gorurdu. Bu haliyle hedef motorla ayni tempoda
        ilerler, birakinca en fazla bir tiklik yol kalir."""
        if not self._basili_yonler:
            self._tekrar_durdur()
            return
        simdi = time.time()
        dt = min(0.2, simdi - self._son_tekrar_t)      # takilma sonrasi sicrama olmasin
        self._son_tekrar_t = simdi
        adim = P.HIZ_TABLO[self.hiz_seviye][0] * dt    # derece/sn x sn
        kpan = ktilt = 0.0
        for yon in self._basili_yonler:                # W+D gibi capraz kombinasyonlar
            _, p, t = self.YON_TABLO[yon]
            kpan += p
            ktilt += t
        if (kpan or ktilt) and not self._aci_hareket(kpan * adim, ktilt * adim):
            self._tekrar_durdur()                      # E-Stop / yasak alan: tekrari kes

    def _tekrar_durdur(self):
        self._tekrar_gecikme.stop()
        self._tekrar_timer.stop()
        self._basili_yonler.clear()

    def _tuslari_birak(self):
        """Tum yon tuslarini birakilmis say (tekrari kes + basili stilleri sifirla)."""
        if not hasattr(self, "_tekrar_timer"):
            return
        self._tekrar_durdur()
        self._ates_kurma_iptal()                       # odak gitti: yarim kalan kurma sayilmaz
        for yon, (ad, _, _) in self.YON_TABLO.items():
            b = getattr(self, ad, None)
            if b is not None and hasattr(self, "_key_normal_style"):
                b.setStyleSheet(self._key_normal_style)
            self._kol_isik(yon, False)

    def changeEvent(self, e):
        # Pencere odagi giderse (Alt+Tab, baska uygulamaya tiklama) tusun BIRAKMA olayi
        # bize hic gelmeyebilir; o zaman surekli hareket sonsuza dek surer ve gimbal
        # kullanici farkinda olmadan donmeye devam eder. Odak kaybinda kesiyoruz.
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self._tuslari_birak()
        super().changeEvent(e)

    # NOT (B1): burada eskiden ikinci bir ates yolu vardi (`_fire_bas`). Iki sorunu vardi:
    #   1. `self.kontrol.ates()` zorunlu `ac` argumani olmadan cagriliyordu -> TypeError
    #      (hicbir yere bagli olmadigi icin patlamamisti; baglandigi an uygulama coker).
    #   2. E-STOP KONTROLU YOKTU -> E-Stop'ta ates edebilirdi (sartname Yetenek 4 ihlali).
    # Cozum: ates icin TEK KAPI var, `_ates_bas`. Yeni bir ates butonu eklenecekse
    # o da `_ates_bas`'a baglanmalidir; guvenlik kontrolleri orada toplanmistir.

    def atis_yasak_mi(self):
        """Su anki yon ATIS PENCERESININ disinda mi? (iki eksen birlikte — sartname
        §4.2 atisa-yasak alan). Pencere tanimlanmamissa ates her yonde serbesttir."""
        return not B.atis_izinli(self.pan_aci, self.tilt_aci, self.bolge)

    YORUNGE_UFUK_S = 0.2

    def tilt_taban_deg(self):
        return B.TILT_CALISMA_MIN if getattr(self.kontrol, "tilt_ayri", False) else 0.0

    def _acilis_hizala(self):
        k = getattr(self, "kontrol", None)
        hz = getattr(k, "acilis_hizalama", None) if k else None
        if hz is None:
            return
        k.acilis_hizalama = None
        self.pan_ham, self.tilt_aci = hz
        self.pan_aci = self.pan_ham % 360.0
        self._pan_goster()
        self._tilt_goster()
        if not self._acilis_yukselisi and k.tilt_ayri:
            self._acilis_yukselisi = True
            self._acilis_yukselisi_bekliyor = True

    def _acilis_yukselisini_dene(self):
        """Kart acilinca ilk STATE3 kilitli gelebilir; hazir olmadan denemeyi tuketme."""
        if not self._acilis_yukselisi_bekliyor:
            return
        if self._hareket_kilitli() or not self.kontrol.tilt.hazir:
            return
        if abs(self.tilt_aci) <= 0.2:
            self._acilis_yukselisi_bekliyor = False
            return
        if self._aci_hareket(0.0, -self.tilt_aci):
            self._acilis_yukselisi_bekliyor = False

    def _aci_hareket(self, d_pan, d_tilt, taban_olculen=False, hiz=None):
        """Tek hareket kapisi: geri bildirim, mekanik limit, izinli pencere, E-Stop."""
        if self._hareket_kilitli():
            self._merkez_durdur()
            return False
        if ((d_tilt or (hiz is not None and hiz[1]))
                and getattr(self.kontrol, "tilt_ayri", False)
                and not self.kontrol.tilt.hazir):
            self.bolge_status.setText("TİLT KARTI HAZIR DEĞİL — hareket engellendi")
            self.bolge_status.setStyleSheet(T.durum_bandi(T.KIRMIZI))
            return False
        if not getattr(self, "_merkez_calisiyor", False):
            self._merkez_durdur("yon komutu geldi")
        self._acilis_hizala()
        tilt_taban = self.tilt_aci
        if taban_olculen and d_tilt:
            olculen = getattr(self.kontrol, "tilt_olculen", None)
            if olculen is not None:
                tilt_taban = olculen
        # Komut verilmeyen ekseni koru: açılışta bildirilen konum izinli pencere
        # dışındaysa diğer ekseni sürmek beklenmedik bir karşı-harekete yol açmasın.
        yeni_pan_ham, pan_durum = ((self.pan_ham, B.SERBEST) if not d_pan else
            B.pan_hareket(self.pan_ham, d_pan, self.bolge.hareket_pan))
        yeni_tilt, tilt_durum = ((self.tilt_aci, B.SERBEST) if not d_tilt else
            B.tilt_hareket(tilt_taban, d_tilt, self.bolge.hareket_tilt,
                           self.max_tilt_limit, self.tilt_taban_deg()))
        durumlar = (pan_durum, tilt_durum)
        if (yeni_pan_ham == self.pan_ham and yeni_tilt == self.tilt_aci
                and any(d != B.SERBEST for d in durumlar)):
            self.bolge_status.setText("▲ HAREKETE YASAK — PENCERE DIŞINA ÇIKILAMAZ")
            self.bolge_status.setStyleSheet(T.durum_bandi(T.KIRMIZI))
            return False

        if hiz is not None:
            pan_v, tilt_v = hiz
            if pan_v:
                ileri, _ = B.pan_hareket(yeni_pan_ham, pan_v * self.YORUNGE_UFUK_S,
                                         self.bolge.hareket_pan)
                if abs(ileri - (yeni_pan_ham + pan_v * self.YORUNGE_UFUK_S)) > 1e-6:
                    pan_v = 0.0
            if tilt_v:
                ileri, _ = B.tilt_hareket(yeni_tilt, tilt_v * self.YORUNGE_UFUK_S,
                                          self.bolge.hareket_tilt,
                                          self.max_tilt_limit, self.tilt_taban_deg())
                if abs(ileri - (yeni_tilt + tilt_v * self.YORUNGE_UFUK_S)) > 1e-6:
                    tilt_v = 0.0
            hiz = (pan_v, tilt_v)

        self.pan_ham = yeni_pan_ham
        self.pan_aci = yeni_pan_ham % 360.0
        self.tilt_aci = yeni_tilt
        self._pan_goster()
        self._tilt_goster()
        if self.atis_yasak_mi():
            self.bolge_status.setText("⚠️ ATIŞA YASAK BÖLGEDESİNİZ — ATEŞ KİLİTLİ")
            self.bolge_status.setStyleSheet(T.durum_bandi(T.SARI))
            self._ates_kes("ATIŞA YASAK AÇI BÖLGESİNE GİRİLDİ")
        elif B.KIRPILDI in durumlar:
            self.bolge_status.setText("▲ HAREKET SINIRINA ULAŞILDI")
            self.bolge_status.setStyleSheet(T.durum_bandi(T.SARI))
        else:
            self.bolge_status.setText("● BÖLGE GÜVENLİ")
            self.bolge_status.setStyleSheet(T.durum_bandi(T.YESIL))
        if getattr(self, "kontrol", None) and self.kontrol.bagli:
            if hiz is not None and self.kontrol.yorunge_destekli:
                self._esp_goster(self.kontrol.yorunge(
                    self.pan_ham if hiz[0] is not None else None, hiz[0],
                    self.tilt_aci if hiz[1] is not None else None, hiz[1]))
            else:
                self._esp_goster(self.kontrol.aci(self.pan_ham, self.tilt_aci))
        return True

    def _nisan_geldi(self, d_yaw, d_pitch):
        """B3 — Otonom nisan dongusunden gelen aci duzeltmesi (AlgiThread.nisan_komut).

        Manuel hareketle AYNI kapidan (_aci_hareket) gecer: E-Stop, yasak alan ve
        tilt limiti otonom modda da aynen uygulanir — guvenlik icin tek yol olmali.

        PD'nin urettigi komut, HER EKSENIN GERCEKTEN GIDEBILECEGI hizla (secili hiz
        duzeyinin pan ve tilt profilleri ayri ayri) kirpilir — basili-tutma D-pad'de
        (_tekrar_tik) kullanilan AYNI matematik: adim = tavan_hiz x gecen_sure.
        ESP32 konum geri bildirimi YOLLAMADIGI
        icin (CLAUDE.md §5.1) pan_ham/tilt_aci gimbalin fiziksel pozisyonu hakkinda
        YAZILIMIN inancidir, olcum degil.

        MESGUL KAPISI (13.08 — "ortaladigi an durmuyor, karsi tarafa geciyor, sistem
        hic yerlesmeden salinip duruyor"): yalniz hiz kirpmasi yetmiyordu. Motor bir
        komutu fiziksel olarak yerine getirirken (ivmelenme profiliyle onlarca-yuzlerce
        ms surer, ozellikle kisa duzeltmelerde tepe hiza HIC ulasilmaz — H_NORMAL'de
        40°/sn'e cikmak 0.4 sn ister) KAMERA GORUNTUSU henuz guncellenmez; o sure icinde
        gelen her yeni kare AYNI (bayat) piksel hatasini gorur ve PD AYNI hatadan taze
        bir duzeltme daha uretir — her biri tek basina hiz sinirinin icinde kalsa bile
        TOPLAMLARI gercek ihtiyacin KAT KAT ustune cikar (motor nihayet yetistiginde
        hedef zaten karsi tarafa gecmis olur, sonra ayni sey tersten tekrarlanir → hic
        yerlesmeyen salinim). Cozum: gonderilen komutun TAHMINI fiziksel tamamlanma
        suresinin bir KISMI kadar (ucgen ivme profili: `2 x sqrt(mesafe/ivme) x
        NISAN_MESGUL_ORANI`, asgari `NISAN_MIN_ARALIK`) yeni komut KABUL EDILMEZ —
        tam tamamlanmasini DEGIL, GORULEBILIR ilerlemeyi bekler (bkz. NISAN_MESGUL_ORANI
        yorumu: tam bekleme akiciligi asiri dusurdugu icin kisaltildi)."""
        if self.mod != "Otonom":
            return
        if self._surekli_takip_mi():
            return   # iki eksen de konum bildiriyor: _takip_olcum_geldi yonetir
        simdi = time.time()
        if simdi < self._nisan_mesgul_ta:
            return   # onceki komutun fiziksel karsiligi henuz gorulmedi, bekle
        (pan_hiz, pan_ivme), (tilt_hiz, tilt_ivme) = \
            self.kontrol.hiz_profilleri(self.hiz_seviye)
        if self._nisan_son_t is not None:
            dt = min(0.2, simdi - self._nisan_son_t)   # uzun kopukluk sonrasi sicrama olmasin
            pan_tavan = pan_hiz * dt
            tilt_tavan = tilt_hiz * dt
            d_yaw = max(-pan_tavan, min(pan_tavan, d_yaw))
            d_pitch = max(-tilt_tavan, min(tilt_tavan, d_pitch))
        self._nisan_son_t = simdi

        # taban_olculen=True: dikey eksende komut, kartin BILDIRDIGI aciya gore
        # kurulur (bkz. _aci_hareket). Kart bildirmiyorsa (eski donanim) eski
        # davranis aynen surer.
        if self._aci_hareket(d_yaw, d_pitch, taban_olculen=True):
            # Ucgen ivme profili (tepe hiza hic ulasilmadigi varsayimi — kisa
            # duzeltmelerde gecerli): TAM tamamlanma t = 2*sqrt(mesafe/ivme); yalniz
            # NISAN_MESGUL_ORANI kadarini bekleriz (bkz. sabitin yorumu — akicilik icin).
            pan_sure = 2.0 * math.sqrt(abs(d_yaw) / max(1.0, pan_ivme))
            tilt_sure = 2.0 * math.sqrt(abs(d_pitch) / max(1.0, tilt_ivme))
            sure = max(pan_sure, tilt_sure) * NISAN_MESGUL_ORANI
            self._nisan_mesgul_ta = simdi + max(NISAN_MIN_ARALIK, sure)
    def _kamera_acilari(self, t):
        """(pan, kamera yukselisi) `t` aninda — InferenceThread'den cagrilir (okuma)."""
        k = getattr(self, "kontrol", None)
        if not (k and k.bagli and k.takip_geri_bildirimli):
            return None
        return k.pan_zamaninda(t), TS.kamera_acisi(k.tilt_zamaninda(t))

    def _surekli_takip_mi(self):
        k = getattr(self, "kontrol", None)
        return bool(k and k.bagli and k.takip_geri_bildirimli)

    def _takip_olcum_geldi(self, d):
        """SUREKLI TAKIP — iki eksen de konumunu bildiriyorsa otonom yolun sahibi.

        PD + mesgul kapisi (_nisan_geldi) sahada titreme ve dur-kalk uretti (21.09:
        40 sn'de 271 ayri tilt hedefi, pan 16 yon degisimi, yatay medyan 43 px):
        her kare kucuk bir adim, motor durur, bayat kareye bakilip yeni adim.
        Burada hedefin DUNYA acisi (kare anindaki eksen acisi + hata/ppd) filtrelenir
        ve karta MUTLAK hedef olarak akar; kart hareket halinde durmadan yeni hedefe
        gecer. Ayrinti ve benzetim sonuclari: hedef_kestirici.EksenTakip.

        Hareket yine TEK KAPIDAN (_aci_hareket) gecer: E-Stop, yasak alan, limit aynen."""
        if self.mod != "Otonom" or not self._surekli_takip_mi():
            return
        k = self.kontrol
        simdi = time.time()
        var = bool(d.get("var"))
        ex = ey = olu_x = olu_y = None
        if var:
            olcek = float(d["w"]) / 1280.0              # ppd 1280 px'te olculdu
            ex, ey, olu_x, olu_y = d["ex"], d["ey"], d["olu_x"], d["olu_y"]
            t_kare = d["t"] - float(algi.AYAR.get("kamera_gecikme", 0.03))
            self._pan_takip.olcum(t_kare, k.pan_zamaninda(t_kare), ex,
                                  float(algi.AYAR.get("takip_ppd_pan", 18.7)) * olcek)
            # Tilt KAMERA ACISINDA izlenir (kol-biyel dogrusal degil, bkz.
            # tilt_surucu.KAMERA_PPD_TABLO); orada ppd pan ile ayni.
            self._tilt_takip.olcum(t_kare, TS.kamera_acisi(k.tilt_zamaninda(t_kare)), ey,
                                   float(algi.AYAR.get("takip_ppd_pan", 18.7)) * olcek)
        sinir = min(B.PAN_MAX, float(algi.AYAR.get("pan_takip_siniri", 170.0)))
        ust = min(self.max_tilt_limit, float(algi.AYAR.get("tilt_takip_ust", 18.0)))
        if k.yorunge_destekli:
            # YORUNGE KIPI: (konum, hiz) — motor hedefin hizinda akar, dur-kalk yok.
            pr = self._pan_takip.yorunge_komut(simdi, k.pan_olculen, -sinir, sinir,
                                               hata_px=ex, olu_px=olu_x)
            tr = self._tilt_takip.yorunge_komut(
                simdi, TS.kamera_acisi(k.tilt_olculen), TS.kamera_acisi(B.TILT_CALISMA_MIN),
                TS.kamera_acisi(ust), hata_px=ey, olu_px=olu_y)
            if pr is None and tr is None:
                return
            d_pan = pan_v = d_tilt = tilt_v = None
            if pr is not None:
                d_pan, pan_v = pr[0] - self.pan_ham, pr[1]
            if tr is not None:
                # kamera acisi -> kol acisi; hiz yerel egimle (kol-biyel dogrusal degil)
                kol = max(B.TILT_CALISMA_MIN, min(ust, TS.kol_acisi(tr[0])))
                egim = (TS.kamera_acisi(kol + 0.05) - TS.kamera_acisi(kol - 0.05)) / 0.1
                d_tilt, tilt_v = kol - self.tilt_aci, tr[1] / max(1e-3, egim)
            if self._aci_hareket(d_pan or 0.0, d_tilt or 0.0, hiz=(pan_v, tilt_v)):
                self._nisan_mesgul_ta = simdi + 0.15
            return
        pan_k = self._pan_takip.komut(simdi, k.pan_olculen, -sinir, sinir,
                                      hata_px=ex, olu_px=olu_x)
        ust = min(self.max_tilt_limit, float(algi.AYAR.get("tilt_takip_ust", 18.0)))
        tilt_k = TS.kol_acisi(self._tilt_takip.komut(
            simdi, TS.kamera_acisi(k.tilt_olculen), TS.kamera_acisi(B.TILT_CALISMA_MIN), TS.kamera_acisi(ust),
            hata_px=ey, olu_px=olu_y))
        if tilt_k is not None:
            tilt_k = max(B.TILT_CALISMA_MIN, min(ust, tilt_k))
        if pan_k is None and tilt_k is None:
            return
        d_pan = 0.0 if pan_k is None else pan_k - self.pan_ham
        d_tilt = 0.0 if tilt_k is None else tilt_k - self.tilt_aci
        if self._aci_hareket(d_pan, d_tilt):
            self._nisan_mesgul_ta = simdi + 0.15      # durum etiketi: "Konumlaniyor..."

    def _yasak_kapsulu(self, tur, ad):
        """Baslikta minimal kapsul: ad + anahtar. Doner: (kapsul, etiket, anahtar)."""
        kapsul = _TiklanirKapsul(lambda t=tur: self._bolge_sayfasi_ac(t))
        kapsul.setObjectName("angtgl")
        kapsul.setCursor(Qt.PointingHandCursor)
        kapsul.setFixedHeight(28)
        h = QHBoxLayout(kapsul)
        h.setContentsMargins(10, 0, 4, 0)
        h.setSpacing(6)
        etiket = QLabel(ad)
        anahtar = AppleSwitch(checked=False, kucuk=True)   # baslikta yer dar: Small
        anahtar.toggled.connect(lambda acik, t=tur: self._yasak_anahtar(t, acik))
        h.addWidget(etiket, 0, Qt.AlignVCenter)
        h.addWidget(anahtar, 0, Qt.AlignVCenter)
        return kapsul, etiket, anahtar

    def _bolge_sayfasi(self, tur):
        """Sade ayar sayfasi: Yatay / Dikey icin Alt-Ust + Kaydet. Aciklama metni yok.
        Kart ICERIK boyundadir; yiginin geri kalani bos kalir (eskiden tum paneli
        dolduruyor, alti bos dev bir kutu oluyordu)."""
        sayfa = QFrame()
        sayfa.setObjectName("ayarpanel")     # goruntu isleme paneliyle ayni opak zemin
        sayfa.setFixedWidth(self.CAM_KUTU_EN)
        v = QVBoxLayout(sayfa)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)
        bas = QHBoxLayout()
        baslik = QLabel("Atışa Yasak Alan" if tur == "atis" else "Harekete Yasak Alan")
        baslik.setObjectName("ayartitle")
        kapat = QPushButton("✕")
        kapat.setObjectName("ayarclose")
        kapat.setCursor(Qt.PointingHandCursor)
        kapat.clicked.connect(self._bolge_sayfasi_kapat)
        bas.addWidget(baslik, 1)
        bas.addWidget(kapat, 0)
        v.addLayout(bas)

        izgara = QGridLayout()
        izgara.setHorizontalSpacing(8)
        izgara.setVerticalSpacing(8)
        # Kutularin araligi YAPISAL sinirdir: yataya 100 yazilamaz (namlu on yarinin
        # disina cikamaz, B.PAN_MAX), dikeye 40 yazilamaz. Operator yalniz DARALTIR.
        for satir, (eksen, ad, sinir) in enumerate(
                (("pan", "Yatay", int(B.PAN_MAX)), ("tilt", "Dikey", int(B.TILT_CALISMA_MAX)))):
            p = getattr(self.bolge, f"{tur}_{eksen}")
            lbl = QLabel(ad)
            lbl.setObjectName("ayarlbl")
            izgara.addWidget(lbl, satir, 0)
            spinler = []
            for sutun, (etiket, deger) in enumerate((("Alt", p.alt), ("Üst", p.ust))):
                e = QLabel(etiket)
                e.setObjectName("engsub")
                spin = QSpinBox()
                spin.setRange(-sinir, sinir)
                spin.setSuffix("°")
                spin.setValue(int(deger))      # degisiklik KAYDET'e kadar uygulanmaz
                izgara.addWidget(e, satir, 1 + sutun * 2)
                izgara.addWidget(spin, satir, 2 + sutun * 2)
                spinler.append(spin)
            self.bolge_spin[(tur, eksen)] = tuple(spinler)
        izgara.setColumnStretch(2, 1)
        izgara.setColumnStretch(4, 1)
        v.addLayout(izgara)

        kaydet = QPushButton("Kaydet")
        kaydet.setObjectName("ayarkaydet")
        kaydet.setCursor(Qt.PointingHandCursor)
        kaydet.clicked.connect(lambda _=False, t=tur: self._bolge_kaydet(t))
        alt = QHBoxLayout()
        alt.addStretch(1)
        alt.addWidget(kaydet)
        v.addLayout(alt)
        return sayfa

    def _bolge_sayfasi_ac(self, tur):
        """Kapsule tiklama: o alanin sayfasi; ayni kapsule tekrar tiklamak kapatir.
        Acarken kutular KAYITLI degerle dolar (yarim kalmis duzenleme tasinmaz)."""
        if self._acik_pencere == tur:
            self._bolge_sayfasi_kapat()
            return
        self._bolge_kutulari_yenile()
        self._pencere_ac(tur)

    def _bolge_sayfasi_kapat(self):
        """Kaydetmeden kapatma: kutulardaki degisiklik ATILIR."""
        if self._acik_pencere in ("atis", "hareket"):
            self._pencere_kapat()

    def _bolge_kaydet(self, tur):
        """KAYDET: yalniz bu alanin kutularini self.bolge'ye yazar, sonra kapatir."""
        for eksen in ("pan", "tilt"):
            alt, ust = self.bolge_spin[(tur, eksen)]
            p = getattr(self.bolge, f"{tur}_{eksen}")
            p.alt, p.ust = float(alt.value()), float(ust.value())
            if p.alt > p.ust:                         # ters girilmis -> tek nokta
                p.ust = p.alt
        self.pencereler[tur].setVisible(False)        # once kapat: tum kutular yenilensin
        self._acik_pencere = None
        self._odak_geri()
        self._bolge_uygula()

    def _yasak_anahtar(self, tur, acik):
        """Anahtar: o alani (iki eksen birlikte) acar/kapar."""
        for eksen in ("pan", "tilt"):
            getattr(self.bolge, f"{tur}_{eksen}").aktif = bool(acik)
        self._bolge_uygula()

    def _bolge_uygula(self, *_):
        """KAYITLI pencereleri uyumlar (atis alani hareket alaninin disina tasamaz —
        bolge.atis_uyumla) ve kutulara + kapsullere yansitir."""
        if len(getattr(self, "bolge_spin", {})) < 4:
            return                                    # sayfalar kurulurken erken cagri
        B.atis_uyumla(self.bolge)
        # Acik sayfa YENILENMEZ: operator deger yazip Kaydet'e basmadan bir anahtari
        # cevirirse yazdiklari sessizce silinmesin (test yakaladi).
        acik = getattr(self, "_acik_pencere", None)
        acik = acik if acik in ("atis", "hareket") else None
        self._bolge_kutulari_yenile(haric=acik)
        self._yasak_dugmeleri_guncelle()
        self._bolge_karolari_yenile()

    def _bolge_karolari_yenile(self):
        """Aci karolarindaki renkli yasak alan dilimleri (KAYITLI pencereler)."""
        b = self.bolge
        if hasattr(self, "arac_yon_ikon"):
            self.arac_yon_ikon.bolge_ayarla(b.hareket_pan, b.atis_pan)
        if hasattr(self, "arac_ikon"):
            self.arac_ikon.bolge_ayarla(b.hareket_tilt, b.atis_tilt)

    def _bolge_kutulari_yenile(self, haric=None):
        """Kutulari KAYITLI degerlere getirir (kaydedilmemis duzenlemeyi atar)."""
        for (tur, eksen), spinler in getattr(self, "bolge_spin", {}).items():
            if tur == haric:
                continue
            p = getattr(self.bolge, f"{tur}_{eksen}")
            for spin, deger in zip(spinler, (p.alt, p.ust)):
                if spin.value() != int(deger):
                    spin.setValue(int(deger))

    def _yasak_dugmeleri_guncelle(self):
        """Kapsullerin gorunumu: acikken renkli ad + anahtar acik; ipucunda araliklar."""
        renkler = {"atis": T.KIRMIZI, "hareket": T.SARI}
        for tur, (kapsul, etiket, anahtar) in getattr(self, "yasak_dugme", {}).items():
            pan, tilt = getattr(self.bolge, f"{tur}_pan"), getattr(self.bolge, f"{tur}_tilt")
            acik = pan.aktif or tilt.aktif
            etiket.setStyleSheet(T.yazi(T.CAGRI_VURGU, renkler[tur] if acik else T.L2))
            anahtar.blockSignals(True)
            anahtar.setChecked(acik)
            anahtar.blockSignals(False)
            kapsul.setToolTip(f"Yatay {pan.alt:+.0f}…{pan.ust:+.0f}° · Dikey {tilt.alt:+.0f}…{tilt.ust:+.0f}°"
                              + ("" if acik else " (kapalı)") + "\nAyarlamak için tıklayın")

    def _hareket_kilitli(self):
        """E-Stop suruyor mu? Hareketin HER yolu (yon tuslari, otonom nisan, merkeze
        alma) buna bakar — kilit tek yerde tanimli ki bir yol unutulmasin.
        (isinstance ile bakilir: QObject'in yerlesik thread() metodu yuzunden
        hasattr/getattr(self,"thread") thread olusmadan once de dolu gorunur.)"""
        if isinstance(getattr(self, "thread", None), VideoThread) and self.thread.estop:
            return True
        # Kart KENDI durduysa (seri monitorden STOP / donanim butonu) arayuz E-Stop'a
        # basilmamis olabilir; komut gonderilirse kart yok sayar ama ekrandaki aci
        # ilerler -> ekran ile hedef kopar.
        return bool(getattr(self, "kontrol", None) and self.kontrol.estop_aktif)

    def _aci_reset(self):
        """Merkeze al (0°, 0°) — ANINDA DEGIL, motor hiziyla KADEMELI.

        Kendi E-Stop kapisi VAR: eskiden bu koruma yalniz MERKEZ butonunun devre
        disi kalmasina dayaniyordu, klavyedeki [R] onu atliyordu.

        ⚠ NEDEN KADEMELI (kullanici uyarisi 22.09): eski surum acilari bir anda 0
        yapip karta "eve don" diyordu. Gercek dunyada motor o mesafeyi ANINDA
        alamaz; ekran sifira ziplarken gimbal hala yoldaydi, yani ekrandaki aci
        gercek konumdan koptu (§5.1'in kacindigi hata sinifi). Artik merkeze
        donus, D-pad'i basili tutmakla AYNI matematikle (tavan hiz x gecen sure)
        adim adim yapilir; yolda operator yon verirse ya da E-Stop gelirse durur."""
        if self._hareket_kilitli():
            return False
        self._merkez_son_t = time.time()
        self._merkez_timer.start(self.TEKRAR_PERIYOT_MS)
        self.sb_msg.setText(f'<span style="color:{BLUE}">●</span>&nbsp;Merkeze alınıyor…')
        return True

    MERKEZ_KURMA_MS = 2000       # MERKEZ butonu / L1-R1: basili tutma suresi

    def _merkez_kurma_baslat(self, kaynak, kim="ui"):
        """Merkeze alma 2 sn basili tutmayi ister: kaza ile dokunmak gimbal'i
        bastan almasin (ates kurmasiyla ayni desen)."""
        if self._hareket_kilitli() or self._merkez_kurma.isActive():
            return
        self._merkez_kurma_kim = kim
        self._kol_isik("l1", True)
        self._kol_isik("r1", True)
        self._merkez_kurma.start(self.MERKEZ_KURMA_MS)
        self.sb_msg.setText(f'<span style="color:{BLUE}">●</span>&nbsp;'
                            f'MERKEZ: {kaynak} basılı tut… (2 sn)')

    def _merkez_kurma_iptal(self, erken=False, kim=None):
        """⚠ `kim`: sayaci YALNIZ baslatan kaynak iptal edebilir. Gamepad yoklamasi
        50 ms'de bir "L1/R1 basili degil" diyor; kaynak ayrimi olmadan ekrandaki
        MERKEZ butonunu basili tutmak HICBIR ZAMAN 2 sn'yi dolduramiyordu — kol
        takiliyken ekrandaki merkez islevsiz kaliyordu (kullanici bildirdi)."""
        if kim is not None and getattr(self, "_merkez_kurma_kim", None) != kim:
            return
        sonlandi = self._merkez_kurma.isActive()
        self._merkez_kurma.stop()
        self._kol_isik("l1", False)
        self._kol_isik("r1", False)
        if erken and sonlandi:
            self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;'
                                f'Merkeze alma iptal — erken bırakıldı')

    def _merkez_kurma_bitti(self):
        self._kol_isik("l1", False)
        self._kol_isik("r1", False)
        self._aci_reset()                 # E-Stop denetimi _aci_reset'in icinde

    def _merkez_durdur(self, sebep=None):
        if getattr(self, "_merkez_timer", None) is not None and self._merkez_timer.isActive():
            self._merkez_timer.stop()
            if sebep:
                self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;'
                                    f'Merkeze alma durduruldu — {sebep}')

    def _merkez_tik(self):
        """Bir adim merkeze. Adim = motorun tavan hizi x gecen sure (bkz. `_tekrar_tik`)."""
        simdi = time.time()
        dt = min(0.2, simdi - self._merkez_son_t)
        self._merkez_son_t = simdi
        adim = P.HIZ_TABLO[self.hiz_seviye][0] * dt

        kalan_pan = -B.pan_isaretli(self.pan_ham)      # 0'a olan isaretli mesafe
        kalan_tilt = -self.tilt_aci
        if abs(kalan_pan) < 0.05 and abs(kalan_tilt) < 0.05:
            self._merkez_durdur()
            self.sb_msg.setText(f'<span style="color:{GRN}">●</span>&nbsp;Merkeze alındı')
            return
        d_pan = max(-adim, min(adim, kalan_pan))
        d_tilt = max(-adim, min(adim, kalan_tilt))
        self._merkez_calisiyor = True
        try:
            ok = self._aci_hareket(d_pan, d_tilt)
        finally:
            self._merkez_calisiyor = False
        if not ok:                                     # E-Stop / yasak alan
            self._merkez_durdur("hareket engellendi")

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

        # Tum yazilar SOLDA toplanir, kartin sagi bos kalir (takim karari 22.09):
        # ustte asamanin icerigi, altinda kural satiri + asama etiketi.
        ic = QVBoxLayout()
        ic.setSpacing(4)

        self.stack = QStackedWidget()
        yok = QLabel("Aşama seçiniz")
        yok.setObjectName("bosmsg")
        yok.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(yok)                     # 0: secim yok
        self.stack.addWidget(self._asama1_panel())    # 1: Asama 1 (kartlar)
        self.stack.addWidget(self._tur_panel(4))      # 2: Asama 2 (tur/4)
        self.stack.addWidget(self._tur_panel(8))      # 3: Asama 3 (tur/8)
        ic.addWidget(self.stack, 1)

        kural_satiri = QHBoxLayout()
        kural_satiri.setSpacing(10)
        self.asama_pill = QLabel(self.asama or "—")
        self.asama_pill.setObjectName("asamap")
        self.kural = QLabel()
        self.kural.setObjectName("kural")
        self.kural.setWordWrap(False)           # tek satir: yukseklik sabit kalsin
        kural_satiri.addWidget(self.asama_pill, 0, Qt.AlignVCenter)
        kural_satiri.addWidget(self.kural, 0, Qt.AlignVCenter)
        kural_satiri.addStretch(1)
        ic.addLayout(kural_satiri)

        sv.addLayout(ic)
        h.addWidget(sysk, 8)

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
                        ("ESP32", "· bağlı değil"), ("Tilt Kartı", "· kapalı"),
                        ("Seri Port", "· bekleniyor"),
                        ("Gamepad", "· aranıyor")):
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
        cont, _, self.sb_fps = self._sb_seg("CAM — | AI —")
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
            dot.setStyleSheet(T.nokta(dot_renk, 6))
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
        if getattr(self, "_acik_pencere", None):
            self._pencere_kapat()            # manuel panel gizlenirken kutucuk askida kalmasin
        for m, b in self.mod_btns.items():
            b.setChecked(m == ad)
        izin = self.IZIN[ad]
        for a, b in self.asama_btns.items():
            b.setEnabled(a in izin)
        if self.asama not in izin:          # gecersiz asama -> secimi kaldir
            self.asama = None
            for b in self.asama_btns.values():
                b.setChecked(False)
        # Otonom'a gecerken asama secili degilse ASAMA 3'e dus. Otonom ates kapisi
        # zaten yalniz Asama 2/3'te acilir (_otonom_ates_kontrol); asamasiz Otonom
        # "her sey calisiyor ama ates etmiyor" gibi gorunuyordu. Varsayilan AŞAMA 2
        # (takim karari 22.09): yarismada Otonom'un ilk asamasi o.
        if ad == "Otonom" and self.asama is None and "Aşama 2" in izin:
            self.asama = "Aşama 2"
            for a, b in self.asama_btns.items():
                b.setChecked(a == self.asama)
        self.sb_mod.setText(f'<span style="color:{BLUE}">Sistem:</span>&nbsp;{ad}')
        # B3: otonom nisan dongusu yalniz Otonom modda calisir. Mod degisince
        # kontrolcunun turev gecmisi sifirlanir (yeni moda gecince sicrama olmasin).
        if isinstance(getattr(self, "thread", None), VideoThread):
            self.inference_thread.otonom = (ad == "Otonom")
            self.inference_thread.nisanci.sifirla()
        if hasattr(self, "sag_mod_stack"):
            # Sag kolondaki QStackedWidget: 0 = Manuel, 1 = Otonom.
            self.sag_mod_stack.setCurrentIndex(0 if ad == "Manuel" else 1)
        # Otonom paneldeki gorev bilgisini guncelle
        if hasattr(self, "oto_gorev_lbl"):
            self._otonom_gorev_guncelle()
        self._asama_uygula()

    def _tus_yonu(self, event):
        """Klavye olayindan D-pad yonu. None = bizim tusumuz degil, Qt'ye birak.
        (Basma ve birakma AYNI haritayi okur — ikisi ayri yazilirsa biri unutulur.)"""
        if getattr(self, "mod", "") != "Manuel" or not hasattr(self, "pan_aci"):
            return None
        if event.isAutoRepeat():
            return None
        return TUS_YON.get(event.key())

    def _ates_kisayolu(self):
        """Gamepad A tusu — ATES butonuyla BIREBIR ayni sey (atesin tek kapisi `_ates_bas`).

        Buton devre disiysa (E-Stop) kisayol da gecmez: kisayolun butondan daha fazla
        yetkisi olamaz, yoksa E-Stop klavyeden asilabilir olurdu."""
        if not hasattr(self, "fire_btn") or not self.fire_btn.isEnabled():
            return
        self.fire_btn.setChecked(not self.fire_btn.isChecked())
        self._ates_bas()

    ATES_TUSLARI = frozenset({Qt.Key_Space, Qt.Key_B})
    ATES_KURMA_MS = 2000          # ates icin basili tutma suresi (takim karari 22.09)

    def _ates_kurma_iptal(self):
        if hasattr(self, "_ates_kurma"):
            self._ates_kurma.stop()
            self._ates_tuslari.clear()
            self._ates_kurma_kaynak = None
            self._ates_isigi()

    def _ates_isigi(self):
        """Koldaki L2/R2: ateş açıkken YANAR, kurma sürerken de yanar (basılı olan
        tuşlar gerçekten onlar). Kurma bitince ateş açılmadıysa söner."""
        acik = (getattr(self, "fire_btn", None) is not None and self.fire_btn.isChecked()) \
            or self._ates_kurma.isActive()
        for ad in ("l2", "r2"):
            self._kol_isik(ad, acik)

    def _ates_kurma_baslat(self, kaynak):
        """Ateş kurma sayacı: 2 sn dolunca ateş açılır. Kaynak klavye ya da kol."""
        self._ates_kurma_kaynak = kaynak
        self._ates_kurma.start(self.ATES_KURMA_MS)
        self._ates_isigi()
        self.sb_msg.setText(f'<span style="color:{RED}">●</span>&nbsp;'
                            f'ATEŞ: {"Space + B" if kaynak == "klavye" else "L2 + R2"} '
                            f'basılı tut… (2 sn)')

    def _ates_kurma_gecerli(self):
        """Sayaç dolduğunda tuşlar HÂLÂ basılı mı? (erken bırakma ateş açmamalı)"""
        if self._ates_kurma_kaynak == "klavye":
            return self._ates_tuslari == self.ATES_TUSLARI
        if self._ates_kurma_kaynak == "kol":
            return self._gp_ates_basili
        return False

    def _ates_kurma_bitti(self):
        """2 sn doldu: iki tus HALA basiliysa ateş acilir — yine TEK kapidan (`_ates_bas`).
        Buton devre disiysa (E-Stop) gecmez: klavyenin butondan fazla yetkisi olamaz."""
        self._ates_kurma.stop()        # tek atislik sayac: sonuc ne olursa olsun BITTI
        if not self._ates_kurma_gecerli():
            self._ates_isigi()
            return
        self._ates_kurma_kaynak = None
        if not hasattr(self, "fire_btn") or not self.fire_btn.isEnabled() \
                or self.fire_btn.isChecked():
            self._ates_isigi()
            return
        self.fire_btn.setChecked(True)
        self._ates_bas()
        self._ates_isigi()

    def _ates_tusu(self, event, basildi):
        """[Space]+[B] basili tutma. HER MODDA calisir (ATES butonu Otonom'da gorunmez
        ama klavye yolu moda bagli degildir). Doner: tus bizimse True."""
        if event.key() not in self.ATES_TUSLARI:
            return False
        if event.isAutoRepeat():
            return True
        if not basildi:
            if self._ates_kurma.isActive():
                self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;'
                                    f'Ateş iptal — tuş erken bırakıldı')
            self._ates_kurma_iptal()
            return True
        self._ates_tuslari.add(event.key())
        if self._ates_tuslari == self.ATES_TUSLARI and not self.fire_btn.isChecked():
            self._ates_kurma_baslat("klavye")
        return True

    def _tus_bas(self, event):
        """Klavyenin TEK kapisi (basma). Doner: tus bizimse True.
        Hareket `_dpad_press` -> `_aci_hareket` ile gider: ekran + KART (motor) birlikte."""
        # [Esc] = ateşi kes. Her modda ve her durumda; kesmek her zaman guvenlidir.
        if event.key() == Qt.Key_Escape:
            self._ates_kurma_iptal()
            self._ates_kes("ESC")
            return True
        if self._ates_tusu(event, basildi=True):
            return True
        yon = self._tus_yonu(event)
        if yon is None:
            return event.key() in TUS_YON           # tekrar/otonom: yine de gorunume birakma
        self._dpad_press(yon)
        return True

    def _tus_birak(self, event):
        if event.key() == Qt.Key_Escape:
            return True
        if self._ates_tusu(event, basildi=False):
            return True
        yon = self._tus_yonu(event)
        if yon is None:
            return event.key() in TUS_YON
        self._dpad_release(yon)
        return True

    def keyPressEvent(self, event):
        if not self._tus_bas(event):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not self._tus_birak(event):
            super().keyReleaseEvent(event)

    def _asama_sec(self, ad):
        if not self.asama_btns[ad].isEnabled():
            return
        self.asama = None if self.asama == ad else ad   # tekrar tikla -> kaldir
        for a, b in self.asama_btns.items():
            b.setChecked(a == self.asama)
        self._asama_uygula()

    def _asama_uygula(self):
        """Secili asamaya gore stack + pill + kural + algi davranisi gunceller."""
        self.stack.setCurrentIndex(self.ASAMA_IDX[self.asama])
        # Algi thread'ine aktif asamayi bildir (renk yalniz A3'te calisir). Thread heniz
        # olusmamis olabilir (ilk cagri __init__ sirasinda). DIKKAT: hasattr(self,"thread")
        # KULLANMA — QObject'in yerlesik thread() metodu yuzunden hep True doner; isinstance ile.
        if isinstance(getattr(self, "thread", None), VideoThread):
            self.thread.asama = self.ASAMA_IDX[self.asama]
            self.inference_thread.asama = self.ASAMA_IDX[self.asama]
        
        # Asama (gorev) degistiginde eski hedefe kilitli kalmamak icin kilidi sifirla
        algi.hedefi_birak_ve_bekle(0.0)

        if self.asama:
            self.asama_pill.setText(self.asama)
            self.asama_pill.setVisible(True)
            self.kural.setVisible(True)
            self._kural_guncelle()
            self._otonom_gorev_guncelle()
        else:
            self.asama_pill.setVisible(False)
            self.kural.setVisible(False)
            self._otonom_gorev_guncelle()

    def _kural_guncelle(self):
        kurallar = {
            "Aşama 1": (f'Zarftaki <b style="color:{RED}">SIRAYLA</b> imha &middot; '
                        f'Yanlış sıra: <b style="color:{RED}">−5 puan</b> &middot; '
                        f'Süre: <i style="color:{BLUE}">5 dk</i> &middot; Baraj: min. 30 puan &middot; Mod: Manuel'),
            "Aşama 2": (f'3 kol &times; <b style="color:{RED}">3 hedef</b> &middot; tur bitmeden imha &middot; '
                        f'sınıflandırma yok &middot; '
                        f'<b style="color:{RED}">3 tur üst üste 0 = elenme</b> &middot; Baraj: min. 20 puan'),
            "Aşama 3": (f'8 tur &middot; her tur <b style="color:{RED}">1 Düşman</b> + '
                        f'<i style="color:{BLUE}">2 Dost</i> &middot; tipe göre menzil '
                        f'(F-16: <b style="color:{RED}">10–15 m</b>) &middot; '
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
        self._kol_isik("start", aktif)      # koldaki Options: E-Stop suresince yanar
        self.thread.estop = aktif
        self.inference_thread.estop = aktif
        self.estop_btn.setText("▶ DEVAM ET" if aktif else "⏻ ACİL DURDUR")
        # 1. ATES kapisi (Yetenek 4) — kesme islemi tek yoldan (_ates_kes) gecer.
        if aktif:
            # DEVAM'da gecikmis bir acilis hareketi kendiliginden baslamasin.
            self._acilis_yukselisi_bekliyor = False
            self._ates_kes("ACİL DURDUR")
        self.fire_btn.setEnabled(not aktif)
        # 2. HAREKET kapisi (Yetenek 3): manuel yon kontrolleri kilitlenir.
        #    (Otonom nisan dongusu de AlgiThread._nisan_al icinde estop'ta durur.)
        if aktif:
            self._tuslari_birak()     # basili tutulan tusun tekrari da kesilmeli
        for ad in ("btn_up", "btn_down", "btn_left", "btn_right", "btn_center"):
            b = getattr(self, ad, None)
            if b is not None:
                b.setEnabled(not aktif)
        if hasattr(self, "bolge_status"):
            if aktif:
                self.bolge_status.setText("⏻ ACİL DURDURULDU — hareket ve ateş kesildi")
                self.bolge_status.setStyleSheet(T.durum_bandi(T.KIRMIZI))
            else:
                self.bolge_status.setText("● BÖLGE GÜVENLİ")
                self.bolge_status.setStyleSheet(T.durum_bandi(T.YESIL))
        if self.kontrol.bagli:
            d = self.kontrol.estop(aktif)
            if aktif:
                # Kart iki ekseni de oldugu yerde dondurdu ve konumunu bildirdi;
                # ekran o konuma cekilir. DEVAM'da hicbir sey sifirlanmaz — motorlar
                # tuttugu icin referans korunur (bkz. _estop_konum_uygula).
                self._estop_konum_uygula()
            self._esp_goster(d)

    def _estop_konum_uygula(self):
        """Kartin ACIL DURDURMADA bildirdigi gercek konumu ekrana yansitir.

        Kart acil durdurmada IKI EKSENI DE oldugu yerde dondurur (sartname Yetenek 3:
        "sistem durur") ve durdugu konumu yazar. Motor hedefe varmadan durduysa (or.
        90'a giderken 45'te E-Stop) ekrandaki "hedef" ile gercek konum ayrisir; bu
        yuzden ekrani kartin bildirdigi konuma cekeriz.

        Kart konum bildirmezse (eski firmware) ekrana DOKUNULMAZ — yanlis bir sayi
        gostermektense son bilinen hedefte kalmak yeglenir."""
        konum = getattr(self.kontrol, "estop_konum", None)
        if konum is None:
            return
        self.kontrol.estop_konum = None
        pan_ger, tilt_ger = konum
        # pan_ham SARMASIZ (birikimli) tutulur; kartin bildirdigi de sarmasizdir.
        self.pan_ham = pan_ger
        self.pan_aci = pan_ger % 360.0
        self.tilt_aci = tilt_ger
        if hasattr(self, "pan_val_lbl"):
            self._pan_goster()
            self._tilt_goster()
        # Otonom PD kontrolcusunun turev gecmisi de sifirlanmali: duraklamadan once
        # birikmis hata, devam edildiginde ani bir sicrama olarak cikmasin.
        if isinstance(getattr(self, "inference_thread", None), InferenceThread):
            self.inference_thread.nisanci.sifirla()

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
                self.bolge_status.setStyleSheet(T.durum_bandi(T.KIRMIZI))
            return
        ac = self.fire_btn.isChecked()
        d = self.kontrol.ates(ac)
        self.fire_btn.setText(ATES_METIN_ACIK if ac else ATES_METIN_KAPALI)
        self._ates_isigi()
        renk = RED if ac else GRN
        kaynak = "mock" if self.kontrol.mock_mu else self.kontrol.kaynak
        self.sb_msg.setText(f'<span style="color:{renk}">●</span>&nbsp;'
                            f'{"LAZER AKTİF" if ac else "Ateş kesildi"} ({kaynak})')
        self._esp_goster(d)

    def _ates_kes(self, sebep):
        """Devam eden atesi GUVENLIK gerekcesiyle keser (buton + donanim + alt cubuk).

        `_ates_bas` yalnizca butona BASILDIGI ANI denetler; ates surerken kosullar
        degisirse (or. gimbal atisa-yasak bolgeye girerse) kesme yolu burasidir.
        Ates zaten kapaliysa hicbir sey yapmaz."""
        if not self.fire_btn.isChecked() and not self.kontrol.durum.get("lazer"):
            return
        self.fire_btn.setChecked(False)
        self.fire_btn.setText(ATES_METIN_KAPALI)
        self._ates_isigi()
        if self.kontrol.bagli:
            self._esp_goster(self.kontrol.ates(False))
        self.sb_msg.setText(f'<span style="color:{RED}">●</span>&nbsp;Ateş kesildi — {sebep}')

    def _esp_goster(self, d):
        """Kontrol katmaninin ozetini alt cubuga yansitir.

        DIKKAT — burada yazan aci OLCULEN degil, KOMUT EDILEN hedeftir: karttaki kod
        konum geri bildirimi yapmiyor (yalniz insan-okur metin yaziyor). Etiket de bunu
        "hedef" diye soyler; olcum gibi gostermek en yaniltici hata olurdu."""
        if not d:
            return
        # ⚠ MOCK YESIL GORUNMEZ: sahte cihazda "Hazır" yazip yesil yanmak "kart takili"
        # demektir — operator kablosuz bir sistemi hazir saniyordu (kullanici sordu).
        # Sahte cihaz her zaman SARI ve acikca "sahte" yazar.
        if self.kontrol.mock_mu:
            self._ci("ESP32", AMB, "· sahte cihaz (kart takılı değil)")
        else:
            renk = {"Hazır": GRN, "ATEŞ": RED, "E-STOP": RED}.get(d["durum_ad"], BD2)
            self._ci("ESP32", renk, f'· {self.kontrol.kaynak} · {d["durum_ad"]}')
        self._ci("Lazer", RED if d["lazer"] else BD2,
                 f'· AKTİF %{d["lazer_guc"]}' if d["lazer"] else f'· kapalı · %{d["lazer_guc"]}')
        if self.kontrol.tilt_ayri:
            tilt = self.kontrol.tilt
            if tilt.mock_mu:
                renk, etiket = AMB, "· sahte kart"
            elif tilt.hazir:
                renk, etiket = GRN, f"· {tilt.aci:+.1f}°" if tilt.aci is not None else "· hazır"
            else:
                renk, etiket = RED, "· kalibrasyon / bağlantı bekleniyor"
            self._ci("Tilt Kartı", renk, etiket)
        else:
            self._ci("Tilt Kartı", BD2, "· kapalı")
        self._lazer_bilgi_yaz()          # LAZER kartinin basligi da ates durumunu gostersin
        # Kart kendi basina durdurulduysa (seri monitorden STOP, ileride donanim butonu)
        # bunu yalnizca metin cikisindan ogreniriz — kontrol.oku() yakalar. O durumda
        # arayuz de E-Stop'a gecmeli: ates kesilir, yon tuslari kilitlenir ve buton
        # "DEVAM ET" olur (yoksa kullanicinin sistemi geri baslatma yolu kalmaz).
        if d["estop"]:
            self._ates_kes("ESP32 durduruldu")
            btn = getattr(self, "estop_btn", None)
            if btn is not None and not btn.isChecked():
                btn.setChecked(True)
                self._estop_bas()

    def _esp_yokla(self):
        """Karttan gelen metinleri periyodik olarak alir (250 ms) ve ATESI TAZELER.

        Kart komut YOLLAMADAN da yazabilir (acilis banner'i, seri monitorden elle
        verilen STOP). Okunmazsa hem seri tampon dolar hem de o olaylardan haberimiz
        olmaz — bu yuzden yoklama gonderme degil, OKUMA yoklamasidir.

        ATES TAZELEMESI burada: lazer acikken karta duzenli "hala aciksin" denir.
        Bu dongu durursa (arayuz donar, uygulama kapanir, kablo kopar) kart lazeri
        KENDI keser — "kes" komutunun gitmesini beklemek guvenli degildir, cunku
        kesmenin gerektigi durumlarin cogunda komut zaten gidemiyordur."""
        if not self.kontrol.bagli:
            return
        if self.fire_btn.isChecked():
            self.kontrol.ates_tazele()
        yeni = self.kontrol.oku()

        # ACILIS HIZALAMASI + YUKSELISI. Hizalama operatorun komut vermesini
        # BEKLEYEMEZ: kart konumunu bildirir bildirmez arayuz ona uymali, cunku
        # acilis yukselisi de o degerden hesaplanir.
        self._acilis_hizala()
        # Namlu calisma araliginin ORTASINA (operator 0). Ilk STATE3 kart kilitliyken
        # gelebilir; deneme ancak kart hazir oldugunda tuketilir.
        self._acilis_yukselisini_dene()

        # FIRMWARE GUNCEL MI? Kart acilista kendi TILT_MAX'ini yazar; bizimkiyle
        # uyusmuyorsa firmware yuklenmemis demektir ve gimbal ESKI limitte takilir
        # (07.08: ekran 120 gosteriyordu, kart 90'da kirpiyordu — sebebi gorunmuyordu).
        if self.kontrol.firmware_uyumsuz:
            kart_deg, bizim = self.kontrol.firmware_uyumsuz
            self.kontrol.firmware_uyumsuz = None
            self.sb_msg.setText(
                f'<span style="color:{AMB}">●</span>&nbsp;<b>FIRMWARE ESKİ</b> — '
                f'kartın tilt tavanı {kart_deg:.0f}°, arayüzünki {bizim:.0f}°. '
                f'Gimbal {kart_deg:.0f}°\'de takılır; esp32/ klasörünü karta yükleyin.')

        # KART KENDILIGINDEN YENIDEN BASLADI MI? (besleme dalgalanmasi / brown-out)
        # Sessizce gecerse kartin konum sayaci sifirdan baslar ama ekrandaki aci eski
        # degerde kalir — sonraki her komut kaymis referansa gider ve kimse fark etmez.
        if self.kontrol.kart_resetlendi:
            self.kontrol.kart_resetlendi = False
            self.pan_aci = self.pan_ham = 0.0
            # Ayri kart resetten sonra sayacini fiziksel kol 0 varsayar; bu yeni
            # operator cercevesinde -30'dur. Fiziksel konum yine de bilinmez ve
            # asagidaki ciddi uyari korunur, fakat ekran/kart hedefi birbirinden
            # kopuk bir 0/-30 cifti gostermemelidir.
            self.tilt_aci = (self.kontrol.tilt_olculen
                             if getattr(self.kontrol, "tilt_ayri", False)
                             and self.kontrol.tilt_olculen is not None else 0.0)
            if hasattr(self, "pan_val_lbl"):
                self._pan_goster()
                self._tilt_goster()
            self._ates_kes("ESP32 yeniden başladı")
            # Dikey eksen ayri karttaysa uyari daha ciddidir: o firmware her
            # acilista "kol fiziksel olarak en asagidaki 0 konumunda" VARSAYAR.
            # Kol yukaridayken reset olduysa kartin bildirdigi aci artik gercek
            # degildir ve bunun disaridan hicbir belirtisi yoktur — operator kolu
            # gercekten 0'a indirmeden takibe devam etmemelidir.
            if getattr(self.kontrol, "tilt_ayri", False):
                self.sb_msg.setText(
                    f'<span style="color:{RED}">●</span>&nbsp;'
                    f'<b>TİLT KARTI YENİDEN BAŞLADI</b> — kart, kolun 0° konumunda '
                    f'olduğunu VARSAYIYOR. Kol yukarıdaysa gösterilen açı YANLIŞTIR: '
                    f'kolu fiziksel olarak en alta indirip doğrulayın.')
            else:
                self.sb_msg.setText(
                    f'<span style="color:{AMB}">●</span>&nbsp;'
                    f'<b>ESP32 YENİDEN BAŞLADI</b> — besleme kesilmiş olabilir. '
                    f'Açı referansı sıfırlandı, gimbal konumunu doğrulayın.')
        if yeni:
            self.sb_msg.setText(f'<span style="color:{TXT3}">ESP32:</span>&nbsp;{yeni[-1]}')
        self._esp_goster(self.kontrol.durum)

    def _live_blink_tick(self):
        """Kamera canli akisi varken kirmizi noktanin estetik yanip sonmesi (pulse)."""
        self.live_blink_state = not self.live_blink_state
        if self.live_blink_state:
            self.live_dot.setStyleSheet(T.nokta(T.KIRMIZI, 7))
        else:
            self.live_dot.setStyleSheet(T.nokta(T._a(T.KIRMIZI, 0.22), 7))

    def _kamera_sec(self, i):
        """Ust seritteki kamera secimi: bir harici kamera ya da 'Kapalı'."""
        veri = self.kam_sec.itemData(i)
        if veri is None:
            return
        if veri == "off":
            self.kamera.kapat()
        else:
            cihaz = next((c for c in kamera_mod.harici_kameralar() if bytes(c.id()) == veri), None)
            if cihaz is None:
                return
            self.kamera.ac(cihaz)
        self._cozunurluk_listesi()

    def _cozunurluk_listesi(self):
        """Secili kameranin DESTEKLEDIGI cozunurlukler (uydurma deger yok)."""
        cihaz = None if self.kamera.kapali else self.kamera.secili_cihaz()
        self.res_sec.blockSignals(True)
        self.res_sec.clear()
        if cihaz is None:
            self.res_sec.addItem("Çözünürlük", None)
            self.res_sec.setEnabled(False)
        else:
            boyutlar = sorted({(f.resolution().width(), f.resolution().height())
                               for f in cihaz.videoFormats()},
                              key=lambda r: r[0] * r[1], reverse=True)
            for w, h in boyutlar:
                self.res_sec.addItem(f"{w}x{h}", (w, h))
            self.res_sec.setEnabled(bool(boyutlar))
            hedef = self.kamera.istenen[:2]
            i = self.res_sec.findData(hedef)
            if i >= 0:
                self.res_sec.setCurrentIndex(i)
        self.res_sec.blockSignals(False)

    def _res_sec(self, i):
        veri = self.res_sec.itemData(i)
        if veri is None:
            return
        self.kamera.istenen = (veri[0], veri[1], self.kamera.istenen[2])
        self.kamera.yeniden_ac()

    def _kameralar_geldi(self, liste):
        """Harici kamera listesi degisti (acilis, takma, cikarma). Liste YALNIZ
        harici kameralari icerir — dahili/telefon/sanal kamera burada hic gorunmez."""
        self.kam_sec.blockSignals(True)
        self.kam_sec.clear()
        if self.kamera.dosya_adi:                     # DERINMAVI_CAM ile dosya/akis
            self.kam_sec.addItem(f"Dosya · {self.kamera.dosya_adi}", None)
            self.kam_sec.blockSignals(False)
            self._cozunurluk_listesi()
            return
        if liste:
            for c in liste:
                self.kam_sec.addItem(c.description(), bytes(c.id()))
        else:
            self.kam_sec.addItem("Kamera bulunamadı", None)
        self.kam_sec.addItem("Kapalı", "off")
        secili = "off" if self.kamera.kapali else self.kamera.secili_id
        i = self.kam_sec.findData(secili)
        self.kam_sec.setCurrentIndex(i if i >= 0 else 0)
        self.kam_sec.blockSignals(False)
        self._cozunurluk_listesi()

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
            # Alt cubuk KISA kalir: sinif adlarinin tamami sigmiyor ve satirin
            # sonu kirpiliyordu. Tam liste ipucu balonunda (tooltip) duruyor.
            sinif_sayisi = ozet.split(" ")[0]
            self.sb_model.setText(
                f'<span style="color:{BLUE}">{dosya}</span>&nbsp;'
                f'<small style="color:{AMB}">· {sinif_sayisi} sınıf · eksik: {adlar}</small>')
            self.sb_model.setToolTip(
                f"Model: {ozet}\n\nBu tipler modelde YOK, tespit EDİLEMEZ:\n  {adlar}\n\n"
                "Şartname 4 hedef tipi + nişan için balon gerektiriyor. Eksik tipler "
                "eğitim setine eklenip model yeniden eğitilmeli.")
            self.sb_msg.setText(f'<span style="color:{AMB}">●</span>&nbsp;'
                                f'Model {ozet} — şu tipler tespit EDİLEMEZ: {adlar}')
        else:
            self.sb_model.setText(f'<span style="color:{BLUE}">{dosya}</span>&nbsp;'
                                  f'<small style="color:{TXT3}">· {ozet.split(" ")[0]} sınıf · tam</small>')
            self.sb_model.setToolTip(f"Model: {ozet}\nŞartnamenin gerektirdiği tüm tipler mevcut.")

    def _durum_geldi(self, mesaj, hata):
        renk = AMB if hata else GRN
        self.sb_msg.setText(f'<span style="color:{renk}">●</span>&nbsp;{mesaj}')
        if "kapatıldı" in mesaj or "kapalı" in mesaj:
            self.video.setPixmap(QPixmap())
            self.video.setText("KAMERA KAPALI\n\n(Akış durduruldu)")
            self._ci("Kamera", TXT3, "· kapalı")
            if self.live_blink_timer.isActive():
                self.live_blink_timer.stop()
            self.live_badge.setVisible(False)
        elif hata:
            self.video.setPixmap(QPixmap())
            self.video.setText(mesaj)
            self._ci("Kamera", BD2, "· yok")
            if self.live_blink_timer.isActive():
                self.live_blink_timer.stop()
            self.live_badge.setVisible(False)

    def _ci(self, ad, renk, alt):
        dot, lbl = self.ci[ad]
        dot.setStyleSheet(T.nokta(renk, 6))
        base = ad
        lbl.setText(f'{base}<small style="color:{TXT3}">&nbsp;{alt}</small>')

    def _badge_stil(self, badge, tip):
        """Dost/düşman rozeti — Apple'ın tonlanmış (tinted) kapsül dili."""
        renk = {"Düşman": T.KIRMIZI, "Dost": T.AKSAN}.get(tip, T.L3)
        badge.setStyleSheet(T.rozet(renk))

    def _saat_guncelle(self):
        self.clk.setText(time.strftime("%H:%M:%S"))



    # ================= KARE GELDI =================
    def _kare_geldi(self, qimg, data):
        try:
            pix = QPixmap.fromImage(qimg).scaled(
                self.video.width(), self.video.height(),
                Qt.KeepAspectRatio, Qt.FastTransformation)
                
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            
            scale_x = pix.width() / qimg.width()
            scale_y = pix.height() / qimg.height()
            
            font = QFont("Consolas", 10, QFont.Bold)
            painter.setFont(font)
            pen = painter.pen()
            pen.setWidth(2)
            
            for bx in data.get("balonlar", []):
                x1, y1, x2, y2 = bx
                rx1, ry1, rx2, ry2 = x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y
                pen.setColor(QColor(60, 200, 235))
                painter.setPen(pen)
                painter.drawRect(QRectF(rx1, ry1, rx2 - rx1, ry2 - ry1))
                painter.drawText(QPointF(rx1, max(12.0, ry1 - 4)), "BALON")
                
            active_idx = data.get("active_idx", -1)
            estop = data.get("estop", False)
            for i, d in enumerate(data.get("dets", [])):
                # Etiket rengi: Dost ise Mavi, Düşman ise Kırmızı, aksi halde (Aşama 1/2) Yeşil
                if d.get("tip") == "Düşman":
                    color = QColor(255, 40, 40)  # Kirmizi
                elif d.get("tip") == "Dost":
                    color = QColor(40, 150, 255) # Mavi
                else:
                    color = QColor(40, 200, 40)  # Yesil
                
                pen.setColor(color)
                painter.setPen(pen)

                x1, y1, x2, y2 = d["box"]
                rx1, ry1, rx2, ry2 = x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y

                painter.drawRect(QRectF(rx1, ry1, rx2 - rx1, ry2 - ry1))

                tip_cv = {"Düşman": "Dusman", "Dost": "Dost"}.get(d["tip"])
                ad_cv = "?" if d["cls"] == "belirsiz" else algi.goster_ad_cv(d["cls"], d.get("ham", d["cls"]))

                txt1 = f"{tip_cv}" if tip_cv else ""
                # Hayalet: gercek bir tespit DEGIL, son bilinen konum. Guveni yapay
                # olarak 1 oldugu icin "%1" yazmak yanilticiydi (operator zayif ama
                # gercek bir tespit sanabilir) — acikca soyluyoruz.
                if d.get("hayalet"):
                    txt2 = f"{ad_cv} · KAYIP"
                else:
                    txt2 = f"{ad_cv} %{d['conf']}"
                
                fm = painter.fontMetrics()
                tw = max(fm.horizontalAdvance(txt1) if txt1 else 0, fm.horizontalAdvance(txt2))
                th = fm.height()
                
                toplam_h = th * (2 if txt1 else 1)
                # Kutunun biraz uzerinden baslasin (cok yukardaysa sifira yapissin)
                y_bg = max(ry1 - 5 - toplam_h, 0.0)
                
                painter.fillRect(QRectF(rx1, y_bg, tw + 8, toplam_h + 4), color)
                
                painter.setPen(QColor(255, 255, 255))
                if txt1:
                    painter.drawText(QPointF(rx1 + 4, y_bg + fm.ascent() + 2), txt1)
                    painter.drawText(QPointF(rx1 + 4, y_bg + th + fm.ascent() + 2), txt2)
                else:
                    painter.drawText(QPointF(rx1 + 4, y_bg + fm.ascent() + 2), txt2)
                if i == active_idx and not estop:
                    # Nisangah KUTU MERKEZINE degil, gimbalin gercekten nisan aldigi
                    # NOKTAYA cizilir: nisan noktasi balondur (maketin ALTINDA), govde
                    # merkezi degil. Ayni fonksiyon (nisan.nisan_noktasi) hem PD'yi hem
                    # bu cizimi besler — ikisi ayri hesaplansaydi ekran lazerin gittigi
                    # yeri YANLIS gosterirdi ve operator kalibrasyonu (balon_ofset)
                    # neye gore cevirecegini goremezdi.
                    hx, hy = nisan.nisan_noktasi(d["box"], data.get("balonlar", []))
                    cx, cy = hx * scale_x, hy * scale_y
                    pen.setColor(color)
                    painter.setPen(pen)
                    painter.drawEllipse(QPointF(cx, cy), 16, 16)
                    painter.drawLine(QPointF(cx - 22, cy), QPointF(cx + 22, cy))
                    painter.drawLine(QPointF(cx, cy - 22), QPointF(cx, cy + 22))
                    # Govde merkezinden nisan noktasina ince bir bag: operator artinin
                    # HANGI hedefe ait oldugunu govdeden ayrik dururken de gorsun.
                    gcx, gcy = (rx1 + rx2) / 2, (ry1 + ry2) / 2
                    pen.setWidth(1)
                    painter.setPen(pen)
                    painter.drawLine(QPointF(gcx, gcy), QPointF(cx, cy))
                    pen.setWidth(2)

            # --- Lazer Referans Nisangahi ---
            # Kare merkezi DEGIL: kamera-lazer boresight/paralaks ofseti kalibre
            # edilmisse (⚙ panel), nisangah lazerin GERCEKTEN vurdugu noktaya kayar.
            # Kalibrasyon yapilmadiysa (ofset=0) davranis eskisiyle aynidir.
            mcx = pix.width() / 2 + algi.AYAR.get("lazer_ofset_x", 0.0) * pix.width()
            mcy = pix.height() / 2 + algi.AYAR.get("lazer_ofset_y", 0.0) * pix.height()
            pen.setColor(QColor(255, 0, 0)) # Kirmizi
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(QPointF(mcx - 10, mcy), QPointF(mcx + 10, mcy))
            painter.drawLine(QPointF(mcx, mcy - 10), QPointF(mcx, mcy + 10))
            painter.setBrush(QColor(255, 0, 0))
            painter.drawEllipse(QPointF(mcx, mcy), 2, 2)
            painter.setBrush(Qt.NoBrush) # Reset brush

            painter.end()
            
            self.video.setPixmap(pix)
        except Exception as e:
            import traceback
            print("DRAWING ERROR:", e)
            traceback.print_exc()
        finally:
            self.thread.kare_islendi()

        # CANLI gostergesi: kare geliyorsa aktif ve yanip soner
        if not self.live_badge.isVisible():
            self.live_badge.setVisible(True)
        if not self.live_blink_timer.isActive():
            self.live_blink_timer.start()
        self._ci("Kamera", GRN, f"· {qimg.width()}×{qimg.height()}")

        # A3'te dost/dusman ayrimi var; A1-A2'de yok (hepsi hedef).
        a3 = data.get("a3", False)
        a = data.get("active")
        self._hedef_liste_guncelle(data.get("hedefler", []), a3)
        # Otonom paneli guncelle (her karede)
        self._otonom_ates_kontrol(data, estop)
        self._otonom_panel_guncelle(a, data, estop)

        self.sb_msg.setText(f'<span style="color:{GRN}">●</span>&nbsp;{data["mesaj"]}')
        self.sb_fps.setText(
            f"CAM&nbsp;<span style='color:{BLUE}'>{data['kamera_fps']:.1f}</span>"
            f"&nbsp;|&nbsp;"
            f"AI&nbsp;<span style='color:{BLUE}'>{data['fps']:.1f}</span>"
        )

    def _ates_engeli(self, a, data):
        """Otonom ates neden acilmadi? (baslik, ayrinti, renk) doner.

        Ates kapisi "nisan hatasi < olu bolge" olunca acilir; ikisi de ekranda
        gorunmedigi surece sistem sessizce ates etmez ve sebebi anlasilmaz —
        sahada tam bu yasandi (16.08: "dusmani taniyor ama ates etmiyor").
        """
        if not a:
            return "Hedef yok", "kilitlenecek düşman bulunamadı", TXT3
        hata = data.get("nisan_hata_px")
        olu = data.get("olu_bolge_px")
        if not hata or not olu:
            return "Nişan hesaplanmadı", "otonom nişan döngüsü çalışmıyor", AMB
        px, py = hata
        ox, oy = olu
        # Hangi eksen engelliyor: operator neyi duzeltecegini bilsin.
        eksen = []
        if abs(px) > ox:
            eksen.append(f"yatay {abs(px):.0f}>{ox:.0f}px")
        if abs(py) > oy:
            eksen.append(f"dikey {abs(py):.0f}>{oy:.0f}px")
        return "Nişan tutmuyor", " · ".join(eksen) or "—", AMB

    def _ates_kapi_yaz(self, baslik, ayrinti, renk):
        """Otonom paneldeki ATES KAPISI satirini gunceller (varsa)."""
        if not hasattr(self, "oto_ates_kapi"):
            return
        self.oto_ates_kapi.setText(f"{baslik} — {ayrinti}")
        self.oto_ates_kapi.setStyleSheet(T.yazi(T.ALTBASLIK, renk))

    def _otonom_ates_kontrol(self, data, estop):
        """Hedef olu bolgeye girdiginde (merkezde) dwell suresi kadar bekler,
        sonrasinda otonom olarak atesi baslatir ve ATES_SURESI kadar acik tutar."""
        if self.mod != "Otonom" or estop or self.asama not in ("Aşama 2", "Aşama 3"):
            self._otonom_hedef_merkezde_t = None
            self._ates_kapi_yaz("Otonom ateş kapalı",
                                "Aşama 2/3 + Otonom mod gerekir", AMB)
            if self._otonom_ates_aktif:
                self._otonom_ates_aktif = False
                if self.fire_btn.isChecked():
                    self.fire_btn.setChecked(False)
                    self._ates_kes("Otonom mod iptali / E-Stop")
            return

        simdi = time.time()
        a = data.get("active")
        # A2/A3'te sinif/taraf hafizasi ates izni DEGILDIR. Bu karede hedefin
        # kirmizisi gorunmuyorsa (veya kutu hayaletse) dwell'i sifirla ve
        # halihazirda acik olan atesi de derhal kes.
        if not data.get("kirmizi_kaniti", False) or (a and a.get("hayalet")):
            self._otonom_hedef_merkezde_t = None
            self._ates_kapi_yaz("Ateş engelli", "Anlık kırmızı hedef kanıtı yok", AMB)
            if self._otonom_ates_aktif:
                self._otonom_ates_aktif = False
                if self.fire_btn.isChecked():
                    self.fire_btn.setChecked(False)
                    self._ates_kes("Kırmızı hedef kanıtı kayboldu")
            return
        
        # Hedef merkezde ise zamani tut (Dwell Time tetikleyicisi)
        if a and data.get("merkezde", False):
            if self._otonom_hedef_merkezde_t is None:
                self._otonom_hedef_merkezde_t = simdi
            gecen = simdi - self._otonom_hedef_merkezde_t
            if gecen >= OTONOM_DWELL_SURE and not self._otonom_ates_aktif:
                # Dwell suresi doldu -> ATESI BASLAT
                self._otonom_ates_aktif = True
                self._otonom_ates_bitis_t = simdi + OTONOM_ATES_SURE
                if not self.fire_btn.isChecked():
                    self.fire_btn.setChecked(True)
                    self._ates_bas()
            elif not self._otonom_ates_aktif:
                self._ates_kapi_yaz("Nişanda — bekleniyor",
                                    f"dwell {gecen:.1f} / {OTONOM_DWELL_SURE:.1f} sn", BLUE)
        else:
            self._otonom_hedef_merkezde_t = None
            if not self._otonom_ates_aktif:
                self._ates_kapi_yaz(*self._ates_engeli(a, data))

        # Ates suresi doldu mu veya hedef tamamen kayboldu mu kontrolu
        if self._otonom_ates_aktif:
            self._ates_kapi_yaz("● ATEŞ",
                                f"kalan {max(0.0, self._otonom_ates_bitis_t - simdi):.1f} sn", RED)
            # Eger hedef hic yoksa (active = None) veya ates suresi dolduysa LAZERI KES
            if not a or simdi >= self._otonom_ates_bitis_t:
                self._otonom_ates_aktif = False
                if self.fire_btn.isChecked():
                    self.fire_btn.setChecked(False)
                    sebep = "Otomatik ateş süresi doldu" if a else "Hedef kaybedildi"
                    self._ates_kes(sebep)
                
                # Eger ates sure doldugu icin bittiyse (basarili imha), juri onayi icin bekle!
                if a and simdi >= self._otonom_ates_bitis_t:
                    algi.hedefi_birak_ve_bekle(OTONOM_BEKLEME_SURE)

    def _otonom_panel_guncelle(self, active_hedef, data, estop):
        """Otonom moddaki takip ve nisan durumunu (sag kolon paneli) gunceller."""
        if not hasattr(self, "oto_durum_baslik"):
            return

        # 1. Takip Durumu
        if active_hedef:
            self.oto_durum_dot.setStyleSheet(T.nokta(T.YESIL, 10))
            self.oto_durum_baslik.setText("Hedef Kilitli")
            self.oto_durum_baslik.setStyleSheet(T.yazi(T.BASLIK3, T.YESIL, "background: transparent;"))
            
            taraf = f" · {active_hedef['tip']}" if data.get("a3") else ""
            self.oto_durum_alt.setText(f"{active_hedef['ad']}{taraf} · %{active_hedef['conf']} güven")
        elif estop:
            self.oto_durum_dot.setStyleSheet(T.nokta(T.KIRMIZI, 10))
            self.oto_durum_baslik.setText("ACİL DURDURMA")
            self.oto_durum_baslik.setStyleSheet(T.yazi(T.BASLIK3, T.KIRMIZI, "background: transparent;"))
            self.oto_durum_alt.setText(data.get("mesaj", ""))
        else:
            self.oto_durum_dot.setStyleSheet(T.nokta(T.SARI, 10))
            self.oto_durum_baslik.setText("Hedef Aranıyor...")
            self.oto_durum_baslik.setStyleSheet(T.yazi(T.BASLIK3, T.SARI, "background: transparent;"))
            self.oto_durum_alt.setText("Görüş alanında hedef yok")

        # 2. Bolge Durumu
        if hasattr(self, "bolge_status"):
            # Manuel paneldeki ayni metin ve stili (guvenli/yasak) kopyala
            self.oto_bolge_status.setText(self.bolge_status.text())
            self.oto_bolge_status.setStyleSheet(self.bolge_status.styleSheet())

        # 3. Nisan Durumu (PD aktif mi)
        if hasattr(self, "pan_val_lbl"):
            self.oto_pan_lbl.setText(f"Azimut: {self.pan_val_lbl.text()}")
            self.oto_tilt_lbl.setText(f"Yükseliş: {self.tilt_val_lbl.text()}")

        if self.mod == "Otonom":
            if estop:
                self.oto_nisan_durum.setText("Sistem durduruldu")
                self.oto_nisan_durum.setStyleSheet(T.yazi(T.CAGRI, T.KIRMIZI))
            elif active_hedef:
                simdi = time.time()
                if simdi < getattr(self, "_nisan_mesgul_ta", 0):
                    self.oto_nisan_durum.setText("Konumlanıyor...")
                    self.oto_nisan_durum.setStyleSheet(T.yazi(T.CAGRI, T.AKSAN))
                else:
                    self.oto_nisan_durum.setText("Takip aktif")
                    self.oto_nisan_durum.setStyleSheet(T.yazi(T.CAGRI, T.YESIL))
            else:
                self.oto_nisan_durum.setText("Bekleniyor")
                self.oto_nisan_durum.setStyleSheet(T.yazi(T.CAGRI, T.L3))

        # 4. Lazer Durumu
        acik = bool(getattr(self, "kontrol", None) and self.kontrol.bagli and self.kontrol.lazer_acik)
        self.oto_lazer_durum.setText(f"● ATEŞ AKTİF · %{self.lazer_guc}" if acik else f"○ Lazer Kapalı · %{self.lazer_guc}")
        self.oto_lazer_durum.setStyleSheet(
            T.yazi(T.GOVDE_VURGU, T.KIRMIZI if acik else T.L3))

    def _otonom_gorev_guncelle(self):
        """Otonom paneldeki aktif gorev aciklamasini gunceller."""
        if not hasattr(self, "oto_gorev_lbl"):
            return
            
        if self.asama == "Aşama 2":
            self.oto_gorev_lbl.setText("Sürü Saldırısı İmhası\nSıra ve tip gözetmeksizin tüm hedefler düşman kabul edilir.")
        elif self.asama == "Aşama 3":
            self.oto_gorev_lbl.setText("Farklı Katmanlarda İmha\nYalnızca düşman (kırmızı) hedefler vurulur. Dost (camgöbeği) hedeflere ateş yasaktır.")
        else:
            self.oto_gorev_lbl.setText("Aşama seçilmedi")

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
        # Inference ve kamera tarama thread'leri de DURDURULMALI: calisan bir
        # QThread yok edilirse Qt "Destroyed while thread is still running" deyip
        # uygulamayi abort ettirir — kapanista cokme olarak gorunuyordu.
        if hasattr(self, "inference_thread"):
            self.inference_thread.durdur()
            # İlk CPU çıkarımı birkaç saniye sürebilir. QThread hâlâ çalışırken
            # pencereyi yok etmek Qt sürecini abort ettirir.
            if not self.inference_thread.wait(30000):
                self.sb_msg.setText("Model işlemi sonlanıyor; pencereyi yeniden kapatın")
                e.ignore()
                return
        if hasattr(self, "kamera"):
            self.kamera.durdur()
        if hasattr(self, "esp_timer"):
            self.esp_timer.stop()      # kapanan port yoklanmasin
        if hasattr(self, "gp_timer"):
            self.gp_timer.stop()
            self.gamepad.kapat()
        if self.kontrol.bagli:
            self.kontrol.estop(True)   # kapanista guvenli duruma al
            self.kontrol.kapat()
        e.accept()

    # ================= STIL =================
    def _stil(self):
        """Tum gorunum app/tasarim.py'den gelir (Apple macOS 27 UI Kit degerleri).

        Burada artik TEK BIR renk/olcu yazili degil: stil sayfasi tasarim
        katmaninda uretilir, burada yalnizca uygulanir. Ayni stil hem pencereye
        hem QApplication'a verilir — ikincisi ayri ust pencerelerin (acilir
        listeler, ipucu baloncuklari) da ayni dili konusmasini saglar."""
        qss = T.qss()
        self.content.setStyleSheet(qss)
        if QApplication.instance():
            QApplication.instance().setStyleSheet(qss)


def main():
    app = QApplication(sys.argv)
    app.setFont(T.uygulama_fontu())      # SF Pro varsa o, yoksa en yakın karşılığı
    w = MainWindow()
    w.showMaximized()   # acilista ekrani tam kapla (yan bosluk kalmasin)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
