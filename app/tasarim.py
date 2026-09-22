"""DERİN MAVİ — Apple tasarım katmanı (TEK KAYNAK).

Arayüzün BÜTÜN görünümü buradan türer: renk, tipografi, ölçü, yarıçap, cam
efekti ve Qt stil sayfası (QSS). `arayuz_qt.py` içinde artık elle yazılmış
renk/ölçü YOKTUR — hepsi bu dosyadaki simgelerden gelir.

DEĞERLERİN KAYNAĞI
------------------
Hiçbir değer "göze güzel geldiği için" seçilmedi. Tamamı **Apple macOS 27 UI
Kit**'inden (Sketch) çıkarıldı: renkler paylaşılan renk kütüphanesinden
(`System Colors/Dark`, `Labels/Dark`, `Fills/Dark`), tipografi Apple'ın metin
stili rampasından (LargeTitle→Caption2), ölçüler de bileşenlerin kendi
artboard'larından (ör. Pop-up Button "3 Rg" = 24 px yükseklik, 6 px yarıçap,
SF Pro Medium 13, soldan 12 px boşluk).

NEDEN TEK DOSYA
---------------
Önceki arayüzde renkler üç ayrı yerde (sabitler, satır içi setStyleSheet,
QSS metni) yazılıydı; biri değişince diğerleri sapıyordu. Artık tek kapı:
bir rengi burada değiştir, bütün uygulama değişir.

LIQUID GLASS HAKKINDA (dürüst not)
----------------------------------
macOS 26/27'nin "Liquid Glass"i gerçek zamanlı ARKA PLAN BULANIKLIĞI
(backdrop blur) + refraksiyon kullanır. Qt'nin stil sayfasında böyle bir
özellik YOKTUR — arkasındaki pikselleri bulanıklaştıramayız. Bu yüzden camı
kit'in kendi reçetesindeki diğer katmanlarla taklit ediyoruz:
  1. yarı saydam koyu gövde (kit: #1A1A1A @%50 üstüne ikinci bir kat),
  2. üst kenarda ışık çizgisi (kit'teki iç gölge y+1 beyaz),
  3. dışta yumuşak düşen gölge (kit: y18 b48 siyah @%45),
  4. tam yuvarlak (kapsül) büyük kontroller.
Sonuç birebir değil ama aynı dili konuşur; farkı ancak yan yana koyunca
görürsün.
"""

# =====================================================================
#  0. Renk yardımcıları
# =====================================================================

def _a(hex_renk: str, alfa: float) -> str:
    """#RRGGBB + alfa → Qt'nin anladığı rgba() metni."""
    h = hex_renk.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alfa:.3f})"


def beyaz(alfa: float) -> str:
    return f"rgba(255, 255, 255, {alfa:.3f})"


def siyah(alfa: float) -> str:
    return f"rgba(0, 0, 0, {alfa:.3f})"


# =====================================================================
#  1. RENKLER — Apple "System Colors / Dark" (kitin renk kütüphanesi)
# =====================================================================
MAVI       = "#0091FF"   # 8 Blue      — sistem vurgu rengi (accent)
KIRMIZI    = "#FF4245"   # 1 Red       — yıkıcı eylem / alarm
TURUNCU    = "#FF9230"   # 2 Orange
SARI       = "#FFD600"   # 3 Yellow    — uyarı
YESIL      = "#30D158"   # 4 Green     — olumlu durum
TEAL       = "#00D2E0"   # 6 Teal
CAMGOBEGI  = "#3CD3FE"   # 7 Cyan
INDIGO     = "#6D7CFF"   # 9 Indigo
MOR        = "#DB34F2"   # 10 Purple
PEMBE      = "#FF375F"   # 11 Pink

# Vurgu rengi tek yerden: markayı Apple mavisinden ayırmak istersen SADECE
# burayı değiştir (ör. Derin Mavi marka mavisi "#2CA6E7").
AKSAN = MAVI

# Etiketler — Labels/Dark. Metin hiyerarşisi yalnız bunlarla kurulur.
L1 = beyaz(1.00)    # birincil metin
L2 = beyaz(0.55)    # ikincil (açıklama, başlık etiketi)
L3 = beyaz(0.25)    # üçüncül (pasif, ipucu)
L4 = beyaz(0.10)    # dördüncül (neredeyse görünmez)

