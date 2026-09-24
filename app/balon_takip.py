# -*- coding: utf-8 -*-
"""DERIN MAVI - Balon takibi (Asama 2/3): BALONU TAKIP ET, KIMLIGINI ARACTAN OGREN.

Neden (24.09 takim karari): araci (F16/Heli/Fuze/IHA) okumak aciya, uzakliga ve isiga
bagli; bazen HIC okunmuyor. Balon ise yuvarlak, tek renk, her acidan ayni: bir kez
kilitlenince okumasi kolay (olculdu: 213 px kilit penceresinde 12 px balon %95).
Imha kaniti da balonun patlamasidir. Bu yuzden roller ters:

  * TAKIP EDILEN = BALON. Nisan dogrudan balonun merkezine gider; govdeden ofset
    kestirimi (algi.nisan_noktasi / balon_ofset) bu yolda kullanilmaz.
  * ARAC = KIMLIK KANITI. Arac okunabildigi her karede hemen ustundeki balonun
    KIMLIK KARTINA oy verir: taraf (govde rengi, renk_analizi) + tip (kesin taninmis
    sinif). Arac modeli okuyamazsa balonun HEMEN USTUNDEKI govdenin rengi taraf oyu
    verir (tip vermez). Kart bir kez kesinlesince arac gorunmese de gecerlidir.
  * KARAR: A2'de her balon hedeftir (sartname: A1-A2'de dost yok). A3'te yalniz karti
    "Düşman" olan balon — kart eksik/belirsizse ATES YOK: dost vurmak -10, beklemek bedava.
  * IMHA: ates edilen balon kaybolursa imhadir. Balonsuz kalan arac bir daha hedef
    olmaz, cunku hedef zaten balondur (arac icin ayrica "vuruldu" yasagi gerekmez).
  * MENZIL (A3): balonun piksel genisligi + olculen capi (ayar "balon_cap_cm") ->
    mesafe. Tipin bandi disinda ates yok (F16 10-15, Heli/Fuze 5-15, IHA 0-15 m).

Sartname V1.5 §5.4 [KESIN]: tum maketlerin ALTINA kirmizi balon; Sekil 3'te balon maketle
ayni direkte, hemen altinda. A1-A2'de yalniz kirmizi maket, A3'te dost mavi / dusman kirmizi.
Gercek Sekil 3 fotografinda olculdu: tam kare taramasi balonu 38 px'te bile ancak %24 ile
gordu, 19 px ve altinda HIC gormedi; 213 px pencere 12-38 px'te %88-97. Uzak balonu bu
yuzden pencereler bulur ve tasir (arac hic okunmasa da kirmizi leke pencereleriyle).

24.09 koridor videosu (kendi kameramiz, 1080p -> 1280x720, 140 sn, kirmizi tisortlu kisi
elinde drone/F16 + altinda balon, 1-20 m; elle dogrulanmis referansla). Bulunan ve
duzeltilen: model gri cami / tisortu / zemin yansimasini "balon" sandi (renk + en/boy
suzgeci), yansima kilidi aldi (dikey devir guvenle), pencere 213 px balonu kaciriyordu
(128 px: 14-28 px balonda 24/30 -> 28/30), arac modeli el yapimi maketi neredeyse hic
okumadi (govde rengi oyu). Sonuc (gercek zamanli oynatma): 16-20 px balonda kilit A2
%84 -> %99, A3 %50 -> %100; A3 20-60 px %50-63 -> %98-100; maketler maviye boyaninca
1904 karede kilit 0. Balonsuz 23.09 ekran kayitlarinda (hareketli namlu, kirmizi F16 elde)
~12 bin karede yanlis balon / kilit 0. Yontem: CLAUDE.md §8.

Model cagrisi kare basina TEK toplu cikarimdir: [tam kare] + pencereler. Olculdu
(RTX 3050 Ti): tam kare 19 ms, tam kare + 2 pencere 29 ms — maliyetin cogu cagri
basina sabit yuk, pencere basina degil.
"""
import math
import threading
import time

import cv2
import numpy as np

import algi
from renk_analizi import renk_oranlari

# ---- Iz (takip) ----
ONAY_KARE = 3            # iz kilitlenmeden once en az bu kadar karede GERCEKTEN gorulmeli
GOSTER_KARE = 2          # tek karelik yanlis kutu ekranda yanip sonmesin
KAYIP_S = 0.5            # bu kadar gorulmeyen iz silinir (algi.KILIT_BIRAKMA_S ile ayni gerekce)
TAHMIN_AZAMI_S = 0.3     # hizla ileri tasima tavani (uzun kayipta kestirim sacmalamasin)
HIZ_YUMUSATMA = 0.3      # iz hizi EMA katsayisi (yalniz esleme kapisi ve hayalet kutu icin)
ESLESME_KAT = 1.5        # eslesme yaricapi = balon boyunun bu kati ...
ESLESME_EN_AZ_PX = 25.0  # ... en az bu kadar piksel
# Birkac kare gorulup kaybolan genc iz (yansima, kameranin dibinden gecen kol) kilidi
# KAYIP_S boyunca hayalet olarak tutuyordu; video: 11 kez 0.5 sn bos kilit.
OTURMUS_KARE = 10        # bu kadar gorulmemis iz "genc"tir ...
KAYIP_GENC_S = 0.2       # ... ve bu kadar gorulmezse silinir
# YENI kilit icin izin guven ortalamasi (EMA). Olculdu: gercek balonlarin %90'i >= 0.55,
# model yanlislarinin (tisort, cam, yansima) ortancasi 0.45. Kurulmus kilit bu esikle
# BIRAKILMAZ; uzaklasan balonun guveni dussede takip surer.
KILIT_GUVEN = 0.5
GUVEN_YUMUSATMA = 0.3
# YENI kilit icin son karelerde modelce GORULME orani (EMA). Olculdu (23.09 ekran kaydi):
# yakindaki buyuk kirmizi F16'nin 14 px'lik parcasi 10 karede 3 kez %34-66 "balon" cikti,
# aralar KAYIP_GENC_S'den kisa oldugu icin iz yasadi ve 3. gorulmede kilit aldi. Gercek
# balon menzil icinde karelerin %90'indan cogunda gorulur.
KILIT_ORAN = 0.5
ORAN_YUMUSATMA = 0.3
KENAR_PX = 3             # kare kenarina degen kutu YENI kilit almaz (yari gorunen cisim)
# CIFT ESIK (ByteTrack'teki gibi): yeni iz "balon_esik" (0.30) ister, DOGRULANMIS izi surdurmek
# icin IZ_ESIK yeter. Olculdu (24.09 video, 14-24 px kilitli balonun 338 hayalet karesi):
# model balonu 87 karede 0.15-0.30 ile goruyordu — esik yuzunden hayalet, ates kapisi kesiliyordu.
IZ_ESIK = 0.15

# ---- Renkle devam: model kisa sure kacirirsa dogrulanmis izi kirmizi leke tasir ----
# Hareket bulaniklastiriyor / 15 m'de model tek tuk kare kaciriyor; her kaciris
# ates kapisinin 0.5 sn bekleme sayacini sifirliyordu (hayalet = ates yok).
RENK_AZAMI_S = 1.5       # model bu kadar gormezse renk izi de biter (hayalet -> silinir)
RENK_ATES_S = 0.4        # model bundan uzun gormediyse ates ENGELLI (yalniz nisan surer)
RENK_BOY = (0.7, 1.4)    # leke boyu / iz boyu
RENK_UZAKLIK_KAT = 0.6   # leke merkezi kestirilen yere en fazla boyun bu kati uzakta
RENK_DOLGU = 0.5         # leke alani / kutu alani (daire 0.785, cizgi/kol cok daha az)

# ---- Tespit suzgeci ----
# Olculdu (24.09 koridor videosu, 3866 gercek balon tespiti): en/boy %99'u 0.73-1.29.
# Modelin "balon" dedigi tisort/kol kutulari 0.40-0.61 — eski (0.4, 2.5) hepsini geciriyordu;
# 0.6 alt siniri da uzaktaki tisortu (23x38 px, %51) gecirdi, kilit + renk izi 1.5 sn surdu.
EN_BOY = (0.7, 1.5)
# Sartname §5.4: TUM balonlar kirmizi. Kutunun ic %60'inda kirmizi piksel orani; gercek
# balon en az 0.83 (556 ornek), model "balon" dedigi gri cam kapi 0.00, parlak zemindeki
# yansima ~0.30. Model renge dayaniyor ama gri camı da %57 "balon" buldu.
KIRMIZI_EN_AZ = 0.45
# Model renge cok dayaniyor: duzensiz kirmizi leke %93 "balon" cikti (24.09 sentetik
# deneme). Kirmizi maket GOVDESI balon sanilmasin: merkezi bir arac kutusunun UST
# bu kadarinda kalan aday atilir (balon govdenin ALTINDA asilidir).
GOVDE_UST = 0.6

# ---- Pencereler (kucuk balonu buyutup okumak) ----
KUCUK_PX = 64            # bundan kucuk kilitli balon kilit penceresinde de taranir
# Olculdu (24.09 video, 14-28 px 30 gercek balon, balona ortali pencere, esik 0.30):
#   320 px 4/30 (ort. guven 0.10) · 256 px 16/30 · 213 px 24/30 (0.55) · 160 px 26/30 ·
#   128 px 28/30 (0.82). Balon modeli, arac modelinin tersine, BUYUTMEYI sever: balon 640
#   girdide ~85 px olunca en iyi. Eski en kucuk pencere 213 px'ti.
PENCERE_KAT = 7          # kilit/iz penceresi = balon boyunun 7 kati ...
PENCERE_EN_AZ = 128      # ... en az 128 px (640 girdide 5x)
PENCERE_EN_COK = 640
# Kirmizi leke penceresi: lekenin 2.2 kati, en cok 320 px. Uzakta balon kirmizi govde ve
# (videoda) tisortle TEK leke oluyor; eski kural (6x, en az 214) 320 px acip balonu
# kaybediyordu. 2.2x birlesik lekeyi de kapsar, balon yine buyuk gorunur.
ONERI_KAT = 2.2
ONERI_EN_COK = 320
PENCERE_AZAMI = 4        # kilit yokken kare basina en cok pencere (maliyet sabit kalsin)
KIRMIZI_PERIYOT = 4      # kilit yokken kirmizi leke pencereleri bu kadar karede bir

# ---- Kimlik karti ----
KART_ONAY = 3            # "Düşman" icin en az bu kadar dusman oyu ...
DOST_ORAN = 4            # ... ve dusman oyu dost oyunun en az 4 kati (dost oyu kolay agir basar)
DOST_ONAY = 2            # "Dost" icin bu kadar dost oyu yeter (temkin: dost vurmak -10)
TIP_ONAY = 2             # tip icin en az bu kadar oy
KART_TAVAN = 60          # oy toplami bunu asinca yarilanir: kart yeni kanita kapanmasin
ALT_KAT = 2.0            # balon arac kutusunun altinda en fazla arac boyunun bu kati kadar

# ---- Govde rengi (arac modeli okuyamazken taraf kaniti) ----
# Olculdu (24.09 video): arac modeli el yapimi drone/F16'yi balon 20-60 px iken 220 karenin
# 2'sinde, 301 karenin 3'unde gordu; A3 karti ancak ~4 m'de kuruldu. Balonun yeri ise
# kesin: govde HEMEN USTUNDE ve rengi taraftir (sartname: dost mavi, dusman kirmizi).
# Bolge: balonun ustu, yatayda +-GOVDE_YATAY boy, yukari GOVDE_YUKARI boy; balonun kendi
# pikselleri maskelenir. Sayilan: balonun SUTUNUNA (+-GOVDE_SUTUN) giren, alt kenari balona
# yakin (GOVDE_BOSLUK) ve bolgenin ust/yan kenarina DEGMEYEN lekelerin TOPLAM alani.
#   * toplam: yandan bakilan F16 ince, 3-5 parcaya bolunuyor; tek leke esigi %46 tuttu,
#     toplam %80 (videoda 398 ornek, tek leke 185 / toplam 318 dogru oy).
#   * kenara degmeme: arka plandaki genis yuzey (tisort, duvar, MAVI GOKYUZU) govde degil —
#     yoksa gokyuzu her dusman balonunu "dost" yapar, kirmizi tisort yerdeki balonu dusman.
# Dost ONCELIKLI: mavi esigi gevsek, mavi varsa kirmizi oy YOK.
GOVDE_YATAY = 2.0
GOVDE_YUKARI = 2.5
GOVDE_SUTUN = 0.75
GOVDE_BOSLUK = 1.5
GOVDE_KIRMIZI_ALAN = 0.10  # toplam kirmizi >= bu x boy^2 (gevsek esikte yerdeki balona 101 oy)
GOVDE_CYAN_ALAN = 0.06     # mavi daha kucukken bile sayilir (dost vurmak -10)
# Kirmizi oy KARTA ancak surekliyse yazilir: tek tuk oy (sandalye benegi, arkadan gecen kisi)
# zamanla birikip yerdeki balonu dusman yapmasin. Oran = son karelerde kirmizi govde gorulme
# EMA'si. Dost oyu BEKLEMEDEN yazilir.
GOVDE_ORAN_YUMUSATMA = 0.2
GOVDE_ORAN_ESIK = 0.5
# renk_analizi esikleriyle ayni kirmizi (gevsek esik ten/sandalye benegini da aliyordu);
# cyan (#00A3E0, H~98) daha genis: uzakta/golgede doygunluk duser, dostu kacirmak pahali.
GOVDE_KIRMIZI_HSV = (((0, 110, 60), (12, 255, 255)), ((168, 110, 60), (180, 255, 255)))
GOVDE_CYAN_HSV = (((85, 60, 50), (112, 255, 255)),)

