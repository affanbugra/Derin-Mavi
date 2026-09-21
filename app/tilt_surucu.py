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
import time

# ---- Kart sabitleri (ws_motor_test/esp32_ws_test/motion_core.h ile AYNI olmali) ----
ACI_MIN, ACI_MAX = 0.0, 60.0        # kol calisma araligi — MEKANIK, 180 DEGIL
BAUD = 115200
NOKTA_MAKS = 16                     # MotionCore::CAPACITY
ZAMAN_ASIMI_MS = 350                # MotionCore::TIMEOUT_MS — bu sure sessizlikte kart kilitlenir
CANLILIK_MS = 120                   # biz bu sikligda "H" yolluyoruz (asiminin ~1/3'u)
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

# Kartin "durum yok" kabul ettigimiz suresi: STATE3 100 ms'de bir gelir; 3 paket
# kacarsa bagi kopmus sayariz (arayuz de oyle gosterir).
DURUM_ASIMI_S = 0.6

KAYNAK = os.environ.get("DERINMAVI_TILT", "off").strip() or "off"

# ESP32-S3'un IKI USB yolu vardir ve hangisine kablo takiliysa BASKA bir COM
# numarasi cikar — sahada "bir seferinde COM3, bir seferinde COM4" tam olarak budur:
#   VID 303A = Espressif NATIVE USB  (kartin kendi USB soketi)
#   VID 1A86 = WCH CH343/CH340       (harici seri cip, UART0)
# Firmware IKISINI DE dinler (Serial + Serial0), yani ikisi de gecerlidir; sorun
# yalnizca numarayi elle yazmaktir. `DERINMAVI_TILT=auto` bu isi bitirir.
ESP_VIDLER = (0x303A, 0x1A86)


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
    """Kol araligina kirpar. Kart da kendi tarafinda kirpar/reddeder (BAD_ANGLE);
    tek tarafa guvenilmez — seri monitorden elle G500 yazan biri de olabilir."""
    return max(ACI_MIN, min(ACI_MAX, float(derece)))


# ---- komut ureticiler (tek cikis noktasi: kimse elle string kurmaz) ----
AC = "E\n"          # kontrolu ac
KAPAT = "D\n"       # durdur + kontrolu kapat
DUR = "X\n"         # durdur, bekleyen hedefi iptal et
CANLI = "H\n"       # heartbeat