# Dolgular — Fills/Dark. Kontrol zeminleri yalnız bunlardan seçilir.
D1 = beyaz(0.10)    # 1 Primary
D2 = beyaz(0.08)    # 2 Secondary
D3 = beyaz(0.05)    # 3 Tertiary
D4 = beyaz(0.03)    # 4 Quaternary
D5 = beyaz(0.02)    # 5 Quinary

# Kontrol durum zeminleri (kit: Pop-up/Bordered Button "Dark/Content Area")
DOLGU_BOSTA    = beyaz(0.07)
DOLGU_USTUNDE  = beyaz(0.10)
DOLGU_BASILI   = beyaz(0.16)
DOLGU_PASIF    = beyaz(0.03)

AYRAC = beyaz(0.12)          # ince ayraç çizgileri
KENAR = beyaz(0.08)          # kart/panel kenarlığı
KENAR_ISIK = beyaz(0.16)     # cam gövdenin ÜST kenarındaki ışık çizgisi

PENCERE = "#1E1E1E"          # Window Backgrounds/Dark Background
ZEMIN   = "#141414"          # pencereden bir tık koyu (video kuyusu vb.)
SIYAH   = "#000000"


# =====================================================================
#  2. TİPOGRAFİ — Apple metin stili rampası (SF Pro)
# =====================================================================
# Yazı tipi yığını: macOS'ta gerçek SF Pro; Windows'ta (yarışma laptopu
# farklı olabilir — CLAUDE.md ilke 7) en yakın karşılıklara düşer.
F  = ("'SF Pro Text', '.AppleSystemUIFont', 'SF Pro Display', 'Inter', "
      "'Segoe UI Variable Text', 'Segoe UI', 'Helvetica Neue', sans-serif")
FM = "'SF Mono', 'Menlo', 'JetBrains Mono', 'Consolas', 'Courier New', monospace"

#            punto, ağırlık
BUYUK_BASLIK = (26, 700)
BASLIK1      = (22, 700)
BASLIK2      = (17, 700)
BASLIK3      = (15, 600)
USTYAZI      = (13, 700)   # Headline
GOVDE        = (13, 400)   # Body
GOVDE_VURGU  = (13, 600)
CAGRI        = (12, 400)   # Callout
CAGRI_VURGU  = (12, 600)
ALTBASLIK    = (11, 400)   # Subheadline
ALTBASLIK_V  = (11, 600)
DIPNOT       = (10, 400)   # Footnote
ETIKETCIK    = (10, 600)   # Caption1 Emphasized — grup başlıkları


def yazi(stil, renk=None, ek=""):
    """Metin stilini QSS parçasına çevirir: `yazi(GOVDE_VURGU, L1)`."""
    punto, agirlik = stil
    parca = f"font-size: {punto}px; font-weight: {agirlik};"
    if renk:
        parca += f" color: {renk};"
    return parca + (" " + ek if ek else "")


# =====================================================================
#  3. ÖLÇÜLER — Apple'ın 5 kademeli kontrol boyutu rampası
# =====================================================================
# (kitten ölçüldü: yükseklik / köşe yarıçapı / punto / yatay iç boşluk)
#   Mini 16/4/10/7 · Small 20/5/11/10 · Regular 24/6/13/12
#   Large 28/kapsül/13/14 · XL 36/kapsül/13/18
# DİKKAT: Large ve XL'de köşe yarıçapı SABİT DEĞİL, KAPSÜL (yükseklik/2).
# macOS 26 ile gelen "Liquid Glass" görünümünün en belirgin işareti budur.
BOY_MINI, BOY_KUCUK, BOY_NORMAL, BOY_BUYUK, BOY_XL = 16, 20, 24, 28, 36
YC_MINI, YC_KUCUK, YC_NORMAL = 4, 5, 6
YC_KAPSUL_BUYUK = BOY_BUYUK // 2      # 14
YC_KAPSUL_XL    = BOY_XL // 2         # 18
ATES_BOY = 44                         # ATEŞ butonu: XL'den biraz büyük (takım kararı 22.09)

YC_KART   = 12    # Group Box (kitten: beyaz %3 dolgu, 12 px yarıçap)
YC_PANEL  = 16    # büyük cam yüzeyler (kit "Large UI": 20 — biz 16 kullanıyoruz)
YC_ACILIR = 10    # popover / menü

