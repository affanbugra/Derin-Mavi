# -*- coding: utf-8 -*-
"""DERIN MAVI — DIKEY EKSEN (tilt) SURUCUSU: ESP32-S3 + HSD57 kapali cevrim kart.

Bu modul, tilt eksenini surmek icin YENI donanimi konusur. Eski `protokol.py`
(AccelStepper, "T<derece>") kartindan BAGIMSIZDIR; ikisi ayni anda, ayri
portlarda calisabilir: pan eski kartta kalir, tilt buraya gider.

NEDEN AYRI BIR KART VE AYRI BIR PROTOKOL?
  Tilt ekseni artik dogrudan tahrik degil, KOL-BIYEL (krank + baglama cubugu)
  mekanizmasiyla suruluyor (bkz. mekanik foto). Iki sonucu var:
    1. Motor acisi ile KOL acisi DOGRUSAL DEGIL. "60 derece" demek icin
       darbe sayisini formulle hesaplayamayiz; olculmus bir KALIBRASYON
       TABLOSU gerekir (kart bunu kalici bellekte tutar).
    2. Kol 0..60 derece arasinda calisir; eski protokoldeki TILT_MAX=180
       bu mekanikte FIZIKSEL OLARAK YOKTUR. Sinir burada kirpilir.

PROTOKOL (ws_motor_test/esp32_ws_test, 115200 baud, ASCII satir + LF):
    E            kontrolu ac (silahlandir). OK,E gelmeden hicbir hareket gecmez.
    D            durdur + kontrolu kapat.      X   durdur, bekleyen hedefi iptal et.
    H            canlilik (heartbeat).
    G<derece>    MUTLAK hedef aci (0..60)      "G12.5000"
    V100/400/800 jog hizi (yalniz dururken; biz jog kullanmiyoruz)
    K / C<der>   KALIBRASYON — bu modul BILEREK GONDERMEZ, bkz. asagi.

    Kart -> laptop, 100 ms'de bir:
    STATE3,pos,target,upper,cal,moving,armed,commissioning,angle,goal,count,last_angle,speed

Bu ham protokol fiziksel KOL acisi (0..60) konusur. Modulun Python API'si ise
operator acisi (-30..+30) konusur: operator 0 = fiziksel kol 30. Donusum yalniz
bu dosyada yapilir; disaridaki kod G/STATE3'un ham acisini kullanmaz.

⚠ KALIBRASYON KOMUTLARI (K/C) BU MODULDE YOK — BILEREK.
  `K` kartta KAYITLI TABLOYU SILER. Kalibrasyon, kolun fiziksel olarak 0
  konumunda olmasini ve operatorun aciyi haricen olcmesini gerektiren bir
  KURULUM islemidir; kazara tetiklenmesi (yanlis tusa basma, otonom dongude
  bir hata) mekanigi dayamaya surebilir. O is icin ayri bir arac var:
  `ws_motor_test/keyboard_control.py`. Tablo kartin kalici belleginde (NVS)
  durur, resetten sonra da yasar — yani bir kere kalibre edilir, Derin Mavi
  yalnizca "kalibre mi?" diye BAKAR (STATE3'teki `cal` biti).

⚠ OLCULEN ACI vs KOMUT EDILEN ACI. Eski kart konum bildirmiyordu, bu yuzden
  ekrandaki aci "hedef"ti (bkz. kontrol.py). BU KART BILDIRIYOR: STATE3'teki
  `angle`, kartin darbe sayacindan + kalibrasyon tablosundan hesapladigi
  konumdur. Hala ENCODER olcumu degildir (encoder HSD57'nin icinde kalir,
  kapali cevrimi surucu kendi yapar) ama laptopun inancindan cok daha
  gercektir: kaybolan/geciken komutlar buradan yakalanir.

⚠ TEK BEKLEME YUVASI — TAKIP ICIN KRITIK. Firmware hareket halindeyken gelen
  yeni hedefi `pending_` yuvasina koyar ve ONCE MEVCUT HEDEFE GIDER, sonra
  bekleyene yonelir. Takipte bu "once eski hedefe kadar git, sonra geri don"
  demektir — namlu asar ve geri salinir. Cozum BU TARAFTA: komutlar kart
  BOSTAYKEN gonderilir, beklerken PC tarafinda TEK YUVALI "en yenisi kazanir"
  kuyrugunda tutulur (bkz. TiltSurucu.git / _bosalt). Boylece karta hicbir
  zaman BAYAT hedef girmez. Kesintisiz yeniden planlama firmware'e eklenirse
  (yol haritasi) bu kuyruk kaldirilabilir.
"""
import math
import os
import re
import time

# ---- Kart sabitleri (ws_motor_test/esp32_ws_test/motion_core.h ile AYNI olmali) ----
# IKI ACI CERCEVESI VAR — karistirilmamali:
#   KOL acisi   : kartin/mekanizmanin acisi, 0..60. Kalibrasyon tablosu, STATE3'teki
#                 `angle`, G/Y komutlari ve darbe sayaci HEP bu cercevededir.
#   OPERATOR acisi: -30..+30. Sistem acilinca kol KULLANICI_SIFIR'a (30) yukselir ve
#                 orasi 0 kabul edilir. NEDEN: kol en alttayken kamera yere/masaya
#                 bakiyor, ilk goruntu ise yaramiyordu; operator "0" deyince namlu
#                 calisma araliginin ORTASINDA olmali, ucunda degil.
# Modulun DISARI actigi her aci (aci_kirp, kamera_acisi, kol_acisi, durum sozlugunun
# `aci`/`hedef` alanlari) OPERATOR cercevesindedir; kola cevirim burada yapilir.
KOL_MIN, KOL_MAX = 0.0, 60.0        # kol calisma araligi — MEKANIK, 180 DEGIL
KULLANICI_SIFIR = 30.0              # operatorun 0 kabul ettigi KOL acisi
ACI_MIN, ACI_MAX = KOL_MIN - KULLANICI_SIFIR, KOL_MAX - KULLANICI_SIFIR   # -30..+30


def kol_karsiligi(aci):
    """Operator acisi -> kol acisi (karta giden)."""
    return float(aci) + KULLANICI_SIFIR


def aci_karsiligi(kol):
    """Kol acisi (karttan gelen) -> operator acisi."""
    return float(kol) - KULLANICI_SIFIR


BAUD = 115200
NOKTA_MAKS = 16                     # MotionCore::CAPACITY
ZAMAN_ASIMI_MS = 350                # MotionCore::TIMEOUT_MS — bu sure sessizlikte kart kilitlenir
CANLILIK_MS = 120                   # biz bu sikligda "H" yolluyoruz (asiminin ~1/3'u)
YOKLAMA_MS = 40                     # arayuzun yokla() periyodu: H gercekten ~120 ms'de bir gitsin
# (24.09 saha: periyot 100 ms iken H fiilen 200 ms'de bir gidiyordu -> 350 ms asimina yalniz
# ~150 ms pay kaliyordu; acilistaki model yuklemesi arayuzu takinca kol yarida kilitlendi.)
R_BEKLEME_S = 1.0                   # R'nin yaniti bu surede gelmezse eski duruma yeniden guvenilir
JOG_HIZLAR = (100, 400, 800)

# ---- HEDEF HAREKETI HIZ PROFILI (firmware "Z<hiz>,<ivme>" komutu) ----
# Firmware'deki siniirlar (MotionCore::HIZ_TABAN/TAVAN, IVME_TABAN/TAVAN) ile AYNI
# olmali; disina cikan deger BAD_SPEED ile reddedilir.
HIZ_TABAN, HIZ_TAVAN = 100.0, 5000.0          # darbe/s
IVME_TABAN, IVME_TAVAN = 200.0, 60000.0       # darbe/s^2

# Kademeler DERECE cinsinden tanimlanir, darbeye kalibrasyondan cevrilir: mekanizma
# degisir veya yeniden kalibre edilirse kademeler KENDILIGINDEN dogru kalir.
# Darbe cinsinden yazilsaydi 60 derece kac darbe ediyorsa ona baglanirdi.
#
# ⚠ ASIL MESELE IVME. Eski firmware 1600 darbe/s tepe hiza 3200 darbe/s^2 ile
# cikiyordu: tepe hiza ulasma suresi 0.5 sn. Kisa hareketlerde tepe hiza HIC
# ulasilmiyor, hareket "agir" hissettiriyordu. Buradaki kademelerde bu sure
# ~0.11 sn. Olculen (2675 darbe/60 derece, 0->20 derece):
#     eski profil (1600/3200)   : 1.04 sn  = 19 derece/sn
#     Normal                    : 0.55 sn  = 36 derece/sn
#     Hizli                     : 0.37 sn  = 54 derece/sn
H_YAVAS, H_NORMAL, H_HIZLI = 1, 2, 3
HIZ_TABLO = {                 # seviye: (tepe hiz derece/sn, ivme derece/sn^2)
    H_YAVAS:  (20.0, 150.0),  # hassas nisan
    H_NORMAL: (45.0, 400.0),
    H_HIZLI:  (75.0, 700.0),  # ani hareket
}
HIZ_VARSAYILAN = H_NORMAL
# OTONOM TAKIP IVME TAVANI (derece/sn^2). 24.09 saha: "balonu sert takip ediyor" — asili
# balon salinirken namlu kademenin tam ivmesiyle (400/500) ileri geri firliyordu (kayitta
# %95 150-380 der/sn^2, balonun kendisi 1-2 der/sn). Kartin yorunge kopyasiyla benzetim:
# 500 -> 250'de tepe ivme yariya iner, takip hatasi degismez (asili balon 9.6 -> 10.2 px,
# rayda 6 der/sn hedef %95 4.1 -> 3.9 px); 150'de rayda hedef geride kalmaya basliyor.
# Tepe hiz kademeninki kalir; manuel kullanim etkilenmez.
TAKIP_IVME = 200.0

# ---- PAN (sag-sol) EKSENI — AYNI ESP32-S3 KARTINDA (GPIO10 PUL / GPIO11 DIR) ----
# Firmware pan'i "P<derece>" ile alir, "PAN1,pos,target,moving,angle,goal,en" yayinlar
# (bkz. ws_motor_test/esp32_ws_test/pan_core.h). Oran sabittir: 6400 darbe/tur,
# 15 -> 83 disli. Aci SARMASIZ (birikimli) ve isaretlidir; 0 = kart acildigi konum.
PAN_DARBE_DER = 6400.0 * (83.0 / 15.0) / 360.0      # ~98.37
PAN_SINIR = 400.0                                    # firmware PanCore::ACI_SINIR
# Pan kademeleri (derece/sn, derece/sn^2). Firmware pan tavani 12000 darbe/sn
# (~122 derece/sn) ve 150000 darbe/sn^2 (bkz. pan_core.h).
# ⚠ IVME ASIL BELIRLEYICI: ilk surumde 100 derece/sn^2 idi; takipteki kisa
# duzeltmelerde tepe hiza hic cikilamadi, sahada "yatay cok yavas" goruldu.
PAN_HIZ_TAVAN, PAN_IVME_TAVAN = 12000.0, 150000.0     # darbe/s, darbe/s^2
PAN_HIZ_TABLO = {
    H_YAVAS:  (25.0, 200.0),
    H_NORMAL: (60.0, 500.0),
    H_HIZLI:  (100.0, 800.0),
}
PAN_TAKIP_IVME = 250.0          # bkz. TAKIP_IVME


def takip_profili(profil, tavan):
    """(hiz, ivme) profilinin otonom takip karsiligi: ivme `tavan`i asamaz."""
    return profil[0], min(profil[1], tavan)


# ---- KOL ACISI -> KAMERA ACISI (surekli takip icin) ----
# Kol-biyel mekanizmasinda kamera, kol "derecesi" basina SABIT miktarda donmuyor.
# OLCULDU (22.09, faz korelasyonu, +-1.5 ve +-4 derece adimlar, iki yon, dokulu oda):
# yerel piksel/derece (1280 px). 50 derecenin ustu tavana bakiyor, olcum guvenilmez
# (guven 0.1-0.4) -> 46'daki deger sabit uzatildi. ⚠ 23.09'dan beri otonom takip
# bu bolgeye de girebilir (gizli tavan kaldirildi); oradaki kazanc TAHMINE dayanir.
# SAHADAKI SONUC: 12.4 sabit kabul edilince 36-50 derecede kontrolcu kolun kendi
# hareketini hedef hareketi sandi (kamera kolun 0.3-0.7'si kadar donuyor), kol
# 35->53 derece firladi ve yuksek acida +-10 derece salindi.
KAMERA_PPD_TABLO = [(0.0, 10.5), (5.0, 10.5), (12.0, 11.3), (20.0, 12.7), (28.0, 13.5),
                    (32.0, 10.0), (36.0, 9.1), (40.0, 7.6), (44.0, 5.3), (46.0, 5.4),
                    (60.0, 5.4)]
# Kameranin GERCEK derece basina piksel sayisi: pan'da olculen (pan disli orani
# sabit, 90 derece sahada dogrulandi). Kare pikseller -> dikeyde de ayni.
KAMERA_PPD_REF = 18.7


def _kamera_tablosu(adim=0.1):
    kol, kam, acc = [0.0], [0.0], 0.0
    x = 0.0
    while x < KOL_MAX - 1e-9:
        y = min(KOL_MAX, x + adim)
        acc += 0.5 * (_ppd_kol(x) + _ppd_kol(y)) * (y - x) / KAMERA_PPD_REF
        kol.append(y)
        kam.append(acc)
        x = y
    return kol, kam


def _ppd_kol(a):
    t = KAMERA_PPD_TABLO
    if a <= t[0][0]:
        return t[0][1]
    for (a0, p0), (a1, p1) in zip(t, t[1:]):
        if a0 <= a <= a1:
            return p0 + (p1 - p0) * (a - a0) / (a1 - a0)
    return t[-1][1]


