"""Harekete / atışa İZİNLİ PENCERELER — şartname §4.2 güvenlik hususu.

[KESİN] Şartname: "Sistemin sadece hedeflerin yer alacağı tarafa bakmasına izin
verilecektir. Kesinlikle tanımlanan yasak bölgeye dönmesine izin verilmeyecek...
Bu atışa yasak alan ile karıştırılmamalıdır. Sistemlerin hem harekete yasak alan
hem de atışa yasak alan tanımlama fonksiyonlarının olması beklenmektedir."

MODEL (takım kararı 21.09.2026): operatör YASAK aralığı değil, İZİN VERİLEN
pencereyi yazar; pencerenin dışı yasaktır. Her eksende iki pencere vardır:
  * hareket penceresi — gimbal bu aralığın DIŞINA çıkamaz (sınırda KIRPILIR,
    komut reddedilmez: sınıra 3° kalmışken 5°'lik adım 3° gider),
  * atış penceresi   — lazer yalnız bu aralığın İÇİNDE açılabilir; dışına
    çıkılırsa ateş KESİLİR.
İkisi "harmanlıdır": atış penceresi hareket penceresinin dışına taşamaz
(`atis_uyumla`) — gidilemeyen yerde ateş izni anlamsızdır.

BİRİMLER (operatörün düşündüğü gibi):
  * Yatay (pan): ÖN = 0°, sağa +, sola − (−180..+180). Fiziksel sınır YOK, 360°
    döner; pencere ön taraf etrafında tanımlanır ki arkadan dolanıp yasak
    bölgeye girilemesin.
  * Dikey (tilt): operatör çalışma açısı, yere paralel = 0°, −25..+25.
    Kartın fiziksel 0..60 ham açısına dönüşüm yalnız tilt_surucu.py içinde yapılır.

Bu modül Qt'ye bağlı değildir: `python app/bolge.py` kendi testlerini koşar.
"""
from dataclasses import dataclass, field

# [KESİN — kullanıcı bilgisi 21.09.2026] dikey mekanik aralık toplam 60°:
TILT_FIZIKSEL_ALT = -30.0      # operatör alt sınırı
TILT_ARALIK = 60.0             # toplam mekanik hareket

# [KESİN — kullanıcı kararı 22.09.2026] YATAY ÇALIŞMA SINIRI.
# Operatör aracın ARKASINDA durur; namlunun onun eksenine girmesi kabul edilemez
# (şartname §4.2: "sadece hedeflerin yer alacağı tarafa bakmasına izin verilecek").
# Bu bir operatör tercihi DEĞİL, tilt'teki 60° gibi yapısal bir sınırdır: hareket
# penceresi kapalı olsa bile uygulanır, pencere yalnız bu aralığı DARALTABİLİR.
# ⚠ BU UC SAYI YARISMA GUNU ARAYUZDEN DEGISTIRILEBILIR (⚙ → SINIRLAR).
# Kodun icine gomulu, operatorun goremedigi bir sinir BIRAKILMAZ: sahada
# "neden bu aciya gitmiyor" sorusunun cevabi ekranda gorunur olmalidir.
# Degeri `sinirlari_ayarla()` degistirir; asagidaki fonksiyonlar her cagrida
# GUNCEL degeri okur (varsayilan argumana baglanmaz — oyle olsaydi arayuzden
# yapilan degisiklik hicbir ise yaramazdi).
PAN_MAX = 60.0                 # ön = 0°, sağa +60, sola −60
TILT_CALISMA_MIN = -25.0       # fiziksel mekanik aralık hâlâ −30…+30
TILT_CALISMA_MAX = 25.0


def sinirlari_ayarla(yatay=None, dikey_alt=None, dikey_ust=None):
    """Calisma sinirlarini degistirir (arayuzdeki SINIRLAR bolumunden gelir)."""
    global PAN_MAX, TILT_CALISMA_MIN, TILT_CALISMA_MAX
    if yatay is not None:
        PAN_MAX = max(1.0, min(180.0, float(yatay)))
    if dikey_alt is not None:
        TILT_CALISMA_MIN = float(dikey_alt)
    if dikey_ust is not None:
        TILT_CALISMA_MAX = float(dikey_ust)
    if TILT_CALISMA_MIN > TILT_CALISMA_MAX:            # ters girildi: tek nokta
        TILT_CALISMA_MAX = TILT_CALISMA_MIN
    return PAN_MAX, TILT_CALISMA_MIN, TILT_CALISMA_MAX