BOSLUK  = 8       # temel ızgara birimi
KENAR_BOSLUK = 16


# =====================================================================
#  4. CAM (Liquid Glass taklidi)
# =====================================================================
def cam(opaklik=0.72, ton="#262626"):
    """Cam gövde dolgusu. Gerçek bulanıklık yok (bkz. modül başlığı);
    yarı saydam gövde + üst ışık çizgisi ile taklit edilir."""
    return (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {_a(ton, opaklik + 0.06)}, stop:1 {_a(ton, opaklik)})")


def golge(widget, yaricap=48, y=18, alfa=0.45):
    """Kit'in büyük cam yüzey gölgesi (y18 b48 siyah @%45). QSS gölge
    desteklemediği için widget'a efekt olarak takılır."""
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    from PySide6.QtGui import QColor
    e = QGraphicsDropShadowEffect(widget)
    e.setBlurRadius(yaricap)
    e.setOffset(0, y)
    e.setColor(QColor(0, 0, 0, int(alfa * 255)))
    widget.setGraphicsEffect(e)
    return e


# =====================================================================
#  5. Paylaşılan bileşen şablonları
# =====================================================================
# Kaydırıcı (Slider). Kit: oluk 6 px beyaz %10 tam yuvarlak, tutamaç beyaz
# daire + yumuşak gölge, dolu kısım vurgu rengi.
def slider_stil(nesne="ayarsl", vurgu=None, tutamac=20, oluk=6):
    """Kaydırıcı. Kit: oluk 6 px beyaz %10 tam yuvarlak, dolu kısım vurgu rengi,
    tutamaç 20 px beyaz daire.

    ⚠ Oluğa DİKEY MARJ vermek zorunludur. Yalnız `height` yazmak yetmiyor: Qt
    oluğu bileşenin tüm yüksekliğine yayıyor ve koyu arayüzde kaydırıcının
    arkasında açık gri bir kutu belirir (bir tur bunu yerel macOS stili sandık,
    değilmiş — kendi kuralımızmış). Marjı yükseklikten hesaplıyoruz ki tutamaç
    veya oluk kalınlığı değişince kendiliğinden doğru kalsın.

    ⚠ Durum ALT BİLEŞENDEN SONRA yazılır: `::handle:horizontal:disabled`.
    Ters sıra (`:disabled::handle`) Qt'de kuralı kaydırıcının GÖVDESİNE
    uygulatıyor — etkin kaydırıcının arkasında %25 beyaz kutu çıkıyordu (22.09)."""
    v = vurgu or AKSAN
    yari = tutamac // 2
    boy = tutamac + 4                     # bileşenin toplam yüksekliği
    dikey = (boy - oluk) // 2             # oluğu dikeyde ortalar
    tut_marj = (oluk - tutamac) // 2      # tutamaç oluğun dışına taşar (negatif)
    ortak = (f"height: {oluk}px; border-radius: {oluk / 2:g}px; "
             f"margin: {dikey}px {yari}px;")
    return f"""
    QSlider#{nesne} {{ min-height: {boy}px; background: transparent; border: none; }}
    QSlider#{nesne}::groove:horizontal    {{ {ortak} background: {D1}; }}
    QSlider#{nesne}::sub-page:horizontal  {{ {ortak} background: {v}; }}
    QSlider#{nesne}::add-page:horizontal  {{ {ortak} background: transparent; }}
    QSlider#{nesne}::handle:horizontal {{
        width: {tutamac}px; height: {tutamac}px;
        margin: {tut_marj}px -{yari}px;
        border-radius: {yari}px;
        background: #FFFFFF;
        border: 0.5px solid {siyah(0.12)};
    }}
    QSlider#{nesne}::handle:horizontal:pressed {{ background: #F2F2F2; }}
    QSlider#{nesne}::sub-page:horizontal:disabled {{ background: {D2}; }}
    QSlider#{nesne}::handle:horizontal:disabled   {{ background: {beyaz(0.25)}; }}
    """