# ---- Govde/balon ust uste (arac okunamazken kirmizi govde balon sanilirsa) ----
YATAY_KAT = 0.8
DIKEY_KAT = 4.0
GOVDE_DEVIR_KARE = 3     # kilitli izin altinda bu kadar kare balon gorulurse kilit ona gecer

# ---- Ates / imha ----
ATES_SURE_S = 2.0        # varsayilan ates turu (arayuz OTONOM_ATES_SURE'yi ates_basladi'ya verir)
IMHA_S = 3.0             # ates basladiktan sonra bu sure icinde kaybolan balon = imha
#                          (ates turu + kamera gecikmesi + kayip siniri; tur uzayinca buyudu)
AZAMI_ATES = 3           # patlamayan balona (gercek lazerle) en cok bu kadar ates turu
YASAK_S = 10.0           # sonra bu kadar yeniden secilmez (arayuz OTONOM_BEKLEME_SURE ile ayni)
# ---- Kart tasima: balon KAYIP_S'den uzun kaybolup AYNI YERDE yeniden bulunursa ----
# Arac okumak zor; kaybolan balonun karti yeni izine gecmezse A3'te arac yeniden okunana
# kadar ates edilemez. Ama yanlis tasima (dusman karti dosta) -10 puandir, bu yuzden:
# tek aday sarti, patlayan balonun karti TASINMAZ, tasinan dusman oyu KART_ONAY ile sinirli
# (DOST_ONAY dost oyu karti hemen cevirir).
KART_HAFIZA_S = 1.5
KART_TASIMA_KAT = 2.0    # yeni balon, kaybolanin kestirilen yerine boyunun bu kati icinde

# ---- Menzil (A3, sartname §6.3) ----
MENZIL = {"f16": (10.0, 15.0), "helikopter": (5.0, 15.0), "fuze": (5.0, 15.0),
          "drone": (0.0, 15.0)}
ORTAK_MENZIL = (10.0, 15.0)   # tip bilinmiyorsa uc tip icin de gecerli bant (CLAUDE.md §2)
MENZIL_PAY = 0.5         # kestirim hatasina pay: bant sinirlarinin bu kadar icinde ates
BOY_YUMUSATMA = 0.3      # mesafe icin balon genisligi EMA katsayisi

# Olu bolge (ates kapisi) balon kutusu yuksekliginin orani: lazer yaricapin yarisi
# icindeyse "nisanda". Arac kutusuna gore ayarli olu_bolge_kutu (0.12) burada kullanilmaz.
OLU_ORANI = 0.25
# A3: balonun ic %40'inin bu kadari dost mavisiyse (mavi govde onunde) ateş yok.
ONDE_MAVI_ORAN = 0.15

# ---- LAZER ALTINDA (24.09 saha) ----
# Lazer balona degince kamerada doygun (beyaz) bir nokta olur ve model balonu tanimaz:
# her atista ~0.25 sn sonra (kamera+islem gecikmesi) iz hayalete dustu, ates kapisi
# lazeri kesti, balon hic 0.2 sn'den uzun isinmadi (%7 de %55 de ayni). Koridor videosundaki
# 122 gercek balona yapay nokta basildi: yaricap 0.15 boy -> model 105/122, kenarda 58/122.
# Ates suresince iki onlem, IKISI DE o karedeki kirmizi kanita bagli (CLAUDE.md §1 kural 7):
#   * TEMIZLIK: balon HALA yerindeyse noktanin pikselleri modele verilmeden once cevreden
#     doldurulur (105 -> 114, kenarda 58 -> 87). Kosulsuz temizlik patlamis balonun
#     arkasindaki duvarda noktanin kirmizi halesinden "balon" uyduruyordu (3 -> 45 / 244).
#   * HALKA KANITI: model yine kacirirsa iz yerinde tutulur — nokta HARIC balon dairesi
#     kirmizi VE dis halka kirmizi DEGIL (sinirli leke; kirmizi govde/arka plan degil).
#     Olculdu: balonda 485/487, bos yerde 5/1220 yanlis. Nokta balonun yarisini kapatirsa
#     karar yok -> kanit yok -> iz hayalet, ates kesilir (guvenli taraf).
LAZER_GECIKME_S = 0.35   # lazer sonunce de bu kadar kare noktayi gosterir (kamera + islem)
LAZER_V, LAZER_S = 230, 110   # doygun nokta (HSV): cok parlak ve soluk
HALKA_IC = 0.5           # nokta haric balon dairesinin (r <= 0.5 boy) en az bu kadari kirmizi
HALKA_DIS = 0.5          # dis halkanin (0.7-1.0 boy) en cok bu kadari kirmizi
HALKA_KARAR = 0.10       # nokta disinda dairenin bu kadari kalmadiysa karar yok

_izler = {}              # iz id ("B7") -> iz sozlugu
_yasak_bolgeler = []     # silinen yasakli izlerin son yeri: yeni kimlikle dogan ayni balon
_kayip_kartlar = []      # silinen izlerin karti: ayni yerde yeniden bulunan balona gecer
_durum = {"sira": 0, "kilit": None, "ust_sayac": 0, "sayac": 0, "asama": None,
          "imha": 0, "son_imha_t": 0.0, "son_imha_id": None, "kare_w": 1280}
_kayma = [0.0, 0.0]
_kayma_kilit = threading.Lock()


def sifirla():
    """Tum izleri, kilidi ve sayaclari temizler (kamera degisince/kopunca)."""
    _izler.clear()
    _yasak_bolgeler.clear()
    _kayip_kartlar.clear()
    _durum.update(kilit=None, ust_sayac=0, sayac=0, imha=0, son_imha_t=0.0,
                  son_imha_id=None)
    with _kayma_kilit:
        _kayma[0] = _kayma[1] = 0.0


def balon_id_mi(tid):
    return isinstance(tid, str) and tid.startswith("B")


def kilitli():
    return _durum["kilit"]


def kilidi_birak():
    _durum["kilit"] = None
    _durum["ust_sayac"] = 0


def son_imha():
    """{"sayi", "t", "id"}: arayuz "balon patladi" mesaji icin."""
    return {"sayi": _durum["imha"], "t": _durum["son_imha_t"], "id": _durum["son_imha_id"]}


def kamera_kaymasi_bildir(dx, dy):
    """algi.kamera_kaymasi_bildir ile ayni: namlu donunce sahnenin goruntudeki kaymasi.
    Olmasaydi pan'da balon "yerinden firlamis" gorunur, iz kopup yeni kimlik alirdi."""
    with _kayma_kilit:
        _kayma[0] += float(dx)
        _kayma[1] += float(dy)


def _kaymayi_uygula(simdi):
    with _kayma_kilit:
        dx, dy = _kayma
        _kayma[0] = _kayma[1] = 0.0
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return
    for iz in _izler.values():
        if _namluya_bagli(iz, simdi):
            continue
        x1, y1, x2, y2 = iz["box"]
        iz["box"] = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