def tilt_fiziksel(operator_acisi):
    """Geriye uyumlu ad: arayüz ve fiziksel açı artık aynı çerçevededir."""
    return float(operator_acisi)


def tilt_sistem(fiziksel):
    return float(fiziksel)


def pan_isaretli(pan):
    """Herhangi bir azimut -> ön taraf etrafında işaretli açı (−180..+180)."""
    return ((float(pan) + 180.0) % 360.0) - 180.0


@dataclass
class Pencere:
    aktif: bool = False
    alt: float = -30.0
    ust: float = 30.0

    def icinde(self, x):
        return (not self.aktif) or (self.alt <= x <= self.ust)


@dataclass
class Bolgeler:
    """Hazır ayarlar (takım kararı 22.09): pencereler KAPALI gelir ama kutular
    makul değerlerle dolu olur — operatör anahtarı açınca hemen kullanılabilir bir
    aralık bulur, sıfırdan sayı girmesi gerekmez.

    * hareket: yatay ±60 · dikey ±25 (yapısal çalışma sınırları)
    * atış   : yatay ±30 · dikey ±15 — ateş alanı hareket alanından DAR başlar;
      güvenli taraf budur (gidilebilen her yere ateş izni vermek değil)."""
    hareket_pan: Pencere = field(default_factory=lambda: Pencere(True, -PAN_MAX, PAN_MAX))
    hareket_tilt: Pencere = field(default_factory=lambda: Pencere(True, TILT_CALISMA_MIN, TILT_CALISMA_MAX))
    atis_pan: Pencere = field(default_factory=lambda: Pencere(False, -30.0, 30.0))
    atis_tilt: Pencere = field(default_factory=lambda: Pencere(False, -15.0, 15.0))


# durum kodları (arayüz şeridi bunlara göre renk/metin seçer)
SERBEST, KIRPILDI, ENGELLENDI = "serbest", "kirpildi", "engellendi"


def pencere_kirp(cur, hedef, alt, ust):
    """1 boyutlu hareketi [alt, ust] penceresine uydurur. Doner: (yeni, durum).

    İçerideyken: hedef sınırda kırpılır (asla dışarı çıkılmaz).
    Dışarıdayken (pencere yeni açıldıysa): yalnız pencereye DOĞRU harekete izin
    verilir — uzaklaşan komut engellenir, yaklaşan komut pencere içinde durur."""
    if alt <= cur <= ust:
        yeni = min(max(hedef, alt), ust)
        return yeni, (SERBEST if yeni == hedef else KIRPILDI)
    if cur < alt:
        if hedef <= cur:
            return cur, ENGELLENDI
        yeni = min(hedef, ust)
        return yeni, (SERBEST if yeni == hedef else KIRPILDI)
    if hedef >= cur:                                    # cur > ust
        return cur, ENGELLENDI
    yeni = max(hedef, alt)
    return yeni, (SERBEST if yeni == hedef else KIRPILDI)


def pan_hareket(pan_ham, d_pan, pencere, pan_max=None):
    """Sarmasız azimut (karta giden) + delta -> (yeni_pan_ham, durum).

    Önce YAPISAL sınır (±pan_max, sessiz kırpma — tilt'teki 0..60 ile aynı kural),
    sonra varsa operatörün hareket penceresi. Hareket işaretli açıda SÜREKLİ
    hesaplanır (sarmaz): gimbal arkadan dolanarak yasak bölgeye geçemez."""
    pan_max = PAN_MAX if pan_max is None else pan_max      # GUNCEL sinir (bkz. yukarisi)
    cur = pan_isaretli(pan_ham)
    # Kart açılışta pencere dışı bir açı bildirebilir. İlk küçük komutun hedefi
    # doğrudan ±60'a sıçramamalı; yalnız güvenli tarafa adım adım dönülebilir.
    if cur > pan_max:
        if d_pan >= 0:
            return pan_ham, ENGELLENDI
        hedef = max(pan_max, cur + d_pan)
        return pan_ham + (hedef - cur), KIRPILDI if hedef == pan_max else SERBEST
    if cur < -pan_max:
        if d_pan <= 0:
            return pan_ham, ENGELLENDI
        hedef = min(-pan_max, cur + d_pan)
        return pan_ham + (hedef - cur), KIRPILDI if hedef == -pan_max else SERBEST
    hedef = max(-pan_max, min(pan_max, cur + d_pan))
    if not pencere.aktif:
        return pan_ham + (hedef - cur), SERBEST
    yeni, durum = pencere_kirp(cur, hedef, pencere.alt, pencere.ust)
    return pan_ham + (yeni - cur), durum