def durum_bandi(renk_metin, boy=BOY_NORMAL):
    """Tam genişlik durum şeridi (BÖLGE GÜVENLİ / ATIŞ YASAK …).
    Apple'da uyarı satırı dolu bir blok değil, RENGİN KENDİSİYLE hafifçe
    tonlanmış bir yüzeydir; metin rengi bilgiyi taşır, zemin yalnızca ima eder."""
    return (f"background: {_a(renk_metin, 0.14)}; border: none; "
            f"border-radius: {YC_NORMAL}px; color: {renk_metin}; "
            f"min-height: {boy}px; max-height: {boy}px; "
            f"font-size: 11px; font-weight: 700; letter-spacing: 0.6px;")


# Uygulama genel yazı tipi adayları: ilki bulunan kullanılır. macOS'ta gerçek
# SF Pro; Windows'ta (yarışma laptopu farklı olabilir) Segoe UI Variable / Inter.
UYGULAMA_FONTLARI = (".AppleSystemUIFont", "SF Pro Text", "SF Pro Display",
                     "Inter", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue")


def uygulama_fontu(punto=10):
    """Sistemde GERÇEKTEN bulunan ilk yazı tipini döndürür.

    Eski kod `QFont(ad).exactMatch()` ile bakıyordu; bu yöntem macOS'ta
    `.AppleSystemUIFont` gibi takma adlarda yanlış cevap verebiliyor.
    QFontDatabase kurulu aileleri listelediği için kesin sonuç verir."""
    from PySide6.QtGui import QFont, QFontDatabase
    kurulu = set(QFontDatabase.families())
    for ad in UYGULAMA_FONTLARI:
        if ad in kurulu:
            return QFont(ad, punto)
    return QFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont).family(), punto)


def nokta(renk, cap=6):
    """Durum noktası (canlı akış, cihaz durumu, otonom durumu…).
    Apple'da durum noktası tam daire ve dolu tek renktir; kenarlık kullanılmaz."""
    return f"background: {renk}; border-radius: {cap / 2:g}px;"


def deger_etiketi(renk_metin):
    """Sayısal değer rozeti (kaydırıcıların sağındaki kutu) — mono yazı."""
    return (f"color: {renk_metin}; background: {_a(renk_metin, 0.14)}; "
            f"border: 1px solid {_a(renk_metin, 0.30)}; border-radius: {YC_NORMAL}px; "
            f"padding: 2px 9px; font-family: {FM}; font-size: 12px; font-weight: 600;")


# D-pad tuşları: Apple'ın XL kapsül butonu. Basılı hâl vurgu rengiyle dolar.
def dpad_stil(basili=False, merkez=False, en=58, boy=BOY_BUYUK):
    yc = boy // 2
    if basili:
        zemin, yazi_renk, kenar = AKSAN, "#FFFFFF", _a(AKSAN, 0.0)
    elif merkez:
        zemin, yazi_renk, kenar = _a(AKSAN, 0.18), AKSAN, _a(AKSAN, 0.35)
    else:
        zemin, yazi_renk, kenar = DOLGU_BOSTA, L1, "transparent"
    return f"""
    QPushButton {{
        background: {zemin};
        border: 1px solid {kenar};
        border-radius: {yc}px;
        color: {yazi_renk};
        font-size: {13 if not merkez else 10}px;
        font-weight: 600;
        min-width: {en}px; max-width: {en}px;
        min-height: {boy}px; max-height: {boy}px;
    }}
    QPushButton:hover {{ background: {AKSAN if basili else DOLGU_USTUNDE}; }}
    QPushButton:disabled {{ background: {DOLGU_PASIF}; color: {L3}; border-color: transparent; }}
    """