def git(derece):
    """MUTLAK hedef aci. Firmware strtod ile okur; keyboard_control.py ile ayni
    bicim kullanilir ki kart iki istemciden ayni sayiyi gorsun."""
    return f"G{aci_kirp(derece):.4f}\n"


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
        if not math.isfinite(last_angle) or not ACI_MIN <= last_angle <= ACI_MAX:
            return None
        if cal and (count < 2 or last_angle != ACI_MAX):
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
            if not ACI_MIN <= angle <= ACI_MAX or not ACI_MIN <= goal <= ACI_MAX:
                return None
        elif upper != 0 or angle != -1 or goal != -1:
            return None
        return dict(pos=pos, target=target, upper=upper, kalibre=bool(cal),
                    hareket=bool(moving), acik=bool(armed),
                    kalibrasyonda=bool(commissioning), aci=angle, hedef=goal,
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
    'BAD_ANGLE': 'Tilt açısı 0–60 arasında olmalı.',
    'BAD_SPEED': 'Tilt jog hızı 100, 400 veya 800 olmalı.',
    'BAD_CAL_POINT': 'Tilt kalibrasyon noktası reddedildi.',
    'CAL_SAVE_FAILED': 'Tilt kalibrasyonu kartın belleğine yazılamadı. Kontrol kapatıldı.',
    'LINE_TOO_LONG': 'Tilt seri komutu bozuldu. Bağlantı yenileniyor.',
    'OTHER_PORT_ACTIVE': 'Tilt kartı başka bir uygulamada açık (keyboard_control.py?). Onu kapat.',
    'PULSE_RANGE': 'Tilt darbe sayacı aralık dışına çıktı.',
    'UNKNOWN_COMMAND': 'Tilt kartı komutu tanımadı (firmware sürümü eski olabilir).',
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

    def __init__(self, kalibre=True, simdi=None):
        self.pos = 0
        self.hedef = 0
        self.acik = False
        self.bekleyen = None
        self.jog = 400
        self.maks_hiz = self.MAKS_HIZ      # Z komutuyla degisir
        self.ivme = 12800.0                # ACCEL_VARSAYILAN (mock ivmeyi UYGULAMAZ)
        self.kalibre = kalibre
        self.son_canli = simdi if simdi is not None else time.time()
        self.t = self.son_canli
        self.kayit = []             # gonderilen komutlar (test icin)

    # --- kalibrasyon tablosu (dogrusal varsayim; mock icin yeterli) ---
    def _aci(self, darbe):
        return darbe * ACI_MAX / self.UST_DARBE

    def _darbe(self, aci):
        return int(round(aci * self.UST_DARBE / ACI_MAX))

    def islet(self, satir, simdi=None):
        """Bir komut satirini isler; kartin yazacagi yaniti (yoksa None) doner."""
        simdi = self.t if simdi is None else simdi
        s = satir.strip()
        self.kayit.append(s)
        self._watchdog(simdi)
        if s == "X":
            self.hedef = self.pos
            self.bekleyen = None
            return "OK,X"
        if s == "D":
            self.hedef = self.pos
            self.bekleyen = None
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
            if not math.isfinite(a) or a < ACI_MIN or a > ACI_MAX:
                return f"ERR,{s},BAD_ANGLE"
            if not self.kalibre:
                return f"ERR,{s},CAL_REQUIRED"
            self.son_canli = simdi
            t = self._darbe(a)
            if self.pos != self.hedef:
                self.bekleyen = t           # TEK YUVA — mevcut hedef once bitecek
            else:
                self.hedef = t
            return f"OK,{s}"
        return f"ERR,{s},UNKNOWN_COMMAND"

    def _watchdog(self, simdi):
        if self.acik and (simdi - self.son_canli) * 1000.0 >= ZAMAN_ASIMI_MS:
            self.hedef = self.pos
            self.bekleyen = None
            self.acik = False

    def ilerlet(self, simdi):
        """Zamani `simdi`ye tasir: motoru hedefe dogru surer, STATE3 satirlarini uretir."""
        satirlar = []
        while self.t < simdi - 1e-9:
            adim = min(0.1, simdi - self.t)     # 100 ms'lik STATE3 periyodu
            self.t += adim
            self._watchdog(self.t)
            if self.acik and self.pos != self.hedef:
                yon = 1 if self.hedef > self.pos else -1
                git_darbe = int(self.maks_hiz * adim)
                kalan = abs(self.hedef - self.pos)
                self.pos += yon * min(git_darbe, kalan)
            if self.pos == self.hedef and self.bekleyen is not None:
                self.hedef, self.bekleyen = self.bekleyen, None
            satirlar.append(self.state3())
        return satirlar

    def state3(self):
        kal = 1 if self.kalibre else 0
        ust = self.UST_DARBE if self.kalibre else 0
        aci = self._aci(self.pos) if self.kalibre else -1.0
        hed = self._aci(self.hedef) if self.kalibre else -1.0
        nokta = 2 if self.kalibre else 1
        son = ACI_MAX if self.kalibre else 0.0
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
        self.hiz_seviye = HIZ_VARSAYILAN
        self._gonderilen_hiz = None     # karta en son giden (hiz, ivme) — None = gonderilmedi
        # Karttaki firmware "Z" komutunu tanimiyorsa (eski surum yuklu) hiz kademesi
        # calismaz. Hareketin geri kalani calismaya DEVAM EDER: G/E/H/X/D eski
        # surumde de var. Bu yuzden bu durum bir HATA degil, bir UYARIDIR.
        self.hiz_desteklenmiyor = False
        self.kalibrasyon_uyarildi = False
        # Kart RESET ATTI mi? (bkz. _kart_yaziyor) — arayuz bunu operatore GORUNUR
        # sekilde soylemeli; sessiz kalirsa aci referansi bozulmus olarak devam eder.
        self.kart_resetlendi = False

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
            baglanti.port = self.kaynak.upper()
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
        """Hareket komutu KABUL EDILIR mi? (bagli + taze durum + acik + kalibre)"""
        return bool(self.bagli and self.taze and self.durum["acik"] and self.durum["kalibre"])

    @property
    def aci(self):
        """Kartin BILDIRDIGI kol acisi (derece) — komut edilen degil. Durum yoksa None.

        Bu, laptopun 'inandigi' aciden farklidir ve arayuzun dikey aci referansi
        BU olmalidir: komut kaybolur/gecikirse fark buradan kapanir."""
        return self.durum["aci"] if (self.taze and self.durum["kalibre"]) else None

    @property
    def hedef_aci(self):
        return self.durum["hedef"] if (self.taze and self.durum["kalibre"]) else None

    @property
    def darbe_per_derece(self):
        """Kalibrasyondan turer: ust sinir darbesi / 60 derece. Mekanizma yeniden
        kalibre edilirse hiz kademeleri KENDILIGINDEN dogru kalir."""
        if not (self.taze and self.durum["kalibre"]) or self.durum["upper"] <= 0:
            return None
        return self.durum["upper"] / ACI_MAX

    def hiz_ayarla(self, seviye):
        """Hiz kademesini secer (Z komutu). Kart mesgul/hazir degilse BEKLETILIR.

        Kademe DERECE cinsinden tanimlidir; darbeye burada, kartin bildirdigi
        kalibrasyona gore cevrilir."""
        self.hiz_seviye = seviye if seviye in HIZ_TABLO else HIZ_VARSAYILAN
        self._hiz_bosalt()
        return self.hiz_seviye

    def _hiz_bosalt(self):
        """Secili kademeyi, kart uygun durumdayken karta bildirir.

        Firmware Z'yi yalnizca DURURKEN kabul eder (hareket ortasinda profil
        degistirmek rampayi tutarsiz birakir), bu yuzden gonderim ertelenebilir."""
        if self.hiz_desteklenmiyor or not self.hazir or self.durum["hareket"]:
            return False
        dpd = self.darbe_per_derece
        if dpd is None:
            return False
        der_hiz, der_ivme = HIZ_TABLO[self.hiz_seviye]
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
        if satir != CANLI:
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

    def _kart_yaziyor(self, s):
        self.durum_satiri = s
        if s.startswith("STATE3,"):
            self._kk_state_sayac = getattr(self, "_kk_state_sayac", 0) + 1
            if self._kk_state_sayac % 10 == 0:
                self._kara_kutu_yaz("<<", s)
        else:
            self._kara_kutu_yaz("<<", s)
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
                # Kart acilis degerlerine dondu: hiz profili yeniden bildirilmeli,
                # yoksa kol sessizce firmware varsayilaninda kalir.
                self._gonderilen_hiz = None
            self._son_pos = d["pos"]
            self.durum = d
            self.son_durum_t = self._saat()
            return
        self.satirlar.append(s)
        self._yeni.append(s)
        del self.satirlar[:-20]
        if s.startswith("ERR,"):
            sebep = s.split(',')[-1]
            # ESKI FIRMWARE: "Z" komutu yok. Hiz kademesi calismaz ama hareketin
            # geri kalani calisir (G/E/H/X/D eski surumde de var). Bir kez soylenir
            # ve bir daha DENENMEZ — yoksa her kademe degisiminde ayni hata dusuerdi.
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
        while "\n" in self._rx:
            satir, self._rx = self._rx.split("\n", 1)
            satir = satir.strip()
            if satir:
                self._kart_yaziyor(satir)
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
        # Hiz profili HEDEFTEN ONCE gider: hedef once gonderilirse kart hareketi
        # eski profille baslatir ve Z artik "hareket halinde" diye reddedilir.
        self._hiz_bosalt()
        self._bosalt()
        self._oku()
        self._kara_kutu_sessizlik()
        return self.ozet()

    def git(self, derece):
        """MUTLAK kol acisi komutu (0..60). Kart mesgulse PC tarafinda BEKLETILIR.

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
        if self.durum["hareket"]:
            return None
        hedef = self._bekleyen_hedef
        # Kartin BILDIRDIGI aciya yeterince yakinsak komut gonderme. Esik kartin
        # kendi cozunurlugunun (darbe basina aci) altina inmemeli; 0.05 derece
        # 6400 darbe/60 derece'de ~5 darbedir.
        simdiki = self.durum["aci"]
        if simdiki is not None and abs(hedef - simdiki) < 0.05:
            self._bekleyen_hedef = None
            return None
        self._bekleyen_hedef = None
        self._gonderilen_hedef = hedef
        self._yaz(git(hedef))
        return hedef

    def dur(self):
        """Hareketi kes ve bekleyen hedefi iptal et (E-Stop / hedef kaybi)."""
        self._bekleyen_hedef = None
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
    # ---- komut bicimi: kart strtod ile okur, keyboard_control.py ile AYNI bicim ----
    assert git(12.5) == "G12.5000\n"
    assert git(-5) == "G0.0000\n" and git(500) == f"G{ACI_MAX:.4f}\n"
    assert aci_kirp(-1) == 0.0 and aci_kirp(61) == 60.0
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
    assert d["aci"] == 30.0 and d["pos"] == 3200, d
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
        return [float(k[1:]) for k in s.mock.kayit if k.startswith("G")]

    tik()
    assert s.taze and s.kalibre, s.durum
    # Kart acilista KILITLIDIR; yokla() E yollar ama durum bir sonraki STATE3'te
    # tazelenir (gercek kartta da 100 ms'lik yayin periyodu kadar gecikir).
    assert not s.acik, "acilista kart kilitli olmaliydi"
    tik()
    assert s.acik, "yokla() kilitli karti kendiliginden acmaliydi"

    # 1. MUTLAK aci komutu kartta hedefe donusur
    s.git(30.0)
    tik()
    assert s.mock.hedef == 3200, s.mock.hedef
    assert s.hareket, "30 dereceye giderken kart HAREKET halinde olmali"

    # 2. ⭐ ASIL MESELE: hareket halindeyken gelen hedefler KARTA GIRMEZ, en
    #    tazesi beklerAksi halde firmware'in tek yuvasi BAYAT hedefi uygular.
    s.git(10.0)
    s.git(45.0)
    s.git(20.0)                      # en tazesi bu
    assert s.mock.bekleyen is None, "karta bayat hedef sizdi"
    assert s._bekleyen_hedef == 20.0

    # 3. Kart bosalinca yalniz EN TAZE hedef gider. Karta giden komutlar tam olarak
    #    [30 (ilk), 20 (en taze)] olmali — arada gelen 10 ve 45 HIC gitmemeli.
    assert yerles(), "kart yerlesmedi"
    assert abs(s.aci - 20.0) < 0.5, f"en taze hedefe gidilmedi: {s.aci}"
    assert gonderilen_hedefler() == [30.0, 20.0], gonderilen_hedefler()

    # 4. Olu bolge: ayni aciya tekrar komut gonderilmez
    n = len(gonderilen_hedefler())
    s.git(20.0)
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
    s.git(50.0)
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
    assert h.hazir and abs(h.darbe_per_derece - MockTiltKart.UST_DARBE / ACI_MAX) < 1e-9
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

    print("tilt_surucu testleri OK — G bicimi, STATE3 cozumu, en-taze-hedef kuyrugu, "
          "canlilik kilidi, kalibrasyon kapisi, kirpma, kart reset tespiti")