def tilt_hareket(tilt_sistem_aci, d_tilt, pencere, sistem_max=None, sistem_min=None):
    """Operatör tilt açısını mekanik ve izinli pencereye kırpar."""
    sistem_max = TILT_CALISMA_MAX if sistem_max is None else sistem_max
    sistem_min = TILT_CALISMA_MIN if sistem_min is None else sistem_min
    # Açılışta kol fiziksel -30'da olabilir. Kullanıcı bu konumdan daha aşağı
    # istemişse kırpma onu ters yönde -25'e yürütmesin; yalnız içeri dönüş serbest.
    if (tilt_sistem_aci < sistem_min and d_tilt <= 0) or (tilt_sistem_aci > sistem_max and d_tilt >= 0):
        return tilt_sistem_aci, ENGELLENDI
    hedef = max(float(sistem_min), min(float(sistem_max), tilt_sistem_aci + d_tilt))
    if not pencere.aktif:
        return hedef, SERBEST
    cur_f = tilt_fiziksel(tilt_sistem_aci)
    yeni_f, durum = pencere_kirp(cur_f, tilt_fiziksel(hedef), pencere.alt, pencere.ust)
    return tilt_sistem(yeni_f), durum


def atis_izinli(pan, tilt_sistem_aci, b):
    """Şu anki yönde lazer açılabilir mi? (iki eksenin atış penceresi birlikte)"""
    return (b.atis_pan.icinde(pan_isaretli(pan))
            and b.atis_tilt.icinde(tilt_fiziksel(tilt_sistem_aci)))


def atis_uyumla(b):
    """"Harmanlama": atış penceresi hareket penceresinin dışına taşamaz.
    Hareket penceresi aktifken atış penceresi onun içine kırpılır. Kesişim boşsa
    atış penceresi tek noktaya iner (pratikte hiç ateş edilemez) — sessizce
    'her yer serbest'e dönmesinden güvenlidir."""
    for hareket, atis in ((b.hareket_pan, b.atis_pan), (b.hareket_tilt, b.atis_tilt)):
        if hareket.aktif and atis.aktif:
            atis.alt = max(atis.alt, hareket.alt)
            atis.ust = min(atis.ust, hareket.ust)
            if atis.alt > atis.ust:
                atis.ust = atis.alt
    return b