# =====================================================================
#  6. UYGULAMANIN TAM STİL SAYFASI
# =====================================================================
def qss() -> str:
    """Tüm arayüzün Qt stil sayfası. Nesne adları `arayuz_qt.py` ile birebir."""
    return f"""
    /* ---------- temel ---------- */
    QWidget {{
        background: transparent;
        color: {L1};
        font-family: {F};
        font-size: 13px;
    }}
    QToolTip {{
        background: rgba(38, 38, 38, 0.96);
        color: {beyaz(0.96)};
        border: 1px solid {KENAR};
        border-radius: {YC_NORMAL}px;
        padding: 3px 6px;
        font-size: 11px;
        font-weight: 500;
    }}
    #content {{
        background: {PENCERE};
    }}
    /* Tum arayuz bir QGraphicsView icinde olceklenerek ciziliyor; gorunumun
       kendi zemini olmamali, yoksa pencere rengi iki kez boyanir. */
    #view {{ background: {PENCERE}; border: none; }}

    /* ---------- üst şerit (büyük cam yüzey) ---------- */
    #top {{
        background: {cam(0.55)};
        border: 1px solid {KENAR};
        border-top: 1px solid {KENAR_ISIK};
        border-radius: {YC_PANEL}px;
    }}
    #brand    {{ {yazi(BASLIK3, L1)} background: transparent; letter-spacing: 0.2px; }}
    #brandtxt {{ {yazi(ALTBASLIK, L2)} background: transparent; }}
    #vdiv, #sbdiv {{ background: {AYRAC}; }}
    #tgcap {{
        {yazi(ETIKETCIK, L2)}
        background: transparent;
        letter-spacing: 0.6px;
        text-transform: uppercase;
    }}

    /* ---------- segmented control (ÇALIŞMA MODU / AKTİF GÖREV) ---------- */
    #tabs {{
        background: {D2};
        border: none;
        border-radius: {YC_NORMAL + 2}px;
        padding: 2px;
    }}
    #tab {{
        {yazi(GOVDE_VURGU, L1)}
        background: transparent;
        border: none;
        border-radius: {YC_NORMAL}px;
        padding: 0 12px;
        min-height: {BOY_NORMAL}px;
    }}
    #tab:hover   {{ background: {D3}; }}
    #tab:pressed {{ background: {DOLGU_BASILI}; }}
    #tab:checked {{
        background: {AKSAN};
        color: #FFFFFF;
    }}
    #tab:disabled          {{ color: {L3}; background: transparent; }}
    #tab:disabled:checked  {{ background: {_a(AKSAN, 0.35)}; color: {beyaz(0.60)}; }}

    /* ---------- açılır liste (kamera / çözünürlük) ---------- */
    /* Ok QSS'te KAPALI: macOS'ta kenarlık-üçgeni dev bir kamaya dönüşüyordu.
       Chevron'u SecimKutusu kendi çiziyor (bkz. arayuz_qt.py). */
    #camsel {{
        background: {DOLGU_BOSTA};
        border: none;
        border-radius: {YC_NORMAL}px;
        padding: 0 30px 0 12px;
        min-height: {BOY_NORMAL}px;
        {yazi(GOVDE_VURGU, L1)}
    }}
    #camsel:hover     {{ background: {DOLGU_USTUNDE}; }}
    #camsel:on        {{ background: {DOLGU_BASILI}; }}
    #camsel:disabled  {{ background: {DOLGU_PASIF}; color: {L3}; }}
    #camsel::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 0px; height: 0px; margin: 0px; border: none; background: transparent;
    }}
    #camsel::down-arrow {{
        image: none; width: 0px; height: 0px; margin: 0px;
        border: none; background: transparent;
    }}
    #camsel QAbstractItemView {{
        background: rgba(38, 38, 38, 0.98);
        color: {L1};
        selection-background-color: {AKSAN};
        selection-color: #FFFFFF;
        border: 1px solid {KENAR};
        border-radius: {YC_ACILIR}px;
        padding: 4px;
        outline: none;
    }}
    #camsel QAbstractItemView::item {{
        padding: 4px 10px; border-radius: {YC_KUCUK}px; min-height: 22px;
    }}
    #camsel QAbstractItemView::item:hover    {{ background: {D2}; }}
    #camsel QAbstractItemView::item:selected {{ background: {AKSAN}; color: #FFFFFF; }}

    /* ---------- CANLI rozeti ---------- */
    #livebadge {{
        background: {_a(KIRMIZI, 0.16)};
        border: none;
        border-radius: {YC_KUCUK}px;
    }}
    #livet {{ {yazi(ETIKETCIK, KIRMIZI)} background: transparent; letter-spacing: 0.8px; }}

    /* ---------- ACİL DURDUR (XL kapsül, yıkıcı) ---------- */
    #estop {{
        background: {_a(KIRMIZI, 0.20)};
        border: none;
        border-radius: {YC_KAPSUL_XL}px;
        color: {KIRMIZI};
        padding: 0 20px;
        min-height: {BOY_XL}px;
        {yazi(GOVDE_VURGU)}
        letter-spacing: 0.3px;
    }}
    #estop:hover   {{ background: {_a(KIRMIZI, 0.30)}; }}
    #estop:pressed {{ background: {_a(KIRMIZI, 0.38)}; }}
    #estop:checked {{ background: {KIRMIZI}; color: #FFFFFF; }}

    /* ---------- kamera kuyusu ---------- */
    #cam {{
        background: {SIYAH};
        border: 1px solid {KENAR};
        border-radius: {YC_KART}px;
    }}
    #video {{
        background: {SIYAH};
        border-radius: {YC_KART}px;
        color: {L3};
        {yazi(GOVDE)}
    }}

    /* ---------- ayar paneli (video üstü popover) ---------- */
    #ayarbtn {{
        background: {cam(0.70)};
        border: 1px solid {KENAR_ISIK};
        border-radius: {YC_NORMAL + 2}px;
        color: {L1};
        font-size: 15px;
    }}
    #ayarbtn:hover {{ background: {_a(AKSAN, 0.80)}; border-color: {AKSAN}; }}
    #ayarpanel {{
        background: rgba(30, 30, 30, 0.97);
        border: 1px solid {KENAR};
        border-top: 1px solid {KENAR_ISIK};
        border-radius: {YC_PANEL}px;
    }}
    #ayarbaslik, #ayartitle {{ {yazi(USTYAZI, L1)} background: transparent; }}
    #ayarkapat, #ayarclose {{
        background: {D2}; border: none; border-radius: 11px;
        color: {L2}; font-size: 13px; font-weight: 600;
        min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
    }}
    #ayarkapat:hover, #ayarclose:hover {{ background: {_a(KIRMIZI, 0.85)}; color: #FFFFFF; }}
    #ayarlbl  {{ {yazi(CAGRI_VURGU, L1)} background: transparent; }}
    /* ayar panelindeki bölüm başlığı: Apple'da kutu değil, üstünde boşluk olan
       küçük ikincil bir etiket satırıdır. */
    #ayargrup {{
        {yazi(ETIKETCIK, L2)}
        background: transparent;
        letter-spacing: 0.6px;
        padding: 10px 0 2px 0;
    }}
    /* panel içi ikincil kartlar (NİŞAN KONTROLÜ, GÖREV BİLGİSİ …) */
    #altkart {{
        background: {D3};
        border: none;
        border-radius: {YC_ACILIR}px;
    }}
    #ayarkaydir, #ayaric {{ background: transparent; border: none; }}
    #ayarkaydir QScrollBar:vertical {{
        background: transparent; width: 12px; margin: 0;
    }}
    #ayarkaydir QScrollBar::handle:vertical {{
        background: {beyaz(0.30)}; border-radius: 3px; min-height: 28px;
        margin: 3px 3px 3px 3px;
    }}
    #ayarkaydir QScrollBar::handle:vertical:hover {{ background: {beyaz(0.55)}; }}
    #ayarkaydir QScrollBar::add-line:vertical, #ayarkaydir QScrollBar::sub-line:vertical {{
        height: 0px; background: transparent;
    }}
    #ayarkaydir QScrollBar::add-page:vertical, #ayarkaydir QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    #ayardeg {{
        {yazi(CAGRI_VURGU, L1, f"font-family: {FM};")}
        background: {D2}; border: none; border-radius: {YC_NORMAL}px;
        padding: 2px 9px;
    }}
    #ayarinfo {{
        background: {D2}; border: none; border-radius: 8px;
        color: {L2}; font-size: 10px; font-weight: 700;
        min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;
    }}
    #ayarinfo:hover {{ background: {_a(AKSAN, 0.90)}; color: #FFFFFF; }}
    #ayaralt {{
        background: {DOLGU_BOSTA}; border: none; border-radius: {YC_NORMAL}px;
        color: {L1}; padding: 0 12px; min-height: {BOY_NORMAL}px;
        {yazi(CAGRI_VURGU)}
    }}
    #ayaralt:hover   {{ background: {DOLGU_USTUNDE}; }}
    #ayaralt:pressed {{ background: {DOLGU_BASILI}; }}
    #ayarkaydet {{
        background: {AKSAN}; border: none; border-radius: {YC_NORMAL}px;
        color: #FFFFFF; padding: 0 16px; min-height: {BOY_NORMAL}px;
        {yazi(GOVDE_VURGU)}
    }}
    #ayarkaydet:hover   {{ background: {_a(AKSAN, 0.85)}; }}
    #ayarkaydet:pressed {{ background: {_a(AKSAN, 0.70)}; }}

    /* ---------- sağ kolon panelleri / kartlar ---------- */
    #panelk {{
        background: {D4};
        border: none;
        border-radius: {YC_KART}px;
    }}
    #ph {{
        {yazi(ETIKETCIK, L2)}
        background: transparent;
        letter-spacing: 0.6px;
        text-transform: uppercase;
    }}
    #turn {{ {yazi(BASLIK2, L1, f"font-family: {FM};")} background: transparent; }}
    #asamap {{
        background: {D4};
        border: none;
        border-radius: {YC_KART}px;
    }}
    #cit  {{ background: {AYRAC}; }}
    #kural {{ {yazi(ALTBASLIK, L2)} background: transparent; }}
    #bosmsg {{ {yazi(CAGRI, L3)} background: transparent; }}
    #ipucu  {{ {yazi(DIPNOT, L3)} background: transparent; }}
    #turbilgi {{ {yazi(ALTBASLIK_V, L2)} background: transparent; }}

    /* ---------- Aşama-1 sıralı kartları ---------- */
    #kart {{
        background: {D3};
        border: 1px solid transparent;
        border-radius: {YC_ACILIR}px;
    }}
    #kart:hover {{ background: {D2}; border-color: {_a(AKSAN, 0.45)}; }}
    #kartno {{
        {yazi(ALTBASLIK_V, "#FFFFFF")}
        background: {AKSAN};
        border-radius: 9px;
        min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
    }}
    #kartad {{ {yazi(CAGRI_VURGU, L1)} background: transparent; }}

    /* ---------- hedef listesi ---------- */
    #hname {{ {yazi(CAGRI_VURGU, L1)} background: transparent; }}
    #hconf {{ {yazi(DIPNOT, L2, f"font-family: {FM};")} background: transparent; }}

    /* ---------- lazer gücü düğmesi (ATEŞ butonunun İÇİNDE, solda) ----------
       Kırmızı zemin üstünde hem ATEŞ (tonlu) hem ATEŞİ KES (dolu) hâlinde okunsun
       diye beyaz yarı saydam daire; renk ATEŞ yazısıyla aynı dilde. */
    #lazerayar {{
        background: {beyaz(0.14)}; border: none; border-radius: {(ATES_BOY - 10) // 2}px;
        color: #FFFFFF; font-size: 15px;
    }}
    #lazerayar:hover   {{ background: {beyaz(0.24)}; }}
    #lazerayar:pressed {{ background: {beyaz(0.32)}; }}

    /* ---------- ATEŞ (XL kapsül) ---------- */
    #fire {{
        background: {_a(KIRMIZI, 0.20)};
        border: none;
        border-radius: {ATES_BOY // 2}px;
        color: {KIRMIZI};
        min-height: {ATES_BOY}px;
        {yazi(GOVDE_VURGU)}
        letter-spacing: 1.2px;
    }}
    #fire:hover    {{ background: {_a(KIRMIZI, 0.30)}; }}
    #fire:pressed  {{ background: {_a(KIRMIZI, 0.38)}; }}
    #fire:checked  {{ background: {KIRMIZI}; color: #FFFFFF; }}
    #fire:disabled {{ background: {DOLGU_PASIF}; color: {L3}; }}
    #firest {{ {yazi(ALTBASLIK, L2)} background: transparent; }}

    /* ---------- aktif hedef şeridi ---------- */
    #engok   {{ {yazi(ALTBASLIK_V, YESIL)} background: transparent; }}
    #engname {{ {yazi(BASLIK3, L1)} background: transparent; }}
    #engsub  {{ {yazi(ALTBASLIK, L2)} background: transparent; }}
    /* azimut/yükseliş okuması: Apple'ın "group box" yüzeyi (yalnız dolgu) */
    #angtgl {{
        background: {D4};
        border: none;
        border-radius: {YC_KART}px;
        {yazi(CAGRI_VURGU, L1)}
    }}
    #tgll    {{ {yazi(ALTBASLIK, L2)} background: transparent; }}

    /* ---------- alt durum çubuğu ---------- */
    #sbar {{
        background: {cam(0.45)};
        border: 1px solid {KENAR};
        border-top: 1px solid {KENAR_ISIK};
        border-radius: {YC_KART}px;
    }}
    #sbseg {{ {yazi(ALTBASLIK, L2)} background: transparent; }}
    #clk   {{ {yazi(GOVDE_VURGU, L1, f"font-family: {FM};")} background: transparent; margin-left: 10px; }}
    #stt   {{ {yazi(ALTBASLIK, L2)} background: transparent; }}

    /* ---------- genel kaydırma çubuğu (Apple: ince, saydam oluk) ---------- */
    QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; }}
    QScrollBar:vertical   {{ width: 12px; margin: 0; }}
    QScrollBar:horizontal {{ height: 12px; margin: 0; }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {beyaz(0.30)}; border-radius: 3px; margin: 3px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {beyaz(0.55)};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; background: transparent; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---------- onay kutusu (Apple: 16 px, dolu vurgu) ---------- */
    QCheckBox {{ {yazi(ALTBASLIK_V, L1)} background: transparent; spacing: 7px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: {YC_KUCUK}px;
        background: {D1}; border: none;
    }}
    QCheckBox::indicator:hover   {{ background: {DOLGU_USTUNDE}; }}
    QCheckBox::indicator:checked {{ background: {AKSAN}; }}
    QCheckBox::indicator:disabled {{ background: {D4}; }}

    /* ---------- sayı kutusu ---------- */
    QSpinBox {{
        background: {D2}; border: none; border-radius: {YC_NORMAL}px;
        color: {L1}; padding: 0 8px; min-height: {BOY_NORMAL}px;
        {yazi(GOVDE)}
        font-family: {FM};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; border: none; }}
    """