# ---------------- geometri ----------------
def _merkez(b):
    return (b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5


def _boy(b):
    return max(1.0, b[2] - b[0], b[3] - b[1])


def _tahmin_merkez(iz, simdi):
    cx, cy = _merkez(iz["box"])
    if _namluya_bagli(iz, simdi):
        return cx, cy
    dt = min(max(0.0, simdi - iz["t_son"]), TAHMIN_AZAMI_S)
    return cx + iz["vx"] * dt, cy + iz["vy"] * dt


def _ustunde(ust, alt):
    """`ust` kutusu `alt` kutusunun HEMEN USTUNDE mi (ayni asili hat)?"""
    ux, uy = _merkez(ust)
    ax, ay = _merkez(alt)
    w = max(ust[2] - ust[0], alt[2] - alt[0])
    h = max(ust[3] - ust[1], alt[3] - alt[1])
    return abs(ux - ax) <= YATAY_KAT * w and 0 < ay - uy <= DIKEY_KAT * h


def _govde_mi(kutu, araclar):
    cx, cy = _merkez(kutu)
    for d in araclar:
        x1, y1, x2, y2 = d["box"]
        if x1 <= cx <= x2 and y1 <= cy <= y1 + GOVDE_UST * (y2 - y1):
            return True
    return False


def _kenarda(kutu, sekil):
    H, W = sekil[:2]
    return (kutu[0] <= KENAR_PX or kutu[1] <= KENAR_PX or
            kutu[2] >= W - KENAR_PX or kutu[3] >= H - KENAR_PX)


# ---------------- renk ----------------
def _maske(bgr, araliklar):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = None
    for alt, ust in araliklar:
        k = cv2.inRange(hsv, alt, ust)
        m = k if m is None else (m | k)
    return m


def _kirmizi_orani(frame, kutu):
    """Kutunun ic %60'indaki kirmizi piksel orani (algi.kirmizi_oneri esikleri)."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = kutu
    w, h = x2 - x1, y2 - y1
    ax1, ay1 = int(max(0, x1 + 0.2 * w)), int(max(0, y1 + 0.2 * h))
    ax2, ay2 = int(min(W, x2 - 0.2 * w)), int(min(H, y2 - 0.2 * h))
    if ax2 - ax1 < 2 or ay2 - ay1 < 2:
        ax1, ay1, ax2, ay2 = int(max(0, x1)), int(max(0, y1)), int(min(W, x2)), int(min(H, y2))
        if ax2 - ax1 < 1 or ay2 - ay1 < 1:
            return 0.0
    s, v = algi.KIRMIZI_ONERI_S, algi.KIRMIZI_ONERI_V
    m = _maske(frame[ay1:ay2, ax1:ax2], (((0, s, v), (12, 255, 255)), ((168, s, v), (180, 255, 255))))
    return float(m.mean()) / 255.0


def _lazer_bak(frame, kutu):
    """Lazer noktali balon: (kanit, nokta_maskesi, kirpinti) — bkz. LAZER ALTINDA.
    kanit: nokta HARIC balon dairesi kirmizi ve dis halka kirmizi degil."""
    x1, y1, x2, y2 = kutu
    s = max(x2 - x1, y2 - y1, 2.0)
    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    H, W = frame.shape[:2]
    ox1, oy1 = int(max(0, cx - s)), int(max(0, cy - s))
    ox2, oy2 = int(min(W, cx + s + 1)), int(min(H, cy + s + 1))
    if ox2 - ox1 < 4 or oy2 - oy1 < 4:
        return False, None, None
    c = frame[oy1:oy2, ox1:ox2]
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    yy, xx = np.mgrid[0:c.shape[0], 0:c.shape[1]]
    d = np.hypot(xx - (cx - ox1), yy - (cy - oy1))
    ic = d <= 0.5 * s
    nokta = ((hsv[..., 2] >= LAZER_V) & (hsv[..., 1] <= LAZER_S) & ic).astype(np.uint8)
    genis = nokta
    if nokta.any():                      # hale: noktanin kendi yaricapi kadar genisletilir
        r = int(math.sqrt(float(nokta.sum()) / math.pi))
        genis = cv2.dilate(nokta, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2))
    bak = ic & (genis == 0)
    if bak.sum() < HALKA_KARAR * ic.sum():
        return False, nokta, (ox1, oy1, ox2, oy2)
    sv, vv = algi.KIRMIZI_ONERI_S, algi.KIRMIZI_ONERI_V
    kir = _maske(c, (((0, sv, vv), (12, 255, 255)), ((168, sv, vv), (180, 255, 255)))) > 0
    dis = (d >= 0.7 * s) & (d <= 1.0 * s)
    oran_ic = float((kir & bak).sum()) / float(bak.sum())
    oran_dis = float((kir & dis).sum()) / float(max(1, dis.sum()))
    return oran_ic >= HALKA_IC and oran_dis <= HALKA_DIS, nokta, (ox1, oy1, ox2, oy2)


def _lazer_temizle(frame, kutu):
    """Balon hala yerindeyse (halka kaniti) lazer noktasini cevreden doldurur; yeni kare
    doner. Kanit yoksa kare AYNEN doner — patlamis balonun yerinde balon uydurulmaz."""
    kanit, nokta, kirp = _lazer_bak(frame, kutu)
    if not kanit or nokta is None or not nokta.any():
        return frame
    ox1, oy1, ox2, oy2 = kirp
    m = cv2.dilate(nokta * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    g = frame.copy()
    g[oy1:oy2, ox1:ox2] = cv2.inpaint(np.ascontiguousarray(frame[oy1:oy2, ox1:ox2]), m, 3,
                                      cv2.INPAINT_TELEA)
    return g


def _govde_rengi(frame, kutu):
    """Balonun HEMEN USTUNDEKI govdenin tarafi: "Dost" | "Düşman" | None (govde yok /
    okunamadi). Mavi leke varsa kirmizi hic sayilmaz (dost oncelikli)."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = kutu
    s = _boy(kutu)
    cx = (x1 + x2) * 0.5
    ox1, ox2 = int(max(0, cx - GOVDE_YATAY * s)), int(min(W, cx + GOVDE_YATAY * s))
    oy1, oy2 = int(max(0, y1 - GOVDE_YUKARI * s)), int(min(H, y1 + 0.15 * s))
    if ox2 - ox1 < 3 or oy2 - oy1 < 3:
        return None
    bolge = frame[oy1:oy2, ox1:ox2]
    bw = ox2 - ox1
    # balonun kendi pikselleri (ust kismi bolgeye giriyor) sayilmasin
    pay = 0.1 * s
    bx1, by1 = int(max(0, x1 - pay - ox1)), int(max(0, y1 - pay - oy1))
    bx2, by2 = int(max(0, x2 + pay - ox1)), int(max(0, y2 + pay - oy1))
    sutun_x1, sutun_x2 = cx - GOVDE_SUTUN * s, cx + GOVDE_SUTUN * s
    en_ust = y1 - GOVDE_BOSLUK * s          # lekenin alt kenari bundan asagida olmali

    def asili_alan(araliklar):
        m = _maske(bolge, araliklar)
        m[by1:by2, bx1:bx2] = 0
        n, _, ist, _ = cv2.connectedComponentsWithStats(m, 8)
        toplam = 0
        for x, y, w, h, alan in ist[1:]:
            if alan < 3 or x == 0 or y == 0 or x + w >= bw:
                continue                     # gurultu / bolgeden tasan arka plan yuzeyi
            gx1, gx2, galt = ox1 + x, ox1 + x + w, oy1 + y + h
            if gx2 >= sutun_x1 and gx1 <= sutun_x2 and galt >= en_ust:
                toplam += alan
        return toplam

    if asili_alan(GOVDE_CYAN_HSV) >= max(GOVDE_CYAN_ALAN * s * s, 6):
        return "Dost"
    if asili_alan(GOVDE_KIRMIZI_HSV) >= max(GOVDE_KIRMIZI_ALAN * s * s, 10):
        return "Düşman"
    return None


# ---------------- kimlik karti ----------------
def _yeni_kart():
    return {"dusman": 0, "dost": 0, "tip": {}, "arac_id": None, "t_arac": None, "govde": 0}


def kart_taraf(kart):
    """"Düşman" | "Dost" | "Belirsiz". Dost once bakilir: yanlis "Düşman" -10 puandir."""
    dusman, dost = kart["dusman"], kart["dost"]
    if dost >= DOST_ONAY and dost * 3 >= dusman:
        return "Dost"
    if dusman >= KART_ONAY and dost * DOST_ORAN <= dusman:
        return "Düşman"
    return "Belirsiz"


def kart_tip(kart):
    if not kart["tip"]:
        return None
    tip, oy = max(kart["tip"].items(), key=lambda kv: kv[1])
    return tip if oy >= TIP_ONAY else None


def _sahip_arac(kutu, araclar):
    """Balonun asili oldugu arac: balon aracin yatay hizasinda ve ALTINDA (en fazla
    ALT_KAT arac boyu). Birden fazla uyarsa asilma noktasina (alt orta) en yakini."""
    bcx, bcy = _merkez(kutu)
    bw = kutu[2] - kutu[0]
    en_iyi, en_iyi_d = None, None
    for d in araclar:
        x1, y1, x2, y2 = d["box"]
        w, h = max(1, x2 - x1), max(1, y2 - y1)
        if abs(bcx - (x1 + x2) * 0.5) > 0.6 * w + 0.5 * bw:
            continue
        if not (y1 + y2) * 0.5 <= bcy <= y2 + ALT_KAT * h:
            continue
        dd = math.hypot(bcx - (x1 + x2) * 0.5, bcy - y2)
        if en_iyi_d is None or dd < en_iyi_d:
            en_iyi, en_iyi_d = d, dd
    return en_iyi


def _kart_oyla(iz, arac, frame, simdi):
    """Bu karede birlikte gorulen aracin kanitini balonun kartina yazar. Renk BU KAREDEN
    okunur (arac takibinin taraf hafizasi degil): oy, o anki kanittir."""
    kart = iz["kart"]
    kirmizi, cyan = renk_oranlari(frame, arac["box"])
    if kirmizi >= algi.RENK_ESIK and kirmizi - cyan >= algi.RENK_FARK_ESIK:
        kart["dusman"] += 1
    elif cyan >= algi.RENK_ESIK and cyan - kirmizi >= algi.RENK_FARK_ESIK:
        kart["dost"] += 1
    if arac.get("cls") in algi.HEDEF_SINIFLARI:
        kart["tip"][arac["cls"]] = kart["tip"].get(arac["cls"], 0) + 1
    _kart_tavani(kart)
    kart["arac_id"], kart["t_arac"] = arac.get("id"), simdi


def _govde_gozlemi(iz, taraf):
    """Bu karenin govde rengi gozlemi. Dost hemen oy olur; kirmizi ancak son karelerde
    surekliyse (govde_oran >= GOVDE_ORAN_ESIK) — tek tuk kirmizi zamanla birikmesin."""
    iz["govde_oran"] += GOVDE_ORAN_YUMUSATMA * ((taraf == "Düşman") - iz["govde_oran"])
    if taraf == "Dost" or (taraf == "Düşman" and iz["govde_oran"] >= GOVDE_ORAN_ESIK):
        _govde_oyla(iz, taraf)


def _govde_oyla(iz, taraf):
    """Arac modeli okumadan, balonun ustundeki govdenin RENGIYLE taraf oyu (tip yok)."""
    kart = iz["kart"]
    kart["dost" if taraf == "Dost" else "dusman"] += 1
    kart["govde"] += 1
    _kart_tavani(kart)


def _kart_tavani(kart):
    if kart["dusman"] + kart["dost"] > KART_TAVAN:
        kart["dusman"] //= 2
        kart["dost"] //= 2
        for k in kart["tip"]:
            kart["tip"][k] = max(1, kart["tip"][k] // 2)


# ---------------- tespit ----------------
def _pencereler(frame, araclar, kilitli_iz, simdi):
    """Buyutulerek taranacak kare pencereler. Kilitliyken yalniz kilitli (kucuk) balon;
    kilit yokken kucuk izler, izi olmayan araclarin alti ve seyrek kirmizi lekeler."""
    H, W = frame.shape[:2]
    pen = []

    def ekle(cx, cy, s, en_cok=PENCERE_EN_COK):
        s = int(min(max(s, PENCERE_EN_AZ), en_cok, W, H))
        x1 = int(min(max(0, cx - s / 2), W - s))
        y1 = int(min(max(0, cy - s / 2), H - s))
        pen.append((x1, y1, x1 + s, y1 + s))

    if kilitli_iz is not None:
        if _boy(kilitli_iz["box"]) < KUCUK_PX:
            cx, cy = _tahmin_merkez(kilitli_iz, simdi)
            ekle(cx, cy, PENCERE_KAT * _boy(kilitli_iz["box"]))
        # A2 suru: kilitliyken diger UZAK (kucuk) balonlarin izi de kopmasin — imhadan sonra
        # siradaki hedef sifirdan aranmasin. Kare basina EN COK bir ek pencere, sirayla.
        digerleri = sorted((z for z in _izler.values() if z is not kilitli_iz and z["dogrulandi"]
                            and _boy(z["box"]) < KUCUK_PX), key=lambda z: z["no"])
        if digerleri:
            z = digerleri[_durum["sayac"] % len(digerleri)]
            cx, cy = _tahmin_merkez(z, simdi)
            ekle(cx, cy, PENCERE_KAT * _boy(z["box"]))
        return pen
    mx, my = W * 0.5, H * 0.5
    kucukler = sorted((z for z in _izler.values() if _boy(z["box"]) < KUCUK_PX),
                      key=lambda z: math.hypot(*(a - b for a, b in zip(_merkez(z["box"]), (mx, my)))))
    for z in kucukler[:2]:
        cx, cy = _tahmin_merkez(z, simdi)
        ekle(cx, cy, PENCERE_KAT * _boy(z["box"]))
    for d in sorted(araclar, key=lambda d: -d.get("conf", 0)):
        if len(pen) >= PENCERE_AZAMI:
            break
        x1, y1, x2, y2 = algi._balon_arama_penceresi(d["box"], frame.shape)
        if any(x1 <= _merkez(z["box"])[0] <= x2 and y1 <= _merkez(z["box"])[1] <= y2
               for z in _izler.values()):
            continue                     # bu aracin balonu zaten izleniyor
        ekle((x1 + x2) * 0.5, (y1 + y2) * 0.5, max(x2 - x1, y2 - y1))
    if _durum["sayac"] % KIRMIZI_PERIYOT == 0:
        for k in algi.kirmizi_oneri(frame, PENCERE_AZAMI):
            if len(pen) >= PENCERE_AZAMI:
                break
            x1, y1, x2, y2 = k
            ekle((x1 + x2) * 0.5, (y1 + y2) * 0.5, ONERI_KAT * max(x2 - x1, y2 - y1), ONERI_EN_COK)
    return pen


def _tespit_et(model, frame, pencereler, esik, araclar):
    """Tam kare + pencereler TEK toplu cikarim. Doner: [{"box", "conf", "kaynak"}]."""
    girdiler = [frame] + [frame[y1:y2, x1:x2] for x1, y1, x2, y2 in pencereler]
    ofset = [(0, 0, "tam")] + [(x1, y1, "pencere") for x1, y1, _, _ in pencereler]
    en_dusuk = min(esik, IZ_ESIK)
    sonuclar = model.predict(girdiler, conf=en_dusuk, imgsz=640, verbose=False)
    ham = []
    for (ox, oy, kaynak), r in zip(ofset, sonuclar):
        for b in (r.boxes if r.boxes is not None else []):
            if not algi.balon_sinifi_mi(r.names[int(b.cls)]) or float(b.conf) < en_dusuk:
                continue
            bx1, by1, bx2, by2 = [float(v) for v in b.xyxy[0].tolist()]
            kutu = (bx1 + ox, by1 + oy, bx2 + ox, by2 + oy)
            w, h = kutu[2] - kutu[0], kutu[3] - kutu[1]
            if w < 2 or h < 2 or not EN_BOY[0] <= w / h <= EN_BOY[1]:
                continue
            if _govde_mi(kutu, araclar):
                continue
            if _kirmizi_orani(frame, kutu) < KIRMIZI_EN_AZ:
                continue
            ham.append({"box": kutu, "conf": float(b.conf), "kaynak": kaynak,
                        "zayif": float(b.conf) < esik})
    # Ayni balon hem tam karede hem pencerede bulunur: en guvenlisi kalir.
    ham.sort(key=lambda t: -t["conf"])
    kalan = []
    for t in ham:
        if all(algi._ortusme(t["box"], k["box"]) < 0.5 for k in kalan):
            kalan.append(t)
    return kalan


# ---------------- izler ----------------
def _yeni_iz(t, simdi):
    _durum["sira"] += 1
    iz = {"id": f"B{_durum['sira']}", "no": _durum["sira"], "box": t["box"],
          "conf": t["conf"], "kaynak": t["kaynak"], "t_ilk": simdi, "t_son": simdi,
          "t_model": simdi, "guven": t["conf"], "govde_oran": 0.0, "dogrulandi": False,
          "oran": 1.0,
          "model_box": t["box"],
          "isabet": 1, "goruldu": True, "vx": 0.0, "vy": 0.0, "kart": _yeni_kart(),
          "ates_t": None, "ates_sure": ATES_SURE_S, "ates_bitis": None,
          "ates_sayisi": 0, "yasak_bitis": 0.0,
          "gen": t["box"][2] - t["box"][0]}
    for y in _yasak_bolgeler:       # yasakli balon yeni kimlikle dogarsa yasak surer
        if algi._ayni_nesne_olabilir(t["box"], y["box"]):
            iz["yasak_bitis"] = max(iz["yasak_bitis"], y["bitis"])
    _kart_devral(iz, simdi)
    _izler[iz["id"]] = iz


def _kart_devral(iz, simdi):
    """Yeni iz, kisa sure once kaybolan kartli bir balonun kestirilen yerindeyse kartini
    alir. O yerin cevresinde tek aday yoksa (baska gorunen balon da varsa) TASINMAZ."""
    cx, cy = _merkez(iz["box"])
    boy = _boy(iz["box"])
    adaylar = []
    for k in _kayip_kartlar:
        dt = min(max(0.0, simdi - k["t"]), TAHMIN_AZAMI_S)
        kx, ky = _merkez(k["box"])
        kx, ky = kx + k["vx"] * dt, ky + k["vy"] * dt
        yaricap = max(KART_TASIMA_KAT * _boy(k["box"]), ESLESME_EN_AZ_PX)
        if math.hypot(cx - kx, cy - ky) <= yaricap and 0.67 <= boy / _boy(k["box"]) <= 1.5:
            adaylar.append((k, kx, ky, yaricap))
    if len(adaylar) != 1:
        return
    k, kx, ky, yaricap = adaylar[0]
    if any(z["goruldu"] and math.hypot(_merkez(z["box"])[0] - kx, _merkez(z["box"])[1] - ky)
           <= yaricap for z in _izler.values()):
        return                           # orada baska bir balon da var: kart kimin, belirsiz
    kart = k["kart"]
    iz["kart"] = {"dusman": min(kart["dusman"], KART_ONAY), "dost": kart["dost"],
                  "tip": dict(kart["tip"]), "arac_id": kart["arac_id"], "t_arac": kart["t_arac"],
                  "govde": kart.get("govde", 0)}
    _kayip_kartlar.remove(k)


def _iz_guncelle(iz, t, simdi):
    dt = simdi - iz["t_son"]
    if 1e-3 < dt <= TAHMIN_AZAMI_S:
        (ox, oy), (nx, ny) = _merkez(iz["box"]), _merkez(t["box"])
        iz["vx"] += HIZ_YUMUSATMA * ((nx - ox) / dt - iz["vx"])
        iz["vy"] += HIZ_YUMUSATMA * ((ny - oy) / dt - iz["vy"])
    elif dt > TAHMIN_AZAMI_S:
        iz["vx"] = iz["vy"] = 0.0
    iz.update(box=t["box"], kaynak=t["kaynak"], t_son=simdi, goruldu=True)
    if t["kaynak"] in ("renk", "lazer"):
        return                  # renk/lazer: yer tasir; guven, isabet, boy MODELDEN gelir
    iz["gen"] += BOY_YUMUSATMA * ((t["box"][2] - t["box"][0]) - iz["gen"])
    iz["guven"] += GUVEN_YUMUSATMA * (t["conf"] - iz["guven"])
    iz.update(conf=t["conf"], t_model=simdi, isabet=iz["isabet"] + 1, model_box=t["box"])
    # Bir kez kilit olcutunu gecen iz "dogrulanmis"tir: uzaklasip guveni dusse de
    # (videoda 16 px'te %31-41) renkle devam edebilir.
    if iz["isabet"] >= ONAY_KARE and iz["guven"] >= KILIT_GUVEN:
        iz["dogrulandi"] = True


def _renkle_devam(frame, simdi):
    """Bu karede modelin kacirdigi DOGRULANMIS izleri kestirilen yerdeki kirmizi yuvarlak
    lekeyle tasir. Yalniz tek uygun leke varsa (iki balon yan yanaysa hangisi belirsiz:
    A3'te dusman kartinin dost balona kaymasi -10). Model RENK_AZAMI_S gormezse biter."""
    H, W = frame.shape[:2]
    alinan = [z["box"] for z in _izler.values() if z["goruldu"]]
    for iz in _izler.values():
        if (iz["goruldu"] or not iz["dogrulandi"]
                or simdi - iz["t_model"] > RENK_AZAMI_S):
            continue
        if iz["ates_t"] is not None and simdi - iz["ates_t"] <= IMHA_S:
            continue                     # ates altinda: patlarsa KAYBOLSUN (imha); govde
            #                              parcasi / balon artigi izlenip lazer bosa yanmasin
        s = _boy(iz["box"])
        tx, ty = _tahmin_merkez(iz, simdi)
        r = 1.5 * s + 4
        ox1, oy1 = int(max(0, tx - r)), int(max(0, ty - r))
        ox2, oy2 = int(min(W, tx + r)), int(min(H, ty + r))
        if ox2 - ox1 < 4 or oy2 - oy1 < 4:
            continue
        adaylar = []
        for x, y, w, h, alan in algi._kirmizi_bilesenler(frame[oy1:oy2, ox1:ox2]):
            kutu = (ox1 + x, oy1 + y, ox1 + x + w, oy1 + y + h)
            # boy MODELIN son kutusuyla kiyaslanir: renk kutusuyla kiyaslansaydi leke her
            # karede %40 buyuyup govde+balon lekesine kayabilirdi (videoda 23 -> 50 px)
            if not RENK_BOY[0] <= max(w, h) / _boy(iz["model_box"]) <= RENK_BOY[1]:
                continue
            if not EN_BOY[0] <= w / max(1, h) <= EN_BOY[1] or alan < RENK_DOLGU * w * h:
                continue
            if any(algi._ortusme(kutu, a) > 0.3 for a in alinan):
                continue                 # baska bir izin bu karedeki kutusu
            cx, cy = _merkez(kutu)
            if math.hypot(cx - tx, cy - ty) <= max(RENK_UZAKLIK_KAT * s, 6.0):
                adaylar.append(kutu)
        if len(adaylar) == 1:
            _iz_guncelle(iz, {"box": adaylar[0], "conf": iz["guven"], "kaynak": "renk"}, simdi)
            alinan.append(adaylar[0])


def _lazer_bitisi(iz):
    """Lazerin bu balonu gosteren SON karesinin ani (ates bittikten sonra da kareler
    LAZER_GECIKME_S boyunca noktayi gosterir) ya da None (ates edilmedi)."""
    t = iz["ates_t"]
    if t is None:
        return None
    bitis = iz["ates_bitis"] if iz["ates_bitis"] is not None else t + iz["ates_sure"]
    return bitis + LAZER_GECIKME_S


def _lazer_altinda(iz, simdi):
    """Bu karede lazer (gercek, otonom ates) bu balona vuruyor olabilir mi?"""
    b = _lazer_bitisi(iz)
    return b is not None and iz["ates_t"] <= simdi <= b


def _namluya_bagli(iz, simdi):
    """ATES TAAHHUDU (24.09): lazer altinda ve sonrasindaki BAKISTA (KAYIP_S: patladi mi?)
    ates edilen balonun izi GORUNTUYE baglidir — namlu balonun uzerinde kalir (duranda
    bekler, hareketlide kestirilen yolda kayar: hedef_kestirici.EksenTakip.korluk). Kamera
    kaymasi ve hizla ileri tasima UYGULANMAZ: uygulansaydi balonu izleyen namlunun kaymasi
    hayaleti geri iterdi; lazer sonrasi geri gelen balon eslesmez, "patladi" sayilip yeni
    kimlikle bastan dogrulanirdi (A3'te kartsiz: yeniden 3 dusman oyu)."""
    b = _lazer_bitisi(iz)
    return b is not None and iz["ates_t"] <= simdi <= b + KAYIP_S


def _lazerle_devam(frame, simdi):
    """Lazer altindaki KILITLI balonu model goremediyse, halka kanitiyla yerinde tutar
    (kaynak "lazer"). Kanit yoksa iz hayalet olur: ates kesilir, kaybolursa imha."""
    iz = _izler.get(_durum["kilit"])
    if iz is None or iz["goruldu"] or not iz["dogrulandi"] or not _lazer_altinda(iz, simdi):
        return
    if _lazer_bak(frame, iz["box"])[0]:
        _iz_guncelle(iz, {"box": iz["box"], "conf": iz["guven"], "kaynak": "lazer"}, simdi)


def _eslestir(tespitler, simdi):
    """Tespitleri izlere en yakin-once (boyla olcekli) esler; kalanlar yeni iz olur."""
    for iz in _izler.values():
        iz["goruldu"] = False
    ciftler = []
    for iid, iz in _izler.items():
        tx, ty = _tahmin_merkez(iz, simdi)
        boy = _boy(iz["box"])
        for j, t in enumerate(tespitler):
            if t["zayif"] and not iz["dogrulandi"]:
                continue                 # dusuk guven yalniz dogrulanmis izi surdurur
            cx, cy = _merkez(t["box"])
            d = math.hypot(cx - tx, cy - ty)
            if d <= max(ESLESME_KAT * boy, ESLESME_EN_AZ_PX) and 0.5 <= _boy(t["box"]) / boy <= 2.0:
                ciftler.append((d / boy, iid, j))
    ciftler.sort()
    iz_kullanildi, t_kullanildi = set(), set()
    for _, iid, j in ciftler:
        if iid in iz_kullanildi or j in t_kullanildi:
            continue
        iz_kullanildi.add(iid)
        t_kullanildi.add(j)
        _iz_guncelle(_izler[iid], tespitler[j], simdi)
    for j, t in enumerate(tespitler):
        if j not in t_kullanildi and not t["zayif"]:
            _yeni_iz(t, simdi)


def _kayip_siniri(iz):
    return KAYIP_S if iz["isabet"] >= OTURMUS_KARE or iz["ates_t"] is not None else KAYIP_GENC_S


def _kayip_ani(iz):
    """Kaybin sayildigi an. ATES TAAHHUDU: lazer noktasi balonu modelden gizler — ates
    suresince (+ LAZER_GECIKME_S) gorulmemek KAYIP DEGIL. Sayac nokta kaybolunca baslar:
    balon KAYIP_S icinde geri gelmezse patlamistir (imha); gelirse kilit aynen surer."""
    b = _lazer_bitisi(iz)
    return iz["t_son"] if b is None else max(iz["t_son"], b)


def _eskileri_sil(simdi):
    for iid in [i for i, z in _izler.items() if simdi - _kayip_ani(z) > _kayip_siniri(z)]:
        iz = _izler.pop(iid)
        if iz["yasak_bitis"] > simdi:
            _yasak_bolgeler.append({"box": iz["box"], "bitis": iz["yasak_bitis"]})
        if iz["ates_t"] is not None and -0.3 <= iz["t_son"] - iz["ates_t"] <= IMHA_S:
            _imha_isle(iz, simdi)          # patlayan balonun karti TASINMAZ
        elif iz["kart"]["dusman"] or iz["kart"]["dost"] or iz["kart"]["tip"]:
            _kayip_kartlar.append({"box": iz["box"], "vx": iz["vx"], "vy": iz["vy"],
                                   "t": iz["t_son"], "kart": iz["kart"]})
        if _durum["kilit"] == iid:
            kilidi_birak()
    _yasak_bolgeler[:] = [y for y in _yasak_bolgeler if y["bitis"] > simdi]
    _kayip_kartlar[:] = [k for k in _kayip_kartlar if simdi - k["t"] <= KART_HAFIZA_S]


def _imha_isle(iz, simdi):
    """Ates edilen balon kayboldu = imha. Ustundeki "balon" izleri (kirmizi govde
    balon sanilmis olabilir) de yasaklanir: balonsuz arac bir daha hedef olmasin."""
    _durum["imha"] += 1
    _durum["son_imha_t"] = simdi
    _durum["son_imha_id"] = iz["id"]
    for z in _izler.values():
        if _ustunde(z["box"], iz["box"]):
            z["yasak_bitis"] = max(z["yasak_bitis"], simdi + YASAK_S)


# ---------------- kilit ----------------
def _izinli(iz, asama, simdi):
    """Kart / yasak / operatorun tip secimi bu balona ates izni veriyor mu?"""
    if simdi < iz["yasak_bitis"]:
        return False
    tipler = algi.hedef_tipleri()
    tip = kart_tip(iz["kart"])
    if asama == 3:
        if kart_taraf(iz["kart"]) != "Düşman":
            return False
        if tipler is not None and tip not in tipler:
            return False
    elif tipler is not None and tip is not None and tip not in tipler:
        return False                     # A2: tip beklenmez; yalniz BILINEN yanlis tip elenir
    return True


def _uygun(iz, asama, simdi, kare_sekli):
    """YENI kilit alabilir mi: modelce dogrulanmis (ONAY_KARE, KILIT_GUVEN), son karelerde
    KARARLI gorulen (KILIT_ORAN), bu karede modelle gorulmus, yari gorunen kenar cismi
    degil ve kart/yasak izin veriyor."""
    return (iz["goruldu"] and iz["kaynak"] != "renk" and iz["isabet"] >= ONAY_KARE
            and iz["guven"] >= KILIT_GUVEN and iz["oran"] >= KILIT_ORAN
            and not _kenarda(iz["box"], kare_sekli) and _izinli(iz, asama, simdi))


def _dikey_komsu(iz, asama, simdi, kare_sekli):
    """Ayni asili hatta, kilidi iz'den DAHA COK hak eden balon izi (ya da None).
      ALTTAKI en az iz kadar guvenliyse: iz, balonun ustundeki kirmizi govde olabilir.
      USTTEKI belirgin daha guvenliyse: iz, parlak zemindeki YANSIMA olabilir (video
      24.09: yansima %32-48, balon %90 — eski "hep alttaki" kurali kilidi yansimaya verdi).
    Iki kosul birbirini dislar: A, B'yi alt diye secerse B, A'yi ust diye secemez."""
    alt, ust = [], []
    for z in _izler.values():
        if z is iz or not _uygun(z, asama, simdi, kare_sekli):
            continue
        if _ustunde(iz["box"], z["box"]) and z["guven"] >= iz["guven"] - 0.1:
            alt.append(z)
        elif _ustunde(z["box"], iz["box"]) and z["guven"] > iz["guven"] + 0.1:
            ust.append(z)
    if alt:
        return min(alt, key=lambda z: z["box"][1])       # en yakin alttaki
    return max(ust, key=lambda z: z["box"][1], default=None)


def _kilidi_guncelle(asama, kare_sekli, simdi):
    iz = _izler.get(_durum["kilit"])
    if iz is not None and not _izinli(iz, asama, simdi):
        kilidi_birak()                   # A3 karti bozuldu / yasaklandi / tip secimi degisti
        iz = None
    adaylar = [z for z in _izler.values()
               if z is not iz and _uygun(z, asama, simdi, kare_sekli)
               and _dikey_komsu(z, asama, simdi, kare_sekli) is None]
    menzilli = asama == 3 and _menzil_etkin()
    if iz is not None:
        # Kilitli "balon" govde ya da yansima olabilir: ayni hatta daha iyi aday
        # kararli bicimde (GOVDE_DEVIR_KARE) gorunuyorsa kilit ona gecer.
        komsu = _dikey_komsu(iz, asama, simdi, kare_sekli) if iz["goruldu"] else None
        # A3: kilitli balon imha bandi DISINDA (ates engelli) ve bantta baska uygun dusman
        # varsa ona gecilir — yoksa sistem uzaktakine kilitli bekler, yakindakini kacirir.
        if komsu is None and menzilli and _menzil_engeli(iz):
            bantta = [z for z in adaylar if not _menzil_engeli(z)]
            komsu = _en_yakin(bantta, kare_sekli) if bantta else None
        _durum["ust_sayac"] = _durum["ust_sayac"] + 1 if komsu is not None else 0
        if komsu is not None and _durum["ust_sayac"] >= GOVDE_DEVIR_KARE:
            _durum["kilit"], _durum["ust_sayac"] = komsu["id"], 0
        return
    if not adaylar:
        return
    if menzilli:                          # A3: once imha bandindakiler
        bantta = [z for z in adaylar if not _menzil_engeli(z)]
        adaylar = bantta or adaylar
    _durum["kilit"], _durum["ust_sayac"] = _en_yakin(adaylar, kare_sekli)["id"], 0


def _en_yakin(adaylar, kare_sekli):
    """Lazer referansina (kare merkezi + boresight ofseti) en yakin iz: en kisa donus."""
    H, W = kare_sekli[:2]
    rx = W * (0.5 + float(algi.AYAR.get("lazer_ofset_x", 0.0)))
    ry = H * (0.5 + float(algi.AYAR.get("lazer_ofset_y", 0.0)))
    return min(adaylar, key=lambda z: math.hypot(_merkez(z["box"])[0] - rx,
                                                 _merkez(z["box"])[1] - ry))


def hedef_sec(bid, simdi=None):
    """Arayuzdeki listeden ELLE balon kilidi. Elle secim yasagi kaldirir, ama A3'te
    karti "Düşman" olmayan balonu yine SECMEZ (dost vurmak -10). Doner: basarili mi."""
    simdi = time.time() if simdi is None else simdi
    if bid is None:
        kilidi_birak()
        return True
    iz = _izler.get(bid)
    if iz is None:
        return False
    iz["yasak_bitis"] = 0.0
    iz["ates_sayisi"] = 0
    if _durum["asama"] in (2, 3) and not _izinli(iz, _durum["asama"], simdi):
        return False
    _durum["kilit"], _durum["ust_sayac"] = bid, 0
    return True


def araca_gore_sec(arac_id, simdi=None):
    """Listeden bir ARAC secildiyse onun (kartla bagli) balonunu kilitle."""
    # Arayuz thread'inden cagrilir; algi thread'i ayni anda iz silebilir -> kopya uzerinde gez.
    bagli = [z for z in list(_izler.values()) if z["kart"]["arac_id"] == arac_id]
    if not bagli:
        return False
    return hedef_sec(max(bagli, key=lambda z: z["kart"]["t_arac"])["id"], simdi)


def ates_basladi(lazer_gercek, simdi=None, sure=None):
    """Arayuz otonom atesi actiginda (`sure`: ates turu, sn). Sahte lazerde kayit tutulmaz:
    hicbir sey patlamaz, kaybolan balon "imha" sayilmamali (algi.hedef_vuruldu ile ayni
    kural) ve lazer noktasi yoktur (LAZER ALTINDA onlemleri calismaz)."""
    iz = _izler.get(_durum["kilit"])
    if iz is not None and lazer_gercek:
        iz["ates_t"] = time.time() if simdi is None else simdi
        iz["ates_sure"] = ATES_SURE_S if sure is None else float(sure)
        iz["ates_bitis"] = None


def ates_bitti(simdi=None):
    """Arayuz atesi kesti (sure doldu, engel, kayip, E-Stop — `_ates_kes`). Lazer altinda
    onlemleri LAZER_GECIKME_S sonra biter."""
    simdi = time.time() if simdi is None else simdi
    for iz in _izler.values():
        if iz["ates_t"] is not None and iz["ates_bitis"] is None:
            iz["ates_bitis"] = simdi


def ates_tamamlandi(lazer_gercek, simdi=None):
    """Ates turu bitti, balon hala yerinde. AZAMI_ATES turdan sonra (gercek lazerle)
    balon YASAK_S boyunca birakilir, siradaki balona gecilir. Doner: yasaklanan id."""
    iz = _izler.get(_durum["kilit"])
    if iz is None or not lazer_gercek:
        return None
    simdi = time.time() if simdi is None else simdi
    iz["ates_sayisi"] += 1
    if iz["ates_sayisi"] < AZAMI_ATES:
        return None
    iz["yasak_bitis"] = simdi + YASAK_S
    kilidi_birak()
    return iz["id"]


# ---------------- cikti ----------------
def _dost_engeli(iz, araclar, frame):
    """A3: lazerin yolunda dost var mi? Dost arac kutusu balonun merkezini ortuyorsa, karti
    "Dost" olan bir balon ust uste biniyorsa ya da balonun ORTASINDA mavi (dost govdesi)
    gorunuyorsa ates engellenir. Sonuncusu arac modeli dostu hic okumasa da calisir."""
    cx, cy = _merkez(iz["box"])
    if iz["goruldu"] and _merkez_mavi_orani(frame, iz["box"]) >= ONDE_MAVI_ORAN:
        return "Dost gövde balonun önünde"
    for d in araclar:
        if d.get("renk_tip") == "Dost" or d.get("tip") == "Dost":
            x1, y1, x2, y2 = d["box"]
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return "Dost araç balonun önünde"
    for z in _izler.values():
        if z is not iz and z["goruldu"] and kart_taraf(z["kart"]) == "Dost" \
                and algi._ortusme(z["box"], iz["box"]) > 0.1:
            return "Dost balon çizgide"
    return None


def _merkez_mavi_orani(frame, kutu):
    """Balon kutusunun ic %40'inda (lazerin vuracagi yer) dost mavisi orani."""
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = kutu
    w, h = x2 - x1, y2 - y1
    ax1, ay1 = int(max(0, x1 + 0.3 * w)), int(max(0, y1 + 0.3 * h))
    ax2, ay2 = int(min(W, x2 - 0.3 * w)), int(min(H, y2 - 0.3 * h))
    if ax2 - ax1 < 1 or ay2 - ay1 < 1:
        return 0.0
    return float(_maske(frame[ay1:ay2, ax1:ax2], GOVDE_CYAN_HSV).mean()) / 255.0


def mesafe_m(iz):
    """Balonun kestirilen uzakligi (m) ya da None (cap olculmedi). Balon kureseldir:
    genisligin acisi mesafeyle ters orantili. ppd kare genisligine olceklenir."""
    cap = float(algi.AYAR.get("balon_cap_cm", 0) or 0)
    if cap <= 0 or iz.get("gen", 0) <= 0:
        return None
    ppd = float(algi.AYAR.get("takip_ppd_pan", 18.7)) * _durum["kare_w"] / 1280.0
    aci = math.radians(iz["gen"] / ppd)
    return (cap / 100.0) / (2.0 * math.tan(aci / 2.0))


def _menzil_etkin():
    return float(algi.AYAR.get("balon_cap_cm", 0) or 0) > 0 and int(algi.AYAR.get("menzil_kontrol", 1))


def _menzil_engeli(iz):
    """A3: balon tipinin imha bandinda degilse sebep metni (sartname: bant disi imha puan
    almaz). Tip bilinmiyorsa ORTAK_MENZIL. Cap girilmediyse ya da ayar kapaliysa None."""
    d = mesafe_m(iz)
    if d is None or not int(algi.AYAR.get("menzil_kontrol", 1)):
        return None
    tip = kart_tip(iz["kart"])
    alt, ust = MENZIL.get(tip, ORTAK_MENZIL)
    if (alt + MENZIL_PAY if alt > 0 else 0.0) <= d <= ust - MENZIL_PAY:
        return None
    ad = algi.goster_ad(tip, tip) if tip else "tip bilinmiyor"
    return f"Menzil dışı {d:.1f} m ({ad}: {alt:.0f}–{ust:.0f} m)"


def _det(iz, asama, simdi):
    taraf = kart_taraf(iz["kart"])
    tip = kart_tip(iz["kart"])
    mesafe = mesafe_m(iz)
    box = iz["box"]
    if not iz["goruldu"]:                # hayalet: son kutu hizla ileri tasinir
        cx, cy = _tahmin_merkez(iz, simdi)
        ox, oy = _merkez(box)
        box = (box[0] + cx - ox, box[1] + cy - oy, box[2] + cx - ox, box[3] + cy - oy)
    uzak = f" {mesafe:.1f}m" if mesafe is not None else ""
    d = {"cls": algi.BALON,
         "ham": "Balon" + (f" {algi.goster_ad_cv(tip, tip)}" if tip else "") + uzak,
         "ad": "Balon" + (f" · {algi.goster_ad(tip, tip)}" if tip else "") + uzak,
         "mesafe": None if mesafe is None else round(mesafe, 1),
         "tip": taraf if asama == 3 else "Hedef", "renk_tip": taraf,
         "conf": int(round(iz["conf"] * 100)),
         "box": tuple(int(round(v)) for v in box), "id": iz["id"], "balon": True,
         "kart_tip": tip, "kaynak": iz["kaynak"], "ates": iz["ates_sayisi"]}
    if not iz["goruldu"]:
        d["hayalet"] = True
    return d


def guncelle(model, frame, arac_dets, asama, estop=False, simdi=None):
    """Bir kare. Doner: (balon_dets, aktif_idx) — balon_dets arac tespitleriyle AYNI
    bicimde (`balon`=True), aktif_idx bu listede kilitli balon ya da -1.

    arac_dets: algi.analiz_et ciktisi (kimlik kaniti; hayalet kutular kullanilmaz).
    Kilit yalniz A2/A3'te ve E-Stop yokken kurulur; A1'de balonlar yalniz gosterilir."""
    simdi = time.time() if simdi is None else simdi
    _durum["asama"] = asama
    _durum["sayac"] += 1
    _durum["kare_w"] = frame.shape[1]
    _kaymayi_uygula(simdi)
    araclar = [d for d in arac_dets if not d.get("hayalet") and not d.get("balon")]
    kilitli_iz = _izler.get(_durum["kilit"])
    pencereler = _pencereler(frame, araclar, kilitli_iz, simdi)
    esik = float(algi.AYAR.get("balon_esik", algi.VARSAYILAN_AYAR["balon_esik"]))
    model_kare = frame
    if kilitli_iz is not None and _lazer_altinda(kilitli_iz, simdi):
        model_kare = _lazer_temizle(frame, kilitli_iz["box"])
    _eslestir(_tespit_et(model, model_kare, pencereler, esik, araclar), simdi)
    for iz in _izler.values():           # modelin bu karede gorup gormedigi (renk sayilmaz)
        iz["oran"] += ORAN_YUMUSATMA * (float(iz["goruldu"]) - iz["oran"])
    _renkle_devam(frame, simdi)
    _lazerle_devam(frame, simdi)
    for iz in _izler.values():
        if iz["goruldu"]:
            arac = _sahip_arac(iz["box"], araclar)
            if arac is not None:
                _kart_oyla(iz, arac, frame, simdi)
            elif iz["kaynak"] not in ("renk", "lazer"):
                _govde_gozlemi(iz, _govde_rengi(frame, iz["box"]))
    _eskileri_sil(simdi)
    if estop or asama not in (2, 3):
        kilidi_birak()
    else:
        _kilidi_guncelle(asama, frame.shape, simdi)

    dets, aktif = [], -1
    for iz in sorted(_izler.values(), key=lambda z: z["no"]):
        kilitli_mi = iz["id"] == _durum["kilit"]
        if not kilitli_mi and (not iz["goruldu"] or iz["isabet"] < GOSTER_KARE):
            continue
        d = _det(iz, asama, simdi)
        if kilitli_mi:
            aktif = len(dets)
            engel = (_dost_engeli(iz, araclar, frame) or _menzil_engeli(iz)) if asama == 3 else None
            # Lazer altinda (kaynak "lazer") model zaten goremez; kanit o karedeki halka.
            if (engel is None and iz["goruldu"] and iz["kaynak"] != "lazer"
                    and simdi - iz["t_model"] > RENK_ATES_S):
                engel = "Balon yalnız renkle izleniyor"   # nisan surer, ates model gorunce
            if engel:
                d["engel"] = engel
        dets.append(d)
    return dets, aktif


if __name__ == "__main__":
    import numpy as np
    import cv2

    # SAHTE BALON MODELI: verilen goruntude tam (0,0,255) renkli lekeleri "balon" bulur.
    # Kirpinti koordinatini kendiliginden verir -> pencere/ofset hesabi da sinanir.
    # tam_en_az: TAM KAREDE bundan kucuk balon gorulmez (uzak balon, gercek modeldeki gibi).
    BALON_RENK = (0, 0, 255)
    KIRMIZI_ARAC, CYAN_ARAC = (10, 10, 245), (224, 163, 0)

    class _Kutu:
        def __init__(self, box, conf=0.9):
            self.cls, self.conf = 0, conf
            self.xyxy = [type("X", (), {"tolist": lambda s, b=box: list(b)})()]

    class _Sonuc:
        def __init__(self, kutular):
            self.boxes, self.names = kutular, {0: "red-balloon"}

    class SahteModel:
        """renkler: {bgr: guven} — model bu renkteki her lekeyi o guvenle "balon" sanir
        (gercek model de gri cami, yansimayi boyle buldu). kor=True: hicbir sey gormez."""
        def __init__(self, tam_en_az=0, renkler=None):
            self.tam_en_az, self.girdi_sayilari = tam_en_az, []
            self.renkler = renkler or {BALON_RENK: 0.9}
            self.kor = False
            self.boyutlar = []

        def predict(self, girdiler, **kw):
            self.girdi_sayilari.append(len(girdiler))
            self.boyutlar.append([img.shape[:2] for img in girdiler])
            cikti = []
            for i, img in enumerate(girdiler):
                kutular = []
                for renk, guven in ([] if self.kor else self.renkler.items()):
                    m = cv2.inRange(img, renk, renk)
                    n, _, ist, _ = cv2.connectedComponentsWithStats(m, 8)
                    for x, y, w, h, alan in ist[1:]:
                        if i == 0 and max(w, h) < self.tam_en_az:
                            continue
                        kutular.append(_Kutu((x, y, x + w, y + h), guven))
                cikti.append(_Sonuc(kutular))
            return cikti

    def sahne(balonlar=(), araclar=()):
        """balonlar: [(cx, cy, cap)], araclar: [((x1,y1,x2,y2), renk)]."""
        k = np.full((720, 1280, 3), 128, np.uint8)
        for box, renk in araclar:
            cv2.rectangle(k, box[:2], box[2:], renk, -1)
        for cx, cy, cap in balonlar:
            r = cap // 2
            cv2.ellipse(k, (cx, cy), (r, r), 0, 0, 360, BALON_RENK, -1)
        return k

    def arac(box, cls="f16", tid=1, taraf="Düşman"):
        return {"cls": cls, "box": box, "id": tid, "conf": 90, "tip": taraf, "renk_tip": taraf}

    T = [1000.0]

    def kos(model, kare, dets=(), asama=2, estop=False, n=1):
        sonuc = None
        for _ in range(n):
            T[0] += 1 / 30
            sonuc = guncelle(model, kare, list(dets), asama, estop, simdi=T[0])
        return sonuc

    m = SahteModel()

    # 1. A2: balon ONAY_KARE karede gorulunce kilitlenir; nisan = balon kutusunun merkezi.
    sifirla()
    kare = sahne([(640, 400, 40)])
    b, a = kos(m, kare, n=ONAY_KARE - 1)
    assert a == -1, "balon onay karesinden once kilitlendi"
    b, a = kos(m, kare)
    assert a >= 0 and b[a]["balon"] and b[a]["tip"] == "Hedef", (b, a)
    nx, ny = algi.det_nisan_noktasi(b[a])
    assert abs(nx - 640) <= 1 and abs(ny - 400) <= 1, (nx, ny)     # govde ofseti YOK

    # 2. A1 (manuel) ve E-Stop: balon GOSTERILIR ama kilit YOK.
    b, a = kos(m, kare, asama=1)
    assert a == -1 and len(b) == 1, (b, a)
    b, a = kos(m, kare, estop=True)
    assert a == -1, "E-Stop'ta balon kilidi"

    # 3. A3: araci hic okunmayan balona ASLA kilit yok (kart bos = ates yok).
    sifirla()
    b, a = kos(m, kare, asama=3, n=10)
    assert a == -1 and b[0]["tip"] == "Belirsiz", b

    # 4. A3: kirmizi arac balonun ustunde KART_ONAY kare -> kart "Düşman" -> kilit.
    #    Arac sonra hic gorunmese de kart ve kilit SURER (arac okumak zor, balon kolay).
    sifirla()
    govde = (600, 300, 680, 360)
    kare_d = sahne([(640, 400, 40)], [(govde, KIRMIZI_ARAC)])
    b, a = kos(m, kare_d, [arac(govde)], asama=3, n=KART_ONAY)
    assert a >= 0 and b[a]["tip"] == "Düşman" and b[a]["kart_tip"] == "f16", (b, a)
    kilit_id = b[a]["id"]
    b, a = kos(m, kare, asama=3, n=20)                      # arac artik okunmuyor
    assert a >= 0 and b[a]["id"] == kilit_id and b[a]["tip"] == "Düşman", (b, a)

    # 5. A3 tip suzgeci: operator yalniz fuze ariyorsa F16'nin balonu kilitlenmez.
    algi.hedef_tipleri_ayarla(["fuze"])
    try:
        b, a = kos(m, kare, asama=3)
        assert a == -1, "operator fuze ariyor, F16 balonu kilitli kaldi"
        algi.hedef_tipleri_ayarla(["f16"])
        b, a = kos(m, kare, asama=3)
        assert a >= 0, "secilen tipin balonu kilitlenmedi"
    finally:
        algi.hedef_tipleri_ayarla(None)

    # 6. A3: DOST (cyan) arac -> kart "Dost" -> kilit yok, elle secim de REDDEDILIR.
    sifirla()
    kare_f = sahne([(640, 400, 40)], [(govde, CYAN_ARAC)])
    b, a = kos(m, kare_f, [arac(govde, taraf="Dost")], asama=3, n=10)
    assert a == -1 and b[0]["tip"] == "Dost", b
    assert hedef_sec(b[0]["id"], simdi=T[0]) is False, "dost balon elle kilitlendi (A3)"

    # 7. A3: kilitliyken dost kaniti gelirse (yanlis esleme) kilit BIRAKILIR.
    sifirla()
    b, a = kos(m, kare_d, [arac(govde)], asama=3, n=KART_ONAY)
    assert a >= 0
    b, a = kos(m, kare_f, [arac(govde, taraf="Dost")], asama=3, n=DOST_ONAY)
    assert a == -1, "dost kaniti geldi, kilit surdu"

    # 8. IMHA: gercek lazerle ates edilen balon kaybolursa imha sayilir, kilit
    #    siradaki balona gecer. Sahte lazerde kaybolma imha SAYILMAZ.
    #    ATES TAAHHUDU (24.09 saha): lazer noktasi balonu modelden gizler — ates suresince
    #    gorunmeyen balon SILINMEZ (iz + kilit yerinde: silinseydi kilit siradakine gecer,
    #    namlu lazer yanarken donerdi). Karar lazer sondukten (+ LAZER_GECIKME_S) sonra:
    #    KAYIP_S icinde geri gelmezse patlamistir.
    sifirla()
    iki = sahne([(640, 400, 40), (900, 400, 40)])
    b, a = kos(m, iki, n=ONAY_KARE)
    ilk = b[a]["id"]
    assert b[a]["box"][0] < 700, "kare merkezine en yakin balon secilmedi"
    ates_basladi(True, simdi=T[0], sure=2.0)
    tek = sahne([(900, 400, 40)])
    b, a = kos(m, tek, n=57)                                     # ~1.9 sn: ates suruyor
    assert a >= 0 and b[a]["id"] == ilk and b[a].get("hayalet"),         "lazer altinda gorunmeyen balon silindi / kilit gecti (ates kesilirdi)"
    assert son_imha()["sayi"] == 0, "ates bitmeden imha sayildi"
    ates_bitti(simdi=T[0])
    b, a = kos(m, tek, n=int((LAZER_GECIKME_S + KAYIP_S) * 30) - 3)
    assert son_imha()["sayi"] == 0 and b[a]["id"] == ilk,         "lazer sondu, balonun geri gelmesi beklenmeden imha sayildi"
    b, a = kos(m, tek, n=6)
    assert son_imha()["sayi"] == 1 and son_imha()["id"] == ilk, son_imha()
    assert a >= 0 and b[a]["id"] != ilk and b[a]["box"][0] > 800, "siradaki balona gecilmedi"
    ates_basladi(False, simdi=T[0])                            # sahte lazer
    b, a = kos(m, sahne([]), n=int(KAYIP_S * 30) + 2)
    assert son_imha()["sayi"] == 1, "sahte lazerde kaybolan balon imha sayildi"

    # 8b. PATLAMAYAN balon lazer sonrasi geri gelir: AYNI kimlik, kilit surer, imha YOK
    #     (yeniden ates edilir). Ates boyunca namlu balonu izler: bu izin kutusu kamera
    #     kaymasiyla kaymaz ve hizla ileri tasinmaz (namluya bagli); digerleri kayar.
    sifirla()
    b, a = kos(m, iki, n=ONAY_KARE)
    ilk = b[a]["id"]
    ates_basladi(True, simdi=T[0], sure=2.0)
    _izler[ilk]["vx"] = 60.0                    # tasinsaydi 0.3 sn'de 18 px kayardi
    b, a = kos(m, tek, n=30)
    kamera_kaymasi_bildir(25.0, 0.0)
    b, a = kos(m, tek)
    assert b[a]["id"] == ilk and b[a].get("hayalet") and abs(b[a]["box"][0] - 620) <= 1,         f"namluya bagli iz kaydi: {b[a]['box']}"
    b, a = kos(m, tek, n=29)
    ates_bitti(simdi=T[0])
    b, a = kos(m, iki, n=int(LAZER_GECIKME_S * 30) + 3)          # nokta sondu, balon yerinde
    assert a >= 0 and b[a]["id"] == ilk and not b[a].get("hayalet"),         "patlamayan balon geri gelince kimligi/kilidi degisti"
    b, a = kos(m, iki, n=int(KAYIP_S * 30) + 5)
    assert son_imha()["sayi"] == 0 and b[a]["id"] == ilk, "patlamayan balon imha sayildi"

    # 9. Patlamayan balon: AZAMI_ATES gercek ates turundan sonra birakilir, digerine
    #    gecilir; YASAK_S dolmadan geri secilmez. Sahte lazer turlari sayilmaz.
    sifirla()
    b, a = kos(m, iki, n=ONAY_KARE)
    ilk = b[a]["id"]
    for _ in range(AZAMI_ATES):
        assert ates_tamamlandi(False, simdi=T[0]) is None
    for _ in range(AZAMI_ATES - 1):
        assert ates_tamamlandi(True, simdi=T[0]) is None
    assert ates_tamamlandi(True, simdi=T[0]) == ilk
    b, a = kos(m, iki, n=5)
    assert a >= 0 and b[a]["id"] != ilk, "yasakli balona geri kilitlendi"

    # 10. Kirmizi maket GOVDESI balon sanilmaz: merkezi arac kutusunun ust kisminda.
    sifirla()
    govde_balon = sahne([(640, 320, 30)], [((600, 280, 680, 400), KIRMIZI_ARAC)])
    b, a = kos(m, govde_balon, [arac((600, 280, 680, 400))], n=5)
    assert b == [] and a == -1, b

    # 11. Arac okunamazken govde ve balon ust uste "balon" gorunurse ALTTAKI kilitlenir;
    #     yanlislikla usttekine kilitliyken alttaki belirirse kilit ona gecer.
    sifirla()
    ust_alt = sahne([(640, 300, 36), (640, 380, 36)])
    b, a = kos(m, ust_alt, n=ONAY_KARE + 1)
    assert a >= 0 and b[a]["box"][1] > 340, ("usttekine kilitlendi", b[a])
    sifirla()
    b, a = kos(m, sahne([(640, 300, 36)]), n=ONAY_KARE)
    assert a >= 0 and b[a]["box"][1] < 320
    b, a = kos(m, ust_alt, n=ONAY_KARE + GOVDE_DEVIR_KARE)
    assert a >= 0 and b[a]["box"][1] > 340, "alttaki balona gecilmedi"

    # 12. KAMERA KAYMASI: namlu donunce balon goruntude 150 px kayar; bildirilen kayma
    #     izi tasir, kimlik degismez. Bildirilmezse iz kopar (testin anlamli oldugu).
    for bildir, ayni_mi in ((True, True), (False, False)):
        sifirla()
        b, a = kos(m, sahne([(500, 400, 40)]), n=ONAY_KARE)
        eski = b[a]["id"]
        if bildir:
            kamera_kaymasi_bildir(150, 0)
        b, a = kos(m, sahne([(650, 400, 40)]))
        yeni = [d for d in b if not d.get("hayalet") and abs(d["box"][0] - 630) <= 2]
        assert (bool(yeni) and yeni[0]["id"] == eski) == ayni_mi, (bildir, b, a)

    # 13. KUCUK UZAK BALON: tam karede gorulmeyen 14 px balon aracin alt penceresinden
    #     bulunur, kilitlenir; arac kaybolunca KILIT PENCERESI tek basina tasir.
    sifirla()
    mk = SahteModel(tam_en_az=20)
    kucuk_govde = (620, 360, 660, 380)
    kare_k = sahne([(640, 400, 14)], [(kucuk_govde, KIRMIZI_ARAC)])
    b, a = kos(mk, kare_k, [arac(kucuk_govde)], n=ONAY_KARE)
    assert a >= 0, "kucuk balon arac penceresinden bulunamadi"
    b, a = kos(mk, sahne([(640, 400, 14)]), n=10)
    assert a >= 0 and not b[a].get("hayalet") and b[a]["kaynak"] == "pencere", b
    assert mk.girdi_sayilari[-1] == 2, f"kilitliyken {mk.girdi_sayilari[-1]} girdi (tam+pencere)"
    sifirla()
    b, a = kos(m, sahne([(640, 400, 80)]), n=ONAY_KARE + 1)
    assert a >= 0 and m.girdi_sayilari[-1] == 1, "buyuk kilitli balonda bosuna pencere tarandi"

    # 14. A3 DOST ONUNDE: dost arac kutusu kilitli balonun merkezini ortuyorsa engel.
    sifirla()
    b, a = kos(m, kare_d, [arac(govde)], asama=3, n=KART_ONAY)
    assert a >= 0 and "engel" not in b[a]
    b, a = kos(m, kare, [arac((560, 350, 720, 450), tid=9, taraf="Dost")], asama=3)
    assert a >= 0 and b[a].get("engel"), ("dost onundeyken engel yok", b[a])

    # 15. KISA KAYIP: kilitli balon bir kare gorulmezse hayalet; donunce ayni kimlik.
    sifirla()
    b, a = kos(m, kare, n=ONAY_KARE)
    eski = b[a]["id"]
    b, a = kos(m, sahne([]))
    assert a >= 0 and b[a]["id"] == eski and b[a]["hayalet"], b
    b, a = kos(m, kare)
    assert a >= 0 and b[a]["id"] == eski and not b[a].get("hayalet"), b

    # 16. ARACTAN SECIM: listeden arac tiklaninca kartla bagli balonu kilitlenir.
    sifirla()
    b, a = kos(m, kare_d, [arac(govde, tid=42)], asama=1, n=3)
    assert a == -1
    _durum["asama"] = 2
    assert araca_gore_sec(42, simdi=T[0]) and kilitli() == b[0]["id"]

    # 17. KART TASIMA: dusman karti kurulan balon KAYIP_S'den uzun kaybolup ayni yerde
    #     yeniden bulunursa karti gecer — arac hic okunmadan A3 kilidi geri gelir.
    bos = sahne([])
    kayip_kare = int((KAYIP_S + 0.3) * 30)

    def dusman_kaybolur(oy=KART_ONAY + 3):
        sifirla()
        b, a = kos(m, kare_d, [arac(govde)], asama=3, n=oy)
        assert a >= 0
        kos(m, bos, asama=3, n=kayip_kare)
        assert not _izler, "kurulum: iz silinmedi"

    dusman_kaybolur()
    b, a = kos(m, kare, asama=3, n=ONAY_KARE)
    assert a >= 0 and b[a]["tip"] == "Düşman" and b[a]["kart_tip"] == "f16", ("kart tasinmadi", b)
    # 17b. Uzakta beliren balon karti ALMAZ.
    dusman_kaybolur()
    b, a = kos(m, sahne([(900, 400, 40)]), asama=3, n=ONAY_KARE + 2)
    assert a == -1 and b[0]["tip"] == "Belirsiz", ("uzaktaki balona kart gecti", b)
    # 17c. Ayni yerde IKI balon belirirse kart kimse gecmez (hangisi oldugu belirsiz).
    dusman_kaybolur()
    b, a = kos(m, sahne([(640, 400, 40), (665, 400, 40)]), asama=3, n=ONAY_KARE + 2)
    assert a == -1 and all(d["tip"] == "Belirsiz" for d in b), ("belirsizken kart gecti", b)
    # 17d. PATLAYAN balonun karti gecmez: ayni yere gelen baska balon (or. arkadaki dost)
    #      dusman sanilmamali.
    sifirla()
    b, a = kos(m, kare_d, [arac(govde)], asama=3, n=KART_ONAY + 3)
    ates_basladi(True, simdi=T[0])
    ates_bitti(simdi=T[0])        # kisa atis: karar nokta sonunce (KART_HAFIZA_S dolmadan)
    kos(m, bos, asama=3, n=kayip_kare + int(LAZER_GECIKME_S * 30) + 2)
    assert son_imha()["sayi"] == 1
    b, a = kos(m, kare, asama=3, n=ONAY_KARE + 2)
    assert a == -1 and b[0]["tip"] == "Belirsiz", ("patlayan balonun karti gecti", b)
    # 17e. Tasinan dusman karti dost kanitiyla HEMEN doner (oy KART_ONAY ile sinirli):
    #      15 dusman oyu aynen tasinsaydi 2 dost oyu karti cevirmezdi.
    dusman_kaybolur(oy=15)
    kos(m, kare, asama=3, n=ONAY_KARE)
    b, a = kos(m, kare_f, [arac(govde, taraf="Dost")], asama=3, n=DOST_ONAY)
    assert a == -1 and b[0]["tip"] == "Dost", ("tasinan kart dost kanitina direndi", b)

    # 18. MENZIL (A3): cap girilmediyse mesafe/engel yok; girildiyse tipin bandi disinda
    #     ates ENGELLI (kilit surer). 41 px balon (sahte kutu) icin mesafe = cap x 0.2613.
    eski_cap, eski_kontrol = algi.AYAR["balon_cap_cm"], algi.AYAR["menzil_kontrol"]
    try:
        def a3_kilit(cls="f16"):
            sifirla()
            return kos(m, kare_d, [arac(govde, cls=cls)], asama=3, n=KART_ONAY + 1)
        algi.ayar_guncelle(balon_cap_cm=0)
        b, a = a3_kilit()
        assert a >= 0 and b[a]["mesafe"] is None and "engel" not in b[a], b[a]
        algi.ayar_guncelle(balon_cap_cm=46)                    # ~12 m: F16 bandinda
        b, a = a3_kilit()
        assert abs(b[a]["mesafe"] - 12.0) < 0.3 and "engel" not in b[a], b[a]
        assert "12.0m" in b[a]["ham"], b[a]["ham"]
        algi.ayar_guncelle(balon_cap_cm=70)                    # ~18 m: cok uzak
        b, a = a3_kilit()
        assert a >= 0 and "Menzil" in b[a].get("engel", ""), ("18 m'de ates engellenmedi", b[a])
        algi.ayar_guncelle(balon_cap_cm=30)                    # ~7.8 m
        b, a = a3_kilit()
        assert "Menzil" in b[a].get("engel", ""), ("F16'ya 7.8 m'de ates izni", b[a])
        b, a = a3_kilit(cls="drone")
        assert "engel" not in b[a], ("IHA 0-15 m, 7.8 m'de engellendi", b[a])
        b, a = a3_kilit(cls="belirsiz")                       # tip okunamadi: ortak 10-15 m
        assert a >= 0 and b[a]["kart_tip"] is None and "Menzil" in b[a].get("engel", ""),             ("tipi bilinmeyen dusmana 7.8 m'de ates izni", b[a])
        algi.ayar_guncelle(menzil_kontrol=0)
        b, a = a3_kilit()
        assert "engel" not in b[a], "menzil kontrolu kapaliyken engel"
        algi.ayar_guncelle(menzil_kontrol=1, balon_cap_cm=70)
        sifirla()
        b, a = kos(m, kare, asama=2, n=ONAY_KARE + 1)
        assert a >= 0 and "engel" not in b[a], "A2'de menzil kurali uygulandi"
        # 18b. A3 IKI DUSMAN: merkeze yakin olan bandin DISINDA (26 px ~19 m), uzaktaki
        #      bantta (41 px ~12 m). Kilit bantta olana kurulur; bant disindakine kilitliyken
        #      bantta dusman belirirse ona gecilir (eskiden uzaktakine kilitli bekliyordu).
        algi.ayar_guncelle(balon_cap_cm=46)
        yakin_govde, uzak_govde = (615, 330, 665, 380), (870, 320, 930, 372)
        sadece_uzak = sahne([(640, 400, 26)], [(yakin_govde, KIRMIZI_ARAC)])
        ikisi = sahne([(640, 400, 26), (900, 400, 41)],
                      [(yakin_govde, KIRMIZI_ARAC), (uzak_govde, KIRMIZI_ARAC)])
        sifirla()
        for _ in range(KART_ONAY + 10):      # ILK kurulan kilit bantta olana (sonradan devir degil)
            b, a = kos(m, ikisi, asama=3)
            if a >= 0:
                break
        assert a >= 0 and b[a]["box"][0] > 800 and "engel" not in b[a], ("bant disindakine kilit", b[a])
        sifirla()
        b, a = kos(m, sadece_uzak, asama=3, n=KART_ONAY + 6)
        assert a >= 0 and "Menzil" in b[a].get("engel", ""), b[a]
        b, a = kos(m, ikisi, asama=3, n=KART_ONAY + 6 + GOVDE_DEVIR_KARE)
        assert a >= 0 and b[a]["box"][0] > 800, ("bantta dusman varken bant disinda beklendi", b[a])
    finally:
        algi.ayar_guncelle(balon_cap_cm=eski_cap, menzil_kontrol=eski_kontrol)

    # ---- 24.09 koridor videosunda bulunan hatalar ----
    # 19. RENK / SEKIL SUZGECI: model gri cami ve uzun kirmizi kolu "balon" sandi; ikisi de
    #     elenir, ayni karedeki gercek balon yine kilitlenir.
    GRI = (150, 150, 150)
    mg = SahteModel(renkler={BALON_RENK: 0.9, GRI: 0.9})
    sifirla()
    k = sahne()
    cv2.ellipse(k, (400, 400), (20, 20), 0, 0, 360, GRI, -1)
    cv2.ellipse(k, (900, 400), (15, 35), 0, 0, 360, BALON_RENK, -1)   # en/boy 0.43 (kol)
    cv2.ellipse(k, (1100, 400), (12, 19), 0, 0, 360, BALON_RENK, -1)  # 0.64 (uzak tisort)
    b, a = kos(mg, k, n=ONAY_KARE + 2)
    assert b == [] and a == -1, ("gri / uzun leke balon sayildi", b)
    cv2.ellipse(k, (640, 400), (20, 20), 0, 0, 360, BALON_RENK, -1)
    b, a = kos(mg, k, n=ONAY_KARE + 1)
    assert a >= 0 and len(b) == 1 and abs(b[a]["box"][0] - 620) <= 2, b

    # 20. YANSIMA: balonun hemen altinda DAHA AZ guvenli "balon" (parlak zemin) kilidi
    #     almaz — kare merkezine daha yakin olsa da. Yansimaya kilitliyken balon belirirse
    #     kilit USTE gecer.
    YANSIMA_RENK = (0, 0, 200)
    my = SahteModel(renkler={BALON_RENK: 0.9, YANSIMA_RENK: 0.7})
    sifirla()
    k = sahne([(640, 320, 36)])
    cv2.ellipse(k, (640, 362), (18, 18), 0, 0, 360, YANSIMA_RENK, -1)   # merkeze daha yakin
    b, a = kos(my, k, n=ONAY_KARE + GOVDE_DEVIR_KARE + 3)
    assert a >= 0 and b[a]["box"][1] < 320, ("kilit yansimada", b[a])
    sifirla()
    yalniz_yansima = sahne()
    cv2.ellipse(yalniz_yansima, (640, 362), (18, 18), 0, 0, 360, YANSIMA_RENK, -1)
    b, a = kos(my, yalniz_yansima, n=ONAY_KARE)
    assert a >= 0 and b[a]["box"][1] > 340
    b, a = kos(my, k, n=ONAY_KARE + GOVDE_DEVIR_KARE + 1)
    assert a >= 0 and b[a]["box"][1] < 320, ("yansimadan balona gecilmedi", b[a])

    # 21. KENAR: kareye yari girmis cisim (kameranin dibinden gecen kol) YENI kilit almaz;
    #     iceri girince alir.
    sifirla()
    b, a = kos(m, sahne([(12, 400, 40)]), n=ONAY_KARE + 3)
    assert a == -1 and len(b) == 1, ("kenardaki cisme kilit", b, a)
    b, a = kos(m, sahne([(60, 400, 40)]), n=2)
    assert a >= 0, "iceri giren balon kilitlenmedi"

    # 22a. SEYREK GORULEN (4 karede 1, %90 guvenle bile) cisim kilit ALMAZ: buyuk kirmizi
    #      govdenin parcasi tek tuk "balon" cikiyordu (23.09 ekran kaydi). Kararli gorulen alir.
    sifirla()
    for j in range(40):
        b, a = kos(m, kare if j % 4 == 0 else bos)
        assert a == -1, ("seyrek gorulen cisme kilit", j, b)
    b, a = kos(m, kare, n=ONAY_KARE + 1)
    assert a >= 0, "kararli gorulen balon kilitlenmedi"

    # 22. DUSUK GUVEN: KILIT_GUVEN altindaki iz gosterilir ama kilitlenmez.
    sifirla()
    b, a = kos(SahteModel(renkler={BALON_RENK: 0.4}), kare, n=10)
    assert a == -1 and len(b) == 1, (b, a)

    # 23. GENC IZ: ONAY_KARE gorulup kaybolan izin kilidi KAYIP_GENC_S'de duser (0.5 sn
    #     bos hayalet kilidi yok); oturmus iz KAYIP_S boyunca hayalet kalir.
    sifirla()
    b, a = kos(m, kare, n=ONAY_KARE)
    assert a >= 0
    b, a = kos(m, bos, n=int(KAYIP_GENC_S * 30) + 2)
    assert a == -1 and not _izler, ("genc iz kilidi tuttu", b)
    sifirla()
    kos(m, kare, n=OTURMUS_KARE)
    b, a = kos(m, bos, n=int(KAYIP_GENC_S * 30) + 2)
    assert a >= 0 and b[a]["hayalet"], "oturmus iz erken silindi"

    # 24. RENKLE DEVAM: model kor (bulaniklik) iken dogrulanmis iz kirmizi lekeyle surer —
    #     hayalet yok, ayni kimlik, hareketi izler. Kisa kayipta ates acik (dwell
    #     sifirlanmasin), RENK_ATES_S sonra ENGELLI, model donunce engel kalkar,
    #     RENK_AZAMI_S sonra renk izi biter.
    mr = SahteModel()
    sifirla()
    b, a = kos(mr, sahne([(600, 400, 40)]), n=OTURMUS_KARE)
    kid = b[a]["id"]
    mr.kor = True
    x = 604
    b, a = kos(mr, sahne([(x, 400, 40)]))
    assert a >= 0 and b[a]["id"] == kid and not b[a].get("hayalet") and b[a]["kaynak"] == "renk", b
    assert "engel" not in b[a], "kisa renk izinde ates engellendi"
    for _ in range(int(RENK_ATES_S * 30) + 1):
        x += 2
        b, a = kos(mr, sahne([(x, 400, 40)]))
    assert a >= 0 and b[a]["id"] == kid and "renkle" in b[a].get("engel", ""), b[a]
    assert abs((b[a]["box"][0] + b[a]["box"][2]) / 2 - x) <= 2, "renk izi balonu izlemedi"
    mr.kor = False
    b, a = kos(mr, sahne([(x, 400, 40)]))
    assert a >= 0 and b[a]["id"] == kid and "engel" not in b[a], b[a]
    mr.kor = True
    b, a = kos(mr, sahne([(x, 400, 40)]), n=int(RENK_AZAMI_S * 30) + 3)
    assert a == -1 or b[a].get("hayalet"), ("renk izi sinirsiz surdu", b[a])
    # 24a. Dogrulanmis izin guveni uzaklasinca dusse de (videoda 16 px'te %31-41) renkle
    #      devam eder — eskiden guven esigi renk devamini kapatiyordu.
    mr.kor = False
    sifirla()
    kos(mr, sahne([(600, 400, 40)]), n=OTURMUS_KARE)
    mr.renkler[BALON_RENK] = 0.35
    b, a = kos(mr, sahne([(600, 400, 40)]), n=12)
    assert _izler[b[a]["id"]]["guven"] < KILIT_GUVEN
    mr.kor = True
    b, a = kos(mr, sahne([(602, 400, 40)]))
    assert a >= 0 and b[a]["kaynak"] == "renk" and not b[a].get("hayalet"), b[a]
    mr.renkler[BALON_RENK] = 0.9
    # 24c. Leke kare kare buyurse (balon govdeye/tisorte karisiyor) renk izi MODELIN son
    #      kutusuna gore sinirli: %25/kare buyume 3. karede durur (eskiden her kare kendi
    #      renk kutusuyla kiyaslanip 23 -> 50 px'e kaydi).
    mr.kor = False
    sifirla()
    kos(mr, sahne([(640, 400, 30)]), n=OTURMUS_KARE)
    mr.kor = True
    for cap in (37, 46, 58):
        b, a = kos(mr, sahne([(640, 400, cap)]))
    assert a >= 0 and b[a].get("hayalet"), ("renk izi buyuyen lekeye kaydi", b[a])
    # 24b. Balon kirmizi govdeye yapisirsa leke boyu tutmaz: iz govdeye KAYMAZ (hayalet).
    mr.kor = False
    sifirla()
    kos(mr, sahne([(640, 400, 40)]), n=OTURMUS_KARE)
    mr.kor = True
    b, a = kos(mr, sahne([(640, 400, 40)], [((600, 330, 680, 385), KIRMIZI_ARAC)]))
    assert a >= 0 and b[a].get("hayalet"), ("renk izi govdeye kaydi", b[a])

    # 24d. CIFT ESIK: dogrulanmis iz 0.2 guvenli tespitle SURER (hayalet degil); ayni
    #      guvenle ILK kez gorulen cisim hic iz acmaz; IZ_ESIK altindaki kutu yok sayilir.
    mz = SahteModel()
    sifirla()
    kos(mz, kare, n=OTURMUS_KARE)
    mz.renkler[BALON_RENK] = 0.2
    b, a = kos(mz, kare, n=5)
    assert a >= 0 and not b[a].get("hayalet") and b[a]["kaynak"] == "tam", ("zayif tespit izi surdurmedi", b)
    sifirla()
    b, a = kos(mz, kare, n=10)
    assert b == [] and a == -1, ("dusuk guvenli yeni cisim iz acti", b)
    # tek guclu gorunus + ardindan yalniz zayif tespitler: iz DOGRULANMADI, genc iz gibi olur
    sifirla()
    kos(SahteModel(), kare)
    b, a = kos(mz, kare, n=20)
    assert b == [] and not _izler, ("zayif tespit dogrulanmamis izi yasatti", b)
    mz.renkler[BALON_RENK] = 0.1
    sifirla()
    kos(SahteModel(), kare, n=OTURMUS_KARE)
    b, a = kos(mz, kare)
    assert a >= 0 and b[a]["kaynak"] != "tam", ("IZ_ESIK altindaki kutu kabul edildi", b[a])
    # 24e. LAZER ALTINDA (24.09 saha): lazer noktasi modeli kor eder (her atis ~0.2 sn'de
    #      kesiliyordu). Balon SAGLAMSA (halka kaniti) iz ates turu boyunca yerinde surer,
    #      "yalniz renkle" engeli gelmez; tur bitince (+ gecikme) kanit tek basina iz yasatmaz.
    mr.kor = False
    sifirla()
    tek_balon = sahne([(640, 400, 40)])
    b, a = kos(mr, tek_balon, n=OTURMUS_KARE)
    ates_basladi(True, simdi=T[0], sure=2.0)
    mr.kor = True
    b, a = kos(mr, tek_balon, n=int((RENK_ATES_S + 0.3) * 30))
    assert a >= 0 and not b[a].get("hayalet") and b[a]["kaynak"] == "lazer" \
        and "engel" not in b[a], ("lazer altinda saglam balon birakildi", b[a])
    ates_bitti(simdi=T[0])
    b, a = kos(mr, tek_balon, n=int(LAZER_GECIKME_S * 30) + 2)
    assert a == -1 or b[a].get("hayalet"), ("ates bitti, halka kaniti izi yasatti", b[a])
    # 24f. Patlayan balonun yerinde (hemen ustunde) KIRMIZI GOVDE kalsa da iz yasamaz:
    #      halka balonun dairesine bakar, govde oraya girmez -> hayalet, kaybolursa imha.
    mr.kor = False
    sifirla()
    govde_ustte = [((600, 330, 680, 384), KIRMIZI_ARAC)]
    b, a = kos(mr, sahne([(640, 400, 40)], govde_ustte), n=OTURMUS_KARE)
    ates_basladi(True, simdi=T[0])
    mr.kor = True
    b, a = kos(mr, sahne([], govde_ustte))
    assert a >= 0 and b[a].get("hayalet"), ("patlayan balonun govdesi izi yasatti", b[a])
    # 24g. Balon KIRMIZI bir yuzeyin (tisort, govde) onundeyse dis halka da kirmizi: sinirli
    #      bir balon kaniti yok -> model gormezse iz hayalet (kirmizi arka plana ates surmez).
    mr.kor = False
    sifirla()
    arka = sahne([(640, 400, 40)], [((520, 300, 760, 500), KIRMIZI_ARAC)])
    b, a = kos(mr, arka, n=OTURMUS_KARE)
    ates_basladi(True, simdi=T[0])
    mr.kor = True
    b, a = kos(mr, arka)
    assert a >= 0 and b[a].get("hayalet"), ("kirmizi arka planda lazer kaniti", b[a])
    mr.kor = False
    # 24h. TEMIZLIK: ortasi delik (lazer noktasi) balonu goremeyen model, ates altinda
    #      temizlenmis karede balonu yeniden gorur. Bos yerdeki nokta + kirmizi hale
    #      temizlenmez (balon uydurulmaz).

    class DelikKor(SahteModel):
        """Balon rengine YAKIN (+-40) ve DOLU (alan/kutu >= 0.7) lekeyi gorur."""
        def predict(self, girdiler, **kw):
            cikti = []
            for img in girdiler:
                alt = tuple(max(0, c - 40) for c in BALON_RENK)
                ust = tuple(min(255, c + 40) for c in BALON_RENK)
                n, _, ist, _ = cv2.connectedComponentsWithStats(cv2.inRange(img, alt, ust), 8)
                cikti.append(_Sonuc([_Kutu((x, y, x + w, y + h), 0.9)
                                     for x, y, w, h, alan in ist[1:] if alan >= 0.7 * w * h]))
            return cikti

    dk = DelikKor()
    noktali = sahne([(640, 400, 40)])
    cv2.circle(noktali, (640, 400), 8, (255, 255, 255), -1)
    kutu40 = (620, 380, 660, 420)
    assert not _tespit_et(dk, noktali, [], 0.3, []), "kurulum: delikli balon gorulmemeliydi"
    assert len(_tespit_et(dk, _lazer_temizle(noktali, kutu40), [], 0.3, [])) == 1, \
        "temizlenen noktali balon gorulmedi"
    sifirla()
    b, a = kos(dk, tek_balon, n=OTURMUS_KARE)
    ates_basladi(True, simdi=T[0])
    b, a = kos(dk, noktali, n=10)
    assert a >= 0 and b[a]["kaynak"] in ("tam", "pencere"), ("ates altinda temizlik yok", b[a])
    bos_nokta = sahne([])
    cv2.circle(bos_nokta, (640, 400), 14, (60, 60, 250), -1)      # kirmizi hale
    cv2.circle(bos_nokta, (640, 400), 8, (255, 255, 255), -1)
    assert _lazer_temizle(bos_nokta, kutu40) is bos_nokta, "bos yerde lazer noktasi temizlendi"
    assert not _lazer_bak(bos_nokta, kutu40)[0], "bos yerde halka kaniti"

    # 25. GOVDE RENGI (A3): arac modeli HIC okumasa da balonun hemen ustundeki kirmizi
    #     govde "Düşman" karti kurar (tip yok); mavi govde "Dost" (kilit yok, elle secim
    #     ret); kirmizi govdede mavi parca -> Dost; yanda / cok yukarda duran renk oy vermez.
    def govdeli(renk, box=(610, 330, 670, 372)):
        return sahne([(640, 400, 40)], [(box, renk)])

    sifirla()
    b, a = kos(m, govdeli(KIRMIZI_ARAC), asama=3, n=KART_ONAY)
    assert a == -1, "kirmizi govde ilk karelerde (sureklilik yokken) kart kurdu"
    b, a = kos(m, govdeli(KIRMIZI_ARAC), asama=3, n=5)
    assert a >= 0 and b[a]["tip"] == "Düşman" and b[a]["kart_tip"] is None, b
    assert _izler[b[a]["id"]]["kart"]["govde"] >= KART_ONAY
    sifirla()
    b, a = kos(m, govdeli(CYAN_ARAC), asama=3, n=10)
    assert a == -1 and b[0]["tip"] == "Dost", b
    assert hedef_sec(b[0]["id"], simdi=T[0]) is False, "mavi govdeli balon elle secildi"
    sifirla()
    k = govdeli(KIRMIZI_ARAC)
    cv2.rectangle(k, (645, 340), (668, 360), CYAN_ARAC, -1)
    b, a = kos(m, k, asama=3, n=10)
    assert a == -1 and b[0]["tip"] == "Dost", ("mavi varken dusman karti", b)
    # yanda (bolgenin icinde, balonun sutununda degil) / yukarda (bolgede, ama balondan kopuk)
    for box in ((680, 335, 715, 372), (620, 285, 660, 310)):
        sifirla()
        b, a = kos(m, govdeli(KIRMIZI_ARAC, box), asama=3, n=10)
        assert a == -1 and b[0]["tip"] == "Belirsiz", ("asili olmayan renk oy verdi", box, b)
    # 25b. Tek tuk kirmizi (5 karede 1: arkadan gecen, sandalye benegi) 60 karede de
    #      dusman karti KURMAZ — eskiden her oy birikiyordu.
    sifirla()
    for j in range(60):
        b, a = kos(m, govdeli(KIRMIZI_ARAC) if j % 5 == 0 else kare, asama=3)
    assert a == -1 and b[0]["tip"] == "Belirsiz", ("tek tuk kirmizi dusman yapti", b)
    # 25c. ARKA PLAN YUZEYI govde degil: balonun arkasindaki genis kirmizi (tisort, duvar)
    #      ya da mavi gokyuzu arama bolgesinin kenarlarina tasar -> oy yok. Gokyuzunun
    #      onundeki kirmizi govde yine "Düşman" (gokyuzu her dusmani dost yapmasin).
    sifirla()
    b, a = kos(m, govdeli(KIRMIZI_ARAC, (500, 150, 780, 390)), asama=3, n=12)
    assert a == -1 and b[0]["tip"] == "Belirsiz", ("genis kirmizi yuzey dusman yapti", b)
    gok = govdeli(KIRMIZI_ARAC)
    cv2.rectangle(gok, (0, 0), (1279, 377), CYAN_ARAC, -1)            # mavi gokyuzu
    cv2.rectangle(gok, (610, 330), (670, 372), KIRMIZI_ARAC, -1)      # onunde kirmizi govde
    sifirla()
    b, a = kos(m, gok, asama=3, n=KART_ONAY + 5)
    assert a >= 0 and b[a]["tip"] == "Düşman", ("mavi gokyuzu dusmani dost yapti", b)

    # 26. PENCERE BOYU: tam karede gorulmeyen kucuk balon kirmizi leke penceresinden
    #     bulunur; pencere kucuk balonda PENCERE_EN_AZ (buyutme 5x), govdeye yapisik
    #     birlesik lekede lekenin ONERI_KAT kati (eski kural 320 acip balonu kaybediyordu).
    for sahne_, en_cok in ((sahne([(640, 400, 14)]), PENCERE_EN_AZ),
                           (sahne([(640, 400, 14)], [((600, 330, 680, 394), KIRMIZI_ARAC)]),
                            200)):              # 80 px birlesik leke: 2.2x = 176 (eskisi 320)
        sifirla()
        mk = SahteModel(tam_en_az=20)
        b, a = kos(mk, sahne_, n=KIRMIZI_PERIYOT * 2)
        assert any(d["kaynak"] == "pencere" for d in b), ("kucuk balon leke penceresinde yok", b)
        kenarlar = [h for cagri in mk.boyutlar for h, w in cagri[1:]]
        assert kenarlar and max(kenarlar) <= en_cok and min(kenarlar) >= PENCERE_EN_AZ, kenarlar

    # 27. SURU (A2): kilitliyken diger UZAK balonun izi de surer (sirayla ek pencere);
    #     eskiden kilit disindaki kucuk balonlar pencere almayip siliniyordu.
    sifirla()
    mk = SahteModel(tam_en_az=20)
    iki_kucuk = sahne([(600, 400, 14), (900, 400, 14)])
    b, a = kos(mk, iki_kucuk, n=OTURMUS_KARE + 5)
    assert a >= 0 and len(b) == 2, b
    n = int((RENK_AZAMI_S + KAYIP_S) * 30) + 15     # renkle devam tek basina tasiyamasin
    b, a = kos(mk, iki_kucuk, n=n)
    assert len([d for d in b if not d.get("hayalet")]) == 2, ("kilit disindaki balonun izi koptu", b)
    assert max(mk.girdi_sayilari[-n:]) == 3, "kilitliyken ek pencere sayisi"

    # 28. ONDE MAVI GOVDE (A3): dusman balonun ortasini mavi bir govde kapatirsa ates
    #     ENGELLI — arac modeli dostu okumasa da.
    sifirla()
    b, a = kos(m, govdeli(KIRMIZI_ARAC), asama=3, n=KART_ONAY + 5)
    assert a >= 0 and "engel" not in b[a]
    k = govdeli(KIRMIZI_ARAC)
    # merkezin ~%25'i: balon hala "balon" (kirmizi suzgeci gecer) ama lazerin yolu mavi.
    # (Ortayi tamamen kaplayan govde balonu kirmizi suzgecinden dusurur -> hayalet, yine ates yok.)
    cv2.rectangle(k, (634, 394), (645, 405), CYAN_ARAC, -1)
    b, a = kos(m, k, asama=3)
    assert a >= 0 and not b[a].get("hayalet") and "Dost" in b[a].get("engel", ""),         ("mavi govde onundeyken ates acik", b[a])

    sifirla()
    print("balon_takip testleri OK — A2 kilit + balon merkezi, A1/E-Stop kilitsiz, A3 kart "
          "(arac yokken kilit yok / dusman karti kalici / dost reddi / dost kaniti kilidi "
          "birakir / tip suzgeci), imha (gercek lazer) + siradaki balon, patlamayan balon "
          "yasagi, govde elemesi, ust-alt devri, kamera kaymasi, kucuk balon penceresi, "
          "dost onunde engeli, kisa kayip, aractan secim, kart tasima (yakin/uzak/belirsiz/"
          "patlayan/dost kaniti), A3 menzil (cap yok / bantta / uzak / yakin F16 / IHA / A2), "
          "renk/sekil suzgeci, yansima, kenar, dusuk guven, genc iz, renkle devam "
          "(engel / sinir / govdeye kaymaz), govde rengi (dusman / dost / karisik / asili degil / "
          "tek tuk kirmizi / arka plan yuzeyi / gokyuzu), pencere boyu (kucuk / birlesik leke), "
          "cift esik, suru (kilit disi iz), onde mavi govde, lazer altinda (halka kaniti / "
          "tur bitince birakir / patlayinca govde yasatmaz / kirmizi arka plan / temizlik / "
          "bos yerde balon uydurmaz)")
