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
from PySide6.QtGui import QImage, QPixmap, QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
    QSizePolicy, QButtonGroup,
    QGraphicsView, QGraphicsScene, QStackedWidget,
    QSlider, QCheckBox, QSpinBox, QScrollArea,
)

import algi
import nisan
import gamepad as gamepad_mod
import kontrol as kontrol_mod
import protokol as P          # hiz duzeyi/durum sabitleri — TEK KAYNAK (bkz. protokol.py)

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

# D-pad tuslari: sabit kutu. Ustteki baslik/aci gostergesi kartlari kucultulerek
# acilan yer buraya verildi — tuslar 52px'ten 64px'e buyudu, aralari da genisledi
# (bkz. _dpad_izgarasi spacing). Dort varyant (kenar/merkez x normal/basili) ayni
# iki sablondan uretilir.
_DPAD_GOVDE = ("QPushButton {{ "
               "  background: {arka}; "
               "  border: {kalinlik} solid {kenar}; "
               "  border-radius: 8px; "
               "  color: {yazi}; "
               "  font-size: {punto}; "
               "  font-weight: 700; "
               "  min-width: 86px; max-width: 86px; "
               "  min-height: 64px; max-height: 64px; "
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

# Adim hassasiyeti butonlari (1°/5°/10°): D-pad ile ayni mantik — tek govde sablonu,
# secili/normal yalnizca renk-kalinlikta ayrisir (secilide hover kurali yok).
_ADIM_GOVDE = ("QPushButton {{ background: {arka}; border: {kalinlik} solid {kenar}; "
               "border-radius: 8px; color: {yazi}; font-size: 12px;{ek} }} ")
ADIM_STIL_SECILI = _ADIM_GOVDE.format(arka="#eaf1f8", kalinlik="1.5px", kenar="#1e4b7a",
                                      yazi="#1e4b7a", ek=" font-weight: 700;")
ADIM_STIL_NORMAL = (_ADIM_GOVDE.format(arka="#ffffff", kalinlik="1px", kenar="#dfe4ea",
                                       yazi="#5f6b78", ek="")
                    + "QPushButton:hover { border-color: #c3d3e2; color: #2b3540; }")

# ATES butonu metinleri — tek kaynak (uc yerde ayri ayri yazilinca biri unutuluyordu).
ATES_METIN_KAPALI = "A T E Ş   [L]"
ATES_METIN_ACIK = "ATEŞİ KES   [L]"

# Klavye -> D-pad yonu (WASD + ok tuslari; R/C/Space = merkeze al).
TUS_YON = {Qt.Key_W: "up", Qt.Key_Up: "up", Qt.Key_S: "down", Qt.Key_Down: "down",
           Qt.Key_A: "left", Qt.Key_Left: "left", Qt.Key_D: "right", Qt.Key_Right: "right",
           Qt.Key_R: "center", Qt.Key_C: "center", Qt.Key_Space: "center"}

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

    def __init__(self, veri):
        super().__init__()
        self.veri = veri
        self._calis = True
        self.model = None
        self.asama = 3                      # 1/2/3/0 — SARTNAME davranisi
        self.estop = False
        self.otonom = False                 # Otonom modda mi
        self.nisanci = nisan.PDNisanci()

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

                if kare is None or sira == son_islenen_sira or self.model is None:
                    self.msleep(3)
                    continue

                son_islenen_sira = sira
                frame = kare.copy()

                dets, balonlar, active_idx = algi.analiz_et(self.model, frame, self.estop, self.asama)

                merkezde = False
                aktif_det = dets[active_idx] if 0 <= active_idx < len(dets) else None
                if self.otonom and not self.estop and aktif_det is not None:
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
                        merkezde = self.veri.merkezde
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
                else:
                    self.nisanci.sifirla()

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
# Tilt kartinin nabiz periyodu (ms). Firmware 350 ms sessizlikte kendini kilitler
# (tilt_surucu.ZAMAN_ASIMI_MS); bu deger asimin ~1/3'u olacak sekilde secildi ki
# arka arkaya iki nabiz kacsa bile kart kilitlenmesin.
TILT_NABIZ_MS = 100

NISAN_MESGUL_ORANI = 0.4
NISAN_MIN_ARALIK = 0.04


class VideoThread(QThread):
    kare_hazir = Signal(QImage, dict)
    durum = Signal(str, bool)               # mesaj, hata_mi
    kameralar_bulundu = Signal(list)        # [{"index": int, "name": str, "is_default": bool}, ...]

    def __init__(self, inference_thread, veri):
        super().__init__()
        self._calis = True
        self.estop = False
        self.asama = 3                      
        self.kaynak_istegi = None           
        self.veri = veri
        self.inference_thread = inference_thread
        self._gui_mesgul = False
        self._hedef_son_gorulen = {}   # titresim onleme: {track_id: (son_gorulen_zaman, hedef_dict)}

    def kare_islendi(self):
        self._gui_mesgul = False

    def run(self):
        self.durum.emit("Kamera aranıyor…", False)
        cap = algi.open_camera()
        if cap is None:
            self.durum.emit("Kamera bulunamadı — bağlı mı / başka uygulama kullanıyor mu?", True)
            return

        if algi.AKTIF_INDEX is not None:
            qt_cams = algi.kameralari_listele_qt()
            if qt_cams:
                self.kameralar_bulundu.emit(qt_cams)
            else:
                self.kameralar_bulundu.emit([{"index": algi.AKTIF_INDEX,
                                              "name": f"Kamera {algi.AKTIF_INDEX}",
                                              "is_default": True}])

        self.durum.emit("Sistem hazır", False)

        okuyucu = algi.KameraOkuyucu(cap)
        son_sira = None
        t_kamera, kamera_fps = time.perf_counter(), 0.0
        
        try:
            while self._calis:
                if self.kaynak_istegi is not None:
                    istek = self.kaynak_istegi
                    self.kaynak_istegi = None
                    algi.takip_sifirla()   
                    self.inference_thread.nisanci.sifirla()
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
                    self.durum.emit("Sistem hazır", False)

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

                if self._gui_mesgul:
                    self.msleep(3)
                    continue

                frame, sira = okuyucu.oku(son_sira)
                if frame is None:              
                    self.msleep(3)
                    continue
                son_sira = sira
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
            okuyucu.kapat()

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
        # Motor hiz duzeyi (ESP32'deki iki step motorun tavan hizi). Her iki modda da
        # gecerli oldugu icin manuel panelde DEGIL, sag kolonun altinda durur.
        self.hiz_seviye = P.HIZ_VARSAYILAN
        self._nisan_son_t = None   # otonom PD komutlari icin hiz-siniri zamanlayicisi
        self._nisan_mesgul_ta = 0.0   # bu zamana kadar yeni otonom komutu KABUL EDILMEZ
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
        self.live_dot.setVisible(False)

        # Kontrol katmani (mock-ESP32 varsayilan; DERINMAVI_ESP env ile gercek porta gecilir)
        self.kontrol = kontrol_mod.Kontrol()
        if self.kontrol.bagli:
            etiket = "· mock (simülasyon)" if self.kontrol.mock_mu else f"· {self.kontrol.kaynak}"
            self._ci("ESP32", AMB if self.kontrol.mock_mu else GRN, etiket)
            self._ci("Seri Port", AMB if self.kontrol.mock_mu else GRN, "· 115200 baud")
            self._hiz_sec(self.hiz_seviye)   # acilista karti ekrandakiyle ayni hiza al
            # DIKEY EKSEN AYRI KARTTAYSA (ESP32-S3 + HSD57, kol-biyel): mekanik
            # tavan 180 degil 60'tir; kaydiricilar ve yasak alan sinirlari buna
            # cekilir. Eski donanimda bu cagri hicbir seyi degistirmez.
            self._tilt_tavan_uygula()
            # ESP32 durum yoklamasi: motorlar hedefe YURURKEN konum, lazer ve (varsa)
            # DONANIMSAL E-Stop yalnizca boyle gorulur — komut gonderilmedigi surece
            # arayuz kartin durumunu ogrenemez. Bos komut hicbir seyi degistirmez.
            self.esp_timer = QTimer(self)
            self.esp_timer.timeout.connect(self._esp_yokla)
            # Periyot ATES TAZELEMESINI de belirler: bu dongu durursa kart lazeri keser.
            self.esp_timer.start(P.ATES_TAZELE_MS)
            # TILT KARTININ NABZI AYRI VE DAHA SIK. Firmware 350 ms sessizlikte
            # kendini kilitler; 250 ms'lik yoklama yalnizca 100 ms pay birakir ve
            # GUI'nin kisa bir takilmasi (YOLO cikarimi, kamera acilisi, pencere
            # tasima) karti kilitler — kilit acilana kadar MOTOR DURUR ve kullanici
            # "hareket etmiyor" diye gorur.
            # Ayri zamanlayici "arayuz donarsa kart kilitlenir" guvenligini BOZMAZ:
            # bu timer da GUI is parcaciginda calisir, arayuz donarsa o da durur.
            if self.kontrol.tilt_ayri:
                self.tilt_timer = QTimer(self)
                self.tilt_timer.timeout.connect(self.kontrol.tilt.yokla)
                self.tilt_timer.start(TILT_NABIZ_MS)
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

        # Kamera secici listesini HEMEN doldur (kamera acilisini bekleme)
        try:
            self._kameralar_geldi(algi.kameralari_listele_qt())
        except Exception:
            pass

        # algi thread (3-thread architecture)
        self.veri = OrtakVeri()
        
        self.inference_thread = InferenceThread(self.veri)
        self.inference_thread.asama = self.ASAMA_IDX[self.asama]
        self.inference_thread.otonom = (self.mod == "Otonom")
        self.inference_thread.model_bilgi.connect(self._model_bilgi_geldi)
        self.inference_thread.nisan_komut.connect(self._nisan_geldi)
        self.inference_thread.start()
        
        self.thread = VideoThread(self.inference_thread, self.veri)
        self.thread.asama = self.ASAMA_IDX[self.asama]
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
        
        self.res_sec = QComboBox()
        self.res_sec.setObjectName("camsel")
        self.res_sec.addItem("Çözünürlük", None)
        self.res_sec.currentIndexChanged.connect(self._res_sec)
        krh.addWidget(self.res_sec, 0, Qt.AlignVCenter)
        
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
        idx = self.kam_sec.currentData()
        if idx is not None:
            self.thread.kaynak_istegi = idx

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
        v.setSpacing(12)

        # Manuel ve Otonom modlar FARKLI paneller gosterir. QStackedWidget ile
        # gecis yapilir — setVisible() QGraphicsProxyWidget icinde guvenilir
        # degil (layout yeniden hesaplanmiyordu). Sayfa 0 = Manuel, Sayfa 1 = Otonom.
        self.sag_mod_stack = QStackedWidget()
        self.manuel_panel = self._manuel_kontrol_panel()
        self.otonom_panel = self._otonom_kontrol_panel()
        self.sag_mod_stack.addWidget(self.manuel_panel)   # 0 = Manuel
        self.sag_mod_stack.addWidget(self.otonom_panel)    # 1 = Otonom
        v.addWidget(self.sag_mod_stack, 1)

        # HEDEFLER / Motor Hizi / Lazer: ucu de hem Manuel hem Otonom modda gecerli
        # oldugu icin sabit alanda durur, moda gore gizlenmez.
        v.addWidget(self._hedefler_karti(), 0)
        v.addWidget(self._hiz_karti(), 0)
        v.addWidget(self._lazer_karti(), 0)

        return kol

    def _otonom_kontrol_panel(self):
        """Otonom mod paneli — takip durumu, aktif hedef bilgisi ve nisan durumu.

        Manuel panelin yerini alir; Otonom modda operatorun gormesi gereken
        bilgi D-pad/ATES degil, sistemin NEYI TAKIP ETTIGINI ve ne durumda oldugudur."""
        mk = QFrame()
        mk.setObjectName("panelk")
        mv = QVBoxLayout(mk)
        mv.setContentsMargins(16, 10, 16, 10)
        mv.setSpacing(8)

        # Baslik
        mt = QLabel("OTONOM TAKİP DURUMU")
        mt.setObjectName("ph")
        mt.setStyleSheet("font-size:10px; padding-bottom:4px;")
        mv.addWidget(mt)

        # Takip durumu gostergesi (kilitli / araniyor / E-Stop)
        self.oto_durum_frame = QFrame()
        self.oto_durum_frame.setObjectName("engok")
        dh = QHBoxLayout(self.oto_durum_frame)
        dh.setContentsMargins(11, 9, 11, 9)
        dh.setSpacing(8)

        self.oto_durum_dot = QLabel()
        self.oto_durum_dot.setFixedSize(10, 10)
        self.oto_durum_dot.setStyleSheet(f"background:{AMB};border-radius:5px;")
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
        nisan_kart.setStyleSheet(f"background:{CARD}; border-radius:8px;")
        nv = QVBoxLayout(nisan_kart)
        nv.setContentsMargins(12, 8, 12, 8)
        nv.setSpacing(4)
        nt = QLabel("NİŞAN KONTROLÜ")
        nt.setStyleSheet(f"font-size:10px; font-weight:700; color:{TXT2}; letter-spacing:0.5px;")
        nv.addWidget(nt)

        self.oto_nisan_durum = QLabel("Bekleniyor")
        self.oto_nisan_durum.setStyleSheet(f"font-size:12px; color:{TXT3}; padding:2px 0;")
        nv.addWidget(self.oto_nisan_durum)

        # ATES KAPISI: otonom ates neden acilmadi/acildi. Bu satir olmadan sistem
        # sessizce ates etmiyor ve sebebi gorulmuyordu (bkz. _ates_engeli).
        self.oto_ates_kapi = QLabel("—")
        self.oto_ates_kapi.setStyleSheet(f"font-size:11px; color:{TXT3}; padding:2px 0;")
        self.oto_ates_kapi.setWordWrap(True)
        nv.addWidget(self.oto_ates_kapi)

        # Aci bilgisi (pan/tilt)
        aci_row = QHBoxLayout()
        aci_row.setSpacing(16)
        self.oto_pan_lbl = QLabel("Azimut: 0.0°")
        self.oto_pan_lbl.setStyleSheet(f"font-family:{FM}; font-size:12px; color:{TXT2};")
        self.oto_tilt_lbl = QLabel("Yükseliş: 0.0°")
        self.oto_tilt_lbl.setStyleSheet(f"font-family:{FM}; font-size:12px; color:{TXT2};")
        aci_row.addWidget(self.oto_pan_lbl)
        aci_row.addWidget(self.oto_tilt_lbl)
        aci_row.addStretch(1)
        nv.addLayout(aci_row)

        mv.addWidget(nisan_kart)

        # Aktif gorev bilgisi
        gorev_kart = QFrame()
        gorev_kart.setStyleSheet(f"background:{CARD}; border-radius:8px;")
        gv = QVBoxLayout(gorev_kart)
        gv.setContentsMargins(12, 8, 12, 8)
        gv.setSpacing(4)
        gt = QLabel("GÖREV BİLGİSİ")
        gt.setStyleSheet(f"font-size:10px; font-weight:700; color:{TXT2}; letter-spacing:0.5px;")
        gv.addWidget(gt)

        self.oto_gorev_lbl = QLabel("Aşama seçilmedi")
        self.oto_gorev_lbl.setStyleSheet(f"font-size:12px; color:{TXT3}; padding:2px 0;")
        self.oto_gorev_lbl.setWordWrap(True)
        gv.addWidget(self.oto_gorev_lbl)

        mv.addWidget(gorev_kart)

        # Bolge durumu (otonom icin de)
        self.oto_bolge_status = QLabel("● BÖLGE GÜVENLİ")
        self.oto_bolge_status.setAlignment(Qt.AlignCenter)
        self.oto_bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
        mv.addWidget(self.oto_bolge_status)

        mv.addStretch(1)

        # Otonom ATES bilgisi — buton YOK ama lazer durumu gosterilir
        self.oto_lazer_durum = QLabel("○ Lazer kapalı")
        self.oto_lazer_durum.setAlignment(Qt.AlignCenter)
        self.oto_lazer_durum.setStyleSheet(f"font-size:13px; font-weight:600; color:{TXT3}; padding:6px 0;")
        mv.addWidget(self.oto_lazer_durum)

        return mk

    def _hedefler_karti(self):
        """HEDEFLER — kamerada tanimlanan ve etiketlenen hedeflerin numarali listesi.

        Motor Hizi/Lazer gibi stack DISINDA: hem Manuel hem Otonom modda gorunur.
        Bir isme tiklamak o hedefi ELLE kilitler (algi.hedef_sec) — otomatik kilitle
        AYNI mekanizmayi (_kilitli_track_id) kullanir, tetikleyici operatordur.
        Kilitli hedefe tekrar tiklamak kilidi birakir, otomatik secime doner."""
        kart = QFrame()
        kart.setObjectName("panelk")
        kv = QVBoxLayout(kart)
        kv.setContentsMargins(19, 11, 19, 13)
        kv.setSpacing(6)

        t = QLabel("HEDEFLER")
        t.setObjectName("ph")
        kv.addWidget(t)

        # Yatay, TEK SATIRLIK liste: yeni hedef tanindikca kart DIKEY buyumesin
        # (alttaki Motor Hizi/Lazer kartlarini asagi itmesin). Isimler yan yana
        # dizilir; sigmayan kisim yatay kaydirmayla gorulur (dikey kaydirma YOK).
        self.hedef_scroll = QScrollArea()
        self.hedef_scroll.setWidgetResizable(True)
        self.hedef_scroll.setFrameShape(QFrame.NoFrame)
        self.hedef_scroll.setFixedHeight(34)
        self.hedef_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.hedef_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hedef_scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")

        hedef_ic = QWidget()
        hedef_ic.setStyleSheet("background:transparent;")
        self.hedef_liste_lay = QHBoxLayout(hedef_ic)
        self.hedef_liste_lay.setContentsMargins(0, 0, 0, 0)
        self.hedef_liste_lay.setSpacing(4)
        self.hedef_scroll.setWidget(hedef_ic)
        kv.addWidget(self.hedef_scroll)

        self.hedef_bos_lbl = QLabel("Hedef bekleniyor…")
        self.hedef_bos_lbl.setStyleSheet(f"font-size:12px; color:{TXT3}; padding:2px 0;")
        kv.addWidget(self.hedef_bos_lbl)

        return kart

    def _hedef_liste_guncelle(self, hedefler, a3):
        """HEDEFLER kartini gunceller: her hedef icin '<no>- <isim>' YAN YANA (yatay).

        Kart dikey buyumez — cok hedef varsa yatay kaydirma devreye girer.
        Renk kilit/taraf durumunu gosterir (kilitli = RED/GRN, A3'te dost = BLUE);
        bu, video uzerindeki kutu etiketinin SABIT yesil renginden ayri ve bagimsizdir."""
        lay = self.hedef_liste_lay
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.hedef_bos_lbl.setVisible(not hedefler)
        for i, hh in enumerate(hedefler):
            tid = hh.get("id")
            kilitli = hh["aktif"]
            if kilitli:
                renk = RED if a3 else GRN
            elif a3 and hh["tip"] == "Dost":
                renk = BLUE
            else:
                renk = TXT2
            # A3'te Dost/Dusman etiketini de goster ki ayni tip hedeflerde karismasin
            if a3 and hh.get("tip"):
                btn_text = f"{i + 1}- {hh['tip']} · {hh['ad']}"
            else:
                btn_text = f"{i + 1}- {hh['ad']}"
            btn = QPushButton(btn_text)
            btn.setObjectName("hedefsatir")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setEnabled(tid is not None)   # ID'siz kutu (nadir) elle kilitlenemez
            btn.setStyleSheet(
                "QPushButton#hedefsatir { text-align:left; border:none; background:transparent; "
                f"padding:3px 4px; font-size:13px; font-weight:{700 if kilitli else 600}; color:{renk}; }} "
                "QPushButton#hedefsatir:hover:enabled { background:rgba(18,88,168,0.10); border-radius:5px; }")
            btn.clicked.connect(lambda checked=False, t=tid: self._hedef_secildi(t))
            lay.addWidget(btn)
        lay.addStretch(1)   # butonlar SOLA yaslanir, sagda bosluk kalir tasmaz

    def _hedef_secildi(self, track_id):
        """HEDEFLER listesinden ELLE hedef secimi.

        Tek kapi `algi.hedef_sec` — otomatik kilitle AYNI mekanizmadir (_kilitli_track_id),
        yalniz tetikleyici operatordur. Ayni (kilitli) hedefe tekrar tiklamak kilidi
        birakir, bir sonraki karede otomatik secime doner."""
        if track_id is None:
            return
        yeni = None if algi.kilitli_hedef() == track_id else track_id
        algi.hedef_sec(yeni)

    def _hiz_karti(self):
        """MOTOR HIZI — ESP32'deki iki step motorun tavan hizi + ivmesi (3 kademe).

        Duzeyler protokol.HIZ_TABLO'da (tek kaynak); burada yalnizca secim yapilir.
        Karta iki satir gider: S<derece/sn> (tavan hiz) ve A<derece/sn²> (ivme);
        step'e cevirmek kartin isi (iki eksenin disli orani farkli)."""
        kart = QFrame()
        kart.setObjectName("panelk")
        kv = QVBoxLayout(kart)
        kv.setContentsMargins(19, 11, 19, 13)
        kv.setSpacing(7)

        ust = QHBoxLayout()
        t = QLabel("MOTOR HIZI")
        t.setObjectName("ph")
        ust.addWidget(t, 1)
        self.hiz_bilgi = QLabel()
        self.hiz_bilgi.setObjectName("engsub")
        ust.addWidget(self.hiz_bilgi, 0, Qt.AlignVCenter)
        kv.addLayout(ust)

        satir, self.hiz_btns = self._seviye_butonlari(
            [(s, P.HIZ_AD[s]) for s in P.HIZ_SEVIYELER], self.hiz_seviye, self._hiz_sec)
        kv.addLayout(satir)
        self._hiz_bilgi_yaz()
        return kart

    def _hiz_bilgi_yaz(self):
        hiz, ivme = P.HIZ_TABLO[self.hiz_seviye]
        self.hiz_bilgi.setText(f"{hiz:.0f}°/s · ivme {ivme:.0f}°/s²")

    def _hiz_sec(self, seviye):
        """Hiz duzeyini degistirir ve ESP32'ye bildirir (mock/gercek fark etmez)."""
        self.hiz_seviye = seviye
        for v, b in self.hiz_btns.items():
            b.setChecked(v == seviye)
            self._step_btn_stil_guncelle(b, v == seviye)
        self._hiz_bilgi_yaz()
        if getattr(self, "kontrol", None) and self.kontrol.bagli:
            self._esp_goster(self.kontrol.hiz_ayarla(seviye))
            self.sb_msg.setText(f'<span style="color:{BLUE}">●</span>&nbsp;'
                                f'Motor hızı: {P.HIZ_AD[seviye]}')

    def _lazer_karti(self):
        """LAZER — imha gucu (%) ve anlik ates durumu.

        "Ne kadar" ile "ne zaman" AYRI: guc kalici bir ayardir (karta G<yuzde> gider),
        ates ac/kes ayri komuttur (L1/L0, ATES butonu). Motor tarafindaki S/A ile P/T
        ayriminin aynisi. Guc ATES SIRASINDA da degistirilebilir — kart yeni duty'yi
        aninda uygular, atesi kesmeden.

        ⚠ Tam guc kullanilmiyor (varsayilan %40) ve dusuk guc DWELL SURESINI uzatir:
          %40'ta balonun patlamasi tam guce gore ~2.5 kat surer. Sure yarismada puana
          baglidir (Asama 1 bonus suresi, Asama 2-3 tur sureleri)."""
        kart = QFrame()
        kart.setObjectName("panelk")
        kv = QVBoxLayout(kart)
        kv.setContentsMargins(19, 11, 19, 13)
        kv.setSpacing(7)

        ust = QHBoxLayout()
        t = QLabel("LAZER")
        t.setObjectName("ph")
        ust.addWidget(t, 1)
        self.lazer_durum = QLabel()
        self.lazer_durum.setObjectName("engsub")
        ust.addWidget(self.lazer_durum, 0, Qt.AlignVCenter)
        kv.addLayout(ust)

        self.lazer_sl = QSlider(Qt.Horizontal)
        self.lazer_sl.setObjectName("ayarsl")
        self.lazer_sl.setMinimum(P.LAZER_GUC_MIN)
        self.lazer_sl.setMaximum(P.LAZER_GUC_MAX)
        self.lazer_sl.setSingleStep(5)
        self.lazer_sl.setPageStep(10)
        self.lazer_sl.setValue(self.lazer_guc)
        self.lazer_sl.setStyleSheet(SLIDER_TASLAK.format(**SLIDER_DEGISIK))
        self.lazer_sl.valueChanged.connect(self._lazer_guc_degisti)
        kv.addWidget(self.lazer_sl)

        # Sik kullanilan guclere tek dokunusla gitmek icin (kaydiriciyi hassas surmek
        # zor); ayni "kademe secici" kalibi motor hizinda ve adim hassasiyetinde de var.
        satir, self.lazer_btns = self._seviye_butonlari(
            [(20, "%20"), (40, "%40"), (70, "%70"), (100, "%100")],
            self.lazer_guc, self._lazer_guc_degisti)
        kv.addLayout(satir)

        self._lazer_bilgi_yaz()
        return kart

    def _lazer_bilgi_yaz(self):
        """Kart basligindaki durum: ates suruyor mu + hangi gucte."""
        if not hasattr(self, "lazer_durum"):
            return
        acik = bool(getattr(self, "kontrol", None)
                    and self.kontrol.bagli and self.kontrol.lazer_acik)
        self.lazer_durum.setText(
            f"● ATEŞ · %{self.lazer_guc}" if acik else f"○ Kapalı · %{self.lazer_guc}")
        self.lazer_durum.setStyleSheet(
            f"color:{RED if acik else TXT3}; font-weight:{700 if acik else 600};")
        for v, b in getattr(self, "lazer_btns", {}).items():
            b.setChecked(v == self.lazer_guc)
            self._step_btn_stil_guncelle(b, v == self.lazer_guc)

    def _lazer_guc_degisti(self, deger):
        """Guc degisiminin TEK kapisi (kaydirici + kademe butonlari ayni yoldan gecer)."""
        deger = P.guc_kirp(deger)
        if deger == self.lazer_guc:
            return                              # ayni deger: hatta bos komut dolasmasin
        self.lazer_guc = deger
        if self.lazer_sl.value() != deger:      # kademe butonuyla gelindiyse kaydirici da izlesin
            self.lazer_sl.blockSignals(True)    # (yoksa valueChanged geri cagirir)
            self.lazer_sl.setValue(deger)
            self.lazer_sl.blockSignals(False)
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

        # Baslik + "Aci Ayarlari" butonu — yon tuslarina yer acmak icin KUCULTULDU
        # (paylasilan #ph/#ayaralt stiline DOKUNULMADI, yalnizca bu iki widget'a ozel
        # ekstra kucultme uygulanir; diger kartlardaki basliklar/butonlar etkilenmez).
        brow = QHBoxLayout()
        mt = QLabel("MANUEL NİŞAN & YÖN KONTROLÜ")
        mt.setObjectName("ph")
        mt.setStyleSheet("font-size:10px; padding-bottom:4px;")
        brow.addWidget(mt, 1)
        self.aci_ayar_btn = QPushButton("⚙ Açı Ayarları")
        self.aci_ayar_btn.setObjectName("ayaralt")
        self.aci_ayar_btn.setCursor(Qt.PointingHandCursor)
        self.aci_ayar_btn.setFixedHeight(20)
        self.aci_ayar_btn.setStyleSheet("padding:2px 12px; font-size:11px;")
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
        self.pan_aci = 0.0            # azimut, 0-360 (EKRAN icin sarmali)
        # ESP32'ye giden azimut SARMASIZ (birikimli) olmalidir: 350°'den 10°'ye gecerken
        # "P370" denir, "P10" degil — yoksa motor kisa yoldan degil 340° geri doner.
        self.pan_ham = 0.0
        self.tilt_aci = 0.0           # yukselis, 0 - max_tilt_limit
        # Operatorun calisma siniri; mekanik tavan protokol.TILT_MAX'tir ve bunun
        # USTUNE cikilamaz (kontrol katmani ayrica kirpar). Acilista tavanin tamami
        # DEGIL, guvenli bir varsayilan gelir — daha yukarisi ⚙ panelinden acilir.
        self.max_tilt_limit = float(P.TILT_CALISMA_VARSAYILAN)
        self.aci_adim = 5.0           # D-pad adim hassasiyeti (derece)
        # Dikey eksende basili-tutma su an karta birakilmis mi? (bkz.
        # _tilt_surekli_baslat). Yalniz ayri tilt karti varken True olur.
        self._tilt_surekli = False

        self.pan_yasak_aktif = False  # harekete yasak alan (azimut)
        self.pan_yasak_min = 120.0
        self.pan_yasak_max = 160.0
        self.tilt_yasak_aktif = False # harekete yasak alan (yukselis)
        self.tilt_yasak_min = 45.0
        self.tilt_yasak_max = float(P.TILT_CALISMA_VARSAYILAN)
        self.atis_yasak_aktif = False # atisa yasak alan (azimut)
        self.atis_pan_min = 45.0
        self.atis_pan_max = 75.0

        # Tusa BASILI TUTUNCA surekli hareket (klavye tekrari mantigi: once kisa bir
        # gecikme, sonra sabit araliklarla tik). Qt'nin kendi auto-repeat'i KULLANILMAZ;
        # hizi isletim sistemi ayari belirlerdi ve iki tus ayni anda basiliyken caprazlama
        # calismazdi.
        self._basili_yonler = set()
        self._son_tekrar_t = 0.0
        self._tekrar_gecikme = QTimer(self)
        self._tekrar_gecikme.setSingleShot(True)
        self._tekrar_gecikme.timeout.connect(self._tekrar_baslat)
        self._tekrar_timer = QTimer(self)
        self._tekrar_timer.setInterval(self.TEKRAR_PERIYOT_MS)
        self._tekrar_timer.timeout.connect(self._tekrar_tik)

    # ---- Ic sayfa 0: D-pad ----
    def _dpad_sayfasi(self):
        sayfa = QWidget()
        dv = QVBoxLayout(sayfa)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(6)
        dv.addWidget(self._aci_gostergesi())

        self.bolge_status = QLabel("● BÖLGE GÜVENLİ")
        self.bolge_status.setObjectName("firest")
        self.bolge_status.setAlignment(Qt.AlignCenter)
        self.bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
        dv.addWidget(self.bolge_status)

        dv.addWidget(self._dpad_izgarasi(), 0, Qt.AlignCenter)
        dv.addLayout(self._adim_butonlari())
        dv.addStretch(1)                       # bosalan yer tuslarin ustune degil altina
        dv.addWidget(self._ates_butonu())
        return sayfa

    def _ates_butonu(self):
        """ATES butonu — AKTIF HEDEF kartindan buraya tasindi (06.08).

        Atesin TEK kapisi hala `_ates_bas`; buton yalnizca yer degistirdi. Klavyeden
        [L] de ayni kapiya baglidir (bkz. keyPressEvent) ve L HER MODDA calisir —
        buton manuel panelde oldugu icin otonom modda gorunmez, ama lazeri kesmenin
        yolu kapanmamalidir (E-Stop ve otomatik kesme yollari da yerinde durur)."""
        self.fire_btn = QPushButton(ATES_METIN_KAPALI)
        self.fire_btn.setObjectName("fire")
        self.fire_btn.setFixedHeight(44)
        self.fire_btn.setCheckable(True)
        self.fire_btn.setCursor(Qt.PointingHandCursor)
        self.fire_btn.setToolTip("[L] — ateşi aç / kes")
        self.fire_btn.clicked.connect(self._ates_bas)
        return self.fire_btn

    def _aci_gostergesi(self):
        """Canli azimut/yukselis sayi gostergesi.

        Yon tuslarina yer acmak icin kucultuldu — baslik/deger fontlari ve kutu
        dolgusu yalnizca burada (inline) kuculur, paylasilan #engsub/#turn stiline
        dokunulmaz (diger kartlardaki ayni objectName'ler etkilenmez)."""
        kutu = QFrame()
        kutu.setObjectName("angtgl")
        gh = QHBoxLayout(kutu)
        gh.setContentsMargins(10, 3, 10, 3)
        gh.setSpacing(10)

        def sutun(baslik, renk):
            v = QVBoxLayout()
            v.setSpacing(0)
            bl = QLabel(baslik)
            bl.setObjectName("engsub")
            bl.setStyleSheet("font-size:10px;")
            deger = QLabel("0.0°")
            deger.setObjectName("turn")
            deger.setStyleSheet(f"font-size:14px; color:{renk}; font-weight:700;")
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
        gl.setContentsMargins(0, 4, 0, 4)
        gl.setSpacing(10)

        # (isim, metin, satir, kolon, ipucu, yon, merkez_mi)
        tuslar = [
            ("btn_up", "▲", 0, 1, "[W] veya [▲] — YUKARI (TİLT +)", "up", False),
            ("btn_left", "◀", 1, 0, "[A] veya [◄] — SOL (PAN -)", "left", False),
            ("btn_center", "MERKEZ", 1, 1, "[R] veya [Space] — SIFIRLA / MERKEZ (0°, 0°)", "home", True),
            ("btn_right", "▶", 1, 2, "[D] veya [►] — SAĞ (PAN +)", "right", False),
            ("btn_down", "▼", 2, 1, "[S] veya [▼] — AŞAĞI (TİLT -)", "down", False),
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

    def _seviye_butonlari(self, secenekler, secili, geri_cagri):
        """Yatay 'kademe secici' buton satiri — adim hassasiyeti ve motor hizi AYNI kalip.
        secenekler: [(deger, etiket), ...]   Doner: (satir_layout, {deger: buton})"""
        satir = QHBoxLayout()
        satir.setSpacing(6)
        btns = {}
        for val, etiket in secenekler:
            b = QPushButton(etiket)
            b.setCheckable(True)
            b.setChecked(val == secili)
            b.setFixedHeight(26)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda checked=False, v=val: geri_cagri(v))
            self._step_btn_stil_guncelle(b, val == secili)
            satir.addWidget(b, 1)
            btns[val] = b
        return satir, btns

    def _adim_butonlari(self):
        """Adim hassasiyeti secimi (1° / 5° / 10°) — D-pad'in bir basista attigi aci.
        (Motor HIZI ile karistirilmamali: bu 'ne kadar', hiz 'ne kadar cabuk'.)"""
        satir, self.step_btns = self._seviye_butonlari(
            [(1.0, "1° Hassas"), (5.0, "5° Orta"), (10.0, "10° Geniş")],
            self.aci_adim, self._aci_adim_sec)
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
        # Tavan MEKANIK sinirdan turer (tek kaynak: protokol.TILT_MAX). Eskiden burada
        # sabit 90 yaziyordu ama protokol 60'ta kirpiyordu: kaydirici 90'a cekilse bile
        # gimbal 60'ta takili kaliyor, operator sebebini goremiyordu.
        self.ap_tilt_sl.setMaximum(int(P.TILT_MAX))
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
            self.tilt_yasak_aktif, self.tilt_yasak_min, self.tilt_yasak_max,
            int(P.TILT_MAX))
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

    # yon -> (buton adi, pan carpani, tilt carpani). "home"/"center" ayri ele alinir
    # (aci degisimi degil, sifirlama). Tek tablo: basma ve birakma ayni yerden okur.
    YON_TABLO = {"up": ("btn_up", 0.0, 1.0), "down": ("btn_down", 0.0, -1.0),
                 "left": ("btn_left", -1.0, 0.0), "right": ("btn_right", 1.0, 0.0)}

    # Basili tutma davranisi: ilk dokunus SECILI ADIM kadar hareket eder (hassas nisan
    # icin tek tik = 1°/5°/10°); tus TEKRAR_GECIKME_MS'den uzun basili kalirsa surekli
    # harekete gecilir.
    TEKRAR_GECIKME_MS = 300
    TEKRAR_PERIYOT_MS = 50

    def _dpad_press(self, direction):
        if direction in ("home", "center"):
            self.btn_center.setStyleSheet(self._key_center_active_style)
            self._aci_reset()
            return
        ad, kpan, ktilt = self.YON_TABLO[direction]
        getattr(self, ad).setStyleSheet(self._key_active_style)
        self._aci_hareket(kpan * self.aci_adim, ktilt * self.aci_adim)   # tek dokunus
        self._basili_yonler.add(direction)
        if not self._tekrar_timer.isActive():
            self._tekrar_gecikme.start(self.TEKRAR_GECIKME_MS)

    def _dpad_release(self, direction):
        if direction in ("home", "center"):
            self.btn_center.setStyleSheet(self._key_center_normal_style)
            return
        getattr(self, self.YON_TABLO[direction][0]).setStyleSheet(self._key_normal_style)
        self._basili_yonler.discard(direction)
        if not self._basili_yonler:
            self._tekrar_durdur()
        elif self.YON_TABLO[direction][2]:
            # Dikey tus birakildi ama yatay hala basili: yalniz dikeyin surekli
            # hareketi biter. Bunu atlarsak "yukari"yi birakip "saga" basili
            # tutan operator, kolu sinira kadar tirmanmaya devam ederken gorurdu.
            self._tilt_surekli_bitir()

    # ---- USB GAMEPAD ----
    GP_TARAMA_TIK = 40      # cihaz yokken kac tikta bir yeniden taransin (~2 sn)

    def _gamepad_durum_yaz(self):
        if self.gamepad.bagli:
            self._ci("Gamepad", GRN, f"· {self.gamepad.ad[:26]}")
        else:
            self._ci("Gamepad", BD2, "· yok")

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
        if d.estop:
            self.estop_btn.setChecked(not self.estop_btn.isChecked())
            self._estop_bas()
            return                                  # ayni tikta baska komut isleme

        if d.ates:
            self._ates_kisayolu()                   # -> _ates_bas (tek kapi)

        if d.merkez and self.btn_center.isEnabled():
            # btn_center E-Stop'ta devre disi kalir; gamepad'in ondan fazla yetkisi yok.
            self._aci_reset()

        if d.hiz_yukari or d.hiz_asagi:
            yeni = self.hiz_seviye + (1 if d.hiz_yukari else -1)
            if yeni in P.HIZ_TABLO:
                self._hiz_sec(yeni)

        # HAREKET: adim = tavan hiz x gecen sure x cubugun sapmasi. Basili tutma
        # (`_tekrar_tik`) ile ayni matematik — tek farki analog carpan. Sabit adim
        # gonderilseydi hedef motorun onune gecer, cubuk birakildiginda gimbal
        # yetismek icin donmeye devam ederdi.
        if d.hareket_var:
            adim = P.HIZ_TABLO[self.hiz_seviye][0] * dt
            self._aci_hareket(d.pan * adim, d.tilt * adim)

    def _tilt_surekli_mi(self):
        """Dikeyde basili-tutma, kartin KENDI ivme profiliyle mi yurusun?

        Yalnizca dikey eksen ayri kartta (ESP32-S3 + HSD57) ve kart hazirken.
        Eski donanimda False doner ve davranis birebir eskisi gibi kalir."""
        k = getattr(self, "kontrol", None)
        return bool(k and k.tilt_ayri and k.tilt.hazir)

    def _tilt_surekli_hedef(self, yon):
        """O yonde gidilebilecek EN UZAK guvenli aci.

        Sinir ve yasak alan komutun KENDISINE gomulur; boylece kart nerede
        duracagini bilir ve PC'nin "simdi dur" demesine yetismesi gerekmez.
        Yoklama 100 ms'de bir yapiliyor ve kol 36 derece/sn'ye cikabiliyor —
        durdurmayi yoklamaya birakmak 3-4 derecelik bir asma demekti."""
        hedef = self.max_tilt_limit if yon > 0 else 0.0
        if self.tilt_yasak_aktif:
            simdi = self.tilt_aci
            if yon > 0 and simdi < self.tilt_yasak_min <= hedef:
                hedef = max(simdi, self.tilt_yasak_min - 0.1)
            elif yon < 0 and simdi > self.tilt_yasak_max >= hedef:
                hedef = min(simdi, self.tilt_yasak_max + 0.1)
        return hedef

    def _tilt_surekli_baslat(self, yon):
        """Dikeyde basili-tutma: karta TEK bir 'sinira kadar git' komutu verir.

        NEDEN 50 ms'de bir kucuk hedef DEGIL: firmware her hedefe yavaslayarak
        yaklasir (MotionCore::schedule -> sqrt(2*ACCEL*kalan)) ve hedefe varinca
        hizi SIFIRLAR. Tik tik 2 derecelik hedef gondermek kolu "ilerle-dur-
        ilerle-dur" yapmaya zorlar, tepe hiza HIC cikilmaz.
        Gercek kalibrasyonla olculdu (2675 darbe / 60 derece = 44.6 darbe/derece,
        ACCEL=3200, MAX_SPEED=1600):
            50 ms'de bir 2 derece  -> her adim 0.24 sn, efektif ~5 derece/sn
            tek uzak hedef         -> tepe hiz 1600 darbe/sn = ~36 derece/sn
        Yedi kat fark ve hareket puruzsuz. Tus birakilinca `_tilt_surekli_bitir`.

        Hareketin TEK KAPISI korunur: komut yine `_aci_hareket`'ten gecer, yani
        E-Stop / yasak alan / aci limiti aynen uygulanir."""
        taban = self.kontrol.tilt_olculen
        if taban is None:
            return False
        hedef = self._tilt_surekli_hedef(yon)
        if abs(hedef - taban) < 0.1:
            return False               # o yonde gidecek yer yok (sinirda)
        if not self._aci_hareket(0.0, hedef - taban, taban_olculen=True):
            return False
        self._tilt_surekli = True
        return True

    def _tilt_surekli_bitir(self):
        """Tus birakildi / hareket kesildi: kolu durdur ve ekrani gercege cek."""
        if not getattr(self, "_tilt_surekli", False):
            return
        self._tilt_surekli = False
        k = getattr(self, "kontrol", None)
        if not (k and k.tilt_ayri):
            return
        self._esp_goster(k.tilt_dur())
        olculen = k.tilt_olculen
        if olculen is not None:
            # Arayuzun inanci kolun DURDUGU yere cekilir; yoksa bir sonraki
            # manuel dokunus uzak hedeften hesaplanirdi.
            self.tilt_aci = olculen
            self.tilt_val_lbl.setText(f"{olculen:.1f}°")

    def _tekrar_baslat(self):
        if not self._basili_yonler:
            return
        self._son_tekrar_t = time.time()
        if self._tilt_surekli_mi():
            ktilt = sum(self.YON_TABLO[y][2] for y in self._basili_yonler)
            if ktilt:
                self._tilt_surekli_baslat(1.0 if ktilt > 0 else -1.0)
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
        if getattr(self, "_tilt_surekli", False):
            # Dikey ekseni kart kendi suruyor (tek uzak hedef, bkz.
            # _tilt_surekli_baslat). Buradan tik tik hedef gondermek o hareketi
            # bolerdi: her yeni hedef kolu yavaslatip durdururdu.
            ktilt = 0.0
            if not kpan:
                return
        if (kpan or ktilt) and not self._aci_hareket(kpan * adim, ktilt * adim):
            self._tekrar_durdur()                      # E-Stop / yasak alan: tekrari kes

    def _tekrar_durdur(self):
        self._tekrar_gecikme.stop()
        self._tekrar_timer.stop()
        self._basili_yonler.clear()
        # Kart kendi suruyorduysa DURDURULMALI: firmware'in hedefi sinirdir,
        # "tus birakildi" diye bir kavrami yoktur — soylenmezse kol sinira
        # kadar gitmeye devam eder.
        self._tilt_surekli_bitir()

    def _tuslari_birak(self):
        """Tum yon tuslarini birakilmis say (tekrari kes + basili stilleri sifirla)."""
        if not hasattr(self, "_tekrar_timer"):
            return
        self._tekrar_durdur()
        for ad, _, _ in self.YON_TABLO.values():
            b = getattr(self, ad, None)
            if b is not None and hasattr(self, "_key_normal_style"):
                b.setStyleSheet(self._key_normal_style)

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
        """Su anki pan acisi ATISA YASAK bolgede mi? (sartname: atisa-yasak alan)"""
        return bool(getattr(self, "atis_yasak_aktif", False)
                    and self.atis_pan_min <= self.pan_aci <= self.atis_pan_max)

    def _tilt_tavan_uygula(self):
        """Dikey eksenin MEKANIK tavanini kontrol katmanindan ogrenip arayuze uygular.

        Kol-biyel mekanizmasinda (ESP32-S3 + HSD57) kol 0..60 derece arasinda
        calisir; eski dogrudan tahrikteki 180 derece bu donanimda FIZIKSEL OLARAK
        YOKTUR. Kaydirici 90'a cekilebilseydi kart 60'ta kirpardi ve gimbal
        sebebi gorunmeden takili kalirdi — protokol.py'deki ayni hatanin (07.08,
        ekran 120 / kart 90) tekrari olurdu. Tavan tek kaynaktan (kontrol.tilt_tavan)
        turer; eski donanimda bu fonksiyon HICBIR SEYI DEGISTIRMEZ."""
        tavan = float(getattr(self.kontrol, "tilt_tavan", P.TILT_MAX))
        if tavan >= P.TILT_MAX:
            return
        self.max_tilt_limit = min(self.max_tilt_limit, tavan)
        self.tilt_yasak_max = min(self.tilt_yasak_max, tavan)
        sl = getattr(self, "ap_tilt_sl", None)
        if sl is not None:
            sl.setMaximum(int(tavan))
            sl.setValue(int(self.max_tilt_limit))      # _ap_tilt_degisti'yi tetikler
        for spin in (getattr(self, "ap_tmin_spin", None), getattr(self, "ap_tmax_spin", None)):
            if spin is not None:
                spin.setMaximum(int(tavan))
        self._ap_tilt_degisti(int(self.max_tilt_limit))

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
        # Sabit 60 yaziliydi: tavan degisince kalirdi. Ayrica kaydiricinin GERCEK
        # tavanini asamaz — kol-biyel donaniminda mekanik tavan 60'tir ve varsayilana
        # donmek onu 90'a cikarmamalidir (bkz. _tilt_tavan_uygula).
        tavan = min(int(P.TILT_CALISMA_VARSAYILAN), self.ap_tilt_sl.maximum())
        self.ap_tilt_sl.setValue(tavan)
        self.ap_pan_cb.setChecked(False)
        self.ap_pmin_spin.setValue(120)
        self.ap_pmax_spin.setValue(160)
        self.ap_tilt_cb.setChecked(False)
        self.ap_tmin_spin.setValue(45)
        self.ap_tmax_spin.setValue(tavan)
        self.ap_atis_cb.setChecked(False)
        self.ap_amin_spin.setValue(45)
        self.ap_amax_spin.setValue(75)
        self._ap_tilt_degisti(tavan)
        self._ap_yasak_degisti()

    def _aci_hareket(self, d_pan, d_tilt, taban_olculen=False):
        """Pan/Tilt acisini degistirir, yasak bolgeleri kontrol eder ve ESP32 komutunu gonderir.

        HAREKETIN TEK KAPISI. E-Stop, yasak alan ve tilt limiti burada uygulanir;
        hem manuel (D-pad/WASD) hem otonom (_nisan_geldi) bu kapidan gecer.

        Giris DELTA'dir (tus basimi / piksel hatasi), ESP32'ye giden ise MUTLAK acidir:
        arayuzdeki aci ile kartin hedefi ayni tek kaynaktan (self.pan_ham/tilt_aci)
        turedigi icin ikisi yapisal olarak KOPAMAZ. (Delta gonderilen surumde limitte
        ekran 60 kalirken kartin hedefi buyumeye devam ediyordu — §13.1'deki hata.)
        """
        # B2 — E-Stop: hicbir hareket komutu gecmez, aci etiketleri de DEGISMEZ.
        # (isinstance ile bakilir: QObject'in yerlesik thread() metodu yuzunden
        #  hasattr/getattr(self,"thread") thread olusmadan once de dolu gorunur.)
        if isinstance(getattr(self, "thread", None), VideoThread) and self.thread.estop:
            return False
        # Kart KENDI durduysa (seri monitorden STOP / donanim butonu) arayuz E-Stop'a
        # basilmamis olabilir. O halde komut gonderilirse kart yok sayar ama ekrandaki
        # aci ilerler -> ekran ile hedef koparadi. Hareket kapisi burada da kapanir.
        if getattr(self, "kontrol", None) and self.kontrol.estop_aktif:
            return False

        yeni_pan_ham = self.pan_ham + d_pan
        yeni_pan = yeni_pan_ham % 360.0

        # DIKEY EKSENIN REFERANSI — `taban_olculen` yalnizca OTONOM TAKIPTE acilir.
        #
        # Eski kart konum bildirmiyordu, bu yuzden delta hep YAZILIMIN INANDIGI
        # aciya (self.tilt_aci) eklenirdi. Yeni tilt karti (ESP32-S3 + HSD57, bkz.
        # tilt_surucu.py) konumunu BILDIRIYOR ve bu, otonom takipte kapali cevrimi
        # gercekten kapatir:
        #
        #   d_tilt, kameranin GORDUGU piksel hatasindan turer — yani kolun GERCEK
        #   konumuna gore olculmus bir hatadir. Onu yazilimin inancina eklemek iki
        #   farkli referansi toplamak demektir: kart komuta yetisemedigi anda
        #   (kol-biyel yavas, firmware tek hedefi bitirip digerine geciyor) inanc
        #   gercegin onune gecer ve her kare bir oncekinin ustune biner — namlu
        #   hedefi asar, sonra geri salinir. Olculen aciya eklenince komut
        #   "su an bulundugum yer + gordugum hata" olur; kaybolan/geciken komut
        #   kalici sapma birakmaz.
        #
        # MANUELDE inanc referansi KORUNUR (taban_olculen=False): operator yon
        # tusuna ucuncu kez bastiginda kol henuz hareket halindeyse bile "3 adim
        # yukari" beklenir; olculene gore hesaplamak o basislari yutardi.
        tilt_taban = self.tilt_aci
        if taban_olculen:
            olculen = getattr(getattr(self, "kontrol", None), "tilt_olculen", None)
            if olculen is not None:
                tilt_taban = olculen
        yeni_tilt = max(0.0, min(self.max_tilt_limit, tilt_taban + d_tilt))

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

        self.pan_ham = yeni_pan_ham
        self.pan_aci = yeni_pan
        self.tilt_aci = yeni_tilt
        self.pan_val_lbl.setText(f"{self.pan_aci:.1f}°")
        self.tilt_val_lbl.setText(f"{self.tilt_aci:.1f}°")

        # Atisa yasak bolgede miyiz? Yalnizca ikaz DEGIL: lazer acikken bolgeye
        # girilirse ates KESILIR (sartname: atisa-yasak alan, ates sirasinda da gecerli).
        if self.atis_yasak_aktif and (self.atis_pan_min <= self.pan_aci <= self.atis_pan_max):
            self.bolge_status.setText("⚠️ ATIŞA YASAK BÖLGEDESİNİZ — ATEŞ KİLİTLİ")
            self.bolge_status.setStyleSheet(f"color:{AMB}; font-size:11px; font-weight:700; padding:2px 0;")
            self._ates_kes("ATIŞA YASAK AÇI BÖLGESİNE GİRİLDİ")
        else:
            self.bolge_status.setText("● BÖLGE GÜVENLİ")
            self.bolge_status.setStyleSheet(f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")

        # ESP32'ye MUTLAK hedef aci gider (pan sarmasiz). Degismeyen ekseni kontrol
        # katmani zaten gondermez, burada ayrica ayiklamaya gerek yok.
        if getattr(self, "kontrol", None) and self.kontrol.bagli:
            self._esp_goster(self.kontrol.aci(self.pan_ham, self.tilt_aci))
        return True

    def _nisan_geldi(self, d_yaw, d_pitch):
        """B3 — Otonom nisan dongusunden gelen aci duzeltmesi (AlgiThread.nisan_komut).

        Manuel hareketle AYNI kapidan (_aci_hareket) gecer: E-Stop, yasak alan ve
        tilt limiti otonom modda da aynen uygulanir — guvenlik icin tek yol olmali.

        PD'nin urettigi komut, MOTORUN GERCEKTEN GIDEBILECEGI hizla (secili hiz duzeyi,
        P.HIZ_TABLO) kirpilir — basili-tutma D-pad'de (_tekrar_tik) kullanilan AYNI
        matematik: adim = tavan_hiz x gecen_sure. ESP32 konum geri bildirimi YOLLAMADIGI
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
        simdi = time.time()
        if simdi < self._nisan_mesgul_ta:
            return   # onceki komutun fiziksel karsiligi henuz gorulmedi, bekle
        tavan_hiz, tavan_ivme = P.HIZ_TABLO[self.hiz_seviye]
        if self._nisan_son_t is not None:
            dt = min(0.2, simdi - self._nisan_son_t)   # uzun kopukluk sonrasi sicrama olmasin
            tavan = tavan_hiz * dt
            d_yaw = max(-tavan, min(tavan, d_yaw))
            d_pitch = max(-tavan, min(tavan, d_pitch))
        self._nisan_son_t = simdi
        # taban_olculen=True: dikey eksende komut, kartin BILDIRDIGI aciya gore
        # kurulur (bkz. _aci_hareket). Kart bildirmiyorsa (eski donanim) eski
        # davranis aynen surer.
        if self._aci_hareket(d_yaw, d_pitch, taban_olculen=True):
            mesafe = max(abs(d_yaw), abs(d_pitch))
            # Ucgen ivme profili (tepe hiza hic ulasilmadigi varsayimi — kisa
            # duzeltmelerde gecerli): TAM tamamlanma t = 2*sqrt(mesafe/ivme); yalniz
            # NISAN_MESGUL_ORANI kadarini bekleriz (bkz. sabitin yorumu — akicilik icin).
            sure = 2.0 * math.sqrt(mesafe / max(1.0, tavan_ivme)) * NISAN_MESGUL_ORANI
            self._nisan_mesgul_ta = simdi + max(NISAN_MIN_ARALIK, sure)

    def _aci_reset(self):
        self.pan_aci = 0.0
        self.pan_ham = 0.0
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
        btn.setStyleSheet(ADIM_STIL_SECILI if secili else ADIM_STIL_NORMAL)

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

        # --- yasak alan kartlari (ikisi ayni kaliptan) ---
        atis_card, self.atis_yasak_lbl, self.atis_yasak_sw = self._yasak_kart("ATIŞA YASAK ALAN")
        h.addWidget(atis_card, 2)
        hrk_card, self.hareket_yasak_lbl, self.hareket_yasak_sw = self._yasak_kart("HAREKETE YASAK ALAN")
        h.addWidget(hrk_card, 2)

        # Ilk durum yansitmasi
        self._yasak_kartlari_guncelle()

        return alt

    def _yasak_kart(self, baslik):
        """Alt paneldeki bir yasak alan karti: baslik + (durum yazisi | anahtar rozeti).
        Atisa ve harekete yasak kartlari birebir ayni kaliptir; icerigi
        _yasak_kartlari_guncelle() doldurur. Doner: (kart, durum_label, anahtar_label)"""
        kart = QFrame()
        kart.setObjectName("panelk")
        kv = QVBoxLayout(kart)
        kv.setContentsMargins(15, 10, 15, 10)
        kv.setSpacing(6)
        ph = QLabel(baslik)
        ph.setObjectName("ph")
        kv.addWidget(ph)

        tgl = QFrame()
        tgl.setObjectName("angtgl")
        th = QHBoxLayout(tgl)
        th.setContentsMargins(12, 9, 12, 9)
        th.setSpacing(10)
        lbl = QLabel('<small style="color:#8094a8">Devre Dışı — Serbest</small>')
        lbl.setObjectName("tgll")
        sw = QLabel()
        sw.setFixedSize(32, 16)
        sw.setStyleSheet("background:#c3d3e2;border-radius:8px;")
        th.addWidget(lbl, 1)
        th.addWidget(sw)
        kv.addWidget(tgl)
        return kart, lbl, sw

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
        # "Tilt Kartı" segmenti dikey eksen AYRI KARTTAYKEN doldurulur (bkz.
        # _esp_goster); eski donanimda "bağlı değil" olarak kalir ve kimseyi
        # yaniltmaz. Segment burada kosulsuz yaratilir cunku alt cubuk, kontrol
        # katmani kurulmadan ONCE insa edilir.
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
        # Otonom'a gecerken asama secili degilse ASAMA 3'e dus. Otonom ates kapisi
        # zaten yalniz Asama 2/3'te acilir (_otonom_ates_kontrol); asamasiz Otonom
        # "her sey calisiyor ama ates etmiyor" gibi gorunuyordu. A3 varsayilan cunku
        # dost/dusman ayrimi (renk) yalniz orada devrede ve en genis davranis o.
        if ad == "Otonom" and self.asama is None and "Aşama 3" in izin:
            self.asama = "Aşama 3"
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
        """[L] tusu — ATES butonuyla BIREBIR ayni sey (atesin tek kapisi `_ates_bas`).

        Buton devre disiysa (E-Stop) kisayol da gecmez: kisayolun butondan daha fazla
        yetkisi olamaz, yoksa E-Stop klavyeden asilabilir olurdu."""
        if not hasattr(self, "fire_btn") or not self.fire_btn.isEnabled():
            return
        self.fire_btn.setChecked(not self.fire_btn.isChecked())
        self._ates_bas()

    def keyPressEvent(self, event):
        # [L] = ates ac/kes. HER MODDA calisir: ATES butonu manuel panelde durdugu icin
        # otonom modda gorunmez, ama lazeri kesme yolu moda bagli OLMAMALIDIR.
        if event.key() == Qt.Key_L and not event.isAutoRepeat():
            self._ates_kisayolu()
            return
        yon = self._tus_yonu(event)
        if yon is None:
            super().keyPressEvent(event)
            return
        self._dpad_press(yon)

    def keyReleaseEvent(self, event):
        yon = self._tus_yonu(event)
        if yon is None:
            super().keyReleaseEvent(event)
            return
        self._dpad_release(yon)

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
        self.inference_thread.estop = aktif
        self.estop_btn.setText("▶ DEVAM ET" if aktif else "⏻ ACİL DURDUR")
        # 1. ATES kapisi (Yetenek 4) — kesme islemi tek yoldan (_ates_kes) gecer.
        if aktif:
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
                self.bolge_status.setStyleSheet(
                    f"color:{RED}; font-size:11px; font-weight:700; padding:2px 0;")
            else:
                self.bolge_status.setText("● BÖLGE GÜVENLİ")
                self.bolge_status.setStyleSheet(
                    f"color:{GRN}; font-size:11px; font-weight:600; padding:2px 0;")
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
            self.pan_val_lbl.setText(f"{self.pan_aci:.1f}°")
            self.tilt_val_lbl.setText(f"{self.tilt_aci:.1f}°")
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
                self.bolge_status.setStyleSheet(
                    f"color:{RED}; font-size:11px; font-weight:700; padding:2px 0;")
            return
        ac = self.fire_btn.isChecked()
        d = self.kontrol.ates(ac)
        self.fire_btn.setText(ATES_METIN_ACIK if ac else ATES_METIN_KAPALI)
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
        if not self.fire_btn.isChecked():
            return
        self.fire_btn.setChecked(False)
        self.fire_btn.setText(ATES_METIN_KAPALI)
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
        renk = {"Hazır": GRN, "ATEŞ": RED, "E-STOP": RED}.get(d["durum_ad"], BD2)
        ek = " · mock" if self.kontrol.mock_mu else ""
        self._ci("ESP32", renk,
                 f'· {d["durum_ad"]} · hedef yatay {d["pan"]:.1f}° dikey {d["tilt"]:.1f}°'
                 f' · {d["hiz_ad"]}{ek}')
        # DIKEY EKSEN KARTI (varsa) AYRI GOSTERILIR — ve HEDEF ile OLCULEN ayri
        # yazilir. Ikisini tek sayiya indirgemek, kartin komuta yetisemedigi ani
        # gorunmez yapardi: ekran "30°" derken kol 12°'de olabilir.
        if d.get("tilt_ayri"):
            t = d["tilt_ozet"] or {}
            t_renk = {"iyi": GRN, "uyari": AMB}.get(t.get("renk"), RED)
            olculen = d.get("tilt_olculen")
            olculen_s = f'{olculen:.1f}°' if olculen is not None else '—'
            # YÜKSELİŞ etiketi artik OLCULEN aciyi gosterir. Bu kart konumunu
            # bildirdigi icin mumkun; eski kartta gosterilen deger "hedef"ti ve
            # kol yetisemediginde ekran gercegi soylemiyordu. Ozellikle basili
            # tutarken onemli: komut "sinira kadar git" oldugu icin hedef 60
            # yazardi, kol ise yolun ortasinda olurdu.
            if olculen is not None and hasattr(self, "tilt_val_lbl"):
                self.tilt_val_lbl.setText(f"{olculen:.1f}°")
            kaynak_s = " · mock" if t.get("mock") else f' · {t.get("kaynak", "")}'
            self._ci("Tilt Kartı", t_renk,
                     f'· {t.get("ad", "—")} · ölçülen {olculen_s} '
                     f'/ hedef {d["tilt"]:.1f}°{kaynak_s}')
        self._ci("Lazer", RED if d["lazer"] else BD2,
                 f'· AKTİF %{d["lazer_guc"]}' if d["lazer"] else f'· kapalı · %{d["lazer_guc"]}')
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
            self.pan_aci = self.pan_ham = self.tilt_aci = 0.0
            if hasattr(self, "pan_val_lbl"):
                self.pan_val_lbl.setText("0.0°")
                self.tilt_val_lbl.setText("0.0°")
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

    def _kamera_sec(self, i):
        veri = self.kam_sec.itemData(i)
        if veri is None:
            return
            
        # Cozunurluk menusu guncelle
        self.res_sec.blockSignals(True)
        self.res_sec.clear()
        if hasattr(self, 'kamera_cozunurlukleri') and veri in self.kamera_cozunurlukleri:
            res_list = self.kamera_cozunurlukleri[veri]
            if res_list:
                for w, h in res_list:
                    self.res_sec.addItem(f"{w}x{h}", (w, h))
            else:
                self.res_sec.addItem("Bilinmiyor", None)
        else:
            self.res_sec.addItem("Otomatik", None)
        self.res_sec.blockSignals(False)
        
        self.thread.kaynak_istegi = veri

    def _res_sec(self, i):
        veri = self.res_sec.itemData(i)
        if veri is None:
            return
        w, h = veri
        algi.ISTENEN_W = w
        algi.ISTENEN_H = h
        
        # Mevcut kamerayi yeni cozunurlukle yeniden baslat
        idx = self.kam_sec.currentData()
        if idx is not None:
            self.thread.kaynak_istegi = idx

    def _kameralar_geldi(self, liste):
        """liste: [{"index": int, "name": str, "is_default": bool, "resolutions": [...]}, ...]"""
        if not hasattr(self, 'kamera_cozunurlukleri'):
            self.kamera_cozunurlukleri = {}
        mevcut = {self.kam_sec.itemData(i) for i in range(self.kam_sec.count())}
        for cam in sorted(liste, key=lambda c: c["index"]):
            idx = cam["index"]
            self.kamera_cozunurlukleri[idx] = cam.get("resolutions", [])
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

        # CANLI gostergesi: kare geliyorsa aktif
        if not self.live_dot.isVisible():
            self.live_dot.setVisible(True)
        self._ci("Kamera", GRN, f"· {qimg.width()}×{qimg.height()}")

        # A3'te dost/dusman ayrimi var; A1-A2'de yok (hepsi hedef).
        a3 = data.get("a3", False)

        # Aktif hedef bilgisi UST SERITTE (AKTIF HEDEF karti kaldirildi — ayni bilgiyi
        # ikinci kez gostermenin anlami yoktu). E-Stop mesaji da buraya dusuyor; eskiden
        # yalnizca kartin alt satirinda gorunuyordu.
        a = data["active"]
        if a:
            self.eng_name.setText("Hedef kilitli")
            taraf = f" · {a['tip']}" if a3 else ""
            self.eng_sub.setText(f"{a['ad']}{taraf} · %{a['conf']} güven")
        else:
            estop = "DURDUR" in data["mesaj"]
            self.eng_name.setText("Hedef bekleniyor")
            self.eng_sub.setText(data["mesaj"] if estop else "—")

        # HEDEFLER karti: numarali, tiklanabilir isim listesi (secim = manuel kilit).
        self._hedef_liste_guncelle(data["hedefler"], a3)

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
        self.oto_ates_kapi.setStyleSheet(f"font-size:11px; color:{renk}; padding:2px 0;")

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
            self.oto_durum_dot.setStyleSheet(f"background:{GRN};border-radius:5px;")
            self.oto_durum_baslik.setText("Hedef Kilitli")
            self.oto_durum_baslik.setStyleSheet(f"font-size:14px; font-weight:700; color:{GRN}; background:transparent;")
            
            taraf = f" · {active_hedef['tip']}" if data.get("a3") else ""
            self.oto_durum_alt.setText(f"{active_hedef['ad']}{taraf} · %{active_hedef['conf']} güven")
        elif estop:
            self.oto_durum_dot.setStyleSheet(f"background:{RED};border-radius:5px;")
            self.oto_durum_baslik.setText("ACİL DURDURMA")
            self.oto_durum_baslik.setStyleSheet(f"font-size:14px; font-weight:700; color:{RED}; background:transparent;")
            self.oto_durum_alt.setText(data.get("mesaj", ""))
        else:
            self.oto_durum_dot.setStyleSheet(f"background:{AMB};border-radius:5px;")
            self.oto_durum_baslik.setText("Hedef Aranıyor...")
            self.oto_durum_baslik.setStyleSheet(f"font-size:14px; font-weight:700; color:{AMB}; background:transparent;")
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
                self.oto_nisan_durum.setStyleSheet(f"font-size:12px; color:{RED}; padding:2px 0;")
            elif active_hedef:
                simdi = time.time()
                if simdi < getattr(self, "_nisan_mesgul_ta", 0):
                    self.oto_nisan_durum.setText("Konumlanıyor...")
                    self.oto_nisan_durum.setStyleSheet(f"font-size:12px; color:{BLUE}; padding:2px 0;")
                else:
                    self.oto_nisan_durum.setText("Takip aktif")
                    self.oto_nisan_durum.setStyleSheet(f"font-size:12px; color:{GRN}; padding:2px 0;")
            else:
                self.oto_nisan_durum.setText("Bekleniyor")
                self.oto_nisan_durum.setStyleSheet(f"font-size:12px; color:{TXT3}; padding:2px 0;")

        # 4. Lazer Durumu
        acik = bool(getattr(self, "kontrol", None) and self.kontrol.bagli and self.kontrol.lazer_acik)
        self.oto_lazer_durum.setText(f"● ATEŞ AKTİF · %{self.lazer_guc}" if acik else f"○ Lazer Kapalı · %{self.lazer_guc}")
        self.oto_lazer_durum.setStyleSheet(
            f"font-size:13px; font-weight:{700 if acik else 600}; "
            f"color:{RED if acik else TXT3}; padding:6px 0;")

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
        if hasattr(self, "esp_timer"):
            self.esp_timer.stop()      # kapanan port yoklanmasin
        if hasattr(self, "gp_timer"):
            self.gp_timer.stop()
            self.gamepad.kapat()
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