# =====================================================================
#  7. Kendi kendini test
# =====================================================================
def _stil_kapsami_testi():
    """Arayüzdeki HER nesne adının bir stil karşılığı var mı?

    Neden kapı testi: Qt'de stil sayfasında karşılığı olmayan bir bileşeni
    macOS YEREL stiliyle çizer — koyu arayüzün ortasında açık gri bir kutu
    belirir. Bu sessiz bir bozulmadır (hata vermez, sadece çirkinleşir) ve
    kaydırıcılarda bir kez başımıza geldi. Yeni bir nesne adı eklendiğinde bu
    test kırmızıya düşer ve stilini yazmayı hatırlatır."""
    import os, re
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arayuz_qt.py")
    if not os.path.isfile(yol):
        return
    kaynak = open(yol, encoding="utf-8").read()
    stil = qss()
    # Stili QSS'te değil, kod içinde satır içi verilenler (bilinçli istisnalar)
    satir_ici = {"ayarsl", "bolgestatus"}
    eksik = sorted({m.group(1) for m in re.finditer(r'setObjectName\("([^"]+)"\)', kaynak)}
                   - {m.group(1) for m in re.finditer(r'#([a-zA-Z0-9_]+)', stil)}
                   - satir_ici)
    assert not eksik, f"stil sayfasında karşılığı olmayan nesne adları: {eksik}"


if __name__ == "__main__":
    s = qss()
    assert "{" in s and "}" in s
    # Biçimlendirme kazası: f-string'den sızmış tek süslü parantez kalmamalı
    assert "{{" not in s and "}}" not in s, "QSS'te kaçmamış çift süslü parantez var"
    for ad in ("#top", "#tab", "#camsel", "#estop", "#fire", "#sbar", "#panelk",
               "#ayarpanel", "#kart", "#video", "QScrollBar", "QCheckBox"):
        assert ad in s, f"stil sayfasında {ad} yok"
    assert slider_stil().count("QSlider#ayarsl") >= 5
    assert dpad_stil(basili=True).count("QPushButton") >= 2
    assert _a("#0091FF", 0.2) == "rgba(0, 145, 255, 0.200)"
    assert nokta(KIRMIZI, 8) == f"background: {KIRMIZI}; border-radius: 4px;"
    _stil_kapsami_testi()
    print("tasarim testleri OK — renk dönüşümü, stil sayfası bütünlüğü, şablonlar, stil kapsamı")