# =====================================================================
#  Kendi kendini test
# =====================================================================
if __name__ == "__main__":
    # birim dönüşümleri
    assert tilt_fiziksel(0) == 0 and tilt_fiziksel(-30) == -30 and tilt_sistem(30) == 30
    assert pan_isaretli(350) == -10 and pan_isaretli(10) == 10 and pan_isaretli(-190) == 170

    # pencere içinde kırpma
    assert pencere_kirp(17, 22, -20, 20) == (20, KIRPILDI)
    assert pencere_kirp(0, 5, -20, 20) == (5, SERBEST)
    # dışarıdayken: uzaklaşma engellenir, yaklaşma serbest
    assert pencere_kirp(25, 30, -20, 20) == (25, ENGELLENDI)
    assert pencere_kirp(25, 18, -20, 20) == (18, SERBEST)

    # dikey: pencere ve komut ayni operator acisinda
    t = Pencere(True, -20.0, 20.0)
    assert tilt_hareket(10.0, 20.0, t) == (20.0, KIRPILDI)
    assert tilt_hareket(-15.0, -10.0, t) == (-20.0, KIRPILDI)
    assert tilt_hareket(0.0, 5.0, t) == (5.0, SERBEST)
    # çalışma sınırı pencere kapalıyken de geçerli (−25..+25)
    assert tilt_hareket(20.0, 20.0, Pencere()) == (25.0, SERBEST)
    assert tilt_hareket(-20.0, -20.0, Pencere()) == (-25.0, SERBEST)
    assert tilt_hareket(-30.0, -1.0, Pencere()) == (-30.0, ENGELLENDI)
    assert tilt_hareket(-30.0, 30.0, Pencere(True, -25.0, 25.0)) == (0.0, SERBEST)

    # yatay YAPISAL sınır: pencere KAPALI olsa da ±60'ın ötesine geçilemez
    assert pan_hareket(50.0, 20.0, Pencere()) == (60.0, SERBEST)
    assert pan_hareket(-50.0, -20.0, Pencere()) == (-60.0, SERBEST)
    assert pan_hareket(60.0, 5.0, Pencere()) == (60.0, SERBEST)      # sınırda dururuz
    assert pan_hareket(-10.0, -20.0, Pencere()) == (-30.0, SERBEST)  # içeride serbest
    # arkadan dolanma: −60'tan sola devam edilemez
    assert pan_hareket(-60.0, -30.0, Pencere()) == (-60.0, SERBEST)
    assert pan_hareket(120.0, -1.0, Pencere()) == (119.0, SERBEST)
    assert pan_hareket(120.0, 1.0, Pencere()) == (120.0, ENGELLENDI)

    # yatay pencere: yapısal sınırı yalnız DARALTABİLİR
    p = Pencere(True, -45.0, 45.0)
    assert pan_hareket(40.0, 20.0, p) == (45.0, KIRPILDI)
    assert pan_hareket(-40.0, -20.0, p) == (-45.0, KIRPILDI)
    ham, d = pan_hareket(360.0 + 40.0, 20.0, p)                # tam tur sonrası da aynı
    assert (ham, d) == (405.0, KIRPILDI), (ham, d)

    # hazır ayarlar: hareket sınırları açılışta etkin
    v = Bolgeler()
    assert v.hareket_pan.aktif and v.hareket_tilt.aktif
    assert not v.atis_pan.aktif and not v.atis_tilt.aktif
    assert (v.hareket_pan.alt, v.hareket_pan.ust) == (-PAN_MAX, PAN_MAX)
    assert (v.hareket_tilt.alt, v.hareket_tilt.ust) == (TILT_CALISMA_MIN, TILT_CALISMA_MAX)
    assert (v.atis_pan.alt, v.atis_pan.ust) == (-30.0, 30.0)
    assert (v.atis_tilt.alt, v.atis_tilt.ust) == (-15.0, 15.0)
    # atis alani hareket alanindan DAR baslamali (harmanlama sonrasi da bozulmamali)
    atis_uyumla(v)
    assert (v.atis_pan.alt, v.atis_pan.ust) == (-30.0, 30.0)

    # atış: iki eksen birlikte
    b = Bolgeler()
    b.atis_pan = Pencere(True, -30.0, 30.0)
    b.atis_tilt = Pencere(True, -10.0, 10.0)
    assert atis_izinli(10.0, 0.0, b)            # pan +10, tilt yatay
    assert atis_izinli(350.0, 0.0, b)           # pan −10 (sarmalı gösterim)
    assert not atis_izinli(45.0, 0.0, b)        # pan dışarıda
    assert not atis_izinli(0.0, 20.0, b)        # tilt +20 dışarıda

    # harmanlama: atış penceresi hareket penceresine kırpılır
    b = Bolgeler(hareket_tilt=Pencere(True, -20.0, 20.0), atis_tilt=Pencere(True, -30.0, 10.0))
    atis_uyumla(b)
    assert (b.atis_tilt.alt, b.atis_tilt.ust) == (-20.0, 10.0)
    b = Bolgeler(hareket_pan=Pencere(True, -10.0, 10.0), atis_pan=Pencere(True, 40.0, 60.0))
    atis_uyumla(b)
    assert b.atis_pan.alt == b.atis_pan.ust == 40.0             # kesişim yok -> tek nokta
    assert not atis_izinli(0.0, 0.0, b)

    print("bolge testleri OK — birimler, pencere kırpma, dikey/yatay hareket, "
          "sarma koruması, atış penceresi, harmanlama")