def _ara(xs, ys, x):
    import bisect
    if x <= xs[0]:
        return ys[0] + (x - xs[0]) * (ys[1] - ys[0]) / (xs[1] - xs[0])
    if x >= xs[-1]:
        return ys[-1] + (x - xs[-1]) * (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
    i = bisect.bisect_right(xs, x)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


_KOL, _KAM = _kamera_tablosu()


def kamera_acisi(aci):
    """OPERATOR acisi -> kameranin gercek yukselis acisi (derece).

    ⚠ Kamera olceginin sifiri KOLUN EN ALTIDIR (fiziksel taban), operatorun sifiri
    degil: olculen tablo (KAMERA_PPD_TABLO) kol acisinda kuruldu ve takip kodu bu
    olcegi alt/ust siniri ifade etmek icin de kullaniyor."""
    return None if aci is None else _ara(_KOL, _KAM, kol_karsiligi(aci))


def kol_acisi(kamera):
    """kamera_acisi'nin tersi (tablo monoton artan). Doner: OPERATOR acisi."""
    return None if kamera is None else aci_karsiligi(_ara(_KAM, _KOL, float(kamera)))


def pan_kirp(derece):
    return max(-PAN_SINIR + 1.0, min(PAN_SINIR - 1.0, float(derece)))


def pan_git(derece):
    return f"P{pan_kirp(derece):.3f}\n"


def pan_yorunge(derece, hiz):
    v = max(-YORUNGE_HIZ_SINIRI, min(YORUNGE_HIZ_SINIRI, float(hiz)))
    return f"PY{pan_kirp(derece):.3f},{v:.3f}\n"


def pan_profili(darbe_sn, ivme_darbe_sn2):
    h = max(HIZ_TABAN, min(PAN_HIZ_TAVAN, float(darbe_sn)))
    iv = max(IVME_TABAN, min(PAN_IVME_TAVAN, float(ivme_darbe_sn2)))
    return f"PZ{h:.1f},{iv:.1f}\n"


def pan_durum_coz(satir):
    """PAN1 satiri -> sozluk; bozuksa None."""
    parts = satir.split(',')
    if len(parts) != 7 or parts[0] != 'PAN1':
        return None
    try:
        pos, target, moving = int(parts[1]), int(parts[2]), int(parts[3])
        angle, goal, en = float(parts[4]), float(parts[5]), int(parts[6])
    except ValueError:
        return None
    if moving not in (0, 1) or en not in (-1, 0, 1):
        return None
    if not (math.isfinite(angle) and math.isfinite(goal)):
        return None
    return dict(pos=pos, target=target, hareket=bool(moving), aci=angle, hedef=goal, en=en)


# Kartin "durum yok" kabul ettigimiz suresi: STATE3 100 ms'de bir gelir; 3 paket
# kacarsa bagi kopmus sayariz (arayuz de oyle gosterir).
DURUM_ASIMI_S = 0.6
DURUM_PERIYODU_S = 0.02             # firmware STATE3/PAN1 yayin araligi (50 Hz)

KAYNAK = os.environ.get("DERINMAVI_TILT", "off").strip() or "off"

# ESP32-S3'un IKI USB yolu vardir ve hangisine kablo takiliysa BASKA bir COM
# numarasi cikar — sahada "bir seferinde COM3, bir seferinde COM4" tam olarak budur:
#   VID 303A = Espressif NATIVE USB  (kartin kendi USB soketi)
#   VID 1A86 = WCH CH343/CH340       (harici seri cip, UART0)
# Firmware IKISINI DE dinler (Serial + Serial0), yani ikisi de gecerlidir; sorun
# yalnizca numarayi elle yazmaktir. `DERINMAVI_TILT=auto` bu isi bitirir.
ESP_VIDLER = (0x303A, 0x1A86)


def port_adi(ad):
    """Kullanicinin yazdigi port adini isletim sistemine uygun hale getirir.

    YALNIZ Windows bicimi (`com3`) buyuk harfe cevrilir. macOS/Linux'ta port bir
    DOSYA YOLUDUR ve buyuk/kucuk harf duyarlidir: eskiden her ad `.upper()` ile
    buyutuluyordu, `/dev/cu.usbmodem1101` -> `/DEV/CU.USBMODEM1101` olup "No such
    file" ile acilamiyordu (Mac'te kart takiliyken "cihaz yok"). Windows'ta davranis
    AYNEN korunur: `COM3`/`com3` yine `COM3` olur."""
    ad = ad.strip()
    if re.fullmatch(r"(?i)com\d+", ad):
        return ad.upper()
    return ad


def otomatik_port_bul(dinleme=0.8, gunluk=None):
    """STATE3 yayinlayan portu kendisi bulur; bulamazsa None.

    Neden "ESP32 gorunen ilk port" yetmez: ayni kartin iki yolu da ESP32 gibi
    gorunur, ustelik baska bir ESP32 (or. pan karti) da takili olabilir. Tek
    kesin olcut KARTIN KONUSTUGU DILDIR — bu yuzden port acilir ve gercekten
    `STATE3,` satiri yazip yazmadigina bakilir. Yanlis karta komut gondermenin
    bedeli, yanlis mekanigi hareket ettirmektir.
    """
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        return None

    adaylar = list(list_ports.comports())
    # ESP32 imzali portlar once denenir; digerleri yine de denenir (USB-TTL
    # donusturuculer baska VID gosterir), yalniz sirasi sonda kalir.
    adaylar.sort(key=lambda p: 0 if (p.vid in ESP_VIDLER) else 1)

    for p in adaylar:
        try:
            # DTR/RTS KAPALI: aksi halde port acilisi karti RESETLER ve firmware
            # "kol 0'da" varsayar — kol yukaridayken bu, aci referansini bozar.
            baglanti = serial.Serial(port=None, baudrate=BAUD, timeout=0)
            baglanti.dtr = False
            baglanti.rts = False
            baglanti.port = p.device
            baglanti.open()
        except Exception as e:
            if gunluk is not None:
                gunluk.append(f"{p.device}: acilamadi ({e})")
            continue
        try:
            baglanti.reset_input_buffer()
            tampon, bitis = "", time.time() + dinleme
            while time.time() < bitis:
                n = baglanti.in_waiting
                if n:
                    tampon += baglanti.read(n).decode("ascii", "replace")
                    if "STATE3," in tampon:
                        if gunluk is not None:
                            gunluk.append(f"{p.device}: STATE3 BULUNDU")
                        return p.device
                time.sleep(0.02)
            if gunluk is not None:
                gunluk.append(f"{p.device}: STATE3 yok "
                              f"({'sessiz' if not tampon else 'baska bir sey konusuyor'})")
        finally:
            try:
                baglanti.close()
            except Exception:
                pass
    return None


def aci_kirp(derece):
    """OPERATOR acisini calisma araligina (-30..+30) kirpar. Kart da kendi tarafinda
    kirpar/reddeder (BAD_ANGLE); tek tarafa guvenilmez — seri monitorden elle G500
    yazan biri de olabilir."""
    return max(ACI_MIN, min(ACI_MAX, float(derece)))


# ---- komut ureticiler (tek cikis noktasi: kimse elle string kurmaz) ----
AC = "E\n"          # kontrolu ac
KAPAT = "D\n"       # durdur + kontrolu kapat
DUR = "X\n"         # durdur, bekleyen hedefi iptal et
CANLI = "H\n"       # heartbeat
SORGU = "Q\n"       # yetenek sorgusu: OK,Q = hareket halinde durmadan yeniden planlar
YORUNGE_SORGU = "YQ\n"   # yetenek sorgusu: OK,YQ = yorunge kipi (Y/PY) var
YORUNGE_HIZ_SINIRI = 300.0  # derece/sn — firmware 400'u reddeder
# LAZER + ACIL DURDURMA (24.09, tek kart: lazer GPIO 18, buton GPIO 15). Kurallar
# firmware'de (esp32_ws_test.ino): L1 1 sn tazelenmezse kart lazeri kendi keser; kontrol
# kapaninca (nabiz kaybi / D) lazer soner; STOP karti kilitler (hareket + L1 reddedilir),
# kilidi PC'nin otomatik "E"si degil yalniz START kaldirir; buton basiliyken START ret.
LAZER_AC = "L1\n"       # ac / tazele (arayuz 250 ms'de bir)
LAZER_KES = "L0\n"      # kes — her porttan, her durumda kabul edilir
ACIL_DUR = "STOP\n"
ACIL_DEVAM = "START\n"
LAZER_DURUM_ASIMI_S = 0.6     # LZR1 bu kadar gelmezse kartin lazer bilgisi bayat


def lazer_guc(yuzde):
    return f"LP{max(0, min(100, int(round(yuzde))))}\n"


def lazer_durum_coz(satir):
    """LZR1,<acik>,<guc>,<acil>,<buton>,<pwm> -> sozluk; bozuksa None."""
    parts = satir.split(',')
    if len(parts) != 6 or parts[0] != 'LZR1':
        return None
    try:
        acik, guc, acil, buton, pwm = (int(p) for p in parts[1:])
    except ValueError:
        return None
    if not 0 <= guc <= 100 or any(v not in (0, 1) for v in (acik, acil, buton, pwm)):
        return None
    return dict(acik=bool(acik), guc=guc, acil=bool(acil), buton=bool(buton), pwm=bool(pwm))


def yorunge(derece, hiz):
    """Y<derece>,<derece/sn>: tilt YORUNGE kipi (otonom takip). Kart referansi
    derece + hiz*t olarak kendisi ilerletir; 150 ms yeni komut gelmezse yumusak durur."""
    v = max(-YORUNGE_HIZ_SINIRI, min(YORUNGE_HIZ_SINIRI, float(hiz)))
    return f"Y{kol_karsiligi(aci_kirp(derece)):.3f},{v:.3f}\n"


def git(derece):
    """MUTLAK hedef aci. Firmware strtod ile okur; keyboard_control.py ile ayni
    bicim kullanilir ki kart iki istemciden ayni sayiyi gorsun. Girdi OPERATOR
    acisidir; karta KOL acisi gider."""
    return f"G{kol_karsiligi(aci_kirp(derece)):.4f}\n"


def hiz_profili(darbe_sn, ivme_darbe_sn2):
    """Z<hiz>,<ivme> — hedef hareketinin tepe hizi ve ivmesi (darbe cinsinden).

    Firmware yalnizca DURURKEN kabul eder ve araligi asani reddeder; burada da
    kirpilir, iki tarafa birden guvenilmez."""
    h = max(HIZ_TABAN, min(HIZ_TAVAN, float(darbe_sn)))
    iv = max(IVME_TABAN, min(IVME_TAVAN, float(ivme_darbe_sn2)))
    return f"Z{h:.1f},{iv:.1f}\n"


def jog_hiz(darbe_sn):
    if darbe_sn not in JOG_HIZLAR:
        raise ValueError(f"jog hizi {JOG_HIZLAR} icinden olmali")
    return f"V{darbe_sn}\n"


def durum_coz(satir):
    """STATE3 satirini sozluge cevirir; bozuk/eski satirda None doner.

    Dogrulama ws_motor_test/protocol.py:parse_status ile AYNIDIR — iki istemci
    ayni kartta ayni satiri farkli yorumlarsa hangisinin dogru oldugu
    anlasilmaz. Gevsetme: burada bir alan serbest birakilirsa, oradaki test de
    guncellenmeli."""
    parts = satir.split(',')
    if len(parts) != 13 or parts[0] != 'STATE3':
        return None
    try:
        pos, target, upper, cal, moving, armed, commissioning = map(int, parts[1:8])
        angle, goal = map(float, parts[8:10])
        count, last_angle, speed = int(parts[10]), float(parts[11]), int(parts[12])
        if not 1 <= count <= NOKTA_MAKS or speed not in JOG_HIZLAR:
            return None
        if not math.isfinite(last_angle) or not KOL_MIN <= last_angle <= KOL_MAX:
            return None
        if cal and (count < 2 or last_angle != KOL_MAX):
            return None
        if any(v not in (0, 1) for v in (cal, moving, armed, commissioning)):
            return None
        if not all(math.isfinite(v) for v in (angle, goal)):
            return None
        if not 0 <= pos <= 1000000 or not 0 <= target <= 1000000:
            return None
        if cal:
            if not 0 < upper <= 1000000 or max(pos, target) > upper or commissioning:
                return None
            if not KOL_MIN <= angle <= KOL_MAX or not KOL_MIN <= goal <= KOL_MAX:
                return None
        elif upper != 0 or angle != -1 or goal != -1:
            return None
        return dict(pos=pos, target=target, upper=upper, kalibre=bool(cal),
                    hareket=bool(moving), acik=bool(armed),
                    kalibrasyonda=bool(commissioning),
                    # KOL -> OPERATOR cercevesi. ⚠ Kalibresizken kart -1 ("bilinmiyor")
                    # bildirir; bu nobetci deger cevrilmez, aynen gecer.
                    aci=aci_karsiligi(angle) if cal else angle,
                    hedef=aci_karsiligi(goal) if cal else goal,
                    # son_aci KALIBRASYON verisidir: kol cercevesinde kalir.
                    nokta=count, son_aci=last_angle, hiz=speed)
    except ValueError:
        return None


# Kartin Turkce olmayan hata kodlari -> operatorun okuyacagi cumle.
HATALAR = {
    'DISARMED': 'Tilt kartı kilitli. Kontrol yeniden açılıyor...',
    'CAL_REQUIRED': 'Tilt kartı KALİBRE DEĞİL. Önce ws_motor_test/keyboard_control.py '
                    'ile kolu 0°–60° arasında kalibre et.',
    'CAL_REQUIRES_ZERO_IDLE': 'Tilt kalibrasyonu yalnızca kol 0 konumunda ve dururken başlar.',
    'STOP_FIRST': 'Tilt kartı hareket hâlinde; komut reddedildi.',
    'BAD_ANGLE': 'Tilt açısı operator ölçeğinde -30…+30 '
                 '(fiziksel kol 0…60) arasında olmalı.',
    'BAD_SPEED': 'Tilt jog hızı 100, 400 veya 800 olmalı.',
    'BAD_CAL_POINT': 'Tilt kalibrasyon noktası reddedildi.',
    'CAL_SAVE_FAILED': 'Tilt kalibrasyonu kartın belleğine yazılamadı. Kontrol kapatıldı.',
    'LINE_TOO_LONG': 'Tilt seri komutu bozuldu. Bağlantı yenileniyor.',
    'OTHER_PORT_ACTIVE': 'Tilt kartı başka bir uygulamada açık (keyboard_control.py?). Onu kapat.',
    'PULSE_RANGE': 'Tilt darbe sayacı aralık dışına çıktı.',
    'UNKNOWN_COMMAND': 'Tilt kartı komutu tanımadı (firmware sürümü eski olabilir).',
    'ESTOP': 'Kart ACİL DURDURMADA — hareket ve ateş reddedildi (DEVAM ET gerekir).',
    'LASER_PWM': 'Kart lazer PWM\'ini kuramadı (GPIO 18) — lazer ÇALIŞMAZ.',
    'BAD_POWER': 'Lazer gücü %0–100 arasında olmalı.',
}


class MockTiltKart:
    """Donanimsiz uctan uca test icin sahte kart (motion_core.h davranisini taklit eder).

    Kapsadigi davranislar — hepsi gercek takip dongusunu etkiler:
      * E/D/X/H/G/V komutlari ve OK/ERR yanitlari
      * silahlandirma kapisi (armed) ve 350 ms canlilik zaman asimi
      * kalibrasyon kapisi (kalibre degilse G reddedilir)
      * TEK BEKLEME YUVASI: hareket halindeyken gelen G, once mevcut hedefe
        gidilip sonra uygulanir — takip mantigimizin asil sinavi budur
      * 100 ms'de bir STATE3 yayini

    Kapsamayan: ivme profili (sabit hizla ilerler) ve gercek mekanik gecikme.
    Zamanlama olcumleri icin degil, MANTIK testi icindir.
    """

    # 60 derecelik kol hareketinin darbe karsiligi. Gercekte KALIBRASYONDAN gelir
    # (mekanizma dogrusal degil); burada yalnizca mock'un ne kadar surede
    # ilerleyecegini belirler.
    UST_DARBE = 6400
    MAKS_HIZ = 3200.0       # darbe/s — MotionCore::MAX_SPEED_VARSAYILAN

    def __init__(self, kalibre=True, simdi=None, yeniden_planlama=False):
        # yeniden_planlama=True: yeni firmware (Q'ya OK der, hareket halinde yeni
        # hedefi durmadan uygular). False: eski firmware (tek bekleme yuvasi).
        self.yeniden_planlama = yeniden_planlama
        self.pos = 0
        self.hedef = 0
        self.acik = False
        self.bekleyen = None
        self.jog = 400
        self.maks_hiz = self.MAKS_HIZ      # Z komutuyla degisir
        self.ivme = 12800.0                # ACCEL_VARSAYILAN (mock ivmeyi UYGULAMAZ)
        self.kalibre = kalibre
        # Pan ekseni (yeni firmware). pan_destek=False eski firmware'i taklit eder.
        self.pan_destek = True
        self.pan_pos = 0
        self.pan_hedef = 0
        self.pan_maks_hiz = 30.0 * PAN_DARBE_DER
        # Yorunge kipi (Y/PY). yorunge_destek=False eski firmware'i taklit eder.
        self.yorunge_destek = True
        self.yor_tilt = None        # (darbe, darbe/sn, t0)
        self.yor_pan = None
        self.son_canli = simdi if simdi is not None else time.time()
        self.t = self.son_canli
        self.kayit = []             # gonderilen komutlar (test icin)
        # Lazer + acil (yeni firmware). lazer_destek=False eski firmware'i taklit eder.
        self.lazer_destek = True
        self.lazer_acik = False
        self.lazer_guc = 40
        self.son_ates = self.t
        self.acil = False
        self.buton = False
        self.metin = []             # kartin kendiliginden yazdigi satirlar (ilerlet'te cikar)

    # --- kalibrasyon tablosu (dogrusal varsayim; mock icin yeterli) ---
    def _aci(self, darbe):
        return darbe * KOL_MAX / self.UST_DARBE

    def _darbe(self, aci):
        return int(round(aci * self.UST_DARBE / KOL_MAX))

    def islet(self, satir, simdi=None):
        """Bir komut satirini isler; kartin yazacagi yaniti (yoksa None) doner."""
        simdi = self.t if simdi is None else simdi
        s = satir.strip()
        self.kayit.append(s)
        self._watchdog(simdi)
        if self.lazer_destek:
            cevap = self._lazer_islet(s, simdi)
            if cevap is not False:
                return cevap
        if s == "YQ":
            return "OK,YQ" if self.yorunge_destek else "ERR,YQ,UNKNOWN_COMMAND"
        if s.startswith("Y") and self.yorunge_destek:
            if not self.acik:
                return f"ERR,{s},DISARMED"
            try:
                a, v = map(float, s[1:].split(","))
            except ValueError:
                return f"ERR,{s},BAD_ANGLE"
            if not 0 <= a <= KOL_MAX:
                return f"ERR,{s},BAD_ANGLE"
            self.hedef, self.bekleyen = self.pos, None
            self.yor_tilt = (self._darbe(a), v * self.UST_DARBE / KOL_MAX, simdi)
            return None                          # firmware Y'ye yanit YAZMAZ
        if s.startswith("PY") and self.yorunge_destek and self.pan_destek:
            if not self.acik:
                return f"ERR,{s},DISABLED"
            try:
                a, v = map(float, s[2:].split(","))
            except ValueError:
                return f"ERR,{s},BAD_ANGLE"
            self.pan_hedef = self.pan_pos
            self.yor_pan = (a * PAN_DARBE_DER, v * PAN_DARBE_DER, simdi)
            return None
        # Firmware: H/Q disindaki her tilt komutu tilt yorungesini, her pan komutu pan
        # yorungesini keser; X/D ikisini birden.
        if s.startswith("P"):
            self.yor_pan = None
        elif s not in ("H", "Q"):
            self.yor_tilt = None
            if s in ("X", "D"):
                self.yor_pan = None
        if s.startswith("P") and self.pan_destek:
            return self._pan_islet(s)
        if s == "X":
            self.hedef = self.pos
            self.bekleyen = None
            self.pan_hedef = self.pan_pos
            return "OK,X"
        if s == "D":
            self.hedef = self.pos
            self.bekleyen = None
            self.pan_hedef = self.pan_pos
            self.acik = False
            return "OK,D"
        if s == "E":
            self.hedef = self.pos
            self.bekleyen = None
            self.acik = True
            self.son_canli = simdi
            return "OK,E"
        if s == "H":
            if self.acik:
                self.son_canli = simdi
            return None                     # firmware H'ye yanit YAZMAZ
        if s == "Q":
            return "OK,Q" if self.yeniden_planlama else "ERR,Q,UNKNOWN_COMMAND"
        if s == "R":
            # Firmware: hareket halindeyse reddet; degilse sayac 0, kalibrasyon korunur.
            if self.pos != self.hedef:
                return "ERR,R,STOP_FIRST"
            self.pos = self.hedef = 0
            self.bekleyen = None
            return "OK,R"
        if s.startswith("Z"):
            # Firmware'de Z, silahlandirma kapisinin ONUNDEDIR (V gibi).
            if self.pos != self.hedef:
                return f"ERR,{s},STOP_FIRST"
            try:
                h_s, iv_s = s[1:].split(",", 1)
                h, iv = float(h_s), float(iv_s)
            except ValueError:
                return f"ERR,{s},BAD_SPEED"
            if not (HIZ_TABAN <= h <= HIZ_TAVAN and IVME_TABAN <= iv <= IVME_TAVAN):
                return f"ERR,{s},BAD_SPEED"
            self.maks_hiz, self.ivme = h, iv
            return f"OK,{s}"
        if not self.acik:
            return f"ERR,{s},DISARMED"
        if s.startswith("V"):
            if self.pos != self.hedef:
                return f"ERR,{s},STOP_FIRST"
            try:
                v = int(s[1:])
            except ValueError:
                return f"ERR,{s},BAD_SPEED"
            if v not in JOG_HIZLAR:
                return f"ERR,{s},BAD_SPEED"
            self.jog = v
            return f"OK,{s}"
        if s.startswith("G"):
            try:
                a = float(s[1:])
            except ValueError:
                return f"ERR,{s},BAD_ANGLE"
            if not math.isfinite(a) or a < KOL_MIN or a > KOL_MAX:
                return f"ERR,{s},BAD_ANGLE"
            if not self.kalibre:
                return f"ERR,{s},CAL_REQUIRED"
            self.son_canli = simdi
            t = self._darbe(a)
            if self.pos != self.hedef and not self.yeniden_planlama:
                self.bekleyen = t           # TEK YUVA — mevcut hedef once bitecek
            else:
                self.hedef = t              # yeni firmware: durmadan yeni hedefe
            return f"OK,{s}"
        return f"ERR,{s},UNKNOWN_COMMAND"

    @staticmethod
    def _hareket_komutu(s):
        """Firmware hareketKomutu() ile ayni: acil kilitte reddedilenler."""
        if s in ("W", "S", "K") or s[:1] in ("G", "C"):
            return True
        if s.startswith("Y"):
            return s != "YQ"
        return s.startswith("P") and len(s) > 1 and (s[1] in "Y-+." or s[1].isdigit())

    def _lazer_islet(self, s, simdi):
        """Lazer/acil komutlari. Doner: yanit (None = sessiz) ya da False (bizim degil)."""
        if s == "STOP":
            self._acil_durdur("(seri STOP)")
            return None
        if s == "START":
            if self.buton:
                self.metin.append("START REDDEDILDI - ACIL STOP BUTONU BASILI (SISTEM DURDURULDU)")
            else:
                self.acil = False
                self.metin.append("SISTEM BASLATILDI")
            return None
        if s == "L0":
            self.lazer_acik = False
            return "OK,L0"
        if s == "L1":
            if self.acil:
                return "ERR,L1,ESTOP"
            if not self.acik:
                return "ERR,L1,DISARMED"
            ilk = not self.lazer_acik
            self.lazer_acik, self.son_ates = True, simdi
            return "OK,L1" if ilk else None
        if s.startswith("LP"):
            try:
                y = int(s[2:])
            except ValueError:
                return f"ERR,{s},BAD_POWER"
            if not 0 <= y <= 100:
                return f"ERR,{s},BAD_POWER"
            self.lazer_guc = y
            return f"OK,{s}"
        if self.acil and self._hareket_komutu(s):
            return f"ERR,{s},ESTOP"
        return False

    def _acil_durdur(self, sebep):
        self.lazer_acik = False
        self.hedef, self.bekleyen = self.pos, None
        self.pan_hedef = self.pan_pos
        self.yor_tilt = self.yor_pan = None
        self.acil = True
        self.metin.append(f"SISTEM DURDURULDU {sebep}")

    def buton_bas(self, basili):
        """Donanim acil stop butonu (test icin). Firmware: basinca kilit; birakinca
        kendiliginden KALKMAZ."""
        if basili and not self.buton:
            self.buton = True
            self._acil_durdur("(ACIL STOP BUTONU)")
        elif not basili and self.buton:
            self.buton = False
            self.metin.append("ACIL STOP BUTONU BIRAKILDI - devam icin START")

    def lzr1(self):
        return (f"LZR1,{int(self.lazer_acik)},{self.lazer_guc},{int(self.acil)},"
                f"{int(self.buton)},1")

    def _pan_islet(self, s):
        """esp32_ws_test.ino:panCommand ile ayni kurallar."""
        if s == "PR":
            if self.pan_pos != self.pan_hedef:
                return "ERR,PR,MOVING"
            self.pan_pos = self.pan_hedef = 0
            return "OK,PR"
        if s.startswith("PZ"):
            try:
                h_s, iv_s = s[2:].split(",", 1)
                h, iv = float(h_s), float(iv_s)
            except ValueError:
                return f"ERR,{s},BAD_PROFILE"
            if self.pan_pos != self.pan_hedef:
                return f"ERR,{s},MOVING"
            if not (HIZ_TABAN <= h <= PAN_HIZ_TAVAN and IVME_TABAN <= iv <= PAN_IVME_TAVAN):
                return f"ERR,{s},BAD_PROFILE"
            self.pan_maks_hiz = h
            return f"OK,{s}"
        if s.startswith("PE"):
            return f"OK,{s}"
        if not self.acik:
            return f"ERR,{s},DISABLED"
        try:
            a = float(s[1:])
        except ValueError:
            return f"ERR,{s},BAD_ANGLE"
        if not math.isfinite(a) or abs(a) > PAN_SINIR:
            return f"ERR,{s},BAD_ANGLE"
        self.pan_hedef = int(round(a * PAN_DARBE_DER))
        return f"OK,{s}"

    def pan1(self):
        return (f"PAN1,{self.pan_pos},{self.pan_hedef},"
                f"{1 if self.pan_pos != self.pan_hedef else 0},"
                f"{self.pan_pos / PAN_DARBE_DER:.3f},{self.pan_hedef / PAN_DARBE_DER:.3f},-1")

    def _watchdog(self, simdi):
        if self.acik and (simdi - self.son_canli) * 1000.0 >= ZAMAN_ASIMI_MS:
            self.hedef = self.pos
            self.bekleyen = None
            self.pan_hedef = self.pan_pos
            self.acik = False
            self.yor_tilt = self.yor_pan = None
        if not self.acik:
            self.lazer_acik = False                 # kilitli kart ates etmez
        if self.lazer_acik and (simdi - self.son_ates) * 1000.0 > 1000.0:
            self.lazer_acik = False                 # olu adam anahtari (1 sn)
            self.metin.append("LAZER KESILDI - tazeleme durdu (olu adam anahtari)")

    @staticmethod
    def _yor_adim(yor, pos, t, azami, alt, ust):
        """Yorunge kipi (kaba): referansa hiz sinirinda yaklas; 150 ms'den eski
        komutta dur. Doner: (yeni_pos, yorunge_hala_aktif_mi)."""
        p0, v0, t0 = yor
        if t - t0 > 0.15:
            return pos, False
        ref = int(round(max(alt, min(ust, p0 + v0 * (t - t0)))))
        yon = 1 if ref > pos else -1
        return pos + yon * min(int(azami), abs(ref - pos)), True

    def ilerlet(self, simdi):
        """Zamani `simdi`ye tasir: motoru hedefe dogru surer, STATE3 satirlarini uretir."""
        satirlar = []
        while self.t < simdi - 1e-9:
            adim = min(0.1, simdi - self.t)     # 100 ms'lik STATE3 periyodu
            self.t += adim
            self._watchdog(self.t)
            if self.acik and self.yor_tilt is not None:
                self.pos, aktif = self._yor_adim(self.yor_tilt, self.pos, self.t,
                                                 self.maks_hiz * adim, 0, self.UST_DARBE)
                self.hedef = self.pos
                if not aktif:
                    self.yor_tilt = None
            if self.acik and self.yor_pan is not None:
                sinir = int(PAN_SINIR * PAN_DARBE_DER)
                self.pan_pos, aktif = self._yor_adim(self.yor_pan, self.pan_pos, self.t,
                                                     self.pan_maks_hiz * adim, -sinir, sinir)
                self.pan_hedef = self.pan_pos
                if not aktif:
                    self.yor_pan = None
            if self.acik and self.pos != self.hedef:
                yon = 1 if self.hedef > self.pos else -1
                git_darbe = int(self.maks_hiz * adim)
                kalan = abs(self.hedef - self.pos)
                self.pos += yon * min(git_darbe, kalan)
            if self.pos == self.hedef and self.bekleyen is not None:
                self.hedef, self.bekleyen = self.bekleyen, None
            if self.acik and self.pan_pos != self.pan_hedef:
                yon = 1 if self.pan_hedef > self.pan_pos else -1
                self.pan_pos += yon * min(int(self.pan_maks_hiz * adim),
                                          abs(self.pan_hedef - self.pan_pos))
            satirlar.append(self.state3())
            if self.pan_destek:
                satirlar.append(self.pan1())
            if self.lazer_destek:
                satirlar.extend(self.metin)
                self.metin.clear()
                satirlar.append(self.lzr1())
        return satirlar

    def state3(self):
        kal = 1 if self.kalibre else 0
        ust = self.UST_DARBE if self.kalibre else 0
        aci = self._aci(self.pos) if self.kalibre else -1.0
        hed = self._aci(self.hedef) if self.kalibre else -1.0
        nokta = 2 if self.kalibre else 1
        son = KOL_MAX if self.kalibre else 0.0
        return (f"STATE3,{self.pos},{self.hedef},{ust},{kal},"
                f"{1 if self.pos != self.hedef else 0},{1 if self.acik else 0},0,"
                f"{aci:.3f},{hed:.3f},{nokta},{son:.3f},{self.jog}")


class TiltSurucu:
    """Tilt kartinin laptop tarafi. Arayuz bunu DOGRUDAN kullanmaz — `kontrol.Kontrol`
    uzerinden konusur (hareketin tek kapisi orasi).

    Kaynak secimi (kontrol.py ile ayni mantik):
        DERINMAVI_TILT=off    -> kapali (varsayilan; tilt eski kartta kalir)
        DERINMAVI_TILT=mock   -> MockTiltKart (donanimsiz test)
        DERINMAVI_TILT=COM3   -> gercek seri port

    Kullanim:
        s = TiltSurucu()
        s.yokla()               # periyodik (250 ms) — okur, canlilik yollar, kuyrugu bosaltir
        s.git(12.5)             # MUTLAK kol acisi
        s.dur()                 # hareketi kes (bekleyeni de iptal eder)
        s.aci                   # kartin BILDIRDIGI aci (None = durum yok)
    """

    def __init__(self, kaynak=None, _saat=time.time):
        self.kaynak = (kaynak or KAYNAK).strip()
        self._saat = _saat
        self.mock = None
        self.seri = None
        self.hata = None
        self.durum = None               # son STATE3 sozlugu
        self.son_durum_t = 0.0
        self.satirlar = []              # kartin yazdigi son metinler (alt cubuk)
        self._yeni = []
        self._rx = ""
        self._bekleyen_hedef = None     # TEK YUVA: "en yenisi kazanir" (bkz. modul basligi)
        self._gonderilen_hedef = None   # karta en son giden aci
        self._son_canli_t = 0.0
        self._ac_denendi_t = 0.0
        self._son_pos = 0
        self._r_t = None                # R gitti, R SONRASI ilk STATE3 henuz gelmedi
        self._r_ok = False              # R'nin OK/ERR yaniti geldi mi
        self.hiz_seviye = HIZ_VARSAYILAN
        self.takip_kipi = False         # otonom takip: ivme TAKIP_IVME ile sinirli
        self._aci_gecmisi = []          # [(zaman, aci), ...] — her STATE3'te bir kayit
        self._gonderilen_hiz = None     # karta en son giden (hiz, ivme) — None = gonderilmedi
        # Karttaki firmware "Z" komutunu tanimiyorsa (eski surum yuklu) hiz kademesi
        # calismaz. Hareketin geri kalani calismaya DEVAM EDER: G/E/H/X/D eski
        # surumde de var. Bu yuzden bu durum bir HATA degil, bir UYARIDIR.
        self.hiz_desteklenmiyor = False
        # Firmware hareket halinde yeni hedefi DURMADAN uygular mi (retarget)?
        # Aciliste "Q" ile sorulur: OK,Q -> True; eski surum UNKNOWN_COMMAND -> False.
        # None = henuz bilinmiyor (o sure eski, guvenli davranis kullanilir).
        self.yeniden_planlama = None
        self._q_soruldu = False
        self.kalibrasyon_uyarildi = False
        # Kart RESET ATTI mi? (bkz. _kart_yaziyor) — arayuz bunu operatore GORUNUR
        # sekilde soylemeli; sessiz kalirsa aci referansi bozulmus olarak devam eder.
        self.kart_resetlendi = False
        # PAN ekseni ayni kartta (yeni firmware PAN1 yayinlar). Eski firmware'de
        # pan_durum hep None kalir ve pan_destekli False olur -> pan eski yola gider.
        self.pan_durum = None
        self.pan_son_t = 0.0
        self._pan_bekleyen = None
        self._pan_gonderilen = None
        self._pan_gonderim_t = 0.0
        self._pan_gonderilen_hiz = None
        self._pan_gecmisi = []          # [(zaman, pan acisi)] — aci_zamaninda'nin pan esi
        # YORUNGE KIPI (Y/PY) destegi: None = henuz sorulmadi, True/False = cevap.
        self.yorunge_destekli = None
        self._yq_soruldu = False
        self._yor_kayit_sayac = 0
        # LAZER (yeni firmware LZR1 yayinlar). Eski firmware'de hep None -> lazer yok.
        self.lazer_durum = None
        self.lazer_son_t = 0.0
        self.lazer_guc_istek = 40
        self._lazer_guc_gonderim_t = 0.0

        if self.kaynak.lower() == "off":
            return
        if self.kaynak.lower() == "mock":
            self.mock = MockTiltKart(simdi=self._saat())
            return
        if self.kaynak.lower() == "auto":
            gunluk = []
            bulunan = otomatik_port_bul(gunluk=gunluk)
            if bulunan is None:
                self.hata = ("Tilt kartı bulunamadı (STATE3 yayını yok). Denenenler: "
                             + ("; ".join(gunluk) if gunluk else "hiç seri port yok"))
                return
            self.kaynak = bulunan       # artik gercek port adi (arayuz bunu gosterir)
        self._ac_seri()

    # ---- KARA KUTU ----
    # Sahada otonom takip sirasinda kart TAMAMEN sustu (STATE3 yok, USB reset'e
    # cevap yok) ve masada 5 dakikalik stres testiyle (komut deseni + sik yon
    # degistiren gercek hareket) yeniden URETILEMEDI. Sebebi tahminle degil kayitla
    # bulmak icin: gercek portta her calistirmada karta giden ve karttan gelen her
    # satir zaman damgasiyla app/loglar/ altina yazilir. Kilitlenme olursa son
    # satirlar, o an ne oldugunu gosterir.
    # STATE3 her 10'da bir yazilir (saniyede 1); dosya saatte ~1-2 MB buyur.
    KARA_KUTU_DIZIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loglar")

    def _kara_kutu_ac(self):
        try:
            os.makedirs(self.KARA_KUTU_DIZIN, exist_ok=True)
            ad = f"tilt_{time.strftime('%Y%m%d_%H%M%S')}_{self.kaynak}.log"
            self.kara_kutu_yolu = os.path.join(self.KARA_KUTU_DIZIN, ad)
            # Satir tamponlu: uygulama coker ya da kapatilirsa son satirlar kaybolmasin.
            self._kara_kutu = open(self.kara_kutu_yolu, "w", encoding="utf-8", buffering=1)
            self._kk_t0 = time.time()
            self._kk_state_sayac = 0
            self._kk_sessiz = False
            self._kara_kutu_yaz("--", f"oturum basladi, port {self.kaynak}")
        except OSError:
            self._kara_kutu = None          # kayit acilamazsa surucu yine calisir

    def _kara_kutu_yaz(self, yon, metin):
        if getattr(self, "_kara_kutu", None) is None:
            return
        try:
            self._kara_kutu.write(f"{time.strftime('%H:%M:%S')} "
                                  f"{time.time() - self._kk_t0:9.3f} {yon} {metin}\n")
        except (OSError, ValueError):
            self._kara_kutu = None

    def _kara_kutu_sessizlik(self):
        """Kart sustugu ANI ve geri geldigi ani kayda gecer."""
        if getattr(self, "_kara_kutu", None) is None or self.durum is None:
            return
        sessiz = not self.taze
        if sessiz != self._kk_sessiz:
            self._kk_sessiz = sessiz
            gecen = self._saat() - self.son_durum_t
            self._kara_kutu_yaz("!!", f"KART SUSTU ({gecen:.2f} sn STATE3 yok)" if sessiz
                                else "kart yeniden konusuyor")

    def _ac_seri(self):
        try:
            import serial              # pyserial — yalniz gercek portta gerekir
            # DTR/RTS KAPALI ACILIR: bircok ESP32-S3 karti port acilinca bu
            # hatlardan RESET atar. Reset, kartin darbe sayacini SIFIRLAR ve
            # firmware "kol fiziksel olarak 0'da" varsayar — kol yukaridayken
            # bu olursa kartin inandigi aci ile gercek aci kalici olarak ayrisir.
            # (ws_motor_test/keyboard_control.py:open_port ayni sebeple boyle yapar.)
            baglanti = serial.Serial(port=None, baudrate=BAUD, timeout=0,
                                     write_timeout=0.05)
            baglanti.dtr = False
            baglanti.rts = False
            baglanti.port = port_adi(self.kaynak)
            baglanti.open()
            baglanti.reset_input_buffer()
            self.seri = baglanti
            self._kara_kutu_ac()
        except Exception as e:
            self.hata = f"Tilt portu açılamadı ({self.kaynak}): {e}"

    # ---- durum ozellikleri ----
    @property
    def bagli(self):
        return self.mock is not None or self.seri is not None

    @property
    def mock_mu(self):
        return self.mock is not None

    @property
    def taze(self):
        """Kart son DURUM_ASIMI_S icinde STATE3 yolladi mi? Yollamadiysa ekrandaki
        her sey bayattir; arayuz 'bağlantı yok' demelidir."""
        return self.durum is not None and (self._saat() - self.son_durum_t) <= DURUM_ASIMI_S

    @property
    def acik(self):
        return bool(self.taze and self.durum["acik"])

    @property
    def kalibre(self):
        return bool(self.taze and self.durum["kalibre"])

    @property
    def hareket(self):
        return bool(self.taze and self.durum["hareket"])

    @property
    def hazir(self):
        """Hareket komutu KABUL EDILIR mi? (bagli + taze durum + acik + kalibre)
        R'den sonra, R SONRASI ilk STATE3 gelene kadar hazir DEGIL (bkz. sifirla)."""
        return bool(self.bagli and self.taze and self.durum["acik"] and self.durum["kalibre"]
                    and not self._r_bekleniyor())

    def _r_bekleniyor(self):
        if self._r_t is None:
            return False
        if self._saat() - self._r_t > R_BEKLEME_S:      # yanit hic gelmedi: kilitte kalma
            self._r_t = None
            return False
        return True

    @property
    def aci(self):
        """Kartin bildirdigi OPERATOR acisi (-30..+30) — komut edilen degil.
        Durum yoksa None.

        Bu, laptopun 'inandigi' aciden farklidir ve arayuzun dikey aci referansi
        BU olmalidir: komut kaybolur/gecikirse fark buradan kapanir."""
        return self.durum["aci"] if (self.taze and self.durum["kalibre"]) else None

    @staticmethod
    def _ara_deger(g, t):
        if t <= g[0][0]:
            return g[0][1]
        if t >= g[-1][0]:
            return g[-1][1]
        for (t0, a0), (t1, a1) in zip(g, g[1:]):
            if t0 <= t <= t1:
                return a0 + (a1 - a0) * (t - t0) / max(1e-9, t1 - t0)
        return g[-1][1]

    def pan_zamaninda(self, t):
        """Pan'in `t` anindaki acisi (PAN1 gecmisinden) — aci_zamaninda'nin pan esi."""
        if not self._pan_gecmisi or not self.pan_destekli:
            return self.pan_aci
        return self._ara_deger(self._pan_gecmisi, t)

    def aci_zamaninda(self, t):
        """Kolun `t` anindaki acisi (STATE3 gecmisinden dogrusal ara deger).

        NEDEN: takip, kameranin gordugu HATAYI kolun acisina ekler. Kare ~60 ms
        gec gelir (olculdu: komut -> goruntu kaymasi ~92 ms, bunun ~30 ms'si kolun
        gorulebilir kadar hareketi). Hata SIMDIKI aciya eklenirse, kolun o arada
        zaten kapattigi kisim IKINCI KEZ sayilir ve kol hedefi asar; kazanc
        arttikca bu salinima doner (gercek kartta kp 0.9'da olculdu). Hata, karenin
        CEKILDIGI andaki aciya eklenirse ayni hata iki kez sayilmaz.
        Gecmis yoksa (eski durum) simdiki aciya doner."""
        g = self._aci_gecmisi
        if not g or not self.taze:
            return self.aci
        if t <= g[0][0]:
            return g[0][1]
        if t >= g[-1][0]:
            return g[-1][1]
        for (t0, a0), (t1, a1) in zip(g, g[1:]):
            if t0 <= t <= t1:
                return a0 + (a1 - a0) * (t - t0) / max(1e-9, t1 - t0)
        return g[-1][1]

    @property
    def hedef_aci(self):
        return self.durum["hedef"] if (self.taze and self.durum["kalibre"]) else None

    @property
    def darbe_per_derece(self):
        """Kalibrasyondan turer: ust sinir darbesi / 60 derece. Mekanizma yeniden
        kalibre edilirse hiz kademeleri KENDILIGINDEN dogru kalir."""
        if not (self.taze and self.durum["kalibre"]) or self.durum["upper"] <= 0:
            return None
        return self.durum["upper"] / KOL_MAX

    def hiz_ayarla(self, seviye):
        """Hiz kademesini secer (Z komutu). Kart mesgul/hazir degilse BEKLETILIR.

        Kademe DERECE cinsinden tanimlidir; darbeye burada, kartin bildirdigi
        kalibrasyona gore cevrilir."""
        self.hiz_seviye = seviye if seviye in HIZ_TABLO else HIZ_VARSAYILAN
        self._hiz_bosalt()
        return self.hiz_seviye

    def takip_kipi_ayarla(self, acik):
        """Otonom takip acik/kapali: iki eksenin ivmesi TAKIP_IVME / PAN_TAKIP_IVME ile
        sinirlanir (tepe hiz kademeninki). Profil kart dururken gider (Z/PZ kurali)."""
        self.takip_kipi = bool(acik)
        self._hiz_bosalt()
        self._pan_hiz_bosalt()
        return self.takip_kipi

    def profil(self):
        """Tilt'e su an istenen (hiz, ivme) — derece cinsinden."""
        p = HIZ_TABLO[self.hiz_seviye]
        return takip_profili(p, TAKIP_IVME) if self.takip_kipi else p

    def pan_profil(self):
        p = PAN_HIZ_TABLO[self.hiz_seviye]
        return takip_profili(p, PAN_TAKIP_IVME) if self.takip_kipi else p

    def _hiz_bosalt(self):
        """Secili kademeyi, kart uygun durumdayken karta bildirir.

        Firmware Z'yi yalnizca DURURKEN kabul eder (hareket ortasinda profil
        degistirmek rampayi tutarsiz birakir), bu yuzden gonderim ertelenebilir."""
        if self.hiz_desteklenmiyor or not self.hazir or self.durum["hareket"]:
            return False
        dpd = self.darbe_per_derece
        if dpd is None:
            return False
        der_hiz, der_ivme = self.profil()
        cift = (round(der_hiz * dpd, 1), round(der_ivme * dpd, 1))
        if cift == self._gonderilen_hiz:
            return False
        self._gonderilen_hiz = cift
        self._yaz(hiz_profili(*cift))
        return True

    def ozet(self):
        """Alt cubugun gosterecegi ozet (None = kart kapali)."""
        if not self.bagli:
            return None
        if not self.taze:
            ad, renk = "bağlantı yok", "kotu"
        elif not self.durum["kalibre"]:
            ad, renk = "KALİBRE DEĞİL", "kotu"
        elif not self.durum["acik"]:
            ad, renk = "kilitli", "uyari"
        elif self.durum["hareket"]:
            ad, renk = "hareket", "iyi"
        else:
            ad, renk = "hazır", "iyi"
        return {"ad": ad, "renk": renk, "aci": self.aci, "hedef": self.hedef_aci,
                "kalibre": self.kalibre, "acik": self.acik, "hareket": self.hareket,
                "mock": self.mock_mu, "kaynak": self.kaynak,
                "kart_satir": self.satirlar[-1] if self.satirlar else ""}

    # ---- alt seviye ----
    def _yaz(self, satir):
        if self.mock is not None:
            cevap = self.mock.islet(satir, self._saat())
            if cevap:
                self._kart_yaziyor(cevap)
            return True
        if self.seri is None:
            return False
        # H her 120 ms gider; kayda yazilsa dosyanin cogu H olurdu ve asil olaylar
        # kaybolurdu. Yazma HATASI ise her zaman kaydedilir (asagida).
        if satir.startswith(("Y", "PY")) and not satir.startswith("YQ"):
            # 25-50 Hz'lik yorunge komutlari kaydi bogmasin: saniyede ~1 tanesi yazilir.
            self._yor_kayit_sayac += 1
            if self._yor_kayit_sayac % 25 == 1:
                self._kara_kutu_yaz(">>", satir.strip())
        elif satir != CANLI:
            self._kara_kutu_yaz(">>", satir.strip())
        try:
            veri = satir.encode("ascii")
            if self.seri.write(veri) != len(veri):
                raise OSError("Eksik seri yazma")
            return True
        except Exception as e:
            self.hata = f"Tilt seri iletişim hatası: {e}"
            self._kara_kutu_yaz("!!", f"YAZMA HATASI ({satir.strip()}): {e}")
            return False

    def _kart_yaziyor(self, s, t=None):
        """t: satirin karttan GELDIGI tahmini an (verilmezse simdi)."""
        if t is None:
            t = self._saat()
        if s.startswith("LZR1,"):
            lz = lazer_durum_coz(s)
            if lz is not None:
                if self.lazer_durum is None or lz["acil"] != self.lazer_durum["acil"] \
                        or lz["buton"] != self.lazer_durum["buton"]:
                    self._kara_kutu_yaz("<<", s)
                self.lazer_durum = lz
                self.lazer_son_t = self._saat()
            return
        if s.startswith("PAN1,"):
            p = pan_durum_coz(s)
            if p is not None:
                # KART RESETI pan sayacindan da yakalanir: kol 0'dayken reset olursa
                # tilt dedektoru (STATE3 pos 20+ -> 0) hicbir sey gormez, ama pan
                # sayaci da 0'a dondu ve namlu yana bakiyorsa referans kaymistir.
                # PR (pan sifirla) kontrol ACIKKEN gelir; reset ise kontrolu kapatir.
                if (p["pos"] == 0 and abs(getattr(self, "_son_pan_pos", 0)) > 20
                        and self.durum is not None and not self.durum["acik"]):
                    self.kart_resetlendi = True
                    self._pan_bekleyen = None
                    self._pan_gonderilen = None
                    self._pan_gonderilen_hiz = None
                self._son_pan_pos = p["pos"]
                self.pan_durum = p
                self.pan_son_t = t
                self._pan_gecmisi.append((self.pan_son_t, p["aci"]))
                del self._pan_gecmisi[:-150]
            return
        self.durum_satiri = s
        if s.startswith("STATE3,"):
            self._kk_state_sayac = getattr(self, "_kk_state_sayac", 0) + 1
            if self._kk_state_sayac % 50 == 0:           # 50 Hz yayinda saniyede bir
                self._kara_kutu_yaz("<<", s)
        else:
            self._kara_kutu_yaz("<<", s)
        if self._r_t is not None:
            if s == "OK,R" or s.startswith("ERR,R,"):
                self._r_ok = True
            elif s.startswith("STATE3,"):
                if not self._r_ok:
                    # R'den ONCE yazilmis durum (tamponda bekliyordu): ESKI sayac. Alinsaydi
                    # hedef "zaten orada" diye atilir, sonraki 0 sayac da kart reseti sanilirdi.
                    self.son_durum_t = t
                    return
                self._r_t = None
        d = durum_coz(s)
        if d is not None:
            # ⚠ KART RESET ATTI MI? Firmware her acilista darbe sayacini 0 kabul eder
            # ve "kol fiziksel olarak en asagidaki 0 konumunda" VARSAYAR. Kol
            # yukaridayken reset olursa (besleme dalgalanmasi, reset dugmesi, USB
            # yeniden numaralandirma) kartin inandigi aci ile GERCEK aci kalici
            # olarak ayrisir — ve bunun hicbir dis belirtisi yoktur: kart sakin
            # sakin yanlis aciyi bildirir, arayuz de onu gosterir.
            # Imza: sayac 0'a dondu VE kontrol kapali (acilis hali). Canlilik
            # zaman asiminda da kontrol kapanir ama sayac KORUNUR — ikisi bu
            # sekilde ayrilir.
            if d["pos"] == 0 and not d["acik"] and self._son_pos > 20:
                self.kart_resetlendi = True
                self._bekleyen_hedef = None     # eski hedef artik anlamsiz referansta
                self._gonderilen_hedef = None   # ... kilit acilinca yeniden de gonderilmemeli
                # Kart acilis degerlerine dondu: hiz profili yeniden bildirilmeli,
                # yoksa kol sessizce firmware varsayilaninda kalir.
                self._gonderilen_hiz = None
                self._q_soruldu = False
                self.yeniden_planlama = None
                self._yq_soruldu = False
                self.yorunge_destekli = None
                # Pan sayaci da 0'dan basladi (acilis konumu = 0).
                self._pan_bekleyen = None
                self._pan_gonderilen = None
                self._pan_gonderilen_hiz = None
            self._son_pos = d["pos"]
            self.durum = d
            self.son_durum_t = t
            if d["kalibre"]:
                self._aci_gecmisi.append((self.son_durum_t, d["aci"]))
                del self._aci_gecmisi[:-150]           # 50 Hz'de ~3 sn
            return
        self.satirlar.append(s)
        self._yeni.append(s)
        del self.satirlar[:-20]
        if s == "OK,YQ":
            self.yorunge_destekli = True
            return
        if s.startswith("ERR,YQ,"):
            self.yorunge_destekli = False       # eski firmware: konum kipiyle devam, HATA DEGIL
            return
        if s == "OK,Q":
            self.yeniden_planlama = True
            return
        if s.startswith("ERR,"):
            sebep = s.split(',')[-1]
            if s.startswith("ERR,Q,"):
                self.yeniden_planlama = False       # eski firmware: hata DEGIL
                return
            # ESKI FIRMWARE: "Z" komutu yok. Hiz kademesi calismaz ama hareketin
            # geri kalani calisir (G/E/H/X/D eski surumde de var). Bir kez soylenir
            # ve bir daha DENENMEZ — yoksa her kademe degisiminde ayni hata dusuerdi.
            if s.startswith("ERR,R,") and sebep == "UNKNOWN_COMMAND":
                self.hata = ("Karttaki firmware sıfırlamayı (R) tanımıyor — eski sürüm. "
                             "Kol en alttayken ESP'nin USB'sini çekip tak; ya da "
                             "ws_motor_test/esp32_ws_test'i yeniden yükle.")
                return
            if s.startswith("ERR,Z") and sebep == "UNKNOWN_COMMAND":
                self.hiz_desteklenmiyor = True
                self._gonderilen_hiz = None
                self.hata = ("Karttaki firmware hız komutunu (Z) tanımıyor — eski sürüm. "
                             "Hareket çalışır ama hız kademesi etkisizdir. "
                             "ws_motor_test/esp32_ws_test yeniden yüklenmeli.")
                return
            self.hata = HATALAR.get(sebep, f"Tilt kartı hatası: {sebep}")

    def _oku(self):
        if self.mock is not None:
            for s in self.mock.ilerlet(self._saat()):
                self._kart_yaziyor(s)
            return
        if self.seri is None:
            return
        try:
            n = self.seri.in_waiting
            if n:
                self._rx += self.seri.read(n).decode("ascii", "replace")
        except Exception as e:
            self.hata = f"Tilt seri iletişim hatası: {e}"
            return
        satirlar = []
        while "\n" in self._rx:
            satir, self._rx = self._rx.split("\n", 1)
            satir = satir.strip()
            if satir:
                satirlar.append(satir)
        # ZAMAN DAMGASI: okuma aralikli yapilir (arayuz zamanlayicisi), bir okumada
        # birkac durum paketi birikmis olabilir. Hepsine "simdi" demek aci gecmisini
        # okuma araligi kadar (100 ms'de 0-100 ms) GEC gosterir; surekli takip kareyi
        # yanlis aciyla esler ve duran hedefte salinir (benzetim: 40 ms hata -> 64 yon
        # degisimi). Kart STATE3'u 20 ms'de bir yollar: paketler geriye dogru o
        # aralikla dagitilir (PAN1 kendi STATE3'uyle ayni ani paylasir).
        simdi = self._saat()
        kalan = sum(1 for x in satirlar if x.startswith("STATE3,"))
        for satir in satirlar:
            if satir.startswith("STATE3,"):
                kalan -= 1
            self._kart_yaziyor(satir, simdi - DURUM_PERIYODU_S * max(0, kalan))
        if len(self._rx) > 8192:            # bozuk akis: tamponu buyutmeye devam etme
            self._rx = ""

    # ---- yuksek seviye ----
    def yokla(self):
        """Periyodik nabiz (arayuzde 250 ms'lik esp_timer'dan cagrilir).

        Uc is yapar, SIRASI onemlidir:
          1. Karttan geleni oku   -> `durum` tazelensin
          2. Canlilik yolla       -> 350 ms sessizlikte kart KENDINI kilitler
          3. Bekleyen hedefi gonder (kart bostaysa) -> bkz. _bosalt

        Kart kilitliyse (armed=0) KENDILIGINDEN yeniden acilir: arayuz bir kare
        gecikmeden donmus olabilir, operatorun her seferinde dugmeye basmasi
        beklenmemeli. E komutu `stop()` cagirir, yani konum KORUNUR - sifirlanmaz.
        """
        if not self.bagli:
            return None
        self._oku()
        simdi = self._saat()
        if (simdi - self._son_canli_t) * 1000.0 >= CANLILIK_MS:
            self._yaz(CANLI)
            self._son_canli_t = simdi
        # Kart kilitliyse tekrar ac (saniyede en fazla ~3 deneme; hatta komut yagdirma)
        if self.taze and not self.durum["acik"] and (simdi - self._ac_denendi_t) > 0.3:
            self._ac_denendi_t = simdi
            self._yaz(AC)
            # Canlilik asimi hareketi YARIDA keser (kart hedefi o anki konuma ceker); arayuz
            # hedefi gonderdi sanir, bir daha gondermez. 24.09 saha: acilis yukselisi 30
            # yerine ~10 derecede kaldi. Son konum hedefi yeniden kuyruga (yorunge, dur() ve
            # kart reseti onu zaten siler; kol oradaysa _bosalt gondermez).
            if self._bekleyen_hedef is None and self._gonderilen_hedef is not None:
                self._bekleyen_hedef = self._gonderilen_hedef
                self._gonderilen_hedef = None
        if self.hazir and not self._yq_soruldu:
            self._yq_soruldu = True
            self._yaz(YORUNGE_SORGU)
        if self.hazir and not self._q_soruldu:
            self._q_soruldu = True
            self._yaz(SORGU)
        # Hiz profili HEDEFTEN ONCE gider: hedef once gonderilirse kart hareketi
        # eski profille baslatir ve Z artik "hareket halinde" diye reddedilir.
        self._hiz_bosalt()
        self._bosalt()
        self._pan_hiz_bosalt()
        self._pan_bosalt()
        self._lazer_guc_bosalt()
        self._oku()
        self._kara_kutu_sessizlik()
        return self.ozet()

    def git(self, derece):
        """MUTLAK operator acisi komutu (-30..+30). Ham karta fiziksel kol
        acisi (0..60) gider. Kart mesgulse PC tarafinda BEKLETILIR.

        Dondurur: karta o an GIDEN aci, ya da kuyruga alindiysa None.

        Neden dogrudan gondermiyoruz: firmware'in tek bekleme yuvasi BAYAT hedefi
        once uygular (modul basligindaki uyari). Burada bekletirsek karta her
        zaman EN TAZE hedef gider — arayuz kare hizinda komut uretse bile."""
        if not self.bagli:
            return None
        hedef = aci_kirp(derece)
        self._bekleyen_hedef = hedef
        return self._bosalt()

    def _bosalt(self):
        """Bekleyen hedefi, kart uygun durumdaysa gonderir.

        Gondermeme sebepleri (hepsi normaldir, hata degildir):
          * durum bayat        -> kartin nerede oldugunu bilmiyoruz
          * kilitli/kalibresiz -> kart zaten reddeder, hattı mesgul etmeyelim
          * HAREKET HALINDE    -> bekle; bu sirada gelen daha taze hedef bunu ezer
          * aci zaten ayni     -> gereksiz komut yok
        """
        if self._bekleyen_hedef is None or not self.hazir:
            return None
        # ESKI FIRMWARE: hareket halindeyken gelen hedef once eski hedefe gidip
        # DURMAYA yol acar; kart bosalana kadar beklenir (tek yuvali kuyruk).
        # YENI FIRMWARE (retarget): hedef hareket halinde DURMADAN uygulanir —
        # beklemek tam da giderilen dur-kalk titremesini geri getirirdi.
        if self.durum["hareket"] and not self.yeniden_planlama:
            return None
        hedef = self._bekleyen_hedef
        # Kartin BILDIRDIGI aciya yeterince yakinsak komut gonderme. Esik kartin
        # kendi cozunurlugunun (darbe basina aci) altina inmemeli; 0.05 derece
        # 6400 darbe/60 derece'de ~5 darbedir.
        simdiki = self.durum["aci"]
        if simdiki is not None and abs(hedef - simdiki) < 0.05:
            self._bekleyen_hedef = None
            return None
        # AYNI HEDEF, KART HENUZ CEVAP VERMEDI: tekrar gonderme. Kart "hareket
        # ediyorum" diyene kadar (sonraki STATE3, en fazla 100 ms) durum hala
        # "bos" gorunur; bu arada gelen her git() ayni G'yi yeniden yollardi.
        # Kara kutuda goruldu: 100 ms'de 10 adet ayni "G0.0000".
        if (self._gonderilen_hedef is not None
                and abs(hedef - self._gonderilen_hedef) < 0.05
                and (self.durum["hareket"]
                     or self.son_durum_t <= getattr(self, "_gonderim_t", 0.0))):
            self._bekleyen_hedef = None
            return None
        self._bekleyen_hedef = None
        self._gonderilen_hedef = hedef
        self._gonderim_t = self._saat()
        self._yaz(git(hedef))
        return hedef

    def sifirla(self):
        """R: "kol SU AN fiziksel olarak en altta" — kartin darbe sayacini 0 yapar.

        Kalibrasyon tablosu SILINMEZ. Neden gerekli: kart kolun yerini OLCMEZ,
        gonderdigi darbeleri sayar. Motor beslemesi kesilince kol yer cekimiyle
        duser ama USB'den beslenen ESP32 eski sayida kalir. Sahada: kol en
        alttayken kart 20 derece diyordu ve her komut kolu alt dayamaya bastirdi.

        YALNIZ kol gercekten en alttayken cagrilmali — yanlis anda cagrilirsa
        referansi bu sefer ters yonde bozar."""
        if not self.bagli:
            return False
        self._bekleyen_hedef = None
        self._gonderilen_hedef = None
        # Sayac 0'a donecek; bu bir KART RESETI degildir, reset dedektoru susturulur.
        self._son_pos = 0
        # R SONRASI ilk STATE3'e kadar eldeki durum ESKIDIR (24.09 saha: kart 30 derecede
        # kalmisti; R'nin ardindan G30 eski "30" durumuna bakip "zaten orada" diye atildi,
        # kol hic kalkmadi). O zamana kadar hazir=False, hedef bekler.
        self._r_t = self._saat()
        self._r_ok = False
        return self._yaz("R\n")

    # ---- PAN (ayni kart) ----
    @property
    def pan_destekli(self):
        """Karttaki firmware pan'i suruyor mu? (taze PAN1 yayini var mi)"""
        return (self.bagli and self.pan_durum is not None
                and (self._saat() - self.pan_son_t) <= DURUM_ASIMI_S)

    @property
    def pan_aci(self):
        """Kartin BILDIRDIGI pan acisi (darbe sayimindan) — yoksa None."""
        return self.pan_durum["aci"] if self.pan_destekli else None

    def pan_git(self, derece):
        """MUTLAK, SARMASIZ pan acisi. Firmware hareket halinde durmadan yeniden
        planlar (PanCore::retarget), bu yuzden hedef bekletilmeden gider; yalniz
        kart kilitliyse/durum bayatsa bir sonraki yoklamaya kalir."""
        if not self.bagli:
            return None
        self._pan_bekleyen = pan_kirp(derece)
        return self._pan_bosalt()

    def _pan_bosalt(self):
        if self._pan_bekleyen is None or not self.pan_destekli:
            return None
        if not (self.taze and self.durum["acik"]):
            return None
        hedef = self._pan_bekleyen
        p = self.pan_durum
        if not p["hareket"] and abs(hedef - p["aci"]) < 0.02:
            self._pan_bekleyen = None
            return None
        # Ayni hedef zaten gitti ve kart henuz yeni PAN1 yollamadi: tekrar yollama.
        if (self._pan_gonderilen is not None and abs(hedef - self._pan_gonderilen) < 0.02
                and (p["hareket"] or self.pan_son_t <= self._pan_gonderim_t)):
            self._pan_bekleyen = None
            return None
        self._pan_bekleyen = None
        self._pan_gonderilen = hedef
        self._pan_gonderim_t = self._saat()
        self._yaz(pan_git(hedef))
        return hedef

    def _pan_hiz_bosalt(self):
        """Pan hiz kademesini (PZ) kart dururken bildirir; tilt ile ayni kademe."""
        if not self.pan_destekli or self.pan_durum["hareket"]:
            return False
        h, iv = self.pan_profil()
        cift = (round(h * PAN_DARBE_DER, 1), round(iv * PAN_DARBE_DER, 1))
        if cift == self._pan_gonderilen_hiz:
            return False
        self._pan_gonderilen_hiz = cift
        self._yaz(pan_profili(*cift))
        return True

    def yorunge(self, derece, hiz):
        """Tilt YORUNGE komutu (otonom takip). Konum kipinin kuyrugu/tekrar-bastirmasi
        burada YOK: kart referansi kendisi ilerlettigi icin her komut gitmeli, ayni
        komut bile (150 ms'de bir gelmezse kart durur)."""
        if not (self.bagli and self.hazir and self.yorunge_destekli):
            return False
        self._bekleyen_hedef = None
        self._gonderilen_hedef = None
        return self._yaz(yorunge(derece, hiz))

    def pan_yorunge(self, derece, hiz):
        if not (self.bagli and self.pan_destekli and self.yorunge_destekli
                and self.taze and self.durum["acik"]):
            return False
        self._pan_bekleyen = None
        self._pan_gonderilen = None
        return self._yaz(pan_yorunge(derece, hiz))

    def pan_sifirla(self):
        """PR: pan'in SU ANKI konumunu 0 kabul ettir (namlu tam karsiya bakarken)."""
        if not self.pan_destekli:
            return False
        self._pan_bekleyen = None
        self._pan_gonderilen = None
        self._son_pan_pos = 0          # bu bir kart reseti degil
        return self._yaz("PR\n")

    # ---- LAZER + ACIL (tek kart) ----
    @property
    def lazer_destekli(self):
        """Kart lazer suruyor mu? (yeni firmware LZR1 yayini TAZE + PWM kurulmus)"""
        return bool(self.bagli and self.lazer_durum is not None and self.lazer_durum["pwm"]
                    and (self._saat() - self.lazer_son_t) <= LAZER_DURUM_ASIMI_S)

    @property
    def lazer_bilinen(self):
        """Kart bu oturumda en az bir kez LZR1 yolladi mi (kesme komutu ona da gitsin)?"""
        return self.bagli and self.lazer_durum is not None

    def lazer(self, ac):
        """L1 (ac / TAZELE) ya da L0 (kes). Kart kurallari firmware'dedir."""
        if not self.bagli:
            return False
        return self._yaz(LAZER_AC if ac else LAZER_KES)

    def lazer_guc_ayarla(self, yuzde):
        """Istenen gucu saklar; kart LZR1'de farkli guc bildirdikce yeniden yollanir
        (kart resetlenirse de kendiliginden duzelir)."""
        self.lazer_guc_istek = max(0, min(100, int(round(yuzde))))
        self._lazer_guc_gonderim_t = 0.0
        self._lazer_guc_bosalt()

    def _lazer_guc_bosalt(self):
        if not self.lazer_destekli or self.lazer_durum["guc"] == self.lazer_guc_istek:
            return
        simdi = self._saat()
        if simdi - self._lazer_guc_gonderim_t < 0.5:
            return
        self._lazer_guc_gonderim_t = simdi
        self._yaz(lazer_guc(self.lazer_guc_istek))

    def acil(self, aktif):
        """STOP (kart kilitlenir) / START. Kartta lazer yoksa (eski firmware) gonderilmez:
        STOP'u tanimaz ve hata yazardi; hareket orada X ile durdurulur."""
        if not self.lazer_bilinen:
            return False
        if aktif:
            self._bekleyen_hedef = None
            self._pan_bekleyen = None
        return self._yaz(ACIL_DUR if aktif else ACIL_DEVAM)

    def dur(self):
        """Hareketi kes ve bekleyen hedefi iptal et (E-Stop / hedef kaybi).
        Firmware'de X pan'i da durdurur."""
        self._bekleyen_hedef = None
        self._gonderilen_hedef = None   # kesilen hedef kilit acilinca geri gelmesin
        self._pan_bekleyen = None
        if self.bagli:
            self._yaz(DUR)
        return self.ozet()

    def kapat(self, kalici=False):
        """kalici=True: karta D yollar (kontrolu kapatir) ve portu kapatir."""
        if not self.bagli:
            return
        self._bekleyen_hedef = None
        self._yaz(KAPAT if kalici else DUR)
        if kalici and self.seri is not None:
            try:
                self.seri.close()
            except Exception:
                pass
            self._kara_kutu_yaz("--", "oturum kapandi")
            try:
                self._kara_kutu.close()
            except Exception:
                pass
            self._kara_kutu = None

    def yeni_satirlar(self):
        yeni, self._yeni = self._yeni, []
        return yeni


if __name__ == "__main__":
    # ---- port adi: Windows eskisi gibi, Mac/Linux yolunun harfleri korunur ----
    assert port_adi("COM3") == "COM3" and port_adi("com12") == "COM12"   # Windows aynen
    assert port_adi(" com5 ") == "COM5"
    assert port_adi("/dev/cu.usbmodem1101") == "/dev/cu.usbmodem1101", "Mac yolu bozuldu"
    assert port_adi("/dev/ttyUSB0") == "/dev/ttyUSB0"                     # Linux
    assert port_adi("/dev/cu.wchusbserial1420") == "/dev/cu.wchusbserial1420"

    # ---- komut bicimi: kart strtod ile okur, keyboard_control.py ile AYNI bicim ----
    # OPERATOR acisi girer, karta KOL acisi cikar (fark: KULLANICI_SIFIR)
    assert git(12.5) == f"G{12.5 + KULLANICI_SIFIR:.4f}\n"
    assert git(0) == f"G{KULLANICI_SIFIR:.4f}\n", "operator 0 = kolun ORTASI"
    assert git(-500) == f"G{KOL_MIN:.4f}\n" and git(500) == f"G{KOL_MAX:.4f}\n"
    assert aci_kirp(-31) == ACI_MIN == -30.0 and aci_kirp(31) == ACI_MAX == 30.0
    assert kol_karsiligi(ACI_MIN) == KOL_MIN and aci_karsiligi(KOL_MAX) == ACI_MAX
    assert jog_hiz(400) == "V400\n"
    try:
        jog_hiz(123)
        raise AssertionError("gecersiz jog hizi kabul edildi")
    except ValueError:
        pass

    # ---- STATE3 cozumu: ws_motor_test/protocol.py ile AYNI dogrulama ----
    iyi = "STATE3,3200,3200,6400,1,0,1,0,30.000,30.000,2,60.000,400"
    d = durum_coz(iyi)
    assert d and d["kalibre"] and d["acik"] and not d["hareket"], d
    # Kart KOL acisini bildirir (30), surucu OPERATOR acisina cevirir (0)
    assert d["aci"] == 0.0 and d["pos"] == 3200, d
    assert durum_coz("STATE,1,2") is None                      # eski firmware
    assert durum_coz("OK,E") is None
    assert durum_coz(iyi.replace(",400", ",999")) is None       # gecersiz jog hizi
    # kalibre DEGILKEN upper/aci/hedef -1 olmali; dolu gelirse satir bozuktur
    assert durum_coz("STATE3,0,0,0,0,0,1,0,-1.000,-1.000,1,0.000,400") is not None
    assert durum_coz("STATE3,0,0,6400,0,0,1,0,-1.000,-1.000,1,0.000,400") is None
    # kalibreyken kol araligi disinda aci kabul edilmemeli
    assert durum_coz("STATE3,3200,3200,6400,1,0,1,0,61.000,30.000,2,60.000,400") is None

    # ---- mock kart: kapilar ----
    saat = [1000.0]
    s = TiltSurucu("mock", _saat=lambda: saat[0])
    assert s.bagli and s.mock_mu and s.aci is None       # daha hic durum gelmedi

    def tik(sure=0.25):
        """Arayuzdeki 250 ms'lik esp_timer'i taklit eder."""
        saat[0] += sure
        return s.yokla()

    def yerles(azami=80):
        """Kuyruk bosalana VE kart iki ardisik STATE3'te duruyor diyene kadar tik at.

        Neden iki ardisik: kuyruk bosaldigi an gonderilen komut kartta henuz
        yayina donusmemistir (STATE3 100 ms'de bir gelir) — tek 'duruyor'
        okumasiyla yetinen bir dongu, yeni hareket baslamadan once biter."""
        bos = 0
        for _ in range(azami):
            tik()
            bos = bos + 1 if (not s.hareket and s._bekleyen_hedef is None) else 0
            if bos >= 2:
                return True
        return False

    def gonderilen_hedefler():
        # Karta KOL acisi gider; test OPERATOR acisiyla okunsun diye geri cevrilir.
        return [aci_karsiligi(float(k[1:])) for k in s.mock.kayit if k.startswith("G")]

    tik()
    assert s.taze and s.kalibre, s.durum
    # Kart acilista KILITLIDIR; yokla() E yollar ama durum bir sonraki STATE3'te
    # tazelenir (gercek kartta da 100 ms'lik yayin periyodu kadar gecikir).
    assert not s.acik, "acilista kart kilitli olmaliydi"
    tik()
    assert s.acik, "yokla() kilitli karti kendiliginden acmaliydi"

    # 1. MUTLAK aci komutu kartta hedefe donusur (operator 0 = kolun ORTASI)
    s.git(0.0)
    tik()
    assert s.mock.hedef == 3200, s.mock.hedef
    assert s.hareket, "ortaya giderken kart HAREKET halinde olmali"

    # 2. ⭐ ASIL MESELE: hareket halindeyken gelen hedefler KARTA GIRMEZ, en
    #    tazesi beklerAksi halde firmware'in tek yuvasi BAYAT hedefi uygular.
    s.git(-20.0)
    s.git(25.0)
    s.git(-10.0)                     # en tazesi bu
    assert s.mock.bekleyen is None, "karta bayat hedef sizdi"
    assert s._bekleyen_hedef == -10.0

    # 3. Kart bosalinca yalniz EN TAZE hedef gider. Karta giden komutlar tam olarak
    #    [0 (ilk), -10 (en taze)] olmali — arada gelen -20 ve 25 HIC gitmemeli.
    assert yerles(), "kart yerlesmedi"
    assert abs(s.aci - (-10.0)) < 0.5, f"en taze hedefe gidilmedi: {s.aci}"
    assert gonderilen_hedefler() == [0.0, -10.0], gonderilen_hedefler()

    # 4. Olu bolge: ayni aciya tekrar komut gonderilmez
    n = len(gonderilen_hedefler())
    s.git(-10.0)
    tik()
    assert len(gonderilen_hedefler()) == n, "gereksiz komut gitti"

    # 5. Kirpma: kol araligi disi hedef araliga cekilir, kart reddetmez
    s.git(90.0)
    assert yerles(), "kart yerlesmedi"
    assert abs(s.aci - ACI_MAX) < 0.5, s.aci
    assert not any(k.endswith("BAD_ANGLE") for k in s.satirlar), s.satirlar

    # 6. CANLILIK: yokla() durursa kart KENDINI kilitler (guvenlik ozelligi)
    saat[0] += 1.0                    # 1 sn sessizlik — 350 ms asimindan buyuk
    s._oku()
    assert not s.mock.acik, "kart canlilik kesilince kilitlenmeliydi"
    assert not s.hazir, "kilitli kartta hareket komutu kabul edilmemeli"
    tik(); tik()          # E gider, sonraki STATE3'te acik gorunur
    assert s.acik, "yokla() kilidi kendiliginden acmaliydi"

    # 7. Kilitliyken komut kaybolmaz, kart acilinca uygulanir
    saat[0] += 1.0
    s._oku()
    assert not s.mock.acik
    s.git(5.0)
    assert s._bekleyen_hedef == 5.0, "kilitliyken hedef kuyrukta beklemeliydi"
    assert yerles(), "kart yerlesmedi"
    assert abs(s.aci - 5.0) < 0.5, s.aci

    # 8. dur(): bekleyen hedefi de iptal eder (E-Stop yolu)
    s.git(-25.0)
    s.dur()
    assert s._bekleyen_hedef is None
    tik()
    assert s.mock.hedef == s.mock.pos, "dur() hareketi kesmeliydi"

    # 9. KALIBRE DEGIL: hicbir hareket komutu gecmez (mekanigi korur)
    saat[0] += 1.0
    s2 = TiltSurucu("mock", _saat=lambda: saat[0])
    s2.mock.kalibre = False
    saat[0] += 0.25
    s2.yokla()
    assert s2.taze and not s2.kalibre and not s2.hazir
    s2.git(30.0)
    saat[0] += 0.25
    s2.yokla()
    assert not any(k.startswith("G") for k in s2.mock.kayit), "kalibresiz kartta G gitti"

    # 11. ⭐ KART RESET TESPITI. Reset, kolun acisini sessizce yalan soyletir
    #     (firmware "kol 0'da" varsayar); fark edilmezse takip yanlis aciya surer.
    saat[0] += 1.0
    s3 = TiltSurucu("mock", _saat=lambda: saat[0])
    tik3 = lambda: (saat.__setitem__(0, saat[0] + 0.25), s3.yokla())[1]
    tik3(); tik3()
    s3.git(30.0)
    for _ in range(40):
        tik3()
        if not s3.hareket and s3._bekleyen_hedef is None:
            break
    assert s3._son_pos > 20 and not s3.kart_resetlendi, s3._son_pos

    # 11a. Canlilik zaman asimi RESET DEGILDIR: kontrol kapanir ama sayac korunur.
    saat[0] += 1.0
    s3._oku()
    assert not s3.mock.acik and not s3.kart_resetlendi, "zaman asimi reset sayildi"

    # 11b. Gercek reset: sayac 0'a dondu + kontrol kapali -> bayrak kalkar,
    #      bekleyen hedef de dusurulur (eski hedef artik bozuk referansa aittir).
    s3._bekleyen_hedef = 45.0
    s3.mock.pos = s3.mock.hedef = 0
    s3.mock.acik = False
    tik3()
    assert s3.kart_resetlendi, "kart reseti yakalanmadi"
    assert s3._bekleyen_hedef is None, "reset sonrasi bayat hedef kuyrukta kaldi"

    # 10. kapali kaynak: her cagri sessizce yutulur (arayuz kosul yazmak zorunda kalmasin)
    kapali = TiltSurucu("off")
    assert not kapali.bagli and kapali.ozet() is None
    assert kapali.git(30.0) is None and kapali.yokla() is None
    kapali.dur(); kapali.kapat()

    # 14. HIZ KADEMESI (Z komutu) — kademeler DERECE, karta DARBE gider
    #     GERCEK kalibrasyonla denenir (olculen: 60 derece = 2675 darbe). Mock'un
    #     kaba varsayilaniyla (6400) Hizli kademesi firmware tavanina carpar ve
    #     test gercekte olmayan bir kirpmayi olcerdi.
    _eski_ust_darbe = MockTiltKart.UST_DARBE
    MockTiltKart.UST_DARBE = 2675
    saat[0] += 1.0
    h = TiltSurucu("mock", _saat=lambda: saat[0])
    tikh = lambda: (saat.__setitem__(0, saat[0] + 0.25), h.yokla())[1]
    tikh(); tikh()
    assert h.hazir and abs(h.darbe_per_derece - MockTiltKart.UST_DARBE / KOL_MAX) < 1e-9
    dpd = h.darbe_per_derece

    # 14a. Acilista varsayilan kademe kendiliginden bildirilir
    tikh()
    der_h, der_iv = HIZ_TABLO[HIZ_VARSAYILAN]
    assert abs(h.mock.maks_hiz - round(der_h * dpd, 1)) < 0.2, h.mock.maks_hiz
    assert abs(h.mock.ivme - round(der_iv * dpd, 1)) < 0.2, h.mock.ivme

    # 14b. Kademe degisimi karta gider ve DERECE->DARBE cevrimi kalibrasyondan turer
    h.hiz_ayarla(H_HIZLI); tikh()
    der_h, der_iv = HIZ_TABLO[H_HIZLI]
    assert abs(h.mock.maks_hiz - round(der_h * dpd, 1)) < 0.2, h.mock.maks_hiz

    # 14c. Ayni kademe tekrar secilirse komut GITMEZ (hatta gereksiz trafik yok)
    n = len([k for k in h.mock.kayit if k.startswith("Z")])
    h.hiz_ayarla(H_HIZLI); tikh()
    assert len([k for k in h.mock.kayit if k.startswith("Z")]) == n

    # 14c2. YUMUSAK TAKIP (24.09 saha): otonom takipte iki eksenin IVMESI tavanli, tepe hiz
    #       kademeninki; takipten cikinca kademenin kendi ivmesine doner.
    def son_pz_ivme():
        pz = [k for k in h.mock.kayit if k.startswith("PZ")]
        return float(pz[-1][2:].split(",")[1]) if pz else None
    h.hiz_ayarla(H_NORMAL); tikh()
    (th, tiv), (ph, piv) = HIZ_TABLO[H_NORMAL], PAN_HIZ_TABLO[H_NORMAL]
    assert tiv > TAKIP_IVME and piv > PAN_TAKIP_IVME, "kurulum: Normal ivmesi tavanin ustunde olmali"
    h.takip_kipi_ayarla(True); tikh()
    assert abs(h.mock.ivme - round(TAKIP_IVME * dpd, 1)) < 0.2, h.mock.ivme
    assert abs(h.mock.maks_hiz - round(th * dpd, 1)) < 0.2, "takipte tepe hiz degisti"
    assert abs(son_pz_ivme() - round(PAN_TAKIP_IVME * PAN_DARBE_DER, 1)) < 0.2, son_pz_ivme()
    h.takip_kipi_ayarla(False); tikh()
    assert abs(h.mock.ivme - round(tiv * dpd, 1)) < 0.2, "takipten cikinca ivme donmedi"
    assert abs(son_pz_ivme() - round(piv * PAN_DARBE_DER, 1)) < 0.2, son_pz_ivme()
    h.hiz_ayarla(H_YAVAS); h.takip_kipi_ayarla(True); tikh()     # tavan zaten ustte: aynen
    assert abs(h.mock.ivme - round(HIZ_TABLO[H_YAVAS][1] * dpd, 1)) < 0.2, h.mock.ivme
    h.takip_kipi_ayarla(False); h.hiz_ayarla(H_HIZLI); tikh()

    # 14d. Gecersiz kademe varsayilana duser
    assert h.hiz_ayarla(99) == HIZ_VARSAYILAN

    # 14e. ⭐ Z HAREKET ORTASINDA REDDEDILIR; kademe kart durunca uygulanir.
    #      Sira onemli: yokla() once hizi, sonra hedefi gonderir — tersi olsaydi
    #      hareket eski profille baslar ve Z bir daha hic gecmezdi.
    h.hiz_ayarla(H_YAVAS)
    h.git(50.0); tikh()
    assert h.hareket, "hareket baslamaliydi"
    der_h, _ = HIZ_TABLO[H_YAVAS]
    assert abs(h.mock.maks_hiz - round(der_h * dpd, 1)) < 0.2, \
        "yavas kademe hareketten ONCE gitmeliydi"
    assert not any(s.endswith("STOP_FIRST") for s in h.satirlar), h.satirlar

    # 14g. ⭐ ESKI FIRMWARE (Z komutu yok): hareket calismaya devam etmeli, yalniz
    #      hiz kademesi etkisiz kalmali ve bu BIR KEZ soylenmeli. Kullanici
    #      uygulamayi karta yeni firmware yuklemeden acabilir — sik bir durum.
    class _EskiFirmware(MockTiltKart):
        def islet(self, satir, simdi=None):
            s = satir.strip()
            if s.startswith("Z"):
                self.kayit.append(s)
                return f"ERR,{s},UNKNOWN_COMMAND"
            return super().islet(satir, simdi)

    saat[0] += 1.0
    e = TiltSurucu("mock", _saat=lambda: saat[0])
    e.mock = _EskiFirmware(simdi=saat[0])
    tike = lambda: (saat.__setitem__(0, saat[0] + 0.25), e.yokla())[1]
    tike(); tike(); tike()
    assert e.hiz_desteklenmiyor, "eski firmware tespit edilmeliydi"
    assert e.hata and "eski sürüm" in e.hata, e.hata
    n_z = len([k for k in e.mock.kayit if k.startswith("Z")])
    e.hiz_ayarla(H_HIZLI); tike(); tike()
    assert len([k for k in e.mock.kayit if k.startswith("Z")]) == n_z, \
        "eski firmware'e Z gondermeye devam edildi"
    # ...ama HAREKET calismali: G/E/H/X eski surumde de var.
    e.git(20.0)
    for _ in range(60):
        tike()
        if not e.hareket and e._bekleyen_hedef is None:
            break
    assert abs(e.aci - 20.0) < 0.5, f"eski firmware'de hareket bozuldu: {e.aci}"

    # 14f. Kirpma: kaba bir kalibrasyon firmware tavanini astirirsa deger KIRPILIR,
    #      komut reddedilmez (kol yavaslar ama calismaya devam eder).
    assert hiz_profili(99999, 999999) == f"Z{HIZ_TAVAN:.1f},{IVME_TAVAN:.1f}\n"
    assert hiz_profili(1, 1) == f"Z{HIZ_TABAN:.1f},{IVME_TABAN:.1f}\n"
    MockTiltKart.UST_DARBE = 6400          # kaba kalibrasyon: Hizli tavani asar
    saat[0] += 1.0
    hk = TiltSurucu("mock", _saat=lambda: saat[0])
    for _ in range(3):
        saat[0] += 0.25; hk.yokla()
    hk.hiz_ayarla(H_HIZLI)
    saat[0] += 0.25; hk.yokla()
    assert hk.mock.maks_hiz == HIZ_TAVAN, hk.mock.maks_hiz
    assert not any(s.endswith("BAD_SPEED") for s in hk.satirlar), hk.satirlar
    MockTiltKart.UST_DARBE = _eski_ust_darbe

    # 15. AYNI HEDEF, KART HENUZ CEVAP VERMEDEN tekrar gonderilmez (kara kutuda
    #     100 ms'de 10 adet ayni G goruldu). Kart durum bildirdikten sonra —
    #     ornegin komut reddedildiyse — ayni hedef yeniden gonderilebilir.
    saat[0] += 1.0
    d = TiltSurucu("mock", _saat=lambda: saat[0])
    for _ in range(3):
        saat[0] += 0.25; d.yokla()
    n0 = len([k for k in d.mock.kayit if k.startswith("G")])
    for _ in range(10):
        d.git(40.0)                      # ayni an, STATE3 araya girmeden
    assert len([k for k in d.mock.kayit if k.startswith("G")]) == n0 + 1, d.mock.kayit[-5:]

    # 16. ⭐ SIFIRLAMA (R). Sahada: kol en alttayken kart 20 derece sandi (motor
    #     beslemesi kesilince kol dustu, USB'den beslenen ESP32 eski sayida kaldi).
    saat[0] += 1.0
    z = TiltSurucu("mock", _saat=lambda: saat[0])
    for _ in range(3):
        saat[0] += 0.25; z.yokla()
    z.mock.pos = z.mock.hedef = z.mock._darbe(20.0)        # kart KOL 20 saniyor
    saat[0] += 0.25; z.yokla()
    assert abs(z.aci - aci_karsiligi(20.0)) < 0.1, z.aci
    assert z.sifirla()
    saat[0] += 0.25; z.yokla()
    # R = "kol SU AN en altta": kol 0, yani OPERATOR cercevesinde en alt uc.
    assert abs(z.aci - ACI_MIN) < 1e-9, f"sifirlama olmadi: {z.aci}"
    assert z.kalibre, "sifirlama kalibrasyonu SILMEMELI"
    assert not z.kart_resetlendi, "bilincli sifirlama 'kart resetlendi' sanildi"
    # kilitliyken (acik=0) sifirlama da reset sanilmamali
    z.mock.pos = z.mock.hedef = z.mock._darbe(15.0); z.mock.acik = False
    saat[0] += 0.25; z._oku()
    z.sifirla(); saat[0] += 0.25; z._oku()
    assert not z.kart_resetlendi, "kilitliyken sifirlama 'kart resetlendi' sanildi"
    # hareket halindeyken reddedilir
    saat[0] += 0.25; z.yokla(); saat[0] += 0.25; z.yokla()
    z.git(40.0); saat[0] += 0.12; z.yokla()
    z.sifirla(); saat[0] += 0.05; z._oku()
    assert z.aci > ACI_MIN + 0.5, "hareket ortasinda sifirlama kabul edildi"

    # 17. ⭐ YENIDEN PLANLAMA (retarget). Sahada takip ederken namlu titriyordu:
    #     kart hareket halinde yeni hedefi bekletiyor, kol her duzeltmede DURUP
    #     yeniden kalkiyordu (~1 sn'lik yaklasmada 6 dur-kalk olculdu).
    #     Yeni firmware Q'ya OK der; surucu o zaman hedefi BEKLETMEDEN gonderir.
    saat[0] += 1.0
    y = TiltSurucu("mock", _saat=lambda: saat[0])
    y.mock = MockTiltKart(simdi=saat[0], yeniden_planlama=True)
    for _ in range(3):
        saat[0] += 0.25; y.yokla()
    assert y.yeniden_planlama is True, "yeni firmware tanınmadı"
    y.git(0.0); saat[0] += 0.1; y.yokla()
    assert y.hareket
    y.git(25.0)                                   # hareket halinde — BEKLETILMEMELI
    assert y.mock.hedef == y.mock._darbe(kol_karsiligi(25.0)), "hedef hareket halinde bekletildi"
    assert y._bekleyen_hedef is None
    #     ayni hedef tekrar tekrar gelirse karta yeniden gitmez (seri hat bogulmasin)
    n = len([k for k in y.mock.kayit if k.startswith("G")])
    for _ in range(5):
        y.git(25.02)
    assert len([k for k in y.mock.kayit if k.startswith("G")]) == n
    #     eski firmware'de ise Q hata DEGIL, sessizce eski davranis
    assert s.yeniden_planlama is False and "tanımadı" not in (s.hata or ""), s.hata

    # 18. aci_zamaninda: gecmisten ara deger (gecikme telafisi bunun ustune kurulu)
    saat[0] += 1.0
    g = TiltSurucu("mock", _saat=lambda: saat[0])
    for _ in range(3):
        saat[0] += 0.25; g.yokla()
    g._aci_gecmisi = [(10.0, 20.0), (10.1, 22.0), (10.2, 26.0)]
    g.son_durum_t = saat[0] = 10.2
    assert abs(g.aci_zamaninda(10.05) - 21.0) < 1e-9
    assert abs(g.aci_zamaninda(10.15) - 24.0) < 1e-9
    assert g.aci_zamaninda(9.0) == 20.0 and g.aci_zamaninda(11.0) == 26.0

    # 12. mock kaynagi seri port acmaya CALISMAMALI (otomatik-bulma dali eklenince
    #     mock, seri acma koduna dusup "port acilamadi" hatasi uretmisti).
    m = TiltSurucu("mock")
    assert m.mock_mu and m.seri is None and m.hata is None, m.hata

    # 13. otomatik bulma: hicbir port STATE3 konusmuyorsa ACIKCA sebep yazilmali,
    #     sessizce "kapali" gibi davranmamali (operator neden calismadigini gorsun).
    #     NOT: yama BU modulun global adina yapilir. `import tilt_surucu` ile
    #     yamalamak calismaz — dosya __main__ olarak kostugunda o import IKINCI
    #     bir modul nesnesi yaratir ve TiltSurucu hala buradaki adi okur.
    _gercek_bul = otomatik_port_bul
    try:
        otomatik_port_bul = lambda dinleme=0.8, gunluk=None: None
        a = TiltSurucu("auto")
        assert not a.bagli and a.hata and "bulunamadı" in a.hata, a.hata
        otomatik_port_bul = lambda dinleme=0.8, gunluk=None: "COM_YOK_99"
        b = TiltSurucu("auto")
        assert not b.bagli and b.hata and "açılamadı" in b.hata, b.hata
    finally:
        otomatik_port_bul = _gercek_bul

    # 13c. YORUNGE KIPI: YQ ile yetenek ogrenilir; Y/PY referansi kart ilerletir,
    #      komut kesilince 150 ms icinde durur; eski firmware'de hic gonderilmez.
    saat = [7000.0]
    yk = TiltSurucu("mock", _saat=lambda: saat[0])
    yk.mock.t = yk.mock.son_canli = saat[0]
    for _ in range(3):
        saat[0] += 0.1; yk.yokla()
    assert yk.yorunge_destekli is True and "YQ" in yk.mock.kayit
    assert yorunge(12.5, 4) == f"Y{12.5 + KULLANICI_SIFIR:.3f},4.000\n"
    assert yorunge(99, 999) == f"Y{KOL_MAX:.3f},300.000\n"
    assert pan_yorunge(-5, -2.5) == "PY-5.000,-2.500\n"
    for i in range(20):                                   # 2 sn: 10 -> 20 derece @5 der/sn
        yk.yorunge(10.0 + 0.5 * i, 5.0); yk.pan_yorunge(1.0 * i, 10.0)
        saat[0] += 0.1; yk.yokla()
    assert abs(yk.aci - 19.5) < 1.0 and abs(yk.pan_aci - 19.0) < 1.5, (yk.aci, yk.pan_aci)
    once = (yk.aci, yk.pan_aci)
    for _ in range(5):                                    # komut YOK -> durmali
        saat[0] += 0.1; yk.yokla()
    assert abs(yk.aci - once[0]) < 1.0 and abs(yk.pan_aci - once[1]) < 1.5
    assert yk.mock.yor_tilt is None and yk.mock.yor_pan is None
    yk.yorunge(30.0, 0.0); yk.dur()
    assert yk.mock.yor_tilt is None and yk.mock.yor_pan is None   # X ikisini de keser
    ey = TiltSurucu("mock", _saat=lambda: saat[0])
    ey.mock.yorunge_destek = False
    ey.mock.t = ey.mock.son_canli = saat[0]
    for _ in range(3):
        saat[0] += 0.1; ey.yokla()
    assert ey.yorunge_destekli is False and ey.hata is None and not ey.yorunge(10, 1)
    assert not any(c.startswith("Y") and c != "YQ" for c in ey.mock.kayit)

    # 13b. operator <-> kamera acisi donusumu: monoton, tersinir, yerel egim tabloyu
    #      izler. Egim tablosu KOL acisinda olculdu; girdi operator acisidir.
    for a in (ACI_MIN, -22.7, -5.0, 14.0, 29.0):
        assert abs(kol_acisi(kamera_acisi(a)) - a) < 1e-6, a
    assert kamera_acisi(ACI_MIN) == 0.0, "kamera olceginin sifiri kolun EN ALTI"
    egim = lambda a: (kamera_acisi(a + 0.05) - kamera_acisi(a - 0.05)) / 0.1 * KAMERA_PPD_REF
    kol28, kol44 = aci_karsiligi(28.0), aci_karsiligi(44.0)
    assert abs(egim(kol28) - 13.5) < 0.2 and abs(egim(kol44) - 5.3) < 0.3, (egim(kol28), egim(kol44))
    assert all(kamera_acisi(a + 0.5) > kamera_acisi(a) for a in range(int(ACI_MIN), int(ACI_MAX)))

    # 14. PAN (ayni kart, GPIO10/11): PAN1 cozumu, P komutu, kademe, X ile durma
    assert pan_durum_coz("PAN1,984,984,0,10.003,10.003,-1")["aci"] == 10.003
    assert pan_durum_coz("PAN1,1,2,3,0,0,-1") is None and pan_durum_coz("STATE3,1") is None
    assert pan_git(12.5) == "P12.500\n" and pan_git(9999) == f"P{PAN_SINIR - 1:.3f}\n"
    assert max(h for h, _ in PAN_HIZ_TABLO.values()) * PAN_DARBE_DER <= PAN_HIZ_TAVAN
    assert max(iv for _, iv in PAN_HIZ_TABLO.values()) * PAN_DARBE_DER <= PAN_IVME_TAVAN
    saat = [9000.0]
    pn = TiltSurucu("mock", _saat=lambda: saat[0])
    pn.mock.t = pn.mock.son_canli = saat[0]
    for _ in range(3):
        saat[0] += 0.1; pn.yokla()
    assert pn.pan_destekli and pn.pan_aci == 0.0
    assert any(c.startswith("PZ") for c in pn.mock.kayit), pn.mock.kayit   # kademe bildirildi
    pn.pan_git(-20.0)
    assert pn.mock.kayit[-1] == "P-20.000", pn.mock.kayit[-1]
    n = len(pn.mock.kayit)
    pn.pan_git(-20.0)                                   # ayni hedef tekrar gitmez
    assert len(pn.mock.kayit) == n
    for _ in range(20):
        saat[0] += 0.1; pn.yokla()
    assert abs(pn.pan_aci + 20.0) < 0.02, pn.pan_aci
    pn.pan_git(30.0); saat[0] += 0.1; pn.yokla()
    assert pn.pan_durum["hareket"]
    pn.dur(); saat[0] += 0.1; pn.yokla()
    assert not pn.pan_durum["hareket"] and pn.pan_aci < 30.0
    pn.pan_sifirla(); saat[0] += 0.1; pn.yokla()
    assert pn.pan_aci == 0.0
    eski = TiltSurucu("mock", _saat=lambda: saat[0])     # eski firmware: PAN1 yok
    eski.mock.pan_destek = False
    eski.mock.t = eski.mock.son_canli = saat[0]
    for _ in range(3):
        saat[0] += 0.1; eski.yokla()
    assert not eski.pan_destekli and eski.pan_git(5.0) is None
    # Pan sayaci kontrol KAPALIYKEN 0'a donerse (ESP reseti) yakalanir — kol 0'dayken bile
    rs = TiltSurucu("mock", _saat=lambda: saat[0])
    rs.mock.t = rs.mock.son_canli = saat[0]
    for _ in range(3):
        saat[0] += 0.1; rs.yokla()
    rs.pan_git(10.0)
    for _ in range(10):
        saat[0] += 0.1; rs.yokla()
    assert rs.pan_aci > 9.0 and not rs.kart_resetlendi
    rs.mock.pan_pos = rs.mock.pan_hedef = 0; rs.mock.acik = False     # reset taklidi
    saat[0] += 0.1; rs.yokla()
    assert rs.kart_resetlendi
    assert not any(c.startswith("P") for c in eski.mock.kayit)

    # ---- 24.09 saha: acilis yukselisi (R + G30) ----
    def yeni_kart():
        k = TiltSurucu("mock", _saat=lambda: saat[0])
        k.mock.t = k.mock.son_canli = saat[0]
        return k

    def kos(k, sure, adim=YOKLAMA_MS / 1000.0):
        for _ in range(int(round(sure / adim))):
            saat[0] += adim
            k.yokla()

    # (a) Kart onceki oturumdan 30 derecede (operator 0). R + hemen G0: eski durum "zaten
    # orada" dedirtip hedefi ATMAMALI — kol 0'dan 30 dereceye kalkmali.
    r1 = yeni_kart(); kos(r1, 0.3)
    r1.git(0.0); kos(r1, 2.0)
    assert abs(r1.mock.pos - r1.mock._darbe(30.0)) <= 2, r1.mock.pos
    r1.sifirla()
    assert not r1.hazir, "R sonrasi ilk durumdan once hareket kabul edildi"
    r1.git(0.0); kos(r1, 2.0)
    assert abs(r1.mock.pos - r1.mock._darbe(30.0)) <= 2, \
        f"R'den sonra G30 atildi, kol kalkmadi (pos {r1.mock.pos})"
    # (b) R'den ONCE yazilmis STATE3 tamponda: eski sayac alinmamali (ne hedef atilir ne de
    # sonraki 0 sayac "kart reseti" sanilir)
    r1.sifirla(); r1._r_ok = False                     # OK,R henuz okunmadi
    r1._kart_yaziyor("STATE3,3200,3200,6400,1,0,0,0,30.000,30.000,2,60.000,400")
    assert r1._son_pos == 0 and not r1.kart_resetlendi
    r1._kart_yaziyor("OK,R")
    r1._kart_yaziyor("STATE3,0,0,6400,1,0,0,0,0.000,0.000,2,60.000,400")
    assert not r1.kart_resetlendi and r1.durum["pos"] == 0 and r1._r_t is None
    # (c) OK,R hic gelmezse surucu sonsuza dek kilitli kalmaz
    r1.sifirla(); r1._r_ok = False
    saat[0] += R_BEKLEME_S + 0.1
    assert not r1._r_bekleniyor()

    # (d) Yukselis sirasinda arayuz takildi (H yok) -> kart kilitlendi, kol yarida kaldi.
    # Kilit acilinca ayni hedef yeniden gitmeli.
    r2 = yeni_kart(); kos(r2, 0.3)
    r2.git(0.0); kos(r2, 0.25)
    yarim = r2.mock.pos
    assert 0 < yarim < r2.mock._darbe(30.0) - 50, yarim
    saat[0] += 0.8; r2._oku()                           # 0.8 sn donma
    assert not r2.mock.acik
    kos(r2, 3.0)
    assert abs(r2.mock.pos - r2.mock._darbe(30.0)) <= 2, \
        f"canlilik asiminden sonra hedef yeniden gitmedi (pos {r2.mock.pos})"
    # ... ama dur() ile KESILEN hedef kilit acilinca geri gelmez
    r2.git(-30.0); kos(r2, 0.25)
    r2.dur(); kos(r2, 0.2)
    durdu = r2.mock.pos
    saat[0] += 0.8; r2._oku()
    kos(r2, 2.0)
    assert r2.mock.acik and r2.mock.pos == durdu, "dur() ile kesilen hedef geri geldi"

    # (e) Arayuz zamanlayicisi YOKLAMA_MS iken H araligi asimin yarisindan kucuk
    r3 = yeni_kart(); kos(r3, 0.3)
    once = len([c for c in r3.mock.kayit if c == "H"])
    kos(r3, 1.2)
    h = len([c for c in r3.mock.kayit if c == "H"]) - once
    assert h >= 8, f"1.2 sn'de yalniz {h} H (en fazla ~150 ms aralik bekleniyor)"
    assert CANLILIK_MS + YOKLAMA_MS <= ZAMAN_ASIMI_MS / 2

    print("tilt_surucu testleri OK — G bicimi, STATE3 cozumu, en-taze-hedef kuyrugu, "
          "canlilik kilidi, kalibrasyon kapisi, kirpma, kart reset tespiti")
